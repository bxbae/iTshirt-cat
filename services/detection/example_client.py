"""Example client. Start the server first:  uvicorn app:app --port 8002

    python example_client.py [image_path_or_url]
Without an argument a synthetic image is generated (it will probably contain no COCO objects;
pass a real photo to see detections).
"""
import io
import sys

import requests
from PIL import Image, ImageDraw

BASE = "http://127.0.0.1:8002"


def load_sample(arg=None) -> bytes:
    if arg and arg.startswith("http"):
        r = requests.get(arg, timeout=30)
        r.raise_for_status()
        return r.content
    if arg:
        with open(arg, "rb") as f:
            return f.read()
    img = Image.new("RGB", (640, 480), (200, 220, 240))
    d = ImageDraw.Draw(img)
    d.rectangle([100, 200, 400, 400], fill=(120, 60, 30))
    d.ellipse([420, 100, 560, 240], fill=(250, 200, 30))
    buf = io.BytesIO()
    img.save(buf, format="JPEG")
    return buf.getvalue()


def main():
    data = load_sample(sys.argv[1] if len(sys.argv) > 1 else None)
    print("health:", requests.get(f"{BASE}/health", timeout=10).json())

    r = requests.post(
        f"{BASE}/detect",
        files={"file": ("sample.jpg", data, "image/jpeg")},
        data={"score_threshold": 0.4},
        timeout=120,  # first call downloads weights (~13 MB) and loads the model
    )
    r.raise_for_status()
    res = r.json()
    print(f"{res['count']} object(s) in {res['width']}x{res['height']}")
    for d in res["detections"]:
        b = d["bbox"]
        print(f"  {d['label']:<14} {d['score']:.2f}  ({b['x1']:.0f},{b['y1']:.0f})-({b['x2']:.0f},{b['y2']:.0f})")

    r = requests.post(
        f"{BASE}/detect/image",
        files={"file": ("sample.jpg", data, "image/jpeg")},
        data={"score_threshold": 0.4},
        timeout=120,
    )
    r.raise_for_status()
    with open("detect_result.png", "wb") as f:
        f.write(r.content)
    print("saved detect_result.png (X-Detection-Count =", r.headers.get("X-Detection-Count"), ")")


if __name__ == "__main__":
    main()
