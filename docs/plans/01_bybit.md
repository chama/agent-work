# Bybit Futures Data Source 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
DDD アーキテクチャで実装済みの `market_data` パッケージに、Bybit 版のデータソースアダプタを追加してください。

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
   - `exchange` プロパティ: 取引所名 (例: `"bybit"`)
   - `fetch(data_type, symbol, start_time, end_time, *, interval, period)` → `pd.DataFrame`
2. **`DataType` enum**: データ種別ごとの正規カラムスキーマ (`DataType.OHLCV.columns` 等)
3. **`HttpClient`**: 共有のHTTPクライアント (retry, rate limit) — 各取引所アダプタから利用
4. **Factory**: `create_source("bybit")` で取引所を切り替え
5. **エクスポート**: `scripts/export_data.py --exchange bybit` で全取引所共通のスクリプトを使用

---

## リファレンス (必ず最初に全て読むこと)

以下のファイルを読み、パターン・設計思想・テスト手法を完全に把握してから実装に入ること:

1. `src/market_data/domain/models.py`
   → DataType enum: 各データ型のカラムスキーマ定義 (`columns`, `uses_interval`, `uses_period`)
   → **全取引所が出力すべき正規カラムの定義元。これに必ず準拠すること**

2. `src/market_data/domain/source.py`
   → FuturesDataSource Protocol: `exchange` プロパティ + `fetch()` メソッド
   → **実装すべきインターフェースの定義**

3. `src/market_data/infra/http_client.py`
   → HttpClient: リトライ(指数バックオフ), レート制限
   → `to_milliseconds()`: datetime/str/int → ミリ秒変換

4. `src/market_data/infra/binance.py`
   → **実装パターンの参考例**
   → `BinanceFuturesSource`: Protocol 実装の具体例
   → `fetch()` → dispatcher dict → 各 `_fetch_*` メソッド
   → `_paginate_klines` / `_paginate_records`: ページネーションヘルパー
   → `_klines_to_df` / `_records_to_ls_df`: raw → canonical DataFrame 変換

5. `src/market_data/__init__.py`
   → `create_source()` ファクトリ + `_REGISTRY` への登録パターン

6. `tests/test_binance_source.py`
   → テストパターン: mock `_http.get` でデータ変換・ページネーションテスト
   → `DataType.*.columns` との一致検証

7. `scripts/export_data.py`
   → 取引所非依存の CLI。`--exchange`, `--symbol`, `--types` 等
   → **このファイルの変更は不要** (Bybit は自動的に `--exchange bybit` で使える)

8. `pyproject.toml` → 現在の依存関係と build-system 設定を確認

---

## 作成・変更するファイル

### 新規作成

1. `src/market_data/infra/bybit.py` → `BybitFuturesSource` クラス (FuturesDataSource 実装)
2. `tests/test_bybit_source.py` → BybitFuturesSource のテスト
3. `data/bybit/.gitkeep` → 出力ディレクトリ

### 変更 (最小限)

4. `src/market_data/__init__.py` → `_ensure_registry()` に Bybit を追加:
   ```python
   from .infra.bybit import BybitFuturesSource
   _REGISTRY["bybit"] = BybitFuturesSource
   ```

---

## 実装パターン (binance.py に倣う)

```python
# src/market_data/infra/bybit.py

from ..domain.models import DataType
from .http_client import HttpClient, to_milliseconds

BASE_URL = "https://api.bybit.com"

class BybitFuturesSource:
    def __init__(self, max_retries=3, rate_limit_sleep=0.1):
        self._http = HttpClient(max_retries=max_retries, rate_limit_sleep=rate_limit_sleep)

    @property
    def exchange(self) -> str:
        return "bybit"

    def close(self): ...
    def __enter__(self): ...
    def __exit__(self, *args): ...

    def fetch(self, data_type, symbol, start_time, end_time, *, interval=None, period=None):
        dispatcher = {
            DataType.OHLCV: self._fetch_ohlcv,
            DataType.INDEX_PRICE: self._fetch_index_price,
            # ... 各 DataType をマッピング
        }
        return dispatcher[data_type](symbol=symbol, start_time=start_time, end_time=end_time, interval=interval, period=period)

    # 各 _fetch_* メソッドで:
    # 1. Bybit API を呼び出し (ページネーション含む)
    # 2. Bybit 固有レスポンスを DataType.columns に準拠した DataFrame に変換
    # 3. 空レスポンスは pd.DataFrame() を返す
```

### 重要: DataFrame の出力カラムは DataType.columns に完全一致させること

例:
- `DataType.OHLCV.columns` → `["timestamp", "open", "high", "low", "close", "volume", "close_time", "quote_volume", "trades", "taker_buy_volume", "taker_buy_quote_volume"]`
- `DataType.FUNDING_RATE.columns` → `["timestamp", "symbol", "funding_rate", "mark_price"]`

Bybit API が対応するフィールドを持たない場合は `None` / `0` / `NaN` で埋める。

---

## Bybit V5 API 仕様

Base URL: `https://api.bybit.com`
カテゴリ: `category=linear` (USDT無期限先物)

### レスポンス形式

全エンドポイント共通:

```json
{"retCode":0,"retMsg":"OK","result":{...},"time":...}
```

- `_http.get()` のレスポンスから `retCode` を検証し、`result` の中身だけを返すラッパーを用意
- `retCode != 0` はエラー (RuntimeError)

### Kline系

Kline / IndexPrice / MarkPrice は全て同じレスポンス構造:

```
result.list = [[startTime, open, high, low, close, volume, turnover], ...]
```

