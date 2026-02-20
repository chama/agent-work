# Workspace Rules

## Tools
- always use uv when python relevant task (e.g `uv run hoge.py`, `uv add [package name]`)
- analyses (Jupyter notebook) は `uv run jupyter notebook` で起動

## Directory Structure

```
analyses/          # 分析用フォルダ。分析はJupyter notebookで行う
data/              # データ用フォルダ。マーケットデータをparquet形式で保存。duckdbも使用
docs/
  knowledges/      # 分析により得られた知見をmd形式で保存
  plans/           # 作業計画をmd形式で保存
  sessions/        # 会話内容をmd形式で保存
scripts/           # データ取得や分析のためのスクリプト
src/               # 自作Pythonパッケージ
tests/             # テスト
```

## Naming Convention

ファイルやフォルダには **日時プレフィックス + 分析概要** の命名規則を使用する。
直近の成果物がディレクトリの末尾に集まるため、すぐに見つけられる。

### Format
```
YYYYMMDD_HHMM_analysis_topic
```

### Examples
- `20260218_0930_btc_volatility_analysis.ipynb`
- `20260218_1400_stablecoin_flow.ipynb`
- `20260218_btc_eth_correlation.md`

## Analysis Workflow

1. **データ取得**: `scripts/` のスクリプトで取引所からデータを取得し `data/` に保存
2. **分析**: `analyses/` でJupyter notebookを使って分析を実施
3. **知見の記録**: 分析で得られた知見を `docs/knowledges/` にmd形式で保存
4. **計画**: 作業計画は `docs/plans/` にmd形式で保存

## Data Format
- マーケットデータは基本的に **parquet形式** で保存する
- 大量データの集計には **duckdb** を使用する
- CSVは一時的な用途のみに使用し、永続的なデータ保存にはparquetを使う
