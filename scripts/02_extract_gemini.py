# -*- coding: utf-8 -*-
# scripts/02_extract_gemini.py
# Extracção de dados económicos de snippets com Gemini 2.5 Flash
#
# USO:
#   python scripts/02_extract_gemini.py            → extracção completa
#   python scripts/02_extract_gemini.py --test     → apenas 20 snippets (teste)
#   python scripts/02_extract_gemini.py --resume   → retoma do checkpoint
#
# Rate limit: ~500 req/dia (Free Tier) · 10 RPM → sleep(6) obrigatório
# O checkpoint é guardado a cada 50 items — pode interromper a qualquer momento

from google import genai
from google.genai import types
import json, time, glob, os, re, sys
from pathlib import Path
from collections import Counter

# ─── Configuração ─────────────────────────────────────────────────────────────

# Carrega chave do .env se existir
ENV_FILE = Path(__file__).parent.parent / ".env"
if ENV_FILE.exists():
    for line in ENV_FILE.read_text(encoding="utf-8").splitlines():
        if line.startswith("GEMINI_API_KEY="):
            os.environ["GEMINI_API_KEY"] = line.split("=", 1)[1].strip()
            break

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
if not GEMINI_KEY:
    print("[ERRO] GEMINI_API_KEY não encontrada. Define no .env ou como variável de ambiente.")
    sys.exit(1)

client = genai.Client(api_key=GEMINI_KEY)

SLEEP      = 6      # 10 RPM → 1 req/6s — NÃO REDUZIR
MIN_REL    = 3      # relevância mínima (1-5) para incluir no dataset
CHECKPOINT = "data/checkpoint.json"
OUTPUT     = "data/extracted_data.json"
RAW_DIR    = "data/raw"

# Modo teste: apenas 20 snippets
TEST_MODE  = "--test" in sys.argv
TEST_LIMIT = 20

# ─── Carrega checkpoint ───────────────────────────────────────────────────────
processed, extracted = set(), []
if os.path.exists(CHECKPOINT):
    with open(CHECKPOINT, encoding="utf-8") as f:
        ck = json.load(f)
    processed = set(ck.get("processed", []))
    extracted = ck.get("results", [])
    print(f"[Checkpoint] {len(processed)} processados, {len(extracted)} extraídos")

if TEST_MODE:
    print(f"[MODO TESTE] Processa apenas {TEST_LIMIT} snippets novos.")


# ─── Utilitários ─────────────────────────────────────────────────────────────
def source_name(url):
    """Mapeia URL para nome do jornal."""
    for domain, name in [
        ("publico.pt",   "Público"),
        ("dn.pt",        "Diário de Notícias"),
        ("expresso.pt",  "Expresso"),
        ("jn.pt",        "Jornal de Notícias"),
        ("tsf.pt",       "TSF"),
        ("ionline.pt",   "i Online"),
        ("cmjornal.pt",  "Correio da Manhã"),
    ]:
        if domain in url:
            return name
    # Fallback: extrai domínio
    parts = url.replace("https://", "").replace("http://", "").split("/")
    return parts[0] if parts else url


def save_checkpoint():
    os.makedirs("data", exist_ok=True)
    with open(CHECKPOINT, "w", encoding="utf-8") as f:
        json.dump({"processed": list(processed), "results": extracted}, f)


# ─── Prompt ───────────────────────────────────────────────────────────────────
PROMPT_TEMPLATE = '''\
Analisa este snippet de um artigo jornalístico português arquivado.

Título: "{title}"
Snippet: "{snippet}"
Data: {year}-{month} | Fonte: {source}

REGRAS:
- Se preços em escudos/contos (artigos antes de 2002): converte para euros (1€ = 200,482 escudos)
- Habitação: extrai €/m² ou €/mês para renda
- Combustíveis: extrai €/L (gasolina ou gasóleo)
- Salário: extrai €/mês (salário mínimo ou médio)
- Inflação/IPC: extrai a percentagem mencionada
- Desemprego: extrai a taxa percentual
- Relevância 5 = valor numérico claro e verificável; 1 = sem dados económicos concretos

Responde APENAS com JSON válido (sem markdown, sem texto fora do JSON):
{{"ano":<int>,"mes":<int|null>,"categoria":<"habitacao"|"combustivel"|"salario"|"inflacao"|"desemprego"|"custo_vida"|"contexto">,"valor_numerico":<float|null>,"unidade":<"€/m2"|"€/L"|"€/mes"|"%"|"€"|null>,"cidade":<"Lisboa"|"Porto"|"Portugal"|null>,"moeda_original":<"euros"|"escudos"|null>,"valor_original":<float|null>,"contexto_curto":<str max 20 palavras>,"sentimento":<"subida"|"descida"|"estavel"|"crise"|"recuperacao">,"relevancia":<1-5>,"titulo_noticia":"{title_safe}","fonte_nome":"{source}","link_arquivo":"{link_arquivo}","link_screenshot":"{link_screenshot}"}}
'''

# ─── Loop principal ───────────────────────────────────────────────────────────
n_proc, n_ok, n_err, n_skip_rel = 0, 0, 0, 0

