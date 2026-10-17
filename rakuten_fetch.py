"""
ミルク単価くらべ: 楽天市場から粉ミルクの価格を集めて data.json を作るスクリプト

使い方:
  環境変数に次の4つを入れてから実行します（キーはコードに直接書かないこと）
    RAKUTEN_APP_ID        アプリケーションID
    RAKUTEN_ACCESS_KEY    アクセスキー
    RAKUTEN_AFFILIATE_ID  アフィリエイトID（なくても動くがリンクに報酬が付かない）
    RAKUTEN_REFERER       アプリ登録の「許可されたウェブサイト」に入れたサイトのURL
                          例: https://www.threads.com/
  python rakuten_fetch.py
"""
import json
import os
import re
import statistics
import sys
import time
import unicodedata
import urllib.error
import urllib.parse
import urllib.request
from collections import Counter
from datetime import datetime, timedelta, timezone

# 2026年の新API。バージョンが廃止されたら新しい日付に書き換える
API_VERSIONS = ["20260701", "20220601"]
API_BASE = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/"

JST = timezone(timedelta(hours=9))
HERE = os.path.dirname(os.path.abspath(__file__))
TOP_N = 5            # 商品ごとに残すショップ数
PAGES = 3            # 1商品あたり何ページ（1ページ30件）見るか
WAIT_SEC = 1.2       # APIへのアクセス間隔（QPS 1 以内）
# 楽天APIは「送料別」かどうかしか返さず、送料の金額はわからない。
# そのため送料別の出品には、この目安額を足して比較する
SHIPPING_ESTIMATE = 800


def env(name, required=True):
    v = os.environ.get(name, "").strip()
    if required and not v:
        sys.exit(f"環境変数 {name} が設定されていません")
    return v


def call_api(params, referer):
    headers = {"Referer": referer, "Origin": referer.rstrip("/"),
               "User-Agent": "milk-tanka/1.0"}
    last_err = None
    for ver in API_VERSIONS:
        url = API_BASE + ver + "?" + urllib.parse.urlencode(params)
        req = urllib.request.Request(url, headers=headers)
        try:
            with urllib.request.urlopen(req, timeout=20) as r:
                return json.load(r)
        except urllib.error.HTTPError as e:
            body = e.read().decode("utf-8", "replace")
            last_err = f"HTTP {e.code} ({ver}): {body[:300]}"
            if e.code == 404:      # このバージョンが無ければ次を試す
                continue
            break
    raise RuntimeError(last_err)


def nfkc(s):
    return unicodedata.normalize("NFKC", s)


# ---------- 商品名から「何缶・何本入りか」を読み取る ----------
COUNT_PATTERNS = [
    r"[×xX✕*]\s*(\d{1,2})\s*(?:缶|個|本|袋|箱|パック|セット)?",
    r"(\d{1,2})\s*(?:缶|個|本|箱|パック)\s*(?:セット|入り?|組)?",
    r"(\d{1,2})\s*セット",
]


def parse_count(name, unit_number):
    t = nfkc(name)
    # 「800g」「240ml」など内容量そのものの数字は取り除く
    t = re.sub(rf"{unit_number}\s*(?:g|ml|グラム)", " ", t, flags=re.I)
    found = []
    for p in COUNT_PATTERNS:
        for m in re.finditer(p, t):
            n = int(m.group(1))
            if 1 <= n <= 48:
                found.append(n)
    if not found:
        return None
    # 「24本×2箱」のように本数と箱数が両方ある場合は掛け算
    hon = [int(x) for x in re.findall(r"(\d{1,2})\s*本", t)]
    hako = [int(x) for x in re.findall(r"[×xX*]?\s*(\d{1,2})\s*(?:箱|ケース)", t)]
    if hon and hako:
        return max(hon) * max(hako)
    return max(found)


def parse_total_grams(name):
    """キューブなど内容量がいろいろな商品用。商品名から合計グラムを読む"""
    t = nfkc(name)
    big = [int(x) for x in re.findall(r"(\d{3,4})\s*g", t, flags=re.I)]
    if big:
        g = max(big)
        # 「108g (200mL分×4袋入)」の袋数は内容量の内訳なので掛けない
        t2 = re.sub(r"\d+\s*ml分?\s*[×xX*]\s*\d+\s*袋入?", " ", t, flags=re.I)
        t2 = re.sub(r"\d+\s*袋", " ", t2)
        return g * (parse_count(t2, g) or 1)
    m = re.search(r"(\d+(?:\.\d+)?)\s*g\s*[×xX*]\s*(\d+)", t, flags=re.I)
    if m:
        return float(m.group(1)) * int(m.group(2))
    return None


