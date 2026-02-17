"""
Create a "Context Pack" by researching a given topic using xAI (Grok) + x_search.

- Designed for pre-writing research (not post-writing factcheck).
- Accepts a free-form topic/question and produces a structured markdown pack.
- Saves artifacts under data/context-research/ (json/txt/md) with timestamps.

Requires:
  XAI_API_KEY in env or .env

Usage:
  uv run x/grok_context_research.py --topic "ClaudeにX検索を足してリサーチを自動化する"
  uv run x/grok_context_research.py --topic "X API recent search rate limits" --locale global --audience engineer
"""

from __future__ import annotations

import argparse
import json
import sys
from datetime import datetime, timezone
from pathlib import Path
from typing import Any

import httpx

DEFAULT_BASE_URL = "https://api.x.ai"
DEFAULT_MODEL = "grok-4-1-fast-reasoning"

REPO_ROOT = Path(__file__).resolve().parent.parent


def load_dotenv(dotenv_path: Path) -> dict[str, str]:
    if not dotenv_path.exists():
        return {}
    out: dict[str, str] = {}
    for raw in dotenv_path.read_text(encoding="utf-8").splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        eq = line.find("=")
        if eq == -1:
            continue
        k = line[:eq].strip()
        v = line[eq + 1 :].strip()
        if not k:
            continue
        if (v.startswith('"') and v.endswith('"')) or (
            v.startswith("'") and v.endswith("'")
        ):
            v = v[1:-1]
        out[k] = v
    return out


def timestamp_slug(d: datetime) -> str:
    iso = d.isoformat()
    # ISO format: 2024-01-02T03:04:05+00:00 or ...Z
    y = iso[0:4]
    m = iso[5:7]
    day = iso[8:10]
    hh = iso[11:13]
    mm = iso[14:16]
    ss = iso[17:19]
    return f"{y}{m}{day}_{hh}{mm}{ss}Z"


def parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Create a Context Pack via xAI (Grok) + x_search",
    )
    parser.add_argument("--topic", required=True, help="What to research")
    parser.add_argument(
        "--locale",
        choices=["ja", "global"],
        default="ja",
        help="ja or global (default: ja)",
    )
    parser.add_argument(
        "--audience",
        choices=["engineer", "investor", "both"],
        default="engineer",
        help="engineer / investor / both (default: engineer)",
    )
    parser.add_argument(
        "--goal",
        default="記事を深くするための周辺情報リサーチ（一次情報/用語/反論/数字を揃える）",
        help="Research goal",
    )
    parser.add_argument(
        "--days", type=int, default=30, help="Lookback hint in days (default: 30)"
    )
    parser.add_argument(
        "--out-dir",
        default="data/context-research",
        help="Output directory (default: data/context-research)",
    )
    parser.add_argument("--xai-api-key", default="", help="xAI API key override")
    parser.add_argument(
        "--xai-base-url", default="", help="xAI base URL override"
    )
    parser.add_argument("--xai-model", default="", help="xAI model override")
    parser.add_argument(
        "--dry-run", action="store_true", help="Print request payload and exit"
    )
    parser.add_argument(
        "--raw-json", action="store_true", help="Also print raw JSON response to stderr"
    )

    args = parser.parse_args(argv)
    if args.days <= 0:
        args.days = 30
    return args


def get_config(
    args: argparse.Namespace,
) -> dict[str, str]:
    import os

    dotenv = load_dotenv(REPO_ROOT / ".env")

    def get_str(env_key: str, cli_value: str, fallback: str) -> str:
        return cli_value or os.environ.get(env_key, "") or dotenv.get(env_key, "") or fallback

    xai_api_key = get_str("XAI_API_KEY", args.xai_api_key, "")
    xai_base_url = get_str(
        "XAI_BASE_URL", args.xai_base_url, DEFAULT_BASE_URL
    ).rstrip("/")
    xai_model = get_str("XAI_MODEL", args.xai_model, DEFAULT_MODEL)

    return {
        "xai_api_key": xai_api_key,
        "xai_base_url": xai_base_url,
        "xai_model": xai_model,
    }


def build_prompt(
    *,
    topic: str,
    locale: str,
    audience: str,
    goal: str,
    days: int,
    now_iso: str,
) -> str:
    if locale == "ja":
        locale_line = (
            "検索・収集は日本語圏を優先（日本語で読める一次情報や日本語で拡散している情報）。"
            "必要なら英語一次情報も併用。"
        )
    else:
        locale_line = (
            "検索・収集はグローバル一次情報（英語中心）を優先。"
            "日本語圏の派生/解説も拾ってよい。"
        )

    if audience == "engineer":
        audience_line = "読者はエンジニア寄り。実装・運用・制約（レート/コスト/権限）を厚めに。"
    elif audience == "investor":
        audience_line = (
            "読者は投資家寄り。評価軸（コスト/優位性/リスク/規約）を厚めに。"
            "ただし投資助言はしない。"
        )
    else:
        audience_line = (
            "読者は投資家+エンジニア。両方に通じる共通言語"
            "（運用/再現性/コスト/監査）で整理。"
        )

    return f"""日本語で回答して。
目的: {goal}
トピック: {topic}
時点: {now_iso}
検索窓の目安: 直近{days}日（ただし仕様/規約/料金は最新を優先）
前提:
- {locale_line}
- {audience_line}
- 数字/仕様/制限は捏造しない。不明は unknown と書く。
- 仕様/価格/レート等は変更され得るので、必ず「As of（参照日）」を付ける。
- 長文の直接引用はしない（要旨で）。
- 投資助言に見える表現は禁止（買い/売り推奨、価格目標、倍化など）。
- 重要: Primary Sources は「公式ドキュメント/公式ブログ/仕様/規約/料金/公式GitHub」など、X投稿以外のURLにする。X投稿URLは Secondary としてのみ可。
- 出力に専用タグ（render_inline_citation など）を入れない。URLは素のURLで書く。
やること:
1) x_search を使って一次情報（公式ドキュメント/仕様/規約/料金/公式ブログ/公式GitHub）を最優先で集める
2) 次に実装例（GitHub、SDK、サンプル）を集める
3) 反論/注意点を最低1つ作る（例: レート制限、コスト爆発、偏り、ポリシー違反、セキュリティ）
4) 記事が深くなる要素を最低2つ作る:
   - 用語の定義（誤解を潰す）
   - datedな数字（レート/料金/制約など）
   - 実装の最小構成（必要な権限、保存形式、ログ）
出力形式（Markdown、以下の見出しを必ず含める）:
- Meta（Timestamp, Topic, Audience, Voice）
- Topic (1 sentence)
- Why Now (3 bullets)
- Key Questions (5-8)
- Terminology / Definitions（Source付き）
- Primary Sources（URL）
- Secondary Sources（URL）
- Contrasts / Counterpoints（Evidence付き）
- Data Points (dated)（As of, Source付き）
- What We Can Safely Say / What We Should Not Say
- Suggested Angles (3)
- Outline Seeds (3-6 headings)
- Sources (URL list)
"""


