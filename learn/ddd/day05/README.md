# Day 5: エンティティ、値オブジェクト、ドメインサービス

> DDDの3つの基本構成要素を理解し、使い分けができるようになる

## 本日のゴール

- エンティティと値オブジェクトの違いを正確に説明できる
- 適切な場面でドメインサービスを導入できる
- 各構成要素を正しく実装できる

---

## 1. エンティティ（Entity）

### 1.1 エンティティとは？

エンティティとは、**同一性（Identity）によって区別される**オブジェクトです。

たとえば、あなたが名前を変えても、引っ越しても、「あなた」であることは変わりません。
これは、あなたが固有の **ID（同一性）** を持っているからです。

```
🧑 田中太郎（ID: user-001）
    ↓ 名前を変更
🧑 田中一郎（ID: user-001）
    → 同一人物！IDが同じだから
```

### 1.2 エンティティの特徴

| 特徴 | 説明 |
|------|------|
| **同一性（Identity）** | IDによって他のオブジェクトと区別される |
| **ライフサイクル** | 生成 → 変更 → 削除の一連の流れを持つ |
| **可変性** | 属性は変わりうるが、IDは不変 |
| **等価性** | IDが同じなら同一のエンティティとみなす |

### 1.3 ライフサイクル

エンティティは、システム内で「誕生」し、状態を変え、最終的に「消滅」する流れを持ちます。

```
生成（Create）
  │
  ▼
状態変更（Update） ← 繰り返し可能
  │
  ▼
削除（Delete）/ 非活性化（Deactivate）
```

**例: 注文（Order）のライフサイクル**

```
注文作成 → 商品追加 → 確定 → 支払い → 発送 → 完了
  │                                           │
  └──── キャンセル ◄──────────────────────────┘
```

### 1.4 ID生成戦略

エンティティのIDをどう生成するかは、重要な設計判断です。

| 戦略 | 例 | メリット | デメリット |
|------|-----|---------|-----------|
| **UUID** | `550e8400-e29b-41d4-a716-446655440000` | DB不要で生成可能、分散システム向き | 長い、ソート不可 |
| **DB連番** | `1, 2, 3, ...` | シンプル、ソート可能 | DB依存、分散で衝突リスク |
| **ULID** | `01ARZ3NDEKTSV4RRFFQ69G5FAV` | ソート可能 + ユニーク | UUIDより知名度低い |
| **ドメイン固有ID** | `ORD-2024-00001` | 業務的に意味がある | 生成ロジックが複雑になりがち |

**推奨**: 特別な理由がなければ **UUID（v4）** を使いましょう。
生成にDBアクセスが不要で、テストもしやすいです。

### 1.5 エンティティの等価性

エンティティの等価性は **IDの比較** で判断します。

```python
class User:
    def __init__(self, user_id: str, name: str):
        self.user_id = user_id
        self.name = name

    def __eq__(self, other):
        if not isinstance(other, User):
            return False
        return self.user_id == other.user_id  # IDのみで比較！

    def __hash__(self):
        return hash(self.user_id)

# 名前が違っても、IDが同じなら同一エンティティ
user1 = User("user-001", "田中太郎")
user2 = User("user-001", "田中一郎")
assert user1 == user2  # True!
```

### 1.6 代表的なエンティティの例

| エンティティ | ID | 変更されうる属性 |
|-------------|-----|----------------|
| **User** | user_id | 名前、メールアドレス、パスワード |
| **Order** | order_id | 注文状態、商品リスト、合計金額 |
| **Product** | product_id | 名前、価格、在庫数 |
| **BankAccount** | account_id | 残高、ステータス |

---

## 2. 値オブジェクト（Value Object）

### 2.1 値オブジェクトとは？

値オブジェクトとは、**属性の組み合わせで区別される**オブジェクトです。
IDを持たず、「値」そのものとして扱います。

```
💴 1000円
    → 別の1000円札と「同じ価値」
    → どの1000円札かは気にしない（IDがない）

📧 test@example.com
    → 同じ文字列なら同じメールアドレス
```

### 2.2 値オブジェクトの特徴

| 特徴 | 説明 |
|------|------|
| **不変（Immutable）** | 一度作ったら変更できない |
| **構造的等価性** | すべての属性が同じなら等価 |
| **自己検証** | 生成時にバリデーションする |
| **副作用がない** | 操作しても新しいオブジェクトを返す |
| **交換可能** | 同じ値なら入れ替えても問題ない |

### 2.3 不変（Immutable）であること

値オブジェクトは **絶対に変更してはいけません**。
変更が必要な場合は、**新しいインスタンスを生成** します。

```python
# ❌ ダメな例: 値を直接変更
money.amount = 2000

# ✅ 良い例: 新しいインスタンスを返す
new_money = money.add(Money(1000, "JPY"))
```

