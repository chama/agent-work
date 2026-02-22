"""
ユビキタス言語の実践例: ECサイトの「注文」ドメイン

このファイルは、ユビキタス言語がどのようにコードに反映されるかを示す。
ECサイトの注文処理を題材に、ドメインエキスパートと開発チームが合意した
用語がそのままクラス名・メソッド名・変数名になっている。

【ユビキタス言語の用語集（抜粋）】
  - 注文（Order）: 購入者が商品の購入を確定した取引
  - 注文明細（OrderLineItem）: 注文内の個々の商品と数量の組
  - 購入者（Buyer）: 商品を購入する会員
  - 注文を確定する（place order）: カートの内容を注文として確定する行為
  - 出荷前キャンセル（cancel before shipment）: 出荷前の注文取り消し
  - 在庫引当（allocate stock）: 注文確定時に在庫を確保すること
  - 在庫不足（insufficient stock）: 要求数量に対して在庫が足りない状態
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import NewType

# ============================================================
# 値オブジェクト: ドメインの識別子や量を型で表現する
# ============================================================

OrderId = NewType("OrderId", str)
ProductId = NewType("ProductId", str)
BuyerId = NewType("BuyerId", str)


@dataclass(frozen=True)
class Money:
    """金額: 通貨と金額の組み合わせを表す値オブジェクト"""
    amount: int    # 金額（円単位、小数なし）
    currency: str = "JPY"

    def __post_init__(self):
        if self.amount < 0:
            raise NegativeMoneyError(self.amount)

    def add(self, other: Money) -> Money:
        """金額を加算する"""
        assert self.currency == other.currency, "通貨が異なります"
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def multiply(self, quantity: int) -> Money:
        """金額に数量を掛ける"""
        return Money(amount=self.amount * quantity, currency=self.currency)


@dataclass(frozen=True)
class Quantity:
    """数量: 注文における商品の個数を表す値オブジェクト"""
    value: int

    def __post_init__(self):
        if self.value <= 0:
            raise InvalidQuantityError(self.value)


# ============================================================
# 注文ステータス: 注文のライフサイクルを表す
# ============================================================

class OrderStatus(Enum):
    """注文ステータス: 注文の現在の状態

    ライフサイクル:
      確定済み → 出荷準備中 → 出荷済み → 配達完了
                └→ キャンセル済み（出荷前のみ可能）
    """
    PLACED = "placed"               # 注文確定済み
    PREPARING = "preparing"         # 出荷準備中
    SHIPPED = "shipped"             # 出荷済み
    DELIVERED = "delivered"         # 配達完了
    CANCELLED = "cancelled"         # キャンセル済み


# ============================================================
# 注文明細: 注文内の個々の商品と数量
# ============================================================

@dataclass(frozen=True)
class OrderLineItem:
    """注文明細: 注文に含まれる1つの商品と数量、小計の組み合わせ

    注意: 「アイテム」ではなく「注文明細（OrderLineItem）」と呼ぶ。
    「アイテム」は曖昧（商品？カートの中身？）なので、ユビキタス言語で排除した。
    """
    product_id: ProductId
    product_name: str      # 注文時点の商品名を保持（後から商品名が変わっても影響しない）
    unit_price: Money      # 注文時点の単価を保持
    quantity: Quantity

    @property
    def subtotal(self) -> Money:
        """小計: 単価 × 数量"""
        return self.unit_price.multiply(self.quantity.value)


# ============================================================
# 注文: 購入者が商品の購入を確定した取引（集約ルート）
# ============================================================

@dataclass
class Order:
    """注文: ECサイトにおける購入取引を表す集約ルート

    注文は複数の注文明細を含み、注文全体の整合性を保証する。
    """
    order_id: OrderId
    buyer_id: BuyerId
    line_items: list[OrderLineItem]
    status: OrderStatus = OrderStatus.PLACED
    placed_at: datetime = field(default_factory=datetime.now)
    cancelled_at: datetime | None = None

    @classmethod
    def place(cls, order_id: OrderId, buyer_id: BuyerId,
              line_items: list[OrderLineItem]) -> Order:
        """注文を確定する

        ビジネスルール: 注文には最低1つの注文明細が必要。
        """
        if not line_items:
            raise EmptyOrderError()
        return cls(order_id=order_id, buyer_id=buyer_id, line_items=line_items)

    def cancel_before_shipment(self) -> None:
        """出荷前キャンセルを行う

        ビジネスルール: 注文確定済み（PLACED）の場合のみキャンセル可能。
        出荷準備中以降はキャンセルできない。
        """
        if self.status != OrderStatus.PLACED:
            raise OrderCancellationError(
                order_id=self.order_id,
                reason=f"注文ステータスが '{self.status.value}' のためキャンセルできません。"
                       f"出荷前（placed）の注文のみキャンセル可能です。"
            )
        self.status = OrderStatus.CANCELLED
        self.cancelled_at = datetime.now()

    @property
    def total_amount(self) -> Money:
        """合計金額: すべての注文明細の小計を合算する"""
        total = Money(amount=0)
        for item in self.line_items:
            total = total.add(item.subtotal)
        return total

    @property
    def is_cancellable(self) -> bool:
        """キャンセル可能かどうか: 出荷前の注文のみtrue"""
        return self.status == OrderStatus.PLACED


# ============================================================
# ドメイン例外: ビジネスルール違反を明確に表現する
# ============================================================

class NegativeMoneyError(Exception):
    """金額がマイナスである場合のエラー"""
    def __init__(self, amount: int):
        super().__init__(f"金額は0以上である必要があります: {amount}円")


class InvalidQuantityError(Exception):
    """数量が不正である場合のエラー"""
    def __init__(self, value: int):
        super().__init__(f"数量は1以上である必要があります: {value}")


class EmptyOrderError(Exception):
    """注文明細が空の注文を確定しようとした場合のエラー"""
    def __init__(self):
        super().__init__("注文には最低1つの注文明細が必要です")


class OrderCancellationError(Exception):
    """注文キャンセルが許可されない場合のエラー"""
    def __init__(self, order_id: OrderId, reason: str):
        super().__init__(f"注文 {order_id} のキャンセルに失敗しました。理由: {reason}")


class InsufficientStockError(Exception):
    """在庫不足エラー: 要求数量に対して在庫が足りない"""
    def __init__(self, product_id: ProductId, requested: Quantity, available: int):
        super().__init__(
            f"商品 {product_id} の在庫が不足しています。"
            f"要求: {requested.value}個、在庫: {available}個"
        )
