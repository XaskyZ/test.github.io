"""Качает фото топ-N кандидатов с CDN kolesa и собирает листы-превью для ручного осмотра."""
import io
import json
import os
import sys
from concurrent.futures import ThreadPoolExecutor

import requests
from PIL import Image, ImageDraw

N = int(sys.argv[1]) if len(sys.argv) > 1 else 30
MAX_PHOTOS = 12
W, H = 480, 300


def fetch(url):
    try:
        r = requests.get(url, timeout=20)
        if r.status_code == 200:
            return Image.open(io.BytesIO(r.content)).convert("RGB")
    except (requests.RequestException, OSError):
        pass
    return None


def photos_for(it):
    """Номера фото на CDN идут не всегда подряд — перебираем с запасом."""
    want = min(it["photo_count"] or 0, MAX_PHOTOS)
    urls = [f"{it['photo_base']}{n}-750x470.jpg" for n in range(1, want + 6)]
    with ThreadPoolExecutor(6) as ex:
        imgs = list(ex.map(fetch, urls))
    got = [(u, im) for u, im in zip(urls, imgs) if im][:want]
    return got


def sheet(it, got, path):
    cols = 4
    rows = (len(got) + cols - 1) // cols
    img = Image.new("RGB", (cols * W, rows * H + 30), "white")
    d = ImageDraw.Draw(img)
    d.text((8, 8), f"{it['id']} {it['name']} {it['price']:,} T  {it['km']} km  {it['city']}", fill="black")
    for i, (_, im) in enumerate(got):
        im.thumbnail((W, H))
        img.paste(im, ((i % cols) * W, 30 + (i // cols) * H))
    img.save(path, quality=80)


def main():
    items = [x for x in json.load(open("data/scored.json")) if not x["flags"]][:N]
    os.makedirs("data/sheets", exist_ok=True)
    for it in items:
        got = photos_for(it)
        it["photos"] = [u for u, _ in got]
        if got:
            sheet(it, got, f"data/sheets/{it['id']}.jpg")
        print(it["id"], len(got), file=sys.stderr)
    json.dump(items, open("data/top.json", "w"), ensure_ascii=False, indent=1)


if __name__ == "__main__":
    main()
