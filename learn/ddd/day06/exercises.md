# Day 6 演習: 集約（Aggregate）とリポジトリ（Repository）

> **目的**: 集約の設計原則、リポジトリパターン、集約境界の判断力を自分の手で考え・実装して身につける
> **所要時間**: 各演習 45〜90分
> **準備するもの**: Python 3.10+、テキストエディタ

---

## 演習1: ECサイトの注文集約を設計・実装する

### 背景

あなたは ECサイト「FreshMart（フレッシュマート）」の注文機能を開発しています。
以下のビジネスルール（不変条件）を満たす「注文集約」を設計・実装してください。

### ビジネスルール（不変条件）

1. **注文明細は1つ以上30個以下** — 空の注文や、31個以上の明細を持つ注文は許可しない
2. **1つの注文の合計金額は500,000円以下** — 高額注文は別の承認フローが必要
3. **同一商品の重複追加は禁止** — 同じ商品を追加しようとした場合は数量を合算する
4. **確定済み（CONFIRMED）の注文に対する商品追加・削除は不可**
5. **キャンセルは出荷前のみ可能** — DRAFT or CONFIRMED のみキャンセルできる
6. **数量は1〜20の範囲**

### 設問1-1: 集約の構成を設計する

以下のテンプレートを埋めてください。

```
┌──────────────────────────────────────────────┐
│ 集約名: 注文集約（Order Aggregate）             │
│                                                │
│ 集約ルート:                                     │
│   クラス名: _______________                     │
│   ID: _______________                          │
│                                                │
│ 内部エンティティ:                                │
│   クラス名: _______________                     │
│   ローカルID: _______________                   │
│                                                │
│ 値オブジェクト:                                  │
│   - _______________                            │
│   - _______________                            │
│   - _______________                            │
│   - _______________                            │
│                                                │
│ 不変条件:                                       │
│   1. _______________                           │
│   2. _______________                           │
│   3. _______________                           │
│   4. _______________                           │
│   5. _______________                           │
│   6. _______________                           │
│                                                │
│ ドメインイベント:                                │
│   - _______________                            │
│   - _______________                            │
│   - _______________                            │
└──────────────────────────────────────────────┘
```

### 設問1-2: 注文集約を実装する

以下のスターターコードを完成させてください。`# TODO` のコメントがある箇所を実装します。

