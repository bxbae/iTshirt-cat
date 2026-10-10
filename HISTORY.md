# HISTORY (최신이 위)

## 2026-10-10 — 하네스 구축 + 5개 모델 서비스 착수
- CLAUDE.md, HISTORY.md, STATS.md, wiki/, .claude/agents/ 생성
- 워크플로우로 5개 서비스(classification, detection, pose, face, emotion) 병렬 구현 시작

## 2026-10-10 — Windows 개발환경 스크립트
- `setup-dev-env.ps1` 추가: VS Code/Git/Miniforge/CUDA 12.6 병렬 설치 + conda py311 + torch 2.14.1
- 한계: 컨테이너가 Linux라 Windows에서 실행/검증하지 못함. torch 2.14.1 존재 여부 미확인
