"""
==========================================================
Day 6 サンプルコード: 注文集約（Order Aggregate）の完全な実装
==========================================================

このファイルでは、ECサイトの「注文」を集約として実装する。

構成:
  - Order（集約ルート）
  - OrderLine（内部エンティティ）
  - OrderId, OrderLineId, Money, Quantity, OrderStatus（値オブジェクト）
  - DomainEvent（ドメインイベント基底クラス）

学習ポイント:
  1. 集約ルート経由でのみ内部を操作する
  2. 不変条件（ビジネスルール）を集約内で保証する
  3. ドメインイベントの記録
  4. 値オブジェクトによる型安全性
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4


# ==========================================================
# ドメインイベント（Domain Event）
# ==========================================================

@dataclass(frozen=True)
class DomainEvent:
    """ドメインイベントの基底クラス（不変）"""
    occurred_on: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class OrderCreated(DomainEvent):
    """注文が作成されたイベント"""
    order_id: str = ""
    customer_id: str = ""


@dataclass(frozen=True)
class OrderItemAdded(DomainEvent):
    """注文に商品が追加されたイベント"""
    order_id: str = ""
    product_id: str = ""
    quantity: int = 0


@dataclass(frozen=True)
class OrderConfirmed(DomainEvent):
    """注文が確定されたイベント"""
    order_id: str = ""
    total_amount: int = 0  # 金額（円単位の整数）


@dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    """注文がキャンセルされたイベント"""
    order_id: str = ""
    reason: str = ""


# ==========================================================
# 値オブジェクト（Value Objects）
# ==========================================================

@dataclass(frozen=True)
class OrderId:
    """注文ID（値オブジェクト）"""
    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("注文IDは空にできません")

    @classmethod
    def generate(cls) -> OrderId:
        """新しい注文IDを生成する"""
        return cls(value=f"ORD-{uuid4().hex[:12].upper()}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class OrderLineId:
    """注文明細ID（値オブジェクト）- 集約内でローカルに一意"""
    value: str

    @classmethod
    def generate(cls) -> OrderLineId:
        return cls(value=f"LINE-{uuid4().hex[:8].upper()}")

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class Money:
    """
    金額（値オブジェクト）

    不変であり、演算は新しい Money を返す。
    円単位の整数で管理し、浮動小数点の誤差を回避する。
    """
    amount: int  # 円単位の整数
    currency: str = "JPY"

    def __post_init__(self) -> None:
        if self.amount < 0:
            raise ValueError(f"金額は0以上である必要があります: {self.amount}")
        if not self.currency:
            raise ValueError("通貨コードは必須です")

    def add(self, other: Money) -> Money:
        """加算（新しい Money を返す）"""
        self._assert_same_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def multiply(self, factor: int) -> Money:
        """整数倍（新しい Money を返す）"""
        if factor < 0:
            raise ValueError(f"乗数は0以上である必要があります: {factor}")
        return Money(amount=self.amount * factor, currency=self.currency)

    def is_greater_than(self, other: Money) -> bool:
        """比較"""
        self._assert_same_currency(other)
        return self.amount > other.amount

    def _assert_same_currency(self, other: Money) -> None:
        if self.currency != other.currency:
            raise ValueError(
                f"通貨が異なります: {self.currency} vs {other.currency}"
            )

    def __str__(self) -> str:
        return f"¥{self.amount:,}"


@dataclass(frozen=True)
class Quantity:
    """数量（値オブジェクト）"""
    value: int

    def __post_init__(self) -> None:
        if self.value < 1:
            raise ValueError(f"数量は1以上である必要があります: {self.value}")
        if self.value > 99:
            raise ValueError(f"数量は99以下である必要があります: {self.value}")

    def __str__(self) -> str:
        return str(self.value)


class OrderStatus(Enum):
    """注文ステータス（値オブジェクト）"""
    DRAFT = "draft"           # 下書き（商品追加中）
    CONFIRMED = "confirmed"   # 確定済み
    SHIPPED = "shipped"       # 出荷済み
    DELIVERED = "delivered"   # 配達完了
    CANCELLED = "cancelled"   # キャンセル


# ==========================================================
# 内部エンティティ（Internal Entity）: OrderLine
# ==========================================================

class OrderLine:
    """
    注文明細行（内部エンティティ）

    ★ 集約の外部からは直接操作できない。
    ★ Order（集約ルート）のメソッドを通じてのみ変更される。
    """

    def __init__(
        self,
        line_id: OrderLineId,
        product_id: str,
        product_name: str,
        unit_price: Money,
        quantity: Quantity,
    ) -> None:
        self._line_id = line_id
        self._product_id = product_id
        self._product_name = product_name  # 注文時点のスナップショット
        self._unit_price = unit_price      # 注文時点のスナップショット
        self._quantity = quantity

    @property
    def line_id(self) -> OrderLineId:
        return self._line_id

    @property
    def product_id(self) -> str:
        return self._product_id

    @property
    def product_name(self) -> str:
        return self._product_name

    @property
    def unit_price(self) -> Money:
        return self._unit_price

    @property
    def quantity(self) -> Quantity:
        return self._quantity

    @property
    def line_total(self) -> Money:
        """この明細行の小計"""
        return self._unit_price.multiply(self._quantity.value)

    def _change_quantity(self, new_quantity: Quantity) -> None:
        """
        数量を変更する（内部メソッド）

        ★ このメソッドは Order（集約ルート）からのみ呼ばれる。
        ★ 外部から呼ばれることを想定していない。
        """
        self._quantity = new_quantity

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, OrderLine):
            return False
        return self._line_id == other._line_id

    def __hash__(self) -> int:
        return hash(self._line_id)

    def __repr__(self) -> str:
        return (
            f"OrderLine(id={self._line_id}, "
            f"product={self._product_name}, "
            f"qty={self._quantity}, "
            f"total={self.line_total})"
        )


# ==========================================================
# ドメイン例外
# ==========================================================

class OrderDomainError(Exception):
    """注文ドメインの基底例外"""
    pass


class EmptyOrderError(OrderDomainError):
    """注文明細が空の状態で確定しようとした"""
    pass


class OrderAmountExceededError(OrderDomainError):
    """注文金額の上限を超えた"""
    pass


class InvalidOrderStateError(OrderDomainError):
    """不正な状態遷移"""
    pass


class OrderLineNotFoundError(OrderDomainError):
    """指定された注文明細が見つからない"""
    pass


# ==========================================================
# 集約ルート（Aggregate Root）: Order
# ==========================================================

class Order:
    """
    注文集約ルート（Aggregate Root）

    ★ 外部からのアクセスはすべてこのクラスのメソッド経由。
    ★ 内部の OrderLine を直接操作させない。
    ★ すべての操作で不変条件をチェックする。

    【不変条件（Invariants）】
    1. 確定時、注文明細は1つ以上必要
    2. 注文合計金額は上限（1,000,000円）以下
    3. 状態遷移は定められた順序でのみ可能
       DRAFT → CONFIRMED → SHIPPED → DELIVERED
       DRAFT → CANCELLED
       CONFIRMED → CANCELLED
    """

    # 注文金額の上限
    MAX_ORDER_AMOUNT = Money(amount=1_000_000)

    def __init__(self, order_id: OrderId, customer_id: str) -> None:
        self._id = order_id
        self._customer_id = customer_id
        self._lines: list[OrderLine] = []
        self._status = OrderStatus.DRAFT
        self._created_at = datetime.now()
        self._confirmed_at: Optional[datetime] = None
        # ドメインイベントを蓄積するリスト
        self._domain_events: list[DomainEvent] = []

    # --- プロパティ（読み取り専用） ---

    @property
    def id(self) -> OrderId:
        return self._id

    @property
    def customer_id(self) -> str:
        return self._customer_id

    @property
    def status(self) -> OrderStatus:
        return self._status

    @property
    def created_at(self) -> datetime:
        return self._created_at

    @property
    def confirmed_at(self) -> Optional[datetime]:
        return self._confirmed_at

    @property
    def line_count(self) -> int:
        """注文明細の数"""
        return len(self._lines)

    @property
    def lines(self) -> tuple[OrderLine, ...]:
        """
        注文明細のタプル（読み取り専用のコピー）

        ★ list ではなく tuple を返すことで、外部からの変更を防ぐ
        """
        return tuple(self._lines)

    @property
    def total_amount(self) -> Money:
        """注文合計金額"""
        total = Money(amount=0)
        for line in self._lines:
            total = total.add(line.line_total)
        return total

    @property
    def domain_events(self) -> list[DomainEvent]:
        """記録されたドメインイベントのリスト"""
        return list(self._domain_events)

    # --- コマンドメソッド（状態を変更する操作） ---

    def add_item(
        self,
        product_id: str,
        product_name: str,
        unit_price: Money,
        quantity: Quantity,
    ) -> OrderLineId:
        """
        注文に商品を追加する

        ★ 集約ルート経由でのみ OrderLine を追加する
        ★ 追加後に不変条件（金額上限）をチェックする
        """
        self._assert_modifiable()

        line_id = OrderLineId.generate()
        new_line = OrderLine(
            line_id=line_id,
            product_id=product_id,
            product_name=product_name,
            unit_price=unit_price,
            quantity=quantity,
        )
        self._lines.append(new_line)

        # 不変条件チェック: 合計金額が上限を超えていないか
        self._assert_within_amount_limit()

        # ドメインイベントを記録
        self._record_event(OrderItemAdded(
            order_id=str(self._id),
            product_id=product_id,
            quantity=quantity.value,
        ))

        return line_id

    def change_item_quantity(
        self, line_id: OrderLineId, new_quantity: Quantity
    ) -> None:
        """
        注文明細の数量を変更する

        ★ 外部は OrderLine を直接操作しない
        ★ 集約ルートが OrderLine を見つけて変更する
        """
        self._assert_modifiable()

        line = self._find_line(line_id)
        line._change_quantity(new_quantity)

        # 不変条件チェック: 合計金額が上限を超えていないか
        self._assert_within_amount_limit()

    def remove_item(self, line_id: OrderLineId) -> None:
        """注文から商品を削除する"""
        self._assert_modifiable()

        line = self._find_line(line_id)
        self._lines.remove(line)

    def confirm(self) -> None:
        """
        注文を確定する

        ★ 不変条件: 明細が1つ以上必要
        ★ 状態遷移: DRAFT → CONFIRMED
        """
        if self._status != OrderStatus.DRAFT:
            raise InvalidOrderStateError(
                f"注文を確定できるのはDRAFT状態のみです（現在: {self._status.value}）"
            )
        if not self._lines:
            raise EmptyOrderError("注文明細が空のため確定できません")

        self._status = OrderStatus.CONFIRMED
        self._confirmed_at = datetime.now()

        # ドメインイベントを記録
        self._record_event(OrderConfirmed(
            order_id=str(self._id),
            total_amount=self.total_amount.amount,
        ))

    def cancel(self, reason: str = "") -> None:
        """
        注文をキャンセルする

        ★ 状態遷移: DRAFT or CONFIRMED → CANCELLED
        ★ 出荷済み・配達完了の注文はキャンセルできない
        """
        if self._status in (OrderStatus.SHIPPED, OrderStatus.DELIVERED):
            raise InvalidOrderStateError(
                f"出荷済み/配達完了の注文はキャンセルできません"
                f"（現在: {self._status.value}）"
            )
        if self._status == OrderStatus.CANCELLED:
            raise InvalidOrderStateError("既にキャンセルされています")

        self._status = OrderStatus.CANCELLED

        # ドメインイベントを記録
        self._record_event(OrderCancelled(
            order_id=str(self._id),
            reason=reason,
        ))

    def clear_domain_events(self) -> None:
        """
        ドメインイベントをクリアする

        ★ リポジトリが save() 後にイベントをディスパッチし、
          その後にクリアする
        """
        self._domain_events.clear()

    # --- 内部メソッド ---

    def _assert_modifiable(self) -> None:
        """変更可能な状態かチェック"""
        if self._status != OrderStatus.DRAFT:
            raise InvalidOrderStateError(
                f"注文を変更できるのはDRAFT状態のみです（現在: {self._status.value}）"
            )

    def _assert_within_amount_limit(self) -> None:
        """合計金額が上限以下かチェック"""
        if self.total_amount.is_greater_than(self.MAX_ORDER_AMOUNT):
            # 不変条件違反: 最後に追加した明細を取り消す
            self._lines.pop()
            raise OrderAmountExceededError(
                f"注文合計金額が上限を超えます（上限: {self.MAX_ORDER_AMOUNT}）"
            )

    def _find_line(self, line_id: OrderLineId) -> OrderLine:
        """注文明細を検索する"""
        for line in self._lines:
            if line.line_id == line_id:
                return line
        raise OrderLineNotFoundError(
            f"注文明細が見つかりません: {line_id}"
        )

    def _record_event(self, event: DomainEvent) -> None:
        """ドメインイベントを記録する"""
        self._domain_events.append(event)

    def __repr__(self) -> str:
        return (
            f"Order(id={self._id}, "
            f"status={self._status.value}, "
            f"lines={self.line_count}, "
            f"total={self.total_amount})"
        )


# ==========================================================
# 使用例
# ==========================================================

def main() -> None:
    """注文集約の使用例デモ"""

    print("=" * 60)
    print("【注文集約（Order Aggregate）のデモ】")
    print("=" * 60)

    # 1. 注文を作成する（DRAFT状態で始まる）
    order_id = OrderId.generate()
    order = Order(order_id=order_id, customer_id="CUST-001")
    print(f"\n1. 注文を作成: {order}")

    # 2. 商品を追加する（集約ルート経由でのみ操作）
    line1_id = order.add_item(
        product_id="PROD-001",
        product_name="プレミアムコーヒー豆 200g",
        unit_price=Money(amount=1980),
        quantity=Quantity(value=2),
    )
    print(f"2. 商品を追加: {order.lines[-1]}")

    line2_id = order.add_item(
        product_id="PROD-002",
        product_name="オーガニック紅茶 100g",
        unit_price=Money(amount=1500),
        quantity=Quantity(value=1),
    )
    print(f"   商品を追加: {order.lines[-1]}")
    print(f"   合計金額: {order.total_amount}")

    # 3. 数量を変更する（集約ルート経由で OrderLine の数量を変更）
    order.change_item_quantity(line1_id, Quantity(value=3))
    print(f"\n3. 数量変更後: {order.lines[0]}")
    print(f"   合計金額: {order.total_amount}")

    # 4. 注文を確定する
    order.confirm()
    print(f"\n4. 注文を確定: status={order.status.value}")

    # 5. 確定後は商品を追加できない（不変条件の保証）
    print("\n5. 確定後の操作テスト:")
    try:
        order.add_item(
            product_id="PROD-003",
            product_name="テスト商品",
            unit_price=Money(amount=100),
            quantity=Quantity(value=1),
        )
    except InvalidOrderStateError as e:
        print(f"   ✅ 期待通りのエラー: {e}")

    # 6. ドメインイベントの確認
    print(f"\n6. 記録されたドメインイベント:")
    for event in order.domain_events:
        print(f"   - {type(event).__name__}: {event}")

    # 7. 金額上限のテスト
    print(f"\n7. 金額上限のテスト:")
    order2 = Order(order_id=OrderId.generate(), customer_id="CUST-002")
    try:
        order2.add_item(
            product_id="PROD-999",
            product_name="超高額商品",
            unit_price=Money(amount=500_001),
            quantity=Quantity(value=2),
        )
    except OrderAmountExceededError as e:
        print(f"   ✅ 金額上限エラー: {e}")

    # 8. キャンセルのテスト
    print(f"\n8. キャンセルのテスト:")
    order3 = Order(order_id=OrderId.generate(), customer_id="CUST-003")
    order3.add_item(
        product_id="PROD-001",
        product_name="テスト商品",
        unit_price=Money(amount=1000),
        quantity=Quantity(value=1),
    )
    order3.cancel(reason="顧客都合によるキャンセル")
    print(f"   status={order3.status.value}")
    cancel_events = [
        e for e in order3.domain_events if isinstance(e, OrderCancelled)
    ]
    print(f"   キャンセルイベント: {cancel_events[0]}")

    print("\n" + "=" * 60)
    print("✅ 集約のポイント:")
    print("  1. Order（集約ルート）のメソッドだけで操作する")
    print("  2. OrderLine を外部から直接変更できない")
    print("  3. 不変条件（金額上限、状態遷移）が常に保証される")
    print("  4. ドメインイベントが記録される")
    print("=" * 60)


if __name__ == "__main__":
    main()
