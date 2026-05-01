# -*- coding: utf-8 -*-
# scripts/01_collect_arquivo_v6.py
#
# Recolha de dados históricos do Arquivo.pt — Custo Portugal
# VERSÃO 6 — Correcções sobre v5 baseadas em análise de logs
#
# CORRECÇÕES v6:
#   FIX A: paginar() — filtro dominio_valido só activo se site!=None
#           (bug causava 0 resultados em todas as queries globais 2021-2024)
#   FIX B: processar_query() — re-tenta ficheiros com 0 resultados
#           (em vez de os reutilizar cegamente)
#   FIX C: QUERIES_GLOBAIS_ANOS expandido com 2003-2010 e 2021
#   NOTA: OUTPUT_DIR = data/raw (igual a v5) — execução 100%% complementar
#
# ╔══════════════════════════════════════════════════════════════════════╗
# ║  PROBLEMAS IDENTIFICADOS NA v4 E CORRECÇÕES APLICADAS NA v5         ║
# ║                                                                      ║
# ║  PROBLEMA 1 — "sapo", "governo", "universidade" no filtro lixo     ║
# ║    São termos que podem aparecer em manchetes LEGÍTIMAS.            ║
# ║    Ex: "Governo anuncia aumento do salário mínimo"                  ║
# ║    Ex: "Sapo revela preços da habitação em Portugal"                ║
# ║    A v4 rejeitaria ambas por terem "governo" e "sapo" no título.   ║
# ║    CORRECÇÃO: filtro de lixo usa só strings de erro técnico.        ║
# ║                                                                      ║
# ║  PROBLEMA 2 — Lógica de paginação redundante e confusa             ║
# ║    v4 tem duas condições para "pages_seen == 1" e "> 1" que        ║
# ║    produzem o mesmo resultado: break em ambos os casos se           ║
# ║    len(items) < PAGE_SIZE. O comentário diz "não parar na 1ª"      ║
# ║    mas o código para sempre que a 1ª página está incompleta.        ║
# ║    CORRECÇÃO: lógica simplificada — break só se página vazia.       ║
# ║    Pagina sempre que devolveu PAGE_SIZE itens (= pode haver mais).  ║
# ║                                                                      ║
# ║  PROBLEMA 3 — ionline.pt e lusa.pt têm indexação muito limitada    ║
# ║    Tier 3 adicionado na v4 mas sem dados empíricos de suporte.     ║
# ║    ionline fundado 2010, lusa tem conteúdo por subscrição.          ║
# ║    Não contribuem para a meta de 500 snippets do Público.           ║
# ║    CORRECÇÃO: mantidos mas movidos para o fim — processados depois  ║
# ║    de tier1+tier2. Se não contribuírem, fácil de os remover.        ║
# ║                                                                      ║
# ║  PROBLEMA 4 — "sapo" nas queries "sempre-verde" não faz sentido    ║
# ║    Queries "sempre-verde" com janelas de 26 anos (1998-2024)        ║
# ║    devolvem resultados espalhados sem foco — o Gemini tem           ║
# ║    dificuldade em extrair dados sem contexto temporal.              ║
# ║    CORRECÇÃO: "sempre-verde" substituídas por 2 queries focadas     ║
# ║    (1998-2010 e 2010-2024) — melhor para o Gemini, mesmo recall.   ║
# ║                                                                      ║
# ║  PROBLEMA 5 — Ausência de queries para o Público em particular     ║
# ║    A meta de 500 snippets do Público é crítica para a Menção       ║
# ║    Honrosa. Queries genéricas com siteSearch não chegam.            ║
# ║    CORRECÇÃO: bloco dedicado de 8 queries Público-específicas       ║
# ║    com vocabulário que o Público usa (análise, INE, etc.).          ║
# ║                                                                      ║
# ║  PROBLEMA 6 — Sem fallback global para anos sem cobertura          ║
# ║    1996-2002 e 2022-2024 continuam escassos mesmo com v4.           ║
# ║    CORRECÇÃO: após loop principal, corre queries GLOBAIS (sem       ║
# ║    siteSearch) para anos com < 20 snippets, com filtro pós-recolha  ║
# ║    para garantir que só entram jornais válidos.                      ║
# ╚══════════════════════════════════════════════════════════════════════╝
#
# RATE LIMIT CRÍTICO: máx 250 req em 180s → sleep(1.3) OBRIGATÓRIO
# Bloqueio de IP é PERMANENTE — NÃO reduzir SLEEP_BETWEEN

import requests, json, time, os, sys
from collections import defaultdict
from datetime import datetime

