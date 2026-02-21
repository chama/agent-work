"""
==========================================================
CQRS（Command Query Responsibility Segregation）概要コード例
==========================================================

CQRS とは、「書き込み（Command）」と「読み込み（Query）」の
責務を分離するアーキテクチャパターンである。

このファイルでは、オンライン書店の「注文」ドメインを題材に、
CQRS パターンの基本的な構造を示す。

■ なぜ CQRS が必要になるか？
  - 書き込み側: ビジネスルールの整合性が最重要 → リッチなドメインモデル
  - 読み込み側: パフォーマンスと表示の柔軟性が最重要 → 非正規化されたビューモデル
  - この2つを1つのモデルで兼ねると、どちらも中途半端になる

■ 構造:
  Command側（Write）: ドメインモデルを使い、ビジネスルールを厳密に適用
  Query側（Read）: 表示に最適化されたデータを高速に返す
"""

from __future__ import annotations

import uuid
from abc import ABC, abstractmethod
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol


# =============================================================================
# 共通: ドメインイベント
# =============================================================================
# CQRS では、Command側で発生したイベントを Query側に伝播させることで
# 読み込み用のデータを更新する。

@dataclass(frozen=True)
class DomainEvent:
    """ドメインイベントの基底クラス"""
    event_id: str = field(default_factory=lambda: str(uuid.uuid4()))
    occurred_at: datetime = field(default_factory=datetime.now)


@dataclass(frozen=True)
class OrderPlaced(DomainEvent):
    """注文が確定されたイベント"""
    order_id: str = ""
    customer_name: str = ""
    total_amount: int = 0
    item_count: int = 0


@dataclass(frozen=True)
class OrderCancelled(DomainEvent):
    """注文がキャンセルされたイベント"""
    order_id: str = ""
    reason: str = ""


# =============================================================================
# 🔵 Command側（書き込みモデル）
# =============================================================================
# ビジネスルールを厳密に守る、リッチなドメインモデル。
# データの整合性と不変条件の維持が最優先。


class OrderStatus(Enum):
    """注文ステータス"""
    DRAFT = "draft"           # 下書き
    CONFIRMED = "confirmed"   # 確定済み
    CANCELLED = "cancelled"   # キャンセル済み
    SHIPPED = "shipped"       # 発送済み


@dataclass(frozen=True)
class OrderItem:
    """注文明細（値オブジェクト）"""
    book_title: str
    unit_price: int    # 単価（円）
    quantity: int

    def __post_init__(self):
        if self.unit_price < 0:
            raise ValueError("単価は0以上でなければならない")
        if self.quantity <= 0:
            raise ValueError("数量は1以上でなければならない")

    @property
    def subtotal(self) -> int:
        """小計を計算"""
        return self.unit_price * self.quantity


@dataclass
class Order:
    """
    注文集約（Command側のドメインモデル）

    ビジネスルール:
    - 注文には1件以上の明細が必要
    - 確定後は明細の変更ができない
    - キャンセルは発送前のみ可能
    - 合計金額が100,000円を超える場合は承認が必要（簡易ルール）
    """
    id: str
    customer_name: str
    items: list[OrderItem] = field(default_factory=list)
    status: OrderStatus = OrderStatus.DRAFT
    _events: list[DomainEvent] = field(default_factory=list)

    # --- ビジネスルール ---

    APPROVAL_THRESHOLD = 100_000  # 承認が必要な金額閾値

    @property
    def total_amount(self) -> int:
        """合計金額"""
        return sum(item.subtotal for item in self.items)

    @property
    def requires_approval(self) -> bool:
        """承認が必要な注文かどうか"""
        return self.total_amount > self.APPROVAL_THRESHOLD

    def add_item(self, item: OrderItem) -> None:
        """明細を追加する"""
        if self.status != OrderStatus.DRAFT:
            raise ValueError("下書き状態でのみ明細を追加できます")
        self.items.append(item)

    def confirm(self) -> None:
        """注文を確定する"""
        if self.status != OrderStatus.DRAFT:
            raise ValueError("下書き状態の注文のみ確定できます")
        if len(self.items) == 0:
            raise ValueError("明細が空の注文は確定できません")
        if self.requires_approval:
            raise ValueError(
                f"合計 ¥{self.total_amount:,} は承認が必要です"
                f"（閾値: ¥{self.APPROVAL_THRESHOLD:,}）"
            )

        self.status = OrderStatus.CONFIRMED

        # ドメインイベントを発行（Query側への通知用）
        self._events.append(
            OrderPlaced(
                order_id=self.id,
                customer_name=self.customer_name,
                total_amount=self.total_amount,
                item_count=len(self.items),
            )
        )

    def cancel(self, reason: str) -> None:
        """注文をキャンセルする"""
        if self.status == OrderStatus.SHIPPED:
            raise ValueError("発送済みの注文はキャンセルできません")
        if self.status == OrderStatus.CANCELLED:
            raise ValueError("既にキャンセル済みです")

        self.status = OrderStatus.CANCELLED
        self._events.append(
            OrderCancelled(order_id=self.id, reason=reason)
        )

    def collect_events(self) -> list[DomainEvent]:
        """発生したドメインイベントを回収"""
        events = self._events.copy()
        self._events.clear()
        return events


