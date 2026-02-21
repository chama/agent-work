"""X (Twitter) OAuth 2.0 リフレッシュトークンでアクセストークンを更新するスクリプト.

必要な環境変数:
    X_CLIENT_ID:            OAuth 2.0 Client ID
    X_CLIENT_SECRET:        OAuth 2.0 Client Secret
    X_OAUTH2_REFRESH_TOKEN: リフレッシュトークン (.env に保存済みのもの)

使い方:
    uv run scripts/x_oauth2_refresh.py
"""

import os
import sys

import requests

TOKEN_URL = "https://api.twitter.com/2/oauth2/token"


def main():
    client_id = os.getenv("X_CLIENT_ID")
    client_secret = os.getenv("X_CLIENT_SECRET")
    refresh_token = os.getenv("X_OAUTH2_REFRESH_TOKEN")

    if not all([client_id, client_secret, refresh_token]):
        print(
            "Error: X_CLIENT_ID, X_CLIENT_SECRET, X_OAUTH2_REFRESH_TOKEN を設定してください",
            file=sys.stderr,
        )
        sys.exit(1)

    resp = requests.post(
        TOKEN_URL,
        auth=(client_id, client_secret),
        data={
            "grant_type": "refresh_token",
            "refresh_token": refresh_token,
        },
        headers={"Content-Type": "application/x-www-form-urlencoded"},
    )
    resp.raise_for_status()
    token_data = resp.json()

    access_token = token_data["access_token"]
    new_refresh_token = token_data.get("refresh_token")

    # .env を更新
    env_path = os.path.normpath(os.path.join(os.path.dirname(__file__), "..", ".env"))
    lines = []
    if os.path.exists(env_path):
        with open(env_path, encoding="utf-8") as f:
            lines = f.readlines()

    lines = [
        line
        for line in lines
        if not line.startswith("X_OAUTH2_ACCESS_TOKEN=")
        and not line.startswith("X_OAUTH2_REFRESH_TOKEN=")
    ]
    lines.append(f"X_OAUTH2_ACCESS_TOKEN={access_token}\n")
    if new_refresh_token:
        lines.append(f"X_OAUTH2_REFRESH_TOKEN={new_refresh_token}\n")

    with open(env_path, "w", encoding="utf-8") as f:
        f.writelines(lines)

    print("アクセストークンを更新しました")
    print(f"  .env に保存: {env_path}")
    if new_refresh_token and new_refresh_token != refresh_token:
        print("  リフレッシュトークンも更新されました")


if __name__ == "__main__":
    main()