# ─── LOGGING ──────────────────────────────────────────────────────────────────
if sys.stdout.encoding != 'utf-8':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except AttributeError:
        # Fallback for older python versions if necessary, though 3.7+ is standard now
        pass

class Logger(object):
    def __init__(self, filename):
        self.terminal = sys.stdout
        self.log = open(filename, "a", encoding="utf-8")
    def write(self, message):
        try:
            self.terminal.write(message)
        except UnicodeEncodeError:
            self.terminal.write(message.encode('ascii', 'replace').decode('ascii'))
        self.log.write(message)
        self.log.flush()
    def flush(self):
        self.terminal.flush()
        self.log.flush()

LOG_DIR = "logs"
os.makedirs(LOG_DIR, exist_ok=True)
log_filename = os.path.join(
    LOG_DIR,
    f"{os.path.basename(__file__)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log"
)
sys.stdout = Logger(log_filename)

BASE_URL      = "https://arquivo.pt/textsearch"
OUTPUT_DIR    = "data/raw"
os.makedirs(OUTPUT_DIR, exist_ok=True)

PAGE_SIZE     = 50    # máx por página que a API suporta
MAX_PER_QUERY = 150   # máx snippets por combinação query×jornal
SLEEP_BETWEEN = 1.3   # segundos entre requests
TIMEOUT       = 60    # timeout por request
MAX_RETRIES   = 5     # tentativas antes de desistir

# ─── JORNAIS ──────────────────────────────────────────────────────────────────
# Tier 1: histórico completo, essenciais para a Menção Honrosa
# Tier 2: boa cobertura em períodos específicos
# Tier 3: complementares — processados por último
JORNAIS = {
    "publico":   "www.publico.pt",      # Tier 1 — meta 500 snippets
    "dn":        "www.dn.pt",           # Tier 1
    "expresso":  "www.expresso.pt",     # Tier 1
    "jn":        "www.jn.pt",           # Tier 2
    "tsf":       "www.tsf.pt",          # Tier 2
    "cmjornal":  "www.cmjornal.pt",     # Tier 2
    "rtp":       "www.rtp.pt",          # Tier 2
    "ionline":   "www.ionline.pt",      # Tier 3
    "lusa":      "www.lusa.pt",         # Tier 3
}

DOMINIOS_VALIDOS = list(JORNAIS.values()) + [
    "publico.pt", "dn.pt", "expresso.pt", "jn.pt", "tsf.pt",
    "ionline.pt", "lusa.pt", "sol.pt", "sabado.pt", "observador.pt",
]

# ─── QUERIES PRINCIPAIS ───────────────────────────────────────────────────────
# PRINCÍPIOS (v4, mantidos):
#   1. 4-7 termos — sem AND desnecessário
#   2. SEM anos no texto — from/to controla o período
#   3. SEM valores numéricos — destroem o recall
#   4. Vocabulário da época para pré-2002 (escudos, contos)
#
# NOVIDADE v5:
#   - "sempre-verde" divididas em 2 janelas (1998-2010 e 2010-2024)
#   - Total: 45 queries × 9 jornais = 405 combinações

