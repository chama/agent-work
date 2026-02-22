"""
==========================================================
Day 6 サンプルコード: リポジトリパターン（Repository Pattern）
==========================================================

このファイルでは、注文集約のリポジトリパターンを実装する。

構成:
  - OrderRepository（抽象クラス / インターフェース）
  - InMemoryOrderRepository（インメモリ実装）

学習ポイント:
  1. リポジトリはドメイン層にインターフェースを定義する
  2. 具象クラスはインフラ層に配置する（ここでは学習用に同一ファイル）
  3. リポジトリは集約全体を保存・取得する
  4. CRUD用語ではなくドメインセマンティクスのメソッド名を使う
  5. リポジトリは集約ルートごとに1つ
"""

from __future__ import annotations

import copy
from abc import ABC, abstractmethod
from datetime import datetime
from typing import Optional

# aggregate.py から集約と値オブジェクトをインポート
from aggregate import (
    DomainEvent,
    Money,
    Order,
    OrderId,
    OrderStatus,
    Quantity,
)


# ==========================================================
# リポジトリインターフェース（ドメイン層に配置）
# ==========================================================

class OrderRepository(ABC):
    """
    注文リポジトリのインターフェース（抽象クラス）

    ★ このインターフェースはドメイン層に属する
    ★ 永続化の詳細（DB, ファイル, API等）には一切触れない
    ★ ドメインの言葉でメソッド名を定義する

    【設計のポイント】
    - save(): 追加も更新も統一（永続化指向リポジトリ）
    - find_xxx(): ドメインの文脈に沿った検索メソッド
    - remove(): 論理削除も物理削除も実装に委ねる
    - next_identity(): ID生成をリポジトリに委譲
    """

    @abstractmethod
    def save(self, order: Order) -> None:
        """
        注文集約を永続化する

        - 新規の場合は追加、既存の場合は更新する
        - 集約全体（Order + OrderLine[]）を一括で保存する
        """
        ...

    @abstractmethod
    def find_by_id(self, order_id: OrderId) -> Optional[Order]:
        """
        注文IDで検索する

        見つからない場合は None を返す。
        例外を投げるかどうかはユースケース層で判断する。
        """
        ...

    @abstractmethod
    def find_by_customer_id(self, customer_id: str) -> list[Order]:
        """
        顧客IDで注文を検索する

        該当する注文のリストを返す（0件なら空リスト）。
        """
        ...

    @abstractmethod
    def find_pending_orders(self) -> list[Order]:
        """
        未確定（DRAFT状態）の注文を検索する

        ドメインの文脈に沿ったクエリメソッドの例。
        """
        ...

    @abstractmethod
    def find_confirmed_orders_since(self, since: datetime) -> list[Order]:
        """
        指定日時以降に確定された注文を検索する

        ドメインの文脈に沿った業務的なクエリの例。
        """
        ...

    @abstractmethod
    def remove(self, order: Order) -> None:
        """
        注文を削除する

        実装によって論理削除か物理削除かが異なる。
        """
        ...

    @abstractmethod
    def next_identity(self) -> OrderId:
        """
        新しい注文IDを生成する

        ID生成の戦略をリポジトリに委譲する。
        UUID, シーケンス, カスタムフォーマット等、
        実装ごとに戦略を変えられる。
        """
        ...

    @abstractmethod
    def count(self) -> int:
        """保存されている注文の総数を返す"""
        ...


# ==========================================================
# インメモリ実装（テスト用 / 学習用）
# ==========================================================

