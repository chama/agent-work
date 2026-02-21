# Day 2 演習問題: ドメインモデルとモデリング

---

## 演習1: 貧血ドメインモデル → リッチドメインモデルへのリファクタリング

### 課題概要

以下の「銀行口座（BankAccount）」システムは貧血ドメインモデルで実装されています。
これをリッチドメインモデルにリファクタリングしてください。

### Before コード（貧血ドメインモデル）

```python
"""
銀行口座システム — 貧血ドメインモデル（リファクタリング前）

【問題点を見つけてください】
1. BankAccount にビジネスロジックがない
2. 不正な状態を外部から作れる
3. ビジネスルールが AccountService に散在している
"""

from dataclasses import dataclass
from datetime import datetime
from enum import Enum


class AccountStatus(Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"


@dataclass
class BankAccount:
    """銀行口座 — データだけのクラス"""
    account_id: str
    owner_name: str
    balance: int  # 残高（円）
    status: AccountStatus = AccountStatus.ACTIVE
    daily_withdrawal_total: int = 0  # 当日の出金合計
    last_withdrawal_date: str = ""   # 最終出金日（YYYY-MM-DD）


@dataclass
class TransactionRecord:
    """取引記録 — データだけのクラス"""
    transaction_id: str
    account_id: str
    transaction_type: str  # "deposit" or "withdrawal"
    amount: int
    timestamp: str
    description: str = ""


class AccountService:
    """口座サービス — 全てのビジネスロジックがここにある"""

    DAILY_WITHDRAWAL_LIMIT = 500000  # 1日の出金上限: 50万円
    MINIMUM_BALANCE = 0               # 最低残高: 0円
    MAX_DEPOSIT_AMOUNT = 10000000     # 1回の入金上限: 1000万円

    def deposit(self, account: BankAccount, amount: int, description: str = "") -> TransactionRecord:
        """入金する"""
        # バリデーション
        if amount <= 0:
            raise ValueError("入金額は1円以上でなければなりません")

        if amount > self.MAX_DEPOSIT_AMOUNT:
            raise ValueError(f"1回の入金上限は{self.MAX_DEPOSIT_AMOUNT:,}円です")

        if account.status != AccountStatus.ACTIVE:
            raise ValueError("アクティブな口座にのみ入金できます")

        # 残高を更新
        account.balance += amount

        # 取引記録を作成
        record = TransactionRecord(
            transaction_id=f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            account_id=account.account_id,
            transaction_type="deposit",
            amount=amount,
            timestamp=datetime.now().isoformat(),
            description=description,
        )
        return record

    def withdraw(self, account: BankAccount, amount: int, description: str = "") -> TransactionRecord:
        """出金する"""
        # バリデーション
        if amount <= 0:
            raise ValueError("出金額は1円以上でなければなりません")

        if account.status != AccountStatus.ACTIVE:
            raise ValueError("アクティブな口座からのみ出金できます")

        if account.balance - amount < self.MINIMUM_BALANCE:
            raise ValueError("残高不足です")

        # 1日の出金上限チェック
        today = datetime.now().strftime("%Y-%m-%d")
        if account.last_withdrawal_date != today:
            account.daily_withdrawal_total = 0
            account.last_withdrawal_date = today

        if account.daily_withdrawal_total + amount > self.DAILY_WITHDRAWAL_LIMIT:
            raise ValueError(
                f"1日の出金上限({self.DAILY_WITHDRAWAL_LIMIT:,}円)を超えます。"
                f"本日の出金済み額: {account.daily_withdrawal_total:,}円"
            )

        # 残高と日次出金額を更新
        account.balance -= amount
        account.daily_withdrawal_total += amount

        record = TransactionRecord(
            transaction_id=f"TXN-{datetime.now().strftime('%Y%m%d%H%M%S')}",
            account_id=account.account_id,
            transaction_type="withdrawal",
            amount=amount,
            timestamp=datetime.now().isoformat(),
            description=description,
        )
        return record

    def transfer(self, from_account: BankAccount, to_account: BankAccount,
                 amount: int, description: str = "") -> tuple[TransactionRecord, TransactionRecord]:
        """振込する"""
        if from_account.account_id == to_account.account_id:
            raise ValueError("同一口座への振込はできません")

        # 出金して入金（ロジックが重複！）
        withdrawal_record = self.withdraw(from_account, amount, f"振込: {description}")
        deposit_record = self.deposit(to_account, amount, f"振込受取: {description}")

        return withdrawal_record, deposit_record

    def freeze_account(self, account: BankAccount) -> None:
        """口座を凍結する"""
        if account.status != AccountStatus.ACTIVE:
            raise ValueError("アクティブな口座のみ凍結できます")
        account.status = AccountStatus.FROZEN

    def close_account(self, account: BankAccount) -> None:
        """口座を解約する"""
        if account.status == AccountStatus.CLOSED:
            raise ValueError("既に解約済みの口座です")
        if account.balance > 0:
            raise ValueError("残高がある口座は解約できません。先に全額出金してください")
        account.status = AccountStatus.CLOSED


# --- 問題のデモ ---
if __name__ == "__main__":
    account = BankAccount(account_id="ACC-001", owner_name="田中太郎", balance=100000)

    # 問題: 不正な状態が簡単に作れる
    account.balance = -999999     # マイナス残高！
    account.status = AccountStatus.ACTIVE  # 凍結口座をアクティブに戻せる！
    account.daily_withdrawal_total = 0     # 出金制限をリセットできる！
```

