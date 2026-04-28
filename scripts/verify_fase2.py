import json
with open('data/final_for_frontend.json', encoding='utf-8') as f:
    data = json.load(f)
for y in ['2000', '2008', '2020']:
    print(f'Ano: {y} | IDE: {data.get(y, {}).get("ide")}')
    for cat in ['habitacao', 'salario', 'combustivel', 'inflacao']:
        info = data.get(y, {}).get(cat, {})
        val = info.get('valor_mediana')
        tit = info.get('noticia_destaque', {}).get('titulo', '')
        link = info.get('noticia_destaque', {}).get('link_arquivo')
        print(f'  {cat:12s}: {str(val):6s} | Titulo: {tit[:40]:40s} | Link: {bool(link)}')
    print()