```python
"""演習1: 注文集約の実装"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4


# --- 値オブジェクト ---

@dataclass(frozen=True)
class OrderId:
    value: str

    @classmethod
    def generate(cls) -> OrderId:
        return cls(value=f"ORD-{uuid4().hex[:12].upper()}")


@dataclass(frozen=True)
class Money:
    amount: int  # 円単位
    currency: str = "JPY"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError(f"金額は0以上: {self.amount}")

    def add(self, other: Money) -> Money:
        return Money(amount=self.amount + other.amount)

    def multiply(self, factor: int) -> Money:
        return Money(amount=self.amount * factor)

    def is_greater_than(self, other: Money) -> bool:
        return self.amount > other.amount

    def __str__(self) -> str:
        return f"¥{self.amount:,}"


@dataclass(frozen=True)
class Quantity:
    value: int

    def __post_init__(self) -> None:
        # TODO: 1〜20の範囲バリデーションを実装
        pass


class OrderStatus(Enum):
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# --- 内部エンティティ ---

class OrderLine:
    def __init__(
        self,
        line_id: str,
        product_id: str,
        product_name: str,
        unit_price: Money,
        quantity: Quantity,
    ) -> None:
        self._line_id = line_id
        self._product_id = product_id
        self._product_name = product_name
        self._unit_price = unit_price
        self._quantity = quantity

    @property
    def product_id(self) -> str:
        return self._product_id

    @property
    def quantity(self) -> Quantity:
        return self._quantity

    @property
    def line_total(self) -> Money:
        return self._unit_price.multiply(self._quantity.value)

    def _change_quantity(self, new_quantity: Quantity) -> None:
        self._quantity = new_quantity


# --- 集約ルート ---

class Order:
    """
    注文集約ルート

    TODO: 以下のメソッドを実装してください

    【不変条件】
    1. 注文明細は1つ以上30個以下
    2. 合計金額は500,000円以下
    3. 同一商品の重複追加は禁止（数量を合算する）
    4. 確定済みの注文は変更不可
    5. キャンセルは出荷前のみ
    6. 数量は1〜20
    """

    MAX_LINE_COUNT = 30
    MAX_ORDER_AMOUNT = Money(amount=500_000)

    def __init__(self, order_id: OrderId, customer_id: str) -> None:
        self._id = order_id
        self._customer_id = customer_id
        self._lines: list[OrderLine] = []
        self._status = OrderStatus.DRAFT
        self._events: list[dict] = []

    @property
    def id(self) -> OrderId:
        return self._id

    @property
    def status(self) -> OrderStatus:
        return self._status

    @property
    def total_amount(self) -> Money:
        total = Money(amount=0)
        for line in self._lines:
            total = total.add(line.line_total)
        return total

    @property
    def line_count(self) -> int:
        return len(self._lines)

    def add_item(
        self,
        product_id: str,
        product_name: str,
        unit_price: Money,
        quantity: Quantity,
    ) -> None:
        """
        商品を追加する

        TODO: 以下を実装してください
        1. DRAFT状態かチェック
        2. 同一商品が既にある場合は数量を合算する
        3. 明細数の上限（30個）チェック
        4. 追加後の合計金額の上限チェック
        """
        pass

    def remove_item(self, product_id: str) -> None:
        """
        商品を削除する

        TODO: 以下を実装してください
        1. DRAFT状態かチェック
        2. 該当する商品を見つけて削除
        3. 見つからない場合はエラー
        """
        pass

    def confirm(self) -> None:
        """
        注文を確定する

        TODO: 以下を実装してください
        1. DRAFT状態かチェック
        2. 明細が1つ以上あるかチェック
        3. ステータスを CONFIRMED に変更
        4. ドメインイベントを記録
        """
        pass

    def cancel(self, reason: str = "") -> None:
        """
        注文をキャンセルする

        TODO: 以下を実装してください
        1. DRAFT or CONFIRMED 状態かチェック
        2. ステータスを CANCELLED に変更
        3. ドメインイベントを記録
        """
        pass


# --- テストケース ---

def test_order_aggregate() -> None:
    """注文集約のテスト"""

    print("テスト開始...")

    # テスト1: 正常な注文作成と確定
    order = Order(OrderId.generate(), "CUST-001")
    order.add_item("P-001", "コーヒー豆", Money(1980), Quantity(2))
    order.add_item("P-002", "紅茶", Money(1500), Quantity(1))
    assert order.line_count == 2
    assert order.total_amount.amount == 1980 * 2 + 1500 * 1
    order.confirm()
    assert order.status == OrderStatus.CONFIRMED
    print("  ✅ テスト1: 正常な注文作成と確定")

    # テスト2: 同一商品の追加 → 数量合算
    order2 = Order(OrderId.generate(), "CUST-001")
    order2.add_item("P-001", "コーヒー豆", Money(1980), Quantity(2))
    order2.add_item("P-001", "コーヒー豆", Money(1980), Quantity(3))
    assert order2.line_count == 1  # 明細は1つのまま
    # 数量は 2 + 3 = 5
    assert order2.total_amount.amount == 1980 * 5
    print("  ✅ テスト2: 同一商品の数量合算")

    # テスト3: 確定済みの注文に追加 → エラー
    try:
        order.add_item("P-003", "抹茶", Money(2500), Quantity(1))
        assert False, "エラーが発生すべき"
    except Exception:
        print("  ✅ テスト3: 確定済み注文への追加はエラー")

    # テスト4: 空の注文の確定 → エラー
    order3 = Order(OrderId.generate(), "CUST-002")
    try:
        order3.confirm()
        assert False, "エラーが発生すべき"
    except Exception:
        print("  ✅ テスト4: 空の注文の確定はエラー")

    # テスト5: 金額上限超過 → エラー
    order4 = Order(OrderId.generate(), "CUST-003")
    try:
        order4.add_item("P-999", "高額商品", Money(300_000), Quantity(2))
        # 300,000 * 2 = 600,000 > 500,000
        assert False, "エラーが発生すべき"
    except Exception:
        print("  ✅ テスト5: 金額上限超過はエラー")

    # テスト6: 出荷済みのキャンセル → エラー
    order5 = Order(OrderId.generate(), "CUST-004")
    order5.add_item("P-001", "コーヒー豆", Money(1980), Quantity(1))
    order5.confirm()
    order5._status = OrderStatus.SHIPPED  # テスト用に直接変更
    try:
        order5.cancel("テスト")
        assert False, "エラーが発生すべき"
    except Exception:
        print("  ✅ テスト6: 出荷済みのキャンセルはエラー")

    # テスト7: 商品の削除
    order6 = Order(OrderId.generate(), "CUST-005")
    order6.add_item("P-001", "コーヒー豆", Money(1980), Quantity(2))
    order6.add_item("P-002", "紅茶", Money(1500), Quantity(1))
    order6.remove_item("P-001")
    assert order6.line_count == 1
    assert order6.total_amount.amount == 1500
    print("  ✅ テスト7: 商品の削除")

    print("\n全テスト合格 🎉")


if __name__ == "__main__":
    test_order_aggregate()
```