def fetch_items(product, app_id, access_key, aff_id, referer):
    items = []
    for page in range(1, PAGES + 1):
        params = {
            "applicationId": app_id,
            "accessKey": access_key,
            "keyword": product["keyword"],
            "NGKeyword": "中古 空き缶 空缶",
            "sort": "+itemPrice",
            "minPrice": product.get("min_price", 1),
            "availability": 1,
            "hits": 30,
            "page": page,
            "imageFlag": 1,
            "format": "json",
            "formatVersion": 2,
        }
        if aff_id:
            params["affiliateId"] = aff_id
        if page > 1:
            time.sleep(WAIT_SEC)
        data = call_api(params, referer)
        got = data.get("Items") or data.get("items") or []
        items += [it.get("Item", it) for it in got]
        if page >= int(data.get("pageCount", 1) or 1):
            break
    return items


def collect(product, app_id, access_key, aff_id, referer):
    items = fetch_items(product, app_id, access_key, aff_id, referer)
    stats = Counter(fetched=len(items))

    offers = []
    unit_number = product.get("unit_g") or product.get("unit_ml")
    for it in items:
        name = it.get("itemName", "")
        norm = nfkc(name)
        if not all(nfkc(w) in norm for w in product["must"]):
            stats["条件の言葉なし"] += 1
            continue
        if any(nfkc(w) in norm for w in product.get("ng", [])):
            stats["除外ワード"] += 1
            continue
        # 「12缶/24缶」のように数量を選ぶ出品は価格がどれのものかわからないので除外
        if re.search(r"\d+\s*(?:缶|本|個|箱|袋)\s*(?:/|／|・|or)\s*\d+\s*(?:缶|本|個|箱|袋)", norm):
            stats["数量を選ぶ出品"] += 1
            continue

        if product.get("parse_size"):
            grams = parse_total_grams(name)
            if not grams:
                stats["内容量が読めない"] += 1
                continue
            ml = grams / product["g_per_100ml"] * 100
            count = None
        else:
            count = parse_count(name, unit_number) or product.get("default_count", 1)
            if "unit_g" in product:
                ml = product["unit_g"] * count / product["g_per_100ml"] * 100
            else:
                ml = product["unit_ml"] * count

        price = int(it.get("itemPrice", 0))
        if not price:
            continue
        postage_separate = it.get("postageFlag") == 1
        shipping = SHIPPING_ESTIMATE if postage_separate else 0
        total = price + shipping
        point_rate = int(it.get("pointRate", 1) or 1)
        imgs = it.get("mediumImageUrls") or []
        img = imgs[0] if imgs else ""
        if isinstance(img, dict):
            img = img.get("imageUrl", "")
        offers.append({
            "shop": it.get("shopName", ""),
            "item_name": name,
            "price": price,
            "postage_separate": postage_separate,
            "shipping_estimate": shipping,
            "total": total,
            "count": count,
            "ml": round(ml),
            "per100": round(total / ml * 100, 1),
            "point_rate": point_rate,
            "per100_after_points": round((total - price * point_rate / 100) / ml * 100, 1),
            "url": it.get("affiliateUrl") or it.get("itemUrl", ""),
            "image": img,
        })

    # 個数の読み違いで極端に安く見えるものを除く（中央値の6割未満）
    if len(offers) >= 3:
        med = statistics.median(o["per100"] for o in offers)
        before = len(offers)
        offers = [o for o in offers if o["per100"] >= med * 0.6]
        stats["安すぎて除外"] += before - len(offers)

    # 同じショップの重複は一番安いものだけ残す
    best = {}
    for o in sorted(offers, key=lambda o: o["per100"]):
        best.setdefault(o["shop"], o)
    offers = sorted(best.values(), key=lambda o: o["per100"])
    stats["使えた件数"] = len(offers)
    return offers[:TOP_N], dict(stats)


def main():
    app_id = env("RAKUTEN_APP_ID")
    access_key = env("RAKUTEN_ACCESS_KEY")
    aff_id = env("RAKUTEN_AFFILIATE_ID", required=False)
    referer = env("RAKUTEN_REFERER")

    with open(os.path.join(HERE, "products.json"), encoding="utf-8") as f:
        products = json.load(f)

    result = []
    for i, p in enumerate(products):
        if i:
            time.sleep(WAIT_SEC)
        try:
            offers, stats = collect(p, app_id, access_key, aff_id, referer)
            print(f"OK  {p['brand']} {p['name']}: {stats}")
        except Exception as e:
            offers, stats = [], {"error": str(e)[:300]}
            print(f"NG  {p['brand']} {p['name']}: {e}")
        meta = {k: p[k] for k in ("id", "brand", "name", "form")}
        result.append({**meta, "offers": offers, "stats": stats})

    out = {"updated": datetime.now(JST).isoformat(timespec="minutes"),
           "source": "楽天市場", "shipping_estimate": SHIPPING_ESTIMATE,
           "products": result}
    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("data.json を書き出しました")


if __name__ == "__main__":
    main()
