"""
Passo 1.1 — Teste com 2 queries, so Publico.
Valida: title, snippet, tstamp, linkToArchive presentes.
"""
import requests, json, time, os

BASE_URL   = "https://arquivo.pt/textsearch"
OUTPUT_DIR = "data/raw"
os.makedirs(OUTPUT_DIR, exist_ok=True)

QUERIES_TEST = [
    {"id": "sal_01", "q": "salario minimo nacional aumento aprovado governo",
     "from": "20050101", "to": "20201231"},
    {"id": "cv_01",  "q": "inflacao Portugal taxa IPC subida precos",
     "from": "20050101", "to": "20201231"},
]

CAMPOS_OBRIGATORIOS = {"title", "snippet", "tstamp", "linkToArchive"}
tudo_ok = True

print("=== PASSO 1.1 - TESTE 2 QUERIES / SO PUBLICO ===\n")

for q in QUERIES_TEST:
    all_items = []
    # Pagina com offset para contornar limite real da API
    for offset in range(0, 200, 50):
        params = {
            "q":          q["q"],
            "from":       q["from"],
            "to":         q["to"],
            "maxItems":   50,
            "offset":     offset,
            "siteSearch": "www.publico.pt",
            "fields":     "title,snippet,tstamp,linkToArchive,linkToScreenshot,originalURL",
        }
        r     = requests.get(BASE_URL, params=params, timeout=30)
        items = r.json().get("response_items", [])
        if not items:
            break
        all_items.extend(items)
        if len(items) < 50:
            break
        time.sleep(0.5)

    fname = q["id"] + "_publico.json"
    fpath = os.path.join(OUTPUT_DIR, fname)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(all_items, f, ensure_ascii=False, indent=2)

    print(f"[{q['id']}] {len(all_items)} snippets -> {fname}")

    if not all_items:
        print("  [AVISO] Sem snippets retornados.")
        tudo_ok = False
        time.sleep(1)
        continue

    faltam = CAMPOS_OBRIGATORIOS - set(all_items[0].keys())
    if faltam:
        print(f"  [ERRO]  Campos em falta: {faltam}")
        tudo_ok = False
    else:
        print("  [OK]    Todos os 4 campos obrigatorios presentes.")

    print(f"  title        : {all_items[0].get('title', '')[:80]}")
    print(f"  tstamp       : {all_items[0].get('tstamp', '')}")
    print(f"  snippet      : {str(all_items[0].get('snippet', ''))[:100]}...")
    print(f"  linkToArchive: {str(all_items[0].get('linkToArchive', ''))[:80]}...")
    time.sleep(1)

print()
print("=== TESTE 1.1 PASSOU ===" if tudo_ok else "=== TESTE 1.1 COM AVISOS ===")
