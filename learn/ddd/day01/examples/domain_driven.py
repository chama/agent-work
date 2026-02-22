"""
ドメイン駆動（Domain-Driven）の設計例

同じ「会員管理システム」を、ドメイン駆動設計（DDD）のアプローチで書き直したもの。
ユビキタス言語に基づき、ビジネスの概念がそのままコードに表れている。

改善点:
- クラス名・メソッド名がビジネス用語で構成されている
- コードを読むだけでビジネスルールが理解できる
- ドメインの概念（会員、会員ステータス、退会）が明確
- マジックナンバーがなく、列挙型で意味を表現
"""

from __future__ import annotations
from dataclasses import dataclass, field
from datetime import datetime
from enum import Enum
from typing import Protocol


# ============================================================
# 値オブジェクト: ドメインの概念を型で表現する
# ============================================================

class MemberStatus(Enum):
    """会員ステータス: 会員の現在の状態を表す"""
    PROVISIONAL = "provisional"   # 仮会員（メール未認証）
    ACTIVE = "active"             # 正会員（認証済み）
    SUSPENDED = "suspended"       # 一時停止中
    WITHDRAWN = "withdrawn"       # 退会済み


@dataclass(frozen=True)
class EmailAddress:
    """メールアドレス: 会員の連絡先を表す値オブジェクト"""
    value: str

    def __post_init__(self):
        if "@" not in self.value:
            raise InvalidEmailAddressError(self.value)


@dataclass(frozen=True)
class MemberId:
    """会員ID: 会員を一意に識別する値オブジェクト"""
    value: str


# ============================================================
# ドメインモデル: ビジネスルールがモデル自体に含まれる
# ============================================================

@dataclass
class Member:
    """会員: サービスに登録し利用する人を表すエンティティ

    「ユーザー」ではなく「会員」とする。
    ユビキタス言語として、チーム全体で「会員」と呼ぶことを合意している。
    """
    member_id: MemberId
    name: str
    email: EmailAddress
    status: MemberStatus = MemberStatus.PROVISIONAL
    registered_at: datetime = field(default_factory=datetime.now)
    withdrawn_at: datetime | None = None

    @classmethod
    def register(cls, member_id: MemberId, name: str, email: EmailAddress) -> Member:
        """新規会員登録を行う

        ビジネスルール: 会員登録直後は「仮会員」状態となる。
        メール認証が完了するまで正会員にはならない。
        """
        return cls(
            member_id=member_id,
            name=name,
            email=email,
            status=MemberStatus.PROVISIONAL,
        )

    def verify_email(self) -> None:
        """メール認証を完了し、正会員になる

        ビジネスルール: 仮会員のみがメール認証を完了できる。
        """
        if self.status != MemberStatus.PROVISIONAL:
            raise MemberStatusTransitionError(
                current=self.status,
                attempted=MemberStatus.ACTIVE,
                reason="メール認証は仮会員のみ実行可能です",
            )
        self.status = MemberStatus.ACTIVE

    def withdraw(self) -> None:
        """退会する

        ビジネスルール: 正会員または一時停止中の会員のみが退会できる。
        退会日時を記録する。
        """
        if self.status not in (MemberStatus.ACTIVE, MemberStatus.SUSPENDED):
            raise MemberStatusTransitionError(
                current=self.status,
                attempted=MemberStatus.WITHDRAWN,
                reason="退会は正会員または一時停止中の会員のみ実行可能です",
            )
        self.status = MemberStatus.WITHDRAWN
        self.withdrawn_at = datetime.now()

    def is_active(self) -> bool:
        """正会員であるかどうかを返す"""
        return self.status == MemberStatus.ACTIVE


# ============================================================
# リポジトリ: 永続化の詳細を抽象化する
# ============================================================

class MemberRepository(Protocol):
    """会員リポジトリ: 会員の保存・検索を抽象化するインターフェース

    「DAO」ではなく「リポジトリ」とする。
    リポジトリはコレクションのように振る舞い、永続化の詳細を隠蔽する。
    """
    def save(self, member: Member) -> None: ...
    def find_by_id(self, member_id: MemberId) -> Member | None: ...
    def find_by_email(self, email: EmailAddress) -> Member | None: ...
    def find_active_members(self) -> list[Member]: ...


# ============================================================
# ドメインサービス: 会員登録のビジネスプロセス
# ============================================================

class MemberRegistrationService:
    """会員登録サービス: 新規会員登録のビジネスロジックを担う

    単一のエンティティに収まらないビジネスロジック（例: 重複チェック）を扱う。
    """

    def __init__(self, member_repository: MemberRepository):
        self._member_repository = member_repository

    def register_new_member(self, name: str, email: EmailAddress) -> Member:
        """新規会員を登録する

        ビジネスルール: 同一メールアドレスでの二重登録は禁止。
        """
        existing = self._member_repository.find_by_email(email)
        if existing is not None:
            raise DuplicateEmailAddressError(email)

        member_id = MemberId(self._generate_id())
        member = Member.register(member_id=member_id, name=name, email=email)
        self._member_repository.save(member)
        return member

    @staticmethod
    def _generate_id() -> str:
        """一意のIDを生成する（簡略化）"""
        import uuid
        return str(uuid.uuid4())


# ============================================================
# ドメイン例外: ビジネスルール違反をドメインの言葉で表現する
# ============================================================

class InvalidEmailAddressError(Exception):
    """不正なメールアドレスエラー"""
    def __init__(self, email: str):
        super().__init__(f"不正なメールアドレスです: {email}")


class DuplicateEmailAddressError(Exception):
    """メールアドレス重複エラー: 同一メールアドレスでの二重登録"""
    def __init__(self, email: EmailAddress):
        super().__init__(f"このメールアドレスは既に登録されています: {email.value}")


class MemberStatusTransitionError(Exception):
    """会員ステータス遷移エラー: 許可されていない状態遷移"""
    def __init__(self, current: MemberStatus, attempted: MemberStatus, reason: str):
        super().__init__(
            f"会員ステータスを {current.value} から {attempted.value} に変更できません。"
            f"理由: {reason}"
        )
