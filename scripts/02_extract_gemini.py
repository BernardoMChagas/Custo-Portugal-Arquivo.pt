# scripts/02_extract_gemini.py
# INSTRUÇÃO ANTIGRAVITY:
# 1. Define variável de ambiente GEMINI_API_KEY antes de correr.
# 2. Executa este script. Monitoriza progresso a cada 50 items.
# 3. Se erro 429, aumenta SLEEP para 8 e retoma do checkpoint automaticamente.
# 4. No fim, imprime estatísticas: total processado, total extraído, por categoria.

import google.generativeai as genai
import json, time, glob, os, re

GEMINI_KEY = os.environ.get("GEMINI_API_KEY", "")
genai.configure(api_key=GEMINI_KEY)
model = genai.GenerativeModel("gemini-2.5-flash")

SLEEP = 6          # 10 RPM → 1 req/6s
MIN_REL = 3        # relevância mínima para incluir
CHECKPOINT = "data/checkpoint.json"
OUTPUT = "data/extracted_data.json"

# Carregar checkpoint
processed, extracted = set(), []
if os.path.exists(CHECKPOINT):
    with open(CHECKPOINT) as f:
        ck = json.load(f)
        processed = set(ck.get("processed", []))
        extracted = ck.get("results", [])
    print(f"Checkpoint: {len(processed)} processados, {len(extracted)} extraídos")

def source_name(url):
    for domain, name in [
        ("publico.pt","Público"), ("dn.pt","Diário de Notícias"),
        ("expresso.pt","Expresso"), ("jn.pt","Jornal de Notícias"),
        ("tsf.pt","TSF"), ("ionline.pt","i Online"), ("cmjornal.pt","CM")
    ]:
        if domain in url:
            return name
    return url.split("/")[2] if "/" in url else url

PROMPT = '''Analisa este snippet de um artigo jornalístico português arquivado.

Título: "{title}"
Snippet: "{snippet}"
Data: {year}-{month} | Fonte: {source}

REGRAS:
- Se preços em escudos/contos (antes de 2002): converte para € (1€=200.482$)
- Habitação: extrai €/m² ou €/mês para renda
- Combustíveis: extrai €/L
- Salário: extrai €/mês
- Inflação: extrai % mencionada
- Relevância 5 = valor numérico claro verificável; 1 = sem dados económicos

Responde APENAS com JSON válido (sem markdown, sem texto adicional):
{{"ano":<int>,"mes":<int|null>,"categoria":<"habitacao"|"combustivel"|"salario"|"inflacao"|"desemprego"|"custo_vida"|"contexto">,"valor_numerico":<float|null>,"unidade":<"€/m2"|"€/L"|"€/mes"|"%"|"€"|null>,"cidade":<"Lisboa"|"Porto"|"Portugal"|null>,"moeda_original":<"euros"|"escudos"|null>,"valor_original":<float|null>,"contexto_curto":<str max 20 palavras>,"sentimento":<"subida"|"descida"|"estavel"|"crise"|"recuperacao">,"relevancia":<1-5>,"titulo_noticia":"{title}","fonte_nome":"{source}","link_arquivo":"{link_arquivo}","link_screenshot":"{link_screenshot}"}}'''

n_proc, n_ok, n_err = 0, 0, 0

for fpath in sorted(glob.glob("data/raw/*.json")):
    with open(fpath, encoding="utf-8") as f:
        items = json.load(f)

    for item in items:
        uid = item.get("linkToArchive") or item.get("originalURL", "")
        if uid in processed:
            continue

        ts = item.get("tstamp", "20000101")
        year, month = ts[:4], ts[4:6]
        src = source_name(item.get("originalURL",""))

        prompt = PROMPT.format(
            title=item.get("title","")[:200],
            snippet=item.get("snippet","")[:600],
            year=year, month=month, source=src,
            link_arquivo=item.get("linkToArchive",""),
            link_screenshot=item.get("linkToScreenshot","")
        )

        try:
            r = model.generate_content(prompt)
            text = re.sub(r"```json|```","", r.text).strip()
            result = json.loads(text)
            if result.get("relevancia", 0) >= MIN_REL:
                extracted.append(result)
                n_ok += 1
            processed.add(uid)
            n_proc += 1
        except Exception as e:
            n_err += 1
            processed.add(uid)

        if n_proc % 50 == 0:
            with open(CHECKPOINT,"w") as f:
                json.dump({"processed":list(processed),"results":extracted}, f)
            print(f"  → {n_proc} processados | {n_ok} extraídos | {n_err} erros")

        time.sleep(SLEEP)

with open(OUTPUT,"w",encoding="utf-8") as f:
    json.dump(extracted, f, ensure_ascii=False, indent=2)

print(f"\n═══ EXTRACÇÃO COMPLETA ═══")
print(f"  Processados: {n_proc} | Extraídos: {n_ok} | Erros: {n_err}")
print(f"  Ficheiro: {OUTPUT}")

# Distribuição por categoria
from collections import Counter
cats = Counter(i["categoria"] for i in extracted)
for cat, cnt in sorted(cats.items(), key=lambda x:-x[1]):
    print(f"  {cat}: {cnt} registos")