**なぜ不変にするのか？**

1. **副作用の排除**: 他の場所で値が変わらない安心感
2. **スレッドセーフ**: 並行処理で競合が起きない
3. **推論の容易さ**: コードの動作が予測しやすい

### 2.4 構造的等価性

値オブジェクトは、**すべての属性が同じなら等しい** と判断します。

```python
# エンティティ: IDで比較
user1 = User(id="001", name="田中")
user2 = User(id="001", name="佐藤")
user1 == user2  # True（IDが同じ）

# 値オブジェクト: すべての属性で比較
money1 = Money(amount=1000, currency="JPY")
money2 = Money(amount=1000, currency="JPY")
money1 == money2  # True（属性がすべて同じ）

money3 = Money(amount=1000, currency="USD")
money1 == money3  # False（通貨が違う）
```

### 2.5 値オブジェクトのメリット

#### メリット1: バリデーションの集約

```python
# ❌ バリデーションが散らばる
def register_user(email: str):
    if "@" not in email:
        raise ValueError("...")
    # ...

def update_email(email: str):
    if "@" not in email:  # 同じチェックが重複！
        raise ValueError("...")

# ✅ 値オブジェクトにバリデーションを集約
class EmailAddress:
    def __init__(self, value: str):
        if "@" not in value:
            raise ValueError("...")
        self._value = value
```

#### メリット2: ドメイン知識の表現

```python
# ❌ プリミティブだと意味が曖昧
def create_order(price: int, quantity: int):
    pass  # priceの単位は？quantityの範囲は？

# ✅ 値オブジェクトで意味を明確に
def create_order(price: Money, quantity: Quantity):
    pass  # 型を見れば意味がわかる
```

### 2.6 プリミティブ型への執着（Primitive Obsession）

**アンチパターン**: ドメインの概念を `str` や `int` などのプリミティブ型で表現すること。

```python
# ❌ プリミティブ型への執着
class User:
    def __init__(self,
                 email: str,        # どんな文字列でも入る
                 phone: str,        # 電話番号のフォーマットは？
                 zipcode: str,      # バリデーションはどこ？
                 age: int):         # 負の数は？1000歳は？
        self.email = email
        self.phone = phone
        self.zipcode = zipcode
        self.age = age

# ✅ 値オブジェクトで表現
class User:
    def __init__(self,
                 email: EmailAddress,     # 必ず有効なメールアドレス
                 phone: PhoneNumber,      # 必ず有効な電話番号
                 zipcode: ZipCode,        # 必ず有効な郵便番号
                 age: Age):               # 必ず有効な年齢
        self.email = email
        self.phone = phone
        self.zipcode = zipcode
        self.age = age
```

### 2.7 代表的な値オブジェクトの例

| 値オブジェクト | 属性 | バリデーション例 |
|--------------|------|----------------|
| **Money** | 金額 + 通貨 | 金額 >= 0、通貨コードが有効 |
| **EmailAddress** | メールアドレス文字列 | RFC準拠のフォーマット |
| **Address** | 都道府県 + 市区町村 + 番地 | 各フィールドが空でない |
| **DateRange** | 開始日 + 終了日 | 開始日 <= 終了日 |
| **PhoneNumber** | 電話番号文字列 | 桁数、フォーマット |
| **Quantity** | 数量 | 正の整数 |

---

## 3. エンティティ vs 値オブジェクト 比較

### 3.1 比較表

| 観点 | エンティティ | 値オブジェクト |
|------|------------|--------------|
| **区別の方法** | ID（同一性） | 属性の組み合わせ |
| **可変性** | 可変（属性が変わりうる） | 不変（変更不可） |
| **等価性** | IDが同じなら等価 | 全属性が同じなら等価 |
| **ライフサイクル** | あり（生成〜削除） | なし（使い捨て） |
| **永続化** | 独自のテーブル/ドキュメント | 親エンティティの一部として保存 |
| **例** | User, Order, Product | Money, Email, Address |

### 3.2 判断フローチャート

```
そのオブジェクトは「追跡」する必要がある？
  │
  ├─ Yes → 同じ属性でも区別したい？
  │          │
  │          ├─ Yes → エンティティ 🏷️
  │          │         （例: 同姓同名の別人を区別したい）
  │          │
  │          └─ No → もう一度考えてみよう
  │
  └─ No → 同じ値なら交換可能？
            │
            ├─ Yes → 値オブジェクト 💎
            │         （例: 1000円は別の1000円と交換できる）
            │
            └─ No → エンティティの可能性大 🏷️
```

### 3.3 具体例で考える

