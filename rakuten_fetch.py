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
from datetime import datetime, timedelta, timezone

# 2026年の新API。バージョンが廃止されたら新しい日付に書き換える
API_VERSIONS = ["20260701", "20220601"]
API_BASE = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/"

JST = timezone(timedelta(hours=9))
HERE = os.path.dirname(os.path.abspath(__file__))
TOP_N = 5          # 商品ごとに残すショップ数
EXCLUDE_POSTAGE_SEPARATE = True   # 送料別の出品を除外する
WAIT_SEC = 1.2     # APIへのアクセス間隔（QPS 1 以内）


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


# ---------- 商品名から「何缶・何本入りか」を読み取る ----------
COUNT_PATTERNS = [
    r"[×xX✕*]\s*(\d{1,2})\s*(?:缶|個|本|袋|箱|パック|セット)?",
    r"(\d{1,2})\s*(?:缶|個|本|箱|パック)\s*(?:セット|入り?|組)?",
    r"(\d{1,2})\s*セット",
]


def parse_count(name, unit_number):
    t = unicodedata.normalize("NFKC", name)
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


def collect(product, app_id, access_key, aff_id, referer):
    params = {
        "applicationId": app_id,
        "accessKey": access_key,
        "keyword": product["keyword"],
        "NGKeyword": "中古 空き缶 空缶",
        "sort": "+itemPrice",
        "minPrice": product.get("min_price", 1),
        "availability": 1,
        "hits": 30,
        "imageFlag": 1,
        "format": "json",
        "formatVersion": 2,
    }
    if aff_id:
        params["affiliateId"] = aff_id
    data = call_api(params, referer)
    items = data.get("Items") or data.get("items") or []

    offers = []
    unit_number = product.get("unit_g") or product.get("unit_ml")
    for it in items:
        it = it.get("Item", it)   # formatVersion=1 で返ってきた場合にも対応
        name = it.get("itemName", "")
        norm = unicodedata.normalize("NFKC", name)
        if not all(unicodedata.normalize("NFKC", w) in norm for w in product["must"]):
            continue
        if any(unicodedata.normalize("NFKC", w) in norm for w in product.get("ng", [])):
            continue
        postage_separate = it.get("postageFlag") == 1
        if EXCLUDE_POSTAGE_SEPARATE and postage_separate:
            continue

        count = parse_count(name, unit_number) or product.get("default_count", 1)
        if "unit_g" in product:
            ml = product["unit_g"] * count / product["g_per_100ml"] * 100
        else:
            ml = product["unit_ml"] * count
        price = int(it.get("itemPrice", 0))
        if not price:
            continue
        point_rate = int(it.get("pointRate", 1) or 1)
        imgs = it.get("mediumImageUrls") or []
        img = imgs[0] if imgs else ""
        if isinstance(img, dict):
            img = img.get("imageUrl", "")
        offers.append({
            "shop": it.get("shopName", ""),
            "item_name": name,
            "price": price,
            "count": count,
            "ml": round(ml),
            "per100": round(price / ml * 100, 1),
            "point_rate": point_rate,
            "per100_after_points": round(price * (1 - point_rate / 100) / ml * 100, 1),
            "url": it.get("affiliateUrl") or it.get("itemUrl", ""),
            "image": img,
        })

    # 個数の読み違いで極端に安く見えるものを除く（中央値の6割未満）
    if len(offers) >= 3:
        med = statistics.median(o["per100"] for o in offers)
        offers = [o for o in offers if o["per100"] >= med * 0.6]

    offers.sort(key=lambda o: o["per100"])
    return offers[:TOP_N]


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
            offers = collect(p, app_id, access_key, aff_id, referer)
            print(f"OK  {p['brand']} {p['name']}: {len(offers)}件")
        except Exception as e:
            offers = []
            print(f"NG  {p['brand']} {p['name']}: {e}")
        meta = {k: p[k] for k in ("id", "brand", "name", "form")}
        result.append({**meta, "offers": offers})

    out = {"updated": datetime.now(JST).isoformat(timespec="minutes"),
           "source": "楽天市場", "products": result}
    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("data.json を書き出しました")


if __name__ == "__main__":
    main()
