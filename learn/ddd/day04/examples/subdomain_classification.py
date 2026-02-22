"""
Day 4 サンプルコード: サブドメイン分類に応じた設計の洗練度の違い

このファイルでは、3種類のサブドメイン（Core / Supporting / Generic）が
それぞれどの程度の設計の深さを持つべきかを、コードで示す。

テーマ: オンラインフードデリバリーサービス
- Core Domain: 配達最適化（ルート計算、配達員マッチング）
- Supporting Subdomain: レストラン管理
- Generic Subdomain: 通知送信
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol


# =============================================================================
# 🔴 Core Domain: 配達最適化エンジン
# =============================================================================
# コアドメインには最もリッチなドメインモデルを適用する。
# - 値オブジェクト、エンティティ、集約、ドメインイベント、ドメインサービスを駆使
# - ビジネスルールをドメインオブジェクトの中に閉じ込める
# - 不変条件（invariant）を厳密に守る


# --- 値オブジェクト ---

@dataclass(frozen=True)
class Location:
    """位置情報を表す値オブジェクト（イミュータブル）"""
    latitude: float
    longitude: float

    def __post_init__(self):
        if not (-90 <= self.latitude <= 90):
            raise ValueError(f"緯度は-90〜90の範囲: {self.latitude}")
        if not (-180 <= self.longitude <= 180):
            raise ValueError(f"経度は-180〜180の範囲: {self.longitude}")

    def distance_to(self, other: Location) -> float:
        """2点間の距離を計算（簡易版: ユークリッド距離）"""
        return (
            (self.latitude - other.latitude) ** 2
            + (self.longitude - other.longitude) ** 2
        ) ** 0.5


@dataclass(frozen=True)
class DeliveryTimeEstimate:
    """配達時間見積もりを表す値オブジェクト"""
    min_minutes: int
    max_minutes: int

    def __post_init__(self):
        if self.min_minutes < 0:
            raise ValueError("最小時間は0以上である必要がある")
        if self.max_minutes < self.min_minutes:
            raise ValueError("最大時間は最小時間以上である必要がある")

    @property
    def average_minutes(self) -> float:
        return (self.min_minutes + self.max_minutes) / 2


# --- ドメインイベント ---

@dataclass(frozen=True)
class DomainEvent:
    """ドメインイベントの基底クラス"""
    occurred_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class DeliveryAssigned(DomainEvent):
    """配達が配達員にアサインされたイベント"""
    delivery_id: str = ""
    courier_id: str = ""
    estimated_time: DeliveryTimeEstimate | None = None


@dataclass(frozen=True)
class DeliveryRouteOptimized(DomainEvent):
    """配達ルートが最適化されたイベント"""
    delivery_id: str = ""
    optimized_distance: float = 0.0


# --- エンティティ ---

class CourierStatus(Enum):
    AVAILABLE = "available"       # 配達可能
    ON_DELIVERY = "on_delivery"   # 配達中
    OFFLINE = "offline"           # オフライン


@dataclass
class Courier:
    """配達員エンティティ"""
    id: str
    name: str
    current_location: Location
    status: CourierStatus
    rating: float  # 評価スコア（1.0〜5.0）
    active_deliveries_count: int = 0

    # ビジネスルール: 同時に持てる配達は最大3件
    MAX_CONCURRENT_DELIVERIES = 3

    @property
    def can_accept_delivery(self) -> bool:
        """この配達員が新しい配達を受けられるか（ビジネスルールの体現）"""
        return (
            self.status == CourierStatus.AVAILABLE
            and self.active_deliveries_count < self.MAX_CONCURRENT_DELIVERIES
        )

    def assign_delivery(self) -> None:
        """配達をアサインする"""
        if not self.can_accept_delivery:
            raise ValueError(
                f"配達員 {self.name} は現在配達を受けられない状態です"
            )
        self.active_deliveries_count += 1
        if self.active_deliveries_count >= self.MAX_CONCURRENT_DELIVERIES:
            self.status = CourierStatus.ON_DELIVERY


# --- 集約ルート ---

@dataclass
class DeliveryRequest:
    """
    配達リクエスト集約（Aggregate Root）

    コアドメインの中心的な集約。
    配達のライフサイクル全体を管理し、不変条件を守る。
    """
    id: str
    pickup_location: Location
    dropoff_location: Location
    assigned_courier: Courier | None = None
    estimated_time: DeliveryTimeEstimate | None = None
    _events: list[DomainEvent] = field(default_factory=list)

    def assign_courier(self, courier: Courier) -> None:
        """
        配達員をアサインする（ビジネスルールを集約内で保護）

        ルール:
        - 配達員は配達可能状態でなければならない
        - 既にアサイン済みの場合は再アサインできない
        """
        if self.assigned_courier is not None:
            raise ValueError("既に配達員がアサインされています")

        if not courier.can_accept_delivery:
            raise ValueError(
                f"配達員 {courier.name} は配達を受けられません"
            )

        courier.assign_delivery()
        self.assigned_courier = courier

        # ドメインイベントを発行
        self._events.append(
            DeliveryAssigned(
                delivery_id=self.id,
                courier_id=courier.id,
                estimated_time=self.estimated_time,
            )
        )

    def collect_events(self) -> list[DomainEvent]:
        """発生したドメインイベントを回収する"""
        events = self._events.copy()
        self._events.clear()
        return events


# --- ドメインサービス ---

class DeliveryOptimizationService:
    """
    配達最適化ドメインサービス

    複数の集約をまたぐロジックや、
    エンティティ単体に属さないドメインロジックを扱う。
    """

    def find_best_courier(
        self,
        delivery: DeliveryRequest,
        available_couriers: list[Courier],
    ) -> Courier | None:
        """
        最適な配達員を見つける

        マッチングアルゴリズム:
        1. 配達可能な配達員のみフィルタリング
        2. ピックアップ地点との距離でソート
        3. 距離が同じなら評価スコアが高い方を優先
        """
        candidates = [c for c in available_couriers if c.can_accept_delivery]

        if not candidates:
            return None

        # 距離と評価のスコアリング（コアドメインの核心的ロジック）
        def score(courier: Courier) -> float:
            distance = courier.current_location.distance_to(
                delivery.pickup_location
            )
            # 距離が近いほど良い（逆数）、評価が高いほど良い
            distance_score = 1.0 / (distance + 0.001)
            rating_score = courier.rating / 5.0
            return distance_score * 0.7 + rating_score * 0.3

        return max(candidates, key=score)

    def estimate_delivery_time(
        self,
        pickup: Location,
        dropoff: Location,
    ) -> DeliveryTimeEstimate:
        """配達時間を見積もる（簡易版）"""
        distance = pickup.distance_to(dropoff)
        # 簡易計算: 距離に応じた時間見積もり
        base_minutes = int(distance * 10)
        return DeliveryTimeEstimate(
            min_minutes=max(10, base_minutes - 5),
            max_minutes=base_minutes + 15,
        )


# =============================================================================
# 🟡 Supporting Subdomain: レストラン管理
# =============================================================================
# 支援サブドメインはシンプルなモデルで十分。
# - 値オブジェクトやエンティティは使うが、集約やドメインイベントは最小限
# - ビジネスロジックは少なめ
# - 「十分に良い」設計を目指す


@dataclass
class MenuItem:
    """メニュー項目（シンプルなデータクラス）"""
    id: str
    name: str
    price: int  # 円
    is_available: bool = True


@dataclass
class Restaurant:
    """
    レストランエンティティ

    支援サブドメインなので、シンプルな設計で十分。
    複雑なドメインイベントやビジネスルールは不要。
    """
    id: str
    name: str
    location: Location
    menu_items: list[MenuItem] = field(default_factory=list)
    is_open: bool = False

    def add_menu_item(self, item: MenuItem) -> None:
        """メニュー項目を追加（シンプルなCRUD的操作）"""
        self.menu_items.append(item)

    def get_available_items(self) -> list[MenuItem]:
        """利用可能なメニュー項目を取得"""
        return [item for item in self.menu_items if item.is_available]

    def open(self) -> None:
        self.is_open = True

    def close(self) -> None:
        self.is_open = False


# =============================================================================
# 🔵 Generic Subdomain: 通知送信
# =============================================================================
# 汎用サブドメインは最もシンプルに。
# - 既製品やSaaSに委譲するのが理想
# - 自作する場合も、最小限のコードで済ませる
# - Protocolやインターフェースで抽象化し、差し替え可能にする


class NotificationSender(Protocol):
    """通知送信のインターフェース（Protocol = 抽象）"""

    def send(self, recipient: str, message: str) -> bool:
        """通知を送信する"""
        ...


class EmailNotificationSender:
    """
    メール通知の実装（汎用サブドメイン）

    実際のプロダクトでは SendGrid や Amazon SES を使う。
    ここではシンプルなスタブ実装を示す。
    """

    def send(self, recipient: str, message: str) -> bool:
        # 実際には外部APIを呼び出す
        print(f"[EMAIL] To: {recipient}, Message: {message}")
        return True


class PushNotificationSender:
    """プッシュ通知の実装（汎用サブドメイン）"""

    def send(self, recipient: str, message: str) -> bool:
        # 実際には Firebase Cloud Messaging 等を呼び出す
        print(f"[PUSH] To: {recipient}, Message: {message}")
        return True


# =============================================================================
# 使用例: 3つのサブドメインを組み合わせる
# =============================================================================

def demo():
    """サブドメイン間の連携デモ"""

    print("=" * 60)
    print("🔴 Core Domain: 配達最適化")
    print("=" * 60)

    # 配達リクエストを作成
    delivery = DeliveryRequest(
        id=str(uuid.uuid4()),
        pickup_location=Location(35.6812, 139.7671),   # 東京駅
        dropoff_location=Location(35.6595, 139.7004),  # 渋谷駅
    )

    # 配達員の候補
    couriers = [
        Courier(
            id="c1",
            name="田中太郎",
            current_location=Location(35.6762, 139.6503),  # 新宿
            status=CourierStatus.AVAILABLE,
            rating=4.8,
        ),
        Courier(
            id="c2",
            name="佐藤花子",
            current_location=Location(35.6838, 139.7744),  # 秋葉原
            status=CourierStatus.AVAILABLE,
            rating=4.5,
        ),
        Courier(
            id="c3",
            name="鈴木一郎",
            current_location=Location(35.6580, 139.7016),  # 渋谷付近
            status=CourierStatus.OFFLINE,
            rating=4.9,
        ),
    ]

    # コアドメインの洗練されたロジック: 最適な配達員を見つける
    optimizer = DeliveryOptimizationService()

    # 時間見積もり
    estimate = optimizer.estimate_delivery_time(
        delivery.pickup_location, delivery.dropoff_location
    )
    delivery.estimated_time = estimate
    print(f"配達時間見積もり: {estimate.min_minutes}〜{estimate.max_minutes}分")

    # 最適マッチング
    best_courier = optimizer.find_best_courier(delivery, couriers)
    if best_courier:
        print(f"最適な配達員: {best_courier.name} (評価: {best_courier.rating})")
        delivery.assign_courier(best_courier)

        # ドメインイベントの確認
        events = delivery.collect_events()
        for event in events:
            print(f"ドメインイベント発行: {type(event).__name__}")
    else:
        print("利用可能な配達員がいません")

    print()
    print("=" * 60)
    print("🟡 Supporting Subdomain: レストラン管理")
    print("=" * 60)

    # 支援サブドメインのシンプルな操作
    restaurant = Restaurant(
        id="r1",
        name="ラーメン屋 麺太郎",
        location=Location(35.6812, 139.7671),
    )
    restaurant.open()
    restaurant.add_menu_item(
        MenuItem(id="m1", name="醤油ラーメン", price=800)
    )
    restaurant.add_menu_item(
        MenuItem(id="m2", name="味噌ラーメン", price=900)
    )
    restaurant.add_menu_item(
        MenuItem(id="m3", name="チャーシュー丼", price=500, is_available=False)
    )

    available = restaurant.get_available_items()
    print(f"レストラン: {restaurant.name}")
    print(f"利用可能メニュー: {[item.name for item in available]}")

    print()
    print("=" * 60)
    print("🔵 Generic Subdomain: 通知送信")
    print("=" * 60)

    # 汎用サブドメインのシンプルな処理
    email_sender = EmailNotificationSender()
    push_sender = PushNotificationSender()

    email_sender.send(
        "customer@example.com",
        "ご注文の配達が開始されました！"
    )
    push_sender.send(
        "device_token_abc123",
        "配達員が向かっています（約15分）"
    )


if __name__ == "__main__":
    demo()