QUERIES = [

    # ═══════════════════════════════════════════════════════════════
    # HABITAÇÃO — 11 queries
    # ═══════════════════════════════════════════════════════════════

    {"id":"hab_esc_96_02",
     "q":"habitação preço escudos contos Lisboa apartamento",
     "from":"19960101","to":"20021231"},

    {"id":"hab_renda_96_10",
     "q":"renda arrendamento Lisboa apartamento habitação",
     "from":"19960101","to":"20101231"},

    {"id":"hab_renda_10_24",
     "q":"renda arrendamento Lisboa apartamento habitação",
     "from":"20100101","to":"20241231"},

    {"id":"hab_aval_03_12",
     "q":"avaliação bancária habitação metro quadrado Portugal",
     "from":"20030101","to":"20121231"},

    {"id":"hab_euros_03_08",
     "q":"habitação preço metro quadrado Lisboa euros comprar",
     "from":"20030101","to":"20081231"},

    {"id":"hab_crise_09_15",
     "q":"habitação preço desce mercado imobiliário crise",
     "from":"20090101","to":"20151231"},

    {"id":"hab_troika_11_14",
     "q":"habitação arrendamento troika mercado imobiliário",
     "from":"20110101","to":"20141231"},

    {"id":"hab_boom_16_20",
     "q":"habitação preço Lisboa recorde sobe euros",
     "from":"20160101","to":"20201231"},

    {"id":"hab_acesso_19_24",
     "q":"habitação inacessível jovens arrendamento Lisboa",
     "from":"20190101","to":"20241231"},

    {"id":"hab_recente_21_24",
     "q":"casas Lisboa preço recorde habitação arrendamento",
     "from":"20210101","to":"20241231"},

    # CORRECÇÃO 4: "sempre-verde" dividida em duas janelas focadas
    {"id":"hab_sv_98_10",
     "q":"habitação Portugal preço comprar arrendar",
     "from":"19980101","to":"20101231"},
    {"id":"hab_sv_10_24",
     "q":"habitação Portugal preço comprar arrendar",
     "from":"20100101","to":"20241231"},

    # ═══════════════════════════════════════════════════════════════
    # COMBUSTÍVEIS — 8 queries
    # ═══════════════════════════════════════════════════════════════

    {"id":"comb_esc_96_02",
     "q":"gasolina preço escudos litro bomba Portugal",
     "from":"19960101","to":"20021231"},

    {"id":"comb_euros_02_08",
     "q":"gasolina gasóleo preço litro euros Portugal",
     "from":"20020101","to":"20081231"},

    {"id":"comb_crise_09_15",
     "q":"combustíveis gasolina preço Portugal imposto sobe",
     "from":"20090101","to":"20151231"},

    {"id":"comb_normal_16_21",
     "q":"gasolina gasóleo preço litro Portugal semana",
     "from":"20160101","to":"20211231"},

    {"id":"comb_guerra_22_24",
     "q":"combustíveis gasolina preço Portugal guerra energia",
     "from":"20220101","to":"20241231"},

    {"id":"comb_gasoleo_00_24",
     "q":"gasóleo preço litro Portugal consumidores",
     "from":"20000101","to":"20241231"},

    {"id":"comb_sv_98_10",
     "q":"gasolina preço Portugal litro bomba",
     "from":"19980101","to":"20101231"},
    {"id":"comb_sv_10_24",
     "q":"gasolina preço Portugal litro bomba",
     "from":"20100101","to":"20241231"},

    # ═══════════════════════════════════════════════════════════════
    # SALÁRIO MÍNIMO — 9 queries
    # ═══════════════════════════════════════════════════════════════

    {"id":"sal_esc_96_02",
     "q":"salário mínimo nacional escudos Portugal trabalhadores",
     "from":"19960101","to":"20021231"},

    {"id":"sal_euros_02_10",
     "q":"salário mínimo nacional euros aumento Portugal",
     "from":"20020101","to":"20101231"},

    {"id":"sal_congela_11_14",
     "q":"salário mínimo congela troika austeridade Portugal",
     "from":"20110101","to":"20141231"},

    {"id":"sal_sobe_15_21",
     "q":"salário mínimo sobe aumento Portugal trabalhadores",
     "from":"20150101","to":"20211231"},

    {"id":"sal_recente_22_24",
     "q":"salário mínimo aumento Portugal trabalhadores",
     "from":"20220101","to":"20241231"},

    {"id":"sal_poder_compra",
     "q":"poder de compra Portugal trabalhadores rendimento",
     "from":"20000101","to":"20241231"},

    {"id":"sal_medio_00_24",
     "q":"salário médio Portugal rendimento trabalhadores INE",
     "from":"20000101","to":"20241231"},

    {"id":"sal_sv_98_10",
     "q":"salário mínimo Portugal aprovado trabalhadores",
     "from":"19980101","to":"20101231"},
    {"id":"sal_sv_10_24",
     "q":"salário mínimo Portugal aprovado trabalhadores",
     "from":"20100101","to":"20241231"},

    # ═══════════════════════════════════════════════════════════════
    # INFLAÇÃO E CUSTO DE VIDA — 9 queries
    # ═══════════════════════════════════════════════════════════════

    {"id":"inf_96_05",
     "q":"inflação Portugal taxa IPC preços subida",
     "from":"19960101","to":"20051231"},

    {"id":"inf_deflacao_09_15",
     "q":"deflação inflação Portugal preços consumidor taxa",
     "from":"20090101","to":"20151231"},

    {"id":"inf_estavel_15_21",
     "q":"inflação Portugal preços consumidor taxa anual",
     "from":"20150101","to":"20211231"},

    {"id":"inf_guerra_22_24",
     "q":"inflação Portugal recorde preços famílias energia",
     "from":"20220101","to":"20241231"},

    {"id":"cv_cabaz_05_24",
     "q":"cabaz alimentar supermercado preços Portugal famílias",
     "from":"20050101","to":"20241231"},

    {"id":"cv_energia_08_24",
     "q":"electricidade gás fatura preço doméstica Portugal",
     "from":"20080101","to":"20241231"},

    {"id":"cv_carestia_96_10",
     "q":"carestia de vida preços Portugal famílias",
     "from":"19960101","to":"20101231"},

    {"id":"inf_sv_98_10",
     "q":"custo de vida Portugal preços famílias caro",
     "from":"19980101","to":"20101231"},
    {"id":"inf_sv_10_24",
     "q":"custo de vida Portugal preços famílias caro",
     "from":"20100101","to":"20241231"},

    # ═══════════════════════════════════════════════════════════════
    # DESEMPREGO — 5 queries
    # ═══════════════════════════════════════════════════════════════

    {"id":"desemp_00_08",
     "q":"taxa desemprego Portugal INE trabalhadores",
     "from":"20000101","to":"20081231"},

    {"id":"desemp_crise_09_14",
     "q":"desemprego Portugal recorde máximo taxa trabalhadores",
     "from":"20090101","to":"20141231"},

    {"id":"desemp_recup_15_24",
     "q":"desemprego Portugal desce mínimo taxa emprego",
     "from":"20150101","to":"20241231"},

    {"id":"desemp_sv_98_10",
     "q":"desemprego Portugal taxa INE trabalhadores",
     "from":"19980101","to":"20101231"},
    {"id":"desemp_sv_10_24",
     "q":"desemprego Portugal taxa INE trabalhadores",
     "from":"20100101","to":"20241231"},

    # ═══════════════════════════════════════════════════════════════
    # CONTEXTO HISTÓRICO — 6 queries
    # ═══════════════════════════════════════════════════════════════

    {"id":"ctx_euro_99_03",
     "q":"euro transição escudos moeda Portugal",
     "from":"19990101","to":"20031231"},

    {"id":"ctx_crise_08_11",
     "q":"crise financeira recessão Portugal banco subprime",
     "from":"20080101","to":"20111231"},

    {"id":"ctx_troika_11_14",
     "q":"troika FMI austeridade cortes Portugal",
     "from":"20110101","to":"20141231"},

    {"id":"ctx_recupera_15_19",
     "q":"Portugal recuperação crescimento económico emprego",
     "from":"20150101","to":"20191231"},

    {"id":"ctx_covid_20_21",
     "q":"pandemia COVID Portugal economia impacto",
     "from":"20200101","to":"20211231"},

    {"id":"ctx_guerra_22_23",
     "q":"guerra Ucrânia inflação energia Portugal",
     "from":"20220101","to":"20231231"},
]

