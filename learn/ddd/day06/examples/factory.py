"""
==========================================================
Day 6 サンプルコード: ファクトリパターン（Factory Pattern）
==========================================================

このファイルでは、注文集約のファクトリを実装する。

構成:
  - OrderFactory（ファクトリクラス）
    - 新規注文の作成
    - カートからの注文作成
    - 永続化データからの再構築（リポジトリが使用）

学習ポイント:
  1. 新規作成（Creation）と再構築（Reconstitution）の区別
  2. 複雑な生成ロジックのカプセル化
  3. ファクトリメソッド vs ファクトリクラス
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Optional

# aggregate.py から集約と値オブジェクトをインポート
from aggregate import (
    DomainEvent,
    Money,
    Order,
    OrderCreated,
    OrderId,
    OrderLine,
    OrderLineId,
    OrderStatus,
    Quantity,
)


# ==========================================================
# カート（注文の元になるデータ構造）
# ==========================================================

@dataclass
class CartItem:
    """カート内の商品（注文ファクトリへの入力データ）"""
    product_id: str
    product_name: str
    unit_price: int  # 円単位
    quantity: int


@dataclass
class Cart:
    """
    ショッピングカート

    ★ カートと注文は別の集約（別のBounded Context の可能性もある）
    ★ ファクトリがカートから注文への変換を担当する
    """
    customer_id: str
    items: list[CartItem] = field(default_factory=list)

    def add_item(self, item: CartItem) -> None:
        self.items.append(item)

    @property
    def is_empty(self) -> bool:
        return len(self.items) == 0


# ==========================================================
# ファクトリクラス
# ==========================================================

class OrderFactory:
    """
    注文集約のファクトリ

    【責務】
    - 新規注文の作成（複数のパターンに対応）
    - 永続化データからの集約再構築

    【新規作成 vs 再構築の違い】
    - 新規作成: IDを生成、不変条件チェック、ドメインイベント記録
    - 再構築: 既存IDを使用、チェック省略、イベント記録なし
    """

    def create_new_order(
        self,
        customer_id: str,
        items: list[dict[str, Any]],
    ) -> Order:
        """
        新規注文を作成する

        Args:
            customer_id: 顧客ID
            items: 商品情報のリスト
                   各要素は {"product_id", "product_name",
                            "unit_price", "quantity"} を持つ

        Returns:
            作成された Order 集約（OrderCreated イベント付き）
        """
        order_id = OrderId.generate()
        order = Order(order_id=order_id, customer_id=customer_id)

        for item in items:
            order.add_item(
                product_id=item["product_id"],
                product_name=item["product_name"],
                unit_price=Money(amount=item["unit_price"]),
                quantity=Quantity(value=item["quantity"]),
            )

        # 新規作成なので OrderCreated イベントを記録
        order._record_event(OrderCreated(
            order_id=str(order_id),
            customer_id=customer_id,
        ))

        return order

    def create_from_cart(self, cart: Cart) -> Order:
        """
        ショッピングカートから注文を作成する

        ★ カートと注文は異なるドメイン概念
        ★ ファクトリがその変換ロジックを担当する

        Args:
            cart: ショッピングカート

        Returns:
            作成された Order 集約

        Raises:
            ValueError: カートが空の場合
        """
        if cart.is_empty:
            raise ValueError("空のカートから注文を作成できません")

        items = [
            {
                "product_id": item.product_id,
                "product_name": item.product_name,
                "unit_price": item.unit_price,
                "quantity": item.quantity,
            }
            for item in cart.items
        ]

        return self.create_new_order(
            customer_id=cart.customer_id,
            items=items,
        )

    def reconstruct(self, data: dict[str, Any]) -> Order:
        """
        永続化データから注文集約を再構築する

        ★ リポジトリの内部で使用される
        ★ データベースから読み込んだデータを Order 集約に変換する
        ★ ドメインイベントは記録しない（過去のイベントを再発行しない）
        ★ バリデーションは最小限（データベースのデータは信頼する）

        Args:
            data: 永続化データの辞書
                  {
                      "id": "ORD-xxxx",
                      "customer_id": "CUST-001",
                      "status": "confirmed",
                      "created_at": "2025-02-14T10:00:00",
                      "confirmed_at": "2025-02-14T10:05:00",
                      "lines": [
                          {
                              "line_id": "LINE-xxxx",
                              "product_id": "PROD-001",
                              "product_name": "コーヒー豆",
                              "unit_price": 1980,
                              "quantity": 2,
                          },
                          ...
                      ]
                  }

        Returns:
            再構築された Order 集約（イベントなし）
        """
        # Order オブジェクトをコンストラクタをバイパスして作成
        order = object.__new__(Order)

        # 内部状態を直接設定する
        order._id = OrderId(data["id"])
        order._customer_id = data["customer_id"]
        order._status = OrderStatus(data["status"])
        order._created_at = datetime.fromisoformat(data["created_at"])
        order._confirmed_at = (
            datetime.fromisoformat(data["confirmed_at"])
            if data.get("confirmed_at")
            else None
        )
        order._domain_events = []  # ★ 再構築時はイベントなし

        # OrderLine を再構築
        order._lines = []
        for line_data in data.get("lines", []):
            line = object.__new__(OrderLine)
            line._line_id = OrderLineId(line_data["line_id"])
            line._product_id = line_data["product_id"]
            line._product_name = line_data["product_name"]
            line._unit_price = Money(amount=line_data["unit_price"])
            line._quantity = Quantity(value=line_data["quantity"])
            order._lines.append(line)

        return order


# ==========================================================
# 使用例
# ==========================================================

def main() -> None:
    """ファクトリパターンの使用例デモ"""

    print("=" * 60)
    print("【ファクトリパターン（Factory Pattern）のデモ】")
    print("=" * 60)

    factory = OrderFactory()

    # --- パターン1: 直接的な新規作成 ---
    print("\n1. 新規注文の作成（create_new_order）:")
    order1 = factory.create_new_order(
        customer_id="CUST-001",
        items=[
            {
                "product_id": "PROD-001",
                "product_name": "プレミアムコーヒー豆 200g",
                "unit_price": 1980,
                "quantity": 2,
            },
            {
                "product_id": "PROD-002",
                "product_name": "オーガニック紅茶 100g",
                "unit_price": 1500,
                "quantity": 1,
            },
        ],
    )
    print(f"   作成された注文: {order1}")
    print(f"   ドメインイベント数: {len(order1.domain_events)}")

    # --- パターン2: カートからの作成 ---
    print("\n2. カートからの注文作成（create_from_cart）:")
    cart = Cart(customer_id="CUST-002")
    cart.add_item(CartItem(
        product_id="PROD-003",
        product_name="抹茶パウダー 50g",
        unit_price=2500,
        quantity=1,
    ))
    cart.add_item(CartItem(
        product_id="PROD-004",
        product_name="ほうじ茶ラテの素 100g",
        unit_price=800,
        quantity=3,
    ))
    order2 = factory.create_from_cart(cart)
    print(f"   カートから作成: {order2}")
    print(f"   合計金額: {order2.total_amount}")

    # --- パターン3: 永続化データからの再構築 ---
    print("\n3. 永続化データからの再構築（reconstruct）:")
    persisted_data = {
        "id": "ORD-ABC123DEF456",
        "customer_id": "CUST-001",
        "status": "confirmed",
        "created_at": "2025-02-14T10:00:00",
        "confirmed_at": "2025-02-14T10:05:00",
        "lines": [
            {
                "line_id": "LINE-11111111",
                "product_id": "PROD-001",
                "product_name": "プレミアムコーヒー豆 200g",
                "unit_price": 1980,
                "quantity": 2,
            },
            {
                "line_id": "LINE-22222222",
                "product_id": "PROD-002",
                "product_name": "オーガニック紅茶 100g",
                "unit_price": 1500,
                "quantity": 1,
            },
        ],
    }
    order3 = factory.reconstruct(persisted_data)
    print(f"   再構築された注文: {order3}")
    print(f"   ステータス: {order3.status.value}")
    print(f"   合計金額: {order3.total_amount}")
    print(f"   ドメインイベント数: {len(order3.domain_events)}")
    print(f"   ★ 再構築ではイベントは記録されない → 0件")

    # --- 新規作成 vs 再構築の比較 ---
    print("\n" + "=" * 60)
    print("✅ ファクトリのポイント:")
    print("  1. 新規作成: ID生成 + バリデーション + イベント記録")
    print("  2. 再構築: 既存ID使用 + チェック省略 + イベントなし")
    print("  3. カートからの変換など、複雑な生成ロジックをカプセル化")
    print("  4. ファクトリメソッド: 集約自身にclassmethodで定義（単純な場合）")
    print("  5. ファクトリクラス: 独立クラスとして定義（複雑な場合）")
    print("=" * 60)


if __name__ == "__main__":
    main()
