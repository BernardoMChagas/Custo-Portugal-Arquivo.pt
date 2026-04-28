import json, os, glob, random
from collections import defaultdict

RAW_DIR = "data/raw"
OUTPUT = "data/extracted_data.json"

# Basic historical trends for mock data
trends = {
    "habitacao":   lambda y: 800 + (y-1996)*60 if y < 2008 else (1500 - (y-2008)*80 if y <= 2014 else 1000 + (y-2014)*150),
    "combustivel": lambda y: 0.70 + (y-1996)*0.03 if y < 2008 else (1.40 + (y-2008)*0.05 if y <= 2012 else 1.60 + (y-2012)*0.02),
    "salario":     lambda y: 300 + (y-1996)*15 if y < 2010 else (475 + (y-2010)*5 if y <= 2015 else 500 + (y-2015)*30),
    "inflacao":    lambda y: random.uniform(1.0, 3.0) if y not in [2011, 2012, 2022] else random.uniform(3.5, 8.0)
}

extracted = []
snippets_by_year = defaultdict(list)

# Load real snippets to use as context
for fpath in glob.glob(f"{RAW_DIR}/*.json"):
    try:
        with open(fpath, encoding="utf-8") as f:
            items = json.load(f)
        for item in items:
            ts = item.get("tstamp", "2000")
            year = int(ts[:4])
            if 1996 <= year <= 2024:
                snippets_by_year[year].append(item)
    except Exception:
        pass

for year in range(1996, 2025):
    snips = snippets_by_year.get(year, [])
    if not snips:
        # Create a dummy snippet if none available
        snips = [{"title": f"Notícia de {year}", "originalURL": "http://publico.pt", "linkToArchive": "", "snippet": ""}]
    
    for cat in ["habitacao", "combustivel", "salario", "inflacao"]:
        # Pick 3 random snippets for this category
        for _ in range(3):
            snip = random.choice(snips)
            val = trends[cat](year)
            # Add some noise
            val = val * random.uniform(0.9, 1.1)
            
            unit = "€/m2" if cat == "habitacao" else "€/L" if cat == "combustivel" else "€/mes" if cat == "salario" else "%"
            
            extracted.append({
                "ano": year,
                "mes": random.randint(1, 12),
                "categoria": cat,
                "valor_numerico": round(val, 3),
                "unidade": unit,
                "cidade": "Lisboa",
                "moeda_original": "euros",
                "valor_original": round(val, 3),
                "contexto_curto": f"Exemplo de {cat} em {year}",
                "sentimento": "crise" if year in [2011, 2012, 2013] else "estavel",
                "relevancia": random.randint(3, 5),
                "titulo_noticia": snip.get("title", f"Notícia de {year}"),
                "fonte_nome": snip.get("originalURL", "").split("/")[2] if "http" in snip.get("originalURL", "") else "Público",
                "link_arquivo": snip.get("linkToArchive", ""),
                "link_screenshot": snip.get("linkToScreenshot", "")
            })

os.makedirs("data", exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(extracted, f, ensure_ascii=False, indent=2)

print(f"Mock dataset generated at {OUTPUT} with {len(extracted)} items.")
