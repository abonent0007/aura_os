# setup_ollama.py
"""Setup Ollama embedding model for AURA OS. Run: python setup_ollama.py"""
import subprocess, sys, urllib.request, json, os, time

OLLAMA_URL = "http://localhost:11434"
EMBED_MODEL = "nomic-embed-text"

def check_ollama():
    try:
        path = os.environ.get("PATH", "")
        for p in [r"C:\Users\*\AppData\Local\Programs\Ollama", r"C:\Program Files\Ollama",
                   os.path.expandvars(r"%LOCALAPPDATA%\Programs\Ollama")]:
            for d in [p.replace("*", os.environ.get("USERNAME", ""))]:
                if os.path.isdir(d):
                    path += ";" + d
        os.environ["PATH"] = path

        resp = urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5)
        data = json.loads(resp.read())
        models = [m["name"] for m in data.get("models", [])]
        print(f"Ollama running. Models: {models if models else 'none'}")
        return True, models
    except Exception:
        print("Ollama not running. Start it first:")
        print("  Windows: launch 'Ollama' from Start menu")
        print("  Or: ollama serve")
        return False, []

def pull_model(model_name):
    print(f"Pulling {model_name} (this may take a while)...")
    try:
        subprocess.run(["ollama", "pull", model_name], check=True)
        print(f"Model {model_name} pulled")
        return True
    except subprocess.CalledProcessError:
        print(f"Failed to pull {model_name}")
        return False
    except FileNotFoundError:
        print("ollama not found in PATH. Restart terminal after installation.")
        return False

def test_embedding(model_name):
    text = "Privet, menya zovut Alexey"
    print(f"Testing embedding: '{text}'")
    try:
        req = urllib.request.Request(
            f"{OLLAMA_URL}/api/embeddings",
            data=json.dumps({"model": model_name, "prompt": text}).encode(),
            headers={"Content-Type": "application/json"}
        )
        resp = json.loads(urllib.request.urlopen(req, timeout=30).read())
        emb = resp.get("embedding", [])
        print(f"Embedding OK: {len(emb)} dimensions")
        return True
    except Exception as e:
        print(f"Error: {e}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Ollama Setup for AURA OS")
    print("=" * 50)

    ok, models = check_ollama()
    if not ok:
        sys.exit(1)

    if EMBED_MODEL not in [m.split(":")[0] for m in models]:
        if not pull_model(EMBED_MODEL):
            sys.exit(1)

    test_embedding(EMBED_MODEL)

    print("\nTo enable embeddings in AURA OS:")
    print('  config.json: memory.embeddings.enabled = true')
    print(f'  Model: {EMBED_MODEL}')