### 設問1-3: 模範解答

<details>
<summary>▶ クリックして模範解答を表示</summary>

```python
@dataclass(frozen=True)
class Quantity:
    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise ValueError(f"数量は1以上: {self.value}")
        if self.value > 20:
            raise ValueError(f"数量は20以下: {self.value}")


class Order:
    MAX_LINE_COUNT = 30
    MAX_ORDER_AMOUNT = Money(amount=500_000)

    def __init__(self, order_id: OrderId, customer_id: str) -> None:
        self._id = order_id
        self._customer_id = customer_id
        self._lines: list[OrderLine] = []
        self._status = OrderStatus.DRAFT
        self._events: list[dict] = []

    @property
    def id(self) -> OrderId:
        return self._id

    @property
    def status(self) -> OrderStatus:
        return self._status

    @property
    def total_amount(self) -> Money:
        total = Money(amount=0)
        for line in self._lines:
            total = total.add(line.line_total)
        return total

    @property
    def line_count(self) -> int:
        return len(self._lines)

    def add_item(
        self,
        product_id: str,
        product_name: str,
        unit_price: Money,
        quantity: Quantity,
    ) -> None:
        # 1. DRAFT状態かチェック
        if self._status != OrderStatus.DRAFT:
            raise ValueError(
                f"DRAFT状態でのみ商品を追加できます（現在: {self._status.value}）"
            )

        # 2. 同一商品チェック → 既にあれば数量合算
        existing_line = self._find_line_by_product(product_id)
        if existing_line is not None:
            new_qty = Quantity(existing_line.quantity.value + quantity.value)
            existing_line._change_quantity(new_qty)
        else:
            # 3. 明細数の上限チェック
            if len(self._lines) >= self.MAX_LINE_COUNT:
                raise ValueError(
                    f"注文明細は{self.MAX_LINE_COUNT}個以下です"
                )

            line = OrderLine(
                line_id=f"LINE-{uuid4().hex[:8]}",
                product_id=product_id,
                product_name=product_name,
                unit_price=unit_price,
                quantity=quantity,
            )
            self._lines.append(line)

        # 4. 合計金額の上限チェック
        if self.total_amount.is_greater_than(self.MAX_ORDER_AMOUNT):
            # 追加を取り消す
            if existing_line is not None:
                # 合算した数量を元に戻す
                original_qty = Quantity(
                    existing_line.quantity.value - quantity.value
                )
                existing_line._change_quantity(original_qty)
            else:
                self._lines.pop()
            raise ValueError(
                f"注文合計が上限を超えます（上限: {self.MAX_ORDER_AMOUNT}）"
            )

    def remove_item(self, product_id: str) -> None:
        # 1. DRAFT状態かチェック
        if self._status != OrderStatus.DRAFT:
            raise ValueError("DRAFT状態でのみ商品を削除できます")

        # 2. 該当する商品を見つけて削除
        line = self._find_line_by_product(product_id)
        if line is None:
            raise ValueError(f"商品が見つかりません: {product_id}")
        self._lines.remove(line)

    def confirm(self) -> None:
        # 1. DRAFT状態かチェック
        if self._status != OrderStatus.DRAFT:
            raise ValueError("DRAFT状態でのみ確定できます")

        # 2. 明細が1つ以上あるかチェック
        if not self._lines:
            raise ValueError("注文明細が空のため確定できません")

        # 3. ステータス変更
        self._status = OrderStatus.CONFIRMED

        # 4. ドメインイベント記録
        self._events.append({
            "type": "OrderConfirmed",
            "order_id": str(self._id.value),
            "total_amount": self.total_amount.amount,
            "occurred_on": datetime.now().isoformat(),
        })

    def cancel(self, reason: str = "") -> None:
        # 1. DRAFT or CONFIRMED 状態かチェック
        if self._status not in (OrderStatus.DRAFT, OrderStatus.CONFIRMED):
            raise ValueError(
                f"キャンセルはDRAFT/CONFIRMED状態のみ可能です"
                f"（現在: {self._status.value}）"
            )

        # 2. ステータス変更
        self._status = OrderStatus.CANCELLED

        # 3. ドメインイベント記録
        self._events.append({
            "type": "OrderCancelled",
            "order_id": str(self._id.value),
            "reason": reason,
            "occurred_on": datetime.now().isoformat(),
        })

    def _find_line_by_product(self, product_id: str):
        for line in self._lines:
            if line.product_id == product_id:
                return line
        return None
```

