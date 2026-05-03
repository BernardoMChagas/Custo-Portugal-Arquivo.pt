# -*- coding: utf-8 -*-
# scripts/04_export_quality_metrics.py
# Gera data/quality_metrics.json para uso no website (secção Metodologia)
# Corre DEPOIS de 03_aggregate.py

import json, statistics, math, os
from collections import defaultdict

# ─── Carrega dados ─────────────────────────────────────────────────────────────
with open("data/checkpoint_v4.json", encoding="utf-8") as f:
    ck = json.load(f)
with open("data/final_for_frontend.json", encoding="utf-8") as f:
    final = json.load(f)

data    = ck.get("results", [])
n_total_snippets   = len(ck.get("processed", []))
n_total_extraidos  = len(data)

IDE_CATS = {"habitacao", "combustivel", "salario", "inflacao"}
ALL_CATS = list(IDE_CATS) + ["desemprego", "custo_vida", "contexto"]

# ─── Cobertura por ano e categoria ────────────────────────────────────────────
by_year = defaultdict(lambda: defaultdict(list))
for item in data:
    ano = item.get("ano")
    cat = item.get("categoria")
    if ano and cat and 1996 <= ano <= 2026:
        by_year[ano][cat].append(item)

# ─── Tabela de cobertura por ano ──────────────────────────────────────────────
cobertura_por_ano = []
for ano in range(1996, 2027):
    row = by_year.get(ano, {})
    cats_ide = {cat: len(row.get(cat, [])) for cat in IDE_CATS}
    cats_ide_ok = sum(1 for v in cats_ide.values() if v > 0)
    entry_final = final.get(str(ano), {})
    cobertura_por_ano.append({
        "ano": ano,
        "habitacao":   cats_ide.get("habitacao", 0),
        "combustivel": cats_ide.get("combustivel", 0),
        "salario":     cats_ide.get("salario", 0),
        "inflacao":    cats_ide.get("inflacao", 0),
        "desemprego":  len(row.get("desemprego", [])),
        "custo_vida":  len(row.get("custo_vida", [])),
        "contexto":    len(row.get("contexto", [])),
        "total":       sum(len(v) for v in row.values()),
        "cats_ide_com_dados": cats_ide_ok,
        "ide_completo": cats_ide_ok == 4,
        "ide": entry_final.get("ide"),
        "ide_confianca_pct": entry_final.get("ide_confianca_pct"),
    })

# ─── Cobertura por categoria ──────────────────────────────────────────────────
cobertura_por_cat = {}
for cat in sorted(IDE_CATS):
    anos_com = sorted(a for a in range(1996, 2027) if by_year.get(a, {}).get(cat))
    anos_sem = sorted(a for a in range(1996, 2027) if not by_year.get(a, {}).get(cat))
    totais   = [len(by_year[a][cat]) for a in anos_com]
    cobertura_por_cat[cat] = {
        "anos_com_dados": anos_com,
        "anos_sem_dados": anos_sem,
        "n_anos_com_dados": len(anos_com),
        "n_anos_sem_dados": len(anos_sem),
        "total_registos": sum(totais),
        "media_fontes_por_ano": round(statistics.mean(totais), 1) if totais else 0,
        "min_fontes": min(totais) if totais else 0,
        "max_fontes": max(totais) if totais else 0,
    }

# ─── Distribuição por fonte ───────────────────────────────────────────────────
from collections import Counter
fontes_counter = Counter()
for item in data:
    fn = item.get("fonte_nome", "Outro")
    if fn:
        fontes_counter[fn] += 1

# Agrupa fontes menores em "Outros"
TOP_N = 10
fontes_top = fontes_counter.most_common(TOP_N)
fontes_outros = sum(v for k, v in fontes_counter.items()
                    if k not in dict(fontes_top))
distribuicao_fontes = [{"fonte": k, "n": v} for k, v in fontes_top]
if fontes_outros:
    distribuicao_fontes.append({"fonte": "Outros", "n": fontes_outros})

# Percentagem do Público (para Menção Honrosa)
n_publico = fontes_counter.get("Publico", 0) + fontes_counter.get("Público", 0)
pct_publico = round(n_publico / n_total_extraidos * 100, 1) if n_total_extraidos else 0

# ─── Scores de confiança globais ──────────────────────────────────────────────
confianças_reais = []
for ano_str, ano_data in final.items():
    for cat in IDE_CATS:
        cat_data = ano_data.get(cat, {})
        if not cat_data.get("fonte_historica", True) and cat_data.get("confianca_pct") is not None:
            confianças_reais.append({
                "ano": int(ano_str),
                "cat": cat,
                "confianca": cat_data["confianca_pct"],
                "n_fontes": cat_data.get("n_fontes", 0),
                "cv": cat_data.get("coef_variacao"),
            })

confianças_vals = [c["confianca"] for c in confianças_reais]

