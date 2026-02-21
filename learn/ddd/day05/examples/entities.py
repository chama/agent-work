"""
Day 5: エンティティ（Entity）の実装例

エンティティの2つの実装パターンを示す:
1. User - ユーザーエンティティ（ID生成、等価性、ライフサイクル）
2. Order - 注文エンティティ（状態遷移、ビジネスルール）
"""

from __future__ import annotations

import uuid
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional

from value_objects import EmailAddress, Money


# ==============================================================================
# ID値オブジェクト（エンティティのIDも値オブジェクトとして定義するのがベストプラクティス）
# ==============================================================================


@dataclass(frozen=True)
class UserId:
    """ユーザーIDを表す値オブジェクト"""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("ユーザーIDは空にできません")

    @staticmethod
    def generate() -> UserId:
        """新しいユーザーIDを生成する（UUID v4を使用）"""
        return UserId(value=str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value


@dataclass(frozen=True)
class OrderId:
    """注文IDを表す値オブジェクト"""

    value: str

    def __post_init__(self) -> None:
        if not self.value:
            raise ValueError("注文IDは空にできません")

    @staticmethod
    def generate() -> OrderId:
        """新しい注文IDを生成する"""
        return OrderId(value=str(uuid.uuid4()))

    def __str__(self) -> str:
        return self.value


# ==============================================================================
# 1. User エンティティ
# ==============================================================================


class User:
    """
    ユーザーエンティティ。

    - UserIdによって一意に識別される
    - 名前やメールアドレスが変わっても、同じUserIdなら同一人物
    - ビジネスルール（バリデーション）をエンティティ内に持つ
    """

    def __init__(self, user_id: UserId, name: str, email: EmailAddress) -> None:
        """
        ユーザーを生成する。

        Args:
            user_id: ユーザーID（必須）
            name: ユーザー名
            email: メールアドレス
        """
        self._user_id = user_id
        self._name = name
        self._email = email
        self._is_active = True
        self._created_at = datetime.now()
        self._updated_at = datetime.now()

    # --- プロパティ（読み取り専用） ---

    @property
    def user_id(self) -> UserId:
        return self._user_id

    @property
    def name(self) -> str:
        return self._name

    @property
    def email(self) -> EmailAddress:
        return self._email

    @property
    def is_active(self) -> bool:
        return self._is_active

    # --- ビジネスロジック ---

    def change_name(self, new_name: str) -> None:
        """名前を変更する"""
        if not new_name or len(new_name.strip()) == 0:
            raise ValueError("名前は空にできません")
        if len(new_name) > 100:
            raise ValueError("名前は100文字以内にしてください")
        self._name = new_name
        self._updated_at = datetime.now()

    def change_email(self, new_email: EmailAddress) -> None:
        """メールアドレスを変更する"""
        self._email = new_email
        self._updated_at = datetime.now()

    def deactivate(self) -> None:
        """ユーザーを無効化する"""
        if not self._is_active:
            raise ValueError("既に無効化されています")
        self._is_active = False
        self._updated_at = datetime.now()

    def reactivate(self) -> None:
        """ユーザーを再有効化する"""
        if self._is_active:
            raise ValueError("既に有効です")
        self._is_active = True
        self._updated_at = datetime.now()

    # --- 等価性: IDのみで比較 ---

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, User):
            return False
        return self._user_id == other._user_id

    def __hash__(self) -> int:
        return hash(self._user_id)

    def __repr__(self) -> str:
        return f"User(id={self._user_id}, name={self._name}, email={self._email})"


# ==============================================================================
# 2. Order エンティティ（状態遷移付き）
# ==============================================================================


class OrderStatus(Enum):
    """注文のステータスを表す列挙型"""

    DRAFT = "draft"  # 下書き
    CONFIRMED = "confirmed"  # 確定済み
    PAID = "paid"  # 支払い済み
    SHIPPED = "shipped"  # 発送済み
    COMPLETED = "completed"  # 完了
    CANCELLED = "cancelled"  # キャンセル


@dataclass
class OrderItem:
    """注文明細（値オブジェクト）"""

    product_name: str
    unit_price: Money
    quantity: int

    def __post_init__(self) -> None:
        if self.quantity <= 0:
            raise ValueError("数量は1以上である必要があります")

    @property
    def subtotal(self) -> Money:
        """小計を計算する"""
        return self.unit_price.multiply(self.quantity)


