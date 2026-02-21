# OKX Futures Data Source 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
DDD アーキテクチャで実装済みの `market_data` パッケージに、OKX 版のデータソースアダプタを追加してください。

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
   - `exchange` プロパティ: 取引所名 (例: `"okx"`)
   - `fetch(data_type, symbol, start_time, end_time, *, interval, period)` → `pd.DataFrame`
2. **`DataType` enum**: データ種別ごとの正規カラムスキーマ (`DataType.OHLCV.columns` 等)
3. **`HttpClient`**: 共有のHTTPクライアント (retry, rate limit) — 各取引所アダプタから利用
4. **Factory**: `create_source("okx")` で取引所を切り替え
5. **エクスポート**: `scripts/export_data.py --exchange okx` で全取引所共通のスクリプトを使用

---

## リファレンス (必ず最初に全て読むこと)

以下のファイルを読み、パターン・設計思想・テスト手法を完全に把握してから実装に入ること:

1. `src/market_data/domain/models.py`
   → DataType enum: 各データ型のカラムスキーマ定義 (`columns`, `uses_interval`, `uses_period`)
   → **全取引所が出力すべき正規カラムの定義元。これに必ず準拠すること**

2. `src/market_data/domain/source.py`
   → FuturesDataSource Protocol: `exchange` プロパティ + `fetch()` メソッド

3. `src/market_data/infra/http_client.py`
   → HttpClient: リトライ(指数バックオフ), レート制限
   → `to_milliseconds()`: datetime/str/int → ミリ秒変換

4. `src/market_data/infra/binance.py`
   → **実装パターンの参考例**
   → `BinanceFuturesSource`: Protocol 実装の具体例
   → `fetch()` → dispatcher dict → 各 `_fetch_*` メソッド

5. `src/market_data/__init__.py`
   → `create_source()` ファクトリ + `_REGISTRY` への登録パターン

6. `tests/test_binance_source.py` → テストパターン参考

7. `scripts/export_data.py` → **変更不要** (`--exchange okx` で自動的に使える)

8. `pyproject.toml` → 依存関係と build-system 設定

---

## 作成・変更するファイル

### 新規作成

1. `src/market_data/infra/okx.py` → `OkxFuturesSource` クラス (FuturesDataSource 実装)
2. `tests/test_okx_source.py` → OkxFuturesSource のテスト
3. `data/okx/.gitkeep` → 出力ディレクトリ

### 変更 (最小限)

4. `src/market_data/__init__.py` → `_ensure_registry()` に OKX を追加:
   ```python
   from .infra.okx import OkxFuturesSource
   _REGISTRY["okx"] = OkxFuturesSource
   ```

---

## 実装パターン (binance.py に倣う)

```python
# src/market_data/infra/okx.py

from ..domain.models import DataType
from .http_client import HttpClient, to_milliseconds

BASE_URL = "https://www.okx.com"

class OkxFuturesSource:
    def __init__(self, max_retries=3, rate_limit_sleep=0.1):
        self._http = HttpClient(max_retries=max_retries, rate_limit_sleep=rate_limit_sleep)

    @property
    def exchange(self) -> str:
        return "okx"

    def fetch(self, data_type, symbol, start_time, end_time, *, interval=None, period=None):
        dispatcher = { DataType.OHLCV: self._fetch_ohlcv, ... }
        return dispatcher[data_type](...)
```

### 重要: DataFrame の出力カラムは DataType.columns に完全一致させること

---

## OKX V5 API 仕様

Base URL: `https://www.okx.com`

### 重要な相違点

- **シンボル形式**: `"BTC-USDT-SWAP"` (Binanceの `"BTCUSDT"` と異なる)
  → `fetch()` の `symbol` 引数は標準形式 (`"BTCUSDT"`) で受け取り、内部で OKX 形式に変換するヘルパーを用意
  → 変換ロジック: `XXXUSDT → XXX-USDT-SWAP`, `XXXUSD → XXX-USD-SWAP`
- **レスポンス**: `{"code":"0","msg":"","data":[...]}`
  → `code != "0"` はエラー
  → `_api_get()` ヘルパーで `data` の中身だけ返す
- **Kline は降順(新→古)で返る** → 昇順ソート必須
- **ページネーション**: `before`/`after` パラメータ (startTime/endTime ではない)
  - `after=ts` → ts より前(古い)のデータを返す。遡るには取得済み最古tsを`after`に設定

### Kline系 (共通構造)

レスポンス:

```
data = [[ts, o, h, l, c, vol, volCcy, volCcyQuote, confirm], ...]
```

