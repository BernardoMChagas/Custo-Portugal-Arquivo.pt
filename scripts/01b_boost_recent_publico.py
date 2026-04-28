# -*- coding: utf-8 -*-
# scripts/01b_boost_recent_publico.py
# Recolha suplementar para:
#   A) Anos 2021-2024 (cobertura temporal em falta)
#   B) Público com formato http://www.publico.pt (Menção Honrosa)
#
# Executa DEPOIS de 01_collect_arquivo.py

import requests, json, time, os

BASE_URL   = "https://arquivo.pt/textsearch"
OUTPUT_DIR = "data/raw"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PAGE_SIZE  = 50
SLEEP      = 1.0

# ─── A) Queries dedicadas a 2021-2024 ────────────────────────────────────────
QUERIES_RECENT = [
    # Habitação recente
    {"id":"boost_hab_2021","q":"habitação preço arrendamento Lisboa renda",
     "from":"20210101","to":"20211231"},
    {"id":"boost_hab_2022","q":"habitação preço arrendamento Lisboa renda",
     "from":"20220101","to":"20221231"},
    {"id":"boost_hab_2023","q":"habitação preço arrendamento Lisboa renda",
     "from":"20230101","to":"20231231"},
    {"id":"boost_hab_2024","q":"habitação preço arrendamento Lisboa renda",
     "from":"20240101","to":"20241231"},
    # Inflação recente
    {"id":"boost_inf_2021","q":"inflação preços Portugal famílias custo vida",
     "from":"20210101","to":"20211231"},
    {"id":"boost_inf_2022","q":"inflação preços Portugal famílias custo vida",
     "from":"20220101","to":"20221231"},
    {"id":"boost_inf_2023","q":"inflação preços Portugal famílias custo vida",
     "from":"20230101","to":"20231231"},
    {"id":"boost_inf_2024","q":"inflação preços Portugal famílias custo vida",
     "from":"20240101","to":"20241231"},
    # Salário recente
    {"id":"boost_sal_2021","q":"salário mínimo Portugal aumento governo trabalhadores",
     "from":"20210101","to":"20211231"},
    {"id":"boost_sal_2022","q":"salário mínimo Portugal aumento governo trabalhadores",
     "from":"20220101","to":"20221231"},
    {"id":"boost_sal_2023","q":"salário mínimo Portugal aumento governo trabalhadores",
     "from":"20230101","to":"20231231"},
    {"id":"boost_sal_2024","q":"salário mínimo Portugal aumento governo trabalhadores",
     "from":"20240101","to":"20241231"},
    # Combustíveis 2022 (guerra Ucrânia)
    {"id":"boost_comb_2022","q":"gasolina gasóleo preço record Portugal litro",
     "from":"20220101","to":"20221231"},
    {"id":"boost_comb_2023","q":"gasolina gasóleo preço Portugal litro",
     "from":"20230101","to":"20231231"},
    {"id":"boost_comb_2024","q":"gasolina gasóleo preço Portugal litro",
     "from":"20240101","to":"20241231"},
]

# ─── B) Público com formato http://www.publico.pt ─────────────────────────────
# A API aceita este formato e pode retornar resultados diferentes
QUERIES_PUBLICO_BOOST = [
    {"id":"pb_hab_recente","q":"preço habitação arrendamento Lisboa renda",
     "from":"20150101","to":"20241231"},
    {"id":"pb_sal_minimo","q":"salário mínimo aumento governo Portugal",
     "from":"20100101","to":"20241231"},
    {"id":"pb_inflacao","q":"inflação preços custo vida Portugal",
     "from":"20100101","to":"20241231"},
    {"id":"pb_combustiveis","q":"gasolina preço Portugal litro",
     "from":"20100101","to":"20241231"},
    {"id":"pb_troika","q":"troika austeridade cortes salários Portugal",
     "from":"20110101","to":"20151231"},
    {"id":"pb_habitacao_crise","q":"habitação crise arrendamento jovens Portugal",
     "from":"20170101","to":"20241231"},
    {"id":"pb_crise_2008","q":"crise financeira recessão Portugal desemprego",
     "from":"20080101","to":"20141231"},
    {"id":"pb_covid","q":"pandemia COVID impacto económico Portugal",
     "from":"20200101","to":"20211231"},
    {"id":"pb_energia","q":"electricidade gás preço fatura energia Portugal",
     "from":"20210101","to":"20241231"},
    {"id":"pb_desemprego","q":"desemprego taxa Portugal trabalhadores",
     "from":"20090101","to":"20241231"},
]

PUBLICO_FORMATS = [
    "www.publico.pt",
    "http://www.publico.pt",
]


def safe_get(params, retries=3):
    for attempt in range(retries):
        try:
            r = requests.get(BASE_URL, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            wait = (attempt + 1) * 3
            print(f"    [AVISO] tentativa {attempt+1}: {e}. Aguarda {wait}s...")
            time.sleep(wait)
    return {}


def paginate(q_config, site=None, max_items=500):
    all_items, offset = [], 0
    while len(all_items) < max_items:
        params = {
            "q":        q_config["q"],
            "from":     q_config["from"],
            "to":       q_config["to"],
            "maxItems": PAGE_SIZE,
            "offset":   offset,
            "fields":   "title,snippet,tstamp,linkToArchive,linkToScreenshot,originalURL",
        }
        if site:
            params["siteSearch"] = site
        data  = safe_get(params)
        items = data.get("response_items", [])
        if not items:
            break
        all_items.extend(items)
        if len(items) < PAGE_SIZE:
            break
        offset += len(items)
        time.sleep(SLEEP)
    return all_items[:max_items]


total_novo = 0

# ── A) Boost 2021-2024 ────────────────────────────────────────────────────────
print("=" * 60)
print("A) Boost temporal 2021-2024 (global, sem siteSearch)")
print("=" * 60)
for q in QUERIES_RECENT:
    fname = f"boost_{q['id']}.json"
    fpath = os.path.join(OUTPUT_DIR, fname)
    if os.path.exists(fpath):
        with open(fpath, encoding="utf-8") as f:
            n = len(json.load(f))
        total_novo += n
        print(f"  [SKIP] {fname} ({n} snippets)")
        continue
    items = paginate(q, site=None, max_items=500)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    total_novo += len(items)
    print(f"  [OK]   {fname}: {len(items)} snippets | total: {total_novo}")
    time.sleep(SLEEP)

# ── B) Boost Público ──────────────────────────────────────────────────────────
print()
print("=" * 60)
print("B) Boost Público (queries dedicadas, dois formatos)")
print("=" * 60)
total_pub = 0
for q in QUERIES_PUBLICO_BOOST:
    for site_format in PUBLICO_FORMATS:
        slug  = site_format.replace("http://", "").replace(".", "_").replace("/", "")
        fname = f"boostpub_{q['id']}_{slug}.json"
        fpath = os.path.join(OUTPUT_DIR, fname)
        if os.path.exists(fpath):
            with open(fpath, encoding="utf-8") as f:
                n = len(json.load(f))
            total_pub += n
            print(f"  [SKIP] {fname} ({n})")
            continue
        items = paginate(q, site=site_format, max_items=100)
        with open(fpath, "w", encoding="utf-8") as f:
            json.dump(items, f, ensure_ascii=False, indent=2)
        total_pub += len(items)
        print(f"  [OK]   {fname}: {len(items)} snippets | Público total: {total_pub}")
        time.sleep(SLEEP)

print()
print("=" * 60)
print(f"BOOST COMPLETO")
print(f"  Novos global:   {total_novo}")
print(f"  Novos Público:  {total_pub}")
print("=" * 60)