# =============================================================================
# 🟢 Query側（読み込みモデル）
# =============================================================================
# 表示に最適化された非正規化データ。
# ビジネスルールは持たず、読み取り専用。


@dataclass(frozen=True)
class OrderSummaryView:
    """
    注文一覧用のビューモデル（Query側）

    特徴:
    - 表示に必要な情報だけを持つ（軽量）
    - 非正規化されている（JOINなしで取得可能）
    - イミュータブル（読み取り専用）
    """
    order_id: str
    customer_name: str
    total_amount: int
    item_count: int
    status: str
    ordered_at: str          # 表示用にフォーマット済み
    total_display: str       # "¥12,000" のように整形済み


@dataclass(frozen=True)
class OrderDetailView:
    """
    注文詳細用のビューモデル（Query側）

    一覧よりも詳しい情報を含む。
    """
    order_id: str
    customer_name: str
    items: list[dict]        # {"title": "...", "price": "¥...", "qty": 1, "subtotal": "¥..."}
    total_amount: str        # 整形済みの合計金額
    status: str
    ordered_at: str


# =============================================================================
# Query Service（読み込み専用サービス）
# =============================================================================

class OrderQueryService:
    """
    注文のクエリサービス

    読み込み専用。ビジネスルールは一切持たない。
    実際のプロダクトでは、読み込み専用DBやキャッシュから取得する。
    """

    def __init__(self) -> None:
        # 簡易的にインメモリストアを使用
        # 実際には Read DB（Redis、Elasticsearch 等）を使う
        self._order_views: dict[str, OrderSummaryView] = {}

    def handle_order_placed(self, event: OrderPlaced) -> None:
        """OrderPlaced イベントを処理して読み込みモデルを更新"""
        view = OrderSummaryView(
            order_id=event.order_id,
            customer_name=event.customer_name,
            total_amount=event.total_amount,
            item_count=event.item_count,
            status="確定済み",
            ordered_at=event.occurred_at.strftime("%Y-%m-%d %H:%M"),
            total_display=f"¥{event.total_amount:,}",
        )
        self._order_views[event.order_id] = view

    def handle_order_cancelled(self, event: OrderCancelled) -> None:
        """OrderCancelled イベントを処理して読み込みモデルを更新"""
        existing = self._order_views.get(event.order_id)
        if existing:
            # イミュータブルなので新しいインスタンスを作成
            updated = OrderSummaryView(
                order_id=existing.order_id,
                customer_name=existing.customer_name,
                total_amount=existing.total_amount,
                item_count=existing.item_count,
                status="キャンセル済み",
                ordered_at=existing.ordered_at,
                total_display=existing.total_display,
            )
            self._order_views[event.order_id] = updated

    def get_all_orders(self) -> list[OrderSummaryView]:
        """全注文の一覧を取得（Query側のメソッド）"""
        return list(self._order_views.values())

    def get_order(self, order_id: str) -> OrderSummaryView | None:
        """注文IDで検索（Query側のメソッド）"""
        return self._order_views.get(order_id)


# =============================================================================
# 簡易イベントバス（Command側 → Query側の橋渡し）
# =============================================================================