# Ordena ficheiros: globais primeiro (mais dados), depois boost e pub
all_files = sorted(glob.glob(f"{RAW_DIR}/*.json"))
# Prioriza ficheiros globais e com dados recentes
all_files.sort(key=lambda f: (
    0 if "global_" in f else 1,
    f
))

print(f"\nFicheiros a processar: {len(all_files)}")
print(f"Snippets já processados (checkpoint): {len(processed)}")
print()

for fpath in all_files:
    try:
        with open(fpath, encoding="utf-8") as f:
            items = json.load(f)
    except Exception as e:
        print(f"  [ERRO] Não conseguiu ler {fpath}: {e}")
        continue

    if not items:
        continue

    fname = os.path.basename(fpath)

    for item in items:
        uid = item.get("linkToArchive") or item.get("originalURL", "")
        if not uid or uid in processed:
            continue

        # Modo teste: para depois de N snippets novos
        if TEST_MODE and n_proc >= TEST_LIMIT:
            print(f"\n[TESTE] Limite de {TEST_LIMIT} atingido. Parando.")
            break

        ts    = item.get("tstamp", "20000101000000")
        year  = ts[:4]
        month = ts[4:6] if len(ts) >= 6 else "01"
        src   = source_name(item.get("originalURL", ""))

        title   = item.get("title", "")[:200]
        snippet = item.get("snippet", "")[:600]
        # Versão safe do título (sem aspas que quebram o JSON do prompt)
        title_safe = title.replace('"', "'").replace('\\', '')

        prompt = PROMPT_TEMPLATE.format(
            title       = title.replace('"', "'"),
            snippet     = snippet.replace('"', "'"),
            year        = year,
            month       = month,
            source      = src,
            title_safe  = title_safe,
            link_arquivo    = item.get("linkToArchive", ""),
            link_screenshot = item.get("linkToScreenshot", ""),
        )

        try:
            response = client.models.generate_content(
                model="gemini-3.1-flash-lite-preview",
                contents=prompt,
            )
            text = re.sub(r"```(?:json)?|```", "", response.text).strip()
            # Remove possível lixo antes/depois do JSON
            m = re.search(r'\{.*\}', text, re.DOTALL)
            if not m:
                raise ValueError(f"JSON não encontrado na resposta: {text[:200]}")
            result = json.loads(m.group())

            # Garante que o ano e tstamp são coerentes
            result["ano"]            = int(year)
            result["titulo_noticia"] = title
            result["fonte_nome"]     = src
            result["link_arquivo"]   = item.get("linkToArchive", "")
            result["link_screenshot"]= item.get("linkToScreenshot", "")

            if result.get("relevancia", 0) >= MIN_REL:
                extracted.append(result)
                n_ok += 1
            else:
                n_skip_rel += 1

            processed.add(uid)
            n_proc += 1

        except Exception as e:
            err_str = str(e)
            if "429" in err_str or "quota" in err_str.lower():
                print(f"\n[LIMITE 429] Quota atingida. Checkpoint guardado. Retoma amanhã.")
                save_checkpoint()
                print(f"  Processados: {n_proc} | Extraídos: {n_ok} | Erros: {n_err}")
                sys.exit(0)
            print(f"  [ERRO] {fname}: {err_str[:100]}")
            n_err += 1
            processed.add(uid)

        # Checkpoint a cada 50
        if n_proc > 0 and n_proc % 50 == 0:
            save_checkpoint()
            print(f"  [checkpoint] {n_proc} processados | {n_ok} extraídos | {n_err} erros | {n_skip_rel} baixa relevância")

        time.sleep(SLEEP)

    else:
        continue  # ficheiro esgotado sem break — continua para o próximo
    break          # modo teste: break interno propagado

# ─── Guarda resultado final ───────────────────────────────────────────────────
save_checkpoint()
os.makedirs("data", exist_ok=True)
with open(OUTPUT, "w", encoding="utf-8") as f:
    json.dump(extracted, f, ensure_ascii=False, indent=2)

print(f"\n{'='*55}")
print(f"EXTRACÇÃO {'(TESTE) ' if TEST_MODE else ''}COMPLETA")
print(f"  Processados : {n_proc}")
print(f"  Extraídos   : {n_ok}  (relevância >= {MIN_REL})")
print(f"  Baixa rel.  : {n_skip_rel}")
print(f"  Erros       : {n_err}")
print(f"  Ficheiro    : {OUTPUT}")
print(f"{'='*55}")

if extracted:
    cats = Counter(i.get("categoria", "?") for i in extracted)
    print("\nDistribuição por categoria:")
    for cat, cnt in sorted(cats.items(), key=lambda x: -x[1]):
        print(f"  {cat:<20} {cnt:>4} registos")

    # Validação rápida: mostra 3 exemplos com valor numérico
    print("\nExemplos extraídos (com valor numérico):")
    exemplos = [i for i in extracted if i.get("valor_numerico")][:3]
    for ex in exemplos:
        print(f"  [{ex.get('ano')}] {ex.get('categoria')} | "
              f"{ex.get('valor_numerico')} {ex.get('unidade','')} | "
              f"rel={ex.get('relevancia')} | {ex.get('titulo_noticia','')[:60]}")
