# Binance実装 DDDレビュー

**日付**: 2026-02-21
**対象**: `src/binance_client/`, `scripts/export_binance_data.py`, `tests/`

---

## 1. 現状のアーキテクチャ概観

```
scripts/export_binance_data.py   ← CLI（プレゼンテーション層）
        │
        ▼
src/binance_client/
    ├── __init__.py               ← 公開API
    ├── futures.py                ← BinanceFuturesClient（アプリケーション + インフラ混在）
    └── base.py                   ← BinanceBaseClient（HTTPインフラ）+ to_milliseconds
        │
        ▼
    Binance REST API              ← 外部サービス
        │
        ▼
    data/binance/*.csv            ← 永続化（CSV出力）
```

現状は「薄いインフラ層」+「全てを担うクライアントクラス」+「手続き的なCLIスクリプト」の3層構成。ドメインモデルは存在せず、DataFrameがデータ伝達の唯一の手段となっている。

---

## 2. 良い点（DDDの観点で評価できるもの）

### 2.1 ユビキタス言語の一部反映

メソッド名やカラム名がBinance先物取引のドメイン用語をそのまま使っている。

```python
# futures.py:266-303
def get_funding_rate_history(...)   # ファンディングレート
def get_open_interest_history(...)  # 建玉
def get_long_short_ratio(...)       # ロング/ショート比率
def get_taker_buy_sell_ratio(...)   # テイカー売買比率
```

カラム名の変換も、Binance APIの`camelCase`からドメインに近い`snake_case`に統一的にマッピングされている（`fundingRate` → `funding_rate`）。これはAnti-Corruption Layer（腐敗防止層）の萌芽と言える。

### 2.2 インフラ関心事の分離

`BinanceBaseClient`がHTTP通信・リトライ・レート制限をカプセル化し、`BinanceFuturesClient`はこれを継承してデータ取得に集中できている。

```python
# base.py:41-100
class BinanceBaseClient:
    # リトライ、429/418ハンドリング、レート制限スリープ
    def _request(self, url, params=None): ...
```

### 2.3 ページネーションの透過性

`_fetch_klines_raw`と`_fetch_records_raw`が自動ページネーションを提供し、呼び出し側はデータ量を意識せずに済む。これはRepository的なパターンの利点を部分的に実現している。

### 2.4 テストの分離

テストがモック(`_request`のパッチ)でHTTP層を分離し、データ変換ロジックに集中している。テストクラスの構成もデータ種別ごとに整理されており、可読性が高い。

---

## 3. DDDの観点での課題

### 3.1 [Critical] ドメインモデルの不在

**現在の最大の問題。** ドメイン層が存在しない。

全てのデータ取得メソッドが`pd.DataFrame`を直接返すため、以下の問題が生じている：

- **ドメイン知識の散逸**: 「ファンディングレートが正ならロングがショートに支払う」といったドメインルールを表現する場所がない
- **不変条件の欠如**: OHLCVで`high >= low`であるべき、funding_rateは通常±0.75%以内、等の制約が表現されない
- **振る舞いの外出し**: ドメインの計算（例: annualized funding rate = rate × 3 × 365）がクライアント外のスクリプトやnotebookに散在する

```python
# 現状: futures.py では raw data → DataFrame の変換のみ
df = pd.DataFrame(raw)
df = df.rename(columns={...})
df["funding_rate"] = df["funding_rate"].astype(float)
return df[["timestamp", "symbol", "funding_rate", "mark_price"]]
```

**あるべき姿（参考）**:
```python
# 例: ドメインモデルがあればこのような記述が可能
@dataclass(frozen=True)
class FundingRate:
    timestamp: datetime
    symbol: str
    rate: Decimal
    mark_price: Decimal

    @property
    def annualized(self) -> Decimal:
        return self.rate * 3 * 365

    @property
    def direction(self) -> str:
        return "longs_pay" if self.rate > 0 else "shorts_pay"
```

