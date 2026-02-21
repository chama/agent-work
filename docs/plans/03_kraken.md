# Kraken Data Source 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
DDD アーキテクチャで実装済みの `market_data` パッケージに、Kraken 版のデータソースアダプタを追加してください。

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
4. **Factory**: `create_source("kraken")` で切り替え
5. **エクスポート**: `scripts/export_data.py --exchange kraken` で使用

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

1. `src/market_data/infra/kraken.py` → `KrakenFuturesSource` クラス
2. `tests/test_kraken_source.py` → テスト
3. `data/kraken/.gitkeep`

### 変更 (最小限)

4. `src/market_data/__init__.py` → `_ensure_registry()` に追加:
   ```python
   from .infra.kraken import KrakenFuturesSource
   _REGISTRY["kraken"] = KrakenFuturesSource
   ```

---

## Kraken API 仕様

Kraken は **Spot API** と **Futures API** の2つがある。両方を活用する。

### Spot API

Base URL: `https://api.kraken.com/0/public`

レスポンス: `{"error":[],"result":{...}}` → `error` が空でなければエラー

シンボル形式: `"XXBTZUSD"`, `"XETHZUSD"` 等 (Krakenの独自命名)
→ ただし `"BTCUSD"`, `"ETHUSD"` でも受け付ける場合がある

| DataType | エンドポイント | パラメータ | 備考 |
|---|---|---|---|
| `OHLCV` | `GET /OHLC` | pair, interval(分: 1,5,15,30,60,240,1440,10080,21600), since(UNIXタイムスタンプ秒) | `result.{pair}` = `[[ts,o,h,l,c,vwap,vol,count],...]`, `result.last` |

**注意:**
- OHLC の `since`: UNIXタイムスタンプ(秒)。レスポンスの `result.last` を次の `since` に使う
- `interval` は分単位: 1, 5, 15, 30, 60, 240, 1440(1d), 10080(1w), 21600(15d)
- OHLC のタイムスタンプも秒単位 → `pd.to_datetime(unit="s", utc=True)`

→ interval 変換: `"1m"→1`, `"5m"→5`, `"1h"→60`, `"4h"→240`, `"1d"→1440`

→ 出力: `DataType.OHLCV.columns` に準拠。Kraken は `close_time`, `quote_volume`, `taker_buy_volume`, `taker_buy_quote_volume` を持たないので `NaN` で埋める

### Futures API

Base URL: `https://futures.kraken.com/derivatives/api/v3`

レスポンス: `{"result":"success","tickers":[...]}` 等 (エンドポイントにより異なる)

シンボル形式: `"PF_XBTUSD"` (perpetual futures), `"PF_BTCUSDT"` 等

| DataType | エンドポイント | パラメータ | 備考 |
|---|---|---|---|
| `FUNDING_RATE` | `GET /historicalfundingrates` | symbol | `[{timestamp, fundingRate, relativeFundingRate},...]` |

→ 出力: `DataType.FUNDING_RATE.columns` = `["timestamp", "symbol", "funding_rate", "mark_price"]`
→ `mark_price` は API にない → `NaN` で埋める

### 設計方針

- `OHLCV` は Spot API の OHLC を使用 (最も信頼性が高い)
- `FUNDING_RATE` は Futures API を使用
- `_api_get_spot()` / `_api_get_futures()` の2つのヘルパーを用意
- サポートしない DataType に対しては空 DataFrame を返すか、`NotImplementedError` を送出

### サポート範囲

Kraken の公開 API はデータ種類が限定的:
- **サポート可能**: OHLCV, FUNDING_RATE
- **サポート不可** (API なし): INDEX_PRICE, MARK_PRICE, OPEN_INTEREST, LONG_SHORT_RATIO, TOP_LS_ACCOUNTS, TOP_LS_POSITIONS, TAKER_BUY_SELL
- サポート外の DataType は dispatcher に含めず、KeyError で適切にエラーにする

---

## 実装時の注意点

1. **pandas 3.x**: `datetime64[ms, UTC]` → `str(...).startswith("datetime64[")` で検証
2. **MagicMock**: `mock._http.get.return_value` を明示的に設定
3. **uv sync**: 新モジュール追加後に必要
4. **Kraken OHLC のタイムスタンプは秒単位** → `pd.to_datetime(unit="s", utc=True)`
5. **Kraken のペア名が独特** (XXBTZUSD等) → レスポンスの result キーがペア名になるため、取得時に適切なキーで取り出す
6. **Spot と Futures でレスポンス形式が異なる** → それぞれ専用のパーサーを用意
7. **Futures API のドキュメント**: WebFetch で https://docs.futures.kraken.com/ を確認推奨

---

## テストパターン

- `DataType.OHLCV` と `DataType.FUNDING_RATE` について正規カラムとの一致を検証
- Spot API / Futures API それぞれのレスポンス形式を mock で再現
- ファクトリ: `create_source("kraken")` のテスト

---

## 実行手順

1. リファレンスファイルを全て読む
2. `src/market_data/infra/kraken.py` を作成
3. `src/market_data/__init__.py` の `_ensure_registry()` に追加
4. `tests/test_kraken_source.py` を作成
5. `data/kraken/.gitkeep` を作成
6. `uv sync`
7. `uv run pytest tests/test_kraken_source.py -v` で全テスト通過を確認
8. 既存テストも壊れていないか確認: `uv run pytest -v`
9. git add → git commit → git push