### リファクタリング要件

以下の要件を満たすリッチドメインモデルに書き直してください：

1. **BankAccount が自分の整合性を守る**
   - 残高がマイナスにならないことを保証する
   - ステータス遷移を自分で管理する（Active → Frozen → Active, Active → Closed）
   - 1日の出金上限を自分で管理する

2. **値オブジェクトを導入する**
   - `Money` — 金額（0以上の整数、不変）
   - `AccountId` — 口座ID（空文字不可、不変）

3. **ドメインイベントを発行する**
   - `MoneyDeposited` — 入金された
   - `MoneyWithdrawn` — 出金された
   - `AccountFrozen` — 口座が凍結された

4. **ビジネスロジックを BankAccount 内に移動する**
   - `account.deposit(amount)` — 入金
   - `account.withdraw(amount)` — 出金
   - `account.freeze()` — 凍結
   - `account.unfreeze()` — 凍結解除
   - `account.close()` — 解約

### ヒント

<details>
<summary>ヒント1: Money 値オブジェクトの設計</summary>

```python
@dataclass(frozen=True)
class Money:
    amount: int

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError("金額は0以上でなければなりません")

    def add(self, other: "Money") -> "Money":
        return Money(self.amount + other.amount)

    def subtract(self, other: "Money") -> "Money":
        # 結果がマイナスになる場合は例外を送出
        ...
```
</details>

<details>
<summary>ヒント2: ステータス遷移の設計</summary>

```python
class AccountStatus(Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"

    def can_transition_to(self, target: "AccountStatus") -> bool:
        allowed = {
            AccountStatus.ACTIVE: {AccountStatus.FROZEN, AccountStatus.CLOSED},
            AccountStatus.FROZEN: {AccountStatus.ACTIVE},  # 凍結解除可能
            AccountStatus.CLOSED: set(),  # 最終状態
        }
        return target in allowed.get(self, set())
```
</details>

<details>
<summary>ヒント3: 1日の出金上限の管理</summary>

```python
class DailyWithdrawalLimit:
    """1日の出金上限を管理する値オブジェクト"""

    LIMIT = Money(500000)

    def __init__(self):
        self._today_total = Money(0)
        self._date = datetime.now().date()

    def can_withdraw(self, amount: Money) -> bool:
        self._reset_if_new_day()
        return self._today_total.add(amount).amount <= self.LIMIT.amount

    def record_withdrawal(self, amount: Money) -> None:
        self._reset_if_new_day()
        self._today_total = self._today_total.add(amount)

    def _reset_if_new_day(self) -> None:
        today = datetime.now().date()
        if self._date != today:
            self._today_total = Money(0)
            self._date = today
```
</details>