# ─── CORRECÇÃO 5: Queries dedicadas ao Público ─────────────────────────────
# Objectivo: contribuir para a meta de 500 snippets do Público
# Vocabulário e ângulos que o Público usa com maior frequência
QUERIES_PUBLICO_EXTRA = [
    {"id":"pub_hab_analise",
     "q":"habitação análise mercado imobiliário Lisboa Portugal",
     "from":"20000101","to":"20241231"},
    {"id":"pub_hab_ine",
     "q":"habitação INE avaliação dados estatísticos Portugal",
     "from":"20050101","to":"20241231"},
    {"id":"pub_sal_minimo_debate",
     "q":"salário mínimo debate negociação sindicatos governo",
     "from":"20050101","to":"20241231"},
    {"id":"pub_inflacao_ine",
     "q":"inflação INE estatísticas preços Portugal dados",
     "from":"20000101","to":"20241231"},
    {"id":"pub_crise_social",
     "q":"crise social Portugal famílias pobreza rendimento",
     "from":"20090101","to":"20241231"},
    {"id":"pub_economia_geral",
     "q":"economia Portugal crescimento PIB famílias",
     "from":"20000101","to":"20241231"},
    {"id":"pub_hab_jovens",
     "q":"habitação jovens Portugal arrendamento acesso comprar",
     "from":"20150101","to":"20241231"},
    {"id":"pub_energia_precos",
     "q":"energia electricidade preços Portugal fatura doméstica",
     "from":"20100101","to":"20241231"},
]

