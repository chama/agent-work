# Bitget Futures Data Client 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
既に実装済みの Binance クライアント (src/binance_client/) と全く同じパターンで、Bitget 版を実装してください。

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

1. `src/bitget_client/__init__.py` → `BitgetFuturesClient` をエクスポート
2. `src/bitget_client/base.py` → `BitgetBaseClient` + `to_milliseconds`
3. `src/bitget_client/futures.py` → `BitgetFuturesClient`
4. `scripts/export_bitget_data.py` → CSV出力スクリプト
5. `tests/test_bitget_client.py`
6. `tests/test_export_bitget_data.py`
7. `data/bitget/.gitkeep`

---

## Bitget V2 API 仕様

Base URL: `https://api.bitget.com`

productType: `"USDT-FUTURES"`

### レスポンス形式

```json
{"code":"00000","msg":"success","requestTime":...,"data":[...]}
```

- `code != "00000"` はエラー
- `_request` で `data` の中身だけ返す

### シンボル形式

`"BTCUSDT"` (Binanceと同じ)

### Kline系

| メソッド | エンドポイント | Limit | 備考 |
|---|---|---|---|
| `get_klines` | `GET /api/v2/mix/market/candles` | 200 | 直近データ |
| (古いデータ) | `GET /api/v2/mix/market/history-candles` | 200 | 古いデータ用 |
| `get_mark_price_klines` | `GET /api/v2/mix/market/mark-price-candles` | 200 | |
| `get_index_price_klines` | `GET /api/v2/mix/market/index-price-candles` | 200 | |

共通params: `productType, symbol, granularity, startTime(ms), endTime(ms), limit`

Kline レスポンス:

```
data = [[ts, open, high, low, close, vol, quoteVol], ...]
```

granularity: `"1m","3m","5m","15m","30m","1h","4h","6h","12h","1d","3d","1w","1M"`

ページネーション: 取得済み最古の `ts - 1` を `endTime` に設定して遡る (降順の可能性あり → ソート必要)

**`get_klines` 内で `candles` と `history-candles` を自動切替すると便利**
(candles で取得できない古いデータは history-candles にフォールバック)

### Funding Rate

```
GET /api/v2/mix/market/history-fund-rate
```

params: `productType, symbol, pageSize(最大100), pageNo(1始まり)`

```
data = [{"symbol","fundingRate","fundingTime"}, ...]
```

**ページネーション: pageNo ベース** (1, 2, 3...)。data が空になるまで pageNo をインクリメント

### Open Interest 履歴

```
GET /api/v2/mix/market/open-interest-history
```

params: `productType, symbol, period(5m,15m,30m,1h,4h,1d), limit`

```
data = [{"ts","openInterest"}, ...]
```

WebFetch で実際のパラメータ・レスポンスを確認推奨

### Long/Short Ratio

```
GET /api/v2/mix/market/account-long-short
```

params: `productType, symbol, period(5m,15m,30m,1h,4h,1d), limit`

```
data = [{"longShortRatio","longRate","shortRate","ts"}, ...]
```

### スナップショット系

| メソッド | エンドポイント | 備考 |
|---|---|---|
| `get_tickers` | `GET /api/v2/mix/market/tickers?productType=USDT-FUTURES` | 全ティッカー |
| `get_contracts` | `GET /api/v2/mix/market/contracts?productType=USDT-FUTURES` | コントラクト一覧 |
| `get_orderbook` | `GET /api/v2/mix/market/merge-depth` | productType, symbol, limit(1-150) |
| `get_futures_symbols` | contracts から tradable の USDT ペアを抽出 | |

---

## 実装時の注意点 (過去の開発で判明した問題)

1. **pandas 3.x**: `datetime64[ms, UTC]` → `str(...).startswith("datetime64[")` で検証
2. **MagicMock**: 明示的に return_value 設定
3. **uv sync**: 新パッケージ作成後に必要
4. **Funding Rate の pageNo ページネーション**: Binance と異なるロジック。`_fetch_records_raw` とは別のヘルパーが必要かもしれない
5. **candles / history-candles の自動切替**: 取得データが空の場合に history-candles を試す
6. **Bitget API ドキュメント**: https://www.bitget.com/api-doc/common/intro を WebFetch で確認推奨

---

## 設計ルール

Binance版と同パターン:
- 全メソッド DataFrame 返却、自動ページネーション、to_milliseconds対応
- Context manager、リトライ、レート制限
- export: `data/bitget/yyyymmdd_hhmm_[symbol]_[interval]_[type].csv`
- テスト: mock使用、実API呼ばない

---

## 実行手順

1. リファレンス全読み
2. 実装
3. `uv sync`
4. `uv run pytest tests/test_bitget_client.py tests/test_export_bitget_data.py -v` でテスト全パス確認
5. git add → git commit → git push
