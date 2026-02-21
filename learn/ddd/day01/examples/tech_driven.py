"""
技術駆動（Tech-Driven）の設計例

このファイルは「悪い例」として、技術用語中心に設計されたコードを示す。
会員管理システムを題材に、DB操作やデータ構造の都合がコードの中心になっている。

問題点:
- クラス名やメソッド名が技術用語（DAO, CRUD操作）で構成されている
- ビジネスルールがどこにあるのか分からない
- コードを読んでも「何のための処理か」が伝わらない
- マジックナンバーが散在している
"""

from datetime import datetime


# ============================================================
# データアクセス層: 技術用語だけで構成されたクラス
# ============================================================

class UserDao:
    """ユーザーDAO（Data Access Object）
    
    問題: "User" は曖昧な用語。会員？管理者？ゲスト？
          "DAO" は技術用語であり、ビジネスの概念ではない。
    """

    def __init__(self, db_connection):
        self.conn = db_connection

    def insert_record(self, data: dict) -> int:
        """レコードをINSERTする
        
        問題: 「レコードを挿入する」— ビジネス的に何をしているのか？
              会員登録？仮登録？招待？ まったく分からない。
        """
        query = """
            INSERT INTO tbl_users (name, email, password_hash, status_flag, 
                                   created_at, updated_at)
            VALUES (%(name)s, %(email)s, %(password_hash)s, %(status_flag)s,
                    %(created_at)s, %(updated_at)s)
        """
        # status_flag=0 は何を意味する？ 仮登録？ 無効？
        data["status_flag"] = 0
        data["created_at"] = datetime.now()
        data["updated_at"] = datetime.now()
        return self.conn.execute(query, data)

    def update_flag(self, user_id: int, flag: int) -> None:
        """フラグを更新する
        
        問題: flag=1 は有効化？ flag=2 は停止？ flag=9 は退会？
              コードを読んでも意味が分からない。
        """
        query = "UPDATE tbl_users SET status_flag = %s, updated_at = %s WHERE id = %s"
        self.conn.execute(query, (flag, datetime.now(), user_id))

    def select_by_id(self, user_id: int) -> dict:
        """IDでSELECTする"""
        query = "SELECT * FROM tbl_users WHERE id = %s"
        return self.conn.fetchone(query, (user_id,))

    def select_by_condition(self, condition: dict) -> list[dict]:
        """条件でSELECTする
        
        問題: どんな条件？ ビジネス的に何を検索している？
        """
        where_clauses = []
        params = []
        for key, value in condition.items():
            where_clauses.append(f"{key} = %s")
            params.append(value)
        query = f"SELECT * FROM tbl_users WHERE {' AND '.join(where_clauses)}"
        return self.conn.fetchall(query, tuple(params))

    def delete_record(self, user_id: int) -> None:
        """レコードを削除する
        
        問題: 物理削除？ ビジネス的に何が起きている？
              退会？ アカウント削除？ データ消去？
        """
        query = "DELETE FROM tbl_users WHERE id = %s"
        self.conn.execute(query, (user_id,))


# ============================================================
# サービス層: ビジネスロジックが技術用語に埋もれている
# ============================================================

class UserService:
    """ユーザーサービス
    
    問題: ビジネスロジックがCRUD操作の手続きに埋もれている。
          何をしたいのか読み取るのが困難。
    """

    def __init__(self, user_dao: UserDao):
        self.dao = user_dao

    def create_user(self, name: str, email: str, password: str) -> int:
        """ユーザーを作成する
        
        問題: 「作成」は技術用語。ビジネス的には「会員登録」のはず。
              バリデーションルールもビジネス用語で表現されていない。
        """
        # バリデーション — 何のルールかコメントがないと分からない
        if len(password) < 8:
            raise ValueError("password too short")  # 英語のエラーメッセージ

        # メール重複チェック — ビジネスルール「同一メールでの二重登録禁止」が見えない
        existing = self.dao.select_by_condition({"email": email})
        if existing:
            raise ValueError("duplicate email")

        data = {
            "name": name,
            "email": email,
            "password_hash": self._hash(password),
        }
        return self.dao.insert_record(data)

    def activate_user(self, user_id: int) -> None:
        """ユーザーを有効化する
        
        問題: マジックナンバー 1 の意味が不明。
              「メール認証完了」というビジネスイベントが見えない。
        """
        self.dao.update_flag(user_id, 1)  # 1 = 有効？

    def deactivate_user(self, user_id: int) -> None:
        """ユーザーを無効化する
        
        問題: 「無効化」は退会？一時停止？アカウントロック？
        """
        self.dao.update_flag(user_id, 9)  # 9 = 退会？無効？

    def get_active_users(self) -> list[dict]:
        """アクティブユーザーを取得する
        
        問題: マジックナンバーで条件を指定。ビジネスの意図が不明。
        """
        return self.dao.select_by_condition({"status_flag": 1})

    @staticmethod
    def _hash(password: str) -> str:
        """パスワードをハッシュ化する（簡略化）"""
        import hashlib
        return hashlib.sha256(password.encode()).hexdigest()
