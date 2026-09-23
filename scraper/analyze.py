"""Скоринг объявлений.

stage1: по данным выдачи отсекает мусор и пишет data/candidates.txt для scrape_detail.py
stage2: с деталями (avgPrice kolesa, текст продавца) считает итоговый балл -> data/scored.json
"""
import json
import re
import statistics
import sys
from collections import defaultdict

LIMIT = 700  # сколько лучших по предварительному баллу дособирать
# Покупатель не механик: всё, что намекает на ремонт/вложения, штрафуем сильнее.
BAD_MULT = 1.5

# Надёжные/ликвидные марки получают бонус, «вечно ломающиеся» и ВАЗ-классика — штраф.
BRAND_BONUS = {
    "Toyota": 12, "Lexus": 12, "Honda": 10, "Mitsubishi": 7, "Mazda": 6, "Nissan": 6,
    "Subaru": 4, "Hyundai": 6, "Kia": 5, "Volkswagen": 4, "Skoda": 4, "Audi": 3,
    "Mercedes-Benz": 3, "Suzuki": 5, "Chevrolet": 2, "Daewoo": 1, "Ford": 2, "Opel": 1,
    "ВАЗ (Lada)": -2, "ГАЗ": -6, "УАЗ": -3, "Москвич": -8, "ЗАЗ": -10, "ИЖ": -8,
}

# Однозначно не то: на запчасти, авария, не на ходу, проблемы с документами.
HARD_BAD = [
    r"на запчаст", r"аварийн", r"не на ходу", r"не заводит", r"без документ", r"не растаможен",
    r"на разбор", r"после дтп", r"битая", r"утиль", r"без двигател", r"двигатель не работ",
    r"мотор (?:за)?[её]лин", r"загнал", r"клин", r"под восстановлен", r"под ремонт",
    r"нужно установить", r"требует ремонт", r"документ(?:ы|ов)? нет", r"в залоге", r"под арестом",
]
# «не был в ДТП», «без ржавчины», «залогов нет» и т.п. вырезаем до поиска плохих слов
NEGATED = r"(?:не|без|нет|ни)\s+(?:был[аио]?\s+)?(?:в\s+|под\s+)?\w*(?:дтп|ржав|гнил|стук|залог|арест|вложени|сварк|крашен|удар|аварий)\w*" \
    r"|(?:дтп|залог\w*|арест\w*|ржавчин\w*)\s+(?:нет|не было)"
SOFT_BAD = {
    r"вложени(?:я|й) (?:нужн|требу)": -8, r"требует вложен": -8, r"нужны вложен": -8,
    r"ржав": -6, r"гнил": -8, r"стук": -7, r"дымит": -8, r"жр[её]т масло": -8, r"ест масло": -6,
    r"пинает": -7, r"пинки": -7, r"толчк": -5, r"течь|теч[её]т|потеет": -4, r"перекрас": -3,
    r"крашен": -2, r"дтп": -5, r"срочно": -1, r"не ездит": -10, r"косметик": -2,
    r"генеральн": -3, r"по доверенност": -3, r"сварк": -5, r"вар[иe]л": -3,
    # юридика и агрегаты — ищутся в полном тексте продавца (scrape_detail.py)
    r"\bРФ\b|росс?ийск|на учет[еу] в р": -15, r"запрет": -15, r"без переоформ": -12,
    r"страховк": -6, r"вложени\w* по мотор": -12, r"коробк\w* (?:хруст|воет|выбива|пинает)": -12,
    r"выбивает": -10, r"на заказ": -20,
}
GOOD = {
    r"вложени[йя] не требует|без вложений": 5, r"сел и поехал": 3, r"не бит": 4,
    r"не крашен": 4, r"родн(?:ая|ой) краск": 3, r"один хозяин|1 хозяин|первый хозяин": 4,
    r"гаражн": 2, r"сервисн": 2, r"вс[её] поменян|вс[её] заменен": 2, r"свеж(?:ая|ий) замен": 2,
    r"ухоженн": 2, r"оригинальн(?:ый|ом) пробег|родной пробег": 2, r"пробег родной": 2,
}


def num(s, pat):
    m = re.search(pat, s or "")
    return m.group(1) if m else None


def base_fields(it):
    d = it["desc"]
    year = num(d, r"(\d{4}) г\.") or num(it.get("name") or "", r"(\d{4})")
    km = num(d, r"пробегом ([\d\s\xa0]+) км")
    it["year"] = int(year) if year else None
    it["km"] = int(re.sub(r"\D", "", km)) if km else None
    it["gearbox"] = "автомат" if re.search(r"КПП (?:автомат|вариатор|робот|типтроник)", d) else \
        ("механика" if "механика" in d else None)
    it["fuel"] = num(d, r"л, (\w+)")
    it["body"] = num(d, r"Б/у ([\w-]+)")
    return it


