"""X (Twitter) のブックマークを取得して docs/x/ にJSON形式で保存するスクリプト.

必要な環境変数:
    X_OAUTH2_ACCESS_TOKEN: OAuth2 User Token (bookmark.read スコープが必要)

使い方:
    uv run scripts/save_x_bookmarks.py
"""

import json
import os
import sys
from datetime import datetime
from pathlib import Path

from xdk import Client


OUTPUT_DIR = Path(__file__).resolve().parent.parent / "docs" / "x"

# X API v2 で取得可能な全フィールド
TWEET_FIELDS = [
    "attachments",
    "author_id",
    "context_annotations",
    "conversation_id",
    "created_at",
    "edit_controls",
    "entities",
    "geo",
    "id",
    "in_reply_to_user_id",
    "lang",
    "possibly_sensitive",
    "public_metrics",
    "referenced_tweets",
    "reply_settings",
    "source",
    "text",
    "withheld",
]

EXPANSIONS = [
    "attachments.poll_ids",
    "attachments.media_keys",
    "author_id",
    "edit_history_tweet_ids",
    "entities.mentions.username",
    "geo.place_id",
    "in_reply_to_user_id",
    "referenced_tweets.id",
    "referenced_tweets.id.author_id",
]

USER_FIELDS = [
    "created_at",
    "description",
    "entities",
    "id",
    "location",
    "most_recent_tweet_id",
    "name",
    "pinned_tweet_id",
    "profile_image_url",
    "protected",
    "public_metrics",
    "url",
    "username",
    "verified",
    "verified_type",
    "withheld",
]

MEDIA_FIELDS = [
    "duration_ms",
    "height",
    "media_key",
    "preview_image_url",
    "type",
    "url",
    "width",
    "alt_text",
    "public_metrics",
    "variants",
]

POLL_FIELDS = [
    "duration_minutes",
    "end_datetime",
    "id",
    "options",
    "voting_status",
]

PLACE_FIELDS = [
    "contained_within",
    "country",
    "country_code",
    "full_name",
    "geo",
    "id",
    "name",
    "place_type",
]


def build_includes_lookup(includes: object) -> dict:
    """includes オブジェクトからルックアップ用辞書を構築する."""
    lookup = {"users": {}, "media": {}, "polls": {}, "places": {}, "tweets": {}}
    if includes is None:
        return lookup

    inc = includes.model_dump() if hasattr(includes, "model_dump") else {}

    for user in inc.get("users") or []:
        lookup["users"][user["id"]] = user
    for media in inc.get("media") or []:
        lookup["media"][media["media_key"]] = media
    for poll in inc.get("polls") or []:
        lookup["polls"][poll["id"]] = poll
    for place in inc.get("places") or []:
        lookup["places"][place["id"]] = place
    for tweet in inc.get("tweets") or []:
        lookup["tweets"][tweet["id"]] = tweet

    return lookup


def enrich_tweet(tweet_data: dict, includes_lookup: dict) -> dict:
    """tweet データに includes の情報を埋め込む."""
    enriched = dict(tweet_data)

    # author 情報を埋め込む
    author_id = tweet_data.get("author_id")
    if author_id and author_id in includes_lookup["users"]:
        enriched["author"] = includes_lookup["users"][author_id]

    # media 情報を埋め込む
    attachments = tweet_data.get("attachments") or {}
    media_keys = attachments.get("media_keys") or []
    if media_keys:
        enriched["media"] = [
            includes_lookup["media"][mk]
            for mk in media_keys
            if mk in includes_lookup["media"]
        ]

    # poll 情報を埋め込む
    poll_ids = attachments.get("poll_ids") or []
    if poll_ids:
        enriched["polls"] = [
            includes_lookup["polls"][pid]
            for pid in poll_ids
            if pid in includes_lookup["polls"]
        ]

    # referenced tweets を埋め込む
    refs = tweet_data.get("referenced_tweets") or []
    if refs:
        enriched_refs = []
        for ref in refs:
            ref_id = ref.get("id")
            if ref_id and ref_id in includes_lookup["tweets"]:
                ref_tweet = dict(includes_lookup["tweets"][ref_id])
                ref_tweet["reference_type"] = ref.get("type")
                # referenced tweet の author も埋め込む
                ref_author_id = ref_tweet.get("author_id")
                if ref_author_id and ref_author_id in includes_lookup["users"]:
                    ref_tweet["author"] = includes_lookup["users"][ref_author_id]
                enriched_refs.append(ref_tweet)
            else:
                enriched_refs.append(ref)
        enriched["referenced_tweets_expanded"] = enriched_refs

    # geo/place 情報を埋め込む
    geo = tweet_data.get("geo") or {}
    place_id = geo.get("place_id")
    if place_id and place_id in includes_lookup["places"]:
        enriched["place"] = includes_lookup["places"][place_id]

    return enriched


def main():
    access_token = os.getenv("X_OAUTH2_ACCESS_TOKEN")
    if not access_token:
        print("Error: X_OAUTH2_ACCESS_TOKEN 環境変数を設定してください", file=sys.stderr)
        sys.exit(1)

    client = Client(access_token=access_token)

    # 自分のユーザーIDを取得
    me = client.users.get_me()
    user_id = me.data.id
    print(f"ユーザー: {me.data.name} (@{me.data.username}), ID: {user_id}")

    # 出力ディレクトリ作成
    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)

    total_saved = 0
    for page in client.users.get_bookmarks(
        id=user_id,
        max_results=100,
        tweet_fields=TWEET_FIELDS,
        expansions=EXPANSIONS,
        user_fields=USER_FIELDS,
        media_fields=MEDIA_FIELDS,
        poll_fields=POLL_FIELDS,
        place_fields=PLACE_FIELDS,
    ):
        if not page.data:
            break

        includes_lookup = build_includes_lookup(page.includes)

        for tweet in page.data:
            tweet_data = tweet if isinstance(tweet, dict) else tweet.model_dump() if hasattr(tweet, "model_dump") else dict(tweet)
            enriched = enrich_tweet(tweet_data, includes_lookup)

            tweet_id = enriched["id"]
            filepath = OUTPUT_DIR / f"{tweet_id}.json"
            with open(filepath, "w", encoding="utf-8") as f:
                json.dump(enriched, f, ensure_ascii=False, indent=2, default=str)

            author = enriched.get("author", {})
            username = author.get("username", "unknown")
            text_preview = enriched.get("text", "")[:50]
            print(f"  保存: {filepath.name}  @{username}: {text_preview}...")
            total_saved += 1

    print(f"\n完了: {total_saved} 件のブックマークを {OUTPUT_DIR} に保存しました")


if __name__ == "__main__":
    main()
