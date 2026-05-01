# -*- coding: utf-8 -*-
# scripts/02_extract_gemini_v3.py — VERSÃO 3 (Estatístico Rigoroso)
#
# CORRECÇÕES v3:
#   1. Prompt totalmente reescrito para proibir Micro-Dados (anedóticos).
#   2. Obriga à extração de dados Macroeconómicos Nacionais (INE, Governo).
#   3. Evita "alucinações" em que o modelo usa o salário de um indivíduo
#      ou a renda de um bairro de luxo específico como indicador do país.
#
# USO:
#   python scripts/02_extract_gemini_v3.py           -- completo
#   python scripts/02_extract_gemini_v3.py --test    -- 20 snippets

from groq import Groq
import json, time, glob, os, re, sys
from pathlib import Path
from collections import Counter, defaultdict
from datetime import datetime

# ─── LOGGING ──────────────────────────────────────────────────────────────────
if hasattr(sys.stdout, 'reconfigure'):
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except Exception:
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
log_filename = os.path.join(LOG_DIR, f"{os.path.basename(__file__)}_{datetime.now().strftime('%Y%m%d_%H%M%S')}.log")
sys.stdout = Logger(log_filename)

# --- Chave API Groq -----------------------------------
GROQ_API_KEY = "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"
client = Groq(api_key=GROQ_API_KEY)

# Lista de modelos por ordem de prioridade (esgotamento de quota)
MODELS_TO_TRY = [
    "llama-3.1-8b-instant",
    "llama-4-scout-17b",
    "qwen/qwen3-32b",
    "openai/gpt-oss-20b",
    "openai/gpt-oss-120b"
]
current_model_idx = 0
ACTIVE_MODEL = MODELS_TO_TRY[current_model_idx]
print(f"[Modelo] Iniciando com: {ACTIVE_MODEL}")

# --- Configuracao -------------------------------------------------------------
SLEEP      = 6.0        # ~10 RPM (Limita o uso para respeitar as 6,000 TPM do modelo 8b)
MIN_REL    = 4          # Na v3/v4 passamos para 4: só queremos dados macro claros
CHECKPOINT = "data/checkpoint_v4.json"   # continua a usar o checkpoint anterior!
OUTPUT     = "data/extracted_data_groq.json"
RAW_DIR    = "data/raw"
TEST_MODE  = "--test" in sys.argv
TEST_LIMIT = 20
# Pre-filtro de qualidade: snippets globais (sem siteSearch) podem ser curtos
MIN_SNIPPET_LEN = 80   # rejeita antes da API — poupa quota

# CORRECCAO 4: Limites plausíveis por categoria
LIMITES = {
    "habitacao":   (100,  8000),
    "combustivel": (0.40, 3.50),
    "salario":     (150,  3000),
    "inflacao":    (-5,   30),
    "desemprego":  (1,    25),
}

def valor_plausivel(categoria, valor):
    if valor is None:
        return True
    lim = LIMITES.get(categoria)
    if not lim:
        return True
    return lim[0] <= valor <= lim[1]

# CORRECCAO 2: Padroes de URLs que NAO sao artigos reais
URL_LIXO = [
    r"https?://[^/]+/?$",
    r"https?://[^/]+/\?",
    r"/tag/",
    r"/tags/",
    r"/categoria/",
    r"/section/",
    r"\?referrer=",
    r"/inicio/?$",
    r"/home/?$",
    r"/index\.html?$",
    r"\.pt/?$",
    r"/author/",
    r"/search\?",
]

def e_artigo_real(url):
    if not url or len(url) < 35:
        return False
    for pattern in URL_LIXO:
        if re.search(pattern, url, re.IGNORECASE):
            return False
    path = url.split("//")[-1].split("/", 1)[-1] if "//" in url else ""
    return len(path) > 15

# --- Checkpoint ---------------------------------------------------------------
processed, extracted = set(), []
if os.path.exists(CHECKPOINT):
    with open(CHECKPOINT, encoding="utf-8") as f:
        ck = json.load(f)
    processed = set(ck.get("processed", []))
    extracted = ck.get("results", [])
    print(f"[Checkpoint] {len(processed)} processados, {len(extracted)} extraidos")
else:
    print("[Checkpoint] Novo")

if TEST_MODE:
    print(f"[MODO TESTE] Max {TEST_LIMIT} snippets\n")

