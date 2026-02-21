"""
==========================================================
Anti-Corruption Layer（腐敗防止層）の実装例
==========================================================

シナリオ:
  あなたのチームは新しい「注文管理コンテキスト」を開発している。
  しかし、顧客情報はレガシーシステム（10年前に構築された基幹系）
  から取得する必要がある。

  レガシーシステムの API は:
  - 命名規則が統一されていない（日本語ローマ字、略語混在）
  - 不要なデータが大量に含まれる
  - NULL が頻出し、データの信頼性が低い

  ACL を使って、レガシーシステムの「汚いモデル」が
  新しいコンテキストに侵食するのを防ぐ。
"""

from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
from typing import Any, Optional


# ==========================================================
# レガシーシステム（外部コンテキスト）
# ※ 実際にはAPI呼び出しだが、学習用にクラスで表現
# ==========================================================

class LegacyCustomerAPI:
    """
    レガシー基幹システムの顧客API（シミュレーション）

    ⚠️ 特徴:
    - フィールド名が日本語ローマ字と英語の混在
    - 不要なフィールドが大量に含まれる
    - NULL が頻出（Optional ではなく None が直接入る）
    - 日付フォーマットが独自（YYYYMMDD の文字列）
    - ステータスがマジックナンバー
    """

    def __init__(self) -> None:
        # レガシーDBのデータをシミュレーション
        self._customers: dict[str, dict[str, Any]] = {
            "K00001": {
                "KOKYAKU_CD": "K00001",            # 顧客コード
                "KOKYAKU_NM": "ﾔﾏﾀﾞ ﾀﾛｳ",         # 半角カナ...
                "KOKYAKU_NM_KANJI": "山田 太郎",      # 漢字名
                "SEIBETSU_KBN": "1",                # 性別区分（1=男, 2=女）
                "UMARE_YMD": "19900315",            # 生年月日（YYYYMMDD）
                "YUBIN_NO": "150-0001",             # 郵便番号
                "JUSHO_1": "東京都",                  # 住所1（都道府県）
                "JUSHO_2": "渋谷区神宮前",             # 住所2（市区町村）
                "JUSHO_3": "1-1-1",                 # 住所3（番地）
                "JUSHO_4": "レジデンス渋谷 301",       # 住所4（建物）
                "DENWA_NO": "03-1234-5678",         # 電話番号
                "KEITAI_NO": "090-1234-5678",       # 携帯番号
                "MAIL_ADDR": "yamada@example.com",   # メールアドレス
                "TORIHIKI_KBN": "A",                # 取引区分（A=優良, B=通常, C=要注意）
                "SHINYO_GAKU": 5000000,             # 信用額（単位: 円）
                "RUIKEI_KINGAKU": 2500000,          # 累計金額
                "LAST_TORIHIKI_YMD": "20250110",    # 最終取引日
                "SAKUJO_FLG": "0",                  # 削除フラグ（0=有効, 1=削除）
                "TOUROKU_YMD": "20100401",          # 登録日
                "KOUSHIN_YMD": "20250110",          # 更新日
                "KOUSHIN_TANTOSHA_CD": "SYS001",    # 更新担当者コード
                "BIKO": None,                       # 備考（大体 NULL）
            },
            "K00002": {
                "KOKYAKU_CD": "K00002",
                "KOKYAKU_NM": "ｽｽﾞｷ ﾊﾅｺ",
                "KOKYAKU_NM_KANJI": "鈴木 花子",
                "SEIBETSU_KBN": "2",
                "UMARE_YMD": "19850720",
                "YUBIN_NO": "160-0022",
                "JUSHO_1": "東京都",
                "JUSHO_2": "新宿区新宿",
                "JUSHO_3": "3-3-3",
                "JUSHO_4": None,                    # 建物名が NULL
                "DENWA_NO": None,                   # 固定電話が NULL
                "KEITAI_NO": "080-9876-5432",
                "MAIL_ADDR": "suzuki@example.com",
                "TORIHIKI_KBN": "B",
                "SHINYO_GAKU": 1000000,
                "RUIKEI_KINGAKU": 150000,
                "LAST_TORIHIKI_YMD": "20241225",
                "SAKUJO_FLG": "0",
                "TOUROKU_YMD": "20200601",
                "KOUSHIN_YMD": "20241225",
                "KOUSHIN_TANTOSHA_CD": "USR042",
                "BIKO": "法人担当切替予定",
            },
        }

    def get_kokyaku(self, kokyaku_cd: str) -> Optional[dict[str, Any]]:
        """顧客情報を取得する（レガシーAPIメソッド名もローマ字）"""
        return self._customers.get(kokyaku_cd)

    def search_kokyaku_by_mail(self, mail_addr: str) -> Optional[dict[str, Any]]:
        """メールアドレスで顧客を検索する"""
        for customer in self._customers.values():
            if customer.get("MAIL_ADDR") == mail_addr:
                return customer
        return None


