"""
Day 5: ドメインサービス（Domain Service）の実装例

ドメインサービスの2つの実装パターンを示す:
1. TransferService - 口座間送金（複数エンティティにまたがる操作）
2. PricingService - 注文の価格計算（複雑なビジネスルール）
"""

from __future__ import annotations

from dataclasses import dataclass
from enum import Enum

from value_objects import Money


# ==============================================================================
# 銀行口座エンティティ（ドメインサービスの動作確認用）
# ==============================================================================


class BankAccount:
    """
    銀行口座エンティティ。

    - 残高の入出金ロジックはエンティティ自身が持つ
    - 口座間の送金ロジックはドメインサービスが担う
    """

    def __init__(self, account_id: str, owner_name: str, balance: Money) -> None:
        self._account_id = account_id
        self._owner_name = owner_name
        self._balance = balance

    @property
    def account_id(self) -> str:
        return self._account_id

    @property
    def owner_name(self) -> str:
        return self._owner_name

    @property
    def balance(self) -> Money:
        return self._balance

    def deposit(self, amount: Money) -> None:
        """入金する（自分自身の操作なのでエンティティのメソッド）"""
        self._balance = self._balance.add(amount)

    def withdraw(self, amount: Money) -> None:
        """出金する（自分自身の操作なのでエンティティのメソッド）"""
        if self._balance.amount < amount.amount:
            raise ValueError(
                f"残高不足です。残高: {self._balance}, 出金額: {amount}"
            )
        self._balance = self._balance.subtract(amount)

    def __repr__(self) -> str:
        return f"BankAccount({self._account_id}, {self._owner_name}, {self._balance})"


# ==============================================================================
# 1. TransferService - 口座間送金ドメインサービス
# ==============================================================================


class TransferService:
    """
    口座間の送金を行うドメインサービス。

    なぜドメインサービスか？
    - 送金は「送金元」にも「送金先」にも自然に属さない操作
    - 2つのエンティティを協調させるロジック
    - ステートレス（内部に状態を持たない）

    なぜエンティティのメソッドにしないのか？
    - BankAccount.transfer_to(target) とすると、
      送金元が送金先を直接操作することになり責務が広がりすぎる
    """

    def transfer(
        self,
        source: BankAccount,
        target: BankAccount,
        amount: Money,
    ) -> None:
        """
        口座間で送金を行う。

        Args:
            source: 送金元口座
            target: 送金先口座
            amount: 送金額

        Raises:
            ValueError: 同一口座への送金、または残高不足の場合
        """
        # ビジネスルール1: 同一口座への送金は不可
        if source.account_id == target.account_id:
            raise ValueError("同一口座への送金はできません")

        # ビジネスルール2: 送金額は0より大きい
        if amount.is_zero():
            raise ValueError("送金額は0より大きい必要があります")

        # ビジネスルール3: 残高が足りること（withdrawの中でもチェックされる）
        source.withdraw(amount)
        target.deposit(amount)


# ==============================================================================
# 2. PricingService - 価格計算ドメインサービス
# ==============================================================================


class CustomerRank(Enum):
    """顧客ランク"""

    REGULAR = "regular"  # 一般会員
    SILVER = "silver"  # シルバー会員
    GOLD = "gold"  # ゴールド会員
    PLATINUM = "platinum"  # プラチナ会員


@dataclass
class OrderForPricing:
    """価格計算用の注文データ（簡略化）"""

    item_count: int  # 商品数
    subtotal: Money  # 小計