### 模範解答

<details>
<summary>模範解答を表示（まずは自分で挑戦してください！）</summary>

```python
"""
銀行口座システム — リッチドメインモデル（リファクタリング後）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, date
from enum import Enum
from typing import Optional


# --- 値オブジェクト ---

@dataclass(frozen=True)
class Money:
    """金額を表す値オブジェクト"""
    amount: int

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError(f"金額は0以上でなければなりません: {self.amount}")

    def add(self, other: Money) -> Money:
        return Money(self.amount + other.amount)

    def subtract(self, other: Money) -> Money:
        result = self.amount - other.amount
        if result < 0:
            raise ValueError("残高不足です")
        return Money(result)

    def is_greater_than(self, other: Money) -> bool:
        return self.amount > other.amount

    @classmethod
    def zero(cls) -> Money:
        return cls(0)


@dataclass(frozen=True)
class AccountId:
    """口座IDを表す値オブジェクト"""
    value: str

    def __post_init__(self):
        if not self.value or not self.value.strip():
            raise ValueError("口座IDは必須です")


# --- ドメインイベント ---

@dataclass(frozen=True)
class DomainEvent:
    occurred_at: datetime = field(default_factory=datetime.now)

@dataclass(frozen=True)
class MoneyDeposited(DomainEvent):
    account_id: str = ""
    amount: int = 0
    new_balance: int = 0

@dataclass(frozen=True)
class MoneyWithdrawn(DomainEvent):
    account_id: str = ""
    amount: int = 0
    new_balance: int = 0

@dataclass(frozen=True)
class AccountFrozen(DomainEvent):
    account_id: str = ""

@dataclass(frozen=True)
class AccountClosed(DomainEvent):
    account_id: str = ""


# --- ステータス ---

class AccountStatus(Enum):
    ACTIVE = "active"
    FROZEN = "frozen"
    CLOSED = "closed"

    def can_transition_to(self, target: AccountStatus) -> bool:
        allowed = {
            AccountStatus.ACTIVE: {AccountStatus.FROZEN, AccountStatus.CLOSED},
            AccountStatus.FROZEN: {AccountStatus.ACTIVE},
            AccountStatus.CLOSED: set(),
        }
        return target in allowed.get(self, set())


# --- 1日の出金制限 ---

class DailyWithdrawalTracker:
    DAILY_LIMIT = Money(500000)

    def __init__(self):
        self._today_total = Money.zero()
        self._date = date.today()

    def can_withdraw(self, amount: Money) -> bool:
        self._reset_if_new_day()
        new_total = self._today_total.add(amount)
        return new_total.amount <= self.DAILY_LIMIT.amount

    def record(self, amount: Money) -> None:
        self._reset_if_new_day()
        self._today_total = self._today_total.add(amount)

    def _reset_if_new_day(self) -> None:
        today = date.today()
        if self._date != today:
            self._today_total = Money.zero()
            self._date = today

    @property
    def remaining_today(self) -> Money:
        self._reset_if_new_day()
        return Money(self.DAILY_LIMIT.amount - self._today_total.amount)


# --- 集約ルート ---

class BankAccount:
    """
    銀行口座 — リッチドメインモデル

    全てのビジネスルールがこのクラス内にカプセル化されている
    """
    MAX_DEPOSIT_AMOUNT = Money(10_000_000)

    def __init__(self, account_id: AccountId, owner_name: str, initial_balance: Money = Money.zero()):
        self._account_id = account_id
        self._owner_name = owner_name
        self._balance = initial_balance
        self._status = AccountStatus.ACTIVE
        self._withdrawal_tracker = DailyWithdrawalTracker()
        self._events: list[DomainEvent] = []

    @property
    def account_id(self) -> AccountId:
        return self._account_id

    @property
    def balance(self) -> Money:
        return self._balance

    @property
    def status(self) -> AccountStatus:
        return self._status

    def deposit(self, amount: Money) -> None:
        """入金する"""
        if amount.amount <= 0:
            raise ValueError("入金額は1円以上でなければなりません")
        if amount.is_greater_than(self.MAX_DEPOSIT_AMOUNT):
            raise ValueError(f"1回の入金上限は{self.MAX_DEPOSIT_AMOUNT.amount:,}円です")
        self._ensure_active("入金")

        self._balance = self._balance.add(amount)
        self._events.append(MoneyDeposited(
            account_id=self._account_id.value,
            amount=amount.amount,
            new_balance=self._balance.amount,
        ))

    def withdraw(self, amount: Money) -> None:
        """出金する"""
        if amount.amount <= 0:
            raise ValueError("出金額は1円以上でなければなりません")
        self._ensure_active("出金")

        if not self._withdrawal_tracker.can_withdraw(amount):
            remaining = self._withdrawal_tracker.remaining_today
            raise ValueError(
                f"1日の出金上限を超えます。本日の残り出金可能額: {remaining.amount:,}円"
            )

        self._balance = self._balance.subtract(amount)  # 残高不足なら例外
        self._withdrawal_tracker.record(amount)
        self._events.append(MoneyWithdrawn(
            account_id=self._account_id.value,
            amount=amount.amount,
            new_balance=self._balance.amount,
        ))

    def freeze(self) -> None:
        """口座を凍結する"""
        self._transition_to(AccountStatus.FROZEN)
        self._events.append(AccountFrozen(account_id=self._account_id.value))

    def unfreeze(self) -> None:
        """凍結を解除する"""
        self._transition_to(AccountStatus.ACTIVE)

    def close(self) -> None:
        """口座を解約する"""
        if self._balance.is_greater_than(Money.zero()):
            raise ValueError("残高がある口座は解約できません")
        self._transition_to(AccountStatus.CLOSED)
        self._events.append(AccountClosed(account_id=self._account_id.value))

    def _ensure_active(self, operation: str) -> None:
        if self._status != AccountStatus.ACTIVE:
            raise ValueError(f"アクティブな口座でのみ{operation}できます")

    def _transition_to(self, target: AccountStatus) -> None:
        if not self._status.can_transition_to(target):
            raise ValueError(
                f"{self._status.value} から {target.value} への遷移はできません"
            )
        self._status = target

    @property
    def domain_events(self) -> list[DomainEvent]:
        return list(self._events)

    def clear_events(self) -> None:
        self._events.clear()
```
</details>

