# Day 5 演習問題

> エンティティ、値オブジェクト、ドメインサービスの理解を深める

---

## 演習1: Money値オブジェクトを実装しよう

### 課題

以下のスターターコードを完成させて、すべてのテストケースが通るようにしてください。

### 要件

- 金額（amount）と通貨（currency）を持つ
- 不変（Immutable）であること
- 同じ通貨同士でのみ加算・減算が可能
- 異なる通貨間の演算はエラーにする
- 金額が負になる操作はエラーにする
- 構造的等価性（同じ金額・通貨なら等価）

### スターターコード

```python
"""
演習1: Money値オブジェクトを実装してください。
TODO コメントの部分を実装してください。
"""
from __future__ import annotations
from dataclasses import dataclass


@dataclass(frozen=True)
class Money:
    """お金を表す値オブジェクト"""
    amount: int
    currency: str

    def __post_init__(self) -> None:
        """バリデーション"""
        # TODO: 以下を実装してください
        # 1. amount が 0 未満ならValueErrorを発生させる
        # 2. currency が空文字ならValueErrorを発生させる
        pass

    def add(self, other: Money) -> Money:
        """加算（同じ通貨のみ）"""
        # TODO: 以下を実装してください
        # 1. 通貨が異なる場合はValueErrorを発生させる
        # 2. 新しいMoneyオブジェクトを返す（不変性を保つ）
        pass

    def subtract(self, other: Money) -> Money:
        """減算（同じ通貨のみ）"""
        # TODO: 以下を実装してください
        # 1. 通貨が異なる場合はValueErrorを発生させる
        # 2. 結果が負になる場合はValueErrorを発生させる
        # 3. 新しいMoneyオブジェクトを返す
        pass

    def multiply(self, factor: int) -> Money:
        """乗算"""
        # TODO: 以下を実装してください
        # 1. factor が負の場合はValueErrorを発生させる
        # 2. 新しいMoneyオブジェクトを返す
        pass

    def is_greater_than(self, other: Money) -> bool:
        """大小比較"""
        # TODO: 以下を実装してください
        # 1. 通貨が異なる場合はValueErrorを発生させる
        # 2. 自分のamountが相手より大きいかを返す
        pass
```

### テストケース

以下のテストがすべて通れば正解です。

```python
"""Money値オブジェクトのテスト"""
import pytest


class TestMoneyCreation:
    """生成時のバリデーションテスト"""

    def test_正常に生成できる(self):
        money = Money(1000, "JPY")
        assert money.amount == 1000
        assert money.currency == "JPY"

    def test_金額0で生成できる(self):
        money = Money(0, "JPY")
        assert money.amount == 0

    def test_負の金額はエラー(self):
        with pytest.raises(ValueError):
            Money(-1, "JPY")

    def test_空の通貨はエラー(self):
        with pytest.raises(ValueError):
            Money(1000, "")


class TestMoneyEquality:
    """構造的等価性のテスト"""

    def test_同じ値なら等価(self):
        assert Money(1000, "JPY") == Money(1000, "JPY")

    def test_金額が違えば不等(self):
        assert Money(1000, "JPY") != Money(2000, "JPY")

    def test_通貨が違えば不等(self):
        assert Money(1000, "JPY") != Money(1000, "USD")


class TestMoneyArithmetic:
    """算術演算のテスト"""

    def test_加算(self):
        result = Money(1000, "JPY").add(Money(500, "JPY"))
        assert result == Money(1500, "JPY")

    def test_異なる通貨の加算はエラー(self):
        with pytest.raises(ValueError):
            Money(1000, "JPY").add(Money(500, "USD"))

    def test_減算(self):
        result = Money(1000, "JPY").subtract(Money(300, "JPY"))
        assert result == Money(700, "JPY")

    def test_結果が負になる減算はエラー(self):
        with pytest.raises(ValueError):
            Money(100, "JPY").subtract(Money(500, "JPY"))

    def test_乗算(self):
        result = Money(500, "JPY").multiply(3)
        assert result == Money(1500, "JPY")

    def test_負の乗数はエラー(self):
        with pytest.raises(ValueError):
            Money(500, "JPY").multiply(-1)


class TestMoneyComparison:
    """比較のテスト"""

    def test_大きい場合True(self):
        assert Money(2000, "JPY").is_greater_than(Money(1000, "JPY")) is True

    def test_小さい場合False(self):
        assert Money(1000, "JPY").is_greater_than(Money(2000, "JPY")) is False

    def test_同額の場合False(self):
        assert Money(1000, "JPY").is_greater_than(Money(1000, "JPY")) is False

    def test_異なる通貨の比較はエラー(self):
        with pytest.raises(ValueError):
            Money(1000, "JPY").is_greater_than(Money(1000, "USD"))


class TestMoneyImmutability:
    """不変性のテスト"""

    def test_加算で元のオブジェクトは変わらない(self):
        original = Money(1000, "JPY")
        original.add(Money(500, "JPY"))
        assert original.amount == 1000  # 元のオブジェクトは変わらない

    def test_属性を直接変更できない(self):
        money = Money(1000, "JPY")
        with pytest.raises(AttributeError):
            money.amount = 2000  # frozen=True なので変更不可
```

