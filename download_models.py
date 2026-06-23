"""Download MobileNet-SSD model files for Object Detection."""

import os
import requests
import sys

BASE_DIR = os.path.dirname(os.path.abspath(__file__))
MODELS_DIR = os.path.join(BASE_DIR, "models")
PROTOTXT_URL = "https://raw.githubusercontent.com/chuanqi305/MobileNet-SSD/master/deploy.prototxt"
CAFFEMODEL_URL = "https://github.com/chuanqi305/MobileNet-SSD/raw/master/mobilenet_iter_73000.caffemodel"

PROTOTXT_PATH = os.path.join(MODELS_DIR, "deploy.prototxt")
CAFFEMODEL_PATH = os.path.join(MODELS_DIR, "mobilenet_ssd.caffemodel")


def download(url, path, desc):
    print(f"Downloading {desc}...")
    try:
        r = requests.get(url, stream=True, timeout=30)
        r.raise_for_status()
        total = int(r.headers.get("content-length", 0))
        downloaded = 0
        with open(path, "wb") as f:
            for chunk in r.iter_content(chunk_size=8192):
                f.write(chunk)
                downloaded += len(chunk)
                if total:
                    pct = downloaded / total * 100
                    print(f"\r  {pct:.1f}% ({downloaded // 1024} KB / {total // 1024} KB)", end="")
        print()
        print(f"  Saved to {path}")
        return True
    except Exception as e:
        print(f"  Error: {e}")
        return False


if __name__ == "__main__":
    if not os.path.exists(PROTOTXT_PATH):
        download(PROTOTXT_URL, PROTOTXT_PATH, "deploy.prototxt")
    else:
        print("deploy.prototxt already exists.")

    if not os.path.exists(CAFFEMODEL_PATH):
        print("\nNote: mobilenet_ssd.caffemodel is ~23 MB and may take a moment.")
        download(CAFFEMODEL_URL, CAFFEMODEL_PATH, "mobilenet_ssd.caffemodel")
    else:
        print("mobilenet_ssd.caffemodel already exists.")

    if os.path.exists(PROTOTXT_PATH) and os.path.exists(CAFFEMODEL_PATH):
        print("\nBoth model files ready! Object Detection is now fully functional.")
    else:
        print("\nSome files are missing. The Object Detection path will fall back to an error message.")
