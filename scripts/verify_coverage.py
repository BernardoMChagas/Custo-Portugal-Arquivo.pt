"""
Passo 1.3 — Verificação de cobertura temporal (min 50 snippets/ano, 2000-2024)
Passo 1.4 — Verificação de cobertura do Público (min 500 snippets)
"""
import glob, json
from collections import Counter, defaultdict

RAW = "data/raw"
TARGET_DOMAINS = [
    "publico.pt", "dn.pt", "expresso.pt",
    "jn.pt", "tsf.pt", "ionline.pt", "cmjornal.pt",
]

# Carrega todos os snippets
todos = []
publico = []

for fpath in sorted(glob.glob(f"{RAW}/*.json")):
    try:
        with open(fpath, encoding="utf-8") as f:
            items = json.load(f)
        todos.extend(items)
        for it in items:
            url = it.get("originalURL", "")
            if "publico.pt" in url:
                publico.append(it)
    except Exception:
        pass

print(f"Total snippets carregados : {len(todos)}")
print(f"Total snippets do Publico : {len(publico)}")
print()

# ── Passo 1.3 — Cobertura temporal ──────────────────────────────────────────
anos = Counter()
for it in todos:
    ts = it.get("tstamp", "")
    if len(ts) >= 4:
        anos[int(ts[:4])] += 1

print("=== PASSO 1.3 — Cobertura temporal (2000-2024) ===")
print(f"{'Ano':<6} {'Snippets':>8}  {'Barra'}")
anos_problema = []
for ano in range(2000, 2025):
    n     = anos.get(ano, 0)
    barra = "#" * min(n // 10, 50)
    flag  = " [!] <30" if n < 30 else (" [aviso] <50" if n < 50 else "")
    print(f"  {ano}   {n:>6}  {barra}{flag}")
    if n < 30:
        anos_problema.append(ano)

print()
if anos_problema:
    print(f"[AVISO] Anos com < 30 snippets: {anos_problema}")
    print("  -> Considerar adicionar queries especificas para esses periodos.")
else:
    print("[OK] Todos os anos 2000-2024 com >= 30 snippets!")

print()

# ── Passo 1.4 — Cobertura do Público ────────────────────────────────────────
print("=== PASSO 1.4 — Cobertura do Publico ===")
print(f"  Total snippets do Publico: {len(publico)}")

if len(publico) >= 500:
    print("  [OK] Meta de 500 snippets ATINGIDA!")
else:
    falta = 500 - len(publico)
    print(f"  [AVISO] Faltam {falta} snippets do Publico para atingir a meta de 500.")
    print("  -> Estrategia: adicionar queries com siteSearch=www.publico.pt")
    print("     ou usar o arquivo do Publico com formato http://www.publico.pt")

print()

# ── Resumo por jornal ────────────────────────────────────────────────────────
print("=== Snippets por jornal (dos ficheiros globais) ===")
por_jornal = defaultdict(int)
for it in todos:
    url = it.get("originalURL", "")
    for d in TARGET_DOMAINS:
        if d in url:
            por_jornal[d] += 1
            break
    else:
        por_jornal["outros"] += 1

for jornal, n in sorted(por_jornal.items(), key=lambda x: -x[1]):
    print(f"  {jornal:<25} {n:>5} snippets")