### ヒント

- `@dataclass(frozen=True)` を使うと、`__eq__` と `__hash__` が自動生成され、属性の変更が禁止されます
- `__post_init__` はdataclassの `__init__` の後に自動的に呼ばれます
- 新しいインスタンスを返すときは `Money(amount=..., currency=...)` のように書きます

---

## 演習2: これはエンティティか？値オブジェクトか？

以下の10個の概念について、**エンティティ**か**値オブジェクト**かを判断し、その理由を考えてください。

### 問題

各問題について、以下の観点から考えましょう:
- IDで追跡する必要があるか？
- 同じ属性でも区別する必要があるか？
- 不変であるべきか？

---

**Q1: 従業員（Employee）**

```
ある会社の人事システムで、従業員を管理する。
同姓同名の従業員がいる可能性がある。
```

<details>
<summary>回答を見る</summary>

**エンティティ** 🏷️

**理由:**
- 同姓同名でも別の従業員として区別する必要がある
- 従業員番号（社員ID）で一意に識別される
- 部署異動や昇進など、ライフサイクルを通じて変化する
- 属性が変わっても同一人物として追跡し続ける必要がある

</details>

---

**Q2: 色（Color）**

```
描画アプリケーションで使用する色。
RGB値で表現される（例: R=255, G=0, B=0 は赤）。
```

<details>
<summary>回答を見る</summary>

**値オブジェクト** 💎

**理由:**
- RGB(255, 0, 0) は誰が使っても同じ「赤」
- 追跡する必要がない（「この赤」と「あの赤」を区別しない）
- 不変であるべき（色が勝手に変わると困る）
- 同じRGB値なら完全に交換可能

</details>

---

**Q3: ショッピングカート（ShoppingCart）**

```
ECサイトのショッピングカート。
ユーザーごとに1つ存在し、商品の追加・削除ができる。
```

<details>
<summary>回答を見る</summary>

**エンティティ** 🏷️

**理由:**
- 特定のユーザーのカートとして追跡が必要
- 商品が追加・削除されるため、ライフサイクルがある
- 同じ商品構成のカートでも、別のユーザーのカートとは区別する
- カートIDまたはユーザーIDで識別される

</details>

---

**Q4: 電話番号（PhoneNumber）**

```
顧客管理システムで使用する電話番号。
「090-1234-5678」のような文字列。
```

<details>
<summary>回答を見る</summary>

**値オブジェクト** 💎

**理由:**
- 同じ番号なら同じ電話番号（構造的等価性）
- 電話番号自体を追跡する必要はない（所有者であるユーザーを追跡する）
- フォーマットのバリデーションを含めて自己完結できる
- 不変であるべき（電話番号の一部だけ変えるのではなく、新しい番号に「交換」する）

</details>

---

**Q5: 予約（Reservation）**

```
レストランの予約システム。
日時、人数、顧客名で構成される。
同じ日時・人数・顧客名の予約が複数ある可能性がある。
```

