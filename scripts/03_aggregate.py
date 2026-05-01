# -*- coding: utf-8 -*-
# scripts/03_aggregate.py — VERSÃO 3 (Checkpoint + Confiança)
#
# NOVIDADES v3:
#   1. Lê dados do checkpoint_v4.json (fonte única consolidada Google+Groq)
#   2. Adiciona métricas de confiança por ano/categoria:
#      - desvio_padrao: dispersão dos valores extraídos
#      - coef_variacao: stddev / mediana (normalizado)
#      - n_fontes: número de notícias distintas
#      - confianca_pct: score de confiança 0-100%
#   3. Mantém lógica de fallback histórico (INE/Pordata)
#   4. Gera final_for_frontend.json com todas as métricas

import json, statistics, os, math
from collections import defaultdict

# ═══════════════════════════════════════════════════════════════════════════════
# HISTORICOS — Valores reais para Portugal, 1996–2024
# ═══════════════════════════════════════════════════════════════════════════════
#
# INDICADORES E FONTES:
#
# ── combustivel (€/litro) ─────────────────────────────────────────────────────
#   Media aritmetica simples entre Gasolina 95 e Gasoleo Rodoviario
#   (precos de venda ao publico, inclui todas as taxas)
#
#   Fonte A — 1996-2001 (valores em Escudos, convertidos a EUR pela taxa fixa
#             1 EUR = 200,482 PTE, Regulamento CE n.2866/98):
#     DGEG — Divisao de Estatistica, "Precos de Venda ao Publico das Gasolinas"
#     Ficheiro: dgeg-pma-1960-2003.xlsx — medias anuais ponderadas por dias de vigencia
#
#   Fonte B — 2002-2003 (valores ja em EUR): idem ficheiro DGEG 1960-2003
#
#   Fonte C — 2004-2024:
#     DGEG — "Precos Medios Anuais dos Combustiveis Liquidos e Gasosos, Portugal Continental"
#     Ficheiro: dgeg-pma-2004-2025_pt.xlsx
#     URL: https://www.dgeg.gov.pt/pt/estatistica/energia/precos-de-energia/
#          precos-de-combustiveis-em-portugal-continental/
#     2004-2014: "Gasolina 95/aditivada base" + "Gasoleo/aditivado base"
#     2015-2024: "Gasolina Simples 95" + "Gasoleo Simples"
#
# ── salario (€/mes) ───────────────────────────────────────────────────────────
#   Retribuicao Minima Mensal Garantida (RMMG)
#   Fonte: PORDATA — https://www.pordata.pt/
#   Serie 1996-2024 (valores confirmados pelo utilizador em 01/05/2026)
#
# ── inflacao (%) ──────────────────────────────────────────────────────────────
#   Taxa de variacao media anual do IPC
#   Fonte: INE — https://www.ine.pt
#
# ── habitacao (€/m2) ──────────────────────────────────────────────────────────
#   • 1996-2009: ESTIMATIVAS — sem serie oficial gratuita continua
#     Base: reconstrucao a partir do Indice de Precos da Habitacao do BPstat
#     (serie 12559645, base 2015=100) e Confidencial Imobiliario
#   • 2009-2017: INE — Inquerito a Avaliacao Bancaria na Habitacao (IABH)
#   • 2018-2024: INE — Estatisticas de Precos da Habitacao ao Nivel Local
#     (preco mediano de transacao, dados fiscais AT/IMT/IMI)
#     2022=1484, 2023=1611, 2024=1777 (valores oficiais INE)
# ═══════════════════════════════════════════════════════════════════════════════

