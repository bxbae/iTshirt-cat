# iTshirt-cat

가벼운 비전/NLP 모델 5종을 FastAPI로 서빙하는 프로젝트 (Windows 로컬, conda env `py311`, torch + CUDA 12.6).

## 구조
- `services/<name>/` : 모델별 독립 FastAPI 앱 (`app.py`, `requirements.txt`, `README.md`, `example_client.py`)
  - classification / detection / pose / face / emotion
- `wiki/` : llm-wiki. 리서치·결정·기억할 정보를 주제별 md로 구조화 (`wiki/index.md`가 목차)
- `HISTORY.md` : 진행 과정 로그 (시간순, 최신이 위)
- `STATS.md` : 현재 상태 대시보드 (서비스별 모델/크기/검증 여부)
- `setup-dev-env.ps1` : Windows 개발환경 설치 스크립트

## 규칙
1. 작업 단위가 끝날 때마다 HISTORY.md(무엇을/왜) + STATS.md(현재 상태)를 갱신한다.
2. 리서치 결과·모델 선택 근거·라이선스·함정은 `wiki/`에 주제별 파일로 쓰고 `wiki/index.md`에 링크한다.
3. 검증하지 않은 것은 "검증됨"이라 쓰지 않는다. STATS.md의 Verified 칸에 실제 실행한 것만 기록.
4. 모델 가중치는 커밋하지 않는다 (.gitignore). 첫 실행 시 자동 다운로드.

## 모델 사용 정책 (비용 절감)
- 메인 에이전트: Sonnet 5.5
- 일반 개발/검색 서브에이전트: Haiku 5.5 또는 Sonnet 5.5 (`.claude/agents/dev.md`, `researcher.md`)
- 리뷰/검증/창의적·중요 결정: Opus 5.5 또는 Fable 5.1 (`.claude/agents/reviewer.md`)
- 독립 작업은 항상 병렬(Workflow/Agent)로 실행한다.
