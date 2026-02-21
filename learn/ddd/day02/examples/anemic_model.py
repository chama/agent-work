"""
貧血ドメインモデル（Anemic Domain Model）の例
=============================================

ECサイトの注文システムを「貧血ドメインモデル」で実装した例。

【特徴】
- Order クラスはデータの入れ物にすぎない（getter/setter のみ）
- ビジネスロジックは全て OrderService クラスに集中している
- Order オブジェクトは自分の整合性を守れない

【問題点】
- ビジネスルールが Service に散在する
- 不正な状態を簡単に作れてしまう
- コードから「注文とは何か」が読み取れない
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# =============================================================================
# ステータス定義
# =============================================================================

class OrderStatus(Enum):
    """注文ステータス"""
    DRAFT = "draft"
    CONFIRMED = "confirmed"
    PAID = "paid"
    SHIPPED = "shipped"
    DELIVERED = "delivered"
    CANCELLED = "cancelled"


# =============================================================================
# 貧血ドメインモデル — データだけを持つクラス群
# =============================================================================

@dataclass
class OrderItem:
    """注文明細 — ただのデータ入れ物"""
    product_id: str
    product_name: str
    unit_price: int       # 単価（円）
    quantity: int          # 数量

    # ↑ ビジネスロジックが一切ない！
    # - 数量が0以下でも設定できてしまう
    # - 単価がマイナスでも設定できてしまう


@dataclass
class Order:
    """
    注文 — 貧血ドメインモデルの典型例

    このクラスには以下の問題がある：
    1. ビジネスロジックが一切ない（データの入れ物）
    2. 全てのフィールドが外部から自由に変更可能
    3. 不正な状態を防ぐ仕組みがない
    """
    order_id: str
    customer_id: str
    items: list[OrderItem] = field(default_factory=list)
    status: OrderStatus = OrderStatus.DRAFT
    total_amount: int = 0
    discount_amount: int = 0
    shipping_fee: int = 0
    ordered_at: Optional[datetime] = None
    cancelled_at: Optional[datetime] = None
    cancellation_reason: Optional[str] = None

    # ↓ getter/setter しかない（Pythonでは dataclass で自動生成されるが、概念は同じ）

    def get_order_id(self) -> str:
        return self.order_id

    def get_status(self) -> OrderStatus:
        return self.status

    def set_status(self, status: OrderStatus) -> None:
        # どんなステータスにも自由に変更できてしまう！
        self.status = status

    def get_items(self) -> list[OrderItem]:
        return self.items

    def add_item(self, item: OrderItem) -> None:
        # バリデーションなし！何でも追加できてしまう
        self.items.append(item)

    def set_total_amount(self, amount: int) -> None:
        # マイナスの金額も設定できてしまう！
        self.total_amount = amount

    def set_discount_amount(self, amount: int) -> None:
        self.discount_amount = amount

    def set_shipping_fee(self, fee: int) -> None:
        self.shipping_fee = fee


# =============================================================================
# サービスクラス — 全てのビジネスロジックがここに集中
# =============================================================================

class OrderService:
    """
    注文サービス — ビジネスロジックの置き場所

    【問題点】
    - Order の知識がこのクラスに漏れ出している
    - このクラスがないと Order は何もできない
    - ビジネスルールを理解するにはこのクラスを全て読む必要がある
    - 他のサービスでも同じチェックを書く必要があり、重複が発生する
    """

    # 定数もサービスに定義されている（本来は注文ドメインの知識）
    FREE_SHIPPING_THRESHOLD = 10000  # 送料無料の閾値
    DEFAULT_SHIPPING_FEE = 500       # 通常送料
    PREMIUM_DISCOUNT_RATE = 0.10     # プレミアム会員割引率
    MAX_ITEMS_PER_ORDER = 20         # 1注文あたりの最大明細数

    def __init__(self, customer_repository, inventory_service, payment_gateway):
        self.customer_repo = customer_repository
        self.inventory_service = inventory_service
        self.payment_gateway = payment_gateway

    def add_item_to_order(self, order: Order, product_id: str,
                          product_name: str, unit_price: int, quantity: int) -> None:
        """
        注文に商品を追加する

        ↓ ビジネスルールが全てここに書かれている
        """
        # バリデーション（本来は Order が自分で守るべき不変条件）
        if quantity <= 0:
            raise ValueError("数量は1以上でなければなりません")

        if unit_price < 0:
            raise ValueError("単価は0以上でなければなりません")

        if len(order.items) >= self.MAX_ITEMS_PER_ORDER:
            raise ValueError(f"1注文あたり最大{self.MAX_ITEMS_PER_ORDER}明細までです")

        if order.status != OrderStatus.DRAFT:
            raise ValueError("下書き状態の注文にのみ商品を追加できます")

        # 在庫チェック
        if not self.inventory_service.is_available(product_id, quantity):
            raise ValueError(f"商品 {product_name} の在庫が不足しています")

        # 既存の同一商品があれば数量を加算
        for item in order.items:
            if item.product_id == product_id:
                item.quantity += quantity
                self._recalculate_total(order)
                return

        # 新規明細を追加
        item = OrderItem(
            product_id=product_id,
            product_name=product_name,
            unit_price=unit_price,
            quantity=quantity,
        )
        order.add_item(item)
        self._recalculate_total(order)

    def remove_item_from_order(self, order: Order, product_id: str) -> None:
        """注文から商品を削除する"""
        if order.status != OrderStatus.DRAFT:
            raise ValueError("下書き状態の注文からのみ商品を削除できます")

        order.items = [item for item in order.items if item.product_id != product_id]
        self._recalculate_total(order)

    def _recalculate_total(self, order: Order) -> None:
        """
        合計金額を再計算する

        ↓ 「合計金額の計算方法」という注文ドメインの知識が
           サービスクラスに漏れ出している
        """
        subtotal = sum(item.unit_price * item.quantity for item in order.items)

        # 割引計算（プレミアム会員かどうかで分岐）
        customer = self.customer_repo.find_by_id(order.customer_id)
        discount = 0
        if customer and customer.is_premium:
            discount = int(subtotal * self.PREMIUM_DISCOUNT_RATE)
        order.set_discount_amount(discount)

        # 送料計算
        amount_after_discount = subtotal - discount
        if amount_after_discount >= self.FREE_SHIPPING_THRESHOLD:
            shipping_fee = 0
        else:
            shipping_fee = self.DEFAULT_SHIPPING_FEE
        order.set_shipping_fee(shipping_fee)

        # 合計
        order.set_total_amount(amount_after_discount + shipping_fee)

    def confirm_order(self, order: Order) -> None:
        """
        注文を確定する

        ↓ 状態遷移のルールがサービスに書かれている
           Order 自身が「自分がどの状態に遷移できるか」を知らない
        """
        if order.status != OrderStatus.DRAFT:
            raise ValueError("下書き状態の注文のみ確定できます")

        if not order.items:
            raise ValueError("明細が空の注文は確定できません")

        # 全商品の在庫を再チェック
        for item in order.items:
            if not self.inventory_service.is_available(item.product_id, item.quantity):
                raise ValueError(f"商品 {item.product_name} の在庫が不足しています")

        # ステータスを変更（外部から自由に設定）
        order.set_status(OrderStatus.CONFIRMED)
        order.ordered_at = datetime.now()

    def cancel_order(self, order: Order, reason: str) -> None:
        """
        注文をキャンセルする

        ↓ キャンセル可能かどうかの判断もサービスに書かれている
        """
        if order.status not in (OrderStatus.DRAFT, OrderStatus.CONFIRMED):
            raise ValueError("下書きまたは確定済みの注文のみキャンセルできます")

        if not reason:
            raise ValueError("キャンセル理由は必須です")

        # 確定済みの場合は在庫を戻す
        if order.status == OrderStatus.CONFIRMED:
            for item in order.items:
                self.inventory_service.release(item.product_id, item.quantity)

        order.set_status(OrderStatus.CANCELLED)
        order.cancelled_at = datetime.now()
        order.cancellation_reason = reason

    def process_payment(self, order: Order) -> None:
        """支払い処理"""
        if order.status != OrderStatus.CONFIRMED:
            raise ValueError("確定済みの注文のみ支払い処理できます")

        # 決済処理
        self.payment_gateway.charge(order.customer_id, order.total_amount)
        order.set_status(OrderStatus.PAID)

    def ship_order(self, order: Order) -> None:
        """出荷処理"""
        if order.status != OrderStatus.PAID:
            raise ValueError("支払い済みの注文のみ出荷できます")

        order.set_status(OrderStatus.SHIPPED)


# =============================================================================
# 使用例 — 貧血モデルの問題点を示す
# =============================================================================

def demonstrate_problems():
    """
    貧血ドメインモデルの問題点を実演する
    """

    # --- 問題1: 不正な状態を簡単に作れる ---
    order = Order(order_id="ORD-001", customer_id="CUST-001")

    # 出荷済みなのにキャンセルに変更できてしまう！
    order.set_status(OrderStatus.SHIPPED)
    order.set_status(OrderStatus.CANCELLED)  # ← ビジネス上ありえない遷移

    # マイナスの金額を設定できてしまう！
    order.set_total_amount(-1000)

    # 数量0の明細を追加できてしまう！
    bad_item = OrderItem(
        product_id="PROD-001",
        product_name="テスト商品",
        unit_price=100,
        quantity=0,  # ← 0個の注文は意味がない
    )
    order.add_item(bad_item)

    print("問題1: 不正な状態が作成可能")
    print(f"  ステータス: {order.status}")         # CANCELLED
    print(f"  合計金額: {order.total_amount}")       # -1000
    print(f"  明細の数量: {order.items[0].quantity}")  # 0

    # --- 問題2: Service がないと何もできない ---
    # order.confirm()         ← こんなメソッドはない
    # order.calculate_total() ← こんなメソッドもない
    # → 全ての操作に OrderService が必要

    # --- 問題3: ビジネスルールがコードから読み取れない ---
    # Order クラスを見ても「注文のルール」がわからない
    # 「どのステータスからどのステータスに遷移できるか？」
    # 「合計金額はどう計算するのか？」
    # → OrderService の全メソッドを読まないとわからない

    print("\n問題2: Order クラスにはビジネスロジックが一切ない")
    print("  → OrderService が全てのルールを持っている")
    print("  → Order は単なるデータの入れ物")

    print("\n問題3: ビジネスルールの散在")
    print("  → 在庫チェックが add_item_to_order と confirm_order の両方にある")
    print("  → ステータス遷移ルールが confirm_order, cancel_order, ship_order に分散")


if __name__ == "__main__":
    demonstrate_problems()