### 3.2 [Critical] 境界づけられたコンテキスト（Bounded Context）の未定義

`BinanceFuturesClient`が1つのクラスに全データ種別を詰め込んでおり（763行、17メソッド）、凝集度が低い。DDDの「1つのBounded Contextは1つの問題領域に集中する」原則に反している。

現状のメソッド一覧からは、少なくとも以下のコンテキストが識別できる：

| コンテキスト | 該当メソッド | 関心事 |
|---|---|---|
| 価格データ | `get_klines`, `get_index_price_klines`, `get_mark_price_klines` | OHLCV、公正価格 |
| ポジション分析 | `get_funding_rate_history`, `get_open_interest_history` | 先物固有指標 |
| センチメント分析 | `get_long_short_ratio`, `get_top_trader_*`, `get_taker_buy_sell_ratio` | 投資家行動 |
| 約定データ | `get_agg_trades` | ティックレベル取引 |
| 市場スナップショット | `get_ticker_24hr`, `get_premium_index`, `get_book_depth`, `get_open_interest` | リアルタイム状態 |

### 3.3 [High] リポジトリパターンの不在

データ取得ロジック（HTTP + ページネーション）とデータ変換ロジック（DataFrame構築）が同一クラス内で密結合している。

```python
# futures.py:266-303 — 1つのメソッドに3つの責務
def get_funding_rate_history(self, symbol, start_time, end_time, limit=1000):
    raw = self._fetch_records_raw(...)   # 1. HTTP通信 + ページネーション
    df = pd.DataFrame(raw)               # 2. データ変換
    df = df.rename(columns={...})         # 3. ドメインマッピング
    return df
```

リポジトリパターンを適用すれば、データソースの差し替え（例: parquetキャッシュからの読み込み）が容易になる。現状は「毎回APIから取得」しか選択肢がない。

### 3.4 [High] 値オブジェクト（Value Object）の不在

以下のドメイン概念がプリミティブ型で表現されており、バリデーションが分散している：

| 概念 | 現状の型 | 問題 |
|---|---|---|
| シンボル | `str` | `"btcusdt"`と`"BTCUSDT"`の混在を防げない |
| インターバル | `str` | 不正な値（`"2d"`等）がランタイムまで検出されない |
| タイムスタンプ | `int/str/datetime` | `to_milliseconds`で都度変換、型が不統一 |
| 期間 | `str` | Kline用とAnalytics用で有効値が異なるが型で区別されない |

`futures.py`にバリデーション定数は定義されているが、実際の検証はされていない：

```python
# futures.py:35-42 — 定義されているが使われていない
KLINE_INTERVALS = {"1m", "3m", "5m", ...}
ANALYTICS_PERIODS = {"5m", "15m", ...}

# get_klines()内でintervalのバリデーションがない
def get_klines(self, symbol, interval, start_time, end_time, limit=1500):
    raw = self._fetch_klines_raw(
        "/fapi/v1/klines",
        {"symbol": symbol, "interval": interval},  # 不正値がそのまま渡る
        ...
    )
```

### 3.5 [High] ユースケース層の不在

`scripts/export_binance_data.py`がCLI引数パーシング・データ取得・CSV保存を全て手続き的に処理している。ユースケース（アプリケーションサービス）として分離されていないため：

- 同じデータ取得ロジックをJupyter notebookから使いたい場合、スクリプトの関数を直接importするか、同じコードを書き直す必要がある
- テストがCLIの表面的な振る舞いに依存し、ビジネスロジックのテストが困難

```python
# export_binance_data.py:67-130 — fetch_and_saveがdispatcher + orchestratorを兼ねる
def fetch_and_save(client, symbol, start, end, interval, period, data_type, output_dir):
    fetchers = {
        "klines": lambda: (client.get_klines(...), interval),
        "funding_rate": lambda: (client.get_funding_rate_history(...), None),
        # ...
    }
    df, suffix = fetchers[data_type]()
    df.to_csv(filepath, index=False)
```