---

## 演習2: 図書館管理システムのイベントストーミング

### 課題概要

あなたは図書館管理システムを開発するチームのメンバーです。
イベントストーミングを実施して、ドメインの全体像を把握してください。

### 背景情報

この図書館では以下の業務が行われています：

- 利用者が本を借りる（最大5冊まで、貸出期間は2週間）
- 利用者が本を返却する
- 延滞した場合、延滞料金が発生する（1日10円/冊）
- 利用者が本を予約する（貸出中の本のみ予約可能）
- 予約した本が返却されたら利用者に通知する
- 司書が新しい本を登録する
- 司書が本の情報を更新する
- 利用者登録と退会の処理がある

### 課題

以下の表を埋めてください：

#### Step 1: ドメインイベント（オレンジの付箋）を洗い出す

過去形で記述してください。少なくとも10個以上見つけてください。

| # | ドメインイベント | 説明 |
|---|----------------|------|
| 1 | （例）本が貸し出された | 利用者が本を借りた |
| 2 | | |
| 3 | | |
| 4 | | |
| 5 | | |
| 6 | | |
| 7 | | |
| 8 | | |
| 9 | | |
| 10 | | |

#### Step 2: コマンド（ブルーの付箋）を特定する

各イベントの原因となるコマンドを特定してください。

| # | コマンド | → 発生するイベント | アクター |
|---|---------|-------------------|---------|
| 1 | （例）本を貸し出す | 本が貸し出された | 司書 |
| 2 | | | |
| 3 | | | |

#### Step 3: 集約（イエローの付箋）を特定する