| 概念 | エンティティ？値オブジェクト？ | 理由 |
|------|--------------------------|------|
| ユーザーアカウント | エンティティ | 同姓同名でも別人として追跡する |
| メールアドレス | 値オブジェクト | `a@b.com` は誰が持っていても同じ値 |
| 注文 | エンティティ | 同じ内容の注文でも別々に追跡する |
| 金額（1000円） | 値オブジェクト | どの1000円も同じ価値 |
| 商品レビュー | エンティティ | 同じ内容でも別のレビューとして追跡する |
| 住所 | 値オブジェクト | 同じ住所なら交換可能 |
| 座席予約 | エンティティ | 特定の予約として追跡が必要 |
| 座標（緯度・経度） | 値オブジェクト | 同じ座標は同じ場所 |

---

## 4. ドメインサービス（Domain Service）

### 4.1 ドメインサービスとは？

ドメインサービスとは、**エンティティにも値オブジェクトにも自然に属さないドメインロジック**を表現するオブジェクトです。

```
🤔 「この処理、どのエンティティに置くべきか迷うな...」
    → ドメインサービスの出番かもしれません
```

### 4.2 ドメインサービスの特徴

| 特徴 | 説明 |
|------|------|
| **ステートレス** | 内部に状態を持たない |
| **ドメインロジックを表現** | ビジネスルールそのもの |
| **複数のオブジェクトをまたぐ操作** | 単一のエンティティに属さない |
| **ドメイン用語で命名** | 技術用語ではなくビジネス用語を使う |

### 4.3 いつドメインサービスを使うか？

#### パターン1: 複数のエンティティにまたがる操作

```python
# 銀行口座間の送金
# → 送金元にも送金先にも属さないロジック
class TransferService:
    def transfer(self, source: BankAccount, target: BankAccount, amount: Money):
        """口座間の送金を行う"""
        source.withdraw(amount)
        target.deposit(amount)
```

**なぜエンティティのメソッドにしないのか？**

```python
# ❌ 送金元のメソッドにすると不自然
class BankAccount:
    def transfer_to(self, target: BankAccount, amount: Money):
        # 自分が送金先の口座を操作するのは責務が広すぎる
        self.withdraw(amount)
        target.deposit(amount)  # 他のエンティティを直接操作...
```

#### パターン2: ドメイン知識に基づく計算

```python
# 割引計算: 商品・顧客・キャンペーンなど複数の情報が必要
class PricingService:
    def calculate_price(self, order: Order, customer: Customer) -> Money:
        """注文の最終価格を計算する"""
        base_price = order.subtotal()
        discount = self._calculate_discount(order, customer)
        return base_price.subtract(discount)
```

#### パターン3: 外部サービスとの連携が必要なドメインルール

```python
# メールアドレスの重複チェック: リポジトリへのアクセスが必要
class UserUniquenessService:
    def __init__(self, user_repository):
        self._user_repository = user_repository

    def is_email_unique(self, email: EmailAddress) -> bool:
        """メールアドレスが一意かどうかを確認する"""
        return self._user_repository.find_by_email(email) is None
```

### 4.4 ドメインサービス vs アプリケーションサービス

これは**非常に重要な区別**です。混同しやすいので注意しましょう。

| 観点 | ドメインサービス | アプリケーションサービス |
|------|----------------|---------------------|
| **目的** | ビジネスルールの実行 | ユースケースの調整 |
| **知識** | ドメイン知識を持つ | ドメイン知識を持たない |
| **依存先** | ドメインモデルのみ | ドメインモデル + インフラ |
| **ステートレス** | はい | はい |
| **テスト** | ドメインモデルだけでテスト可能 | モック/スタブが必要 |
| **層** | ドメイン層 | アプリケーション層 |

**具体例で比較:**

```python
# ドメインサービス（ビジネスルール）
class TransferService:
    """口座間送金のビジネスルール"""
    def transfer(self, source: BankAccount, target: BankAccount, amount: Money):
        if source.balance < amount:
            raise InsufficientFundsError()
        source.withdraw(amount)
        target.deposit(amount)

# アプリケーションサービス（ユースケースの調整）
class TransferApplicationService:
    """送金ユースケースの実行と調整"""
    def __init__(self, account_repo, transfer_service, notification_service):
        self._account_repo = account_repo
        self._transfer_service = transfer_service
        self._notification_service = notification_service

    def execute_transfer(self, source_id: str, target_id: str, amount: int):
        # 1. リポジトリからエンティティを取得
        source = self._account_repo.find_by_id(source_id)
        target = self._account_repo.find_by_id(target_id)
        money = Money(amount, "JPY")

        # 2. ドメインサービスでビジネスルール実行
        self._transfer_service.transfer(source, target, money)

        # 3. リポジトリで永続化
        self._account_repo.save(source)
        self._account_repo.save(target)

        # 4. 通知（インフラ関心事）
        self._notification_service.notify_transfer(source_id, target_id, money)
```