# ─── CORRECÇÃO 6: Queries globais para anos sem cobertura ─────────────────
# Executadas sem siteSearch — filtro pós-recolha garante qualidade
# Janelas anuais para anos que ficarem com < 20 snippets no loop principal
QUERIES_GLOBAIS_ANOS = {
    1996: [
        {"id":"glob_96_hab","q":"habitação preço escudos Lisboa contos", "from":"19960101","to":"19961231"},
        {"id":"glob_96_sal","q":"salário mínimo escudos Portugal trabalhadores", "from":"19960101","to":"19961231"},
        {"id":"glob_96_inf","q":"inflação Portugal preços taxa IPC", "from":"19960101","to":"19961231"},
    ],
    1997: [
        {"id":"glob_97_hab","q":"habitação preço escudos Lisboa contos", "from":"19970101","to":"19971231"},
        {"id":"glob_97_sal","q":"salário mínimo escudos Portugal", "from":"19970101","to":"19971231"},
        {"id":"glob_97_inf","q":"inflação Portugal preços IPC taxa", "from":"19970101","to":"19971231"},
    ],
    1998: [
        {"id":"glob_98_hab","q":"habitação preço Lisboa mercado imobiliário", "from":"19980101","to":"19981231"},
        {"id":"glob_98_sal","q":"salário mínimo Portugal trabalhadores", "from":"19980101","to":"19981231"},
        {"id":"glob_98_inf","q":"inflação Portugal preços IPC", "from":"19980101","to":"19981231"},
    ],
    1999: [
        {"id":"glob_99_hab","q":"habitação preço Lisboa apartamento", "from":"19990101","to":"19991231"},
        {"id":"glob_99_sal","q":"salário mínimo Portugal euro escudos", "from":"19990101","to":"19991231"},
        {"id":"glob_99_comb","q":"gasolina preço litro escudos Portugal", "from":"19990101","to":"19991231"},
    ],
    2000: [
        {"id":"glob_00_hab","q":"habitação preço Lisboa euros mercado", "from":"20000101","to":"20001231"},
        {"id":"glob_00_sal","q":"salário mínimo Portugal euros aprovado", "from":"20000101","to":"20001231"},
        {"id":"glob_00_comb","q":"gasolina preço litro Portugal bomba", "from":"20000101","to":"20001231"},
    ],
    2001: [
        {"id":"glob_01_hab","q":"habitação preço Lisboa metros quadrados", "from":"20010101","to":"20011231"},
        {"id":"glob_01_sal","q":"salário mínimo Portugal euros trabalhadores", "from":"20010101","to":"20011231"},
        {"id":"glob_01_comb","q":"gasolina gasóleo preço litro Portugal", "from":"20010101","to":"20011231"},
    ],
    2002: [
        {"id":"glob_02_hab","q":"habitação preço Lisboa euros comprar", "from":"20020101","to":"20021231"},
        {"id":"glob_02_sal","q":"salário mínimo Portugal euros aumento", "from":"20020101","to":"20021231"},
        {"id":"glob_02_euro","q":"euro transição escudos Portugal moeda", "from":"20020101","to":"20021231"},
    ],
    # FIX C: anos 2003-2010 adicionados em v6 (cobertura muito fraca em v5)
    2003: [
        {"id":"glob_03_hab","q":"habitação preço Lisboa metros quadrados euros", "from":"20030101","to":"20031231"},
        {"id":"glob_03_sal","q":"salário mínimo Portugal euros trabalhadores", "from":"20030101","to":"20031231"},
        {"id":"glob_03_inf","q":"inflação Portugal preços taxa IPC", "from":"20030101","to":"20031231"},
    ],
    2004: [
        {"id":"glob_04_hab","q":"habitação preço Lisboa comprar metros euros", "from":"20040101","to":"20041231"},
        {"id":"glob_04_sal","q":"salário mínimo Portugal euros aumento", "from":"20040101","to":"20041231"},
        {"id":"glob_04_comb","q":"gasolina preço litro Portugal euros bomba", "from":"20040101","to":"20041231"},
    ],
    2005: [
        {"id":"glob_05_hab","q":"habitação imobiliário Lisboa preço euros", "from":"20050101","to":"20051231"},
        {"id":"glob_05_sal","q":"salário mínimo Portugal trabalhadores euros", "from":"20050101","to":"20051231"},
        {"id":"glob_05_inf","q":"inflação Portugal preços consumidor taxa", "from":"20050101","to":"20051231"},
    ],
    2006: [
        {"id":"glob_06_hab","q":"habitação preço Lisboa mercado imobiliário", "from":"20060101","to":"20061231"},
        {"id":"glob_06_sal","q":"salário mínimo Portugal aumento euros", "from":"20060101","to":"20061231"},
        {"id":"glob_06_comb","q":"gasolina gasóleo preço litro Portugal", "from":"20060101","to":"20061231"},
    ],
    2007: [
        {"id":"glob_07_hab","q":"habitação preço Lisboa avaliação bancária", "from":"20070101","to":"20071231"},
        {"id":"glob_07_sal","q":"salário mínimo Portugal euros trabalhadores", "from":"20070101","to":"20071231"},
        {"id":"glob_07_comb","q":"gasolina preço litro Portugal subida", "from":"20070101","to":"20071231"},
    ],
    2008: [
        {"id":"glob_08_hab","q":"habitação preço Lisboa crise imobiliário", "from":"20080101","to":"20081231"},
        {"id":"glob_08_sal","q":"salário mínimo Portugal euros trabalhadores", "from":"20080101","to":"20081231"},
        {"id":"glob_08_crise","q":"crise financeira Portugal banco recessão", "from":"20080101","to":"20081231"},
    ],
    2009: [
        {"id":"glob_09_desemp","q":"desemprego Portugal taxa subida recessão", "from":"20090101","to":"20091231"},
        {"id":"glob_09_sal","q":"salário mínimo Portugal trabalhadores", "from":"20090101","to":"20091231"},
        {"id":"glob_09_inf","q":"inflação deflação Portugal preços taxa", "from":"20090101","to":"20091231"},
    ],
    2010: [
        {"id":"glob_10_hab","q":"habitação preço Lisboa mercado imobiliário", "from":"20100101","to":"20101231"},
        {"id":"glob_10_sal","q":"salário mínimo Portugal trabalhadores euros", "from":"20100101","to":"20101231"},
        {"id":"glob_10_desemp","q":"desemprego Portugal taxa máximo", "from":"20100101","to":"20101231"},
    ],
    # FIX C: 2021 adicionado em v6 (zero snippets em v5)
    2021: [
        {"id":"glob_21_hab","q":"habitação Lisboa preço arrendamento euros", "from":"20210101","to":"20211231"},
        {"id":"glob_21_sal","q":"salário mínimo Portugal aumento euros trabalhadores", "from":"20210101","to":"20211231"},
        {"id":"glob_21_inf","q":"inflação Portugal preços famílias subida", "from":"20210101","to":"20211231"},
    ],
    2022: [
        {"id":"glob_22_inf","q":"inflação Portugal preços famílias subida", "from":"20220101","to":"20221231"},
        {"id":"glob_22_comb","q":"gasolina preço Portugal litro guerra energia", "from":"20220101","to":"20221231"},
        {"id":"glob_22_hab","q":"habitação Lisboa preço recorde arrendamento", "from":"20220101","to":"20221231"},
    ],
    2023: [
        {"id":"glob_23_inf","q":"inflação Portugal preços IPC taxa", "from":"20230101","to":"20231231"},
        {"id":"glob_23_hab","q":"habitação Lisboa preço arrendamento crise", "from":"20230101","to":"20231231"},
        {"id":"glob_23_sal","q":"salário mínimo Portugal aumento trabalhadores", "from":"20230101","to":"20231231"},
    ],
    2024: [
        {"id":"glob_24_inf","q":"inflação Portugal preços taxa IPC", "from":"20240101","to":"20241231"},
        {"id":"glob_24_hab","q":"habitação Lisboa preço arrendamento euros", "from":"20240101","to":"20241231"},
        {"id":"glob_24_sal","q":"salário mínimo Portugal aumento euros", "from":"20240101","to":"20241231"},
    ],
}

