# Kraken Data Client 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
既に実装済みの Binance クライアント (src/binance_client/) と全く同じパターンで、Kraken 版を実装してください。

---

## プロジェクト規約

- Python: uv (uv run, uv sync)
- ファイル名: yyyymmdd_hhmm_[概要].csv
- パッケージ: src/ 以下
- テスト: uv run pytest

---

## リファレンス (必ず最初に全て読むこと)

1. `src/binance_client/base.py` → BaseClient設計
2. `src/binance_client/futures.py` → 全メソッドパターン
3. `scripts/export_binance_data.py` → CLI・export設計
4. `tests/test_binance_client.py` → テストパターン
5. `tests/test_export_binance_data.py` → exportテストパターン
6. `pyproject.toml`

---

## 作成するファイル (これ以外は変更禁止)

1. `src/kraken_client/__init__.py` → `KrakenFuturesClient` をエクスポート
2. `src/kraken_client/base.py` → `KrakenBaseClient` + `to_milliseconds`
3. `src/kraken_client/futures.py` → `KrakenFuturesClient`
4. `scripts/export_kraken_data.py` → CSV出力スクリプト
5. `tests/test_kraken_client.py`
6. `tests/test_export_kraken_data.py`
7. `data/kraken/.gitkeep`

---

## Kraken API 仕様

Kraken は **Spot API** と **Futures API** の2つがある。両方を活用する。

### Spot API

Base URL: `https://api.kraken.com/0/public`

レスポンス: `{"error":[],"result":{...}}` → `error` が空でなければエラー

シンボル形式: `"XXBTZUSD"`, `"XETHZUSD"` 等 (Krakenの独自命名)
→ ただし `"BTCUSD"`, `"ETHUSD"` でも受け付ける場合がある

| メソッド | エンドポイント | パラメータ | 備考 |
|---|---|---|---|
| `get_klines` | `GET /OHLC` | pair, interval(分: 1,5,15,30,60,240,1440,10080,21600), since(UNIXタイムスタンプ秒) | `result.{pair}` = `[[ts,o,h,l,c,vwap,vol,count],...]`, `result.last` |
| `get_ticker` | `GET /Ticker` | pair | 現在価格 |
| `get_orderbook` | `GET /Depth` | pair, count | asks/bids |
| `get_trades` | `GET /Trades` | pair, since(ナノ秒), count | 約定履歴 |
| `get_asset_pairs` | `GET /AssetPairs` | - | 取引ペア一覧 |
| `get_spread` | `GET /Spread` | pair, since | スプレッド履歴 |

**注意:**
- OHLC の `since`: UNIXタイムスタンプ(秒)。レスポンスの `result.last` を次の `since` に使う
- `interval` は分単位: 1, 5, 15, 30, 60, 240, 1440(1d), 10080(1w), 21600(15d)
- OHLC のタイムスタンプも秒単位 → ×1000 でミリ秒変換必要

### Futures API

Base URL: `https://futures.kraken.com/derivatives/api/v3`

レスポンス: `{"result":"success","tickers":[...]}` 等 (エンドポイントにより異なる)

シンボル形式: `"PF_XBTUSD"` (perpetual futures), `"PI_XBTUSD"` (inverse)
USDT建て: `"PF_BTCUSDT"` 等

| メソッド | エンドポイント | パラメータ | 備考 |
|---|---|---|---|
| `get_funding_rate_history` | `GET /historicalfundingrates` | symbol | `[{timestamp, fundingRate, relativeFundingRate},...]` |
| `get_futures_tickers` | `GET /tickers` | - | 全先物ティッカー |
| `get_futures_orderbook` | `GET /orderbook` | symbol | 先物板情報 |
| `get_futures_instruments` | `GET /instruments` | - | 先物商品一覧 |
| `get_futures_candles` | `GET /charts/v1/trade/{symbol}/{interval}` | WebFetchでAPI確認推奨 | 先物kline(存在すれば) |

**Futures API のエンドポイント構造は WebFetch で https://docs.futures.kraken.com/ を確認推奨**

Spot OHLC で大半の価格分析は可能。Futures API は funding rate 等の先物固有データに使う。

### 設計方針

- `get_klines` は Spot API の OHLC を使用 (最も信頼性が高い)
- `get_funding_rate_history` は Futures API を使用
- `base.py` に `SPOT_BASE_URL` と `FUTURES_BASE_URL` の両方を定義
- `_request` 内でどちらの URL かに応じてレスポンスパースを分岐

---

## 実装時の注意点 (過去の開発で判明した問題)

1. **pandas 3.x**: `datetime64[ms, UTC]` → テストでは `str(...).startswith("datetime64[")` で検証
2. **MagicMock**: 明示的に `mock.method.return_value` を設定
3. **uv sync**: 新パッケージ作成後に必要
4. **Kraken OHLC のタイムスタンプは秒単位** → `pd.to_datetime(unit="s")` を使うか ×1000して`unit="ms"`
5. **Kraken のペア名が独特** (XXBTZUSD等) → `get_asset_pairs` で正規名を取得するヘルパーがあると便利
6. export スクリプトの interval 変換: `"1m"→1`, `"5m"→5`, `"1h"→60`, `"4h"→240`, `"1d"→1440`

---

## 設計ルール

Binance版と同パターン:
- 全メソッド DataFrame 返却、自動ページネーション、to_milliseconds対応
- Context manager、リトライ、レート制限
- export: `data/kraken/yyyymmdd_hhmm_[symbol]_[interval]_[type].csv`
- テスト: mock使用、実API呼ばない

---

## 実行手順

1. リファレンス全読み
2. 実装
3. `uv sync`
4. `uv run pytest tests/test_kraken_client.py tests/test_export_kraken_data.py -v` でテスト全パス確認
5. git add → git commit → git push
