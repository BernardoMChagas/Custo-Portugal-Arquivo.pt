# scripts/01_collect_arquivo.py
# INSTRUÇÃO ANTIGRAVITY: Executa este script. Guarda JSONs em data/raw/.
# Imprime progresso a cada query. No fim: total de snippets por categoria.

import requests, json, time, os

BASE_URL = "https://arquivo.pt/textsearch"
OUTPUT_DIR = "data/raw"
os.makedirs(OUTPUT_DIR, exist_ok=True)

QUERIES = [
  # ═══════════════════════════════════════════════════════
  # HABITAÇÃO
  # ═══════════════════════════════════════════════════════

  # 1996-2004: linguagem da época (escudos, fogos, alojamento)
  {"id":"hab_01","q":"preço casas comprar Lisboa vender",
   "from":"19960101","to":"20041231"},
  {"id":"hab_02","q":"alojamento habitação preço contos escudos",
   "from":"19960101","to":"20021231"},                    # era dos escudos
  {"id":"hab_03","q":"fogos habitação custo mercado imobiliário",
   "from":"19980101","to":"20061231"},
  {"id":"hab_04","q":"avaliação bancária habitação metro quadrado",
   "from":"20010101","to":"20121231"},

  # 2005-2015: boom, crise, troika
  {"id":"hab_05","q":"preço habitação metro quadrado INE subida",
   "from":"20050101","to":"20151231"},
  {"id":"hab_06","q":"renda apartamento Lisboa arrendar contrato",
   "from":"20000101","to":"20261231"},
  {"id":"hab_07","q":"mercado imobiliário preços descem caem crise",
   "from":"20080101","to":"20141231"},
  {"id":"hab_08","q":"troika arrendamento habitação reforma",
   "from":"20110101","to":"20141231"},

  # 2016-2026: boom atual
  {"id":"hab_09","q":"preço casas Lisboa recorde máximo histórico",
   "from":"20160101","to":"20261231"},
  {"id":"hab_10","q":"habitação inacessível jovens crise arrendamento",
   "from":"20190101","to":"20261231"},
  {"id":"hab_11","q":"Golden Visa Airbnb alojamento local preços sobem",
   "from":"20170101","to":"20261231"},

  # ═══════════════════════════════════════════════════════
  # COMBUSTÍVEIS
  # ═══════════════════════════════════════════════════════

  {"id":"comb_01","q":"gasolina preço escudos litro bomba",
   "from":"19960101","to":"20021231"},                    # era dos escudos
  {"id":"comb_02","q":"preço gasolina litro euros bomba",
   "from":"20020101","to":"20261231"},
  {"id":"comb_03","q":"gasóleo preço litro aumento descida",
   "from":"20000101","to":"20261231"},
  {"id":"comb_04","q":"combustíveis preço recorde máximo sobe",
   "from":"20080101","to":"20261231"},
  {"id":"comb_05","q":"petróleo preço barril Portugal impacto",
   "from":"20000101","to":"20261231"},
  {"id":"comb_06","q":"guerra Ucrânia combustíveis preço Portugal energia",
   "from":"20220101","to":"20241231"},

  # ═══════════════════════════════════════════════════════
  # SALÁRIO MÍNIMO E RENDIMENTO
  # ═══════════════════════════════════════════════════════

  {"id":"sal_01","q":"salário mínimo nacional aumento aprovado governo",
   "from":"19960101","to":"20261231"},                    # query sempre-verde
  {"id":"sal_02","q":"ordenado mínimo Portugal escudos trabalhadores",
   "from":"19960101","to":"20021231"},                    # era dos escudos
  {"id":"sal_03","q":"salário médio Portugal trabalhadores rendimento",
   "from":"20000101","to":"20261231"},
  {"id":"sal_04","q":"poder de compra portugueses desceu perdeu deteriorou",
   "from":"20080101","to":"20261231"},
  {"id":"sal_05","q":"desemprego taxa Portugal INE record",
   "from":"20000101","to":"20261231"},
  {"id":"sal_06","q":"salário mínimo 600 700 800 euros aumento",
   "from":"20170101","to":"20261231"},                    # anos recentes

  # ═══════════════════════════════════════════════════════
  # CUSTO DE VIDA E INFLAÇÃO
  # ═══════════════════════════════════════════════════════

  {"id":"cv_01","q":"inflação Portugal taxa IPC subida preços",
   "from":"19990101","to":"20261231"},
  {"id":"cv_02","q":"carestia de vida preços sobem famílias",
   "from":"19960101","to":"20101231"},                    # termo histórico
  {"id":"cv_03","q":"custo de vida Portugal caro aumentou famílias",
   "from":"20050101","to":"20261231"},
  {"id":"cv_04","q":"cabaz alimentar preço supermercado alimentação",
   "from":"20050101","to":"20261231"},
  {"id":"cv_05","q":"inflação recorde máximo Portugal 2022 guerra energia",
   "from":"20220101","to":"20241231"},
  {"id":"cv_06","q":"electricidade gás preço fatura doméstica subida",
   "from":"20080101","to":"20261231"},

  # ═══════════════════════════════════════════════════════
  # CONTEXTO HISTÓRICO (anotações na timeline)
  # ═══════════════════════════════════════════════════════

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

# Domínios por prioridade
SITES = {
  "tier1": [
    "http://www.publico.pt",      # Menção Honrosa + maior cobertura económica
    "http://www.dn.pt",           # Diário de Notícias — muito bom para preços
    "http://www.expresso.pt",     # Semanário de referência
  ],
  "tier2": [
    "http://www.jn.pt",
    "http://www.tsf.pt",
    "http://www.ionline.pt",
  ]
}

def fetch_query(q_config, site=None):
    params = {
        "q": q_config["q"],
        "from": q_config["from"],
        "to": q_config["to"],
        "maxItems": 500,
        "fields": "title,snippet,tstamp,linkToArchive,linkToScreenshot,originalURL",
    }
    if site:
        params["siteSearch"] = site

    results, offset = [], 0
    while True:
        params["offset"] = offset
        try:
            r = requests.get(BASE_URL, params=params, timeout=30)
            data = r.json()
            items = data.get("response_items", [])
            if not items:
                break
            results.extend(items)
            if len(items) < 500:
                break
            offset += len(items)
            time.sleep(0.8)
        except Exception as e:
            print(f"  ⚠ Erro: {e}")
            break
    return results

total = 0
for query in QUERIES:
    for tier, sites in SITES.items():
        for site in sites:
            slug = site.replace("http://www.", "").replace(".", "_")
            fname = f"{query['id']}_{slug}.json"
            fpath = os.path.join(OUTPUT_DIR, fname)
            if os.path.exists(fpath):
                print(f"  ✓ Já existe: {fname}")
                continue
            items = fetch_query(query, site)
            with open(fpath, "w", encoding="utf-8") as f:
                json.dump(items, f, ensure_ascii=False, indent=2)
            total += len(items)
            print(f"  ✓ {fname}: {len(items)} snippets (total: {total})")
            time.sleep(2)

print(f"\n═══ RECOLHA COMPLETA: {total} snippets em {len(os.listdir(OUTPUT_DIR))} ficheiros ═══")
