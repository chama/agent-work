# Phemex Futures Data Source 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
DDD アーキテクチャで実装済みの `market_data` パッケージに、Phemex 版のデータソースアダプタを追加してください。

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
4. **Factory**: `create_source("phemex")` で切り替え
5. **エクスポート**: `scripts/export_data.py --exchange phemex` で使用

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

1. `src/market_data/infra/phemex.py` → `PhemexFuturesSource` クラス (FuturesDataSource 実装)
2. `tests/test_phemex_source.py` → テスト
3. `data/phemex/.gitkeep`

### 変更 (最小限)

4. `src/market_data/__init__.py` → `_ensure_registry()` に追加:
   ```python
   from .infra.phemex import PhemexFuturesSource
   _REGISTRY["phemex"] = PhemexFuturesSource
   ```

---

## Phemex API 仕様

Base URL: `https://api.phemex.com`

### 重要な特徴

- **一部エンドポイントは価格を Ep (scaled integer) 形式で返す**
  → USDT建てコントラクトでは通常スケーリング不要だが、確認が必要
  → スケーリングが必要な場合: `実価格 = Ep値 / 10^(priceScale)`

- **Kline のタイムスタンプ・パラメータは秒単位** (ミリ秒ではない)

- **APIドキュメントを WebFetch で確認推奨**: https://phemex-docs.github.io/

### Kline

```
GET /exchange/public/md/v2/kline
```

params: `symbol, resolution(秒: 60,300,900,1800,3600,14400,86400), from(秒), to(秒)`

レスポンス:
```json
{
  "code": 0,
  "msg": "OK",
  "data": {
    "total": -1,
    "rows": [
      [timestamp, interval, lastCloseEp, openEp, highEp, lowEp, closeEp, volumeEv, turnoverEv, ...]
    ]
  }
}
```

**注意:**
- rows 内のカラム順: `[ts, interval, lastClose, open, high, low, close, volume, turnover, ...]`
- Ep/Ev の扱い: USDT契約では `priceScale=4` → `Ep / 10^4 = 実価格` (要確認)
- `from`/`to` は秒単位 → `to_milliseconds()` の結果を `// 1000` して秒に変換
- ページネーション: 取得済み最新ts + resolution を次の from に
- `code != 0` はエラー → `_api_get()` ヘルパーで `data` を抽出

interval → resolution 変換:

| interval | resolution (秒) |
|---|---|
| `"1m"` | 60 |
| `"5m"` | 300 |
| `"15m"` | 900 |
| `"30m"` | 1800 |
| `"1h"` | 3600 |
| `"4h"` | 14400 |
| `"1d"` | 86400 |

→ 出力: `DataType.OHLCV.columns` に準拠
→ `close_time`, `trades`, `taker_buy_volume`, `taker_buy_quote_volume` はない → `NaN` / `0` で埋める

### Funding Rate

```
GET /api-data/public/data/funding-rate-history
```

params: `symbol, start(ページオフセットまたはタイムスタンプ), end, limit(200)`

レスポンス:
```json
{
  "code": 0,
  "data": {
    "rows": [
      {"symbol", "fundingRate", "fundingRateTimestamp", "timestamp", ...}
    ]
  }
}
```

→ 出力: `DataType.FUNDING_RATE.columns` = `["timestamp", "symbol", "funding_rate", "mark_price"]`
→ `mark_price` がない場合は `NaN` で埋める

**Funding Rate History は `/api-data` パスの場合あり**

### サポート範囲

Phemex は公開データ種類が限定的:
- **サポート可能**: OHLCV, FUNDING_RATE
- **サポート不可** (パブリックAPIなし): INDEX_PRICE, MARK_PRICE, OPEN_INTEREST, LONG_SHORT_RATIO, TOP_LS_ACCOUNTS, TOP_LS_POSITIONS, TAKER_BUY_SELL
- **取得可能なデータのみ実装し、存在しないものは無理に実装しない**

---

## 実装時の注意点

1. **pandas 3.x**: `datetime64[ms, UTC]` → `str(...).startswith("datetime64[")` で検証
2. **MagicMock**: `mock._http.get.return_value` を明示的に設定
3. **uv sync**: 新モジュール追加後に必要
4. **タイムスタンプ秒単位のエンドポイント**: `to_milliseconds()` の結果を `// 1000` して秒に変換
5. **Ep/Ev スケーリング**: USDT契約で必要かどうかをドキュメントで確認
6. **WebFetch で API ドキュメントの最新情報を確認してから実装に入ること**

---

## テストパターン

- `DataType.OHLCV` と `DataType.FUNDING_RATE` について正規カラムとの一致を検証
- Phemex のレスポンス構造 (`code`/`data`/`rows`) を mock で再現
- Ep スケーリングのテスト (該当する場合)
- ファクトリ: `create_source("phemex")` のテスト

---

## 実行手順

1. リファレンスファイルを全て読む
2. **WebFetch で Phemex API ドキュメントを確認**
3. `src/market_data/infra/phemex.py` を作成
4. `src/market_data/__init__.py` の `_ensure_registry()` に追加
5. `tests/test_phemex_source.py` を作成
6. `data/phemex/.gitkeep` を作成
7. `uv sync`
8. `uv run pytest tests/test_phemex_source.py -v` で全テスト通過を確認
9. 既存テストも壊れていないか確認: `uv run pytest -v`
10. git add → git commit → git push