</details>

---

## 演習2: OrderRepository インターフェースの定義と InMemory 実装

### 背景

演習1で作った注文集約を永続化するためのリポジトリを設計・実装してください。

### 設問2-1: リポジトリインターフェースを定義する

以下の要件を満たす `OrderRepository` 抽象クラスを定義してください。

**必須メソッド:**

| メソッド | 説明 | 戻り値 |
|---------|------|--------|
| `save(order)` | 注文を保存（新規追加・更新を統一） | `None` |
| `find_by_id(order_id)` | 注文IDで検索 | `Optional[Order]` |
| `find_by_customer_id(customer_id)` | 顧客IDで検索 | `list[Order]` |
| `find_by_status(status)` | ステータスで検索 | `list[Order]` |
| `remove(order_id)` | 注文を削除 | `None` |
| `count()` | 総件数を返す | `int` |

### スターターコード

```python
"""演習2: リポジトリパターンの実装"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from typing import Optional

# 演習1の Order, OrderId, OrderStatus を使用する前提


class OrderRepository(ABC):
    """
    注文リポジトリのインターフェース

    TODO: 上記の表に基づいて抽象メソッドを定義してください
    """

    # TODO: 抽象メソッドを定義する
    pass


class InMemoryOrderRepository(OrderRepository):
    """
    インメモリのリポジトリ実装

    TODO: 各メソッドを実装してください

    ヒント:
    - 内部ストアには dict[str, Order] を使用する
    - deep copy を使って保存し、参照による意図しない変更を防ぐ
    """

    def __init__(self) -> None:
        self._store: dict[str, Order] = {}

    # TODO: 各メソッドを実装する


# --- テストケース ---

def test_repository() -> None:
    """リポジトリのテスト"""

    print("リポジトリテスト開始...")

    repo = InMemoryOrderRepository()

    # テスト1: 保存と取得
    order = Order(OrderId.generate(), "CUST-001")
    order.add_item("P-001", "コーヒー豆", Money(1980), Quantity(2))
    repo.save(order)
    found = repo.find_by_id(order.id)
    assert found is not None
    assert found.id == order.id
    assert found.line_count == 1
    print("  ✅ テスト1: 保存と取得")

    # テスト2: 存在しないIDの検索 → None
    not_found = repo.find_by_id(OrderId("ORD-NONEXISTENT"))
    assert not_found is None
    print("  ✅ テスト2: 存在しないIDの検索")

    # テスト3: 更新（再save）
    found.add_item("P-002", "紅茶", Money(1500), Quantity(1))
    repo.save(found)
    updated = repo.find_by_id(order.id)
    assert updated is not None
    assert updated.line_count == 2
    print("  ✅ テスト3: 更新（再save）")

    # テスト4: 顧客IDで検索
    order2 = Order(OrderId.generate(), "CUST-001")
    order2.add_item("P-003", "抹茶", Money(2500), Quantity(1))
    repo.save(order2)

    order3 = Order(OrderId.generate(), "CUST-002")
    order3.add_item("P-001", "コーヒー豆", Money(1980), Quantity(1))
    repo.save(order3)

    cust1_orders = repo.find_by_customer_id("CUST-001")
    assert len(cust1_orders) == 2
    print("  ✅ テスト4: 顧客IDで検索")

    # テスト5: ステータスで検索
    order2.confirm()
    repo.save(order2)
    confirmed = repo.find_by_status(OrderStatus.CONFIRMED)
    assert len(confirmed) == 1
    print("  ✅ テスト5: ステータスで検索")

    # テスト6: 削除
    repo.remove(order.id)
    assert repo.count() == 2
    assert repo.find_by_id(order.id) is None
    print("  ✅ テスト6: 削除")

    # テスト7: deep copy の確認（保存後の変更がストアに影響しない）
    order4 = Order(OrderId.generate(), "CUST-003")
    order4.add_item("P-001", "コーヒー豆", Money(1980), Quantity(1))
    repo.save(order4)
    # 保存後にオリジナルを変更
    order4.add_item("P-002", "紅茶", Money(1500), Quantity(1))
    # ストア内のデータは変更されていないはず
    stored = repo.find_by_id(order4.id)
    assert stored is not None
    assert stored.line_count == 1  # 変更前の状態のまま
    print("  ✅ テスト7: deep copy による保護")

    print("\n全テスト合格 🎉")


if __name__ == "__main__":
    test_repository()
```