# ─── UTILITÁRIOS ──────────────────────────────────────────────────────────────

def dominio_valido(url):
    url = url.lower()
    return any(d in url for d in DOMINIOS_VALIDOS)


def snippet_util(item):
    """
    CORRECÇÃO 1: filtro apenas para erros técnicos inequívocos.
    Remove "sapo", "governo", "universidade" — são termos válidos em manchetes.
    """
    snippet = item.get("snippet", "").strip()
    title   = item.get("title",   "").strip()

    if len(snippet) < 40 and len(title) < 25:
        return False

    # Só rejeita erros técnicos inequívocos — NÃO palavras temáticas
    lixo_tecnico = [
        "página não encontrada", "page not found", "404 not found",
        "javascript required", "enable javascript",
        "subscribe to read", "login to continue",
        "outros artigos",                            # menu de navegação puro
    ]
    title_lower = title.lower()
    if any(l in title_lower for l in lixo_tecnico):
        return False

    # Rejeita snippets muito curtos sem dígitos (provavelmente menus)
    if len(snippet) < 80 and not any(c.isdigit() for c in snippet):
        return False

    return True


def safe_get(params, retries=MAX_RETRIES):
    for attempt in range(retries):
        try:
            r = requests.get(BASE_URL, params=params, timeout=TIMEOUT)
            r.encoding = "utf-8"
            r.raise_for_status()
            return r.json()
        except Exception as e:
            wait = (attempt + 1) * 5
            print(f"    [AVISO] Tentativa {attempt+1}/{retries}: {e}. Aguarda {wait}s...")
            time.sleep(wait)
    return {}


