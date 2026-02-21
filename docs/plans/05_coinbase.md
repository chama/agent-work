# Coinbase Spot Data Source 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
DDD アーキテクチャで実装済みの `market_data` パッケージに、Coinbase 版のデータソースアダプタを追加してください。

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
4. **Factory**: `create_source("coinbase")` で切り替え
5. **エクスポート**: `scripts/export_data.py --exchange coinbase` で使用

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

1. `src/market_data/infra/coinbase.py` → `CoinbaseSource` クラス (FuturesDataSource 実装)
2. `tests/test_coinbase_source.py` → テスト
3. `data/coinbase/.gitkeep`

### 変更 (最小限)

4. `src/market_data/__init__.py` → `_ensure_registry()` に追加:
   ```python
   from .infra.coinbase import CoinbaseSource
   _REGISTRY["coinbase"] = CoinbaseSource
   ```

---

## Coinbase API 仕様

Coinbase Exchange API (旧 Coinbase Pro) を使用。

Base URL: `https://api.exchange.coinbase.com`

### 重要な特徴

- **Coinbase は主に現物取引所** (米国でのデリバティブは制限あり)
  → **サポートする DataType は `OHLCV` のみ**
  → それ以外の DataType は dispatcher に含めず、KeyError で適切にエラーにする

- **シンボル形式**: `"BTC-USD"`, `"ETH-USD"`, `"BTC-USDT"` (ハイフン区切り)
  → symbol 変換ヘルパー: `"BTCUSDT"` → `"BTC-USDT"`, `"BTCUSD"` → `"BTC-USD"`

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

interval → granularity 変換:

| interval | granularity (秒) |
|---|---|
| `"1m"` | 60 |
| `"5m"` | 300 |
| `"15m"` | 900 |
| `"1h"` | 3600 |
| `"6h"` | 21600 |
| `"1d"` | 86400 |

サポート外のintervalはエラーにする。

→ 出力: `DataType.OHLCV.columns` に準拠
→ Coinbase は `close_time`, `quote_volume`, `trades`, `taker_buy_volume`, `taker_buy_quote_volume` を持たないため `NaN` / `0` で埋める

---

## 実装時の注意点

1. **pandas 3.x**: `datetime64[ms, UTC]` → `str(...).startswith("datetime64[")` で検証
2. **MagicMock**: `mock._http.get.return_value` を明示的に設定
3. **uv sync**: 新モジュール追加後に必要
4. **Coinbase candle のカラム順**: `[time, LOW, HIGH, OPEN, CLOSE, vol]` → DataFrame変換時にマッピング注意
5. **タイムスタンプは秒単位** → `pd.to_datetime(unit="s", utc=True)`
6. **ISO8601 文字列が必要な箇所**: `datetime.fromtimestamp(ts, tz=timezone.utc).isoformat() + "Z"`
7. **granularity は限定的** (60, 300, 900, 3600, 21600, 86400) → サポート外のintervalはエラー
8. **レスポンスにラッパーがない**: `_http.get()` の結果がそのままリストで返る

---

## テストパターン

- `DataType.OHLCV` について `list(df.columns) == DataType.OHLCV.columns` を検証
- Coinbase の candle レスポンス (降順の配列) を mock で再現
- カラム順の逆転が正しく処理されていることを確認
- ファクトリ: `create_source("coinbase")` のテスト

---

## 実行手順

1. リファレンスファイルを全て読む
2. `src/market_data/infra/coinbase.py` を作成
3. `src/market_data/__init__.py` の `_ensure_registry()` に追加
4. `tests/test_coinbase_source.py` を作成
5. `data/coinbase/.gitkeep` を作成
6. `uv sync`
7. `uv run pytest tests/test_coinbase_source.py -v` で全テスト通過を確認
8. 既存テストも壊れていないか確認: `uv run pytest -v`
9. git add → git commit → git push
