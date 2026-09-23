"""Собирает все объявления kolesa.kz по городам и лимиту цены (страницы выдачи)."""
import json
import re
import sys
import time

import requests
from bs4 import BeautifulSoup

UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/128.0 Safari/537.36")
CITIES = ["karaganda", "astana"]
PRICE_TO = 1_000_000
DELAY = 1.5

s = requests.Session()
s.headers["User-Agent"] = UA


def get(url, tries=4):
    for i in range(tries):
        try:
            r = s.get(url, timeout=30)
            if r.status_code == 200:
                return r.text
            print("HTTP", r.status_code, url, file=sys.stderr)
        except requests.RequestException as e:
            print("ERR", e, url, file=sys.stderr)
        time.sleep(2 ** (i + 1))
    return None


def parse_page(html, city):
    soup = BeautifulSoup(html, "lxml")
    meta = {}
    for m in re.finditer(r"listing\.items\.push\((\{.*?\})\);", html):
        try:
            d = json.loads(m.group(1))
            meta[d["id"]] = d
        except json.JSONDecodeError:
            pass
    items = []
    for card in soup.select("div.a-card.js__a-card"):
        aid = int(card["data-id"])
        title = card.select_one(".a-card__title")
        price = card.select_one(".a-card__price")
        desc = card.select_one(".a-card__description")
        img = card.select_one("img")
        photo_base = None
        if img and img.get("src"):
            mm = re.match(r"(https://kolesa-photos[^ ]+/)\d+-\d+x\d+\.\w+", img["src"])
            if mm:
                photo_base = mm.group(1)
        md = meta.get(aid, {})
        items.append({
            "id": aid,
            "city": city,
            "title": title.get_text(" ", strip=True) if title else "",
            "name": md.get("name"),
            "brand": md.get("attributes", {}).get("brand"),
            "model": md.get("attributes", {}).get("model"),
            "price": md.get("unitPrice") or int(re.sub(r"\D", "", price.get_text()) or 0),
            "desc": desc.get_text(" ", strip=True) if desc else "",
            "photo_count": md.get("photoCount"),
            "photo_base": photo_base,
            "labels": [x.get_text(strip=True) for x in card.select(".a-label__text")],
            "url": f"https://kolesa.kz/a/show/{aid}",
            "seller_type": md.get("seller", {}).get("userTypeId"),
        })
    pages = [int(x) for x in re.findall(r"[?&]page=(\d+)", html)]
    return items, max(pages or [1])


def main():
    out = {}
    for city in CITIES:
        base = f"https://kolesa.kz/cars/{city}/?price%5Bto%5D={PRICE_TO}"
        page, last = 1, 1
        while page <= last:
            html = get(base + (f"&page={page}" if page > 1 else ""))
            if not html:
                page += 1
                continue
            items, maxp = parse_page(html, city)
            last = max(last, maxp)
            for it in items:
                out[it["id"]] = it
            print(f"{city} p{page}/{last}: +{len(items)} (всего {len(out)})", file=sys.stderr)
            page += 1
            time.sleep(DELAY)
    json.dump(list(out.values()), open("data/list.json", "w"), ensure_ascii=False, indent=1)
    print("done", len(out), file=sys.stderr)


if __name__ == "__main__":
    main()