def market_medians(items):
    """Своя медиана цены по марке+модели+году (±1 год) — запасной вариант к avgPrice kolesa."""
    by = defaultdict(list)
    for it in items:
        if it["year"]:
            by[(it["brand"], it["model"])].append((it["year"], it["price"]))
    med = {}
    for it in items:
        pts = [p for y, p in by[(it["brand"], it["model"])] if it["year"] and abs(y - it["year"]) <= 1]
        med[it["id"]] = (statistics.median(pts), len(pts)) if len(pts) >= 4 else (None, len(pts))
    return med


def disc_points(d):
    """Скидка к рынку выгодна до ~30%; сильно дешевле рынка — обычно скрытые проблемы."""
    if d <= 0.3:
        return max(d, -0.3) * 60
    return 18 - (d - 0.3) * 50


def clean(text):
    return re.sub(NEGATED, " ", text or "", flags=re.I)


def hard_bad(text):
    text = clean(text)
    return [p for p in HARD_BAD if re.search(p, text, re.I)]


def stage1():
    items = [base_fields(it) for it in json.load(open("data/list.json"))]
    med = market_medians(items)
    cand = []
    for it in items:
        if it["price"] < 150_000 or (it["photo_count"] or 0) < 4:
            continue
        if hard_bad(it["desc"] + " " + it["title"]):
            continue
        # предварительный балл без деталей: своя медиана, год, пробег, марка
        m = med[it["id"]][0]
        pre = disc_points(1 - it["price"] / m) if m else 0
        pre += ((it["year"] or 1995) - 2000) * 1.2 + BRAND_BONUS.get(it["brand"], 0)
        pre -= max((it["km"] or 250_000) - 150_000, 0) / 20_000
        cand.append((pre, it["id"]))
    cand.sort(reverse=True)
    top = [aid for _, aid in cand[:LIMIT]]
    open("data/candidates.txt", "w").write("\n".join(map(str, top)))
    print(f"всего {len(items)}, прошли фильтр {len(cand)}, на детали {len(top)}", file=sys.stderr)


def stage2():
    items = [base_fields(it) for it in json.load(open("data/list.json"))]
    try:
        det = json.load(open("data/detail.json"))
    except FileNotFoundError:  # карточки не скачались (блок kolesa) — работаем по выдаче
        det = {}
    empty = {"params": {}, "text": "", "avg_price": None, "options": [], "photos": {}}
    med = market_medians(items)
    out = []
    for it in items:
        if hard_bad(it["desc"] + " " + it["title"]) or it["price"] < 150_000:
            continue
        d = det.get(str(it["id"]), empty)
        p = d["params"]
        text = (d["text"] or "") + " " + it["desc"]
        it.update(text=d["text"], options=d["options"], params=p, avg_price=d["avg_price"])
        it["photos"] = [f"{it['photo_base']}{n}-750x470.jpg"
                        for n in d["photos"].get(it["photo_base"], [])] if it["photo_base"] else []
        flags = hard_bad(text)
        if p.get("Растаможен в Казахстане", "Да") != "Да":
            flags.append("не растаможен")
        if p.get("Руль") == "Справа":
            it.setdefault("notes_auto", []).append("правый руль")
        m, n = med[it["id"]]
        if not (d["avg_price"] or m):
            continue  # не с чем сравнить цену
        ref = d["avg_price"] or m
        it["own_median"], it["peers"] = m, n
        it["discount"] = round(1 - it["price"] / ref, 3) if ref else None
        # --- балл ---
        sc, why = 0.0, []
        if it["discount"] is not None:
            sc += disc_points(it["discount"])
            why.append(f"цена {-it['discount']*100:+.0f}% к рынку")
        if it["year"]:
            sc += (it["year"] - 2000) * 1.2
        if not it["km"]:
            sc -= 2  # пробег не указан
        else:
            sc -= max(it["km"] - 150_000, 0) / 20_000
            if it["km"] < 30_000 and it["year"] and it["year"] < 2012:
                sc -= 4
                why.append("подозрительно малый пробег")
        sc += BRAND_BONUS.get(it["brand"], 0)
        ct = clean(text)
        for pat, w in {**SOFT_BAD, **GOOD}.items():
            if re.search(pat, text if w > 0 else ct, re.I):
                w = w * BAD_MULT if w < 0 else w
                sc += w
                why.append(("+" if w > 0 else "") + f"{w} «{pat.split('|')[0]}»")
        sc += min(len(it["photos"]) or it["photo_count"] or 0, 12) * 0.5
        if it["gearbox"] == "автомат":
            sc += 2
        it["flags"], it["score"], it["why"] = flags, round(sc, 1), why
        out.append(it)
    out.sort(key=lambda x: (not x["flags"], x["score"]), reverse=True)
    json.dump(out, open("data/scored.json", "w"), ensure_ascii=False, indent=1)
    ok = [x for x in out if not x["flags"]]
    print(f"оценено {len(out)}, без флагов {len(ok)}", file=sys.stderr)
    for x in ok[:40]:
        print(x["score"], x["id"], x["city"], x["name"], x["price"], x["avg_price"],
              x["km"], x["gearbox"], x["discount"], "; ".join(x["why"]))


if __name__ == "__main__":
    {"1": stage1, "2": stage2}[sys.argv[1]]()
