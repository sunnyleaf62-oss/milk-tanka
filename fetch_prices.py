"""
ミルク単価くらべ: 楽天市場とYahoo!ショッピングから粉ミルクの価格を集めて data.json を作る

環境変数（GitHubのSecretsに登録。コードに直接書かないこと）
  楽天
    RAKUTEN_APP_ID        アプリケーションID
    RAKUTEN_ACCESS_KEY    アクセスキー
    RAKUTEN_AFFILIATE_ID  アフィリエイトID
    RAKUTEN_REFERER       楽天のアプリ登録で許可したサイトのURL
  Yahoo!ショッピング（未設定ならYahoo!はスキップ）
    YAHOO_CLIENT_ID       Yahoo!デベロッパーネットワークのClient ID
    VC_SID / VC_PID       バリューコマースのYahoo!ショッピング用 sid と pid
                          （未設定でも動くが、リンクに報酬が付かない）
  Amazon（未設定ならAmazonはスキップ）
    AMAZON_CREDENTIAL_ID / AMAZON_CREDENTIAL_SECRET  Creators APIの認証情報
    AMAZON_API_VERSION    認証情報のバージョン（例 3.3）
    AMAZON_PARTNER_TAG    アソシエイトのトラッキングID（例 xxxx-22）
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

RAKUTEN_VERSIONS = ["20260701", "20220601"]
RAKUTEN_BASE = "https://openapi.rakuten.co.jp/ichibams/api/IchibaItem/Search/"
YAHOO_URL = "https://shopping.yahooapis.jp/ShoppingWebService/V3/itemSearch"

JST = timezone(timedelta(hours=9))
HERE = os.path.dirname(os.path.abspath(__file__))
TOP_N = 10           # 商品ごとに残すショップ数（全モールの合計）
RAKUTEN_PAGES = 3    # 楽天: 1ページ30件
YAHOO_PAGES = 2      # Yahoo!: 1ページ50件
AMAZON_PAGES = 3     # Amazon: 1ページ10件
WAIT_SEC = 1.2       # APIへのアクセス間隔（どちらも1秒1回まで）
# 送料の金額はAPIでわからないため、送料無料でない出品にはこの目安額を足す
SHIPPING_ESTIMATE = 800


def env(name, required=False):
    v = os.environ.get(name, "").strip()
    if required and not v:
        sys.exit(f"環境変数 {name} が設定されていません")
    return v


def get_json(url, headers=None):
    req = urllib.request.Request(url, headers={"User-Agent": "milk-tanka/1.0", **(headers or {})})
    with urllib.request.urlopen(req, timeout=20) as r:
        return json.load(r)


def nfkc(s):
    return unicodedata.normalize("NFKC", s)


# ================= 楽天 =================
def rakuten_call(params, referer):
    headers = {"Referer": referer, "Origin": referer.rstrip("/")}
    last_err = None
    for ver in RAKUTEN_VERSIONS:
        url = RAKUTEN_BASE + ver + "?" + urllib.parse.urlencode(params)
        try:
            return get_json(url, headers)
        except urllib.error.HTTPError as e:
            last_err = f"HTTP {e.code} ({ver}): {e.read().decode('utf-8', 'replace')[:300]}"
            if e.code == 404:
                continue
            break
    raise RuntimeError(last_err)


def rakuten_items(product, cfg, shop_code=None):
    out = []
    for page in range(1, (1 if shop_code else RAKUTEN_PAGES) + 1):
        params = {
            "applicationId": cfg["app_id"], "accessKey": cfg["access_key"],
            "keyword": product["keyword"], "NGKeyword": "中古 空き缶 空缶",
            "sort": "+itemPrice", "minPrice": product.get("min_price", 1),
            "availability": 1, "hits": 30, "page": page, "imageFlag": 1,
            "format": "json", "formatVersion": 2,
        }
        if cfg["aff_id"]:
            params["affiliateId"] = cfg["aff_id"]
        if shop_code:
            params["shopCode"] = shop_code
            params["keyword"] = product.get("shop_keyword") or product["keyword"].replace("大缶", "").strip()
        if page > 1:
            time.sleep(WAIT_SEC)
        data = rakuten_call(params, cfg["referer"])
        for it in data.get("Items") or data.get("items") or []:
            it = it.get("Item", it)
            imgs = it.get("mediumImageUrls") or []
            img = imgs[0] if imgs else ""
            if isinstance(img, dict):
                img = img.get("imageUrl", "")
            out.append({
                "mall": "楽天",
                "name": it.get("itemName", ""),
                "price": int(it.get("itemPrice", 0) or 0),
                "free_shipping": it.get("postageFlag") == 0,
                "shop": it.get("shopName", ""),
                "url": it.get("affiliateUrl") or it.get("itemUrl", ""),
                "image": img,
                "point_rate": int(it.get("pointRate", 1) or 1),
            })
        if page >= int(data.get("pageCount", 1) or 1):
            break
    return out


# ================= Yahoo!ショッピング =================
def vc_link(url, sid, pid):
    if not (sid and pid):
        return url
    return ("https://ck.jp.ap.valuecommerce.com/servlet/referral?"
            f"sid={sid}&pid={pid}&vc_url=" + urllib.parse.quote(url, safe=""))


def yahoo_items(product, cfg):
    out = []
    for page in range(YAHOO_PAGES):
        params = {
            "appid": cfg["client_id"], "query": product["keyword"],
            "results": 50, "start": 1 + page * 50, "sort": "+price",
            "price_from": product.get("min_price", 1), "in_stock": "true",
            "image_size": 146,
        }
        if page:
            time.sleep(WAIT_SEC)
        try:
            data = get_json(YAHOO_URL + "?" + urllib.parse.urlencode(params))
        except urllib.error.HTTPError as e:
            raise RuntimeError(f"HTTP {e.code}: {e.read().decode('utf-8', 'replace')[:300]}")
        hits = data.get("hits") or []
        for h in hits:
            name = h.get("name", "")
            if any(w in name for w in ("中古", "空き缶", "空缶")):
                continue
            ship = (h.get("shipping") or {}).get("code")
            img = h.get("image") or {}
            out.append({
                "mall": "Yahoo!",
                "name": name,
                "price": int(h.get("price", 0) or 0),
                "free_shipping": ship == 2,          # 2 = 送料無料
                "shop": (h.get("seller") or {}).get("name", ""),
                "url": vc_link(h.get("url", ""), cfg["vc_sid"], cfg["vc_pid"]),
                "image": img.get("medium") or img.get("small") or "",
                "point_rate": int((h.get("point") or {}).get("times", 1) or 1),
            })
        if len(hits) < 50:
            break
    return out


# ================= Amazon（Creators API） =================
def _get(obj, *path):
    for p in path:
        if obj is None:
            return None
        obj = obj[p] if isinstance(p, int) else getattr(obj, p, None)
    return obj


def _amazon_item(it):
    listings = _get(it, "offers_v2", "listings") or []
    if not listings:
        return None
    lst = listings[0]
    amount = _get(lst, "price", "money", "amount")
    if not amount:
        return None
    merchant = _get(lst, "merchant_info", "name") or "Amazon"
    return {
        "mall": "Amazon",
        "name": _get(it, "item_info", "title", "display_value") or "",
        "price": int(round(float(amount))),
        # Amazon販売分は送料無料として扱い、他の出品者は目安送料を足す
        "free_shipping": "amazon" in merchant.lower(),
        "shop": merchant,
        "url": _get(it, "detail_page_url") or "",
        "image": _get(it, "images", "primary", "medium", "url")
                 or _get(it, "images", "primary", "large", "url") or "",
        "point_rate": 1,
    }


def amazon_items(product, cfg):
    from amazon_creatorsapi import AmazonCreatorsApi, Country
    from amazon_creatorsapi.models import SortBy

    if "client" not in cfg:
        cfg["client"] = AmazonCreatorsApi(
            credential_id=cfg["credential_id"], credential_secret=cfg["credential_secret"],
            version=cfg["version"], tag=cfg["tag"], country=Country.JP)
    api = cfg["client"]
    out = []
    for page in range(1, AMAZON_PAGES + 1):
        if page > 1:
            time.sleep(WAIT_SEC)
        try:
            res = api.search_items(keywords=product["keyword"], item_count=10, item_page=page,
                                   sort_by=SortBy.PRICE_COLON_LOW_TO_HIGH)
        except Exception as e:
            if type(e).__name__ == "ItemsNotFoundError":
                break
            raise
        items = _get(res, "items") or []
        out += [x for x in (_amazon_item(it) for it in items) if x]
        if len(items) < 10:
            break
    # products.json の amazon_asins：検索に出てこないセール品などをASINで直接取りにいく
    #   文字列（ASINだけ）か {"asin": ..., "grams": 合計g} の形。grams を書くと商品名を読まずにその量で計算する
    pins = [a if isinstance(a, dict) else {"asin": a} for a in (product.get("amazon_asins") or [])]
    if pins:
        time.sleep(WAIT_SEC)
        by_asin = {pin["asin"]: pin for pin in pins}
        try:
            for it in api.get_items(list(by_asin)) or []:
                x = _amazon_item(it)
                pin = by_asin.get(_get(it, "asin"))
                if x and pin:
                    x["pinned"] = True
                    for k in ("grams", "ml"):
                        if pin.get(k):
                            x["fixed_" + k] = pin[k]
                    out.append(x)
        except Exception as e:
            if type(e).__name__ != "ItemsNotFoundError":
                raise
    return out


# ================= 内容量の読み取り =================
COUNT_PATTERNS = [
    r"[×xX✕*]\s*(\d{1,2})\s*(?:缶|個|本|袋|箱|パック|セット)?",
    r"(\d{1,2})\s*(?:缶|個|本|箱|パック)\s*(?:セット|入り?|組)?",
    r"(\d{1,2})\s*セット",
]
CHOICE_PATTERN = r"\d+\s*(?:缶|本|個|箱|袋)\s*(?:/|／|・|or)\s*\d+\s*(?:缶|本|個|箱|袋)"


def parse_count(name, unit_number):
    t = nfkc(name)
    t = re.sub(rf"{unit_number}\s*(?:g|ml|グラム)", " ", t, flags=re.I)
    found = [int(m.group(1)) for p in COUNT_PATTERNS for m in re.finditer(p, t)
             if 1 <= int(m.group(1)) <= 48]
    if not found:
        return None
    hon = [int(x) for x in re.findall(r"(\d{1,2})\s*本", t)]
    hako = [int(x) for x in re.findall(r"[×xX*]?\s*(\d{1,2})\s*(?:箱|ケース)", t)]
    if hon and hako:
        return max(hon) * max(hako)
    return max(found)


def parse_total_grams(name):
    """粉ミルク・キューブ・スティック用。商品名から合計グラムを読む"""
    t = nfkc(name)
    # 「2缶入×3セット(1缶810g)」「2袋入×4箱(1袋400g)」＝ 入数 × セット数 × 1個の量
    per = re.search(r"1\s*(?:缶|袋|個|本|箱)\s*(\d{3,4})\s*g", t, flags=re.I)
    nest = re.search(r"(\d{1,2})\s*(?:缶|袋|個|本)\s*入?\s*[×xX✕*]\s*(\d{1,2})\s*(?:個)?\s*(?:セット|箱|ケース|個|パック)", t)
    if per and nest:
        return int(per.group(1)) * int(nest.group(1)) * int(nest.group(2))
    big = [int(x) for x in re.findall(r"(\d{3,4})\s*g", t, flags=re.I)]
    if big:
        g = max(big)
        # 「1560g(780g×2缶)」のように合計と内訳が両方あるときは合計だけを使う
        if any(abs(g - o * k) <= 2 for o in set(big) if o < g for k in range(2, 49)):
            return g
        # 「400g×2袋」（詰め替え）は袋数を掛ける
        bag = re.search(rf"{g}\s*g\s*[×xX*]\s*(\d{{1,2}})\s*袋", t, flags=re.I)
        if bag:
            rest = t[bag.end():]
            more = re.search(r"[×xX*]\s*(\d{1,2})\s*(?:箱|個|セット|パック)", rest)
            return g * int(bag.group(1)) * (int(more.group(1)) if more else 1)
        # 「108g (200mL分×4袋入)」「560g (28g×20袋)」の袋数は内訳なので掛けない
        t2 = re.sub(r"\d+\s*ml分?\s*[×xX*]\s*\d+\s*袋入?", " ", t, flags=re.I)
        t2 = re.sub(r"\d+\s*袋", " ", t2)
        return g * (parse_count(t2, g) or 1)
    m = re.search(r"(\d+(?:\.\d+)?)\s*g\s*[×xX*]\s*(\d+)", t, flags=re.I)
    if m:
        total = float(m.group(1)) * int(m.group(2))
        rest = t[m.end():]
        box = re.search(r"[×xX*]\s*(\d{1,2})\s*(?:箱|個|セット|パック)", rest)
        return total * (int(box.group(1)) if box else 1)
    return None


def parse_total_ml(name, default_count=1):
    """液体ミルク用。「200ml×24本」などから合計mlを読む"""
    t = nfkc(name)
    t = re.sub(r"\d+\s*ml分", " ", t, flags=re.I)
    sizes = [int(x) for x in re.findall(r"(\d{2,3})\s*ml", t, flags=re.I)]
    if not sizes:
        return None
    unit = max(set(sizes), key=sizes.count)
    return unit * (parse_count(t, unit) or default_count)


# ================= ショップのクーポン（deals.json） =================
def load_deals():
    path = os.path.join(HERE, "deals.json")
    if not os.path.exists(path):
        return {}
    with open(path, encoding="utf-8") as f:
        return json.load(f)


DEALS = load_deals()
SHOP_SEARCH = [s["shop_code"] for s in DEALS.get("shop_coupons", []) if s.get("shop_code")]


def shop_coupon(it):
    """楽天24などショップ全体のクーポン。金額の条件に合う一番大きいものを1枚だけ使う。
    翌朝の更新まで表示が残るので、期限の24時間前を過ぎたら使わない"""
    if it["mall"] != "楽天":
        return 0, ""
    soon = datetime.now(JST) + timedelta(hours=24)
    best = (0, "")
    for sc in DEALS.get("shop_coupons", []):
        if not it["shop"].startswith(sc["shop_prefix"]):
            continue
        if sc.get("until") and datetime.fromisoformat(sc["until"]) <= soon:
            continue
        for tier in sc["tiers"]:
            if it["price"] >= tier["min_price"] and tier["amount"] > best[0]:
                best = (tier["amount"], sc["note"])
    return best


def to_offer(product, it, stats):
    name, norm = it["name"], nfkc(it["name"])
    pinned = it.get("pinned")  # ASINで指定した商品は名前のチェックを省く
    if not pinned and not all(nfkc(w) in norm for w in product.get("must", [])):
        stats["条件の言葉なし"] += 1
        return None
    if not pinned and product.get("must_any") and not any(nfkc(w) in norm for w in product["must_any"]):
        stats["条件の言葉なし"] += 1
        return None
    if not pinned and any(nfkc(w) in norm for w in product.get("ng", [])):
        stats["除外ワード"] += 1
        return None
    if not pinned and re.search(CHOICE_PATTERN, norm) or not pinned and re.search(r"[×xX*]\s*\d+\s*(?:缶|本|個|袋|箱)\s*[/／]\s*\d", norm):
        stats["数量を選ぶ出品"] += 1
        return None
    if not it["price"]:
        return None

    unit_number = product.get("unit_g") or product.get("unit_ml")
    count = None
    if it.get("fixed_ml") or it.get("fixed_grams"):
        ml = it.get("fixed_ml") or it["fixed_grams"] / product["g_per_100ml"] * 100
    elif product.get("liquid"):
        ml = parse_total_ml(name)
        if not ml:
            stats["内容量が読めない"] += 1
            return None
    elif product.get("parse_size"):
        grams = parse_total_grams(name)
        if not grams:
            stats["内容量が読めない"] += 1
            return None
        ml, count = grams / product["g_per_100ml"] * 100, None
    else:
        count = parse_count(name, unit_number) or product.get("default_count", 1)
        ml = (product["unit_g"] * count / product["g_per_100ml"] * 100
              if "unit_g" in product else product["unit_ml"] * count)

    # 楽天24（ベビー館など）は39ショップ：3,980円以上は送料無料（API上は「送料別」と返ることがある）
    if it["mall"] == "楽天" and it["shop"].startswith("楽天24") and it["price"] >= 3980:
        it = {**it, "free_shipping": True}
    shipping = 0 if it["free_shipping"] else SHIPPING_ESTIMATE
    total = it["price"] + shipping
    coupon, coupon_note = shop_coupon(it)
    total -= coupon
    pr = it["point_rate"]
    return {
        "mall": it["mall"], "shop": it["shop"], "item_name": name,
        "price": it["price"], "postage_separate": not it["free_shipping"],
        "shipping_estimate": shipping, "total": total, "count": count,
        "ml": round(ml), "per100": round(total / ml * 100, 1),
        "point_rate": pr,
        "per100_after_points": round((total - (it["price"] - coupon) * pr / 100) / ml * 100, 1),
        "url": it["url"], "image": it["image"],
        **({"coupon": coupon, "coupon_note": coupon_note} if coupon else {}),
    }


def build(product, raw_items):
    stats = Counter(fetched=len(raw_items))
    offers = [o for o in (to_offer(product, it, stats) for it in raw_items) if o]
    if product.get("min_per100"):
        # 液体ミルクは割高な単品出品が多く中央値が当てにならないので、下限の単価で読み違いを除く
        before = len(offers)
        offers = [o for o in offers if o["per100"] >= product["min_per100"]]
        stats["安すぎて除外"] += before - len(offers)
    elif len(offers) >= 3:
        med = statistics.median(o["per100"] for o in offers)
        before = len(offers)
        offers = [o for o in offers if o["per100"] >= med * 0.6]
        stats["安すぎて除外"] += before - len(offers)
    best = {}
    for o in sorted(offers, key=lambda o: o["per100"]):
        best.setdefault((o["mall"], o["shop"]), o)
    offers = sorted(best.values(), key=lambda o: o["per100"])
    stats["使えた件数"] = len(offers)
    return offers[:TOP_N], dict(stats)


def main():
    rk = {"app_id": env("RAKUTEN_APP_ID"), "access_key": env("RAKUTEN_ACCESS_KEY"),
          "aff_id": env("RAKUTEN_AFFILIATE_ID"), "referer": env("RAKUTEN_REFERER")}
    yh = {"client_id": env("YAHOO_CLIENT_ID"), "vc_sid": env("VC_SID"), "vc_pid": env("VC_PID")}
    use_rakuten = all(rk[k] for k in ("app_id", "access_key", "referer"))
    use_yahoo = bool(yh["client_id"])
    az = {"credential_id": env("AMAZON_CREDENTIAL_ID"), "credential_secret": env("AMAZON_CREDENTIAL_SECRET"),
          "version": env("AMAZON_API_VERSION") or "3.3", "tag": env("AMAZON_PARTNER_TAG")}
    use_amazon = all(az[k] for k in ("credential_id", "credential_secret", "tag"))
    if not (use_rakuten or use_yahoo or use_amazon):
        sys.exit("楽天かYahoo!のキーが設定されていません")
    print(f"楽天: {'ON' if use_rakuten else 'OFF'} / Yahoo!: {'ON' if use_yahoo else 'OFF'}"
          f" / Amazon: {'ON' if use_amazon else 'OFF'}")

    with open(os.path.join(HERE, "products.json"), encoding="utf-8") as f:
        products = json.load(f)

    result = []
    for p in products:
        raw, errors = [], {}
        for mall, on, fn, cfg in (("楽天", use_rakuten, rakuten_items, rk),
                                  ("Yahoo!", use_yahoo, yahoo_items, yh),
                                  ("Amazon", use_amazon, amazon_items, az)):
            if not on:
                continue
            time.sleep(WAIT_SEC)
            try:
                raw += fn(p, cfg)
                for kw in p.get("extra_keywords", []):
                    time.sleep(WAIT_SEC)
                    raw += fn({**p, "keyword": kw}, cfg)
                if mall == "楽天":
                    for code in SHOP_SEARCH:
                        time.sleep(WAIT_SEC)
                        raw += fn(p, cfg, code)
            except Exception as e:
                errors[mall] = str(e)[:300]
                print(f"NG  {mall} {p['brand']} {p['name']}: {e}")
        offers, stats = build(p, raw)
        stats["malls"] = Counter(o["mall"] for o in offers)
        if errors:
            stats["errors"] = errors
        print(f"OK  {p['brand']} {p['name']}: {stats}")
        meta = {k: p[k] for k in ("id", "target", "brand", "name", "form", "g_per_100ml", "g_note") if k in p}
        result.append({**meta, "offers": offers, "stats": stats})

    out = {"updated": datetime.now(JST).isoformat(timespec="minutes"),
           "sources": [m for m, on in (("楽天市場", use_rakuten), ("Yahoo!ショッピング", use_yahoo), ("Amazon", use_amazon)) if on],
           "shipping_estimate": SHIPPING_ESTIMATE, "products": result,
           "events": DEALS.get("events", [])}
    with open(os.path.join(HERE, "data.json"), "w", encoding="utf-8") as f:
        json.dump(out, f, ensure_ascii=False, indent=2)
    print("data.json を書き出しました")


if __name__ == "__main__":
    main()
