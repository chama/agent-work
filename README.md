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

データ取得:
```bash
uv run python scripts/fetch_binance_data.py
```
