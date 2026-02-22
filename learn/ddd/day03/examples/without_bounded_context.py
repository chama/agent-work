"""
==========================================================
アンチパターン: 境界づけられたコンテキストを使わない場合
==========================================================

ECサイトにおいて、1つの「統一モデル」で
カタログ・在庫・注文・配送のすべてのコンテキストを
カバーしようとした例。

このコードは「こうしてはいけない」という教材です。
問題点をコメントで解説しています。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional


# ==========================================================
# 問題1: あらゆるコンテキストの状態を1つの Enum に詰め込んでいる
# ==========================================================

class ProductStatus(Enum):
    """商品の状態 — 全コンテキストの状態が混在している"""
    # カタログコンテキストの状態
    DRAFT = "draft"                    # 下書き（カタログ）
    PUBLISHED = "published"            # 公開中（カタログ）
    UNPUBLISHED = "unpublished"        # 非公開（カタログ）

    # 在庫コンテキストの状態
    IN_STOCK = "in_stock"              # 在庫あり（在庫）
    OUT_OF_STOCK = "out_of_stock"      # 在庫切れ（在庫）
    BACKORDERED = "backordered"        # 入荷待ち（在庫）

    # 配送コンテキストの状態
    READY_TO_SHIP = "ready_to_ship"    # 出荷準備完了（配送）
    SHIPPED = "shipped"                # 出荷済み（配送）

    # ⚠️ 問題: 状態遷移のルールが不明瞭
    # DRAFT → PUBLISHED は可能だが、DRAFT → SHIPPED は可能？
    # ProductStatus だけでは判断できない


# ==========================================================
# 問題2: God Object — あらゆるコンテキストの属性が1つのクラスに
# ==========================================================

@dataclass
class Product:
    """
    全コンテキストの要件を1つのクラスに詰め込んだ「神オブジェクト」

    ⚠️ 問題点:
    - 40以上の属性を持ち、全容を把握するのが困難
    - カタログチームの変更が在庫ロジックを壊すリスク
    - どの属性がどのコンテキストで使われるか不明瞭
    - テストが肥大化する
    """

    # --- 基本情報（全コンテキスト共通のつもり）---
    id: str = ""
    name: str = ""
    status: ProductStatus = ProductStatus.DRAFT

    # --- カタログコンテキストの属性 ---
    description: str = ""
    long_description: str = ""
    images: list[str] = field(default_factory=list)
    categories: list[str] = field(default_factory=list)
    tags: list[str] = field(default_factory=list)
    brand: str = ""
    seo_title: str = ""
    seo_description: str = ""
    display_price: float = 0.0          # 表示価格
    discount_price: Optional[float] = None  # 割引価格
    is_featured: bool = False           # おすすめ商品か

    # --- 在庫コンテキストの属性 ---
    sku: str = ""
    stock_quantity: int = 0
    warehouse_location: str = ""
    reorder_point: int = 0              # 発注点
    safety_stock: int = 0               # 安全在庫
    lot_number: str = ""
    expiration_date: Optional[datetime] = None  # 賞味期限
    last_stock_check: Optional[datetime] = None

    # --- 注文コンテキストの属性 ---
    unit_price: float = 0.0             # 単価
    tax_rate: float = 0.1               # 税率
    max_order_quantity: int = 99
    min_order_quantity: int = 1

    # --- 配送コンテキストの属性 ---
    weight_kg: float = 0.0
    width_cm: float = 0.0
    height_cm: float = 0.0
    depth_cm: float = 0.0
    is_fragile: bool = False
    is_hazardous: bool = False
    shipping_class: str = "standard"
    customs_code: str = ""

    # --- 仕入コンテキストの属性 ---
    supplier_id: str = ""
    cost_price: float = 0.0             # 原価
    lead_time_days: int = 0             # 納入リードタイム

    # ==========================================================
    # 問題3: あらゆるコンテキストのビジネスロジックが混在
    # ==========================================================

    def publish(self) -> None:
        """カタログに公開する（カタログコンテキストのロジック）"""
        if not self.name or not self.description:
            raise ValueError("商品名と説明は必須です")
        if self.display_price <= 0:
            raise ValueError("価格は0より大きい必要があります")
        # ⚠️ 問題: カタログ公開時に在庫チェックが必要？
        # チームによって意見が割れる
        if self.stock_quantity <= 0:
            raise ValueError("在庫がない商品は公開できません")
        self.status = ProductStatus.PUBLISHED

    def check_stock(self, requested_quantity: int) -> bool:
        """在庫を確認する（在庫コンテキストのロジック）"""
        return self.stock_quantity >= requested_quantity

    def reserve_stock(self, quantity: int) -> None:
        """在庫を引き当てる（在庫コンテキストのロジック）"""
        if not self.check_stock(quantity):
            raise ValueError(f"在庫不足: 要求={quantity}, 在庫={self.stock_quantity}")
        self.stock_quantity -= quantity

        # ⚠️ 問題: 在庫が減ったことでカタログの表示も変わるべき？
        # 在庫0になったら自動的にステータスを変える？
        if self.stock_quantity == 0:
            self.status = ProductStatus.OUT_OF_STOCK
            # ↑ 在庫ロジックがカタログの状態を変更している！
            # これにより「公開中だが在庫切れ」という状態を表現できない

    def calculate_price(self, quantity: int) -> float:
        """注文金額を計算する（注文コンテキストのロジック）"""
        base = self.unit_price * quantity
        tax = base * self.tax_rate
        return base + tax

    def calculate_shipping_cost(self) -> float:
        """配送料を計算する（配送コンテキストのロジック）"""
        # ⚠️ 問題: 配送ロジックが商品クラスに含まれている
        base_cost = 500  # 基本送料
        if self.weight_kg > 10:
            base_cost += (self.weight_kg - 10) * 100
        if self.is_fragile:
            base_cost += 300
        if self.is_hazardous:
            base_cost += 1000
        return base_cost

    def needs_reorder(self) -> bool:
        """発注が必要か判定する（仕入コンテキストのロジック）"""
        return self.stock_quantity <= self.reorder_point

    def calculate_profit_margin(self) -> float:
        """利益率を計算する（会計コンテキストのロジック）"""
        if self.cost_price == 0:
            return 0.0
        return (self.unit_price - self.cost_price) / self.unit_price


# ==========================================================
# 問題4: 「顧客」も同様に God Object になる
# ==========================================================

@dataclass
class Customer:
    """
    全コンテキストの要件を1つに詰め込んだ顧客モデル

    ⚠️ 販売が知りたいこと（購買力）と
       配送が知りたいこと（届け先）が混在している
    """

    # --- 基本情報 ---
    id: str = ""
    name: str = ""
    email: str = ""

    # --- 販売コンテキスト ---
    loyalty_rank: str = "bronze"        # ロイヤルティランク
    total_purchase_amount: float = 0.0  # 累計購入額
    credit_limit: float = 100000.0      # 与信枠
    preferred_categories: list[str] = field(default_factory=list)

    # --- 配送コンテキスト ---
    delivery_addresses: list[dict] = field(default_factory=list)
    phone_number: str = ""
    delivery_preference: str = "anytime"  # 配達希望時間帯
    access_instructions: str = ""         # 配達時の注意事項

    # --- カスタマーサポートコンテキスト ---
    support_tickets: list[dict] = field(default_factory=list)
    satisfaction_score: Optional[float] = None
    is_vip: bool = False

    def calculate_discount_rate(self) -> float:
        """ロイヤルティランクに基づく割引率（販売ロジック）"""
        rates = {"bronze": 0.0, "silver": 0.03, "gold": 0.05, "platinum": 0.10}
        return rates.get(self.loyalty_rank, 0.0)

    def get_primary_delivery_address(self) -> dict:
        """メインの配送先を取得（配送ロジック）"""
        if not self.delivery_addresses:
            raise ValueError("配送先が登録されていません")
        return self.delivery_addresses[0]

    def can_purchase(self, amount: float) -> bool:
        """購入可能か判定（販売ロジック）"""
        return amount <= self.credit_limit

    def add_support_ticket(self, subject: str, description: str) -> None:
        """サポートチケット追加（CSロジック）"""
        self.support_tickets.append({
            "subject": subject,
            "description": description,
            "created_at": datetime.now().isoformat(),
            "status": "open",
        })


# ==========================================================
# 問題5: 全コンテキストが同じモデルを操作するサービス層
# ==========================================================

class UnifiedOrderService:
    """
    統一された注文サービス

    ⚠️ 問題:
    - カタログ、在庫、注文、配送、会計のロジックが混在
    - 1つの変更が全コンテキストに影響
    - テストが複雑（全コンテキストのモックが必要）
    - チーム間のコードコンフリクトが頻発
    """

    def place_order(
        self,
        customer: Customer,
        product: Product,
        quantity: int,
    ) -> dict:
        """注文を処理する — 全コンテキストのロジックが一箇所に"""

        # 1. カタログコンテキストのチェック
        if product.status != ProductStatus.PUBLISHED:
            raise ValueError("公開されていない商品は注文できません")

        # 2. 販売コンテキストのチェック
        order_amount = product.calculate_price(quantity)
        if not customer.can_purchase(order_amount):
            raise ValueError("与信枠を超えています")

        # 3. 在庫コンテキストの操作
        product.reserve_stock(quantity)

        # 4. 配送コンテキストの計算
        shipping_cost = product.calculate_shipping_cost()
        delivery_address = customer.get_primary_delivery_address()

        # 5. 販売コンテキストのポイント計算
        discount_rate = customer.calculate_discount_rate()
        discount_amount = order_amount * discount_rate

        # 6. 会計コンテキストの利益計算
        margin = product.calculate_profit_margin()

        # 7. 仕入コンテキストの発注チェック
        if product.needs_reorder():
            # ⚠️ 注文処理の中で発注ロジックを呼ぶ？
            print(f"⚠️ 商品 {product.name} の発注が必要です")

        # ⚠️ 問題: このメソッドを変更するには
        # カタログ、販売、在庫、配送、会計、仕入の
        # 6チームすべてとの調整が必要

        return {
            "customer_id": customer.id,
            "product_id": product.id,
            "quantity": quantity,
            "subtotal": order_amount,
            "discount": discount_amount,
            "shipping": shipping_cost,
            "total": order_amount - discount_amount + shipping_cost,
            "delivery_address": delivery_address,
            "profit_margin": margin,
        }


# ==========================================================
# 使用例 — このコードの問題を実感する
# ==========================================================

def main() -> None:
    """統一モデルの問題を実感するデモ"""

    # 1つの Product に全コンテキストの情報を詰め込む
    product = Product(
        id="PROD-001",
        name="プレミアムコーヒー豆 200g",
        status=ProductStatus.PUBLISHED,
        # カタログ情報
        description="厳選されたアラビカ種100%",
        images=["coffee_main.jpg", "coffee_detail.jpg"],
        categories=["飲料", "コーヒー"],
        brand="Premium Roast",
        display_price=1980.0,
        # 在庫情報
        sku="SKU-COFFEE-001",
        stock_quantity=50,
        warehouse_location="A-3-12",
        reorder_point=10,
        safety_stock=5,
        # 注文情報
        unit_price=1980.0,
        tax_rate=0.08,  # 食品なので軽減税率
        # 配送情報
        weight_kg=0.25,
        is_fragile=False,
        shipping_class="standard",
        # 仕入情報
        supplier_id="SUP-COFFEE-FARM",
        cost_price=800.0,
        lead_time_days=14,
    )

    customer = Customer(
        id="CUST-001",
        name="山田太郎",
        email="yamada@example.com",
        loyalty_rank="gold",
        total_purchase_amount=250000.0,
        credit_limit=500000.0,
        delivery_addresses=[{
            "zip": "150-0001",
            "address": "東京都渋谷区神宮前1-1-1",
            "type": "home",
        }],
        phone_number="090-1234-5678",
        delivery_preference="evening",
    )

    # 統一サービスで注文
    service = UnifiedOrderService()
    order = service.place_order(customer, product, quantity=3)

    print("=" * 60)
    print("【統一モデルでの注文結果】")
    print("=" * 60)
    for key, value in order.items():
        print(f"  {key}: {value}")

    # ⚠️ 以下の問題に注意:
    print("\n⚠️ この設計の問題点:")
    print("  1. Product クラスが 30以上の属性を持つ God Object")
    print("  2. ProductStatus に全コンテキストの状態が混在")
    print("  3. 注文処理に6つのコンテキストのロジックが混在")
    print("  4. 在庫の引当がカタログの状態を勝手に変更する")
    print("  5. テストに全コンテキストのセットアップが必要")
    print("  6. チーム間でコードコンフリクトが頻発する")


if __name__ == "__main__":
    main()