**重要:**
- 降順(新しい→古い)で返る。取得後に昇順ソートが必須
- ページネーション: `result.list` の最古要素の `startTime - 1` を次の `end` として遡る
- limit: 最大200件/リクエスト

interval パラメータ: 数値(分) = `1,3,5,15,30,60,120,240,360,720` または文字 = `D,W,M`

→ `_fetch_ohlcv` 内で以下の変換マッピングが必要:
- `"1m"→"1"`, `"3m"→"3"`, `"5m"→"5"`, `"15m"→"15"`, `"30m"→"30"`
- `"1h"→"60"`, `"2h"→"120"`, `"4h"→"240"`, `"6h"→"360"`, `"12h"→"720"`
- `"1d"→"D"`, `"1w"→"W"`, `"1M"→"M"`

| DataType | エンドポイント | 固有パラメータ |
|---|---|---|
| `OHLCV` | `GET /v5/market/kline` | category, symbol, interval, start, end, limit |
| `INDEX_PRICE` | `GET /v5/market/index-price-kline` | 同上 |
| `MARK_PRICE` | `GET /v5/market/mark-price-kline` | 同上 |

### Funding Rate

```
GET /v5/market/funding/history
```

params: `category=linear, symbol, startTime, endTime, limit(最大200)`

```
result.list = [{"symbol","fundingRate","fundingRateTimestamp"}, ...]
```

ページネーション: 最古の `fundingRateTimestamp - 1` を次の `endTime` に

→ 出力: `DataType.FUNDING_RATE.columns` = `["timestamp", "symbol", "funding_rate", "mark_price"]`
→ Bybit API に `mark_price` がない場合は `NaN` で埋める

### Open Interest

```
GET /v5/market/open-interest
```

params: `category=linear, symbol, intervalTime(5min,15min,30min,1h,4h,1d), startTime, endTime, limit(最大200), cursor`

```
result.list = [{"openInterest","timestamp"}, ...]
result.nextPageCursor → 次のリクエストの cursor パラメータに使用
```

→ 出力: `DataType.OPEN_INTEREST.columns` = `["timestamp", "symbol", "open_interest", "open_interest_value"]`
→ `open_interest_value` が API にない場合は `NaN` で埋める

### Long/Short Ratio

```
GET /v5/market/account-ratio
```

params: `category=linear, symbol, period(5min,15min,30min,1h,4h,1d), limit(最大500)`

```
result.list = [{"symbol","buyRatio","sellRatio","timestamp"}, ...]
```

→ 出力: `DataType.LONG_SHORT_RATIO.columns` = `["timestamp", "symbol", "long_short_ratio", "long_account", "short_account"]`
→ `buyRatio` / `sellRatio` → `long_account` / `short_account` にマッピング
→ `long_short_ratio` = `buyRatio / sellRatio` で計算

---

## 実装時の注意点 (過去の開発で判明した問題)

1. **pandas 3.x** では `pd.to_datetime(unit="ms")` が `datetime64[ms, UTC]` を返す (ns ではない)
   → テストで dtype 検証する場合: `assert str(df["timestamp"].dtype).startswith("datetime64[")`

2. **MagicMock** の `dir()` は未アクセスの属性を列挙しない
   → テストでは `mock._http.get.return_value = ...` のように明示的に設定

3. 新しい infra モジュール追加後は **`uv sync`** が必要 (setuptools がパッケージを再発見)

4. **Bybit のレスポンスラッパー**: `_http.get()` の結果から `retCode` 検証 + `result` 抽出するヘルパーを `bybit.py` 内に定義
   ```python
   def _api_get(self, url, params=None):
       resp = self._http.get(url, params)
       if resp.get("retCode") != 0:
           raise RuntimeError(f"Bybit API error: {resp}")
       return resp["result"]
   ```

5. **降順→昇順ソート**: Kline 系は全て降順で返るので、ページネーション完了後に timestamp でソートすること

---

## テストパターン (test_binance_source.py に倣う)

```python
# tests/test_bybit_source.py

from market_data import DataType, create_source
from market_data.infra.bybit import BybitFuturesSource

class TestFactory:
    def test_create_bybit_source(self):
        source = create_source("bybit", rate_limit_sleep=0)
        assert source.exchange == "bybit"

class TestOhlcv:
    def test_fetch_returns_canonical_columns(self):
        source = BybitFuturesSource(rate_limit_sleep=0)
        # Bybit kline レスポンスを mock
        raw_response = {"retCode": 0, "retMsg": "OK", "result": {"list": [...]}}
        with patch.object(source._http, "get", return_value=raw_response):
            df = source.fetch(DataType.OHLCV, "BTCUSDT", "2024-01-01", "2024-01-02", interval="1h")
        assert list(df.columns) == DataType.OHLCV.columns  # ← 正規カラムとの一致を検証
```

- 全 DataType について `list(df.columns) == DataType.*.columns` を検証すること
- mock は `source._http.get` をパッチし、Bybit のレスポンス構造 (`retCode`/`result`) を再現

---

## 実行手順

1. リファレンスファイルを全て読む (特に `binance.py` のパターンを熟読)
2. `src/market_data/infra/bybit.py` を作成
3. `src/market_data/__init__.py` の `_ensure_registry()` に Bybit を追加
4. `tests/test_bybit_source.py` を作成
5. `data/bybit/.gitkeep` を作成
6. `uv sync` を実行
7. `uv run pytest tests/test_bybit_source.py -v` で全テスト通過を確認
8. 既存テストも壊れていないか確認: `uv run pytest -v`
9. git add → git commit → git push