### 3.6 [Medium] エラードメインの不在

全てのエラーが`RuntimeError`で表現されている。DDDではドメイン固有の例外を定義し、呼び出し側がエラーの種類に応じた処理を行えるようにする。

```python
# base.py — 全て RuntimeError
raise RuntimeError(f"IP banned by Binance: {resp.text}")       # IPバン
raise RuntimeError(f"HTTP {resp.status_code}: {resp.text}")     # サーバーエラー
raise RuntimeError(f"Request failed after {self.max_retries}...") # ネットワークエラー
```

区別すべきエラー：
- `RateLimitExceeded` — リトライ可能
- `IPBanned` — 即座に停止すべき
- `InvalidSymbol` — ユーザー入力ミス
- `DataUnavailable` — 30日制限等のAPI制約

### 3.7 [Medium] Anti-Corruption Layer（腐敗防止層）の不完全さ

Binance APIの構造がドメインモデルに漏れている例：

```python
# futures.py:87 — Binance APIの内部仕様（index 6 = close_time）がクライアントに露出
current = data[-1][6] + 1

# futures.py:594 — APIの短縮キー("a", "p", "T"等)がメソッド内に直接出現
df = df.rename(columns={
    "a": "agg_trade_id",
    "p": "price",
    ...
})
```

APIレスポンスの構造変更がクライアントコードに直接影響する。マッパークラスを導入して変換を局所化すべき。

### 3.8 [Medium] 継承 vs 委譲

`BinanceFuturesClient`が`BinanceBaseClient`を**継承**している。DDDでは外部サービスへの依存は**委譲（コンポジション）**で持つ方が、テスタビリティと責務分離の面で好ましい。

```python
# 現状: 継承
class BinanceFuturesClient(BinanceBaseClient): ...

# 推奨: 委譲
class BinanceFuturesClient:
    def __init__(self, http_client: BinanceBaseClient):
        self._http = http_client
```

継承では`BinanceFuturesClient`のテスト時に`_request`をパッチする必要があるが、委譲ならモックを注入するだけで済む。

### 3.9 [Low] コード重複

Long/Short ratio関連の3メソッド（`get_long_short_ratio`, `get_top_trader_long_short_ratio_accounts`, `get_top_trader_long_short_ratio_positions`）がほぼ同一のコード構造を持つ（エンドポイントURLのみが異なる）。

```python
# futures.py:354-397 と 403-443 と 449-489 が同一パターン
df = pd.DataFrame(raw)
df = df.rename(columns={
    "longShortRatio": "long_short_ratio",
    "longAccount": "long_account",
    "shortAccount": "short_account",
})
df["timestamp"] = pd.to_datetime(df["timestamp"], unit="ms", utc=True)
for col in ["long_short_ratio", "long_account", "short_account"]:
    df[col] = df[col].astype(float)
```

これはDDDの問題というよりDRY原則の問題だが、ドメインモデルを導入すれば自然に解消される。

---

## 4. データフロー図と課題マッピング

```
[CLI: export_binance_data.py]
     │  ← 3.5: ユースケース層なし
     ▼
[BinanceFuturesClient]
     │  ← 3.1: ドメインモデルなし
     │  ← 3.2: 全データ種別が1クラスに集中
     │  ← 3.3: HTTP通信とデータ変換が同一メソッド
     │  ← 3.4: バリデーションなし
     │  ← 3.7: APIレスポンス構造が漏洩
     │  ← 3.8: 継承で密結合
     ▼
[BinanceBaseClient]
     │  ← 3.6: 全エラーがRuntimeError
     ▼
[Binance REST API]
```

---

## 5. 改善提案の優先順位

このプロジェクトは個人の分析ツールであり、大規模チーム開発とは前提が異なる。DDDの全要素を導入する必要はないが、以下の優先順で実用的な改善が見込める。

