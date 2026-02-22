"""
==========================================================
正しいパターン: 境界づけられたコンテキストで分割した場合
==========================================================

同じECサイトを Bounded Context で適切に分割した例。
各コンテキストが独自のモデルを持ち、必要な属性だけを管理します。

それぞれのコンテキスト内では:
- モデルがシンプルで理解しやすい
- ユビキタス言語が一貫している
- 独立してテスト・デプロイ可能
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4


# ==========================================================
# カタログコンテキスト（Catalog Context）
# 関心事: 商品を魅力的に見せること
# ==========================================================

class CatalogProductStatus(Enum):
    """カタログにおける商品の状態（公開管理のみ）"""
    DRAFT = "draft"
    PUBLISHED = "published"
    UNPUBLISHED = "unpublished"


@dataclass
class CatalogProduct:
    """
    カタログコンテキストの「商品」

    このコンテキストでの関心事:
    - 顧客にどう見せるか（名前、説明、画像）
    - どのカテゴリに属するか
    - 表示価格はいくらか
    """
    id: str
    name: str
    description: str
    price: float
    images: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    brand: str = ""
    status: CatalogProductStatus = CatalogProductStatus.DRAFT

    def publish(self) -> None:
        """カタログに公開する"""
        if not self.name or not self.description:
            raise ValueError("商品名と説明は必須です")
        if self.price <= 0:
            raise ValueError("価格は0より大きい必要があります")
        # ✅ カタログの公開は在庫に依存しない
        # 在庫切れでも「近日入荷」として公開できる
        self.status = CatalogProductStatus.PUBLISHED

    def unpublish(self) -> None:
        """カタログから非公開にする"""
        self.status = CatalogProductStatus.UNPUBLISHED

    def is_visible(self) -> bool:
        """顧客に表示可能か"""
        return self.status == CatalogProductStatus.PUBLISHED


# ==========================================================
# 在庫コンテキスト（Inventory Context）
# 関心事: 在庫を正確に管理すること
# ==========================================================

@dataclass
class InventoryItem:
    """
    在庫コンテキストの「商品」（ここでは InventoryItem と呼ぶ）

    このコンテキストでの関心事:
    - 今いくつあるか
    - どこに保管されているか
    - いつ発注すべきか

    ✅ 注目: カタログでは Product だが、ここでは InventoryItem
    コンテキストに適した名前を使う
    """
    sku: str
    product_id: str  # カタログコンテキストとの紐付け用
    quantity_on_hand: int = 0
    warehouse_location: str = ""
    reorder_point: int = 0
    safety_stock: int = 0

    def is_available(self, requested_quantity: int) -> bool:
        """要求数量の在庫があるか確認する"""
        return self.quantity_on_hand >= requested_quantity

    def reserve(self, quantity: int) -> "StockReservation":
        """在庫を引き当てる（予約する）"""
        if not self.is_available(quantity):
            raise InsufficientStockError(
                f"在庫不足: SKU={self.sku}, "
                f"要求={quantity}, 在庫={self.quantity_on_hand}"
            )
        self.quantity_on_hand -= quantity
        # ✅ 在庫引当の結果を StockReservation として返す
        # カタログの状態には一切触れない
        return StockReservation(
            reservation_id=str(uuid4()),
            sku=self.sku,
            quantity=quantity,
            reserved_at=datetime.now(),
        )

    def receive(self, quantity: int) -> None:
        """入荷を記録する"""
        if quantity <= 0:
            raise ValueError("入荷数量は正の数である必要があります")
        self.quantity_on_hand += quantity

    def needs_reorder(self) -> bool:
        """発注が必要か判定する"""
        return self.quantity_on_hand <= self.reorder_point


@dataclass
class StockReservation:
    """在庫引当の結果を表す値オブジェクト"""
    reservation_id: str
    sku: str
    quantity: int
    reserved_at: datetime


class InsufficientStockError(Exception):
    """在庫不足を表すドメイン例外"""
    pass


# ==========================================================
# 注文コンテキスト（Order Context）
# 関心事: 注文を正確に処理すること
# ==========================================================

class OrderStatus(Enum):
    """注文の状態"""
    PENDING = "pending"        # 確認中
    CONFIRMED = "confirmed"    # 確定
    CANCELLED = "cancelled"    # キャンセル


@dataclass
class OrderLine:
    """注文明細行 — 注文コンテキストでの「商品」の表現"""
    product_id: str
    product_name: str  # 注文時点のスナップショット
    unit_price: float  # 注文時点の価格
    quantity: int
    tax_rate: float = 0.10

    @property
    def subtotal(self) -> float:
        """税抜き小計"""
        return self.unit_price * self.quantity

    @property
    def tax_amount(self) -> float:
        """税額"""
        return self.subtotal * self.tax_rate

    @property
    def total(self) -> float:
        """税込み合計"""
        return self.subtotal + self.tax_amount


@dataclass
class Order:
    """
    注文コンテキストの「注文」

    ✅ 注目: 注文は Product そのものを持たない
    注文時点の「商品名」「価格」のスナップショットを持つ
    （商品の価格が後から変わっても注文金額は変わらない）
    """
    id: str
    customer_id: str
    lines: list[OrderLine] = field(default_factory=list)
    status: OrderStatus = OrderStatus.PENDING
    ordered_at: Optional[datetime] = None

    def add_line(self, line: OrderLine) -> None:
        """注文明細を追加する"""
        self.lines.append(line)

    def confirm(self) -> None:
        """注文を確定する"""
        if not self.lines:
            raise ValueError("注文明細が空です")
        self.status = OrderStatus.CONFIRMED
        self.ordered_at = datetime.now()

    def cancel(self) -> None:
        """注文をキャンセルする"""
        if self.status != OrderStatus.PENDING:
            raise ValueError("確認中の注文のみキャンセル可能です")
        self.status = OrderStatus.CANCELLED

    @property
    def total_amount(self) -> float:
        """注文合計金額"""
        return sum(line.total for line in self.lines)


# ==========================================================
# 配送コンテキスト（Shipping Context）
# 関心事: 荷物を確実に届けること
# ==========================================================

class ShipmentStatus(Enum):
    """配送の状態"""
    PREPARING = "preparing"    # 準備中
    SHIPPED = "shipped"        # 出荷済み
    DELIVERED = "delivered"    # 配達完了


@dataclass
class ShippingItem:
    """配送コンテキストでの「商品」— 荷物としての側面のみ"""
    product_id: str
    weight_kg: float
    width_cm: float = 0.0
    height_cm: float = 0.0
    depth_cm: float = 0.0
    is_fragile: bool = False
    is_hazardous: bool = False


@dataclass
class Recipient:
    """
    配送コンテキストでの「顧客」— 届け先としての側面のみ

    ✅ 注目: 販売コンテキストの Customer とは異なるモデル
    ここでは「どこに届けるか」だけが関心事
    """
    name: str
    postal_code: str
    address: str
    phone_number: str
    delivery_preference: str = "anytime"
    access_instructions: str = ""


@dataclass
class Shipment:
    """配送コンテキストの「出荷」"""
    id: str
    order_id: str  # 注文コンテキストとの紐付け
    recipient: Recipient
    items: list[ShippingItem] = field(default_factory=list)
    status: ShipmentStatus = ShipmentStatus.PREPARING
    tracking_number: Optional[str] = None

    @property
    def total_weight(self) -> float:
        """総重量"""
        return sum(item.weight_kg for item in self.items)

    @property
    def has_fragile_items(self) -> bool:
        """壊れ物を含むか"""
        return any(item.is_fragile for item in self.items)

    def calculate_shipping_cost(self) -> float:
        """配送料を計算する"""
        base_cost = 500.0
        weight = self.total_weight
        if weight > 10:
            base_cost += (weight - 10) * 100
        if self.has_fragile_items:
            base_cost += 300
        return base_cost

    def ship(self, tracking_number: str) -> None:
        """出荷する"""
        self.tracking_number = tracking_number
        self.status = ShipmentStatus.SHIPPED

    def deliver(self) -> None:
        """配達完了を記録する"""
        self.status = ShipmentStatus.DELIVERED


# ==========================================================
# 販売コンテキスト（Sales Context）
# 関心事: 顧客の購買力とロイヤルティ管理
# ==========================================================

class LoyaltyRank(Enum):
    """ロイヤルティランク"""
    BRONZE = "bronze"
    SILVER = "silver"
    GOLD = "gold"
    PLATINUM = "platinum"


@dataclass
class SalesCustomer:
    """
    販売コンテキストの「顧客」

    ✅ 配送コンテキストの Recipient とは別物
    ここでは「どのくらい買ってくれるか」が関心事
    """
    id: str
    name: str
    loyalty_rank: LoyaltyRank = LoyaltyRank.BRONZE
    total_purchase_amount: float = 0.0
    credit_limit: float = 100000.0

    def discount_rate(self) -> float:
        """ロイヤルティランクに基づく割引率"""
        rates = {
            LoyaltyRank.BRONZE: 0.0,
            LoyaltyRank.SILVER: 0.03,
            LoyaltyRank.GOLD: 0.05,
            LoyaltyRank.PLATINUM: 0.10,
        }
        return rates[self.loyalty_rank]

    def can_purchase(self, amount: float) -> bool:
        """与信枠内か確認する"""
        return amount <= self.credit_limit

    def record_purchase(self, amount: float) -> None:
        """購入を記録し、ランクを更新する"""
        self.total_purchase_amount += amount
        self._update_rank()

    def _update_rank(self) -> None:
        """累計購入額に基づくランク自動更新"""
        if self.total_purchase_amount >= 1000000:
            self.loyalty_rank = LoyaltyRank.PLATINUM
        elif self.total_purchase_amount >= 500000:
            self.loyalty_rank = LoyaltyRank.GOLD
        elif self.total_purchase_amount >= 100000:
            self.loyalty_rank = LoyaltyRank.SILVER


# ==========================================================
# コンテキスト間の連携（アプリケーションサービス層）
# ==========================================================

class PlaceOrderUseCase:
    """
    注文ユースケース — 複数コンテキストを協調させる

    ✅ 各コンテキストのサービスを呼び出すが、
       各コンテキストの内部ロジックには立ち入らない。
    ✅ 各コンテキストは自分の責務だけを果たす。
    """

    def __init__(
        self,
        catalog_product: CatalogProduct,
        inventory_item: InventoryItem,
        sales_customer: SalesCustomer,
        recipient: Recipient,
        shipping_item: ShippingItem,
    ) -> None:
        # 本来は各コンテキストのリポジトリ経由で取得するが、
        # 学習用に直接渡している
        self.catalog_product = catalog_product
        self.inventory_item = inventory_item
        self.sales_customer = sales_customer
        self.recipient = recipient
        self.shipping_item = shipping_item

    def execute(self, quantity: int) -> dict:
        """注文を実行する"""

        # 1. カタログコンテキスト: 商品が公開中か確認
        if not self.catalog_product.is_visible():
            raise ValueError("この商品は現在購入できません")

        # 2. 在庫コンテキスト: 在庫を引き当てる
        reservation = self.inventory_item.reserve(quantity)

        # 3. 注文コンテキスト: 注文を作成する
        order = Order(id=str(uuid4()), customer_id=self.sales_customer.id)
        order.add_line(OrderLine(
            product_id=self.catalog_product.id,
            product_name=self.catalog_product.name,  # スナップショット
            unit_price=self.catalog_product.price,    # スナップショット
            quantity=quantity,
            tax_rate=0.08,  # 食品の軽減税率
        ))

        # 4. 販売コンテキスト: 与信チェックと割引計算
        if not self.sales_customer.can_purchase(order.total_amount):
            # ✅ 在庫引当を戻す処理が必要（Saga パターン）
            # 学習用のため簡略化
            raise ValueError("与信枠を超えています")

        discount_rate = self.sales_customer.discount_rate()
        discount_amount = order.total_amount * discount_rate

        # 5. 配送コンテキスト: 配送を準備する
        shipment = Shipment(
            id=str(uuid4()),
            order_id=order.id,
            recipient=self.recipient,
            items=[self.shipping_item],
        )
        shipping_cost = shipment.calculate_shipping_cost()

        # 6. 注文を確定する
        order.confirm()

        # 7. 販売実績を記録する
        final_amount = order.total_amount - discount_amount + shipping_cost
        self.sales_customer.record_purchase(final_amount)

        return {
            "order_id": order.id,
            "reservation_id": reservation.reservation_id,
            "shipment_id": shipment.id,
            "subtotal": order.total_amount,
            "discount": discount_amount,
            "shipping_cost": shipping_cost,
            "total": final_amount,
            "customer_rank": self.sales_customer.loyalty_rank.value,
        }


# ==========================================================
# 使用例 — Bounded Context 分割のメリットを実感する
# ==========================================================

def main() -> None:
    """Bounded Context で分割された設計のデモ"""

    # ✅ 各コンテキストが自分に必要な情報だけを持つ

    # カタログコンテキスト: 顧客に見せる商品情報
    catalog_product = CatalogProduct(
        id="PROD-001",
        name="プレミアムコーヒー豆 200g",
        description="厳選されたアラビカ種100%",
        price=1980.0,
        images=["coffee_main.jpg", "coffee_detail.jpg"],
        categories=["飲料", "コーヒー"],
        brand="Premium Roast",
        status=CatalogProductStatus.PUBLISHED,
    )

    # 在庫コンテキスト: 倉庫での管理情報
    inventory_item = InventoryItem(
        sku="SKU-COFFEE-001",
        product_id="PROD-001",
        quantity_on_hand=50,
        warehouse_location="A-3-12",
        reorder_point=10,
        safety_stock=5,
    )

    # 販売コンテキスト: 購買力の管理
    sales_customer = SalesCustomer(
        id="CUST-001",
        name="山田太郎",
        loyalty_rank=LoyaltyRank.GOLD,
        total_purchase_amount=250000.0,
        credit_limit=500000.0,
    )

    # 配送コンテキスト: 届け先情報
    recipient = Recipient(
        name="山田太郎",
        postal_code="150-0001",
        address="東京都渋谷区神宮前1-1-1",
        phone_number="090-1234-5678",
        delivery_preference="evening",
    )

    # 配送コンテキスト: 荷物としての商品情報
    shipping_item = ShippingItem(
        product_id="PROD-001",
        weight_kg=0.25,
        is_fragile=False,
    )

    # 注文を実行
    use_case = PlaceOrderUseCase(
        catalog_product=catalog_product,
        inventory_item=inventory_item,
        sales_customer=sales_customer,
        recipient=recipient,
        shipping_item=shipping_item,
    )

    result = use_case.execute(quantity=3)

    print("=" * 60)
    print("【Bounded Context 分割後の注文結果】")
    print("=" * 60)
    for key, value in result.items():
        print(f"  {key}: {value}")

    print("\n✅ この設計のメリット:")
    print("  1. 各コンテキストのモデルがシンプルで理解しやすい")
    print("  2. カタログの状態と在庫の状態が独立している")
    print("  3. 各コンテキストを独立してテスト可能")
    print("  4. チームが独立して開発・デプロイできる")
    print("  5. ユビキタス言語がコンテキスト内で一貫している")
    print("     - カタログ: Product（見せるもの）")
    print("     - 在庫: InventoryItem（管理するもの）")
    print("     - 配送: ShippingItem（届けるもの）")
    print("     - 注文: OrderLine（注文の明細）")

    print("\n✅ コンテキスト間の連携:")
    print("  - product_id で緩く紐付け（直接参照しない）")
    print("  - 各コンテキストが自分の責務だけを果たす")
    print("  - アプリケーションサービスが協調を担当する")


if __name__ == "__main__":
    main()
