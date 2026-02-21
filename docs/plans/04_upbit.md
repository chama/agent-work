# Upbit Spot Data Client 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
既に実装済みの Binance クライアント (src/binance_client/) と全く同じパターンで、Upbit 版を実装してください。

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

1. `src/upbit_client/__init__.py` → `UpbitClient` をエクスポート (※先物なしのためFuturesは付けない)
2. `src/upbit_client/base.py` → `UpbitBaseClient` + `to_milliseconds`
3. `src/upbit_client/spot.py` → `UpbitClient` (spotデータ)
4. `scripts/export_upbit_data.py` → CSV出力スクリプト
5. `tests/test_upbit_client.py`
6. `tests/test_export_upbit_data.py`
7. `data/upbit/.gitkeep`

---

## Upbit API 仕様

Base URL: `https://api.upbit.com/v1`

### 重要な特徴

- **Upbit は現物のみ** (先物取引なし)
  → funding rate, OI, LS比率 等の先物データは存在しない
  → Spot のマーケットデータを網羅的に取得する設計にする

- **マーケット形式が独特**: `"KRW-BTC"`, `"USDT-BTC"`, `"BTC-ETH"`
  → `{quote}-{base}` の順序 (Binanceの BTCUSDT とは逆)
  → export スクリプトでは市場指定 (`--market KRW-BTC`) とする

- **レスポンス**: JSON配列が直接返る (ラッパーなし)。HTTP 4xx/5xx はエラー

- **レート制限**: 秒間10リクエスト (Remaining ヘッダーで確認可能)

### Kline / Candle

分足:

```
GET /candles/minutes/{unit}   unit=1,3,5,10,15,30,60,240
```

日足:

```
GET /candles/days
```

週足:

```
GET /candles/weeks
```

月足:

```
GET /candles/months
```

共通params: `market`(必須), `to`(最新足のUTC時刻 `"yyyy-MM-dd'T'HH:mm:ss"`), `count`(最大200)

レスポンス:

```json
[
  {
    "market": "KRW-BTC",
    "candle_date_time_utc": "2025-01-01T00:00:00",
    "candle_date_time_kst": "2025-01-01T09:00:00",
    "opening_price": 50000000,
    "high_price": 51000000,
    "low_price": 49000000,
    "trade_price": 50500000,
    "timestamp": 1735689600000,
    "candle_acc_trade_price": 1234567890,
    "candle_acc_trade_volume": 123.456,
    "unit": 1
  },
  ...
]
```

**ページネーション**: 取得結果の最古の `candle_date_time_utc` を次の `to` パラメータに設定して遡る

`to` のフォーマット: ISO 8601 (例: `"2025-01-01T00:00:00"`)

1回で200件まで。大量取得時はループ必要。

### その他のエンドポイント

| メソッド | エンドポイント | 備考 |
|---|---|---|
| `get_klines` | 分足/日足/週足/月足を interval で自動切替 | interval に応じてURLを分岐 |
| `get_trades` | `GET /trades/ticks` | market, to, count, cursor で約定履歴 |
| `get_ticker` | `GET /ticker` | markets(カンマ区切り) で現在価格 |
| `get_orderbook` | `GET /orderbook` | markets で板情報 |
| `get_markets` | `GET /market/all` | 全マーケット一覧 |

### get_klines の interval 設計

export スクリプトの `--interval` から Upbit のエンドポイントに変換:

| interval | Upbit エンドポイント |
|---|---|
| `"1m"` | `/candles/minutes/1` |
| `"3m"` | `/candles/minutes/3` |
| `"5m"` | `/candles/minutes/5` |
| `"10m"` | `/candles/minutes/10` |
| `"15m"` | `/candles/minutes/15` |
| `"30m"` | `/candles/minutes/30` |
| `"1h"` | `/candles/minutes/60` |
| `"4h"` | `/candles/minutes/240` |
| `"1d"` | `/candles/days` |
| `"1w"` | `/candles/weeks` |
| `"1M"` | `/candles/months` |

### export スクリプトの types

Upbit は現物のみなので:

- `KLINE_TYPES = {"klines"}` (index_price, mark_price は不可)
- `ANALYTICS_TYPES = {}` (funding_rate, OI, LS比率 は不可)
- デフォルトで klines のみ取得

---

## 実装時の注意点 (過去の開発で判明した問題)

1. **pandas 3.x**: `datetime64[ms, UTC]` → `str(...).startswith("datetime64[")` で検証
2. **MagicMock**: 明示的に return_value 設定
3. **uv sync**: 新パッケージ作成後に必要
4. **Upbit の timestamp はミリ秒** だが、`candle_date_time_utc` は ISO文字列 → `pd.to_datetime()`
5. **レート制限が厳しい** (10req/sec) → `rate_limit_sleep` のデフォルトを 0.15 程度に
6. **market名の方向注意**: `KRW-BTC` (Upbit) vs `BTCUSDT` (Binance)
7. ファイル名は `futures.py` ではなく **`spot.py`** とする (先物がないため)

---

## 設計ルール

Binance版と同パターン:
- 全メソッド DataFrame 返却、自動ページネーション、to_milliseconds対応
- Context manager、リトライ、レート制限
- export: `data/upbit/yyyymmdd_hhmm_[market]_[interval]_[type].csv`
- テスト: mock使用、実API呼ばない

---

## 実行手順

1. リファレンス全読み
2. 実装
3. `uv sync`
4. `uv run pytest tests/test_upbit_client.py tests/test_export_upbit_data.py -v` でテスト全パス確認
5. git add → git commit → git push
