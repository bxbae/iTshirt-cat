"""Example client. Usage: python example_client.py [face_image_path_or_url] [second_image]

With no args it downloads a public sample face (OpenCV's lena.jpg) and demonstrates every endpoint.
Server must be running: uvicorn app:app --port 8004
"""
import sys

import requests

BASE = "http://127.0.0.1:8004"
SAMPLE_URL = "https://raw.githubusercontent.com/opencv/opencv/4.x/samples/data/lena.jpg"


def load(src: str) -> bytes:
    if src.startswith("http"):
        r = requests.get(src, timeout=60)
        r.raise_for_status()
        return r.content
    with open(src, "rb") as f:
        return f.read()


def main():
    a = load(sys.argv[1] if len(sys.argv) > 1 else SAMPLE_URL)
    b = load(sys.argv[2]) if len(sys.argv) > 2 else a  # same image -> expect same_person=True

    print("health:", requests.get(f"{BASE}/health", timeout=10).json())

    r = requests.post(f"{BASE}/detect", files={"file": ("a.jpg", a)}, timeout=120).json()
    print(f"detect: {r['count']} face(s)")
    for f in r["faces"]:
        print("  box", f["box"], "score", round(f["score"], 3))

    r = requests.post(f"{BASE}/embed", files={"file": ("a.jpg", a)}, timeout=120).json()
    print("embed: dim", r["dim"], "first 4:", [round(x, 3) for x in r["embedding"][:4]])

    r = requests.post(f"{BASE}/verify", files={"file1": ("a.jpg", a), "file2": ("b.jpg", b)}, timeout=120).json()
    print("verify: same_person", r["same_person"], "cosine", round(r["cosine_similarity"], 3), "thr", r["threshold"])

    r = requests.post(f"{BASE}/gallery/register", data={"name": "alice"}, files={"file": ("a.jpg", a)}, timeout=120)
    print("register:", r.json()["gallery_size"], "in gallery")
    r = requests.post(f"{BASE}/gallery/identify", files={"file": ("b.jpg", b)}, timeout=120).json()
    print("identify:", r["name"], "cosine", round(r["cosine_similarity"], 3))


if __name__ == "__main__":
    main()
