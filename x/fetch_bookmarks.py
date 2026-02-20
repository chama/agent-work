"""X(Twitter) ブックマーク取得スクリプト

OAuth2 PKCEフローで認証し、ブックマークした投稿のテキストを取得・表示する。

使い方:
    1. 環境変数を設定:
        export X_CLIENT_ID="your_client_id"
        export X_CLIENT_SECRET="your_client_secret"
    2. 実行:
        uv run python x/fetch_bookmarks.py
    3. 初回はブラウザが開くので認証を行う。トークンはファイルに保存され次回以降再利用される。
"""

import json
import os
import sys
import time
import webbrowser
from http.server import HTTPServer, BaseHTTPRequestHandler
from urllib.parse import urlparse, parse_qs

from xdk import Client

TOKEN_FILE = os.path.join(os.path.dirname(__file__), ".x_token.json")
REDIRECT_URI = "http://localhost:3000/callback"
SCOPES = ["tweet.read", "users.read", "bookmark.read", "offline.access"]


def save_token(token: dict) -> None:
    with open(TOKEN_FILE, "w") as f:
        json.dump(token, f)


def load_token() -> dict | None:
    if not os.path.exists(TOKEN_FILE):
        return None
    with open(TOKEN_FILE, "r") as f:
        token = json.load(f)
    # トークン期限切れチェック
    expires_at = token.get("expires_at")
    if expires_at and time.time() >= expires_at:
        return None
    return token


def authenticate_with_pkce(client_id: str, client_secret: str) -> Client:
    """OAuth2 PKCEフローでユーザー認証を行い、Clientを返す。"""

    # 保存済みトークンがあれば再利用
    token = load_token()
    if token:
        print("保存済みトークンを使用します。")
        client = Client(
            client_id=client_id,
            client_secret=client_secret,
            redirect_uri=REDIRECT_URI,
            scope=SCOPES,
            token=token,
            access_token=token.get("access_token"),
        )
        return client

    # 新規認証フロー
    client = Client(
        client_id=client_id,
        client_secret=client_secret,
        redirect_uri=REDIRECT_URI,
        scope=SCOPES,
    )

    auth_url = client.get_authorization_url()
    print(f"ブラウザで認証してください:\n{auth_url}")
    webbrowser.open(auth_url)

    # ローカルサーバーでコールバックを待つ
    authorization_code = _wait_for_callback()

    token = client.exchange_code(authorization_code)
    save_token(token)
    print("認証完了。トークンを保存しました。")
    return client


def _wait_for_callback() -> str:
    """ローカルHTTPサーバーでOAuth2コールバックを待ち、認可コードを返す。"""
    authorization_code = None

    class CallbackHandler(BaseHTTPRequestHandler):
        def do_GET(self):
            nonlocal authorization_code
            query = parse_qs(urlparse(self.path).query)

            if "error" in query:
                error = query["error"][0]
                desc = query.get("error_description", [""])[0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(f"認証エラー: {error} - {desc}".encode())
                return

            authorization_code = query.get("code", [None])[0]
            self.send_response(200)
            self.send_header("Content-Type", "text/html; charset=utf-8")
            self.end_headers()
            self.wfile.write("認証完了！このタブを閉じてください。".encode())

        def log_message(self, format, *args):
            pass  # ログ抑制

    parsed = urlparse(REDIRECT_URI)
    server = HTTPServer((parsed.hostname, parsed.port), CallbackHandler)
    print(f"コールバック待機中 ({REDIRECT_URI}) ...")

    while authorization_code is None:
        server.handle_request()

    server.server_close()

    if not authorization_code:
        print("認可コードの取得に失敗しました。", file=sys.stderr)
        sys.exit(1)

    return authorization_code


def fetch_bookmarks(client: Client) -> list[dict]:
    """ブックマーク一覧を取得し、投稿データのリストを返す。"""
    me = client.users.get_me()
    user_id = me.data.id
    print(f"ユーザー: {me.data.name} (@{me.data.username})")

    bookmarks = []
    for page in client.users.get_bookmarks(
        id=user_id,
        tweet_fields=["created_at", "author_id", "text"],
        expansions=["author_id"],
        user_fields=["username", "name"],
    ):
        if not page.data:
            break

        # author_id → ユーザー情報のマップを構築
        user_map = {}
        if page.includes and hasattr(page.includes, "users"):
            for user in page.includes.users:
                uid = user.get("id") if isinstance(user, dict) else getattr(user, "id", None)
                user_map[uid] = user

        for tweet in page.data:
            if isinstance(tweet, dict):
                text = tweet.get("text", "")
                author_id = tweet.get("author_id", "")
                created_at = tweet.get("created_at", "")
                tweet_id = tweet.get("id", "")
            else:
                text = getattr(tweet, "text", "")
                author_id = getattr(tweet, "author_id", "")
                created_at = getattr(tweet, "created_at", "")
                tweet_id = getattr(tweet, "id", "")

            author = user_map.get(author_id)
            if author:
                if isinstance(author, dict):
                    author_name = author.get("name", "")
                    author_username = author.get("username", "")
                else:
                    author_name = getattr(author, "name", "")
                    author_username = getattr(author, "username", "")
            else:
                author_name = ""
                author_username = ""

            bookmarks.append({
                "id": tweet_id,
                "text": text,
                "author_name": author_name,
                "author_username": author_username,
                "created_at": created_at,
            })

    return bookmarks


def format_bookmarks(bookmarks: list[dict]) -> str:
    """ブックマークリストを読みやすい文字列に変換する。"""
    if not bookmarks:
        return "ブックマークはありません。"

    lines = []
    for i, bm in enumerate(bookmarks, 1):
        author = f"{bm['author_name']} (@{bm['author_username']})" if bm["author_username"] else "不明"
        lines.append(f"--- [{i}] {author} ({bm['created_at']}) ---")
        lines.append(bm["text"])
        lines.append("")

    return "\n".join(lines)


def main():
    client_id = os.getenv("X_CLIENT_ID")
    client_secret = os.getenv("X_CLIENT_SECRET")

    if not client_id:
        print("環境変数 X_CLIENT_ID を設定してください。", file=sys.stderr)
        sys.exit(1)

    client = authenticate_with_pkce(client_id, client_secret)
    bookmarks = fetch_bookmarks(client)
    output = format_bookmarks(bookmarks)
    print(output)


if __name__ == "__main__":
    main()