### Priority 1: 値オブジェクト + バリデーション（効果: 高 / コスト: 低）

最も費用対効果が高い改善。不正な引数が実行時に静かに失敗する現状は分析ツールとして致命的。

```python
# src/binance_client/types.py (新規)
from dataclasses import dataclass

@dataclass(frozen=True)
class Symbol:
    value: str
    def __post_init__(self):
        object.__setattr__(self, 'value', self.value.upper())
        if not self.value.endswith("USDT"):
            raise ValueError(f"USDT-M futures require USDT pair: {self.value}")

@dataclass(frozen=True)
class KlineInterval:
    value: str
    VALID = {"1m","3m","5m","15m","30m","1h","2h","4h","6h","8h","12h","1d","3d","1w","1M"}
    def __post_init__(self):
        if self.value not in self.VALID:
            raise ValueError(f"Invalid interval: {self.value}. Valid: {self.VALID}")
```

### Priority 2: エラー型の整理（効果: 中 / コスト: 低）

```python
# src/binance_client/exceptions.py (新規)
class BinanceError(Exception): ...
class RateLimitError(BinanceError): ...
class IPBanError(BinanceError): ...
class APIError(BinanceError):
    def __init__(self, status_code: int, message: str): ...
```

### Priority 3: 重複コードの共通化（効果: 中 / コスト: 低）

Long/Short ratio系3メソッドの共通化。

```python
def _fetch_long_short_ratio(self, endpoint: str, symbol, period, start_time, end_time, limit):
    """Long/Short ratio系エンドポイントの共通処理"""
    raw = self._fetch_records_raw(endpoint, ...)
    if not raw:
        return pd.DataFrame()
    df = pd.DataFrame(raw)
    df = df.rename(columns={...})
    # 共通変換
    return df
```

### Priority 4: 継承→委譲への変更（効果: 中 / コスト: 中）

テスタビリティ向上とDI（依存性注入）の基盤。

### Priority 5: リポジトリパターン（効果: 高 / コスト: 高）

APIキャッシュ（parquet保存→再利用）を実現する場合に必要。分析ワークフロー上、同じデータを何度も取得する可能性が高いため、長期的には費用対効果が高い。

```python
# 例: リポジトリインターフェース
class FuturesDataRepository(Protocol):
    def get_klines(self, symbol: Symbol, interval: KlineInterval,
                   start: datetime, end: datetime) -> pd.DataFrame: ...

# Binance API実装
class BinanceAPIRepository(FuturesDataRepository): ...

# キャッシュ付き実装（Decorator）
class CachedRepository(FuturesDataRepository):
    def __init__(self, inner: FuturesDataRepository, cache_dir: Path): ...
```

### Priority 6以降: Bounded Context分割、ドメインモデル導入

プロジェクトの規模と目的（個人分析ツール）を考慮すると、完全なDDDモデルは過剰設計（YAGNI）になる可能性が高い。上記Priority 1-5を実施した上で、複雑なドメインロジック（例: 複合指標の計算、アラート条件の定義等）が増えた段階で検討するのが妥当。

---

## 6. 総評

現時点の実装は「データ取得ユーティリティ」として十分に機能しており、コードの可読性・テストカバレッジ・エラーハンドリングの基本は押さえている。DDDの全要素が欠けているが、個人の分析ツールという文脈では必ずしも全てが必要ではない。

特に評価できるのは：
- APIレスポンスの命名変換（腐敗防止層の萌芽）
- ページネーションの透過的処理
- テストでのHTTP層分離

改善すべき優先事項は：
1. **値オブジェクト + バリデーション** — 不正入力の早期検出
2. **エラー型の整理** — 障害対応の明確化
3. **コード重複の排除** — 保守性向上

これらはDDDの「戦術的パターン」の中でも軽量な部分であり、現在のアーキテクチャを大幅に変更せずに導入可能。
