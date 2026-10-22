# 고객지원 문서 부족한 점 보고서 (2026-10-22)

팀 자료 5종(`CLAUDE.md`, `repo-structure.md`, `planning.md`, `requirements.md`, `agent-common.md`)과 우리 고객지원 문서·프로토타입을 대조해 찾은 것이다. A는 **우리 문서에서 고친 것**, B는 **새로 만든 문서**, C는 **팀에 확인·수정을 요청할 것**, D는 **프로토타입 코드가 아직 다른 것**이다.

## A. 우리 문서에서 고친 것 (반영 완료)

| # | 부족했던 점 | 고친 곳 |
|---|---|---|
| G1 | 목차가 공통 목차(10개)와 달랐고 공통 항목을 다시 정의함 | `support-agent-plan.md` v2로 재작성, "공통안 n장을 따른다" |
| G2 | Agent Card가 `action_grade`/`acl`/`input` 형식 | 공통안 4장 형식(`grade`, `allowed_requesters`, `verifier`, `priority`, 스키마 경로)으로 새로 작성 → `support/agent-card.json` |
| G3 | skill에 `priority`(required/recommended/optional) 없음 | 2장 표에 표시. 시나리오 A 필수 = `inquiry_draft`, `reply_send`, `compensation_request`, 문의 위젯 이벤트 |
| G4 | Task 상태에 `reason_code` 없음 (`dept_input`/`customer_input`/`human_input`) | 공통안 5장 반영, 대시보드 표시 규칙 포함 |
| G5 | C 보류를 "상담원 승인 + 부서 보류"로 설명 | **safety 보류 큐 하나 + 10분 자동 거절 + 사람 토큰 결정** 으로 수정 (결정 2·6) |
| G6 | LLM이 Anthropic | `LLMClient`(OpenAI 호환)·Gemini·`SUPPORT_LLM_*`, LLM 실패 시 `fallback` 템플릿, LLM 문장 속 숫자가 다르면 문장 폐기 |
| G7 | 포트·레포 위치·폴더 미확정 | 8102, `agents/support/`, 8장 폴더 구조, README 5항목 |
| G8 | 교차검증을 "마케팅/고객지원이 재무에 요청"으로 서술 | `execute()`만 호출하고 안전 레이어가 finance `verify_amount`로 라우팅 (후속 13) — 루프·alignment 문서도 패치 |
| G9 | 영향 숫자의 출처가 불명확 | 영향 원천 숫자는 data `impact_analysis`만. 보상 대상 판정에서 대조 (공통안 8장) |
| G10 | 사례 카드·공지 색인을 우리가 가질 듯한 서술 | 카드 저장·검색은 memory, 결정 카드 문장은 hr (`record_case`) |
| G11 | 이벤트 목록이 불완전 | 공통안 6장 카탈로그로 발행·구독·단계(1차/2차) 정리. `support.inquiry_received`는 확정(1차) |
| G13 | 시나리오별 역할 없음 | 6장: SCN-A/B/S/L |
| G14 | 단독 테스트가 공통 8항목과 다름 | 9장에 8항목 표 + 고유 테스트 |
| G15 | 판매자 안내(DEP-CS-03, SCN-B) skill 누락 | `seller_notice` 추가 (optional) |
| G16 | 환경변수·테이블·ID 규칙 | 8장 이름 규칙 표 (`SUPPORT_*`, `tenant_id`·`context_id`, `inq_`·`ret_`·`rfd_`…) |
| G17 | 브랜치 규칙이 `dev`에서 `폴더/기능` | `support/<feature>` 규칙 확인(공통안은 `폴더/기능`), 영문 소문자·`-` |
| G18 | `reply_send` 금전 약속 포함 = B 라는 안 | 폐기. 약속은 `promises[]`·정책표 코드에 있는 것만, 지급 쪽 관문에서 B 처리 |
| G19 | 대시보드가 고객지원 문서에 섞임 | `dashboard-plan.md` 분리 (DSH-01~04, SHOP-09) |
| G20 | 연결 지도가 없었음 | `images/support-connections` 추가 (공통안 기준 support 중심 지도) |
| G21 | 루프 문서의 확인 필요 중 닫힌 것이 열려 있음 | `marketing-support-loop.md`·`marketing-plan-alignment.md`에 "공통안 13장으로 닫힘" 표시 |

## B. 새로 만든 문서

| 문서 | 내용 |
|---|---|
| `support-agent-plan.md` (v2) | 공통 목차 10장 구성 |
| `support/agent-card.json` | 12개 skill, 이벤트, 외부 호출 목록 (초안) |
| `dashboard-plan.md` | dashboard-api(8020)·dashboard-web(3001), DSH-01~04, 문의 위젯 |
| `support-gap-report.md` | 이 문서 |
| `images/support-connections` | support 연결 지도 |

