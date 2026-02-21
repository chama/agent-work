# Binance データCSVエクスポート

## ゴール

BinanceFuturesClientで取得した全種類のデータを、任意の期間・シンボルを指定して
`data/binance/yyyymmdd_hhmm_[概要].csv` 形式で出力できるようにする。

## タスクリスト

- [ ] **T-1: エクスポートスクリプト作成**（実装）M — FR-1, FR-2
  - 内容: CLIで --symbol, --start, --end, --interval, --period, --types を受け取り、
    BinanceFuturesClientで各データを取得し CSV保存する
  - 成果物: `scripts/export_binance_data.py`

- [ ] **T-2: テスト**（テスト）S — AC-1
  - 内容: スクリプトのファイル名生成・データ型選択ロジックのユニットテスト
  - 成果物: `tests/test_export_binance_data.py`
