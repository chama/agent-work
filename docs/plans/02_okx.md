# OKX Futures Data Client 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
既に実装済みの Binance クライアント (src/binance_client/) と全く同じパターンで、OKX 版を実装してください。

---

## プロジェクト規約

- Python 操作は常に uv を使う (uv run, uv sync)
- データは data/ 以下に保存
- ファイル名規則: yyyymmdd_hhmm_[概要].csv
- パッケージは src/ 以下に配置 (setuptools が自動発見)
- テスト: uv run pytest

---

## リファレンス (必ず最初に全て読むこと)

1. `src/binance_client/base.py` → BaseClient設計、to_milliseconds、リトライ
2. `src/binance_client/futures.py` → ページネーションヘルパー、DataFrame変換、全メソッド
3. `scripts/export_binance_data.py` → CLI設計、make_filename、fetch_and_save、main(argv)
4. `tests/test_binance_client.py` → クライアントテストパターン
5. `tests/test_export_binance_data.py` → exportテストパターン
6. `pyproject.toml` → 依存関係と build-system

---

## 作成するファイル (これ以外は変更禁止)

1. `src/okx_client/__init__.py` → `OkxFuturesClient` をエクスポート
2. `src/okx_client/base.py` → `OkxBaseClient` + `to_milliseconds`
3. `src/okx_client/futures.py` → `OkxFuturesClient`
4. `scripts/export_okx_data.py` → CSV出力スクリプト
5. `tests/test_okx_client.py`
6. `tests/test_export_okx_data.py`
7. `data/okx/.gitkeep`

---

## OKX V5 API 仕様

Base URL: `https://www.okx.com`

### 重要な相違点

- **シンボル形式**: `"BTC-USDT-SWAP"` (Binanceの `"BTCUSDT"` と異なる)
  → export スクリプトで `"BTCUSDT"` 入力を `"BTC-USDT-SWAP"` に自動変換するヘルパーを用意
  → 変換ロジック: `XXXUSDT → XXX-USDT-SWAP`, `XXXUSD → XXX-USD-SWAP`
- **レスポンス**: `{"code":"0","msg":"","data":[...]}`
  → `code != "0"` はエラー
  → `_request` で `data` の中身だけ返す
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

| メソッド | エンドポイント | 備考 |
|---|---|---|
| `get_klines` | `GET /api/v5/market/history-candles` | 過去データ用。instId, bar, after, before, limit |
| `get_index_price_klines` | `GET /api/v5/market/index-candles` | instId は `"BTC-USDT"` (SWAPなし) |
| `get_mark_price_klines` | `GET /api/v5/market/mark-price-candles` | instId は `"BTC-USDT-SWAP"` |

**bar パラメータ**: `"1m","3m","5m","15m","30m","1H","2H","4H","6H","12H","1D","1W","1M"`

**H/D は大文字** (Binanceの `"1h","1d"` と異なる)
→ export スクリプトで `"1h"→"1H"`, `"4h"→"4H"`, `"1d"→"1D"` の変換が必要

### Funding Rate

```
GET /api/v5/public/funding-rate-history
```

params: `instId, before, after, limit(最大100)`

```
data = [{"instId","fundingRate","realizedRate","fundingTime"}, ...]
```

### Open Interest 履歴

```
GET /api/v5/rubik/stat/contracts-open-interest-history
```

params: `instId, period(5m,1H,1D), begin, end`

```
data = [{"ts","oi","oiCcy"}, ...]
```

**パラメータ名が `begin`/`end`** (startTime/endTime ではない)

### Long/Short Ratio

```
GET /api/v5/rubik/stat/contracts-long-short-account-ratio
```

params: `instId, period(5m,1H,1D), begin, end`

```
data = [{"ts","ratio"}, ...]
```

### Taker Volume

```
GET /api/v5/rubik/stat/taker-volume
```

params: `ccy(BTC等 ※instIdではなく通貨名), instType=CONTRACTS, begin, end, period`

```
data = [{"ts","sellVol","buyVol"}, ...]
```

**`ccy` パラメータ**: `"BTC"` (シンボルではなく通貨名を使う)

### スナップショット系

| メソッド | エンドポイント |
|---|---|
| `get_tickers` | `GET /api/v5/market/tickers?instType=SWAP` |
| `get_instruments` | `GET /api/v5/public/instruments?instType=SWAP` |
| `get_orderbook` | `GET /api/v5/market/books?instId=...&sz=...` |
| `get_futures_symbols` | instruments から `state=live` の SWAP を抽出 |

---

## 実装時の注意点 (過去の開発で判明した問題)

1. **pandas 3.x**: `datetime64[ms, UTC]` → テストでは `str(...).startswith("datetime64[")` で検証
2. **MagicMock**: `dir()` は未アクセス属性を列挙しない → 明示的に `mock.get_klines.return_value = ...` と設定
3. **uv sync**: 新パッケージ作成後に必要
4. export テスト: scripts/ を sys.path に追加必要

---

## 設計ルール

Binance版と完全に同じ設計思想:
- 全メソッド DataFrame 返却、自動ページネーション、to_milliseconds対応
- Context manager、リトライ、レート制限
- export: `data/okx/yyyymmdd_hhmm_[symbol]_[interval]_[type].csv`
- テスト: mock使用、実API呼ばない

---

## 実行手順

1. リファレンス全読み
2. 実装
3. `uv sync`
4. `uv run pytest tests/test_okx_client.py tests/test_export_okx_data.py -v` でテスト全パス確認
5. git add → git commit → git push