## C. 팀에 확인·수정을 요청할 것 (우리 쪽에서 결정할 수 없음)

| # | 내용 | 누구에게 | 제안 |
|---|---|---|---|
| G-C1 | **클레임 ID 접두사가 없다.** CLAUDE.md ID 목록에 `inq_`·`ret_`·`rfd_`는 있으나 클레임이 없다 | 준하 | `clm_` 추가 |
| G-C2 | **`return.received` 필드 불일치.** requirements 부록 `claim_id, order_id, 입고 시각` ↔ 공통안 6장 "반품 입고 시각" | 재헌·준하 | `return_id`(`ret_`), `order_id`, `received_at` — `claim_id`는 고객지원 내부 값이라 이벤트에 넣지 않는다 |
| G-C3 | **SHOP-09 우선순위 불일치.** requirements "권장" ↔ 공통안 12장 시나리오 A "문의 위젯 이벤트 필수" | 준하 | 이벤트는 필수, 위젯 화면은 권장으로 분리해 적기 |
| G-C4 | **장애 보상 단가·기준.** `impact_analysis`는 영향 고객 ID·피해 금액만 주고 건당 보상액은 없다. 환불은 `compensation_per_*` 키가 보상 쿠폰 위주 | 재현·태윤 | 단가·대상 판정은 support 정책표, 상한은 finance 기준표. **현금 환불용 기준 키**(`refund_per_order` 등) 추가 필요 |
| G-C5 | **대시보드 C 결정 쓰기 경로.** "결정 API는 사람 토큰만"(공통안 7장) ↔ "dashboard-api는 공통 로그만 읽음"(CLAUDE.md) — 결정을 어디로 쓰나 | 태윤·병환 | dashboard-api는 safety 결정 API로 위임만 하고 읽기는 공통 로그. 계약에 명시 |
| G-C6 | **`needs_review`(사람 확정) 액션 등록.** 불량·반품 흐름의 사람 확인을 레지스트리에 어떻게 올릴지 | 태윤 | `claim_manual_review`를 C 액션으로 신규 등록, Task는 `human_input` |
| G-C7 | **`compensation_request`를 A로 신고** 해도 누적 기준은 마케팅 `issue_coupon`에서 계산됨. 요청 쪽(support)이 중복 계산하지 않는다는 합의가 필요 | 태윤·재헌 | 안전 레이어가 `issue_coupon` 기준으로 계산, 우리는 조회만 |
| G-C8 | **브랜치 이름.** CLAUDE.md "`폴더/기능`" ↔ 이전 안 `support/<feature>` | 준하 | `support/<feature>`는 `폴더/기능` 규칙과 같다 — 변경 없음, 확인만 |
| G-C9 | **판매자 안내 입력.** SCN-B에서 support가 finance 판정을 어떻게 받는지 skill·Task가 없다 | 준하 | orchestrator가 결과를 Task 입력으로 전달 |
| G-C10 | **문의→사건 context_id.** `support.inquiry_received`는 `context_id: null`, 사건 발급은 orchestrator. 문의가 사건과 무관할 땐 `ctx_`가 없는 일반 문의는 어떻게 추적하나 | 준하 | 사건이 아닌 일상 문의는 `context_id`를 `null`로 두거나 문의 단위 ID를 허용하는지 결정 필요 |

## D. 프로토타입 코드가 팀 규약과 다른 점 (문서만 맞춤, 코드 미변경)

| # | 현재 코드 | 목표 | 크기 |
|---|---|---|---|
| D1 | Anthropic/mock LLM 제공자 | `LLMClient`(OpenAI 호환, Gemini), `SUPPORT_LLM_*` | 중 |
| D2 | 상담원이 직접 승인·거절 | C 보류 → safety 큐, 10분 자동 거절 | 중 (safety 필요) |
| D3 | 앱이 보상·환불 직접 지급 | `execute()` 뒤, 보상은 marketing `issue_coupon` 요청 | 대 |
| D4 | 모놀리식 FastAPI + Next.js 14 | uv workspace 독립 패키지 + React/Vite | 대 |
| D5 | `tenant_id`·`context_id` 없음, 테이블 단수 | 모든 테이블에 추가, 복수형 snake_case | 중 |
| D6 | `/api/claims` 등 | `/api/support/claims`, `{data, meta}` | 중 |
| D7 | 한글 커밋 메시지, 접두사 없는 환경변수 | Conventional Commits, `SUPPORT_*` | 소 |

D1~D7은 **팀 레포(`ax-backend`) 쪽 뼈대(준하의 `contracts/`·`agent-template/`)가 올라온 뒤** 옮기는 게 안전하다. 그 전에는 판정 엔진·큐·가드를 프레임워크 독립 모듈로 분리해 두는 단계 1이 가장 효과가 크다.
