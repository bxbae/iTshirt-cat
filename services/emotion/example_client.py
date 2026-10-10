"""Example: python example_client.py [base_url]"""
import sys
import requests

BASE = sys.argv[1] if len(sys.argv) > 1 else "http://127.0.0.1:8005"
TEXTS = [
    "오늘 승진했어! 너무 기쁘고 행복해",
    "친구가 거짓말을 해서 정말 화가 나",
    "혼자 있으니까 너무 외롭고 슬퍼요",
    "내일 발표인데 떨리고 불안하다",
    "이게 무슨 일이야, 깜짝 놀랐네",
]

print(requests.get(f"{BASE}/health", timeout=10).json())
r = requests.post(f"{BASE}/predict", json={"texts": TEXTS, "top_k": 3}, timeout=300)
r.raise_for_status()
data = r.json()
print("model:", data["model"], "device:", data["device"])
for text, res in zip(TEXTS, data["results"]):
    print(text, "->", ", ".join(f"{s['label']}({s['score']:.2f})" for s in res))