HISTORICOS = {
    # ano: {habitacao(€/m²*), combustivel(€/L), salario(€/mes), inflacao(%)}
    # * = estimativa nao-oficial para 1996-2017

    # 1996-2001: combustivel convertido de Escudos (/ 200,482)
    1996: {"habitacao":  400, "combustivel": 0.673, "salario": 272.3, "inflacao":  3.1},
    # gas95=0.789€ gas=0.557€ | hab=estimativa
    1997: {"habitacao":  440, "combustivel": 0.693, "salario": 282.8, "inflacao":  2.3},
    # gas95=0.813€ gas=0.574€ | hab=estimativa
    1998: {"habitacao":  490, "combustivel": 0.686, "salario": 293.8, "inflacao":  2.8},
    # gas95=0.810€ gas=0.562€ | hab=estimativa
    1999: {"habitacao":  550, "combustivel": 0.682, "salario": 305.8, "inflacao":  2.4},
    # gas95=0.803€ gas=0.561€ | hab=estimativa
    2000: {"habitacao":  620, "combustivel": 0.772, "salario": 318.2, "inflacao":  2.9},
    # gas95=0.867€ gas=0.677€ | hab=estimativa
    2001: {"habitacao":  680, "combustivel": 0.796, "salario": 334.2, "inflacao":  4.4},
    # gas95=0.913€ gas=0.679€ | hab=estimativa

    # 2002-2003: combustivel ja em EUR
    2002: {"habitacao":  720, "combustivel": 0.765, "salario": 348.0, "inflacao":  3.7},
    # gas95=0.858€ gas=0.671€ | hab=estimativa
    2003: {"habitacao":  740, "combustivel": 0.834, "salario": 356.6, "inflacao":  3.3},
    # gas95=0.957€ gas=0.710€ | hab=estimativa

    # 2004-2014: DGEG gasolina aditivada base + gasoleo aditivado
    2004: {"habitacao":  750, "combustivel": 0.911, "salario": 365.6, "inflacao":  2.5},
    # gas95=1.033€ gas=0.789€
    2005: {"habitacao":  760, "combustivel": 1.044, "salario": 374.7, "inflacao":  2.3},
    # gas95=1.149€ gas=0.939€
    2006: {"habitacao":  780, "combustivel": 1.162, "salario": 385.9, "inflacao":  3.0},
    # gas95=1.279€ gas=1.044€
    2007: {"habitacao":  810, "combustivel": 1.202, "salario": 403.0, "inflacao":  2.5},
    # gas95=1.322€ gas=1.081€
    2008: {"habitacao":  840, "combustivel": 1.323, "salario": 426.0, "inflacao":  2.7},
    # gas95=1.386€ gas=1.260€
    2009: {"habitacao":  820, "combustivel": 1.119, "salario": 450.0, "inflacao": -0.9},
    # gas95=1.235€ gas=1.003€
    2010: {"habitacao":  900, "combustivel": 1.263, "salario": 475.0, "inflacao":  1.4},
    # gas95=1.373€ gas=1.153€ | hab=IABH INE
    2011: {"habitacao":  880, "combustivel": 1.459, "salario": 485.0, "inflacao":  3.7},
    # gas95=1.546€ gas=1.372€ | hab=IABH INE
    2012: {"habitacao":  840, "combustivel": 1.546, "salario": 485.0, "inflacao":  2.8},
    # gas95=1.641€ gas=1.450€ | hab=IABH INE
    2013: {"habitacao":  810, "combustivel": 1.484, "salario": 485.0, "inflacao":  0.3},
    # gas95=1.579€ gas=1.388€ | hab=IABH INE
    2014: {"habitacao":  800, "combustivel": 1.414, "salario": 485.0, "inflacao": -0.3},
    # gas95=1.524€ gas=1.303€ | hab=IABH INE

    # 2015-2024: DGEG gasolina simples 95 + gasoleo simples
    2015: {"habitacao":  830, "combustivel": 1.301, "salario": 505.0, "inflacao":  0.5},
    # gas95=1.432€ gas=1.171€ | hab=IABH INE
    2016: {"habitacao":  870, "combustivel": 1.243, "salario": 530.0, "inflacao":  0.6},
    # gas95=1.368€ gas=1.119€ | hab=IABH INE
    2017: {"habitacao":  960, "combustivel": 1.352, "salario": 557.0, "inflacao":  1.6},
    # gas95=1.463€ gas=1.242€ | hab=IABH/Confidencial Imobiliario
    2018: {"habitacao":  930, "combustivel": 1.440, "salario": 580.0, "inflacao":  1.2},
    # gas95=1.537€ gas=1.343€ | hab=INE Precos Habitacao (trimestral, est.)
    2019: {"habitacao": 1050, "combustivel": 1.427, "salario": 600.0, "inflacao":  0.3},
    # gas95=1.492€ gas=1.363€ | hab=INE Precos Habitacao (est.)
    2020: {"habitacao": 1095, "combustivel": 1.316, "salario": 635.0, "inflacao": -0.1},
    # gas95=1.387€ gas=1.244€ | hab=INE Precos Habitacao (est.)
    2021: {"habitacao": 1300, "combustivel": 1.521, "salario": 665.0, "inflacao":  1.3},
    # gas95=1.619€ gas=1.423€ | hab=INE Precos Habitacao (est.)
    2022: {"habitacao": 1484, "combustivel": 1.823, "salario": 705.0, "inflacao":  7.8},
    # gas95=1.850€ gas=1.796€ | hab=INE Estatisticas Construcao e Habitacao 2022
    2023: {"habitacao": 1611, "combustivel": 1.654, "salario": 760.0, "inflacao":  5.4},
    # gas95=1.719€ gas=1.589€ | hab=INE Estatisticas Construcao e Habitacao 2023
    2024: {"habitacao": 1777, "combustivel": 1.648, "salario": 820.0, "inflacao":  2.3},
    # gas95=1.716€ gas=1.581€ | hab=INE Estatisticas Construcao e Habitacao 2024
}

