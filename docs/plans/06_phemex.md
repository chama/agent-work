# Phemex Futures Data Client 実装プロンプト

あなたは暗号資産データ分析用リポジトリで作業しています。
既に実装済みの Binance クライアント (src/binance_client/) と全く同じパターンで、Phemex 版を実装してください。

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

1. `src/phemex_client/__init__.py` → `PhemexFuturesClient` をエクスポート
2. `src/phemex_client/base.py` → `PhemexBaseClient` + `to_milliseconds`
3. `src/phemex_client/futures.py` → `PhemexFuturesClient`
4. `scripts/export_phemex_data.py` → CSV出力スクリプト
5. `tests/test_phemex_client.py`
6. `tests/test_export_phemex_data.py`
7. `data/phemex/.gitkeep`

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
- `from`/`to` は秒単位
- ページネーション: 取得済み最新ts + resolution を次の from に

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

**Funding Rate History は `/api-data` パスの場合あり**

### その他のエンドポイント

| メソッド | エンドポイント | 備考 |
|---|---|---|
| `get_trades` | `GET /md/v2/trade` | symbol, limit で直近トレード |
| `get_tickers` | `GET /md/v2/ticker/24hr` | symbol(任意) で24hティッカー |
| `get_products` | `GET /public/products` | コントラクト一覧 |
| `get_orderbook` | `GET /md/orderbook` | symbol で板情報 |

### 公開データの制限

Phemex は他取引所と比べて公開データ種類が少ない:
- OI履歴、LS比率、テイカー比率等はパブリックAPIで取得できない可能性が高い
- **取得可能なデータのみ実装し、存在しないものは無理に実装しない**
- export スクリプトの types も実装したデータのみ含める

---

## 実装時の注意点 (過去の開発で判明した問題)

1. **pandas 3.x**: `datetime64[ms, UTC]` → `str(...).startswith("datetime64[")` で検証
2. **MagicMock**: 明示的に return_value 設定
3. **uv sync**: 新パッケージ作成後に必要
4. **タイムスタンプ秒単位のエンドポイント**: `to_milliseconds` の結果を `// 1000` して秒に変換
5. **Ep/Ev スケーリング**: `get_products` でコントラクトの `priceScale`/`valueScale` を取得し変換
6. **WebFetch で API ドキュメントの最新情報を確認してから実装に入ること**

---

## 設計ルール

Binance版と同パターン:
- 全メソッド DataFrame 返却、自動ページネーション、to_milliseconds対応
- Context manager、リトライ、レート制限
- export: `data/phemex/yyyymmdd_hhmm_[symbol]_[interval]_[type].csv`
- テスト: mock使用、実API呼ばない

---

## 実行手順

1. リファレンス全読み
2. **WebFetch で Phemex API ドキュメントを確認**
3. 実装
4. `uv sync`
5. `uv run pytest tests/test_phemex_client.py tests/test_export_phemex_data.py -v` でテスト全パス確認
6. git add → git commit → git push
