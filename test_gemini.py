import requests
import json

key = "AIzaSyB49dFGXcACkYzE94oimfFHYbsXBUYdCtg"
url = f"https://generativelanguage.googleapis.com/v1beta/models/gemini-2.5-flash:generateContent?key={key}"
data = {
    "contents": [{"parts": [{"text": "Olá, fala em português? Responde com 1 frase curta."}]}]
}
response = requests.post(url, json=data)
print("Resposta Gemini:")
print(response.json()['candidates'][0]['content']['parts'][0]['text'])
