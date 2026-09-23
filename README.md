# Парсер kolesa.kz: машины до 1 млн ₸ в Караганде и Астане

Запускать с **домашнего IP**: сервер Claude kolesa.kz заблокировал. С обычного
интернета со скоростью 1 запрос в 1,5 с блока быть не должно.

```bash
pip install requests beautifulsoup4 lxml pillow
cd scraper
python3 scrape_list.py        # выдача -> data/list.json (~5 мин)
python3 analyze.py 1          # фильтр + предварительный балл -> data/candidates.txt
python3 scrape_detail.py      # полный текст продавца, avgPrice kolesa (~700 карточек, ~20 мин)
python3 analyze.py 2          # итоговый балл с полным текстом -> data/scored.json
python3 photos.py 40          # листы с фото топ-40 -> data/sheets/
```

- Город и лимит цены: `CITIES` и `PRICE_TO` в `scrape_list.py`.
- Стоп-слова и веса: `HARD_BAD`, `SOFT_BAD`, `GOOD` в `analyze.py`.
- Не ставьте `WORKERS` больше 1–2: kolesa режет частые запросы.