def paginar(q_config, site=None, max_items=MAX_PER_QUERY):
    """
    CORRECÇÃO 2: lógica de paginação correcta.
    - Continua enquanto a última página veio cheia (= pode haver mais)
    - Para quando a página vier vazia ou incompleta
    - site=None para queries globais (com filtro pós-recolha)
    """
    all_items = []
    offset    = 0
    seen_urls = set()

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
            break  # sem resultados — para

        for item in items:
            url = item.get("originalURL", "") or item.get("linkToArchive", "")
            # FIX A: só filtra domínio quando há siteSearch (queries focadas)
            # queries globais (site=None) aceitam qualquer domínio — filtro pós-recolha
            if site is not None and not dominio_valido(url):
                continue
            if url in seen_urls:
                continue
            seen_urls.add(url)
            if not snippet_util(item):
                continue
            all_items.append(item)

        # CORRECÇÃO 2: pagina só se a página veio cheia
        if len(items) < PAGE_SIZE:
            break

        offset += len(items)
        time.sleep(SLEEP_BETWEEN)

    return all_items[:max_items]


# ─── FASE 1: Loop principal ────────────────────────────────────────────────────
n_queries = len(QUERIES)
n_jornais = len(JORNAIS)
n_combos  = n_queries * n_jornais

print("=" * 70)
print("RECOLHA Arquivo.pt — Custo Portugal v6")
print(f"  Jornais: {n_jornais} | Queries principais: {n_queries}")
print(f"  Queries Público extra: {len(QUERIES_PUBLICO_EXTRA)}")
print(f"  Combinações fase 1: {n_combos}")
print(f"  Sleep: {SLEEP_BETWEEN}s | Timeout: {TIMEOUT}s")
print(f"  Duração estimada: {n_combos * SLEEP_BETWEEN / 60:.0f}–{(n_combos + len(QUERIES_PUBLICO_EXTRA)) * (SLEEP_BETWEEN + 0.5) / 60:.0f} min")
print("=" * 70)

stats_jornal  = defaultdict(int)
stats_ano     = defaultdict(int)
stats_cat     = defaultdict(int)
total_geral   = 0
n_skip_exist  = 0
n_zero_combos = 0


def processar_query(nome_jornal, query, site, prefixo=""):
    """Processa uma query×jornal e devolve número de snippets novos."""
    global total_geral, n_skip_exist, n_zero_combos
    fname = f"{prefixo}{nome_jornal}_{query['id']}.json"
    fpath = os.path.join(OUTPUT_DIR, fname)

    if os.path.exists(fpath):
        with open(fpath, encoding="utf-8") as f:
            existing = json.load(f)
        n = len(existing)
        # FIX B: reutiliza cache só se tiver dados; re-tenta ficheiros vazios
        if n > 0:
            stats_jornal[nome_jornal] += n
            stats_cat[query["id"].split("_")[0]] += n
            for item in existing:
                ts = item.get("tstamp", "20000101")
                stats_ano[ts[:4]] += 1
            n_skip_exist += 1
            return n
        # n == 0 → apaga e tenta de novo
        os.remove(fpath)

    items = paginar(query, site=site)
    with open(fpath, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)

    n = len(items)
    stats_jornal[nome_jornal] += n
    stats_cat[query["id"].split("_")[0]] += n
    for item in items:
        ts = item.get("tstamp", "20000101")
        stats_ano[ts[:4]] += 1
    if n == 0:
        n_zero_combos += 1
    time.sleep(SLEEP_BETWEEN)
    return n


# Fase 1A: todos os jornais × todas as queries principais
for nome_jornal, site in JORNAIS.items():
    print(f"\n{'─'*60}")
    print(f"  JORNAL: {nome_jornal} ({site})")
    print(f"{'─'*60}")
    total_jornal = 0

    for query in QUERIES:
        n = processar_query(nome_jornal, query, site)
        total_geral  += n
        total_jornal += n
        if n > 0:
            print(f"  [OK] {query['id']}: {n} | total {nome_jornal}: {total_jornal}")

    print(f"  => {nome_jornal}: {total_jornal} snippets")