### 設問2-2: 模範解答

<details>
<summary>▶ クリックして模範解答を表示</summary>

```python
class OrderRepository(ABC):
    @abstractmethod
    def save(self, order: Order) -> None:
        ...

    @abstractmethod
    def find_by_id(self, order_id: OrderId) -> Optional[Order]:
        ...

    @abstractmethod
    def find_by_customer_id(self, customer_id: str) -> list[Order]:
        ...

    @abstractmethod
    def find_by_status(self, status: OrderStatus) -> list[Order]:
        ...

    @abstractmethod
    def remove(self, order_id: OrderId) -> None:
        ...

    @abstractmethod
    def count(self) -> int:
        ...


class InMemoryOrderRepository(OrderRepository):
    def __init__(self) -> None:
        self._store: dict[str, Order] = {}

    def save(self, order: Order) -> None:
        self._store[order.id.value] = copy.deepcopy(order)

    def find_by_id(self, order_id: OrderId) -> Optional[Order]:
        stored = self._store.get(order_id.value)
        if stored is None:
            return None
        return copy.deepcopy(stored)

    def find_by_customer_id(self, customer_id: str) -> list[Order]:
        return [
            copy.deepcopy(o)
            for o in self._store.values()
            if o._customer_id == customer_id
        ]

    def find_by_status(self, status: OrderStatus) -> list[Order]:
        return [
            copy.deepcopy(o)
            for o in self._store.values()
            if o.status == status
        ]

    def remove(self, order_id: OrderId) -> None:
        key = order_id.value
        if key not in self._store:
            raise ValueError(f"注文が見つかりません: {order_id.value}")
        del self._store[key]

    def count(self) -> int:
        return len(self._store)
```

</details>

---

## 演習3: 集約境界の判断問題

### 背景

DDDで最も難しい判断の1つが「何を1つの集約にまとめ、何を別の集約にするか」です。
以下のシナリオを読んで、適切な集約境界を考えてください。

### シナリオA: ブログシステム

以下のデータ構造を持つブログシステムがあります。

```
- ブログ記事（BlogPost）
  - タイトル
  - 本文
  - 著者ID
  - 公開日
  - ステータス（下書き/公開/非公開）
  - カテゴリ

- コメント（Comment）
  - 本文
  - 投稿者ID
  - 投稿日時

- タグ（Tag）
  - タグ名
```

**ビジネスルール:**
- 記事はドラフト状態でのみ編集可能
- 公開記事にはコメントを付けられる
- コメントは1記事あたり最大1000件
- 1つのコメントは1000文字以下
- タグは記事間で共有される（同じタグを複数の記事に付けられる）

**設問A-1:** BlogPost, Comment, Tag をどのように集約に分けますか？

以下の選択肢から選び、理由を説明してください。

