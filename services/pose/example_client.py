"""사용: python example_client.py [이미지경로_또는_URL]  (서버: uvicorn app:app --port 8003)
인자가 없으면 ultralytics 공식 샘플(bus.jpg, 사람 포함) URL을 받아 사용하고, 실패하면 단색 이미지로 대체한다."""
import io
import sys

import requests
from PIL import Image

BASE = "http://127.0.0.1:8003"
SAMPLE_URL = "https://github.com/ultralytics/assets/releases/download/v0.0.0/bus.jpg"


def fallback_image() -> bytes:
    buf = io.BytesIO()
    Image.new("RGB", (320, 240), (200, 120, 40)).save(buf, format="JPEG")  # 사람 없음 -> 빈 결과
    return buf.getvalue()


def load(arg):
    if arg is None:
        try:
            r = requests.get(SAMPLE_URL, timeout=30)
            r.raise_for_status()
            return r.content
        except requests.RequestException as e:
            print("샘플 다운로드 실패, 단색 이미지 사용:", e)
            return fallback_image()
    if arg.startswith("http"):
        return requests.get(arg, timeout=30).content
    with open(arg, "rb") as f:
        return f.read()


if __name__ == "__main__":
    print(requests.get(f"{BASE}/health", timeout=10).json())
    data = load(sys.argv[1] if len(sys.argv) > 1 else None)
    files = {"file": ("img.jpg", data, "image/jpeg")}

    r = requests.post(f"{BASE}/pose", params={"conf": 0.25}, files=files, timeout=300)
    print(r.status_code)
    if r.status_code != 200:
        print(r.text)
        sys.exit(1)
    j = r.json()
    print(f"device={j['device']} persons={j['num_persons']} size={j['image_width']}x{j['image_height']}")
    for i, p in enumerate(j["persons"]):
        print(f" person {i}: score={p['score']:.2f} bbox={[round(v) for v in p['bbox']]}")
        for k in p["keypoints"][:3]:
            print(f"   {k['name']}: ({k['x']:.0f},{k['y']:.0f}) score={k['score']:.2f}")

    r = requests.post(f"{BASE}/pose/image", files=files, timeout=300)
    print(r.status_code, r.headers.get("content-type"), len(r.content), "bytes")
    if r.status_code == 200:
        with open("pose_overlay.png", "wb") as f:
            f.write(r.content)
        print("저장: pose_overlay.png")