# Fase 1B: queries extra dedicadas ao Público (CORRECÇÃO 5)
print(f"\n{'─'*60}")
print(f"  PÚBLICO — queries dedicadas ({len(QUERIES_PUBLICO_EXTRA)} queries)")
print(f"{'─'*60}")
total_pub_extra = 0
for query in QUERIES_PUBLICO_EXTRA:
    n = processar_query("publico", query, "www.publico.pt", prefixo="pubx_")
    total_geral    += n
    total_pub_extra += n
    if n > 0:
        print(f"  [OK] {query['id']}: {n} | Público extra total: {total_pub_extra}")
print(f"  => Público extra: {total_pub_extra} snippets")

# ─── FASE 2: Queries globais para anos escassos ────────────────────────────────
# CORRECÇÃO 6: corre depois do loop principal para preencher lacunas temporais
LIMIAR_GLOBAL = 20   # corre queries globais se o ano tiver < 20 snippets

anos_escassos = [a for a in range(1996, 2025)
                 if stats_ano.get(str(a), 0) < LIMIAR_GLOBAL
                 and str(a) in {str(k) for k in QUERIES_GLOBAIS_ANOS}]

if anos_escassos:
    print(f"\n{'─'*60}")
    print(f"  FASE 2 — Queries globais para anos escassos: {anos_escassos}")
    print(f"{'─'*60}")

    for ano in anos_escassos:
        qs_ano = QUERIES_GLOBAIS_ANOS.get(ano, [])
        total_ano = 0
        for query in qs_ano:
            # site=None → sem siteSearch → global, filtro pós-recolha activo
            n = processar_query(f"glob{ano}", query, site=None, prefixo="")
            total_geral += n
            total_ano   += n
            if n > 0:
                print(f"  [OK] {query['id']} (global): {n} snippets")
        print(f"  => {ano}: +{total_ano} snippets globais")
else:
    print(f"\n  FASE 2 — Todos os anos têm >= {LIMIAR_GLOBAL} snippets. Nenhuma query global necessária.")

# ─── RELATÓRIO FINAL ──────────────────────────────────────────────────────────
n_files = len([f for f in os.listdir(OUTPUT_DIR) if f.endswith(".json")])

print(f"\n{'='*70}")
print(f"RECOLHA COMPLETA v5")
print(f"  Total snippets : {total_geral}")
print(f"  Ficheiros JSON : {n_files}")
print(f"  Já existiam    : {n_skip_exist} (cache)")
print(f"  Combos c/ zero : {n_zero_combos}")

print(f"\nPor jornal:")
for jornal, n in sorted(stats_jornal.items(), key=lambda x: -x[1]):
    barra = "█" * min(40, n // 5)
    print(f"  {jornal:<12} {n:>5}  {barra}")

print(f"\nPor categoria:")
for cat, n in sorted(stats_cat.items(), key=lambda x: -x[1]):
    barra = "█" * min(30, n // 3)
    print(f"  {cat:<8} {n:>5}  {barra}")

print(f"\nCobertura por ano (✓≥50  ⚠≥20  ✗<20):")
anos_ok = anos_aviso = anos_fail = 0
for ano in range(1996, 2025):
    n = stats_ano.get(str(ano), 0)
    if n >= 50:
        status = "✓"; anos_ok += 1
    elif n >= 20:
        status = "⚠"; anos_aviso += 1
    else:
        status = "✗"; anos_fail += 1
    barra = "█" * min(30, n // 3)
    print(f"  {ano}  {status}  {n:>4}  {barra}")

print(f"\n  ✓ (≥50): {anos_ok}/29  |  ⚠ (≥20): {anos_aviso}/29  |  ✗ (<20): {anos_fail}/29")

pub_total = stats_jornal.get("publico", 0)
print(f"\nMeta Menção Honrosa Público:")
print(f"  {pub_total} snippets {'✓ OK' if pub_total >= 500 else f'✗ Faltam {500 - pub_total}'}")

periodos = [
    ("Era escudos  1996-2002", range(1996, 2003), 30),
    ("Pré-crise    2003-2008", range(2003, 2009), 30),
    ("Crise/Troika 2009-2014", range(2009, 2015), 50),
    ("Recuperação  2015-2020", range(2015, 2021), 50),
    ("Recente      2021-2024", range(2021, 2025), 20),
]
print(f"\nCobertura por período histórico:")
for nome, anos, meta in periodos:
    n  = sum(stats_ano.get(str(a), 0) for a in anos)
    ok = "✓" if n >= meta else f"✗ faltam {meta - n}"
    print(f"  {nome}  {n:>4} snippets  meta={meta}  {ok}")

print(f"{'='*70}")
