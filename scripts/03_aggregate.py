# scripts/03_aggregate.py
# INSTRUÇÃO ANTIGRAVITY: Executa após 02_extract_gemini.py.
# Gera data/final_for_frontend.json e imprime o ano com IDE mais alto.

import json, statistics
from collections import defaultdict
import os

with open("data/extracted_data.json", encoding="utf-8") as f:
    data = json.load(f)

# Agrupar por ano + categoria
by_year = defaultdict(lambda: defaultdict(list))
for item in data:
    ano, cat = item.get("ano"), item.get("categoria")
    if ano and cat and 1996 <= ano <= 2026:
        by_year[ano][cat].append(item)

# Dataset por ano
final = {}
for ano in sorted(by_year):
    final[ano] = {}
    for cat, items in by_year[ano].items():
        valores = [i["valor_numerico"] for i in items if i.get("valor_numerico")]
        melhor = max(items, key=lambda x: x.get("relevancia", 0))
        final[ano][cat] = {
            "valor_mediana": round(statistics.median(valores), 2) if valores else None,
            "n_fontes": len(items),
            "noticia_destaque": {
                "titulo": melhor.get("titulo_noticia", ""),
                "contexto": melhor.get("contexto_curto", ""),
                "fonte": melhor.get("fonte_nome", ""),
                "sentimento": melhor.get("sentimento", ""),
                "link_arquivo": melhor.get("link_arquivo", ""),
                "link_screenshot": melhor.get("link_screenshot", ""),
            }
        }

# Índice de Dificuldade Económica (IDE)
def norm(vals_dict, invert=False):
    """Normaliza valores para 0-100. invert=True para salário (menor = mais difícil)."""
    clean = {k:v for k,v in vals_dict.items() if v is not None}
    if not clean:
        return {}
    mn, mx = min(clean.values()), max(clean.values())
    if mx == mn:
        return {k: 50 for k in clean}
    normalized = {k: (v-mn)/(mx-mn)*100 for k,v in clean.items()}
    if invert:
        normalized = {k: 100-v for k,v in normalized.items()}
    return {k: round(v, 1) for k,v in normalized.items()}

hab  = {a: final[a].get("habitacao",{}).get("valor_mediana") for a in final}
comb = {a: final[a].get("combustivel",{}).get("valor_mediana") for a in final}
sal  = {a: final[a].get("salario",{}).get("valor_mediana") for a in final}
inf  = {a: final[a].get("inflacao",{}).get("valor_mediana") for a in final}

h_n = norm(hab)           # mais alto = mais caro = mais difícil
c_n = norm(comb)          # mais alto = combustível mais caro = mais difícil
s_n = norm(sal, True)     # mais alto salário = menos difícil → inverter
i_n = norm(inf)           # mais alta inflação = mais difícil

for ano in final:
    ide = round(
        h_n.get(ano, 50) * 0.35 +
        s_n.get(ano, 50) * 0.30 +
        c_n.get(ano, 50) * 0.20 +
        i_n.get(ano, 50) * 0.15, 1
    )
    final[ano]["ide"] = ide
    # Adicionar dados normalizados para o frontend poder construir o gráfico de componentes
    final[ano]["ide_componentes"] = {
        "habitacao": h_n.get(ano, 50),
        "salario": s_n.get(ano, 50),
        "combustivel": c_n.get(ano, 50),
        "inflacao": i_n.get(ano, 50),
    }

os.makedirs("data", exist_ok=True)
with open("data/final_for_frontend.json", "w", encoding="utf-8") as f:
    json.dump(final, f, ensure_ascii=False, indent=2)

ides = {a: final[a]["ide"] for a in final if "ide" in final[a]}
pior = max(ides, key=ides.get)
melhor = min(ides, key=ides.get)

print(f"\n═══ AGREGAÇÃO COMPLETA ═══")
print(f"  Anos com dados: {len(final)}")
print(f"  Ano mais difícil: {pior} (IDE: {ides[pior]})")
print(f"  Ano mais fácil: {melhor} (IDE: {ides[melhor]})")
print(f"  Dataset: data/final_for_frontend.json")
