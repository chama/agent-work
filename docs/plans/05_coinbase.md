# Coinbase Spot Data Client 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
既に実装済みの Binance クライアント (src/binance_client/) と全く同じパターンで、Coinbase 版を実装してください。

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

1. `src/coinbase_client/__init__.py` → `CoinbaseClient` をエクスポート
2. `src/coinbase_client/base.py` → `CoinbaseBaseClient` + `to_milliseconds`
3. `src/coinbase_client/spot.py` → `CoinbaseClient`
4. `scripts/export_coinbase_data.py` → CSV出力スクリプト
5. `tests/test_coinbase_client.py`
6. `tests/test_export_coinbase_data.py`
7. `data/coinbase/.gitkeep`

---

## Coinbase API 仕様

Coinbase Exchange API (旧 Coinbase Pro) を使用。

Base URL: `https://api.exchange.coinbase.com`

### 重要な特徴

- **Coinbase は主に現物取引所** (米国でのデリバティブは制限あり)
  → Spot マーケットデータの取得に注力する

- **シンボル形式**: `"BTC-USD"`, `"ETH-USD"`, `"BTC-USDT"` (ハイフン区切り)

- **レスポンス**: JSON配列が直接返る (ラッパーなし)。HTTP ステータスでエラー判定

- **レート制限**: Public API は 10 requests/second

### Kline / Candle

```
GET /products/{product_id}/candles
```

params: `start`(ISO8601), `end`(ISO8601), `granularity`(秒: 60, 300, 900, 3600, 21600, 86400)

レスポンス:

```json
[[time, low, high, open, close, volume], ...]
```

**注意:**
- カラム順が一般的と異なる: `[time, LOW, HIGH, OPEN, CLOSE, vol]`
- `time`: UNIXタイムスタンプ(秒)
- 降順(新→古)で返る → 昇順ソート必要
- 1回で最大300件
- ページネーション: `start`/`end` (ISO8601) をずらして遡る

### その他のエンドポイント

| メソッド | エンドポイント | パラメータ | 備考 |
|---|---|---|---|
| `get_klines` | `GET /products/{id}/candles` | start, end, granularity | OHLCV |
| `get_trades` | `GET /products/{id}/trades` | limit, before, after | 約定履歴 |
| `get_ticker` | `GET /products/{id}/ticker` | - | 現在価格 |
| `get_orderbook` | `GET /products/{id}/book` | level(1,2,3) | 板情報 |
| `get_products` | `GET /products` | - | 全商品一覧 |
| `get_product_stats` | `GET /products/{id}/stats` | - | 24h統計 |

### get_klines の interval → granularity 変換

| interval | granularity (秒) |
|---|---|
| `"1m"` | 60 |
| `"5m"` | 300 |
| `"15m"` | 900 |
| `"1h"` | 3600 |
| `"6h"` | 21600 |
| `"1d"` | 86400 |

### export スクリプトの types

- `KLINE_TYPES = {"klines"}`
- `ANALYTICS_TYPES = {}` (先物データなし)

---

## 実装時の注意点 (過去の開発で判明した問題)

1. **pandas 3.x**: `datetime64[ms, UTC]` → `str(...).startswith("datetime64[")` で検証
2. **MagicMock**: 明示的に return_value 設定
3. **uv sync**: 新パッケージ作成後に必要
4. **Coinbase candle のカラム順**: `[time, LOW, HIGH, OPEN, CLOSE, vol]` → DataFrame変換時に注意
5. **タイムスタンプは秒単位** → `pd.to_datetime(unit="s", utc=True)` または ×1000して`unit="ms"`
6. **ISO8601 文字列が必要な箇所**: `datetime.utcfromtimestamp(ts).isoformat() + "Z"` (※Python 3.12以降の非推奨に注意、`datetime.fromtimestamp(ts, tz=timezone.utc)` を使用)
7. **granularity は限定的** (60, 300, 900, 3600, 21600, 86400) → サポート外のintervalはエラーにする
8. ファイル名は `futures.py` ではなく **`spot.py`**

---

## 設計ルール

Binance版と同パターン:
- 全メソッド DataFrame 返却、自動ページネーション、to_milliseconds対応
- Context manager、リトライ、レート制限
- export: `data/coinbase/yyyymmdd_hhmm_[product_id]_[interval]_[type].csv`
- テスト: mock使用、実API呼ばない

---

## 実行手順

1. リファレンス全読み
2. 実装
3. `uv sync`
4. `uv run pytest tests/test_coinbase_client.py tests/test_export_coinbase_data.py -v` でテスト全パス確認
5. git add → git commit → git push