### 4.5 ⚠️ ドメインサービスの過剰使用に注意

ドメインサービスを多用しすぎると、**貧血ドメインモデル（Anemic Domain Model）** になります。

```
❌ 貧血ドメインモデルの兆候:
  - エンティティがゲッター/セッターしか持たない
  - ビジネスロジックがすべてサービスにある
  - エンティティが「データの入れ物」になっている
```

```python
# ❌ 貧血ドメインモデル: ロジックがサービスに漏れている
class Order:
    """ただのデータコンテナ"""
    def __init__(self):
        self.items = []
        self.status = "draft"

class OrderService:
    def add_item(self, order, item):
        if order.status != "draft":
            raise Error("確定済みの注文には追加できません")
        order.items.append(item)
        # ↑ このロジックはOrderエンティティ内にあるべき！

# ✅ リッチドメインモデル: ロジックがエンティティ内にある
class Order:
    """ビジネスルールを持つエンティティ"""
    def __init__(self):
        self._items = []
        self._status = "draft"

    def add_item(self, item):
        if self._status != "draft":
            raise Error("確定済みの注文には追加できません")
        self._items.append(item)
```

**判断基準:**

```
そのロジックは、単一のエンティティの責務か？
  │
  ├─ Yes → エンティティのメソッドにする
  │
  └─ No → 複数のエンティティにまたがるか？
            │
            ├─ Yes → ドメインサービスにする
            │
            └─ No → もう一度考え直す
```

---

## 5. 3つの構成要素の関係図

```
┌─────────────────────────────────────────────────┐
│                  ドメイン層                        │
│                                                   │
│  ┌──────────────┐     ┌──────────────────────┐   │
│  │  エンティティ   │     │  値オブジェクト         │   │
│  │              │     │                      │   │
│  │  - User      │◄────│  - EmailAddress      │   │
│  │  - Order     │     │  - Money             │   │
│  │  - Product   │     │  - Address           │   │
│  │              │     │  - DateRange         │   │
│  └──────┬───────┘     └──────────────────────┘   │
│         │                                         │
│         │ 複数エンティティにまたがるロジック            │
│         ▼                                         │
│  ┌──────────────────────┐                        │
│  │  ドメインサービス        │                        │
│  │                      │                        │
│  │  - TransferService   │                        │
│  │  - PricingService    │                        │
│  └──────────────────────┘                        │
│                                                   │
└─────────────────────────────────────────────────┘
```

---

## 6. 実装のベストプラクティス

### エンティティ

1. **IDは生成時に確定する**（コンストラクタで必須にする）
2. **不正な状態を作れないようにする**（バリデーションをコンストラクタに）
3. **ビジネスルールはエンティティ内に置く**（貧血モデルを避ける）
4. **`__eq__` と `__hash__` はIDベースで実装する**

### 値オブジェクト

1. **必ず不変にする**（`@dataclass(frozen=True)` や `__setattr__` の禁止）
2. **生成時にバリデーションする**（不正な値は存在させない）
3. **`__eq__` と `__hash__` は全属性ベースで実装する**
4. **ドメインに関連する操作を持たせる**（例: `Money.add()`）

### ドメインサービス

1. **ステートレスにする**（内部状態を持たない）
2. **ドメイン用語で命名する**（`TransferService`, not `AccountHelper`）
3. **使いすぎに注意**（まずエンティティに置けないか考える）
4. **インターフェースに依存する**（具体実装に依存しない）

---

## 7. まとめ

```
┌────────────────────────────────────────────────────────────┐
│                    今日学んだこと                              │
│                                                              │
│  🏷️ エンティティ = IDで識別、ライフサイクルあり、可変          │
│  💎 値オブジェクト = 値で識別、不変、自己検証                   │
│  🔧 ドメインサービス = 複数オブジェクトにまたがるロジック        │
│                                                              │
│  判断に迷ったら:                                              │
│  「追跡が必要？」 → エンティティ                               │
│  「値として交換可能？」 → 値オブジェクト                        │
│  「どこにも属さないルール？」 → ドメインサービス                │
└────────────────────────────────────────────────────────────┘
```

---

## 次回予告

**Day 6: 集約（Aggregate）とリポジトリ（Repository）**
- 集約ルートとは何か
- トランザクション境界の設計
- リポジトリパターンの実装

---

## 参考資料

- Eric Evans「Domain-Driven Design」 第5章, 第6章
- Vaughn Vernon「実践ドメイン駆動設計」 第5章, 第6章
- Martin Fowler「Value Object」パターン解説