<details>
<summary>回答を見る</summary>

**エンティティ** 🏷️

**理由:**
- 同じ内容の予約でも、別々の予約として管理する必要がある
- 予約IDで識別される
- 予約のキャンセル、変更などライフサイクルがある
- 「予約番号12345」として追跡し、状態が変化する

</details>

---

**Q6: 座標（Coordinate）**

```
地図アプリケーションの座標。
緯度（latitude）と経度（longitude）で表現される。
```

<details>
<summary>回答を見る</summary>

**値オブジェクト** 💎

**理由:**
- 同じ緯度・経度なら同じ場所を指す
- 座標自体を追跡する必要はない
- 不変であるべき（座標が勝手に動いたら困る）
- 完全に交換可能（北緯35度は誰にとっても北緯35度）

</details>

---

**Q7: チャットメッセージ（ChatMessage）**

```
チャットアプリのメッセージ。
送信者、本文、送信日時を持つ。
同じ内容のメッセージが複数ありうる。
```

<details>
<summary>回答を見る</summary>

**エンティティ** 🏷️

**理由:**
- 同じ内容のメッセージでも、別々のメッセージとして区別する（「おはよう」が2回）
- メッセージIDで識別される
- 既読/未読、編集、削除などの状態変化がある
- 特定のメッセージを参照（返信先）する必要がある

</details>

---

**Q8: 通貨（Currency）**

```
為替システムの通貨。
通貨コード（JPY, USD）と通貨名を持つ。
```

<details>
<summary>回答を見る</summary>

**値オブジェクト** 💎

**理由:**
- 「JPY」は世界中どこでも同じ「日本円」
- 通貨コードが同じなら同一の通貨
- 不変であるべき（JPYが突然USDに変わったら困る）
- 追跡する必要がない（通貨マスタのように見えるが、値として扱うのが自然）

**補足:** 通貨の為替レートを管理するシステムでは、CurrencyPairエンティティとして扱う場合もあります。コンテキストに依存します。

</details>

---

**Q9: 請求書（Invoice）**

```
経理システムの請求書。
請求先、請求明細、合計金額、発行日を持つ。
請求書番号で管理される。
```

<details>
<summary>回答を見る</summary>

**エンティティ** 🏷️

**理由:**
- 請求書番号で一意に識別される
- 未送付→送付済み→支払い済み のようなライフサイクルがある
- 同じ内容の請求書でも別々に管理する
- 法的に追跡が必要（「請求書番号 INV-2024-001」を特定できる必要がある）

</details>

---

**Q10: 期間（Period）**

```
勤怠管理システムの勤務期間。
開始日と終了日で構成される。
「2024年4月1日〜2024年4月30日」のような値。
```

<details>
<summary>回答を見る</summary>

**値オブジェクト** 💎

**理由:**
- 同じ開始日と終了日なら同じ期間
- 期間自体を追跡する必要はない（勤務記録エンティティの属性として使う）
- 不変であるべき（期間が勝手に伸縮したら困る）
- 「4/1〜4/30」は誰にとっても同じ期間

</details>

---

### 採点基準

| 正解数 | 評価 |
|--------|------|
| 10問 | 完璧！エンティティと値オブジェクトの区別が正確にできています |
| 8-9問 | 優秀！基本的な考え方が身についています |
| 6-7問 | 良好。間違えた問題の解説を読み返しましょう |
| 5問以下 | README.mdの比較セクションをもう一度読みましょう |

---

## 演習3: Orderエンティティにビジネスルールを追加しよう

### 課題

`examples/entities.py` の `Order` エンティティに、以下のビジネスルールを追加してください。

### 追加する機能

#### 機能1: 注文金額の上限チェック

```
ビジネスルール: 1回の注文の合計金額は100万円（1,000,000円）を超えてはいけない
```

- `add_item` メソッドで、商品追加後の合計が100万円を超える場合はエラーにする
- エラーメッセージ: `"注文合計が上限（¥1,000,000）を超えます"`

#### 機能2: 同一商品の数量制限