def post_json(
    url: str,
    headers: dict[str, str],
    payload: Any,
    timeout_s: float,
) -> Any:
    with httpx.Client(timeout=timeout_s) as client:
        resp = client.post(url, headers=headers, json=payload)
        if resp.status_code >= 400:
            raise RuntimeError(f"HTTP {resp.status_code}: {resp.text[:4000]}")
        return resp.json()


def extract_text(resp: Any) -> str:
    if isinstance(resp, dict):
        # Try output array (responses API format)
        out = resp.get("output")
        if isinstance(out, list):
            parts: list[str] = []
            for item in out:
                if not isinstance(item, dict):
                    continue
                content = item.get("content")
                if not isinstance(content, list):
                    continue
                for c in content:
                    if not isinstance(c, dict):
                        continue
                    t = c.get("text")
                    if isinstance(t, str) and t.strip():
                        parts.append(t)
            if parts:
                return "\n".join(parts).strip()

        # Fallback keys
        for k in ("output_text", "text", "content"):
            v = resp.get(k)
            if isinstance(v, str) and v.strip():
                return v.strip()

    return json.dumps(resp, indent=2, ensure_ascii=False)


def save_file(out_dir: str, filename: str, content: str) -> Path:
    abs_dir = Path(out_dir) if Path(out_dir).is_absolute() else REPO_ROOT / out_dir
    abs_dir.mkdir(parents=True, exist_ok=True)
    p = abs_dir / filename
    p.write_text(content, encoding="utf-8")
    return p


def main() -> None:
    args = parse_args()
    cfg = get_config(args)

    if not cfg["xai_api_key"].strip():
        print("Missing XAI_API_KEY. Set it in .env or environment.", file=sys.stderr)
        sys.exit(2)

    topic = args.topic.strip()
    if not topic:
        print(
            'Missing --topic. Example: --topic "ClaudeにX検索を足してリサーチを自動化する"',
            file=sys.stderr,
        )
        sys.exit(2)

    now = datetime.now(timezone.utc)
    prompt = build_prompt(
        topic=topic,
        locale=args.locale,
        audience=args.audience,
        goal=args.goal,
        days=args.days,
        now_iso=now.isoformat(),
    )

    payload: dict[str, Any] = {
        "model": cfg["xai_model"],
        "input": prompt,
        "tools": [{"type": "x_search"}],
    }

    if args.dry_run:
        print(json.dumps(payload, indent=2, ensure_ascii=False))
        return

    url = f"{cfg['xai_base_url']}/v1/responses"
    headers = {
        "Content-Type": "application/json",
        "Authorization": f"Bearer {cfg['xai_api_key']}",
    }

    resp = post_json(url, headers, payload, timeout_s=180.0)
    text = extract_text(resp)

    ts = timestamp_slug(now)
    base = f"{ts}_{args.locale}_context"

    md = (
        f"# Context Pack ({args.locale})\n\n"
        f"## Meta\n"
        f"- Timestamp (UTC): {now.isoformat()}\n"
        f"- Topic: {topic}\n"
        f"- Audience: {args.audience}\n\n"
        f"---\n\n"
        f"{text}\n"
    )

    json_file = save_file(
        args.out_dir,
        f"{base}.json",
        json.dumps(
            {
                "timestamp": now.isoformat(),
                "topic": topic,
                "params": {
                    "locale": args.locale,
                    "audience": args.audience,
                    "goal": args.goal,
                    "days": args.days,
                    "model": cfg["xai_model"],
                    "base_url": cfg["xai_base_url"],
                    "out_dir": args.out_dir,
                },
                "request": payload,
                "response": resp,
                "extracted_text": text,
            },
            indent=2,
            ensure_ascii=False,
        ),
    )
    txt_file = save_file(args.out_dir, f"{base}.txt", text)
    md_file = save_file(args.out_dir, f"{ts}_context.md", md)

    cwd = Path.cwd()
    print(f"Saved: {json_file.relative_to(cwd)}", file=sys.stderr)
    print(f"Saved: {txt_file.relative_to(cwd)}", file=sys.stderr)
    print(f"Saved: {md_file.relative_to(cwd)}", file=sys.stderr)

    if args.raw_json:
        print(json.dumps(resp, indent=2, ensure_ascii=False), file=sys.stderr)

    print(text)


if __name__ == "__main__":
    main()
