# ミルク単価くらべ：運営メモ

このファイルは、Claudeとの会話が分かれても同じ前提で作業するためのメモです。
このリポジトリを読み込んだClaudeは、作業の前にここを確認し、決まったことが変わったらここも書き換えてください。

## サイト
- 公開URL：https://sunnyleaf62-oss.github.io/milk-tanka/
- 姉妹サイト：おむつ単価くらべ https://sunnyleaf62-oss.github.io/omutsu-tanka/ ／ mama-note https://sunnyleaf62-oss.github.io/mama-note/
- 公開：GitHub Pages（main ブランチの / を公開）
- 価格の更新：GitHub Actions「価格を毎日更新」。毎朝5:47（日本時間）と、products.json・fetch_prices.py・deals.json を変えたときに自動で動く

## アフィリエイト
| モール | 仕組み | 値 |
|---|---|---|
| 楽天 | 楽天ウェブサービスAPI（ウェブアプリケーション型。許可サイトは sunnyleaf62-oss.github.io） | Secrets: RAKUTEN_APP_ID / RAKUTEN_ACCESS_KEY / RAKUTEN_AFFILIATE_ID / RAKUTEN_REFERER |
| Yahoo!ショッピング | 商品検索API v3 ＋ バリューコマース（審査通過済み） | Secret: YAHOO_CLIENT_ID。VCの sid=3784952 / pid=892737497 は fetch_prices.py に記載（公開される値） |
| Amazon | Creators API（認証情報バージョン 3.3） | Secrets: AMAZON_CREDENTIAL_ID / AMAZON_CREDENTIAL_SECRET / AMAZON_API_VERSION / AMAZON_PARTNER_TAG |

- AmazonのトラッキングIDは **milk-tanka-22**（このサイト専用）。運営者の個人用のトラッキングIDは使わない（このリポジトリは公開なので、ここにも書かない）。
- 新しい「Yahoo!ショッピングアフィリエイト」（2026年1月開始・PayPayマネー払い）はAPI非対応のため、サイトではバリューコマースを使う。SNS投稿用には使ってよい。
- キーやシークレットはチャットに貼らず、GitHubの Settings → Secrets に直接入れてもらう。

## 決めたこと（運営者の方針）
- 報酬が付かないリンクでも、いちばん安いお店を正直に表示する（わざと楽天などへ誘導しない）。
- 表記：ページ上部に「（当ページのリンクには広告が含まれています）」を小さく。フッターに「Amazonのアソシエイトとして、当サイトは適格販売により収入を得ています。」（Amazon規約で必須）。楽天・バリューコマースの社名は書かない。
- 種類：乳児用／フォローアップの切り替え。タイプ表記は「粉ミルク・キューブ・スティック・液体」（「缶」とは書かない）。
- 配色：アイコン（水色の哺乳びん）に合わせた水色・青ベース。
- 送料が分からない送料別の出品は、目安800円を足して比べる。

## 商品の追加・調整
- products.json に1商品ずつ書く。`g_per_100ml` は必ずメーカー表示で確認する（例：チルミル・つよいこは5.6gで40ml → 14g）。
- 検索に出てこないセール品などは `amazon_asins` に `{"asin": "...", "grams": 合計g}` で直接指定できる。
- セール・クーポン・キャンペーンのバナーは deals.json に書く。

## 気をつけること
- 自動更新（Actions）が data.json を書き込むので、push の前に必ず `git pull --rebase` する。
- コミットのメールアドレスは必ず `sunnyleaf62-oss@users.noreply.github.com` を使う（`git -c user.name="sunnyleaf62-oss" -c user.email="sunnyleaf62-oss@users.noreply.github.com" commit ...`）。個人のメールアドレスは公開の履歴に残るので使わない。
- 2026年11月1日に履歴を書き換えた（個人情報の削除）。それより前に作ったクローンは使わず、取り直してから作業する。
- 内容量の読み違いを見つけたら、data.json の stats（除外理由の件数）を見て、products.json の must / ng か fetch_prices.py の読み取りを直す。