# ==========================================================
# 新しいコンテキストのドメインモデル（クリーンなモデル）
# ==========================================================

@dataclass(frozen=True)
class Address:
    """住所（値オブジェクト）"""
    postal_code: str
    prefecture: str
    city: str
    street: str
    building: str = ""

    @property
    def full_address(self) -> str:
        """住所のフル表示"""
        parts = [self.prefecture, self.city, self.street]
        if self.building:
            parts.append(self.building)
        return " ".join(parts)


@dataclass(frozen=True)
class ContactInfo:
    """連絡先情報（値オブジェクト）"""
    email: str
    phone_number: str  # 最も確実に繋がる番号


class CreditRating:
    """信用評価（値オブジェクト）"""

    def __init__(self, rating: str) -> None:
        valid_ratings = {"EXCELLENT", "GOOD", "STANDARD", "CAUTION"}
        if rating not in valid_ratings:
            raise ValueError(f"無効な信用評価: {rating}")
        self._rating = rating

    @property
    def value(self) -> str:
        return self._rating

    def allows_credit_purchase(self) -> bool:
        """掛け売りが可能か"""
        return self._rating in {"EXCELLENT", "GOOD"}

    def __repr__(self) -> str:
        return f"CreditRating({self._rating})"

    def __eq__(self, other: object) -> bool:
        if not isinstance(other, CreditRating):
            return NotImplemented
        return self._rating == other._rating


@dataclass
class Customer:
    """
    注文管理コンテキストの「顧客」

    ✅ クリーンで、このコンテキストに必要な情報だけを持つ
    ✅ レガシーシステムの命名規則やデータ構造に一切依存しない
    """
    id: str
    name: str
    address: Address
    contact: ContactInfo
    credit_rating: CreditRating
    credit_limit: int  # 円
    registered_at: datetime

    def can_place_order(self, amount: int) -> bool:
        """注文可能か判定する"""
        if not self.credit_rating.allows_credit_purchase():
            return False
        return amount <= self.credit_limit


# ==========================================================
# Anti-Corruption Layer（腐敗防止層）
# ==========================================================

class CustomerTranslator:
    """
    トランスレーター: レガシーモデル → 新ドメインモデル の変換

    ✅ ACL の核心部分。ここで「翻訳」を行う。
    ✅ レガシーの汚いデータ構造を、クリーンなドメインモデルに変換。
    ✅ データの正規化、デフォルト値の設定、バリデーションもここで行う。
    """

    @staticmethod
    def translate(legacy_data: dict[str, Any]) -> Customer:
        """レガシー顧客データを新ドメインモデルに変換する"""

        # 名前の変換（半角カナではなく漢字名を使用）
        name = legacy_data.get("KOKYAKU_NM_KANJI", "")
        if not name:
            # 漢字名がなければ半角カナを使う（フォールバック）
            name = legacy_data.get("KOKYAKU_NM", "不明")

        # 住所の組み立て
        address = Address(
            postal_code=legacy_data.get("YUBIN_NO", ""),
            prefecture=legacy_data.get("JUSHO_1", ""),
            city=legacy_data.get("JUSHO_2", ""),
            street=legacy_data.get("JUSHO_3", ""),
            building=legacy_data.get("JUSHO_4") or "",  # NULL → 空文字
        )

        # 連絡先の組み立て（携帯番号を優先、なければ固定電話）
        phone = legacy_data.get("KEITAI_NO") or legacy_data.get("DENWA_NO") or ""
        contact = ContactInfo(
            email=legacy_data.get("MAIL_ADDR", ""),
            phone_number=phone,
        )

        # 取引区分 → 信用評価への変換
        credit_rating = CustomerTranslator._translate_credit_rating(
            legacy_data.get("TORIHIKI_KBN", "B")
        )

        # 日付の変換（YYYYMMDD文字列 → datetime）
        registered_at = CustomerTranslator._parse_legacy_date(
            legacy_data.get("TOUROKU_YMD", "")
        )

        return Customer(
            id=legacy_data.get("KOKYAKU_CD", ""),
            name=name,
            address=address,
            contact=contact,
            credit_rating=credit_rating,
            credit_limit=int(legacy_data.get("SHINYO_GAKU", 0)),
            registered_at=registered_at,
        )

    @staticmethod
    def _translate_credit_rating(torihiki_kbn: str) -> CreditRating:
        """
        レガシーの取引区分を信用評価に変換

        レガシー: A=優良, B=通常, C=要注意
        新モデル: EXCELLENT, GOOD, STANDARD, CAUTION
        """
        mapping = {
            "A": "EXCELLENT",
            "B": "STANDARD",
            "C": "CAUTION",
        }
        rating_str = mapping.get(torihiki_kbn, "STANDARD")
        return CreditRating(rating_str)

    @staticmethod
    def _parse_legacy_date(date_str: str) -> datetime:
        """レガシーの日付文字列（YYYYMMDD）を datetime に変換"""
        if not date_str or len(date_str) != 8:
            return datetime(2000, 1, 1)  # デフォルト値
        try:
            return datetime.strptime(date_str, "%Y%m%d")
        except ValueError:
            return datetime(2000, 1, 1)  # パースエラー時のフォールバック


