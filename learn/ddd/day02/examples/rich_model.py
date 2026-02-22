"""
リッチドメインモデル（Rich Domain Model）の例
=============================================

anemic_model.py と同じECサイトの注文システムを
「リッチドメインモデル」で書き直した例。

【特徴】
- Order クラスがビジネスロジックを持つ
- オブジェクトが自分の整合性（不変条件）を守る
- 不正な状態を外部から作れない
- コードを読むだけで「注文のビジネスルール」が理解できる

【anemic_model.py との違い】
- Order がデータ + ビジネスロジックを持つ
- Service は「手順の調整」のみ（ドメインロジックを持たない）
- ドメインイベントで「何が起きたか」を表現する
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from decimal import Decimal
from enum import Enum
from typing import Optional


# =============================================================================
# 値オブジェクト（Value Objects）
# =============================================================================

@dataclass(frozen=True)
class Money:
    """
    金額を表す値オブジェクト

    - 不変（frozen=True）
    - マイナスの金額は作れない
    - 金額同士の演算が可能
    """
    amount: int  # 円（整数）

    def __post_init__(self):
        if self.amount < 0:
            raise ValueError(f"金額は0以上でなければなりません: {self.amount}")

    def add(self, other: Money) -> Money:
        """金額を加算する"""
        return Money(self.amount + other.amount)

    def subtract(self, other: Money) -> Money:
        """金額を減算する（結果が0未満になる場合はエラー）"""
        result = self.amount - other.amount
        if result < 0:
            raise ValueError("金額がマイナスになります")
        return Money(result)

    def multiply(self, factor: int) -> Money:
        """数量を掛ける"""
        if factor < 0:
            raise ValueError("乗数は0以上でなければなりません")
        return Money(self.amount * factor)

    def apply_rate(self, rate: Decimal) -> Money:
        """割引率などを適用する"""
        return Money(int(self.amount * rate))

    def is_greater_than_or_equal(self, other: Money) -> bool:
        """他の金額以上かどうかを判定する"""
        return self.amount >= other.amount

    @classmethod
    def zero(cls) -> Money:
        """0円を返す"""
        return cls(0)

    def __str__(self) -> str:
        return f"¥{self.amount:,}"


@dataclass(frozen=True)
class Quantity:
    """
    数量を表す値オブジェクト

    - 不変（frozen=True）
    - 1以上の整数のみ
    """
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise ValueError(f"数量は1以上でなければなりません: {self.value}")

    def add(self, other: Quantity) -> Quantity:
        """数量を加算する"""
        return Quantity(self.value + other.value)

    def __str__(self) -> str:
        return f"{self.value}個"


# =============================================================================
# ドメインイベント（Domain Events）
# =============================================================================

@dataclass(frozen=True)
class DomainEvent:
    """ドメインイベントの基底クラス"""
    occurred_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class OrderConfirmed(DomainEvent):
    """注文が確定された"""
    order_id: str = ""
    total_amount: int = 0


@dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    """注文がキャンセルされた"""
    order_id: str = ""
    reason: str = ""
    was_confirmed: bool = False  # 確定済みからのキャンセルか（在庫戻しが必要）


@dataclass(frozen=True)
class ItemAddedToOrder(DomainEvent):
    """注文に商品が追加された"""
    order_id: str = ""
    product_id: str = ""
    quantity: int = 0


# =============================================================================
# 注文ステータス
# =============================================================================

class OrderStatus(Enum):
    """注文ステータス"""
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"

    def can_transition_to(self, target: OrderStatus) -> bool:
        """
        許可された状態遷移を定義する

        ステータス遷移の知識がステータス自身にカプセル化されている
        """
        allowed_transitions = {
            OrderStatus.DRAFT: {OrderStatus.CONFIRMED, OrderStatus.CANCELLED},
            OrderStatus.CONFIRMED: {OrderStatus.PAID, OrderStatus.CANCELLED},
            OrderStatus.PAID: {OrderStatus.SHIPPED},
            OrderStatus.SHIPPED: {OrderStatus.DELIVERED},
            OrderStatus.DELIVERED: set(),   # 最終状態
            OrderStatus.CANCELLED: set(),   # 最終状態
        }
        return target in allowed_transitions.get(self, set())


# =============================================================================
# 割引ポリシー（ドメインの概念を明示的にモデル化）
# =============================================================================

class DiscountPolicy:
    """割引ポリシーの基底クラス — Strategy パターン"""

    def calculate_discount(self, subtotal: Money) -> Money:
        """割引額を計算する"""
        raise NotImplementedError


class NoDiscount(DiscountPolicy):
    """割引なし"""

    def calculate_discount(self, subtotal: Money) -> Money:
        return Money.zero()


class PremiumMemberDiscount(DiscountPolicy):
    """
    プレミアム会員割引 — 10%オフ

    ビジネスルール: プレミアム会員は全商品10%割引
    """
    DISCOUNT_RATE = Decimal("0.10")

    def calculate_discount(self, subtotal: Money) -> Money:
        return subtotal.apply_rate(self.DISCOUNT_RATE)


class SeasonalDiscount(DiscountPolicy):
    """
    季節割引 — 指定割引率

    ビジネスルール: セール期間中は指定の割引率を適用
    """

    def __init__(self, rate: Decimal):
        if not (Decimal("0") < rate < Decimal("1")):
            raise ValueError("割引率は0〜1の間でなければなりません")
        self.rate = rate

    def calculate_discount(self, subtotal: Money) -> Money:
        return subtotal.apply_rate(self.rate)


# =============================================================================
# 送料ポリシー
# =============================================================================

class ShippingFeePolicy:
    """送料ポリシー"""
    FREE_SHIPPING_THRESHOLD = Money(10000)
    DEFAULT_SHIPPING_FEE = Money(500)

    def calculate(self, order_amount: Money) -> Money:
        """
        送料を計算する

        ビジネスルール: 10,000円以上で送料無料、それ以外は500円
        """
        if order_amount.is_greater_than_or_equal(self.FREE_SHIPPING_THRESHOLD):
            return Money.zero()
        return self.DEFAULT_SHIPPING_FEE


# =============================================================================
# 注文明細（OrderLine）— 値オブジェクト
# =============================================================================

@dataclass(frozen=True)
class OrderLine:
    """
    注文明細 — 不変の値オブジェクト

    - 生成時にバリデーションされる
    - 不正な状態では作れない
    - 小計の計算は自分の責務
    """
    product_id: str
    product_name: str
    unit_price: Money
    quantity: Quantity

    def __post_init__(self):
        if not self.product_id:
            raise ValueError("商品IDは必須です")
        if not self.product_name:
            raise ValueError("商品名は必須です")

    @property
    def subtotal(self) -> Money:
        """小計を計算する — 明細自身の責務"""
        return self.unit_price.multiply(self.quantity.value)

    def with_added_quantity(self, additional: Quantity) -> OrderLine:
        """数量を追加した新しい明細を返す（不変なので新規作成）"""
        new_quantity = self.quantity.add(additional)
        return OrderLine(
            product_id=self.product_id,
            product_name=self.product_name,
            unit_price=self.unit_price,
            quantity=new_quantity,
        )


# =============================================================================
# 注文（Order）— 集約ルート（Aggregate Root）
# =============================================================================

class Order:
    """
    注文 — リッチドメインモデル

    【設計原則】
    1. 全てのビジネスルールをこのクラス内にカプセル化
    2. 不正な状態を外部から作れないようにする
    3. 状態遷移を自分で管理する
    4. ドメインイベントで「何が起きたか」を通知する

    【anemic_model.py との違い】
    - set_status() がない → 外部からステータスを直接変更できない
    - confirm(), cancel() などのビジネスメソッドを持つ
    - 不変条件を自分で守る
    """

    MAX_ITEMS_PER_ORDER = 20  # 1注文あたりの最大明細数

    def __init__(
        self,
        order_id: str,
        customer_id: str,
        discount_policy: DiscountPolicy | None = None,
        shipping_fee_policy: ShippingFeePolicy | None = None,
    ):
        if not order_id:
            raise ValueError("注文IDは必須です")
        if not customer_id:
            raise ValueError("顧客IDは必須です")

        self._order_id = order_id
        self._customer_id = customer_id
        self._items: dict[str, OrderLine] = {}  # product_id → OrderLine
        self._status = OrderStatus.DRAFT
        self._discount_policy = discount_policy or NoDiscount()
        self._shipping_fee_policy = shipping_fee_policy or ShippingFeePolicy()
        self._ordered_at: Optional[datetime] = None
        self._cancelled_at: Optional[datetime] = None
        self._cancellation_reason: Optional[str] = None
        self._domain_events: list[DomainEvent] = []

    # --- プロパティ（読み取り専用） ---

    @property
    def order_id(self) -> str:
        return self._order_id

    @property
    def customer_id(self) -> str:
        return self._customer_id

    @property
    def status(self) -> OrderStatus:
        return self._status

    @property
    def items(self) -> list[OrderLine]:
        return list(self._items.values())

    @property
    def ordered_at(self) -> Optional[datetime]:
        return self._ordered_at

    @property
    def cancellation_reason(self) -> Optional[str]:
        return self._cancellation_reason

    @property
    def domain_events(self) -> list[DomainEvent]:
        """発生したドメインイベントを取得する"""
        return list(self._domain_events)

    def clear_domain_events(self) -> None:
        """ドメインイベントをクリアする（永続化後に呼ぶ）"""
        self._domain_events.clear()

    # --- 金額計算（ドメインロジック） ---

    @property
    def subtotal(self) -> Money:
        """小計（割引前、送料前）を計算する"""
        total = Money.zero()
        for item in self._items.values():
            total = total.add(item.subtotal)
        return total

    @property
    def discount_amount(self) -> Money:
        """割引額を計算する"""
        return self._discount_policy.calculate_discount(self.subtotal)

    @property
    def amount_after_discount(self) -> Money:
        """割引後の金額を計算する"""
        return self.subtotal.subtract(self.discount_amount)

    @property
    def shipping_fee(self) -> Money:
        """送料を計算する"""
        return self._shipping_fee_policy.calculate(self.amount_after_discount)

    @property
    def total_amount(self) -> Money:
        """
        合計金額を計算する

        ビジネスルール: 小計 - 割引 + 送料
        → この計算ロジックが Order 内にカプセル化されている
        """
        return self.amount_after_discount.add(self.shipping_fee)

    # --- ビジネス操作（コマンド） ---

    def add_item(self, product_id: str, product_name: str,
                 unit_price: int, quantity: int) -> None:
        """
        注文に商品を追加する

        【不変条件】
        - 下書き状態でのみ追加可能
        - 最大明細数を超えない
        - 数量は1以上（Quantity値オブジェクトが保証）
        - 単価は0以上（Money値オブジェクトが保証）
        """
        self._ensure_status(OrderStatus.DRAFT, "下書き状態の注文にのみ商品を追加できます")

        price = Money(unit_price)
        qty = Quantity(quantity)

        # 既存の同一商品があれば数量を加算
        if product_id in self._items:
            existing = self._items[product_id]
            self._items[product_id] = existing.with_added_quantity(qty)
        else:
            if len(self._items) >= self.MAX_ITEMS_PER_ORDER:
                raise ValueError(
                    f"1注文あたり最大{self.MAX_ITEMS_PER_ORDER}明細までです"
                )
            self._items[product_id] = OrderLine(
                product_id=product_id,
                product_name=product_name,
                unit_price=price,
                quantity=qty,
            )

        # ドメインイベントを記録
        self._record_event(ItemAddedToOrder(
            order_id=self._order_id,
            product_id=product_id,
            quantity=quantity,
        ))

    def remove_item(self, product_id: str) -> None:
        """注文から商品を削除する"""
        self._ensure_status(OrderStatus.DRAFT, "下書き状態の注文からのみ商品を削除できます")

        if product_id not in self._items:
            raise ValueError(f"商品 {product_id} は注文に含まれていません")

        del self._items[product_id]

    def confirm(self) -> None:
        """
        注文を確定する

        【事前条件】
        - 下書き状態であること
        - 明細が1つ以上あること

        【事後条件】
        - ステータスが CONFIRMED になる
        - 注文日時が記録される
        - OrderConfirmed イベントが発生する
        """
        self._ensure_status(OrderStatus.DRAFT, "下書き状態の注文のみ確定できます")

        if not self._items:
            raise ValueError("明細が空の注文は確定できません")

        self._transition_to(OrderStatus.CONFIRMED)
        self._ordered_at = datetime.now()

        self._record_event(OrderConfirmed(
            order_id=self._order_id,
            total_amount=self.total_amount.amount,
        ))

    def cancel(self, reason: str) -> None:
        """
        注文をキャンセルする

        【ビジネスルール】
        - 下書きまたは確定済みの注文のみキャンセル可能
        - 出荷済み・配達済みの注文はキャンセルできない
        - キャンセル理由は必須

        【事後条件】
        - ステータスが CANCELLED になる
        - キャンセル日時と理由が記録される
        - OrderCancelled イベントが発生する
          （確定済みからのキャンセルは was_confirmed=True → 在庫戻しが必要）
        """
        if self._status not in (OrderStatus.DRAFT, OrderStatus.CONFIRMED):
            raise ValueError(
                f"現在のステータス({self._status.value})ではキャンセルできません。"
                "下書きまたは確定済みの注文のみキャンセル可能です。"
            )

        if not reason or not reason.strip():
            raise ValueError("キャンセル理由は必須です")

        was_confirmed = self._status == OrderStatus.CONFIRMED

        self._transition_to(OrderStatus.CANCELLED)
        self._cancelled_at = datetime.now()
        self._cancellation_reason = reason

        self._record_event(OrderCancelled(
            order_id=self._order_id,
            reason=reason,
            was_confirmed=was_confirmed,
        ))

    def mark_as_paid(self) -> None:
        """支払い済みにする"""
        self._ensure_status(OrderStatus.CONFIRMED, "確定済みの注文のみ支払い処理できます")
        self._transition_to(OrderStatus.PAID)

    def ship(self) -> None:
        """出荷する"""
        self._ensure_status(OrderStatus.PAID, "支払い済みの注文のみ出荷できます")
        self._transition_to(OrderStatus.SHIPPED)

    def deliver(self) -> None:
        """配達完了にする"""
        self._ensure_status(OrderStatus.SHIPPED, "出荷済みの注文のみ配達完了にできます")
        self._transition_to(OrderStatus.DELIVERED)

    # --- 内部メソッド ---

    def _ensure_status(self, expected: OrderStatus, message: str) -> None:
        """現在のステータスが期待値と一致することを確認する"""
        if self._status != expected:
            raise ValueError(message)

    def _transition_to(self, target: OrderStatus) -> None:
        """
        ステータスを遷移する

        許可されていない遷移はエラーになる
        → OrderStatus.can_transition_to() で遷移ルールを管理
        """
        if not self._status.can_transition_to(target):
            raise ValueError(
                f"ステータスを {self._status.value} から "
                f"{target.value} に変更することはできません"
            )
        self._status = target

    def _record_event(self, event: DomainEvent) -> None:
        """ドメインイベントを記録する"""
        self._domain_events.append(event)

    def __repr__(self) -> str:
        return (
            f"Order(id={self._order_id}, status={self._status.value}, "
            f"items={len(self._items)}, total={self.total_amount})"
        )


# =============================================================================
# アプリケーションサービス — 「手順の調整」のみ
# =============================================================================

class OrderApplicationService:
    """
    注文アプリケーションサービス

    【リッチモデルでの Service の役割】
    - ビジネスロジックは Order に委譲する
    - このクラスは「手順の調整」のみを行う
      1. リポジトリからの取得
      2. ドメインオブジェクトのメソッド呼び出し
      3. リポジトリへの保存
      4. ドメインイベントのディスパッチ
      5. 外部サービスの呼び出し

    【anemic_model.py の OrderService との違い】
    - ビジネスルール（合計計算、ステータス遷移チェック等）が一切ない
    - Order に処理を委譲しているだけ
    """

    def __init__(self, order_repository, inventory_service,
                 payment_gateway, event_dispatcher):
        self.order_repo = order_repository
        self.inventory_service = inventory_service
        self.payment_gateway = payment_gateway
        self.event_dispatcher = event_dispatcher

    def confirm_order(self, order_id: str) -> None:
        """
        注文を確定する

        【比較: anemic_model.py の OrderService.confirm_order()】
        - 貧血モデル: ステータスチェック、在庫チェック、ステータス設定...全部 Service
        - リッチモデル: order.confirm() を呼ぶだけ。ルールは Order が知っている
        """
        # 1. 取得
        order = self.order_repo.find_by_id(order_id)
        if order is None:
            raise ValueError(f"注文 {order_id} が見つかりません")

        # 2. 在庫チェック（外部サービス連携 = アプリケーションの関心事）
        for item in order.items:
            if not self.inventory_service.is_available(item.product_id, item.quantity.value):
                raise ValueError(f"商品 {item.product_name} の在庫が不足しています")

        # 3. ドメインオブジェクトにビジネス操作を委譲
        order.confirm()  # ← ビジネスルールは Order 内にある

        # 4. 保存
        self.order_repo.save(order)

        # 5. ドメインイベントのディスパッチ
        for event in order.domain_events:
            self.event_dispatcher.dispatch(event)
        order.clear_domain_events()

    def cancel_order(self, order_id: str, reason: str) -> None:
        """注文をキャンセルする"""
        order = self.order_repo.find_by_id(order_id)
        if order is None:
            raise ValueError(f"注文 {order_id} が見つかりません")

        # ドメインオブジェクトに委譲（キャンセル可能かどうかは Order が判断）
        order.cancel(reason)

        self.order_repo.save(order)

        # イベント処理（在庫戻しはイベントハンドラで行う）
        for event in order.domain_events:
            self.event_dispatcher.dispatch(event)
        order.clear_domain_events()


# =============================================================================
# 使用例 — リッチモデルの利点を示す
# =============================================================================

def demonstrate_rich_model():
    """
    リッチドメインモデルの利点を実演する
    """

    print("=" * 60)
    print("リッチドメインモデルの実演")
    print("=" * 60)

    # --- 利点1: 不正な状態を作れない ---
    print("\n--- 利点1: 不正な状態を作れない ---")

    order = Order(
        order_id="ORD-001",
        customer_id="CUST-001",
        discount_policy=PremiumMemberDiscount(),
    )

    # マイナスの金額は作れない（Money値オブジェクトが防ぐ）
    try:
        Money(-1000)
    except ValueError as e:
        print(f"  Money(-1000) → エラー: {e}")

    # 数量0は作れない（Quantity値オブジェクトが防ぐ）
    try:
        Quantity(0)
    except ValueError as e:
        print(f"  Quantity(0) → エラー: {e}")

    # ステータスを直接変更する方法がない
    # order._status = OrderStatus.SHIPPED  # ← 規約上やってはいけない
    # order.set_status(...)                # ← そもそもメソッドが存在しない

    # --- 利点2: ビジネスロジックが Order に集約されている ---
    print("\n--- 利点2: ビジネスロジックが Order に集約 ---")

    order.add_item("PROD-001", "プログラミング入門書", 3000, 2)
    order.add_item("PROD-002", "ドメイン駆動設計", 4500, 1)

    print(f"  小計: {order.subtotal}")
    print(f"  割引（プレミアム10%）: {order.discount_amount}")
    print(f"  送料: {order.shipping_fee}")
    print(f"  合計: {order.total_amount}")

    # --- 利点3: 状態遷移が安全 ---
    print("\n--- 利点3: 状態遷移が安全 ---")

    # 空の注文は確定できない
    empty_order = Order(order_id="ORD-002", customer_id="CUST-002")
    try:
        empty_order.confirm()
    except ValueError as e:
        print(f"  空の注文を確定 → エラー: {e}")

    # 正しい遷移
    order.confirm()
    print(f"  注文確定: {order.status.value}")

    # 確定済みの注文に商品は追加できない
    try:
        order.add_item("PROD-003", "新しい本", 2000, 1)
    except ValueError as e:
        print(f"  確定済み注文に追加 → エラー: {e}")

    # 確定済みから出荷には直接遷移できない（支払いが必要）
    try:
        order.ship()
    except ValueError as e:
        print(f"  支払い前に出荷 → エラー: {e}")

    # --- 利点4: ドメインイベントで「何が起きたか」がわかる ---
    print("\n--- 利点4: ドメインイベント ---")
    for event in order.domain_events:
        print(f"  イベント: {type(event).__name__} - {event}")

    # --- 利点5: コードが業務用語で書かれている ---
    print("\n--- 利点5: ユビキタス言語がコードに反映 ---")
    print("  order.confirm()   → 「注文を確定する」")
    print("  order.cancel()    → 「注文をキャンセルする」")
    print("  order.ship()      → 「注文を出荷する」")
    print("  order.total_amount → 「合計金額」")
    print("  → ドメインエキスパートもコードを読める！")


if __name__ == "__main__":
    demonstrate_rich_model()