コマンドを受け取り、イベントを発生させる「主体」を特定してください。

| # | 集約 | 管理するコマンド |
|---|------|----------------|
| 1 | （例）蔵書（Book） | 本を登録する、本の情報を更新する |
| 2 | | |
| 3 | | |

#### Step 4: ポリシー（パープルの付箋）を特定する

イベントに反応して次のアクションを起こすビジネスルールを見つけてください。

| # | トリガーイベント | ポリシー（ルール） | 発行するコマンド |
|---|----------------|-------------------|----------------|
| 1 | （例）本が返却された | 予約者がいれば通知する | 予約者に通知する |
| 2 | | | |

#### Step 5: 境界づけられたコンテキスト（Bounded Context）の候補を挙げる

関連する集約をグルーピングして、コンテキストの境界を提案してください。

```
コンテキスト候補:

┌─ ??? コンテキスト ──────────┐  ┌─ ??? コンテキスト ──────────┐
│                              │  │                              │
│  [???] [???]                 │  │  [???]                       │
│                              │  │                              │
└──────────────────────────────┘  └──────────────────────────────┘
```

### ヒント

<details>
<summary>ヒント: ドメインイベントの例</summary>

以下のような業務の出来事を考えてみましょう：
- 本に関するイベント（登録、更新、廃棄...）
- 貸出に関するイベント（貸出、返却、延滞...）
- 予約に関するイベント（予約、キャンセル、通知...）
- 利用者に関するイベント（登録、退会、ペナルティ...）
- 料金に関するイベント（延滞料金発生、支払い...）
</details>

### 模範解答

<details>
<summary>模範解答を表示（まずは自分で挑戦してください！）</summary>

#### ドメインイベント

| # | ドメインイベント | 説明 |
|---|----------------|------|
| 1 | 本が貸し出された | 利用者が本を借りた |
| 2 | 本が返却された | 利用者が本を返した |
| 3 | 本が予約された | 貸出中の本に予約が入った |
| 4 | 予約がキャンセルされた | 利用者が予約を取り消した |
| 5 | 予約者に通知された | 予約していた本が返却されたことを通知 |
| 6 | 新しい本が登録された | 司書が新刊を登録した |
| 7 | 本の情報が更新された | 司書が本の情報を修正した |
| 8 | 延滞が検出された | 返却期限を過ぎた貸出が見つかった |
| 9 | 延滞料金が発生した | 延滞に対して料金が計算された |
| 10 | 延滞料金が支払われた | 利用者が延滞料金を支払った |
| 11 | 利用者が登録された | 新しい利用者が図書カードを作った |
| 12 | 利用者が退会した | 利用者が図書カードを返却した |
| 13 | 貸出上限に達した | 利用者の貸出数が5冊に達した |

#### コマンドとアクター

| # | コマンド | → イベント | アクター |
|---|---------|-----------|---------|
| 1 | 本を貸し出す | 本が貸し出された | 司書 |
| 2 | 本を返却する | 本が返却された | 司書 |
| 3 | 本を予約する | 本が予約された | 利用者 |
| 4 | 予約をキャンセルする | 予約がキャンセルされた | 利用者 |
| 5 | 本を登録する | 新しい本が登録された | 司書 |
| 6 | 本の情報を更新する | 本の情報が更新された | 司書 |
| 7 | 延滞をチェックする | 延滞が検出された | システム（日次バッチ） |
| 8 | 延滞料金を支払う | 延滞料金が支払われた | 利用者 |
| 9 | 利用者を登録する | 利用者が登録された | 司書 |
| 10 | 退会する | 利用者が退会した | 利用者 |

#### 集約

| # | 集約 | 管理するコマンド |
|---|------|----------------|
| 1 | 蔵書（Book） | 本を登録する、本の情報を更新する |
| 2 | 貸出（Loan） | 本を貸し出す、本を返却する |
| 3 | 予約（Reservation） | 本を予約する、予約をキャンセルする |
| 4 | 利用者（Member） | 利用者を登録する、退会する |
| 5 | 延滞料金（OverdueFee） | 延滞料金を計算する、延滞料金を支払う |

