# download_vosk_model.py
"""Download Vosk Russian speech recognition model."""
import os, sys, zipfile, urllib.request
from pathlib import Path

MODEL_URL = "https://alphacephei.com/vosk/models/vosk-model-small-ru-0.22.zip"
MODELS_DIR = Path(__file__).parent / "models"
MODEL_NAME = "vosk-model-small-ru-0.22"
ZIP_PATH = MODELS_DIR / "vosk-model-ru.zip"
EXTRACT_DIR = MODELS_DIR / MODEL_NAME

def download_with_progress(url, dest):
    print(f"Downloading Vosk Russian model...")
    print(f"  URL: {url}")
    print(f"  Size: ~400 MB")

    def report(block_num, block_size, total_size):
        downloaded = block_num * block_size
        percent = min(100, downloaded * 100 / total_size) if total_size > 0 else 0
        mb = downloaded / (1024 * 1024)
        total_mb = total_size / (1024 * 1024) if total_size > 0 else 0
        sys.stdout.write(f"\r  {percent:.0f}% ({mb:.0f}/{total_mb:.0f} MB)")
        sys.stdout.flush()

    urllib.request.urlretrieve(url, dest, report)
    print("\n  Download complete")

def extract_model():
    print(f"Extracting to {EXTRACT_DIR}...")
    MODELS_DIR.mkdir(parents=True, exist_ok=True)
    with zipfile.ZipFile(ZIP_PATH, 'r') as zf:
        zf.extractall(MODELS_DIR)
    print("  Extract complete")
    ZIP_PATH.unlink()
    print("  Archive removed")

def verify():
    required = EXTRACT_DIR / "am" / "final.mdl"
    if required.exists():
        size_mb = sum(f.stat().st_size for f in EXTRACT_DIR.rglob("*") if f.is_file()) / (1024*1024)
        print(f"\nModel ready: {EXTRACT_DIR} ({size_mb:.0f} MB)")
        return True
    else:
        print(f"\nERROR: model not found in {EXTRACT_DIR}")
        return False

if __name__ == "__main__":
    print("=" * 50)
    print("Vosk Model Downloader for AURA OS")
    print("=" * 50)

    if EXTRACT_DIR.exists():
        print(f"[warn] Model already exists: {EXTRACT_DIR}")
        if verify():
            print("  Delete folder to re-download.")
            sys.exit(0)

    try:
        download_with_progress(MODEL_URL, ZIP_PATH)
        extract_model()
        verify()
    except Exception as e:
        print(f"\nERROR: {e}")
        print("\nManual download:")
        print(f"  1. Open: {MODEL_URL}")
        print(f"  2. Extract to: {EXTRACT_DIR}")