# ─── Funções de qualidade de dados ────────────────────────────────────────────
def remove_outliers(values):
    """Remove outliers usando IQR. Retorna lista limpa."""
    if len(values) < 4:
        return values
    s = sorted(values)
    q1 = statistics.median(s[:len(s)//2])
    q3 = statistics.median(s[len(s)//2 + len(s)%2:])
    iqr = q3 - q1
    if iqr == 0:
        return values
    lo = q1 - 1.5 * iqr
    hi = q3 + 1.5 * iqr
    cleaned = [v for v in values if lo <= v <= hi]
    return cleaned if cleaned else values


def calcular_confianca(valores_limpos, n_fontes_original, relevancia_media):
    """
    Calcula um score de confiança 0-100% com base em 3 factores:

    1. CONSISTÊNCIA (40%): Quanto menores o desvio padrão relativo (CV),
       mais consistentes são as fontes entre si → mais confiança.
       CV = stddev / mediana. CV=0 → 100%, CV>=0.5 → 0%

    2. VOLUME (35%): Quantas fontes independentes reportaram o valor.
       1 fonte → 20%, 2 → 45%, 3 → 65%, 5+ → 100%

    3. RELEVÂNCIA (25%): Média de relevância dos itens (escala 1-5).
       Relevância 5 → 100%, relevância 1 → 0%

    Retorna dict com score total e parcelas para transparência no frontend.
    """
    n = len(valores_limpos)
    if n == 0:
        return {"confianca_pct": 0, "desvio_padrao": None, "coef_variacao": None,
                "score_consistencia": 0, "score_volume": 0, "score_relevancia": 0}

    mediana = statistics.median(valores_limpos)
    std = statistics.stdev(valores_limpos) if n >= 2 else 0.0
    cv  = (std / mediana) if mediana != 0 else 0.0

    # Score de consistência: penaliza CV alto
    score_consistencia = max(0.0, 1.0 - (cv / 0.5)) * 100  # 0% se CV >= 50%
    score_consistencia = min(100.0, score_consistencia)

    # Score de volume: logarítmico, satura em 5 fontes
    score_volume = min(100.0, (math.log(n + 1) / math.log(6)) * 100)

    # Score de relevância: 1-5 mapeado para 0-100%
    score_relevancia = max(0.0, min(100.0, (relevancia_media - 1) / 4 * 100))

    # Score composto ponderado
    confianca = (
        score_consistencia * 0.40 +
        score_volume       * 0.35 +
        score_relevancia   * 0.25
    )

    return {
        "confianca_pct":    round(confianca, 1),
        "desvio_padrao":    round(std, 4) if n >= 2 else None,
        "coef_variacao":    round(cv, 4)  if n >= 2 else None,
        "score_consistencia": round(score_consistencia, 1),
        "score_volume":       round(score_volume, 1),
        "score_relevancia":   round(score_relevancia, 1),
    }


# ─── Carrega dados do checkpoint consolidado (Google + Groq) ──────────────────
CHECKPOINT = "data/checkpoint_v4.json"
try:
    with open(CHECKPOINT, encoding="utf-8") as f:
        ck = json.load(f)
    data = ck.get("results", [])
    print(f"[Dados] {len(data)} registos extraídos carregados de {CHECKPOINT}")
    print(f"[Dados] {len(ck.get('processed', []))} snippets processados no total")
except FileNotFoundError:
    print(f"[AVISO] {CHECKPOINT} não encontrado. A usar só dados históricos.")
    data = []

# ─── Agrupa por ano + categoria ───────────────────────────────────────────────
by_year = defaultdict(lambda: defaultdict(list))
for item in data:
    ano, cat = item.get("ano"), item.get("categoria")
    val = item.get("valor_numerico")
    if ano and cat and val is not None and 1996 <= ano <= 2024:
        by_year[ano][cat].append(item)

# ─── Categorias que entram no IDE ────────────────────────────────────────────
IDE_CATS = {"habitacao", "combustivel", "salario", "inflacao"}

# ─── Constrói dataset por ano ─────────────────────────────────────────────────
final = {}
anos_com_dados_reais = set()
stats_qualidade = []  # para relatório final

for ano in range(1996, 2025):
    final[ano] = {}
    cats_ano = by_year.get(ano, {})

    for cat, items in cats_ano.items():
        valores_brutos = [i["valor_numerico"] for i in items if i.get("valor_numerico") is not None]
        valores = remove_outliers(valores_brutos)
        melhor  = max(items, key=lambda x: x.get("relevancia", 0))
        relev_media = statistics.mean(i.get("relevancia", 3) for i in items)

        confianca = calcular_confianca(valores, len(items), relev_media)

        links_arquivo = [melhor.get("link_arquivo")] if melhor.get("link_arquivo") else []
        for i in items:
            if i.get("link_arquivo") and i.get("link_arquivo") not in links_arquivo:
                links_arquivo.append(i.get("link_arquivo"))
        links_arquivo = links_arquivo[:5]
                
        links_screenshot = [melhor.get("link_screenshot")] if melhor.get("link_screenshot") else []
        for i in items:
            if i.get("link_screenshot") and i.get("link_screenshot") not in links_screenshot:
                links_screenshot.append(i.get("link_screenshot"))
        links_screenshot = links_screenshot[:5]

        final[ano][cat] = {
            "valor_mediana":    round(statistics.median(valores), 4) if valores else None,
            "n_fontes":         len(items),
            "n_fontes_apos_iqr": len(valores),
            "fonte_historica":  False,
            **confianca,  # desvio_padrao, coef_variacao, confianca_pct, scores parciais
            "noticia_destaque": {
                "titulo":          melhor.get("titulo_noticia", ""),
                "contexto":        melhor.get("contexto_curto", ""),
                "fonte":           melhor.get("fonte_nome", ""),
                "sentimento":      melhor.get("sentimento", ""),
                "link_arquivo":    links_arquivo,
                "link_screenshot": links_screenshot,
            }
        }
        if cat in IDE_CATS and valores:
            anos_com_dados_reais.add(ano)
            if cat in IDE_CATS:
                stats_qualidade.append({
                    "ano": ano, "cat": cat,
                    "n": len(valores), "cv": confianca.get("coef_variacao"),
                    "conf": confianca["confianca_pct"]
                })

    # Fallback histórico para categorias IDE em falta
    hist = HISTORICOS.get(ano, {})
    for cat_key in IDE_CATS:
        if cat_key not in final[ano] and hist.get(cat_key) is not None:
            final[ano][cat_key] = {
                "valor_mediana":    hist[cat_key],
                "n_fontes":         0,
                "n_fontes_apos_iqr": 0,
                "fonte_historica":  True,
                "confianca_pct":    None,   # histórico não tem score de confiança
                "desvio_padrao":    None,
                "coef_variacao":    None,
                "score_consistencia": None,
                "score_volume":     None,
                "score_relevancia": None,
                "noticia_destaque": {
                    "titulo":   f"Dados históricos {ano} — {cat_key} (INE/Pordata)",
                    "contexto": f"Valor de referência histórico {ano}",
                    "fonte":    "INE/Pordata",
                    "sentimento": "estavel",
                    "link_arquivo": "", "link_screenshot": "",
                }
            }

print(f"\n[Dataset] Anos com dados reais do Arquivo.pt: {sorted(anos_com_dados_reais)}")

# ─── Cálculo do IDE ───────────────────────────────────────────────────────────
def norm(vals_dict, invert=False):
    clean = {k: v for k, v in vals_dict.items() if v is not None}
    if not clean:
        return {}
    mn, mx = min(clean.values()), max(clean.values())
    if mx == mn:
        return {k: 50 for k in clean}
    normalized = {k: (v - mn) / (mx - mn) * 100 for k, v in clean.items()}
    if invert:
        normalized = {k: 100 - v for k, v in normalized.items()}
    return {k: round(v, 1) for k, v in normalized.items()}

hab  = {a: final[a].get("habitacao",  {}).get("valor_mediana") for a in final}
comb = {a: final[a].get("combustivel",{}).get("valor_mediana") for a in final}
sal  = {a: final[a].get("salario",    {}).get("valor_mediana") for a in final}
inf  = {a: final[a].get("inflacao",   {}).get("valor_mediana") for a in final}

h_n = norm(hab)
c_n = norm(comb)
s_n = norm(sal, True)   # invertido: salário alto = vida mais fácil
i_n = norm(inf)

# IDE: confiança do índice = média ponderada das confianças das componentes
for ano in final:
    ide = round(
        h_n.get(ano, 50) * 0.35 +
        s_n.get(ano, 50) * 0.30 +
        c_n.get(ano, 50) * 0.20 +
        i_n.get(ano, 50) * 0.15, 1
    )

    # Confiança do IDE = média das confianças das 4 componentes (só dados reais)
    confianças_componentes = [
        final[ano].get(cat, {}).get("confianca_pct")
        for cat in IDE_CATS
        if final[ano].get(cat, {}).get("confianca_pct") is not None
    ]
    ide_confianca = round(statistics.mean(confianças_componentes), 1) if confianças_componentes else None

    final[ano]["ide"] = ide
    final[ano]["ide_confianca_pct"] = ide_confianca   # NOVO: confiança do IDE
    final[ano]["ide_componentes"] = {
        "habitacao":   h_n.get(ano, 50),
        "salario":     s_n.get(ano, 50),
        "combustivel": c_n.get(ano, 50),
        "inflacao":    i_n.get(ano, 50),
    }

# ─── Saída ────────────────────────────────────────────────────────────────────
final_str = {str(k): v for k, v in final.items()}
os.makedirs("data", exist_ok=True)
with open("data/final_for_frontend.json", "w", encoding="utf-8") as f:
    json.dump(final_str, f, ensure_ascii=False, indent=2)

ides = {a: final[a]["ide"] for a in final if "ide" in final[a]}
pior    = max(ides, key=ides.get)
melhor_ = min(ides, key=ides.get)

print(f"\n{'='*60}")
print(f"AGREGAÇÃO COMPLETA")
print(f"  Anos cobertos    : {len(final)}")
print(f"  Ano mais difícil : {pior}  (IDE: {ides[pior]})")
print(f"  Ano mais fácil   : {melhor_} (IDE: {ides[melhor_]})")
print(f"  Output           : data/final_for_frontend.json")
print(f"{'='*60}")

# ─── Relatório de Qualidade ───────────────────────────────────────────────────
n_hist = sum(
    1 for ano in final for cat in IDE_CATS
    if final[ano].get(cat, {}).get("fonte_historica")
)
n_real = sum(
    1 for ano in final for cat in IDE_CATS
    if not final[ano].get(cat, {}).get("fonte_historica") and final[ano].get(cat)
)
print(f"\n{'-'*60}")
print(f"QUALIDADE DOS DADOS")
print(f"  Pontos reais (Arquivo.pt): {n_real}")
print(f"  Pontos históricos (INE)  : {n_hist}")

if stats_qualidade:
    confianças = [s["conf"] for s in stats_qualidade]
    print(f"\n  Score de confiança (dados reais):")
    print(f"    Média    : {statistics.mean(confianças):.1f}%")
    print(f"    Mediana  : {statistics.median(confianças):.1f}%")
    print(f"    Mínimo   : {min(confianças):.1f}%")
    print(f"    Máximo   : {max(confianças):.1f}%")

    # Top 5 entradas com mais confiança
    top = sorted(stats_qualidade, key=lambda x: -x["conf"])[:5]
    print(f"\n  Top 5 entradas mais confiáveis:")
    for s in top:
        print(f"    {s['ano']} {s['cat']:<12} n={s['n']} CV={s['cv'] or 0:.2f} -> {s['conf']}%")

    # Bottom 5
    bot = sorted(stats_qualidade, key=lambda x: x["conf"])[:5]
    print(f"\n  5 entradas com menos confiança:")
    for s in bot:
        print(f"    {s['ano']} {s['cat']:<12} n={s['n']} CV={s['cv'] or 0:.2f} -> {s['conf']}%")

# Confiança IDE por ano
print(f"\n  Confiança do IDE por ano (só anos com dados reais):")
for ano in sorted(final.keys()):
    conf = final[ano].get("ide_confianca_pct")
    ide  = final[ano].get("ide")
    if conf is not None:
        bar = "#" * int(conf / 10)
        print(f"    {ano}  IDE={ide:4.1f}  Confiança={conf:5.1f}%  {bar}")
print(f"{'-'*60}")