class PricingService:
    """
    注文の最終価格を計算するドメインサービス。

    なぜドメインサービスか？
    - 価格計算には「注文」「顧客ランク」「割引ルール」の
      複数の情報が必要
    - 特定のエンティティに属さない横断的なビジネスルール
    - ステートレス（割引ルールはメソッド内で完結）
    """

    # 顧客ランクごとの割引率（%）
    _RANK_DISCOUNT_RATES: dict[CustomerRank, int] = {
        CustomerRank.REGULAR: 0,
        CustomerRank.SILVER: 3,
        CustomerRank.GOLD: 5,
        CustomerRank.PLATINUM: 10,
    }

    # まとめ買い割引の閾値
    _BULK_DISCOUNT_THRESHOLD = 5  # 5個以上で割引
    _BULK_DISCOUNT_RATE = 5  # 5%割引

    def calculate_final_price(
        self,
        order: OrderForPricing,
        customer_rank: CustomerRank,
    ) -> Money:
        """
        注文の最終価格を計算する。

        割引ルール:
        1. 顧客ランク割引: ランクに応じた割引率を適用
        2. まとめ買い割引: 5個以上で5%割引
        3. 割引は重複適用可能（合算）

        Args:
            order: 価格計算対象の注文
            customer_rank: 顧客のランク

        Returns:
            割引適用後の最終価格
        """
        subtotal = order.subtotal

        # 割引率を計算（ランク割引 + まとめ買い割引）
        total_discount_rate = self._calculate_total_discount_rate(
            order, customer_rank
        )

        # 割引額を計算
        discount_amount = subtotal.amount * total_discount_rate // 100
        discount = Money(discount_amount, subtotal.currency)

        return subtotal.subtract(discount)

    def _calculate_total_discount_rate(
        self,
        order: OrderForPricing,
        customer_rank: CustomerRank,
    ) -> int:
        """合計割引率を計算する"""
        rate = 0

        # 顧客ランク割引
        rate += self._RANK_DISCOUNT_RATES.get(customer_rank, 0)

        # まとめ買い割引
        if order.item_count >= self._BULK_DISCOUNT_THRESHOLD:
            rate += self._BULK_DISCOUNT_RATE

        return rate


# ==============================================================================
# 使用例
# ==============================================================================

if __name__ == "__main__":
    # --- TransferService の使用例 ---
    print("=== TransferService（口座間送金）===")

    # 口座を作成
    alice_account = BankAccount("ACC-001", "田中花子", Money(100000, "JPY"))
    bob_account = BankAccount("ACC-002", "佐藤太郎", Money(50000, "JPY"))
    print(f"送金前 - 花子: {alice_account.balance}, 太郎: {bob_account.balance}")

    # ドメインサービスで送金を実行
    transfer_service = TransferService()
    transfer_service.transfer(alice_account, bob_account, Money(30000, "JPY"))
    print(f"送金後 - 花子: {alice_account.balance}, 太郎: {bob_account.balance}")

    # 残高不足の送金を試みる
    try:
        transfer_service.transfer(alice_account, bob_account, Money(999999, "JPY"))
    except ValueError as e:
        print(f"送金エラー: {e}")

    # --- PricingService の使用例 ---
    print("\n=== PricingService（価格計算）===")

    pricing_service = PricingService()

    # 一般会員、3商品の注文
    order1 = OrderForPricing(item_count=3, subtotal=Money(10000, "JPY"))
    price1 = pricing_service.calculate_final_price(order1, CustomerRank.REGULAR)
    print(f"一般会員・3商品: {order1.subtotal} → {price1}（割引なし）")

    # ゴールド会員、3商品の注文（5%割引）
    price2 = pricing_service.calculate_final_price(order1, CustomerRank.GOLD)
    print(f"ゴールド会員・3商品: {order1.subtotal} → {price2}（ランク5%割引）")

    # ゴールド会員、6商品の注文（5% + 5% = 10%割引）
    order2 = OrderForPricing(item_count=6, subtotal=Money(30000, "JPY"))
    price3 = pricing_service.calculate_final_price(order2, CustomerRank.GOLD)
    print(f"ゴールド会員・6商品: {order2.subtotal} → {price3}（ランク5% + まとめ買い5%）")

    # プラチナ会員、10商品の注文（10% + 5% = 15%割引）
    order3 = OrderForPricing(item_count=10, subtotal=Money(50000, "JPY"))
    price4 = pricing_service.calculate_final_price(order3, CustomerRank.PLATINUM)
    print(f"プラチナ会員・10商品: {order3.subtotal} → {price4}（ランク10% + まとめ買い5%）")