```
選択肢1: すべて1つの集約
  ┌──────────────────────────┐
  │  BlogPost（集約ルート）    │
  │  ├── Comment[]            │
  │  └── Tag[]                │
  └──────────────────────────┘

選択肢2: BlogPost + Comment を1つの集約、Tag は別
  ┌──────────────────────────┐   ┌───────────┐
  │  BlogPost（集約ルート）    │   │ Tag       │
  │  └── Comment[]            │   └───────────┘
  └──────────────────────────┘

選択肢3: それぞれ別の集約
  ┌───────────┐ ┌───────────┐ ┌───────────┐
  │ BlogPost  │ │ Comment   │ │ Tag       │
  │(post_id)  │ │(post_id)  │ │(tag_name) │
  └───────────┘ └───────────┘ └───────────┘
```

**設問A-2:** もし「コメントの合計が1000件を超えたら記事を自動的に非公開にする」というルールが追加されたら、集約の設計はどう変わりますか？

---

### シナリオB: ホテル予約システム

```
- 部屋（Room）
  - 部屋番号
  - 部屋タイプ（シングル/ダブル/スイート）
  - 1泊料金
  - アメニティ一覧

- 予約（Reservation）
  - 宿泊者名
  - チェックイン日
  - チェックアウト日
  - 部屋番号
  - 合計金額
  - ステータス（仮予約/確定/キャンセル）

- レビュー（Review）
  - 評価（1-5）
  - コメント
  - 宿泊者名
  - 投稿日
```

**ビジネスルール:**
- 同じ部屋の同じ日に複数の予約は不可（ダブルブッキング防止）
- 予約はチェックイン3日前までキャンセル可能
- レビューはチェックアウト後のみ投稿可能
- 合計金額 = 1泊料金 × 泊数

**設問B-1:** Room, Reservation, Review をどのように集約に分けますか？理由も説明してください。

**設問B-2:** 「ダブルブッキング防止」の不変条件はどの集約で保証しますか？

ヒント: この問題には複数の正解があります。以下の観点から考えてみましょう。

```
考慮すべき観点:
  1. 不変条件の範囲 — 「同じ部屋の同じ日に複数予約不可」は
     Room と Reservation の両方に関わる
  2. 並行アクセス — 人気の部屋は同時に複数の予約リクエストが来る
  3. パフォーマンス — Room に全予約を持たせると巨大になる
```

---

### シナリオC: 勤怠管理システム

```
- 社員（Employee）
  - 社員番号
  - 氏名
  - 部署
  - 雇用形態（正社員/パート）

- 勤怠記録（AttendanceRecord）
  - 出勤日
  - 出勤時刻
  - 退勤時刻
  - 休憩時間
  - 勤務時間（計算値）
  - ステータス（出勤中/退勤済/承認済）

- 月次集計（MonthlyAttendanceSummary）
  - 年月
  - 総労働時間
  - 残業時間
  - 出勤日数
  - 有給使用日数
```

**ビジネスルール:**
- 1日の勤務時間は24時間を超えない
- 月の残業時間は45時間以下（超えた場合は管理者にアラート）
- 勤怠記録は本人または管理者のみ変更可能
- 月次集計は勤怠記録から自動計算される

**設問C-1:** Employee, AttendanceRecord, MonthlyAttendanceSummary をどのように集約に分けますか？

**設問C-2:** 「月の残業時間は45時間以下」という不変条件は、即時整合性で保証すべきですか？それとも結果整合性で十分ですか？理由を説明してください。

---

### 模範解答

<details>
<summary>▶ クリックしてシナリオAの模範解答を表示</summary>

**設問A-1: 選択肢3（それぞれ別の集約）が最適**

```
理由:

1. コメントが最大1000件 → BlogPost に含めると巨大な集約になる
   → 記事の編集のたびに1000件のコメントもロードされる → パフォーマンス問題

2. Tag は記事間で共有される → 特定の BlogPost に属さない
   → 独立した集約が自然

3. ライフサイクルが異なる
   - BlogPost: 著者が管理
   - Comment: 読者が追加（記事とは独立した操作）
   - Tag: 記事より長いライフサイクル（記事が消えてもタグは残りうる）

4. 並行アクセス
   - 記事の編集中にコメントが追加されることがある
   - 同じ集約にすると、編集とコメント追加が競合する

設計:
  BlogPost集約: {post_id, title, body, author_id, status, category_ids}
  Comment集約:  {comment_id, post_id, body, commenter_id, posted_at}
  Tag集約:      {tag_id, name}
  ※ BlogPost と Tag は多対多の関連テーブルで管理
```