#### ポリシー

| # | トリガーイベント | ポリシー | 発行するコマンド |
|---|----------------|---------|----------------|
| 1 | 本が返却された | 予約者がいれば通知する | 予約通知を送信する |
| 2 | 本が返却された | 延滞していたら料金を計算する | 延滞料金を計算する |
| 3 | 延滞が検出された | 延滞者に通知する | 延滞通知を送信する |
| 4 | 利用者が退会した | 未返却の本があれば返却を求める | 返却を督促する |

#### 境界づけられたコンテキスト

```
┌─ 蔵書管理コンテキスト ────────┐  ┌─ 貸出管理コンテキスト ────────┐
│                                │  │                                │
│  [蔵書(Book)]                  │  │  [貸出(Loan)]                  │
│                                │  │  [予約(Reservation)]           │
│  本の登録、情報管理             │  │  [延滞料金(OverdueFee)]        │
│                                │  │                                │
│                                │  │  貸出・返却・予約・延滞管理     │
└────────────────────────────────┘  └────────────────────────────────┘

┌─ 利用者管理コンテキスト ──────┐
│                                │
│  [利用者(Member)]              │
│                                │
│  利用者の登録・退会管理         │
└────────────────────────────────┘
```
</details>

---

## 演習3: ECサイト注文ドメインのモデル図設計

### 課題概要

ECサイトの「注文」ドメインについて、ドメインモデル図を設計してください。
以下のビジネス要件を満たすモデルを考えてください。

### ビジネス要件

1. **注文（Order）**
   - 注文には1つ以上の注文明細がある
   - 注文には配送先住所が必要
   - 注文ステータス: 下書き → 確定 → 支払い済 → 出荷済 → 配達完了（キャンセル可能）
   - 注文合計が10,000円以上なら送料無料

2. **注文明細（OrderLine）**
   - 商品、数量、単価を持つ
   - 小計を計算できる

3. **割引**
   - プレミアム会員は10%割引
   - 期間限定の割引クーポンが使える（割引率 or 定額）
   - 割引は併用できない（最も割引額が大きいものを適用）

4. **配送先住所（ShippingAddress）**
   - 郵便番号、都道府県、市区町村、番地、建物名
   - 離島への配送は追加送料500円

5. **支払い**
   - クレジットカードまたは銀行振込
   - 支払い方法によって手数料が異なる（銀行振込は300円の手数料）

### 課題

以下のフォーマットでドメインモデル図を設計してください：

```
【テンプレート】

┌──────────────────────────┐
│ クラス名                   │
│ 《種別: エンティティ/値/etc》│
├──────────────────────────┤
│ 属性:                      │
│   - 属性名: 型              │
├──────────────────────────┤
│ 振る舞い:                   │
│   + メソッド名(): 戻り値     │
├──────────────────────────┤
│ ビジネスルール:              │
│   ・ルールの説明             │
└──────────────────────────┘
```

以下の要素を設計してください：

1. **エンティティ**: Order, OrderLine, Payment
2. **値オブジェクト**: Money, Quantity, ShippingAddress, DiscountCoupon
3. **ドメインサービス**: DiscountCalculationService（最適な割引を選択）
4. **関連図**: 各クラスの関連（1対多、1対1など）

### ヒント

<details>
<summary>ヒント1: 割引の設計</summary>

「割引」をどうモデル化するか考えてみましょう：

1. 割引の種類をポリモーフィズムで表現する
   - `MemberDiscount` — 会員割引
   - `CouponDiscount` — クーポン割引
   - 共通インターフェース: `calculate_discount(subtotal: Money) -> Money`

2. 「併用不可、最大割引を適用」というルールはどこに書くべきか？
   - → DiscountCalculationService（複数の割引ポリシーを比較する）
</details>

<details>
<summary>ヒント2: 配送先住所と送料の設計</summary>

