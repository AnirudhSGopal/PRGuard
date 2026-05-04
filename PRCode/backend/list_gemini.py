import urllib.request
import json
import os

TIMEOUT = 10
api_key = os.getenv("GCP_API_KEY")
if not api_key:
    raise RuntimeError("Missing required environment variable: GCP_API_KEY")

url = f"https://generativelanguage.googleapis.com/v1beta/models?key={api_key}"

try:
    with urllib.request.urlopen(url, timeout=TIMEOUT) as response:
        html = response.read()
        models = json.loads(html)["models"]
        for m in models:
            name = m.get("name")
            methods = m.get("supportedGenerationMethods", [])
            print(f"{name} - {methods}")
except Exception as e:
    print(f"Error: {e}")