```
ビジネスルール: 同一商品は1注文につき最大10個まで
```

- `add_item` メソッドで、同じ商品名の既存アイテムがある場合は数量を合算してチェック
- エラーメッセージ: `"同一商品は10個までです"`

#### 機能3: 注文メモの追加

```
ビジネスルール: 注文にメモを追加できる（200文字以内）
確定前のみ追加・変更可能
```

- `add_note(note: str)` メソッドを追加
- 200文字を超える場合はエラー
- 確定後（DRAFT以外）は変更不可

### テストケース

以下のテストが通ることを確認してください。

```python
"""Order エンティティの追加テスト"""

def test_注文金額上限_超えるとエラー():
    order = Order(OrderId.generate(), UserId.generate())
    # 単価50万円の商品を追加
    order.add_item(OrderItem("高額商品A", Money(500000, "JPY"), 1))
    # さらに60万円を追加 → 合計110万円で上限超過
    with pytest.raises(ValueError, match="上限"):
        order.add_item(OrderItem("高額商品B", Money(600000, "JPY"), 1))


def test_注文金額上限_ちょうどはOK():
    order = Order(OrderId.generate(), UserId.generate())
    order.add_item(OrderItem("商品", Money(1000000, "JPY"), 1))
    # ちょうど100万円はOK
    assert order.total_amount == Money(1000000, "JPY")


def test_同一商品の数量制限():
    order = Order(OrderId.generate(), UserId.generate())
    order.add_item(OrderItem("DDDの本", Money(3000, "JPY"), 8))
    # 同じ商品をさらに追加 → 合計11個で制限超過
    with pytest.raises(ValueError, match="10個まで"):
        order.add_item(OrderItem("DDDの本", Money(3000, "JPY"), 3))


def test_注文メモ_正常():
    order = Order(OrderId.generate(), UserId.generate())
    order.add_note("ギフト包装お願いします")
    # メモが設定されていることを確認


def test_注文メモ_200文字超はエラー():
    order = Order(OrderId.generate(), UserId.generate())
    with pytest.raises(ValueError):
        order.add_note("あ" * 201)


def test_注文メモ_確定後は変更不可():
    order = Order(OrderId.generate(), UserId.generate())
    order.add_item(OrderItem("商品", Money(1000, "JPY"), 1))
    order.confirm()
    with pytest.raises(ValueError):
        order.add_note("遅れて追加したメモ")
```

### ヒント

1. **金額上限チェック**: `add_item` の中で、追加後の合計金額を事前計算してチェック
2. **同一商品の数量制限**: 既存のitemsから同じ商品名のアイテムを探し、数量を合算
3. **注文メモ**: `_note` 属性はすでに `__init__` で定義済み。`add_note` メソッドを追加するだけ

### 期待される実装のイメージ

```python
def add_item(self, item: OrderItem) -> None:
    """注文に商品を追加する"""
    if self._status != OrderStatus.DRAFT:
        raise ValueError("下書き状態の注文にのみ商品を追加できます")

    # TODO: ここに金額上限チェックを追加

    # TODO: ここに同一商品の数量制限チェックを追加

    self._items.append(item)

def add_note(self, note: str) -> None:
    """注文にメモを追加する"""
    # TODO: 実装してください
    pass
```

---

## 提出方法

1. 演習1: `exercises/exercise1_money.py` として実装を保存
2. 演習2: 自分の回答をメモし、解説と比較
3. 演習3: `examples/entities.py` に直接機能を追加

---

## 振り返りチェックリスト

学習の振り返りに使ってください。

- [ ] エンティティと値オブジェクトの違いを、自分の言葉で説明できる
- [ ] 値オブジェクトを不変に実装する方法がわかった
- [ ] エンティティの等価性をIDで実装する理由がわかった
- [ ] ドメインサービスを使うべき場面がわかった
- [ ] ドメインサービスとアプリケーションサービスの違いがわかった
- [ ] プリミティブ型への執着（Primitive Obsession）の問題がわかった
- [ ] 貧血ドメインモデルを避けるべき理由がわかった
