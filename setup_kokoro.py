import os
import sys
import urllib.request
from pathlib import Path

BASE_DIR = Path(__file__).parent
BIN_DIR = BASE_DIR / "bin"
KOKORO_DIR = BIN_DIR / "kokoro"

MODEL_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/kokoro-v1.0.onnx"
VOICES_URL = "https://github.com/thewh1teagle/kokoro-onnx/releases/download/model-files-v1.0/voices-v1.0.bin"

MODEL_PATH = KOKORO_DIR / "kokoro-v1.0.onnx"
VOICES_PATH = KOKORO_DIR / "voices-v1.0.bin"

def download_file(url: str, dest: Path):
    print(f"Downloading {url} to {dest}...")
    headers = {"User-Agent": "Mozilla/5.0"}
    req = urllib.request.Request(url, headers=headers)
    
    with urllib.request.urlopen(req) as response, open(dest, "wb") as out_file:
        length = response.getheader("content-length")
        if length:
            total_size = int(length)
            downloaded = 0
            block_size = 1024 * 64
            while True:
                block = response.read(block_size)
                if not block:
                    break
                out_file.write(block)
                downloaded += len(block)
                percent = int(downloaded * 100 / total_size)
                if percent % 10 == 0:
                    sys.stdout.write(f"\rProgress: {percent}% ({downloaded // (1024*1024)}MB / {total_size // (1024*1024)}MB)")
                    sys.stdout.flush()
            print()
        else:
            out_file.write(response.read())

def setup_kokoro():
    KOKORO_DIR.mkdir(parents=True, exist_ok=True)
    
    # 1. Download Model
    if not MODEL_PATH.exists() or MODEL_PATH.stat().st_size < 1000:
        download_file(MODEL_URL, MODEL_PATH)
    else:
        print("Kokoro ONNX model already exists.")
        
    # 2. Download Voices
    if not VOICES_PATH.exists() or VOICES_PATH.stat().st_size < 1000:
        download_file(VOICES_URL, VOICES_PATH)
    else:
        print("Kokoro voices binary already exists.")
        
    # 3. Test Kokoro ONNX Synthesis
    print("\nRunning test of Kokoro ONNX model...")
    try:
        from kokoro_onnx import Kokoro
        kokoro = Kokoro(str(MODEL_PATH), str(VOICES_PATH))
        samples, sample_rate = kokoro.create(
            "Hello. Kokoro high fidelity voice synthesis is active.",
            voice="af_heart",
            speed=1.0,
            lang="en-us"
        )
        if len(samples) > 0:
            print(f"[Success] Kokoro synthesized {len(samples)} samples at {sample_rate}Hz successfully!")
        else:
            print("[Error] Kokoro synthesis returned empty audio samples.")
            sys.exit(1)
    except Exception as exc:
        print(f"[Error] Kokoro initialization/synthesis test failed: {exc}")
        sys.exit(1)

if __name__ == "__main__":
    setup_kokoro()
