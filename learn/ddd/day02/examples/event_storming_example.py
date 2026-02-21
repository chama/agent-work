"""
イベントストーミングの結果をコードでモデル化した例
================================================

ECサイトの「注文〜配送」フローについてイベントストーミングを実施し、
発見されたドメインイベント、コマンド、集約、ポリシーを
Pythonのクラスとして表現した例。

【イベントストーミングで発見された要素】

  時系列フロー:
  ─────────────────────────────────────────────────────────

  👤顧客                     👤顧客              👤決済システム
    │                          │                     │
    ▼                          ▼                     ▼
  [カートに追加する]         [注文を確定する]       [支払いを処理する]
    │                          │                     │
    ▼                          ▼                     ▼
  [カート]                   [注文]                [支払い]
    │                          │                     │
    ▼                          ▼                     ▼
  (商品がカートに追加された)  (注文が確定された)    (支払いが完了した)
                                                      │
                                          ┌───────────┘
                                          ▼
                                    《支払い完了時に在庫を引き当てる》  ← ポリシー
                                          │
                                          ▼
                                    [在庫を引き当てる]
                                          │
                                          ▼
                                        [在庫]
                                          │
                                          ▼
                                    (在庫が引き当てられた)
                                          │
                                          ▼
                                    《在庫引当完了時に出荷指示を出す》  ← ポリシー
                                          │
                                          ▼
                                    [出荷を指示する]
                                          │
                                          ▼
                                        [出荷]
                                          │
                                          ▼
                                    (商品が出荷された)

  凡例:
    👤 = アクター
    [ ] = コマンド / 集約
    ( ) = ドメインイベント
    《 》= ポリシー（イベントに反応するビジネスルール）
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Optional
from uuid import uuid4


# =============================================================================
# 共通の基底クラス
# =============================================================================

@dataclass(frozen=True)
class DomainEvent:
    """
    ドメインイベント（オレンジの付箋）

    イベントストーミングで最初に洗い出す要素。
    「〜が起きた」「〜された」と過去形で表現する。
    """
    event_id: str = field(default_factory=lambda: str(uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class Command:
    """
    コマンド（ブルーの付箋）

    イベントを引き起こすアクション。
    「〜する」と命令形で表現する。
    """
    command_id: str = field(default_factory=lambda: str(uuid4()))
    issued_at: datetime = field(default_factory=datetime.now)


# =============================================================================
# 境界づけられたコンテキスト1: カートコンテキスト（Cart Context）
# =============================================================================

# --- コマンド ---

@dataclass(frozen=True)
class AddItemToCart(Command):
    """
    「カートに商品を追加する」コマンド

    アクター: 顧客
    トリガー: 商品ページで「カートに入れる」ボタンを押す
    """
    cart_id: str = ""
    product_id: str = ""
    product_name: str = ""
    unit_price: int = 0
    quantity: int = 0


@dataclass(frozen=True)
class RemoveItemFromCart(Command):
    """
    「カートから商品を削除する」コマンド

    アクター: 顧客
    トリガー: カート画面で「削除」ボタンを押す
    """
    cart_id: str = ""
    product_id: str = ""


@dataclass(frozen=True)
class UpdateCartItemQuantity(Command):
    """
    「カートの商品数量を変更する」コマンド

    アクター: 顧客
    トリガー: カート画面で数量を変更する
    """
    cart_id: str = ""
    product_id: str = ""
    new_quantity: int = 0


# --- ドメインイベント ---

@dataclass(frozen=True)
class ItemAddedToCart(DomainEvent):
    """「商品がカートに追加された」イベント"""
    cart_id: str = ""
    product_id: str = ""
    product_name: str = ""
    quantity: int = 0


@dataclass(frozen=True)
class ItemRemovedFromCart(DomainEvent):
    """「商品がカートから削除された」イベント"""
    cart_id: str = ""
    product_id: str = ""


@dataclass(frozen=True)
class CartItemQuantityUpdated(DomainEvent):
    """「カートの商品数量が変更された」イベント"""
    cart_id: str = ""
    product_id: str = ""
    old_quantity: int = 0
    new_quantity: int = 0


# --- 集約 ---

class Cart:
    """
    カート集約（イエローの付箋）

    【責務】
    - 商品の追加・削除・数量変更を管理する
    - カート内の合計を計算する

    【イベントストーミングで発見されたルール】
    - 同じ商品を追加すると数量が加算される
    - カートの商品数には上限がある（30商品まで）
    - 数量は1〜99の範囲
    """

    MAX_ITEMS = 30
    MAX_QUANTITY = 99

    def __init__(self, cart_id: str, customer_id: str):
        self.cart_id = cart_id
        self.customer_id = customer_id
        self._items: dict[str, dict] = {}  # product_id → {name, price, quantity}
        self._events: list[DomainEvent] = []

    def handle_add_item(self, command: AddItemToCart) -> None:
        """「カートに商品を追加する」コマンドを処理する"""
        if command.quantity <= 0:
            raise ValueError("数量は1以上でなければなりません")

        if command.product_id in self._items:
            # 既存商品の数量を加算
            current_qty = self._items[command.product_id]["quantity"]
            new_qty = current_qty + command.quantity
            if new_qty > self.MAX_QUANTITY:
                raise ValueError(f"数量は{self.MAX_QUANTITY}以下でなければなりません")
            self._items[command.product_id]["quantity"] = new_qty
        else:
            if len(self._items) >= self.MAX_ITEMS:
                raise ValueError(f"カートには最大{self.MAX_ITEMS}商品までです")
            self._items[command.product_id] = {
                "name": command.product_name,
                "price": command.unit_price,
                "quantity": command.quantity,
            }

        self._events.append(ItemAddedToCart(
            cart_id=self.cart_id,
            product_id=command.product_id,
            product_name=command.product_name,
            quantity=command.quantity,
        ))

    def handle_remove_item(self, command: RemoveItemFromCart) -> None:
        """「カートから商品を削除する」コマンドを処理する"""
        if command.product_id not in self._items:
            raise ValueError("指定された商品はカートにありません")

        del self._items[command.product_id]
        self._events.append(ItemRemovedFromCart(
            cart_id=self.cart_id,
            product_id=command.product_id,
        ))

    @property
    def total(self) -> int:
        """カートの合計金額を計算する"""
        return sum(
            item["price"] * item["quantity"]
            for item in self._items.values()
        )

    def pop_events(self) -> list[DomainEvent]:
        """発生したイベントを取り出す"""
        events = list(self._events)
        self._events.clear()
        return events


# =============================================================================
# 境界づけられたコンテキスト2: 注文コンテキスト（Order Context）
# =============================================================================

# --- コマンド ---

@dataclass(frozen=True)
class PlaceOrder(Command):
    """
    「注文を確定する」コマンド

    アクター: 顧客
    トリガー: カート画面で「注文する」ボタンを押す
    """
    order_id: str = ""
    customer_id: str = ""
    items: tuple = ()  # (product_id, product_name, unit_price, quantity) のタプル群
    shipping_address: str = ""


@dataclass(frozen=True)
class CancelOrder(Command):
    """
    「注文をキャンセルする」コマンド

    アクター: 顧客
    トリガー: 注文履歴画面で「キャンセル」ボタンを押す
    """
    order_id: str = ""
    reason: str = ""


# --- ドメインイベント ---

@dataclass(frozen=True)
class OrderPlaced(DomainEvent):
    """
    「注文が確定された」イベント

    【イベントストーミングでの発見】
    このイベントが発生すると、以下のポリシーが起動する：
    - 在庫引き当てポリシー
    - 注文確認メール送信ポリシー
    """
    order_id: str = ""
    customer_id: str = ""
    total_amount: int = 0


@dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    """
    「注文がキャンセルされた」イベント

    【イベントストーミングでの発見】
    このイベントが発生すると、以下のポリシーが起動する：
    - 在庫解放ポリシー（引き当て済みの場合）
    - 返金処理ポリシー（支払い済みの場合）
    """
    order_id: str = ""
    reason: str = ""


# --- 集約 ---

class OrderStatus(Enum):
    PLACED = "placed"         # 注文確定
    PAID = "paid"             # 支払い完了
    PREPARING = "preparing"   # 出荷準備中
    SHIPPED = "shipped"       # 出荷済み
    DELIVERED = "delivered"   # 配達完了
    CANCELLED = "cancelled"   # キャンセル


class OrderAggregate:
    """
    注文集約（イエローの付箋）

    【責務】
    - 注文のライフサイクルを管理する
    - 注文に関するビジネスルールを適用する

    【イベントストーミングで発見されたルール】
    - 注文確定時には少なくとも1つの明細が必要
    - キャンセルは出荷前のみ可能
    - 出荷済みの注文は返品フローに進む（キャンセルとは異なる）
    """

    def __init__(self, order_id: str, customer_id: str):
        self.order_id = order_id
        self.customer_id = customer_id
        self.status = OrderStatus.PLACED
        self.items: list[dict] = []
        self.total_amount: int = 0
        self.shipping_address: str = ""
        self._events: list[DomainEvent] = []

    @classmethod
    def place(cls, command: PlaceOrder) -> OrderAggregate:
        """「注文を確定する」コマンドから注文を生成する"""
        if not command.items:
            raise ValueError("注文には少なくとも1つの商品が必要です")

        order = cls(
            order_id=command.order_id,
            customer_id=command.customer_id,
        )
        order.shipping_address = command.shipping_address

        for product_id, product_name, unit_price, quantity in command.items:
            order.items.append({
                "product_id": product_id,
                "product_name": product_name,
                "unit_price": unit_price,
                "quantity": quantity,
            })

        order.total_amount = sum(
            item["unit_price"] * item["quantity"]
            for item in order.items
        )

        order._events.append(OrderPlaced(
            order_id=order.order_id,
            customer_id=order.customer_id,
            total_amount=order.total_amount,
        ))

        return order

    def cancel(self, command: CancelOrder) -> None:
        """「注文をキャンセルする」コマンドを処理する"""
        cancellable_statuses = {OrderStatus.PLACED, OrderStatus.PAID, OrderStatus.PREPARING}
        if self.status not in cancellable_statuses:
            raise ValueError(
                f"現在のステータス({self.status.value})ではキャンセルできません"
            )

        self.status = OrderStatus.CANCELLED
        self._events.append(OrderCancelled(
            order_id=self.order_id,
            reason=command.reason,
        ))

    def pop_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events


# =============================================================================
# 境界づけられたコンテキスト3: 決済コンテキスト（Payment Context）
# =============================================================================

# --- コマンド ---

@dataclass(frozen=True)
class ProcessPayment(Command):
    """
    「支払いを処理する」コマンド

    アクター: 決済システム（自動）
    トリガー: OrderPlaced イベントに反応して自動起動
    """
    payment_id: str = ""
    order_id: str = ""
    amount: int = 0
    payment_method: str = ""  # "credit_card", "bank_transfer" など


# --- ドメインイベント ---

@dataclass(frozen=True)
class PaymentCompleted(DomainEvent):
    """
    「支払いが完了した」イベント

    【イベントストーミングでの発見】
    このイベントが発生すると、以下のポリシーが起動する：
    - 在庫引き当てポリシー
    """
    payment_id: str = ""
    order_id: str = ""
    amount: int = 0


@dataclass(frozen=True)
class PaymentFailed(DomainEvent):
    """
    「支払いが失敗した」イベント

    【ホットスポット（赤い付箋）で議論された内容】
    - 支払い失敗時に注文をどうするか？
    - → 結論: 一定時間内にリトライ可能、超過で自動キャンセル
    """
    payment_id: str = ""
    order_id: str = ""
    reason: str = ""


# --- 集約 ---

class PaymentStatus(Enum):
    PENDING = "pending"
    COMPLETED = "completed"
    FAILED = "failed"
    REFUNDED = "refunded"


class PaymentAggregate:
    """
    支払い集約（イエローの付箋）

    【責務】
    - 支払い処理のライフサイクルを管理する

    【イベントストーミングで発見されたルール】
    - 1注文に対して1支払い
    - 支払い方法によって処理が異なる
    - 失敗時は3回までリトライ可能
    """

    MAX_RETRY_COUNT = 3

    def __init__(self, payment_id: str, order_id: str, amount: int):
        self.payment_id = payment_id
        self.order_id = order_id
        self.amount = amount
        self.status = PaymentStatus.PENDING
        self.retry_count = 0
        self._events: list[DomainEvent] = []

    def process(self, command: ProcessPayment) -> None:
        """「支払いを処理する」コマンドを処理する"""
        if self.status != PaymentStatus.PENDING:
            raise ValueError("処理待ちの支払いのみ処理できます")

        # 実際にはここで外部決済ゲートウェイを呼び出す
        # この例ではシミュレーション
        success = self._simulate_payment(command.payment_method)

        if success:
            self.status = PaymentStatus.COMPLETED
            self._events.append(PaymentCompleted(
                payment_id=self.payment_id,
                order_id=self.order_id,
                amount=self.amount,
            ))
        else:
            self.retry_count += 1
            if self.retry_count >= self.MAX_RETRY_COUNT:
                self.status = PaymentStatus.FAILED
                self._events.append(PaymentFailed(
                    payment_id=self.payment_id,
                    order_id=self.order_id,
                    reason="最大リトライ回数を超過しました",
                ))

    def refund(self) -> None:
        """返金処理"""
        if self.status != PaymentStatus.COMPLETED:
            raise ValueError("完了済みの支払いのみ返金できます")
        self.status = PaymentStatus.REFUNDED

    def _simulate_payment(self, payment_method: str) -> bool:
        """支払い処理のシミュレーション（実際には外部APIを呼ぶ）"""
        return True  # デモのため常に成功

    def pop_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events


# =============================================================================
# 境界づけられたコンテキスト4: 在庫コンテキスト（Inventory Context）
# =============================================================================

# --- コマンド ---

@dataclass(frozen=True)
class AllocateStock(Command):
    """
    「在庫を引き当てる」コマンド

    アクター: システム（自動）
    トリガー: PaymentCompleted イベントに反応して自動起動（ポリシー）
    """
    order_id: str = ""
    product_id: str = ""
    quantity: int = 0


@dataclass(frozen=True)
class ReleaseStock(Command):
    """
    「在庫を解放する」コマンド

    アクター: システム（自動）
    トリガー: OrderCancelled イベントに反応して自動起動（ポリシー）
    """
    order_id: str = ""
    product_id: str = ""
    quantity: int = 0


# --- ドメインイベント ---

@dataclass(frozen=True)
class StockAllocated(DomainEvent):
    """
    「在庫が引き当てられた」イベント

    【イベントストーミングでの発見】
    このイベントが発生すると、以下のポリシーが起動する：
    - 出荷指示ポリシー（全商品の引き当てが完了した場合）
    """
    order_id: str = ""
    product_id: str = ""
    quantity: int = 0


@dataclass(frozen=True)
class StockAllocationFailed(DomainEvent):
    """
    「在庫引き当てが失敗した」イベント

    【ホットスポット（赤い付箋）で議論された内容】
    - 一部の商品の在庫がない場合、注文全体をどうするか？
    - → 結論: 在庫のある商品だけ出荷し、残りはバックオーダーとする
    """
    order_id: str = ""
    product_id: str = ""
    requested_quantity: int = 0
    available_quantity: int = 0


# --- 集約 ---

class InventoryAggregate:
    """
    在庫集約（イエローの付箋）

    【責務】
    - 商品ごとの在庫数を管理する
    - 在庫の引き当て・解放を行う

    【イベントストーミングで発見されたルール】
    - 在庫は引き当て（予約）と実在庫の2つの概念がある
    - 引き当てた在庫は出荷まで保持する
    - 引き当て失敗時はバックオーダーとして記録する
    """

    def __init__(self, product_id: str, total_stock: int):
        self.product_id = product_id
        self.total_stock = total_stock      # 実在庫
        self.allocated_stock = 0            # 引き当て済み在庫
        self._events: list[DomainEvent] = []

    @property
    def available_stock(self) -> int:
        """引き当て可能な在庫数"""
        return self.total_stock - self.allocated_stock

    def allocate(self, command: AllocateStock) -> None:
        """「在庫を引き当てる」コマンドを処理する"""
        if command.quantity <= 0:
            raise ValueError("引き当て数量は1以上でなければなりません")

        if self.available_stock >= command.quantity:
            self.allocated_stock += command.quantity
            self._events.append(StockAllocated(
                order_id=command.order_id,
                product_id=self.product_id,
                quantity=command.quantity,
            ))
        else:
            self._events.append(StockAllocationFailed(
                order_id=command.order_id,
                product_id=self.product_id,
                requested_quantity=command.quantity,
                available_quantity=self.available_stock,
            ))

    def release(self, command: ReleaseStock) -> None:
        """「在庫を解放する」コマンドを処理する"""
        if command.quantity > self.allocated_stock:
            raise ValueError("引き当て済み在庫以上の数量は解放できません")

        self.allocated_stock -= command.quantity

    def pop_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events


# =============================================================================
# 境界づけられたコンテキスト5: 出荷コンテキスト（Shipping Context）
# =============================================================================

# --- コマンド ---

@dataclass(frozen=True)
class CreateShipment(Command):
    """
    「出荷を指示する」コマンド

    アクター: システム（自動）
    トリガー: StockAllocated イベント（全商品の引き当て完了時）に反応して自動起動
    """
    shipment_id: str = ""
    order_id: str = ""
    shipping_address: str = ""
    items: tuple = ()


# --- ドメインイベント ---

@dataclass(frozen=True)
class ShipmentCreated(DomainEvent):
    """「出荷指示が作成された」イベント"""
    shipment_id: str = ""
    order_id: str = ""


@dataclass(frozen=True)
class ShipmentDispatched(DomainEvent):
    """
    「商品が出荷された」イベント

    【イベントストーミングでの発見】
    このイベントが発生すると、以下のポリシーが起動する：
    - 出荷通知メール送信ポリシー
    - 追跡番号通知ポリシー
    """
    shipment_id: str = ""
    order_id: str = ""
    tracking_number: str = ""


@dataclass(frozen=True)
class ShipmentDelivered(DomainEvent):
    """「商品が配達された」イベント"""
    shipment_id: str = ""
    order_id: str = ""


# --- 集約 ---

class ShipmentStatus(Enum):
    CREATED = "created"
    DISPATCHED = "dispatched"
    DELIVERED = "delivered"


class ShipmentAggregate:
    """
    出荷集約（イエローの付箋）

    【責務】
    - 出荷のライフサイクルを管理する

    【イベントストーミングで発見されたルール】
    - 出荷は作成 → 発送 → 配達完了 の順で進む
    - 発送時に追跡番号が付与される
    """

    def __init__(self, shipment_id: str, order_id: str, shipping_address: str):
        self.shipment_id = shipment_id
        self.order_id = order_id
        self.shipping_address = shipping_address
        self.status = ShipmentStatus.CREATED
        self.tracking_number: Optional[str] = None
        self._events: list[DomainEvent] = []

    @classmethod
    def create(cls, command: CreateShipment) -> ShipmentAggregate:
        """「出荷を指示する」コマンドから出荷を生成する"""
        shipment = cls(
            shipment_id=command.shipment_id,
            order_id=command.order_id,
            shipping_address=command.shipping_address,
        )
        shipment._events.append(ShipmentCreated(
            shipment_id=shipment.shipment_id,
            order_id=shipment.order_id,
        ))
        return shipment

    def dispatch(self, tracking_number: str) -> None:
        """発送する"""
        if self.status != ShipmentStatus.CREATED:
            raise ValueError("作成済みの出荷のみ発送できます")

        self.status = ShipmentStatus.DISPATCHED
        self.tracking_number = tracking_number
        self._events.append(ShipmentDispatched(
            shipment_id=self.shipment_id,
            order_id=self.order_id,
            tracking_number=tracking_number,
        ))

    def mark_delivered(self) -> None:
        """配達完了にする"""
        if self.status != ShipmentStatus.DISPATCHED:
            raise ValueError("発送済みの出荷のみ配達完了にできます")

        self.status = ShipmentStatus.DELIVERED
        self._events.append(ShipmentDelivered(
            shipment_id=self.shipment_id,
            order_id=self.order_id,
        ))

    def pop_events(self) -> list[DomainEvent]:
        events = list(self._events)
        self._events.clear()
        return events


# =============================================================================
# ポリシー（パープルの付箋）— イベントに反応するビジネスルール
# =============================================================================

class AllocationPolicy:
    """
    在庫引き当てポリシー

    ビジネスルール: 「支払いが完了したら、在庫を引き当てる」

    イベントストーミングでの表記:
      (支払いが完了した) ──→ 《在庫引き当てポリシー》 ──→ [在庫を引き当てる]
    """

    def handle(self, event: PaymentCompleted, order_items: list[dict]) -> list[AllocateStock]:
        """PaymentCompleted イベントに反応して AllocateStock コマンドを生成する"""
        commands = []
        for item in order_items:
            commands.append(AllocateStock(
                order_id=event.order_id,
                product_id=item["product_id"],
                quantity=item["quantity"],
            ))
        return commands


class ShippingPolicy:
    """
    出荷指示ポリシー

    ビジネスルール: 「全商品の在庫引き当てが完了したら、出荷を指示する」

    イベントストーミングでの表記:
      (在庫が引き当てられた) ──→ 《出荷指示ポリシー》 ──→ [出荷を指示する]
    """

    def __init__(self):
        self._allocated_items: dict[str, set[str]] = {}  # order_id → {product_ids}

    def handle(self, event: StockAllocated,
               expected_item_count: int) -> Optional[CreateShipment]:
        """StockAllocated イベントに反応して、全商品の引き当てが完了したか確認する"""
        order_id = event.order_id

        if order_id not in self._allocated_items:
            self._allocated_items[order_id] = set()

        self._allocated_items[order_id].add(event.product_id)

        # 全商品の引き当てが完了したか確認
        if len(self._allocated_items[order_id]) >= expected_item_count:
            return CreateShipment(
                shipment_id=str(uuid4()),
                order_id=order_id,
            )

        return None  # まだ全商品の引き当てが完了していない


class StockReleasePolicy:
    """
    在庫解放ポリシー

    ビジネスルール: 「注文がキャンセルされたら、引き当て済みの在庫を解放する」

    イベントストーミングでの表記:
      (注文がキャンセルされた) ──→ 《在庫解放ポリシー》 ──→ [在庫を解放する]
    """

    def handle(self, event: OrderCancelled,
               allocated_items: list[dict]) -> list[ReleaseStock]:
        """OrderCancelled イベントに反応して ReleaseStock コマンドを生成する"""
        commands = []
        for item in allocated_items:
            commands.append(ReleaseStock(
                order_id=event.order_id,
                product_id=item["product_id"],
                quantity=item["quantity"],
            ))
        return commands


# =============================================================================
# フロー全体のシミュレーション
# =============================================================================

def simulate_order_flow():
    """
    イベントストーミングで発見したフロー全体をシミュレーションする

    時系列:
    1. 顧客がカートに商品を追加
    2. 顧客が注文を確定
    3. 支払いが処理される
    4. 在庫が引き当てられる
    5. 出荷が指示される
    6. 商品が出荷される
    """

    print("=" * 60)
    print("イベントストーミング結果のシミュレーション")
    print("=" * 60)

    # --- Step 1: カートに商品を追加 ---
    print("\n📦 Step 1: カートに商品を追加")
    cart = Cart(cart_id="CART-001", customer_id="CUST-001")

    cart.handle_add_item(AddItemToCart(
        cart_id="CART-001",
        product_id="PROD-001",
        product_name="ドメイン駆動設計入門",
        unit_price=3000,
        quantity=1,
    ))
    cart.handle_add_item(AddItemToCart(
        cart_id="CART-001",
        product_id="PROD-002",
        product_name="実践クリーンアーキテクチャ",
        unit_price=4500,
        quantity=2,
    ))

    cart_events = cart.pop_events()
    for event in cart_events:
        print(f"  イベント: {type(event).__name__} - {event.product_name}")

    print(f"  カート合計: ¥{cart.total:,}")

    # --- Step 2: 注文を確定 ---
    print("\n📋 Step 2: 注文を確定")
    order = OrderAggregate.place(PlaceOrder(
        order_id="ORD-001",
        customer_id="CUST-001",
        items=(
            ("PROD-001", "ドメイン駆動設計入門", 3000, 1),
            ("PROD-002", "実践クリーンアーキテクチャ", 4500, 2),
        ),
        shipping_address="東京都渋谷区...",
    ))

    order_events = order.pop_events()
    for event in order_events:
        print(f"  イベント: {type(event).__name__} - 合計: ¥{event.total_amount:,}")

    # --- Step 3: 支払い処理 ---
    print("\n💳 Step 3: 支払い処理")
    payment = PaymentAggregate(
        payment_id="PAY-001",
        order_id="ORD-001",
        amount=order.total_amount,
    )
    payment.process(ProcessPayment(
        payment_id="PAY-001",
        order_id="ORD-001",
        amount=order.total_amount,
        payment_method="credit_card",
    ))

    payment_events = payment.pop_events()
    for event in payment_events:
        print(f"  イベント: {type(event).__name__} - ¥{event.amount:,}")

    # --- Step 4: ポリシーが反応 → 在庫引き当て ---
    print("\n📊 Step 4: 在庫引き当て（ポリシーが自動起動）")

    allocation_policy = AllocationPolicy()
    allocate_commands = allocation_policy.handle(
        payment_events[0],  # PaymentCompleted
        order.items,
    )

    # 在庫集約に対してコマンドを実行
    inventory_prod1 = InventoryAggregate(product_id="PROD-001", total_stock=10)
    inventory_prod2 = InventoryAggregate(product_id="PROD-002", total_stock=5)

    inventories = {"PROD-001": inventory_prod1, "PROD-002": inventory_prod2}

    all_stock_events = []
    for cmd in allocate_commands:
        inventory = inventories[cmd.product_id]
        inventory.allocate(cmd)
        stock_events = inventory.pop_events()
        all_stock_events.extend(stock_events)
        for event in stock_events:
            print(f"  イベント: {type(event).__name__} - {event.product_id} x {event.quantity}")

    print(f"  PROD-001 残在庫: {inventory_prod1.available_stock}")
    print(f"  PROD-002 残在庫: {inventory_prod2.available_stock}")

    # --- Step 5: ポリシーが反応 → 出荷指示 ---
    print("\n🚚 Step 5: 出荷指示（ポリシーが自動起動）")

    shipping_policy = ShippingPolicy()
    create_shipment_cmd = None
    for event in all_stock_events:
        if isinstance(event, StockAllocated):
            cmd = shipping_policy.handle(event, expected_item_count=2)
            if cmd:
                create_shipment_cmd = cmd

    if create_shipment_cmd:
        shipment = ShipmentAggregate.create(create_shipment_cmd)
        shipment_events = shipment.pop_events()
        for event in shipment_events:
            print(f"  イベント: {type(event).__name__} - {event.shipment_id[:8]}...")

        # --- Step 6: 出荷 ---
        print("\n📮 Step 6: 商品を出荷")
        shipment.dispatch(tracking_number="JP-1234567890")
        dispatch_events = shipment.pop_events()
        for event in dispatch_events:
            print(f"  イベント: {type(event).__name__} - 追跡番号: {event.tracking_number}")

    print("\n✅ フロー完了!")
    print("\n【まとめ: イベントストーミングで発見された境界づけられたコンテキスト】")
    print("  1. カートコンテキスト   — 商品の選択と管理")
    print("  2. 注文コンテキスト     — 注文のライフサイクル")
    print("  3. 決済コンテキスト     — 支払い処理")
    print("  4. 在庫コンテキスト     — 在庫の引き当てと管理")
    print("  5. 出荷コンテキスト     — 出荷と配送")


if __name__ == "__main__":
    simulate_order_flow()
