"""
Day 5: 値オブジェクト（Value Object）の実装例

値オブジェクトの4つの実装パターンを示す:
1. Money - 通貨と金額を持つ値オブジェクト（算術演算付き）
2. EmailAddress - バリデーション付きの値オブジェクト
3. Address - 複数属性を持つ値オブジェクト
4. DateRange - 範囲を表す値オブジェクト
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from datetime import date


# ==============================================================================
# 1. Money（お金）- 算術演算を持つ値オブジェクト
# ==============================================================================


@dataclass(frozen=True)  # frozen=True で不変にする
class Money:
    """
    お金を表す値オブジェクト。

    - 金額（amount）と通貨（currency）のペアで表現
    - 不変: 一度生成したら変更できない
    - 同じ通貨同士でのみ演算可能
    """

    amount: int  # 最小通貨単位（円なら1円単位）で保持する
    currency: str  # 通貨コード（"JPY", "USD" など）

    # サポートする通貨コードの一覧
    SUPPORTED_CURRENCIES = {"JPY", "USD", "EUR", "GBP"}

    def __post_init__(self) -> None:
        """生成時のバリデーション"""
        if self.amount < 0:
            raise ValueError(f"金額は0以上である必要があります: {self.amount}")
        if self.currency not in self.SUPPORTED_CURRENCIES:
            raise ValueError(f"未対応の通貨コードです: {self.currency}")

    def add(self, other: Money) -> Money:
        """加算: 同じ通貨同士のみ可能"""
        self._assert_same_currency(other)
        return Money(amount=self.amount + other.amount, currency=self.currency)

    def subtract(self, other: Money) -> Money:
        """減算: 同じ通貨同士のみ可能"""
        self._assert_same_currency(other)
        if self.amount < other.amount:
            raise ValueError("減算結果が負になります")
        return Money(amount=self.amount - other.amount, currency=self.currency)

    def multiply(self, factor: int) -> Money:
        """乗算: 数量倍する場合などに使用"""
        if factor < 0:
            raise ValueError("乗数は0以上である必要があります")
        return Money(amount=self.amount * factor, currency=self.currency)

    def is_greater_than(self, other: Money) -> bool:
        """比較: 同じ通貨同士のみ可能"""
        self._assert_same_currency(other)
        return self.amount > other.amount

    def is_zero(self) -> bool:
        """金額がゼロかどうか"""
        return self.amount == 0

    def _assert_same_currency(self, other: Money) -> None:
        """通貨が同じであることを保証する"""
        if self.currency != other.currency:
            raise ValueError(
                f"異なる通貨間の演算はできません: {self.currency} と {other.currency}"
            )

    def __str__(self) -> str:
        """人間が読みやすい形式で表示"""
        if self.currency == "JPY":
            return f"¥{self.amount:,}"
        return f"{self.amount:,} {self.currency}"


# ==============================================================================
# 2. EmailAddress（メールアドレス）- バリデーション付き値オブジェクト
# ==============================================================================


@dataclass(frozen=True)
class EmailAddress:
    """
    メールアドレスを表す値オブジェクト。

    - 生成時に必ずバリデーションを通す
    - 不正なメールアドレスは存在できない
    """

    value: str

    # シンプルなメールアドレスの正規表現パターン
    _PATTERN = re.compile(r"^[a-zA-Z0-9_.+-]+@[a-zA-Z0-9-]+\.[a-zA-Z0-9-.]+$")

    def __post_init__(self) -> None:
        """生成時のバリデーション"""
        if not self.value:
            raise ValueError("メールアドレスは空にできません")
        if not self._PATTERN.match(self.value):
            raise ValueError(f"無効なメールアドレスです: {self.value}")
        # 正規化: 小文字に変換して保持
        # frozen=True でも __post_init__ 内なら object.__setattr__ で設定可能
        object.__setattr__(self, "value", self.value.lower())

    @property
    def local_part(self) -> str:
        """ローカル部分（@の前）を返す"""
        return self.value.split("@")[0]

    @property
    def domain(self) -> str:
        """ドメイン部分（@の後）を返す"""
        return self.value.split("@")[1]

    def __str__(self) -> str:
        return self.value


# ==============================================================================
# 3. Address（住所）- 複数属性を持つ値オブジェクト
# ==============================================================================


@dataclass(frozen=True)
class Address:
    """
    住所を表す値オブジェクト。

    - 複数の属性の組み合わせで一つの概念を表現
    - すべての属性が一致すれば同じ住所とみなす
    """

    prefecture: str  # 都道府県
    city: str  # 市区町村
    street: str  # 番地
    building: str = ""  # 建物名（任意）

    def __post_init__(self) -> None:
        """生成時のバリデーション"""
        if not self.prefecture:
            raise ValueError("都道府県は必須です")
        if not self.city:
            raise ValueError("市区町村は必須です")
        if not self.street:
            raise ValueError("番地は必須です")

    @property
    def full_address(self) -> str:
        """完全な住所文字列を返す"""
        parts = [self.prefecture, self.city, self.street]
        if self.building:
            parts.append(self.building)
        return " ".join(parts)

    def with_new_building(self, building: str) -> Address:
        """建物名を変更した新しいAddressを返す（不変性を保つ）"""
        return Address(
            prefecture=self.prefecture,
            city=self.city,
            street=self.street,
            building=building,
        )

    def __str__(self) -> str:
        return self.full_address


# ==============================================================================
# 4. DateRange（日付範囲）- 範囲を表す値オブジェクト
# ==============================================================================


@dataclass(frozen=True)
class DateRange:
    """
    日付の範囲を表す値オブジェクト。

    - 開始日と終了日のペアで範囲を表現
    - 範囲に関する操作（重複判定、包含判定）を提供
    """

    start: date  # 開始日（含む）
    end: date  # 終了日（含む）

    def __post_init__(self) -> None:
        """生成時のバリデーション"""
        if self.start > self.end:
            raise ValueError(
                f"開始日は終了日以前である必要があります: {self.start} > {self.end}"
            )

    @property
    def days(self) -> int:
        """期間の日数を返す（開始日と終了日を含む）"""
        return (self.end - self.start).days + 1

    def contains(self, target_date: date) -> bool:
        """指定した日付がこの範囲に含まれるか"""
        return self.start <= target_date <= self.end

    def overlaps(self, other: DateRange) -> bool:
        """他の日付範囲と重複するか"""
        return self.start <= other.end and other.start <= self.end

    def __str__(self) -> str:
        return f"{self.start} 〜 {self.end}（{self.days}日間）"


# ==============================================================================
# 使用例
# ==============================================================================

if __name__ == "__main__":
    # --- Money の使用例 ---
    print("=== Money ===")
    price = Money(1000, "JPY")
    tax = Money(100, "JPY")
    total = price.add(tax)
    print(f"商品: {price}, 税: {tax}, 合計: {total}")

    # 同じ値なら等価（構造的等価性）
    money1 = Money(500, "JPY")
    money2 = Money(500, "JPY")
    print(f"500円 == 500円: {money1 == money2}")  # True

    # --- EmailAddress の使用例 ---
    print("\n=== EmailAddress ===")
    email = EmailAddress("User@Example.COM")
    print(f"メール: {email}")  # 小文字に正規化される
    print(f"ローカル部: {email.local_part}")
    print(f"ドメイン: {email.domain}")

    # --- Address の使用例 ---
    print("\n=== Address ===")
    addr = Address("東京都", "渋谷区", "神南1-2-3", "DDDビル5F")
    print(f"住所: {addr}")

    # 建物名を変更 → 新しいオブジェクトが返る（不変性）
    new_addr = addr.with_new_building("新DDDビル10F")
    print(f"新住所: {new_addr}")
    print(f"元の住所は変わらない: {addr}")

    # --- DateRange の使用例 ---
    print("\n=== DateRange ===")
    campaign = DateRange(date(2024, 12, 1), date(2024, 12, 31))
    print(f"キャンペーン期間: {campaign}")
    print(f"12/15は期間内: {campaign.contains(date(2024, 12, 15))}")  # True
    print(f"1/5は期間内: {campaign.contains(date(2025, 1, 5))}")  # False

    another = DateRange(date(2024, 12, 25), date(2025, 1, 10))
    print(f"期間の重複: {campaign.overlaps(another)}")  # True