class LegacyCustomerAdapter:
    """
    アダプター: レガシーAPIの呼び出しをラップする

    ✅ レガシーAPIの詳細（エンドポイント、認証、エラーハンドリング）を隠蔽
    ✅ 呼び出し側はレガシーAPIの存在を意識しなくてよい
    """

    def __init__(self, legacy_api: LegacyCustomerAPI) -> None:
        self._legacy_api = legacy_api
        self._translator = CustomerTranslator()

    def find_by_id(self, customer_id: str) -> Optional[Customer]:
        """IDで顧客を検索する"""
        legacy_data = self._legacy_api.get_kokyaku(customer_id)
        if legacy_data is None:
            return None

        # 削除フラグチェック（レガシー特有のロジックもここで吸収）
        if legacy_data.get("SAKUJO_FLG") == "1":
            return None

        return self._translator.translate(legacy_data)

    def find_by_email(self, email: str) -> Optional[Customer]:
        """メールアドレスで顧客を検索する"""
        legacy_data = self._legacy_api.search_kokyaku_by_mail(email)
        if legacy_data is None:
            return None

        if legacy_data.get("SAKUJO_FLG") == "1":
            return None

        return self._translator.translate(legacy_data)


class CustomerRepository:
    """
    ファサード: 新コンテキストが利用するリポジトリインターフェース

    ✅ 新コンテキストのコードは、このリポジトリだけを使う
    ✅ データの取得元がレガシーAPIであることを知らない
    ✅ 将来レガシーを廃止しても、このインターフェースは変わらない
    """

    def __init__(self, adapter: LegacyCustomerAdapter) -> None:
        self._adapter = adapter

    def get(self, customer_id: str) -> Customer:
        """顧客を取得する（見つからなければ例外）"""
        customer = self._adapter.find_by_id(customer_id)
        if customer is None:
            raise CustomerNotFoundError(f"顧客が見つかりません: {customer_id}")
        return customer

    def find_by_email(self, email: str) -> Optional[Customer]:
        """メールアドレスで顧客を検索する"""
        return self._adapter.find_by_email(email)


class CustomerNotFoundError(Exception):
    """顧客が見つからない場合のドメイン例外"""
    pass


# ==========================================================
# ACL の構造を可視化
# ==========================================================

