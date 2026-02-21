"""X (Twitter) OAuth 2.0 Authorization Code Flow with PKCE でアクセストークンを取得するスクリプト.

必要な環境変数:
    X_CLIENT_ID:     X Developer Portal の OAuth 2.0 Client ID
    X_CLIENT_SECRET: X Developer Portal の OAuth 2.0 Client Secret

事前準備 (X Developer Portal):
    1. User authentication settings を有効化
    2. Type of App → "Web App, Automated App or Bot" を選択
    3. Callback URL に http://localhost:3000/callback を追加
    4. Website URL を適当に設定 (例: http://localhost)

使い方:
    uv run scripts/x_oauth2_token.py

取得したトークンは .env に追記されます。
"""

import base64
import hashlib
import http.server
import json
import os
import secrets
import sys
import threading
import urllib.parse
import webbrowser

import requests

AUTHORIZE_URL = "https://twitter.com/i/oauth2/authorize"
TOKEN_URL = "https://api.twitter.com/2/oauth2/token"
REDIRECT_URI = "http://localhost:3000/callback"
SCOPES = ["bookmark.read", "tweet.read", "users.read", "offline.access"]


def generate_pkce():
    """PKCE code_verifier と code_challenge (S256) を生成."""
    code_verifier = secrets.token_urlsafe(64)[:128]
    digest = hashlib.sha256(code_verifier.encode("ascii")).digest()
    code_challenge = base64.urlsafe_b64encode(digest).rstrip(b"=").decode("ascii")
    return code_verifier, code_challenge


def build_authorize_url(client_id: str, code_challenge: str, state: str) -> str:
    """認可URLを構築."""
    params = {
        "response_type": "code",
        "client_id": client_id,
        "redirect_uri": REDIRECT_URI,
        "scope": " ".join(SCOPES),
        "state": state,
        "code_challenge": code_challenge,
        "code_challenge_method": "S256",
    }
    return f"{AUTHORIZE_URL}?{urllib.parse.urlencode(params)}"


def exchange_code_for_token(
    client_id: str, client_secret: str, code: str, code_verifier: str
) -> dict:
    """認可コードをアクセストークンに交換."""
    resp = requests.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={
            "grant_type": "authorization_code",
            "code": code,
            "redirect_uri": REDIRECT_URI,
            "code_verifier": code_verifier,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    return resp.json()


def save_to_env(access_token: str, refresh_token: str | None):
    """トークンを .env ファイルに保存."""
    env_path = os.path.join(os.path.dirname(__file__), "..", ".env")
    env_path = os.path.normpath(env_path)

    lines = []
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()

    # 既存の X_OAUTH2 行を除去
    lines = [
        line
        for line in lines
        if not line.startswith("X_OAUTH2_ACCESS_TOKEN=")
        and not line.startswith("X_OAUTH2_REFRESH_TOKEN=")
    ]

    lines.append(f"X_OAUTH2_ACCESS_TOKEN={access_token}\n")
    if refresh_token:
        lines.append(f"X_OAUTH2_REFRESH_TOKEN={refresh_token}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print(f"\n.env に保存しました: {env_path}")


class CallbackHandler(http.server.BaseHTTPRequestHandler):
    """コールバックを受け取るHTTPハンドラ."""

    auth_code: str | None = None
    received_state: str | None = None
    error: str | None = None

    def do_GET(self):
        parsed = urllib.parse.urlparse(self.path)
        params = urllib.parse.parse_qs(parsed.query)

        if parsed.path == "/callback":
            if "error" in params:
                CallbackHandler.error = params["error"][0]
                self.send_response(400)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    f"<h1>認可エラー: {CallbackHandler.error}</h1><p>ブラウザを閉じてください</p>".encode()
                )
            else:
                CallbackHandler.auth_code = params.get("code", [None])[0]
                CallbackHandler.received_state = params.get("state", [None])[0]
                self.send_response(200)
                self.send_header("Content-Type", "text/html; charset=utf-8")
                self.end_headers()
                self.wfile.write(
                    "<h1>認可成功!</h1><p>このページを閉じてターミナルに戻ってください</p>".encode()
                )
        else:
            self.send_response(404)
            self.end_headers()

    def log_message(self, format, *args):
        pass  # ログ抑制


def main():
    client_id = os.getenv("X_CLIENT_ID")
    client_secret = os.getenv("X_CLIENT_SECRET")

    if not client_id or not client_secret:
        print(
            "Error: X_CLIENT_ID と X_CLIENT_SECRET 環境変数を設定してください",
            file=sys.stderr,
        )
        print("\nX Developer Portal → OAuth 2.0 Client ID & Client Secret を確認")
        sys.exit(1)

    # PKCE パラメータ生成
    code_verifier, code_challenge = generate_pkce()
    state = secrets.token_urlsafe(32)

    # ローカルサーバー起動
    server = http.server.HTTPServer(("localhost", 3000), CallbackHandler)
    server_thread = threading.Thread(target=server.handle_request, daemon=True)
    server_thread.start()

    # 認可URLをブラウザで開く
    authorize_url = build_authorize_url(client_id, code_challenge, state)
    print("ブラウザで X の認可ページを開きます...")
    print(f"\n自動で開かない場合は以下のURLをブラウザに貼り付けてください:\n{authorize_url}\n")
    webbrowser.open(authorize_url)

    # コールバック待機
    print("認可を待機中... (ブラウザで「Authorize app」をクリックしてください)")
    server_thread.join(timeout=300)
    server.server_close()

    if CallbackHandler.error:
        print(f"\nエラー: {CallbackHandler.error}", file=sys.stderr)
        sys.exit(1)

    if not CallbackHandler.auth_code:
        print("\nタイムアウト: 認可コードを受信できませんでした", file=sys.stderr)
        sys.exit(1)

    if CallbackHandler.received_state != state:
        print("\nエラー: state パラメータが一致しません", file=sys.stderr)
        sys.exit(1)

    # トークン交換
    print("アクセストークンを取得中...")
    token_data = exchange_code_for_token(
        client_id, client_secret, CallbackHandler.auth_code, code_verifier
    )

    access_token = token_data["access_token"]
    refresh_token = token_data.get("refresh_token")
    expires_in = token_data.get("expires_in")
    scope = token_data.get("scope")

    print(f"\nアクセストークン取得成功!")
    print(f"  スコープ: {scope}")
    if expires_in:
        print(f"  有効期限: {expires_in}秒 ({expires_in // 3600}時間)")
    if refresh_token:
        print(f"  リフレッシュトークン: あり (offline.access)")

    # .env に保存
    save_to_env(access_token, refresh_token)

    print(f"\n使い方:")
    print(f"  source .env && uv run scripts/save_x_bookmarks.py")
    print(f"  または:")
    print(f"  X_OAUTH2_ACCESS_TOKEN={access_token[:20]}... uv run scripts/save_x_bookmarks.py")


if __name__ == "__main__":
    main()
