# Bybit Futures Data Client 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
既に実装済みの Binance クライアント (src/binance_client/) と全く同じパターンで、Bybit 版を実装してください。

---

## プロジェクト規約

- Python 操作は常に uv を使う (uv run, uv sync)
- データは data/ 以下に保存
- ファイル名規則: yyyymmdd_hhmm_[概要].csv
- パッケージは src/ 以下に配置 (setuptools が自動発見する)
- テスト: uv run pytest

---

## リファレンス (必ず最初に全て読むこと)

以下のファイルを読み、パターン・設計思想・テスト手法を完全に把握してから実装に入ること:

1. `src/binance_client/base.py`
   → BaseClient: リトライ(指数バックオフ), レート制限, to_milliseconds(datetime/str/int対応)
   → context manager (`__enter__`/`__exit__`)

2. `src/binance_client/futures.py`
   → `_fetch_klines_raw`: kline形式のページネーション汎用ヘルパー
   → `_fetch_records_raw`: JSON record形式のページネーション汎用ヘルパー
   → `_klines_to_df`: 生データ→DataFrame変換 (型変換、カラム名)
   → 各 `get_*` メソッド: 全て pandas DataFrame を返す
   → スナップショット系 (ticker, orderbook, premium_index) も実装

3. `scripts/export_binance_data.py`
   → CLI (argparse): `--symbol`, `--start`, `--end`, `--interval`, `--period`, `--types`, `--output-dir`, `--list-types`
   → `make_filename()`: yyyymmdd_hhmm_[symbol]_[interval]_[type].csv
   → `fetch_and_save()`: fetchers dict でデータ種別→取得関数をマッピング
   → `main(argv)`: テスタブルな設計 (argv引数, int戻り値)

4. `tests/test_binance_client.py`
   → to_milliseconds の網羅テスト
   → BaseClient: mock response でリトライ・エラー処理テスト
   → FuturesClient: mock `_request` でデータ変換・ページネーションテスト

5. `tests/test_export_binance_data.py`
   → make_filename: `datetime.now()` を patch
   → parse_args: 引数パーステスト
   → fetch_and_save: mock client でCSV保存確認
   → main: mock BinanceFuturesClient で統合テスト

6. `pyproject.toml` → 現在の依存関係と build-system 設定を確認

---

## 作成するファイル (これ以外は変更禁止)

1. `src/bybit_client/__init__.py` → `BybitFuturesClient` をエクスポート
2. `src/bybit_client/base.py` → `BybitBaseClient` + `to_milliseconds`
3. `src/bybit_client/futures.py` → `BybitFuturesClient` (全メソッド)
4. `scripts/export_bybit_data.py` → CSV出力スクリプト
5. `tests/test_bybit_client.py` → クライアントテスト
6. `tests/test_export_bybit_data.py` → エクスポートスクリプトテスト
7. `data/bybit/.gitkeep` → 出力ディレクトリ

---

## Bybit V5 API 仕様

Base URL: `https://api.bybit.com`
カテゴリ: `category=linear` (USDT無期限先物)

### レスポンス形式

全エンドポイント共通:

```json
{"retCode":0,"retMsg":"OK","result":{...},"time":...}
```

- `_request` では `retCode` を検証し、`result` の中身だけを返すこと
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

→ export スクリプトでは以下の変換マッピングが必要:
- `"1m"→"1"`, `"3m"→"3"`, `"5m"→"5"`, `"15m"→"15"`, `"30m"→"30"`
- `"1h"→"60"`, `"2h"→"120"`, `"4h"→"240"`, `"6h"→"360"`, `"12h"→"720"`
- `"1d"→"D"`, `"1w"→"W"`, `"1M"→"M"`

| メソッド | エンドポイント | 固有パラメータ |
|---|---|---|
| `get_klines` | `GET /v5/market/kline` | category, symbol, interval, start, end, limit |
| `get_index_price_klines` | `GET /v5/market/index-price-kline` | 同上 |
| `get_mark_price_klines` | `GET /v5/market/mark-price-kline` | 同上 |

### Funding Rate

```
GET /v5/market/funding/history
```

params: `category=linear, symbol, startTime, endTime, limit(最大200)`

```
result.list = [{"symbol","fundingRate","fundingRateTimestamp"}, ...]
```

ページネーション: 最古の `fundingRateTimestamp - 1` を次の `endTime` に

### Open Interest

```
GET /v5/market/open-interest
```

params: `category=linear, symbol, intervalTime(5min,15min,30min,1h,4h,1d), startTime, endTime, limit(最大200), cursor`

```
result.list = [{"openInterest","timestamp"}, ...]
result.nextPageCursor → 次のリクエストの cursor パラメータに使用
```

### Long/Short Ratio

```
GET /v5/market/account-ratio
```

params: `category=linear, symbol, period(5min,15min,30min,1h,4h,1d), limit(最大500)`

```
result.list = [{"symbol","buyRatio","sellRatio","timestamp"}, ...]
```

### スナップショット系

| メソッド | エンドポイント |
|---|---|
| `get_tickers` | `GET /v5/market/tickers?category=linear` |
| `get_instruments_info` | `GET /v5/market/instruments-info?category=linear` |
| `get_orderbook` | `GET /v5/market/orderbook?category=linear&symbol=...&limit=...` |
| `get_futures_symbols` | instruments-info から `status="Trading"` の USDT ペアを抽出 |

---

## 実装時の注意点 (過去の開発で判明した問題)

1. **pandas 3.x** では `pd.to_datetime(unit="ms")` が `datetime64[ms, UTC]` を返す (ns ではない)
   → テストで dtype 検証する場合: `assert str(df["timestamp"].dtype).startswith("datetime64[")`

2. **MagicMock** の `dir()` は未アクセスの属性を列挙しない
   → テストでは `for attr in dir(mock)` ではなく、`mock.get_klines.return_value = ...` のように明示的に設定

3. 新パッケージ作成後は **`uv sync`** が必要 (setuptools がパッケージを再発見するため)

4. export スクリプトのテストで scripts/ を sys.path に追加する必要がある:
   ```python
   sys.path.insert(0, str(Path(__file__).resolve().parent.parent / "scripts"))
   ```

---

## 設計ルール

- 全データ取得メソッドは pandas DataFrame を返す
- timestamp列: `pd.to_datetime(unit="ms", utc=True)`
- float列: `.astype(float)`
- 空レスポンス: 空の DataFrame を返す (`pd.DataFrame()`)
- ページネーションは内部で自動的に全件取得
- `to_milliseconds`: datetime, str(`'YYYY-MM-DD'` / `'YYYY-MM-DD HH:MM:SS'`), int(ms) を受付
- Context manager 対応 (`__enter__`/`__exit__`)
- export ファイル名: `yyyymmdd_hhmm_[symbol lower]_[interval]_[type].csv`
- export 先: `data/bybit/`
- テストは全て `unittest.mock` を使い、実 API を呼ばない

---

## 実行手順

1. リファレンスファイルを全て読む
2. `src/bybit_client/` パッケージを作成
3. `scripts/export_bybit_data.py` を作成
4. `tests/` を作成
5. `uv sync` を実行
6. `uv run pytest tests/test_bybit_client.py tests/test_export_bybit_data.py -v` で全テスト通過を確認
7. git add → git commit → git push