```python
@dataclass(frozen=True)
class ShippingAddress:
    postal_code: str
    prefecture: str
    city: str
    street: str
    building: str = ""

    @property
    def is_remote_island(self) -> bool:
        """離島かどうかを判定する"""
        # 離島の郵便番号リストで判定（実際にはもっと複雑）
        remote_prefixes = ["100-01", "100-02"]  # 例: 伊豆諸島、小笠原
        return any(self.postal_code.startswith(p) for p in remote_prefixes)
```

送料の計算は ShippingFeePolicy に委譲する：
- 通常配送: 500円（10,000円以上で無料）
- 離島追加料金: +500円
</details>

<details>
<summary>ヒント3: 支払い方法と手数料</summary>

支払い方法をポリモーフィズムで表現する：

```python
class PaymentMethod:
    def calculate_fee(self) -> Money:
        raise NotImplementedError

class CreditCardPayment(PaymentMethod):
    def calculate_fee(self) -> Money:
        return Money(0)  # 手数料なし

class BankTransferPayment(PaymentMethod):
    def calculate_fee(self) -> Money:
        return Money(300)  # 振込手数料300円
```
</details>

### 模範解答

<details>
<summary>模範解答を表示（まずは自分で挑戦してください！）</summary>

```
┌──────────────────────────────┐
│ Order（注文）                  │
│ 《エンティティ / 集約ルート》   │
├──────────────────────────────┤
│ 属性:                          │
│   - order_id: OrderId          │
│   - customer: Customer         │
│   - lines: List[OrderLine]     │
│   - shipping_address:          │
│       ShippingAddress          │
│   - status: OrderStatus        │
│   - discount_policy:           │
│       DiscountPolicy           │
│   - payment: Payment           │
├──────────────────────────────┤
│ 振る舞い:                      │
│   + add_line(product, qty,     │
│       price): void             │
│   + remove_line(product): void │
│   + confirm(): void            │
│   + cancel(reason): void       │
│   + subtotal(): Money          │
│   + discount_amount(): Money   │
│   + shipping_fee(): Money      │
│   + payment_fee(): Money       │
│   + total_amount(): Money      │
├──────────────────────────────┤
│ ビジネスルール:                 │
│   ・明細は1つ以上必要           │
│   ・10,000円以上で送料無料      │
│   ・確定後は明細の変更不可       │
│   ・出荷後のキャンセル不可       │
└────────────┬─────────────────┘
             │ 1..*
             ▼
┌──────────────────────────────┐
│ OrderLine（注文明細）           │
│ 《値オブジェクト》              │
├──────────────────────────────┤
│ 属性:                          │
│   - product_id: str            │
│   - product_name: str          │
│   - unit_price: Money          │
│   - quantity: Quantity         │
├──────────────────────────────┤
│ 振る舞い:                      │
│   + subtotal(): Money          │
├──────────────────────────────┤
│ ビジネスルール:                 │
│   ・数量は1以上                 │
│   ・単価は0以上                 │
│   ・小計 = 単価 × 数量          │
└──────────────────────────────┘

┌──────────────────────────────┐    ┌──────────────────────────────┐
│ Money（金額）                  │    │ Quantity（数量）               │
│ 《値オブジェクト》              │    │ 《値オブジェクト》              │
├──────────────────────────────┤    ├──────────────────────────────┤
│   - amount: int (>= 0)        │    │   - value: int (>= 1)        │
├──────────────────────────────┤    ├──────────────────────────────┤
│   + add(other): Money          │    │   + add(other): Quantity     │
│   + subtract(other): Money     │    └──────────────────────────────┘
│   + multiply(n): Money         │
│   + apply_rate(rate): Money    │
└──────────────────────────────┘

┌──────────────────────────────┐
│ ShippingAddress（配送先住所）    │
│ 《値オブジェクト》              │
├──────────────────────────────┤
│   - postal_code: str           │
│   - prefecture: str            │
│   - city: str                  │
│   - street: str                │
│   - building: str              │
├──────────────────────────────┤
│   + is_remote_island(): bool   │
│   + full_address(): str        │
├──────────────────────────────┤
│ ビジネスルール:                 │
│   ・郵便番号は必須              │
│   ・離島は追加送料500円          │
└──────────────────────────────┘

┌──────────────────────────────┐
│ DiscountPolicy（割引ポリシー）  │
│ 《ドメインサービス / Strategy》 │
├──────────────────────────────┤
│ 実装クラス:                     │
│   - NoDiscount                 │
│   - MemberDiscount (10%)       │
│   - CouponDiscount (率 or 額)  │
├──────────────────────────────┤
│   + calculate_discount(        │
│       subtotal: Money): Money  │
├──────────────────────────────┤
│ ビジネスルール:                 │
│   ・併用不可                    │
│   ・最大割引額を自動適用         │
└──────────────────────────────┘

┌──────────────────────────────┐
│ DiscountCalculationService    │
│ 《ドメインサービス》            │
├──────────────────────────────┤
│   + select_best_discount(      │
│       policies: List[Policy],  │
│       subtotal: Money          │
│     ): DiscountPolicy          │
├──────────────────────────────┤
│ ビジネスルール:                 │
│   ・複数の割引候補から最大の     │
│     ものを選択                  │
└──────────────────────────────┘

┌──────────────────────────────┐
│ Payment（支払い）              │
│ 《エンティティ》               │
├──────────────────────────────┤
│   - payment_id: str            │
│   - method: PaymentMethod      │
│   - amount: Money              │
│   - status: PaymentStatus      │
├──────────────────────────────┤
│   + process(): void            │
│   + refund(): void             │
│   + fee(): Money               │
├──────────────────────────────┤
│ PaymentMethod 実装:            │
│   - CreditCardPayment (0円)    │
│   - BankTransferPayment (300円)│
└──────────────────────────────┘


【関連図】

  Order ──────1────── ShippingAddress
    │
    ├──── 1..* ────── OrderLine
    │
    ├──────1──────── DiscountPolicy
    │
    └──────1──────── Payment
                        │
                        └── PaymentMethod
```

