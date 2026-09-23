"""Дособирает карточки объявлений: параметры, текст продавца, avgPrice kolesa, номера фото."""
import json
import os
import re
import sys
import time
from concurrent.futures import ThreadPoolExecutor

from bs4 import BeautifulSoup

from scrape_list import DELAY, get

OUT = "data/detail.json"
WORKERS = 3


def parse_detail(html):
    soup = BeautifulSoup(html, "lxml")
    params = {}
    for dl in soup.select(".offer__parameters dl, dl"):
        dt, dd = dl.select_one("dt"), dl.select_one("dd")
        if dt and dd:
            params[dt.get_text(" ", strip=True)] = dd.get_text(" ", strip=True)
    m = re.search(r'"descriptionText":("(?:[^"\\]|\\.)*")', html)
    text = json.loads(m.group(1)) if m else ""
    m = re.search(r'"avgPrice":(\d+)', html)
    avg = int(m.group(1)) if m else None
    options = [x.get_text(strip=True) for x in soup.select(".offer__option-label")]
    photos = {}  # папка фото -> номера (на странице есть и чужие фото из «похожих»)
    for base, n in re.findall(r"(https://kolesa-photos[^\"' ]+/)(\d+)-\d+x\d+\.jpg", html):
        photos.setdefault(base.replace("\\/", "/"), set()).add(int(n))
    photos = {k: sorted(v) for k, v in photos.items()}
    return {"params": params, "text": text, "avg_price": avg, "options": options, "photos": photos}


def fetch(aid):
    html = get(f"https://kolesa.kz/a/show/{aid}")
    time.sleep(DELAY)
    return aid, parse_detail(html) if html else None


def main():
    ids = [int(x) for x in sys.argv[1:]] if len(sys.argv) > 1 else \
        [int(x) for x in open("data/candidates.txt").read().split()]
    done = json.load(open(OUT)) if os.path.exists(OUT) else {}
    todo = [a for a in ids if str(a) not in done]
    with ThreadPoolExecutor(WORKERS) as ex:
        for n, (aid, d) in enumerate(ex.map(fetch, todo), 1):
            if d:
                done[str(aid)] = d
            if n % 25 == 0:
                json.dump(done, open(OUT, "w"), ensure_ascii=False)
                print(f"{n}/{len(todo)}", file=sys.stderr)
    json.dump(done, open(OUT, "w"), ensure_ascii=False)
    print("done", len(done), file=sys.stderr)

if __name__ == "__main__":
    main()
