# Bitget Futures Data Source 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
DDD アーキテクチャで実装済みの `market_data` パッケージに、Bitget 版のデータソースアダプタを追加してください。

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
4. **Factory**: `create_source("bitget")` で切り替え
5. **エクスポート**: `scripts/export_data.py --exchange bitget` で使用

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

1. `src/market_data/infra/bitget.py` → `BitgetFuturesSource` クラス (FuturesDataSource 実装)
2. `tests/test_bitget_source.py` → テスト
3. `data/bitget/.gitkeep`

### 変更 (最小限)

4. `src/market_data/__init__.py` → `_ensure_registry()` に追加:
   ```python
   from .infra.bitget import BitgetFuturesSource
   _REGISTRY["bitget"] = BitgetFuturesSource
   ```

---

## Bitget V2 API 仕様

Base URL: `https://api.bitget.com`

productType: `"USDT-FUTURES"`

### レスポンス形式

```json
{"code":"00000","msg":"success","requestTime":...,"data":[...]}
```

- `code != "00000"` はエラー
- `_api_get()` ヘルパーで `data` の中身だけ返す

### シンボル形式

`"BTCUSDT"` (Binanceと同じ)

### Kline系

| DataType | エンドポイント | Limit | 備考 |
|---|---|---|---|
| `OHLCV` | `GET /api/v2/mix/market/candles` | 200 | 直近データ |
| (古いデータ) | `GET /api/v2/mix/market/history-candles` | 200 | 古いデータ用 |
| `MARK_PRICE` | `GET /api/v2/mix/market/mark-price-candles` | 200 | |
| `INDEX_PRICE` | `GET /api/v2/mix/market/index-price-candles` | 200 | |

共通params: `productType, symbol, granularity, startTime(ms), endTime(ms), limit`

Kline レスポンス:
```
data = [[ts, open, high, low, close, vol, quoteVol], ...]
```

granularity: `"1m","3m","5m","15m","30m","1h","4h","6h","12h","1d","3d","1w","1M"`

ページネーション: 取得済み最古の `ts - 1` を `endTime` に設定して遡る (降順の可能性あり → ソート必要)

**`_fetch_ohlcv` 内で `candles` と `history-candles` を自動切替すると便利**
(candles で取得できない古いデータは history-candles にフォールバック)

→ 出力: `DataType.OHLCV.columns` に準拠
→ `close_time`, `trades`, `taker_buy_volume`, `taker_buy_quote_volume` はない → `NaN` / `0` で埋める

### Funding Rate

```
GET /api/v2/mix/market/history-fund-rate
```

params: `productType, symbol, pageSize(最大100), pageNo(1始まり)`

```
data = [{"symbol","fundingRate","fundingTime"}, ...]
```

**ページネーション: pageNo ベース** (1, 2, 3...)。data が空になるまで pageNo をインクリメント

→ 出力: `DataType.FUNDING_RATE.columns` = `["timestamp", "symbol", "funding_rate", "mark_price"]`
→ `mark_price` がない場合は `NaN` で埋める

### Open Interest 履歴

```
GET /api/v2/mix/market/open-interest-history
```

params: `productType, symbol, period(5m,15m,30m,1h,4h,1d), limit`

```
data = [{"ts","openInterest"}, ...]
```

→ 出力: `DataType.OPEN_INTEREST.columns` = `["timestamp", "symbol", "open_interest", "open_interest_value"]`
→ `open_interest_value` がない場合は `NaN` で埋める

WebFetch で実際のパラメータ・レスポンスを確認推奨

### Long/Short Ratio

```
GET /api/v2/mix/market/account-long-short
```

params: `productType, symbol, period(5m,15m,30m,1h,4h,1d), limit`

```
data = [{"longShortRatio","longRate","shortRate","ts"}, ...]
```

→ 出力: `DataType.LONG_SHORT_RATIO.columns` = `["timestamp", "symbol", "long_short_ratio", "long_account", "short_account"]`
→ `longRate` → `long_account`, `shortRate` → `short_account` にマッピング

---

## 実装時の注意点

1. **pandas 3.x**: `datetime64[ms, UTC]` → `str(...).startswith("datetime64[")` で検証
2. **MagicMock**: `mock._http.get.return_value` を明示的に設定
3. **uv sync**: 新モジュール追加後に必要
4. **Funding Rate の pageNo ページネーション**: Binance と異なるロジック。専用のページネーションヘルパーが必要
5. **candles / history-candles の自動切替**: 取得データが空の場合に history-candles を試す
6. **Bitget API ドキュメント**: https://www.bitget.com/api-doc/common/intro を WebFetch で確認推奨

---

## テストパターン

- 全サポート DataType について `list(df.columns) == DataType.*.columns` を検証
- Bitget のレスポンス構造 (`code`/`data`) を mock で再現
- pageNo ページネーションのテスト
- candles / history-candles 自動切替のテスト
- ファクトリ: `create_source("bitget")` のテスト

---

## 実行手順

1. リファレンスファイルを全て読む
2. `src/market_data/infra/bitget.py` を作成
3. `src/market_data/__init__.py` の `_ensure_registry()` に追加
4. `tests/test_bitget_source.py` を作成
5. `data/bitget/.gitkeep` を作成
6. `uv sync`
7. `uv run pytest tests/test_bitget_source.py -v` で全テスト通過を確認
8. 既存テストも壊れていないか確認: `uv run pytest -v`
9. git add → git commit → git push