### コードでの実装例

```python
class Order:
    def total_amount(self) -> Money:
        """
        合計金額 = 小計 - 割引 + 送料 + 決済手数料

        全ての金額計算ルールがこのメソッドに集約されている
        """
        subtotal = self.subtotal()
        discount = self._discount_policy.calculate_discount(subtotal)
        after_discount = subtotal.subtract(discount)
        shipping = self._calculate_shipping_fee(after_discount)
        payment_fee = self._payment.fee()

        return after_discount.add(shipping).add(payment_fee)

    def _calculate_shipping_fee(self, order_amount: Money) -> Money:
        """送料を計算する"""
        base_fee = Money(0) if order_amount.amount >= 10000 else Money(500)
        remote_fee = Money(500) if self._shipping_address.is_remote_island() else Money(0)
        return base_fee.add(remote_fee)
```
</details>

---

## 提出方法

各演習の回答をPythonファイルまたはMarkdownファイルとして作成し、
`day02/answers/` ディレクトリに保存してください。

```
day02/
├── answers/
│   ├── exercise1_bank_account.py   ← 演習1の回答
│   ├── exercise2_event_storming.md ← 演習2の回答
│   └── exercise3_domain_model.md   ← 演習3の回答
```

## 自己チェックリスト

回答を提出する前に、以下を確認してください：

- [ ] 演習1: BankAccount が自分の整合性を守れているか？
- [ ] 演習1: 不正な状態を外部から作る方法がないか？
- [ ] 演習1: ドメインイベントが適切に発行されているか？
- [ ] 演習2: ドメインイベントが10個以上見つかったか？
- [ ] 演習2: 全てのイベントに対応するコマンドとアクターがあるか？
- [ ] 演習2: ポリシー（イベントに反応するルール）を見つけたか？
- [ ] 演習2: 境界づけられたコンテキストの候補を挙げたか？
- [ ] 演習3: エンティティと値オブジェクトを区別できているか？
- [ ] 演習3: ビジネスルールがドメインモデル内にカプセル化されているか？
- [ ] 演習3: 割引・送料・決済手数料の計算ルールが明確か？
