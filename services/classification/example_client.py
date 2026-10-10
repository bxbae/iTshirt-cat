"""사용: python example_client.py [이미지경로_또는_URL]  (서버: uvicorn app:app --port 8001)"""
import io
import sys

import requests
from PIL import Image

BASE = "http://127.0.0.1:8001"


def sample_image() -> bytes:
    img = Image.new("RGB", (320, 240), (200, 120, 40))  # 코드로 생성한 단색 이미지
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def load(arg):
    if arg is None:
        return sample_image()
    if arg.startswith("http"):
        return requests.get(arg, timeout=30).content
    with open(arg, "rb") as f:
        return f.read()


if __name__ == "__main__":
    print(requests.get(f"{BASE}/health", timeout=10).json())
    data = load(sys.argv[1] if len(sys.argv) > 1 else None)
    r = requests.post(f"{BASE}/predict", params={"top_k": 3},
                      files={"file": ("img.jpg", data, "image/jpeg")}, timeout=120)
    print(r.status_code)
    for p in r.json().get("predictions", []):
        print(f"{p['probability']:.3f}  {p['label']}")
    if r.status_code != 200:
        print(r.text)
