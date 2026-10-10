# HISTORY (최신이 위)

## 2026-10-10 — 5개 모델 서비스 구현 완료 (워크플로우 15 에이전트)
- Build(Sonnet 5.5 x5) → Review(Opus 5.5 x5, 읽기 전용) → Fix(Sonnet 5.5 x5)
- 리뷰 공통 지적과 반영: 압축폭탄/초대형 이미지(픽셀 상한 413), 동기 추론이 이벤트 루프 차단(threadpool), PowerShell README 명령 오류(`curl.exe`, `$env:`), 503 응답에 내부 예외 노출
- face: opencv 의존성(high) 및 모델 로드 관련 지적 반영
- 컨테이너 검증: 서비스별 pytest 통과(classification 12, detection 15, pose 15, face 13+1 skip, emotion 10). 합쳐서 한 번에 돌리면 `app` 모듈명 충돌 → 서비스 디렉터리별로 실행
- 확인된 사실: torch 2.14.1은 PyPI에 실제 존재(컨테이너에 2.14.1+cu130 설치됨). cu126 인덱스 존재는 여전히 미확인(프록시 403)
- 한계: 실제 사전학습 가중치 추론(classification/detection/emotion)은 pytorch.org/HF 차단으로 미검증. Windows/GPU 미검증

## 2026-10-10 — 하네스 구축 + 5개 모델 서비스 착수
- CLAUDE.md, HISTORY.md, STATS.md, wiki/, .claude/agents/ 생성
- 워크플로우로 5개 서비스(classification, detection, pose, face, emotion) 병렬 구현 시작

## 2026-10-10 — Windows 개발환경 스크립트
- `setup-dev-env.ps1` 추가: VS Code/Git/Miniforge/CUDA 12.6 병렬 설치 + conda py311 + torch 2.14.1
- 한계: 컨테이너가 Linux라 Windows에서 실행/검증하지 못함. torch 2.14.1 존재 여부 미확인