class InMemoryOrderRepository(OrderRepository):
    """
    インメモリのリポジトリ実装

    ★ テストやプロトタイピングで使用する
    ★ データはメモリ上の辞書に保存される
    ★ アプリケーション終了時にデータは失われる

    【実装のポイント】
    - deep copy で保存し、外部からの参照による意図しない変更を防ぐ
    - 集約全体を1つの単位として扱う
    """

    def __init__(self) -> None:
        # OrderId の文字列をキーとし、Order 集約を値とする辞書
        self._store: dict[str, Order] = {}

    def save(self, order: Order) -> None:
        """
        注文集約を保存する

        ★ deep copy を使って、リポジトリ内のデータと
          外部で操作中のオブジェクトを分離する
        """
        # 集約全体を deep copy して保存
        self._store[str(order.id)] = copy.deepcopy(order)

    def find_by_id(self, order_id: OrderId) -> Optional[Order]:
        """注文IDで検索する"""
        stored = self._store.get(str(order_id))
        if stored is None:
            return None
        # deep copy を返して、ストア内のデータを保護する
        return copy.deepcopy(stored)

    def find_by_customer_id(self, customer_id: str) -> list[Order]:
        """顧客IDで注文を検索する"""
        results = [
            copy.deepcopy(order)
            for order in self._store.values()
            if order.customer_id == customer_id
        ]
        return results

    def find_pending_orders(self) -> list[Order]:
        """未確定（DRAFT状態）の注文を検索する"""
        return [
            copy.deepcopy(order)
            for order in self._store.values()
            if order.status == OrderStatus.DRAFT
        ]

    def find_confirmed_orders_since(self, since: datetime) -> list[Order]:
        """指定日時以降に確定された注文を検索する"""
        return [
            copy.deepcopy(order)
            for order in self._store.values()
            if order.status == OrderStatus.CONFIRMED
            and order.confirmed_at is not None
            and order.confirmed_at >= since
        ]

    def remove(self, order: Order) -> None:
        """注文を削除する（物理削除）"""
        key = str(order.id)
        if key not in self._store:
            raise ValueError(f"削除対象の注文が見つかりません: {order.id}")
        del self._store[key]

    def next_identity(self) -> OrderId:
        """新しい注文IDを生成する"""
        return OrderId.generate()

    def count(self) -> int:
        """保存されている注文の総数"""
        return len(self._store)


# ==========================================================
# 使用例
# ==========================================================

def main() -> None:
    """リポジトリパターンの使用例デモ"""

    print("=" * 60)
    print("【リポジトリパターン（Repository Pattern）のデモ】")
    print("=" * 60)

    # リポジトリを作成
    repository: OrderRepository = InMemoryOrderRepository()

    # 1. 新しい注文を作成し、保存する
    print("\n1. 注文を作成して保存:")
    order_id = repository.next_identity()
    order = Order(order_id=order_id, customer_id="CUST-001")
    order.add_item(
        product_id="PROD-001",
        product_name="プレミアムコーヒー豆 200g",
        unit_price=Money(amount=1980),
        quantity=Quantity(value=2),
    )
    repository.save(order)
    print(f"   保存完了: {order}")
    print(f"   総件数: {repository.count()}")

    # 2. IDで検索する
    print("\n2. IDで検索:")
    found = repository.find_by_id(order_id)
    if found:
        print(f"   見つかった: {found}")
    else:
        print("   見つかりませんでした")

    # 3. 注文を変更して再保存する
    print("\n3. 注文を変更して再保存:")
    if found:
        found.add_item(
            product_id="PROD-002",
            product_name="オーガニック紅茶 100g",
            unit_price=Money(amount=1500),
            quantity=Quantity(value=1),
        )
        repository.save(found)
        print(f"   再保存完了: {found}")

    # 4. もう1つ注文を作成（同じ顧客）
    order2_id = repository.next_identity()
    order2 = Order(order_id=order2_id, customer_id="CUST-001")
    order2.add_item(
        product_id="PROD-003",
        product_name="抹茶パウダー 50g",
        unit_price=Money(amount=2500),
        quantity=Quantity(value=1),
    )
    order2.confirm()
    repository.save(order2)

    # 5. 顧客IDで検索する
    print("\n4. 顧客IDで検索 (CUST-001):")
    customer_orders = repository.find_by_customer_id("CUST-001")
    for o in customer_orders:
        print(f"   - {o}")
    print(f"   合計: {len(customer_orders)}件")

    # 6. 未確定の注文を検索する
    print("\n5. 未確定（DRAFT）の注文を検索:")
    pending = repository.find_pending_orders()
    for o in pending:
        print(f"   - {o}")

    # 7. 注文を削除する
    print("\n6. 注文を削除:")
    order_to_remove = repository.find_by_id(order_id)
    if order_to_remove:
        repository.remove(order_to_remove)
        print(f"   削除完了: {order_id}")
        print(f"   総件数: {repository.count()}")

    # 8. 存在しないIDで検索
    print("\n7. 存在しないIDで検索:")
    not_found = repository.find_by_id(OrderId("ORD-NONEXISTENT"))
    print(f"   結果: {not_found}")  # None

    print("\n" + "=" * 60)
    print("✅ リポジトリのポイント:")
    print("  1. ドメイン層にインターフェースを定義（抽象クラス）")
    print("  2. インフラ層に具象クラスを実装")
    print("  3. 集約全体を1つの単位として保存・取得")
    print("  4. CRUD用語ではなくドメインの言葉でメソッド名を付ける")
    print("  5. 内部エンティティ用のリポジトリは作らない")
    print("=" * 60)


if __name__ == "__main__":
    main()
