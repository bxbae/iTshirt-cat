#!/usr/bin/env bash
# 캣북스 데모를 한 번에 실행합니다: ./start.sh   (종료: Ctrl+C)
# 필요한 것: Python 3.11+, Node.js 20+
set -euo pipefail
cd "$(dirname "$0")"

command -v python3 >/dev/null || { echo "python3가 필요합니다 (3.11 이상)"; exit 1; }
command -v npm >/dev/null || { echo "Node.js(npm)가 필요합니다 (20 이상)"; exit 1; }

if [ ! -d backend/.venv ]; then
  echo "▶ 백엔드 패키지 설치 (처음 한 번)"
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -q -r backend/requirements.txt
fi
if [ ! -d frontend/node_modules ]; then
  echo "▶ 프런트엔드 패키지 설치 (처음 한 번)"
  (cd frontend && npm install --no-audit --no-fund --loglevel=error)
fi

pids=()
cleanup() { kill "${pids[@]}" 2>/dev/null || true; }
trap cleanup EXIT INT TERM

echo "▶ 백엔드 시작 (http://localhost:8000)"
(cd backend && LLM_PROVIDER="${LLM_PROVIDER:-mock}" .venv/bin/uvicorn app.main:app --port 8000) &
pids+=($!)

echo "▶ 프런트엔드 시작 (http://localhost:3000)"
(cd frontend && npm run dev) &
pids+=($!)

echo
echo "  쇼핑몰   http://localhost:3000        (로그인: /login 에서 가상 고객 선택)"
echo "  상담원   http://localhost:3000/admin"
echo "  초기화   Ctrl+C 후 backend/catbooks.db 를 지우고 다시 실행"
echo
wait
