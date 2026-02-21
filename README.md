# Crypto Analysis Workspace

暗号資産取引の分析ワークスペース。

## Directory Structure

```
analyses/          # 分析用 (Jupyter notebook)
data/              # マーケットデータ (parquet, duckdb)
docs/
  knowledges/      # 分析で得られた知見 (md)
  plans/           # 作業計画 (md)
  sessions/        # セッション記録 (md)
scripts/           # データ取得・分析スクリプト
src/               # 自作Pythonパッケージ
tests/             # テスト
```

## Setup

```bash
uv sync
```

## Usage

### Binance Futures データ取得

`BinanceFuturesClient` を使い、任意のシンボル・期間のデータを CSV で `data/binance/` に出力する。

```bash
# 全データタイプを一括取得
uv run scripts/export_binance_data.py \
  --symbol BTCUSDT --start 2025-01-01 --end 2025-02-01

# 特定のデータのみ取得
uv run scripts/export_binance_data.py \
  --symbol BTCUSDT --start 2025-01-01 --end 2025-02-01 \
  --types klines,funding_rate

# インターバル・集計期間を指定
uv run scripts/export_binance_data.py \
  --symbol ETHUSDT --start 2025-01-01 --end 2025-02-01 \
  --interval 4h --period 15m

# 取得可能なデータタイプ一覧
uv run scripts/export_binance_data.py --list-types
```

#### 引数

| 引数 | 説明 | デフォルト |
|---|---|---|
| `--symbol` | 取引ペア (BTCUSDT 等) | 必須 |
| `--start` | 開始日 (YYYY-MM-DD) | 必須 |
| `--end` | 終了日 (YYYY-MM-DD) | 必須 |
| `--interval` | ローソク足間隔 (1m,5m,15m,1h,4h,1d 等) | `1h` |
| `--period` | 分析系データの集計期間 (5m,15m,1h,4h,1d 等) | `1h` |
| `--types` | カンマ区切りでデータ種類を指定 | 全種類 |
| `--output-dir` | 出力先ディレクトリ | `data/binance` |

#### 取得可能データ

| タイプ | 内容 |
|---|---|
| `klines` | OHLCV ローソク足 |
| `index_price` | インデックス価格 (現物加重平均) |
| `mark_price` | マーク価格 (清算・PnL 用公正価格) |
| `funding_rate` | ファンディングレート履歴 |
| `open_interest` | 建玉残高推移 (直近30日) |
| `long_short_ratio` | グローバル ロング/ショート比率 (直近30日) |
| `top_ls_accounts` | トップトレーダー LS 比率 - アカウント数 (直近30日) |
| `top_ls_positions` | トップトレーダー LS 比率 - ポジション量 (直近30日) |
| `taker_buy_sell` | テイカー売買比率 (直近30日) |

出力ファイル名: `yyyymmdd_hhmm_[symbol]_[interval]_[type].csv`

### Python からの利用

```python
from binance_client import BinanceFuturesClient

client = BinanceFuturesClient()
df = client.get_klines("BTCUSDT", "1h", "2025-01-01", "2025-02-01")
df.to_parquet("data/btcusdt_1h.parquet")
```

### 分析ノートブック

```bash
uv run jupyter notebook
```