class SimpleEventBus:
    """
    シンプルなイベントバス

    Command側で発生したイベントをQuery側に伝播する。
    実際のプロダクトでは、RabbitMQ、Kafka、Amazon SNS/SQS 等を使用する。
    """

    def __init__(self, query_service: OrderQueryService) -> None:
        self._query_service = query_service

    def publish(self, events: list[DomainEvent]) -> None:
        """イベントを発行し、Query側のハンドラに伝播する"""
        for event in events:
            if isinstance(event, OrderPlaced):
                self._query_service.handle_order_placed(event)
                print(f"  [EventBus] OrderPlaced → Query側を更新")
            elif isinstance(event, OrderCancelled):
                self._query_service.handle_order_cancelled(event)
                print(f"  [EventBus] OrderCancelled → Query側を更新")


# =============================================================================
# デモ: CQRS パターンの動作確認
# =============================================================================

def demo():
    """CQRS パターンのデモンストレーション"""

    print("=" * 60)
    print("CQRS パターン デモ: オンライン書店の注文")
    print("=" * 60)

    # --- セットアップ ---
    query_service = OrderQueryService()
    event_bus = SimpleEventBus(query_service)

    # --- Command側: 注文を作成・確定 ---
    print("\n📝 Command側: 注文の作成と確定")
    print("-" * 40)

    order = Order(id="ORD-001", customer_name="田中太郎")
    order.add_item(OrderItem(book_title="ドメイン駆動設計入門", unit_price=3200, quantity=1))
    order.add_item(OrderItem(book_title="Clean Architecture", unit_price=3500, quantity=1))
    order.add_item(OrderItem(book_title="リファクタリング 第2版", unit_price=4800, quantity=2))

    print(f"  注文ID: {order.id}")
    print(f"  顧客名: {order.customer_name}")
    print(f"  明細数: {len(order.items)}件")
    print(f"  合計金額: ¥{order.total_amount:,}")
    print(f"  承認要否: {'要承認' if order.requires_approval else '不要'}")

    # 注文を確定
    order.confirm()
    print(f"  ステータス: {order.status.value}")

    # ドメインイベントを発行 → Query側に反映
    events = order.collect_events()
    event_bus.publish(events)

    # --- Command側: 2つ目の注文 ---
    print("\n📝 Command側: 2つ目の注文")
    print("-" * 40)

    order2 = Order(id="ORD-002", customer_name="佐藤花子")
    order2.add_item(OrderItem(book_title="プログラマの数学", unit_price=2400, quantity=1))
    order2.confirm()
    print(f"  注文ID: {order2.id}, 合計: ¥{order2.total_amount:,}")

    events2 = order2.collect_events()
    event_bus.publish(events2)

    # --- Command側: 2つ目の注文をキャンセル ---
    print("\n❌ Command側: 注文キャンセル")
    print("-" * 40)

    order2.cancel("顧客都合によるキャンセル")
    print(f"  注文ID: {order2.id} をキャンセル")

    cancel_events = order2.collect_events()
    event_bus.publish(cancel_events)

    # --- Query側: 注文一覧を取得 ---
    print("\n📊 Query側: 注文一覧の取得")
    print("-" * 40)

    all_orders = query_service.get_all_orders()
    for view in all_orders:
        print(f"  [{view.order_id}] {view.customer_name}")
        print(f"    金額: {view.total_display} / {view.item_count}点")
        print(f"    状態: {view.status} / 日時: {view.ordered_at}")

    # --- CQRS のポイント解説 ---
    print("\n" + "=" * 60)
    print("💡 CQRS パターンのポイント")
    print("=" * 60)
    print("""
  ┌─────────────────────────────────────────────────────┐
  │  Command側（書き込み）        Query側（読み込み）       │
  │  ─────────────────        ─────────────────         │
  │  ・リッチなドメインモデル    ・軽量なビューモデル        │
  │  ・ビジネスルールを厳守     ・表示に最適化             │
  │  ・整合性が最優先          ・パフォーマンスが最優先     │
  │  ・Order集約（複雑）       ・OrderSummaryView（単純）  │
  │                                                      │
  │     Command ──→ Event ──→ Query側の更新              │
  │   （イベントを介して同期）                              │
  └─────────────────────────────────────────────────────┘

  ✅ メリット:
    - 読み書きそれぞれに最適なモデルを使える
    - 読み込みのスケーリングが独立して可能
    - 複雑なクエリのためにドメインモデルを汚さなくてよい

  ⚠️ 注意点:
    - 結果整合性（Eventual Consistency）を受け入れる必要がある
    - システム全体の複雑さが増す
    - すべてのドメインに適用すべきではない（コアドメインの複雑な部分のみ）
    """)


if __name__ == "__main__":
    demo()