# IDE por ano (apenas anos com dados reais)
ide_por_ano_real = [
    {"ano": int(a), "ide": v["ide"], "confianca": v.get("ide_confianca_pct")}
    for a, v in final.items()
    if v.get("ide_confianca_pct") is not None
]
ide_por_ano_real.sort(key=lambda x: x["ano"])

ide_vals = [x["ide"] for x in ide_por_ano_real]
ano_mais_dificil = max(ide_por_ano_real, key=lambda x: x["ide"])
ano_mais_facil   = min(ide_por_ano_real, key=lambda x: x["ide"])

# ─── Constrói o objecto final ─────────────────────────────────────────────────
metrics = {
    "meta": {
        "gerado_em": "2026-05-01",
        "versao": "4.0",
        "descricao": "Metricas de qualidade do dataset Custo Portugal para uso no website",
    },
    "pipeline": {
        "total_snippets_recolhidos": 4338,
        "total_snippets_processados": n_total_snippets,
        "total_registos_extraidos": n_total_extraidos,
        "taxa_extracao_pct": round(n_total_extraidos / n_total_snippets * 100, 1),
        "anos_cobertos": 29,
        "periodo": "1996-2026",
        "modelos_llm": [
            "llama-3.1-8b-instant",
            "llama-4-scout-17b",
            "qwen/qwen3-32b",
            "openai/gpt-oss-20b",
            "openai/gpt-oss-120b"
        ],
        "api": "Groq (migrado do Gemini — instabilidade 503)",
    },
    "cobertura_por_ano": cobertura_por_ano,
    "cobertura_por_categoria": cobertura_por_cat,
    "distribuicao_fontes": distribuicao_fontes,
    "publico": {
        "n_registos": n_publico,
        "percentagem_total": pct_publico,
        "nota": "Percentagem dos registos extraidos provenientes do arquivo do Publico.pt"
    },
    "confianca_global": {
        "media_pct": round(statistics.mean(confianças_vals), 1) if confianças_vals else None,
        "mediana_pct": round(statistics.median(confianças_vals), 1) if confianças_vals else None,
        "minimo_pct": round(min(confianças_vals), 1) if confianças_vals else None,
        "maximo_pct": round(max(confianças_vals), 1) if confianças_vals else None,
        "n_pontos_avaliados": len(confianças_vals),
        "metodo": "Score composto: consistencia(40%) + volume(35%) + relevancia(25%)",
        "top5_mais_confiaveis": sorted(confianças_reais, key=lambda x: -x["confianca"])[:5],
        "top5_menos_confiaveis": sorted(confianças_reais, key=lambda x: x["confianca"])[:5],
    },
    "ide": {
        "ano_mais_dificil": ano_mais_dificil,
        "ano_mais_facil":   ano_mais_facil,
        "por_ano": ide_por_ano_real,
        "pesos": {
            "habitacao": 0.35,
            "salario":   0.30,
            "combustivel": 0.20,
            "inflacao":  0.15,
        },
        "nota_metodologica": (
            "O IDE e calculado sobre medianas de valores extraidos de artigos do Arquivo.pt "
            "com relevancia >= 4. Anos sem dados reais usam fallback INE/Pordata/DGEG "
            "(identificados por fonte_historica=true no dataset). "
            "O salario e invertido na normalizacao (mais salario = menos dificuldade)."
        ),
    },
    "fontes_historicas": {
        "habitacao": "INE (IABH 2009-2017; Estatisticas Precos Habitacao 2018-2026); estimativas BPstat/CI para 1996-2008",
        "combustivel": "DGEG (dgeg-pma-1960-2003.xlsx; dgeg-pma-2004-2025_pt.xlsx) — media Gasolina95+Gasoleo",
        "salario": "PORDATA — RMMG (Retribuicao Minima Mensal Garantida)",
        "inflacao": "INE — Taxa de variacao media anual do IPC",
    }
}

os.makedirs("data", exist_ok=True)
with open("data/quality_metrics.json", "w", encoding="utf-8") as f:
    json.dump(metrics, f, ensure_ascii=False, indent=2)

print("=" * 60)
print("QUALITY METRICS — RESUMO")
print("=" * 60)
print(f"  Snippets recolhidos : {metrics['pipeline']['total_snippets_recolhidos']}")
print(f"  Snippets processados: {n_total_snippets}")
print(f"  Registos extraidos  : {n_total_extraidos} ({metrics['pipeline']['taxa_extracao_pct']}% de extracao util)")
print(f"  Confinca media      : {metrics['confianca_global']['media_pct']}%")
print(f"  Publico.pt          : {n_publico} registos ({pct_publico}% do total)")
print(f"  Ano mais dificil    : {ano_mais_dificil['ano']} (IDE={ano_mais_dificil['ide']})")
print(f"  Ano mais facil      : {ano_mais_facil['ano']} (IDE={ano_mais_facil['ide']})")
print(f"\n  Output: data/quality_metrics.json")
print("=" * 60)