def print_acl_architecture() -> None:
    """ACLのアーキテクチャを表示する"""
    print("""
╔══════════════════════════════════════════════════════════════════╗
║              Anti-Corruption Layer のアーキテクチャ                ║
╠══════════════════════════════════════════════════════════════════╣
║                                                                  ║
║  ┌─────────────────┐                                             ║
║  │ 新コンテキスト     │                                             ║
║  │                 │  CustomerRepository.get("K00001")            ║
║  │  注文サービス     │──────────┐                                   ║
║  │                 │          │                                   ║
║  └─────────────────┘          ▼                                   ║
║                     ┌──────────────────────────┐                 ║
║                     │ Anti-Corruption Layer     │                 ║
║                     │                          │                 ║
║                     │  ┌────────────────────┐  │                 ║
║                     │  │ CustomerRepository │  │  ← Facade       ║
║                     │  │ （ファサード）        │  │                 ║
║                     │  └────────┬───────────┘  │                 ║
║                     │           │              │                 ║
║                     │  ┌────────▼───────────┐  │                 ║
║                     │  │ LegacyCustomer     │  │  ← Adapter      ║
║                     │  │ Adapter            │  │                 ║
║                     │  └────────┬───────────┘  │                 ║
║                     │           │              │                 ║
║                     │  ┌────────▼───────────┐  │                 ║
║                     │  │ CustomerTranslator │  │  ← Translator   ║
║                     │  │ （変換ロジック）      │  │                 ║
║                     │  └────────────────────┘  │                 ║
║                     │                          │                 ║
║                     └──────────┬───────────────┘                 ║
║                                │                                 ║
║                                ▼                                 ║
║                     ┌──────────────────────────┐                 ║
║                     │ レガシー基幹システム        │                 ║
║                     │                          │                 ║
║                     │  KOKYAKU_CD, KOKYAKU_NM  │                 ║
║                     │  JUSHO_1, JUSHO_2 ...    │                 ║
║                     │  TORIHIKI_KBN, SAKUJO_FLG│                 ║
║                     │                          │                 ║
║                     └──────────────────────────┘                 ║
║                                                                  ║
╚══════════════════════════════════════════════════════════════════╝
    """)


# ==========================================================
# 使用例
# ==========================================================

def main() -> None:
    """ACL を使ったレガシーシステム連携のデモ"""

    print("=" * 60)
    print("Anti-Corruption Layer デモ")
    print("=" * 60)

    # --- ACL のセットアップ ---
    # レイヤー構造: Repository → Adapter → Translator → Legacy API
    legacy_api = LegacyCustomerAPI()
    adapter = LegacyCustomerAdapter(legacy_api)
    repository = CustomerRepository(adapter)

    # --- ACL の構造を表示 ---
    print_acl_architecture()

    # --- 使用例1: IDで顧客を取得 ---
    print("【例1】IDで顧客を取得")
    print("-" * 40)

    customer = repository.get("K00001")
    print(f"  ID:       {customer.id}")
    print(f"  名前:     {customer.name}")
    print(f"  住所:     {customer.address.full_address}")
    print(f"  Email:    {customer.contact.email}")
    print(f"  電話:     {customer.contact.phone_number}")
    print(f"  信用評価:  {customer.credit_rating}")
    print(f"  与信枠:   ¥{customer.credit_limit:,}")
    print(f"  登録日:   {customer.registered_at.strftime('%Y-%m-%d')}")
    print(f"  注文可能(¥100,000): {customer.can_place_order(100000)}")

    # --- 使用例2: メールで顧客を検索 ---
    print(f"\n{'【例2】メールで顧客を検索'}")
    print("-" * 40)

    customer2 = repository.find_by_email("suzuki@example.com")
    if customer2:
        print(f"  ID:       {customer2.id}")
        print(f"  名前:     {customer2.name}")
        print(f"  住所:     {customer2.address.full_address}")
        print(f"  信用評価:  {customer2.credit_rating}")
        # 建物名が NULL だったケースも正しく処理されている
        print(f"  建物名:   '{customer2.address.building}' (空文字に正規化済み)")

    # --- 使用例3: 存在しない顧客 ---
    print(f"\n{'【例3】存在しない顧客を取得'}")
    print("-" * 40)
    try:
        repository.get("K99999")
    except CustomerNotFoundError as e:
        print(f"  例外: {e}")

    # --- ACL のメリットを表示 ---
    print(f"\n{'=' * 60}")
    print("✅ ACL のメリット:")
    print("=" * 60)
    print("  1. 新コンテキストのコードにレガシーの命名規則が漏れない")
    print("     → KOKYAKU_CD ではなく customer.id")
    print("     → JUSHO_1 + JUSHO_2 ではなく address.full_address")
    print()
    print("  2. レガシーのデータ品質問題を ACL 内で吸収")
    print("     → NULL は空文字やデフォルト値に変換")
    print("     → YYYYMMDD 文字列は datetime に変換")
    print("     → 半角カナは漢字名にフォールバック")
    print()
    print("  3. レガシーシステムの変更が新コンテキストに波及しない")
    print("     → Translator の変換ロジックを修正するだけ")
    print("     → 新コンテキストの Customer モデルは不変")
    print()
    print("  4. 段階的なリプレースが可能")
    print("     → 将来、Adapter の接続先を新DBに切り替えるだけ")
    print("     → Repository のインターフェースは変わらない")


if __name__ == "__main__":
    main()
