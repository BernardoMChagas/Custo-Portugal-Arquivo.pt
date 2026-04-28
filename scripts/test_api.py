"""
Diagnostico aprofundado da API Arquivo.pt
- Testa sem siteSearch (global)
- Testa com maxItems diferentes
- Testa com e sem o parametro 'fields'
- Inspeciona a resposta raw
"""
import requests, json, pprint

BASE_URL = "https://arquivo.pt/textsearch"
Q        = "salario minimo Portugal"

tests = [
    # (descricao, params_extras)
    ("Sem siteSearch, maxItems=10",
     {"q": Q, "from": "20100101", "to": "20201231", "maxItems": 10}),

    ("Com www.publico.pt, maxItems=10",
     {"q": Q, "from": "20100101", "to": "20201231", "maxItems": 10,
      "siteSearch": "www.publico.pt"}),

    ("Com www.publico.pt, maxItems=500",
     {"q": Q, "from": "20100101", "to": "20201231", "maxItems": 500,
      "siteSearch": "www.publico.pt"}),

    ("Com www.publico.pt, sem 'from'/'to'",
     {"q": Q, "maxItems": 10, "siteSearch": "www.publico.pt"}),

    # Testa o endpoint de fulltext search alternativo
    ("Sem siteSearch, maxItems=10, com fields",
     {"q": Q, "from": "20100101", "to": "20201231", "maxItems": 10,
      "fields": "title,snippet,tstamp,linkToArchive,originalURL"}),
]

for desc, params in tests:
    try:
        r    = requests.get(BASE_URL, params=params, timeout=30)
        data = r.json()
        items   = data.get("response_items", [])
        est_tot = data.get("estimated_nr_results", "N/A")
        print(f"\n[{desc}]")
        print(f"  HTTP {r.status_code} | items={len(items)} | estimated_total={est_tot}")
        print(f"  URL: {r.url[:120]}")
        if items:
            print(f"  Campos item[0]: {sorted(items[0].keys())}")
            print(f"  originalURL[0]: {items[0].get('originalURL','')[:80]}")
    except Exception as e:
        print(f"\n[{desc}]  ERRO: {e}")