class Order:
    """
    注文エンティティ。

    - OrderIdによって一意に識別される
    - 状態遷移のルールをエンティティ内に持つ
    - 不正な状態遷移を防ぐ
    """

    def __init__(self, order_id: OrderId, customer_id: UserId) -> None:
        self._order_id = order_id
        self._customer_id = customer_id
        self._items: list[OrderItem] = []
        self._status = OrderStatus.DRAFT
        self._created_at = datetime.now()
        self._note: Optional[str] = None

    # --- プロパティ ---

    @property
    def order_id(self) -> OrderId:
        return self._order_id

    @property
    def status(self) -> OrderStatus:
        return self._status

    @property
    def items(self) -> list[OrderItem]:
        return list(self._items)  # 防御的コピーを返す

    @property
    def total_amount(self) -> Money:
        """注文合計金額を計算する"""
        if not self._items:
            return Money(0, "JPY")
        total = self._items[0].subtotal
        for item in self._items[1:]:
            total = total.add(item.subtotal)
        return total

    # --- ビジネスロジック ---

    def add_item(self, item: OrderItem) -> None:
        """注文に商品を追加する（下書き状態のみ可能）"""
        if self._status != OrderStatus.DRAFT:
            raise ValueError("下書き状態の注文にのみ商品を追加できます")
        self._items.append(item)

    def remove_item(self, product_name: str) -> None:
        """注文から商品を削除する（下書き状態のみ可能）"""
        if self._status != OrderStatus.DRAFT:
            raise ValueError("下書き状態の注文からのみ商品を削除できます")
        self._items = [i for i in self._items if i.product_name != product_name]

    def confirm(self) -> None:
        """注文を確定する"""
        if self._status != OrderStatus.DRAFT:
            raise ValueError("下書き状態の注文のみ確定できます")
        if not self._items:
            raise ValueError("商品が1つもない注文は確定できません")
        self._status = OrderStatus.CONFIRMED

    def pay(self) -> None:
        """支払いを記録する"""
        if self._status != OrderStatus.CONFIRMED:
            raise ValueError("確定済みの注文のみ支払い可能です")
        self._status = OrderStatus.PAID

    def ship(self) -> None:
        """発送を記録する"""
        if self._status != OrderStatus.PAID:
            raise ValueError("支払い済みの注文のみ発送可能です")
        self._status = OrderStatus.SHIPPED

    def complete(self) -> None:
        """注文を完了する"""
        if self._status != OrderStatus.SHIPPED:
            raise ValueError("発送済みの注文のみ完了にできます")
        self._status = OrderStatus.COMPLETED

    def cancel(self) -> None:
        """注文をキャンセルする（完了・キャンセル済み以外で可能）"""
        if self._status in (OrderStatus.COMPLETED, OrderStatus.CANCELLED):
            raise ValueError("完了済みまたはキャンセル済みの注文はキャンセルできません")
        self._status = OrderStatus.CANCELLED

    # --- 等価性: IDのみで比較 ---

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, Order):
            return False
        return self._order_id == other._order_id

    def __hash__(self) -> int:
        return hash(self._order_id)

    def __repr__(self) -> str:
        return (
            f"Order(id={self._order_id}, status={self._status.value}, "
            f"items={len(self._items)}, total={self.total_amount})"
        )


# ==============================================================================
# 使用例
# ==============================================================================

if __name__ == "__main__":
    # --- User エンティティの使用例 ---
    print("=== User エンティティ ===")
    user_id = UserId.generate()
    user = User(user_id, "田中太郎", EmailAddress("tanaka@example.com"))
    print(f"作成: {user}")

    # 名前を変更しても同一人物
    user.change_name("田中一郎")
    print(f"名前変更後: {user}")

    # IDが同じなら等価（エンティティの等価性）
    same_user = User(user_id, "別の名前", EmailAddress("other@example.com"))
    print(f"同じIDのユーザーは等価: {user == same_user}")  # True

    # --- Order エンティティの使用例 ---
    print("\n=== Order エンティティ ===")
    order_id = OrderId.generate()
    customer_id = UserId.generate()
    order = Order(order_id, customer_id)

    # 商品を追加
    order.add_item(OrderItem("DDDの本", Money(3000, "JPY"), 1))
    order.add_item(OrderItem("ノート", Money(500, "JPY"), 3))
    print(f"注文: {order}")

    # 状態遷移: 下書き → 確定 → 支払い → 発送 → 完了
    order.confirm()
    print(f"確定後: {order}")

    order.pay()
    print(f"支払い後: {order}")

    order.ship()
    print(f"発送後: {order}")

    order.complete()
    print(f"完了: {order}")
