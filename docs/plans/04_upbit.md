# Upbit Spot Data Source 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
DDD アーキテクチャで実装済みの `market_data` パッケージに、Upbit 版のデータソースアダプタを追加してください。

---

## プロジェクト規約

- Python 操作は常に uv を使う (uv run, uv sync)
- データは data/ 以下に保存
- ファイル名規則: yyyymmdd_hhmm_[概要].csv
- パッケージは src/market_data/ 以下に配置
- テスト: uv run pytest

---

## アーキテクチャ概要

本リポジトリは DDD (Domain-Driven Design) に基づく構成をとっている:

```
src/market_data/
  __init__.py                  # 公開API: create_source(), DataType, FuturesDataSource
  domain/
    models.py                  # DataType enum + 共通カラムスキーマ定義
    source.py                  # FuturesDataSource Protocol (取引所共通インターフェース)
  infra/
    http_client.py             # 汎用HTTPクライアント (retry/rate limit)
    binance.py                 # BinanceFuturesSource (実装参考例)
scripts/
  export_data.py               # 取引所非依存のエクスポートスクリプト (--exchange フラグ)
```

### 設計の要点

1. **`FuturesDataSource` Protocol**: 全取引所が実装すべきインターフェース
2. **`DataType` enum**: データ種別ごとの正規カラムスキーマ
3. **`HttpClient`**: 共有のHTTPクライアント
4. **Factory**: `create_source("upbit")` で切り替え
5. **エクスポート**: `scripts/export_data.py --exchange upbit` で使用

---

## リファレンス (必ず最初に全て読むこと)

1. `src/market_data/domain/models.py` → DataType enum + 正規カラムスキーマ
2. `src/market_data/domain/source.py` → FuturesDataSource Protocol
3. `src/market_data/infra/http_client.py` → HttpClient, to_milliseconds
4. `src/market_data/infra/binance.py` → **実装パターンの参考例**
5. `src/market_data/__init__.py` → ファクトリ + レジストリ
6. `tests/test_binance_source.py` → テストパターン参考
7. `scripts/export_data.py` → **変更不要**
8. `pyproject.toml`

---

## 作成・変更するファイル

### 新規作成

1. `src/market_data/infra/upbit.py` → `UpbitSource` クラス (FuturesDataSource 実装)
2. `tests/test_upbit_source.py` → テスト
3. `data/upbit/.gitkeep`

### 変更 (最小限)

4. `src/market_data/__init__.py` → `_ensure_registry()` に追加:
   ```python
   from .infra.upbit import UpbitSource
   _REGISTRY["upbit"] = UpbitSource
   ```

---

## Upbit API 仕様

Base URL: `https://api.upbit.com/v1`

### 重要な特徴

- **Upbit は現物のみ** (先物取引なし)
  → funding rate, OI, LS比率 等の先物データは存在しない
  → **サポートする DataType は `OHLCV` のみ**
  → それ以外の DataType は dispatcher に含めず、KeyError で適切にエラーにする

- **マーケット形式が独特**: `"KRW-BTC"`, `"USDT-BTC"`, `"BTC-ETH"`
  → `{quote}-{base}` の順序 (Binanceの BTCUSDT とは逆)
  → `fetch()` の `symbol` 引数は Binance 形式 (`"BTCUSDT"`) で受け取り、内部で変換するか、
     あるいは Upbit 形式 (`"KRW-BTC"`) をそのまま受け付ける設計にする
  → 変換ヘルパー: `"BTCKRW"` → `"KRW-BTC"`, `"BTCUSDT"` → `"USDT-BTC"`

- **レスポンス**: JSON配列が直接返る (ラッパーなし)。HTTP 4xx/5xx はエラー

- **レート制限**: 秒間10リクエスト → `rate_limit_sleep` のデフォルトを 0.15 程度に

### Kline / Candle

分足:
```
GET /candles/minutes/{unit}   unit=1,3,5,10,15,30,60,240
```

日足 / 週足 / 月足:
```
GET /candles/days
GET /candles/weeks
GET /candles/months
```

共通params: `market`(必須), `to`(最新足のUTC時刻 `"yyyy-MM-dd'T'HH:mm:ss"`), `count`(最大200)

レスポンス:
```json
[
  {
    "market": "KRW-BTC",
    "candle_date_time_utc": "2025-01-01T00:00:00",
    "opening_price": 50000000,
    "high_price": 51000000,
    "low_price": 49000000,
    "trade_price": 50500000,
    "timestamp": 1735689600000,
    "candle_acc_trade_price": 1234567890,
    "candle_acc_trade_volume": 123.456
  }
]
```

**ページネーション**: 取得結果の最古の `candle_date_time_utc` を次の `to` パラメータに設定して遡る

interval → エンドポイント変換:

| interval | Upbit エンドポイント |
|---|---|
| `"1m"` | `/candles/minutes/1` |
| `"3m"` | `/candles/minutes/3` |
| `"5m"` | `/candles/minutes/5` |
| `"15m"` | `/candles/minutes/15` |
| `"30m"` | `/candles/minutes/30` |
| `"1h"` | `/candles/minutes/60` |
| `"4h"` | `/candles/minutes/240` |
| `"1d"` | `/candles/days` |
| `"1w"` | `/candles/weeks` |
| `"1M"` | `/candles/months` |

→ 出力: `DataType.OHLCV.columns` に準拠
→ Upbit は `close_time`, `quote_volume`, `trades`, `taker_buy_volume`, `taker_buy_quote_volume` を持たないため:
  - `close_time` → `NaN`
  - `quote_volume` → `candle_acc_trade_price` をマッピング
  - `trades` → `0` (取得不可)
  - `taker_buy_volume`, `taker_buy_quote_volume` → `NaN`

---

## 実装時の注意点

1. **pandas 3.x**: `datetime64[ms, UTC]` → `str(...).startswith("datetime64[")` で検証
2. **MagicMock**: `mock._http.get.return_value` を明示的に設定
3. **uv sync**: 新モジュール追加後に必要
4. **Upbit の timestamp はミリ秒** だが、`candle_date_time_utc` は ISO文字列 → `pd.to_datetime()`
5. **レート制限が厳しい** (10req/sec) → `rate_limit_sleep` のデフォルトを 0.15 程度に
6. **market名の方向注意**: `KRW-BTC` (Upbit) vs `BTCUSDT` (Binance)
7. **レスポンスにラッパーがない**: `_http.get()` の結果がそのままリストで返る

---

## テストパターン

- `DataType.OHLCV` について `list(df.columns) == DataType.OHLCV.columns` を検証
- Upbit のレスポンス (JSON配列) を mock で再現
- ファクトリ: `create_source("upbit")` のテスト

---

## 実行手順

1. リファレンスファイルを全て読む
2. `src/market_data/infra/upbit.py` を作成
3. `src/market_data/__init__.py` の `_ensure_registry()` に追加
4. `tests/test_upbit_source.py` を作成
5. `data/upbit/.gitkeep` を作成
6. `uv sync`
7. `uv run pytest tests/test_upbit_source.py -v` で全テスト通過を確認
8. 既存テストも壊れていないか確認: `uv run pytest -v`
9. git add → git commit → git push