**設問A-2: 「1000件超えたら非公開にする」ルール**

```
このルールは BlogPost と Comment の両方に関わるが、
即時整合性は不要（数件の誤差は許容される）。

→ 結果整合性で対応:
  1. Comment が追加されたら CommentAdded イベントを発行
  2. BlogPost がイベントを受けて件数をチェック
  3. 1000件超なら非公開にする

これなら集約を分離したまま、ルールを実現できる。
```

</details>

<details>
<summary>▶ クリックしてシナリオBの模範解答を表示</summary>

**設問B-1: 3つの独立した集約**

```
Room集約:        {room_number, room_type, rate, amenities}
Reservation集約: {reservation_id, room_number, guest_name,
                  check_in, check_out, amount, status}
Review集約:      {review_id, reservation_id, rating, comment}

理由:
1. Room, Reservation, Review のライフサイクルが異なる
2. Room に全予約を持たせると巨大になる（過去の予約も含めて）
3. Review は予約後にのみ作成される独立したライフサイクル
```

**設問B-2: ダブルブッキング防止**

```
方法1: ドメインサービスで保証
  class ReservationService:
      def make_reservation(self, room_number, check_in, check_out):
          # リポジトリで既存予約を検索
          existing = reservation_repo.find_overlapping(
              room_number, check_in, check_out
          )
          if existing:
              raise DoubleBookingError(...)
          # 新しい予約を作成・保存

  → 楽観的ロック（バージョン番号）と組み合わせて
    並行アクセスの問題を防ぐ

方法2: Room 集約に「予約可能日」を持たせる
  → Room集約が予約可能性を管理する
  → ただし Room が大きくなりすぎるリスク

推奨: 方法1（ドメインサービス + 楽観的ロック）
```

</details>

<details>
<summary>▶ クリックしてシナリオCの模範解答を表示</summary>

**設問C-1: 3つの独立した集約**

```
Employee集約:                {employee_id, name, department, employment_type}
AttendanceRecord集約:        {record_id, employee_id, date, clock_in,
                              clock_out, break_time, status}
MonthlyAttendanceSummary集約: {summary_id, employee_id, year_month,
                               total_hours, overtime_hours, ...}

理由:
1. Employee は人事コンテキスト、勤怠は勤怠コンテキスト
   → Bounded Context が異なる可能性
2. 勤怠記録は日次で作成・更新、月次集計は月末に作成
   → ライフサイクルが異なる
3. AttendanceRecord を Employee に含めると
   1年分で365レコード → 巨大すぎる
```

**設問C-2: 「月45時間」は結果整合性で十分**

```
理由:
1. リアルタイムに厳密に45時間を超えないようにする必要はない
   - 退勤を記録した瞬間に「44時間59分です、あと1分です」
     と制御する必要はない
   - 後から集計して超過を検知し、アラートを出せば十分

2. 即時整合性にすると
   - 毎回の退勤記録時に月の全勤怠をロードする必要がある
   - パフォーマンスが悪化する
   - AttendanceRecord と MonthlyAttendanceSummary を
     同一集約にする必要が出る → 巨大化

3. 結果整合性の実装例:
   - AttendanceRecord を保存 → AttendanceRecorded イベント発行
   - MonthlyAttendanceSummary がイベントを受けて再計算
   - 45時間超過なら OvertimeExceeded イベントを発行
   - 管理者通知サービスがアラートメールを送信
```

</details>

---

## 振り返りチェックリスト

本日の学習が完了したら、以下を確認してください:

- [ ] 集約とは何か、自分の言葉で説明できる
- [ ] 集約ルートの責務（門番の役割）を理解した
- [ ] 集約の4つの設計原則を説明できる
- [ ] 「大きすぎる集約」のアンチパターンを理解した
- [ ] 集約境界を見つけるヒューリスティクスを3つ以上知っている
- [ ] リポジトリのインターフェースを定義し、InMemory実装ができる
- [ ] リポジトリと DAO の違いを説明できる
- [ ] ファクトリの新規作成と再構築の違いを理解した
- [ ] 即時整合性と結果整合性の使い分けができる

---

> **次のステップ**: 演習が完了したら、Day 7「ドメインイベント、仕様パターン、アーキテクチャ」に進みましょう。