def nome_jornal(url):
    for dominio, nome in [
        ("publico.pt",    "Publico"),
        ("dn.pt",         "Diario de Noticias"),
        ("expresso.pt",   "Expresso"),
        ("jn.pt",         "Jornal de Noticias"),
        ("tsf.pt",        "TSF"),
        ("cmjornal.pt",   "Correio da Manha"),
        ("observador.pt", "Observador"),
        ("rtp.pt",        "RTP"),
    ]:
        if dominio in url:
            return nome
    partes = url.replace("https://","").replace("http://","").split("/")
    return partes[0] if partes else "outro"

def guardar_checkpoint():
    os.makedirs("data", exist_ok=True)
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump({"processed": list(processed), "results": extracted},
                  f, ensure_ascii=False)

# --- PROMPT V3: O ESTATÍSTICO RIGOROSO -----------------------------------------
PROMPT = '''\
És um ESTATÍSTICO RIGOROSO especializado em extrair DADOS MACROECONÓMICOS do arquivo web português.
A tua missão é extrair dados fiáveis e representativos do país, REJEITANDO COMPLETAMENTE casos particulares e anedóticos.

=== ARTIGO ===
Snippet (texto do artigo): "{snippet}"
Título HTML (pode ser lixo): "{title}"
Data: {year}-{month} | Jornal: {source}

=== REGRAS DE OURO (IGNORAR RESULTA EM FALHA) ===

REGRA 1 - EXIGÊNCIA MACROECONÓMICA ABSOLUTA:
  - SÓ ACEITAS: "Salário Mínimo Nacional", "Salário Médio", "Inflação (INE)", "Taxa de Desemprego (INE)", "Preço médio de Combustível (bomba)", "Preço médio/mediano de Habitação/Renda".
  - REJEITAS (relevancia=1): Salários de pessoas específicas (ex: bispos, políticos, gestores, futebolistas), preços de casas específicas ou bairros de luxo (ex: Expo98), estimativas vagas de comentadores, valores de outros países.

REGRA 2 - VALORES PLAUSÍVEIS (PORTUGAL, ANO {year}):
  - Habitacao (euros_m2): Média nacional ou Lisboa/Porto. Tem de refletir o mercado. Rendas de casas inteiras não são euros/m2!
  - Combustível (euros_L): Gasolina/Gasóleo comercial (ex: 1.50). Não é barril de Brent!
  - Salário (euros_mes): Mínimo/Médio nacional. Salários milionários são para rejeitar!
  - Escudos (para valores pré-2002): 1 euro = 200.482 escudos | 1 conto = 4.988 euros.

REGRA 3 - CONSTRUÇÃO DA NOTÍCIA:
  - `titulo_noticia`: Manchete factual e sintética do evento real (ex: "Salário mínimo sobe para 500 euros"). NUNCA uses "Página não encontrada" ou nomes de secções ("Economia", "Opinião").
  - `contexto_curto`: Explica EXATAMENTE a que se refere o valor de forma macro (ex: "Salário Mínimo Nacional definido pelo Governo").

REGRA 4 - RELEVÂNCIA (1-5) - SÊ MUITO RESTRITO:
  - 5: Dado macroeconómico oficial e inequívoco (ex: INE reporta desemprego, Governo anuncia Salário Mínimo).
  - 4: Dado macroeconómico genérico claro.
  - 1 a 3: REJEITA tudo o que for micro-dados, casos individuais, desporto, celebridades, ou textos sem valor numérico associado.

=== OUTPUT ===
Responde APENAS com JSON válido (sem markdown, sem backticks, sem comentários adicionais):
{{"ano":<int>,"mes":<int|null>,"categoria":<"habitacao"|"combustivel"|"salario"|"inflacao"|"desemprego"|"custo_vida"|"contexto">,"valor_numerico":<float|null>,"unidade":<"euros_m2"|"euros_L"|"euros_mes"|"percentagem"|null>,"cidade":<"Lisboa"|"Porto"|"Portugal"|null>,"moeda_original":<"euros"|"escudos"|null>,"valor_original_escudos":<float|null>,"contexto_curto":"<max 20 palavras explicativas>","sentimento":<"subida"|"descida"|"estavel"|"crise"|"recuperacao">,"relevancia":<1|2|3|4|5>,"titulo_noticia":"<manchete factual>","fonte_nome":"{source}","link_arquivo":"{link_arquivo}","link_screenshot":"{link_screenshot}"}}
'''

# --- CORRECCAO 8: Ordem de processamento - tier1 primeiro --------------------
all_files = sorted(glob.glob(f"{RAW_DIR}/*.json"))

