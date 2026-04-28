# -*- coding: utf-8 -*-
# scripts/01_collect_arquivo.py
# Recolha de dados históricos do Arquivo.pt — Custo Portugal
#
# ESTRATÉGIA:
#   1. Recolha GLOBAL (sem siteSearch) com paginação → máx. 500 snippets/query
#      Cobre todos os jornais, maximiza cobertura temporal
#   2. Recolha DEDICADA ao Público (siteSearch=www.publico.pt) com paginação
#      Essencial para a Menção Honrosa do Jornal Público
#
# RATE LIMIT CRÍTICO: máx 250 req em 180s → sleep(1) OBRIGATÓRIO entre requests
# Bloqueio de IP é PERMANENTE.

import requests, json, time, os, sys

BASE_URL   = "https://arquivo.pt/textsearch"
OUTPUT_DIR = "data/raw"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PAGE_SIZE      = 50    # items por request (seguro e eficiente)
MAX_GLOBAL     = 500   # máx snippets por query global
MAX_PUBLICO    = 100   # máx snippets por query no Público (paginação offset)
SLEEP_BETWEEN  = 1.0  # segundos entre requests — NÃO REDUZIR

# ─── QUERIES — exactamente como no documento base, COM ACENTOS ──────────────

QUERIES = [
  # ═════════════════════════════════════════════════════════════════
  # HABITAÇÃO
  # ═════════════════════════════════════════════════════════════════
  # Era dos escudos (1996-2004): vocabulário da época
  {"id":"hab_01","q":"preço casas comprar Lisboa vender",
   "from":"19960101","to":"20041231"},
  {"id":"hab_02","q":"alojamento habitação preço contos escudos",
   "from":"19960101","to":"20021231"},
  {"id":"hab_03","q":"fogos habitação custo mercado imobiliário",
   "from":"19980101","to":"20061231"},
  {"id":"hab_04","q":"avaliação bancária habitação metro quadrado",
   "from":"20010101","to":"20121231"},
  # Boom, crise, troika (2005-2015)
  {"id":"hab_05","q":"preço habitação metro quadrado INE subida",
   "from":"20050101","to":"20151231"},
  {"id":"hab_06","q":"renda apartamento Lisboa arrendar contrato",
   "from":"20000101","to":"20241231"},
  {"id":"hab_07","q":"mercado imobiliário preços descem caem crise",
   "from":"20080101","to":"20141231"},
  {"id":"hab_08","q":"troika arrendamento habitação reforma",
   "from":"20110101","to":"20141231"},
  # Boom actual (2016-2024)
  {"id":"hab_09","q":"preço casas Lisboa recorde máximo histórico",
   "from":"20160101","to":"20241231"},
  {"id":"hab_10","q":"habitação inacessível jovens crise arrendamento",
   "from":"20190101","to":"20241231"},
  {"id":"hab_11","q":"Golden Visa Airbnb alojamento local preços sobem",
   "from":"20170101","to":"20241231"},

  # ═════════════════════════════════════════════════════════════════
  # COMBUSTÍVEIS
  # ═════════════════════════════════════════════════════════════════
  {"id":"comb_01","q":"gasolina preço escudos litro bomba",
   "from":"19960101","to":"20021231"},
  {"id":"comb_02","q":"preço gasolina litro euros bomba",
   "from":"20020101","to":"20241231"},
  {"id":"comb_03","q":"gasóleo preço litro aumento descida",
   "from":"20000101","to":"20241231"},
  {"id":"comb_04","q":"combustíveis preço recorde máximo sobe",
   "from":"20080101","to":"20241231"},
  {"id":"comb_05","q":"petróleo preço barril Portugal impacto",
   "from":"20000101","to":"20241231"},
  {"id":"comb_06","q":"guerra Ucrânia combustíveis preço Portugal energia",
   "from":"20220101","to":"20241231"},

  # ═════════════════════════════════════════════════════════════════
  # SALÁRIO MÍNIMO E RENDIMENTO
  # ═════════════════════════════════════════════════════════════════
  {"id":"sal_01","q":"salário mínimo nacional aumento aprovado governo",
   "from":"19960101","to":"20241231"},
  {"id":"sal_02","q":"ordenado mínimo Portugal escudos trabalhadores",
   "from":"19960101","to":"20021231"},
  {"id":"sal_03","q":"salário médio Portugal trabalhadores rendimento",
   "from":"20000101","to":"20241231"},
  {"id":"sal_04","q":"poder de compra portugueses desceu perdeu deteriorou",
   "from":"20080101","to":"20241231"},
  {"id":"sal_05","q":"desemprego taxa Portugal INE record",
   "from":"20000101","to":"20241231"},
  {"id":"sal_06","q":"salário mínimo 600 700 800 euros aumento",
   "from":"20170101","to":"20241231"},

  # ═════════════════════════════════════════════════════════════════
  # CUSTO DE VIDA E INFLAÇÃO
  # ═════════════════════════════════════════════════════════════════
  {"id":"cv_01","q":"inflação Portugal taxa IPC subida preços",
   "from":"19990101","to":"20241231"},
  {"id":"cv_02","q":"carestia de vida preços sobem famílias",
   "from":"19960101","to":"20101231"},
  {"id":"cv_03","q":"custo de vida Portugal caro aumentou famílias",
   "from":"20050101","to":"20241231"},
  {"id":"cv_04","q":"cabaz alimentar preço supermercado alimentação",
   "from":"20050101","to":"20241231"},
  {"id":"cv_05","q":"inflação recorde máximo Portugal 2022 guerra energia",
   "from":"20220101","to":"20241231"},
  {"id":"cv_06","q":"electricidade gás preço fatura doméstica subida",
   "from":"20080101","to":"20241231"},

  # ═════════════════════════════════════════════════════════════════
  # CONTEXTO HISTÓRICO
  # ═════════════════════════════════════════════════════════════════
  {"id":"ctx_01","q":"crise financeira Portugal recessão economy",
   "from":"20080101","to":"20141231"},
  {"id":"ctx_02","q":"troika FMI Portugal austeridade cortes salários",
   "from":"20110101","to":"20151231"},
  {"id":"ctx_03","q":"COVID-19 economia Portugal desemprego impacto",
   "from":"20200101","to":"20211231"},
  {"id":"ctx_04","q":"Euro moeda transição escudos 2002 Portugal",
   "from":"20010601","to":"20030101"},
  {"id":"ctx_05","q":"guerra Ucrânia economia inflação Portugal impacto",
   "from":"20220101","to":"20231231"},
  {"id":"ctx_06","q":"subprime crise 2008 Portugal banco",
   "from":"20080101","to":"20101231"},
]

