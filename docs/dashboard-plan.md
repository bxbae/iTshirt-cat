# 대시보드 구성안 (dashboard-api · dashboard-web)

담당: 병환. 팀 자료(`CLAUDE.md`, `repo-structure.md`, `requirements.md`, `planning.md`) 기준. 고객지원 에이전트 구성안과는 별도 문서로 둔다 — 대시보드는 `support` 에이전트가 아니라 **공통 모듈**이다.

## 1. 위치

| 항목 | 값 |
|---|---|
| 서버 | `ax-backend/dashboard-api/` · 포트 **8020** · 서비스(LLM 없음) |
| 화면 | `ax-frontend/dashboard-web/` · 포트 **3001** · React + Vite, `common-frontend` 기반 |
| 타입 | `ax-frontend/types/` — CI가 만든 `contracts/openapi/dashboard-api` 에서 `openapi-typescript`로 자동 생성, 직접 수정 금지 |
| 환경 | `VITE_DASHBOARD_API_URL=http://localhost:8020` |
| 데이터 | **공통 로그 저장소만 읽는다.** safety·orchestrator 내부를 직접 읽지 않는다 (repo-structure 핵심 규칙 3) |
| API 형식 | `/api/dashboard/<복수 명사>`, 성공 `{data, meta}`, 실패 `{error:{code,message}}` |

## 2. 요구사항 매핑

| ID | 내용 | 우선순위 | 화면 |
|---|---|---|---|
| DSH-01 | 사건 흐름: `context_id`별 Task를 시간순, 부서·상태 색 구분 (working/completed/input-required) | 필수 | 사건 타임라인 |
| DSH-02 | 실시간 갱신: 공통 로그를 SSE/폴링으로 전달 | 필수 | (전 화면) |
| DSH-03 | 안전 레이어 표시: 등급 판정, B 교차검증, C 보류 + 근거 리포트, **C 승인·거절 버튼(사람 토큰만)** | 필수 | C 보류 큐 |
| DSH-04 | KPI: MTTR, 자동 처리율, 등급별 건수, 1·2차 비교, 이관·반복 경로, 차단 건수, 사람 기준값 대비 | 권장 | KPI |
| SHOP-09 | 문의 위젯 (고객지원 소관, shop-web에 임베드) | 권장 | 위젯 |

공통안 12장 시나리오 A 필수는 **사건 타임라인 + C 보류 큐**. KPI·부서별 탭·연동 현황은 그다음.

## 3. 화면

### 3-1. 사건 타임라인 (DSH-01, 필수)
- 사건 목록(`ctx_inc_…`) → 한 사건의 Task를 부서 레인(orchestrator, infra, data, planning, marketing, support, finance, hr)으로 시간순 표시.
- 상태 색: `working` 진행, `completed` 완료, `input-required` 대기(`reason_code`로 `dept_input`/`customer_input`/`human_input` 구분 표시), `rejected`·`failed`·`canceled` 오류색.
- 정책 거절(`completed` + `outcome: auto_rejected`)은 오류색이 아니라 "정책 거절" 배지로 — 이관률·실패율 지표를 오염시키지 않기 위해 (공통안 5장).
- 각 Task에 `evidence`, `decision_reason`, 안전 레이어 등급 배지.

### 3-2. C 보류 큐 (DSH-03, 필수)
- 모든 부서의 C 건이 **safety 보류 큐 하나**에서 온다. 부서별 보류 화면을 만들지 않는다 (공통안 7장). 부서 필터만 둔다.
- 행: 액션, 요청 부서, 계산 금액, 기준표 버전, 보류 사유(`amount_mismatch`, `compensation_per_customer` 초과 등), 근거 리포트, **남은 시간(10분 카운트다운)**.
- 승인·거절 버튼은 사람 JWT로만 활성. 버튼은 safety 결정 API를 호출한다(대시보드가 직접 실행하지 않음). 무응답 10분이면 자동 거절된 상태로 표시.
- 감사: 누가 언제 무엇을 결정했는지, 무시된 경고도 남긴다 (공통안 9장 분업 원칙 3).

### 3-3. 안전 레이어 표시 (DSH-03)
- 등급별 처리·차단 건수, B 교차검증 결과(요청 부서 ≠ verifier), 차단 사유(인증·ACL·인젝션).

### 3-4. 고객지원 탭 (선택, 시나리오 A 이후)
- 프로토타입 `/admin`(문의함·코파일럿·클레임 판정·보상 큐·후기)을 이식. 이 탭의 쓰기는 **모두 support 에이전트 API 경유**이며 `execute()` 관문을 우회하지 않는다.
- 상담원 승인(`needs_review`)은 C 보류 큐로 일원화한다.

### 3-5. KPI (DSH-04, 권장)
- MTTR, 자동 처리율(`input-required` 없이 끝난 비율), 고객지원 Task 처리 시간, 등급별 건수, 이관 건수·반복 경로, 인젝션·ACL 차단 건수, 1차 vs 2차 사건 비교(SCN-L), 사람 기준값 vs 실측.
- 숫자는 코드로 산출하고 LLM을 쓰지 않는다.

### 3-6. 문의 위젯 (SHOP-09)
- 독립 번들로 shop-web에 임베드, 고객 로그인은 shop-web의 것을 따른다.
- 접수 시 `support.inquiry_received` 이벤트를 `events.publish`(Redis Streams)로 발행. 원문은 `untrusted`. 응답은 위젯에 표시.

## 4. API (초안, `contracts/openapi/`로 자동 생성되는 것이 원본)

| 메서드·경로 | 용도 |
|---|---|
| `GET /api/dashboard/incidents` | 사건 목록 (`context_id`, 상태, 소요 시간) |
| `GET /api/dashboard/incidents/{context_id}/tasks` | 사건의 Task 타임라인 |
| `GET /api/dashboard/events/stream` | SSE (DSH-02) |
| `GET /api/dashboard/holds` | C 보류 큐 (safety 보류 큐 읽기) |
| `POST /api/dashboard/holds/{exe_id}/decisions` | 승인·거절 — 사람 토큰만. safety 결정 API로 위임 |
| `GET /api/dashboard/safety-stats` | 등급별 건수·차단 건수 |
| `GET /api/dashboard/kpis` | DSH-04 |

> `/holds`는 **읽기 전용 뷰 + 결정 위임**이다. 부서별 보류 목록을 만들지 않는다는 규칙과 "dashboard-api는 공통 로그만 읽는다"는 규칙을 둘 다 지키려면 결정 쓰기를 safety API에 위임해야 하는데, 이 경로가 규약에 명시돼 있지 않다 — [부족한 점 보고서](support-gap-report.md) G12.

## 5. 개발 순서

1. dashboard-api: 공통 로그 읽기 + 사건·Task 목록, OpenAPI 생성 (준하의 로그 저장소 형식 필요)
2. dashboard-web: `common-frontend` 기반 뼈대, 사건 타임라인 (DSH-01)
3. SSE (DSH-02)
4. C 보류 큐 + 승인·거절 (DSH-03) — 태윤의 safety 결정 API 필요
5. 문의 위젯 (SHOP-09)
6. KPI (DSH-04), 고객지원 탭

단독 테스트: 목 로그 데이터로 타임라인 표시 · 사람 토큰 없이 결정 API 호출 시 거부 · 10분 경과 시 자동 거절 표시 · 정책 거절이 오류로 집계되지 않음.