def prioridade(fpath):
    nome = os.path.basename(fpath)
    if nome.startswith("publico_"):    return 0
    if nome.startswith("dn_"):         return 1
    if nome.startswith("expresso_"):   return 2
    if nome.startswith("jn_"):         return 3
    if nome.startswith("tsf_"):        return 4
    return 5

all_files.sort(key=prioridade)
print(f"\n[Ficheiros] {len(all_files)} a processar")
print(f"[Snippets]  {len(processed)} ja processados\n")

# --- Loop principal -----------------------------------------------------------
n_proc = n_ok = n_err = 0
n_skip_rel = n_skip_outlier = n_skip_home = 0
stats_ano = defaultdict(int)
keys_failed_in_a_row = 0

for fpath in all_files:
    try:
        with open(fpath, encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        print(f"  [ERRO LEITURA] {fpath}: {e}")
        continue

    if not items:
        continue

    for item in items:
        uid = item.get("linkToArchive") or item.get("originalURL", "")
        if not uid or uid in processed:
            continue

        if TEST_MODE and n_proc >= TEST_LIMIT:
            print(f"\n[TESTE] Limite atingido.")
            guardar_checkpoint()
            sys.exit(0)

        link_arquivo = item.get("linkToArchive", "")

        # CORRECCAO 2: rejeita homepages antes da API
        if not e_artigo_real(link_arquivo):
            processed.add(uid)
            n_skip_home += 1
            n_proc += 1
            continue

        # Pre-filtro: snippet demasiado curto (tipico de resultados globais de baixa qualidade)
        snippet_text = item.get("snippet", "")
        if len(snippet_text.strip()) < MIN_SNIPPET_LEN:
            processed.add(uid)
            n_skip_home += 1
            n_proc += 1
            continue

        ts    = item.get("tstamp", "20000101000000")
        year  = int(ts[:4])
        month = int(ts[4:6]) if len(ts) >= 6 else 1
        src   = nome_jornal(item.get("originalURL", ""))

        prompt = PROMPT.format(
            snippet        = item.get("snippet","")[:600].replace('"',"'").replace("\\"," "),
            title          = item.get("title","")[:200].replace('"',"'").replace("\\"," "),
            year           = year,
            month          = f"{month:02d}",
            ym1            = year - 1,
            yp1            = year + 1,
            source         = src,
            link_arquivo   = link_arquivo,
            link_screenshot= item.get("linkToScreenshot",""),
        )

        for attempt in range(3):
            try:
                if attempt == 0:
                    print(f"\n  [{n_proc}] -> {link_arquivo[:60]}...")
                
                ACTIVE_MODEL = MODELS_TO_TRY[current_model_idx]
                chat = client.chat.completions.create(
                    model=ACTIVE_MODEL,
                    messages=[{"role": "user", "content": prompt}],
                    temperature=0,
                )
                text = re.sub(r"```(?:json)?|```", "", chat.choices[0].message.content).strip()
                m    = re.search(r'\{.*\}', text, re.DOTALL)
                if not m:
                    raise ValueError(f"JSON nao encontrado: {text[:150]}")

                json_str = m.group()
                
                try:
                    result = json.loads(json_str, strict=False)
                except Exception as e:
                    # Llama-8b costuma gerar \u mal formatados e barras inválidas
                    json_str = json_str.replace("\\", "\\\\")
                    try:
                        result = json.loads(json_str, strict=False)
                    except Exception as e2:
                        print(f"  [RAW_TEXT] {json_str[:200]}")
                        raise e2

                # CORRECCAO 5: validacao temporal ±1 ano
                ano_ext = result.get("ano")
                if ano_ext and abs(int(ano_ext) - year) > 1:
                    processed.add(uid); n_proc += 1; break

                result["ano"]             = year
                result["fonte_nome"]      = src
                result["link_arquivo"]    = link_arquivo
                result["link_screenshot"] = item.get("linkToScreenshot","")

                # CORRECCAO 4: outliers
                cat   = result.get("categoria","")
                valor = result.get("valor_numerico")
                if not valor_plausivel(cat, valor):
                    processed.add(uid); n_skip_outlier += 1; n_proc += 1; break

                if result.get("relevancia", 0) >= MIN_REL:
                    extracted.append(result)
                    n_ok += 1
                    stats_ano[str(year)] += 1
                else:
                    n_skip_rel += 1

                processed.add(uid); n_proc += 1; break

            except Exception as e:
                err = str(e)
                err_lower = err.lower()
                
                # Erros Críticos de API (Falha Fatal)
                if "401" in err or "403" in err or "unauthorized" in err_lower or "forbidden" in err_lower:
                    print(f"\n  [ERRO FATAL] Credenciais API inválidas (401/403).")
                    guardar_checkpoint()
                    sys.exit(1)

                # Erro no Snippet (ignorar snippet - ex: muito grande)
                if "413" in err or "too large" in err_lower:
                    print(f"\n  [413] Snippet demasiado grande, a ignorar...")
                    processed.add(uid); n_proc += 1; break

                # Erros que forçam Rotação de Modelo (Esgotamento / Falta do modelo / Limite de requests)
                if any(x in err_lower for x in ["429", "rate limit", "498", "capacity exceeded", "404", "not found", "does not exist", "400"]):
                    print(f"\n  [QUOTA/MODELO] Falha no modelo {MODELS_TO_TRY[current_model_idx]} ({err[:30]}). Mudando para o próximo...")
                    current_model_idx += 1
                    
                    if current_model_idx >= len(MODELS_TO_TRY):
                        # Todos os modelos esgotados. Calcular tempo até à meia-noite PT (08:00 UTC)
                        from datetime import timedelta
                        agora = datetime.utcnow()
                        prox_reset = agora.replace(hour=8, minute=0, second=0, microsecond=0)
                        if agora >= prox_reset:
                            prox_reset += timedelta(days=1)
                        segundos_espera = (prox_reset - agora).total_seconds()
                        
                        horas = int(segundos_espera // 3600)
                        minutos = int((segundos_espera % 3600) // 60)
                        
                        print(f"\n  [ALERTA] Todos os modelos esgotados! Quota diária totalmente consumida.")
                        print(f"  [SLEEP] A aguardar até ao reset da meia-noite PT (faltam {horas}h {minutos}m)...")
                        guardar_checkpoint()
                        time.sleep(segundos_espera + 60) # Adiciona 1 minuto extra de margem
                        current_model_idx = 0 # Reinicia a lista após o reset
                    
                    continue # Tenta de novo com o próximo modelo
                
                # Erros de Servidor (500, 502, 503) ou Rede - Aguardar e Retentar
                if "500" in err or "502" in err or "503" in err or "connection" in err_lower or "disconnected" in err_lower:
                    print(f"\n  [REDE/SERVIDOR] Erro temporario. Aguardando 30s...")
                    time.sleep(30)
                    continue
                
                # Erros de Alucinação / Parsing (422) ou genéricos
                print(f"  [ERRO] {err[:80]}")
                n_err += 1
                if attempt == 2:
                    processed.add(uid); n_proc += 1; break
            
            # Se chegou aqui, o pedido teve sucesso
            keys_failed_in_a_row = 0

        if n_proc > 0 and n_proc % 50 == 0:
            guardar_checkpoint()
            taxa = n_ok / n_proc * 100 if n_proc else 0
            print(f"  [ckpt {n_proc}] ok={n_ok}({taxa:.0f}%) err={n_err} "
                  f"rel={n_skip_rel} out={n_skip_outlier} home={n_skip_home}")

        time.sleep(SLEEP)

# --- Resultado ----------------------------------------------------------------
guardar_checkpoint()
os.makedirs("data", exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(extracted, f, ensure_ascii=False, indent=2)

print(f"\n{'='*55}")
print(f"EXTRACCAO {'(TESTE) ' if TEST_MODE else ''}COMPLETA")
print(f"  Processados   : {n_proc}")
print(f"  Extraidos     : {n_ok}  (relevancia >= {MIN_REL})")
print(f"  Baixa rel.    : {n_skip_rel}")
print(f"  Outliers      : {n_skip_outlier}")
print(f"  Homepages skip: {n_skip_home}")
print(f"  Erros         : {n_err}")
print(f"  Output        : {OUTPUT}")

if extracted:
    cats = Counter(i.get("categoria","?") for i in extracted)
    print(f"\nPor categoria:")
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {cat:<20} {cnt:>4}")
    print(f"\nPor ano (dados extraidos):")
    for ano in sorted(stats_ano.keys()):
        n   = stats_ano[ano]
        bar = "x" * min(20, n)
        print(f"  {ano}  {n:>3}  {bar}")
    anos_com = sorted(int(a) for a in stats_ano.keys())
    if anos_com:
        print(f"\n  Cobertura: {min(anos_com)}-{max(anos_com)} ({len(anos_com)} anos)")
print(f"{'='*55}")