# Domínios alvo para rastreio (filtro pós-recolha)
TARGET_DOMAINS = [
    "publico.pt", "dn.pt", "expresso.pt",
    "jn.pt", "tsf.pt", "ionline.pt", "cmjornal.pt",
]


def safe_get(params, retries=3):
    """GET com retry automático em caso de erro de rede."""
    for attempt in range(retries):
        try:
            r = requests.get(BASE_URL, params=params, timeout=30)
            r.raise_for_status()
            return r.json()
        except Exception as e:
            wait = (attempt + 1) * 3
            print(f"    [AVISO] Tentativa {attempt+1}/{retries} falhou: {e}. Aguarda {wait}s...")
            time.sleep(wait)
    return {}


def paginate(q_config, site=None, max_items=MAX_GLOBAL):
    """Recolhe snippets com paginação via offset."""
    all_items = []
    offset    = 0

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
        est = data.get("estimated_nr_results", "?")

        if len(items) < PAGE_SIZE:
            break               # última página

        offset += len(items)
        time.sleep(SLEEP_BETWEEN)

    return all_items[:max_items]


def count_per_domain(items):
    counts = {}
    for it in items:
        url = it.get("originalURL", "")
        for d in TARGET_DOMAINS:
            if d in url:
                counts[d] = counts.get(d, 0) + 1
                break
    return counts


# ─── FASE 1: Recolha GLOBAL ──────────────────────────────────────────────────
print("=" * 65)
print("FASE 1 — Recolha global (sem siteSearch)")
print("=" * 65)

total_global = 0
for query in QUERIES:
    fname = f"global_{query['id']}.json"
    fpath = os.path.join(OUTPUT_DIR, fname)

    if os.path.exists(fpath):
        with open(fpath, encoding="utf-8") as f:
            n = len(json.load(f))
        total_global += n
        print(f"  [SKIP] {fname} ({n} snippets já recolhidos)")
        continue

    items = paginate(query, site=None, max_items=MAX_GLOBAL)

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    domain_counts = count_per_domain(items)
    pub_n         = domain_counts.get("publico.pt", 0)
    total_global += len(items)

    print(f"  [OK] {fname}: {len(items)} snippets | Público:{pub_n} | total: {total_global}")
    time.sleep(SLEEP_BETWEEN)

print(f"\n  => Global: {total_global} snippets em {len(QUERIES)} ficheiros\n")


# ─── FASE 2: Recolha DEDICADA ao Público ─────────────────────────────────────
print("=" * 65)
print("FASE 2 — Recolha dedicada Público (siteSearch=www.publico.pt)")
print("=" * 65)

total_publico = 0
for query in QUERIES:
    fname = f"pub_{query['id']}.json"
    fpath = os.path.join(OUTPUT_DIR, fname)

    if os.path.exists(fpath):
        with open(fpath, encoding="utf-8") as f:
            n = len(json.load(f))
        total_publico += n
        print(f"  [SKIP] {fname} ({n} snippets já recolhidos)")
        continue

    items = paginate(query, site="www.publico.pt", max_items=MAX_PUBLICO)

    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    total_publico += len(items)
    print(f"  [OK] {fname}: {len(items)} snippets | total Público: {total_publico}")
    time.sleep(SLEEP_BETWEEN)

print(f"\n  => Público: {total_publico} snippets em {len(QUERIES)} ficheiros\n")


# ─── RESUMO FINAL ─────────────────────────────────────────────────────────────
n_files = len(os.listdir(OUTPUT_DIR))
total   = total_global + total_publico

print("=" * 65)
print(f"RECOLHA COMPLETA: {total} snippets em {n_files} ficheiros")
print(f"  Global:  {total_global}")
print(f"  Publico: {total_publico}")
print("=" * 65)