- `ts`: ミリ秒 (文字列) → int変換必要
- `confirm`: `"0"`=未確定, `"1"`=確定
- limit: 最大100件/リクエスト

| DataType | エンドポイント | 備考 |
|---|---|---|
| `OHLCV` | `GET /api/v5/market/history-candles` | 過去データ用。instId, bar, after, before, limit |
| `INDEX_PRICE` | `GET /api/v5/market/index-candles` | instId は `"BTC-USDT"` (SWAPなし) |
| `MARK_PRICE` | `GET /api/v5/market/mark-price-candles` | instId は `"BTC-USDT-SWAP"` |

**bar パラメータ**: `"1m","3m","5m","15m","30m","1H","2H","4H","6H","12H","1D","1W","1M"`

**H/D は大文字** (Binanceの `"1h","1d"` と異なる)
→ 内部で `"1h"→"1H"`, `"4h"→"4H"`, `"1d"→"1D"` の変換が必要

### Funding Rate

```
GET /api/v5/public/funding-rate-history
```

params: `instId, before, after, limit(最大100)`

```
data = [{"instId","fundingRate","realizedRate","fundingTime"}, ...]
```

→ 出力: `DataType.FUNDING_RATE.columns` = `["timestamp", "symbol", "funding_rate", "mark_price"]`
→ `mark_price` が API にない場合は `NaN` で埋める

### Open Interest 履歴

```
GET /api/v5/rubik/stat/contracts-open-interest-history
```

params: `instId, period(5m,1H,1D), begin, end`

```
data = [{"ts","oi","oiCcy"}, ...]
```

**パラメータ名が `begin`/`end`** (startTime/endTime ではない)

→ 出力: `DataType.OPEN_INTEREST.columns` = `["timestamp", "symbol", "open_interest", "open_interest_value"]`

### Long/Short Ratio

```
GET /api/v5/rubik/stat/contracts-long-short-account-ratio
```

params: `instId, period(5m,1H,1D), begin, end`

```
data = [{"ts","ratio"}, ...]
```

→ 出力: `DataType.LONG_SHORT_RATIO.columns` = `["timestamp", "symbol", "long_short_ratio", "long_account", "short_account"]`
→ `ratio` から `long_account`, `short_account` を算出 (ratio = long/short なので)

### Taker Volume

```
GET /api/v5/rubik/stat/taker-volume
```

params: `ccy(BTC等 ※instIdではなく通貨名), instType=CONTRACTS, begin, end, period`

```
data = [{"ts","sellVol","buyVol"}, ...]
```

**`ccy` パラメータ**: `"BTC"` (シンボルではなく通貨名を使う)
→ symbol から通貨名を抽出するヘルパーが必要

→ 出力: `DataType.TAKER_BUY_SELL.columns` = `["timestamp", "buy_sell_ratio", "buy_vol", "sell_vol"]`
→ `buy_sell_ratio` は `buyVol / sellVol` で計算

---

## 実装時の注意点

1. **pandas 3.x**: `datetime64[ms, UTC]` → テストでは `str(...).startswith("datetime64[")` で検証
2. **MagicMock**: `mock._http.get.return_value` を明示的に設定
3. **uv sync**: 新モジュール追加後に必要
4. **OKX レスポンスラッパー**:
   ```python
   def _api_get(self, url, params=None):
       resp = self._http.get(url, params)
       if resp.get("code") != "0":
           raise RuntimeError(f"OKX API error: {resp}")
       return resp["data"]
   ```
5. **シンボル変換**: `_to_inst_id("BTCUSDT")` → `"BTC-USDT-SWAP"` を内部ヘルパーとして定義
6. **降順→昇順ソート**: Kline 系は取得後に timestamp でソート

---

## テストパターン

- 全 DataType について `list(df.columns) == DataType.*.columns` を検証
- mock は `source._http.get` をパッチし、OKX のレスポンス構造 (`code`/`data`) を再現
- ファクトリ: `create_source("okx")` のテスト

---

## 実行手順

1. リファレンスファイルを全て読む (特に `binance.py` のパターンを熟読)
2. `src/market_data/infra/okx.py` を作成
3. `src/market_data/__init__.py` の `_ensure_registry()` に OKX を追加
4. `tests/test_okx_source.py` を作成
5. `data/okx/.gitkeep` を作成
6. `uv sync` を実行
7. `uv run pytest tests/test_okx_source.py -v` で全テスト通過を確認
8. 既存テストも壊れていないか確認: `uv run pytest -v`
9. git add → git commit → git push
