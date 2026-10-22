# 고객지원 참고 문서

팀 자료(`CLAUDE.md`, `repo-structure.md`, `planning.md`, `requirements.md`, `agent-common.md`) 기준으로 2026-10-22에 갱신했다.

| 문서 | 내용 |
|---|---|
| [support-agent-plan.md](support-agent-plan.md) | **v2** — 공통안 목차 10장에 맞춘 고객지원(`support`) 구성안: skill·등급 표, 이벤트, 연결 지도, 시나리오 역할, 안전장치, 폴더·README, 단독 테스트, 확인 필요 |
| [support/agent-card.json](support/agent-card.json) | 공통안 4장 형식의 Agent Card 초안 (12 skill, 이벤트, 외부 호출) |
| [dashboard-plan.md](dashboard-plan.md) | dashboard-api(8020)·dashboard-web(3001), DSH-01~04, C 보류 승인 화면, 문의 위젯 |
| [support-gap-report.md](support-gap-report.md) | 부족했던 점 정리, 팀에 확인·수정 요청할 것, 프로토타입 코드 차이 |
| [marketing-support-loop.md](marketing-support-loop.md) | 마케팅 ↔ 고객지원 대외 소통 루프(①~⑤), 자동화 흐름, 확인 필요(공통안으로 닫힌 것 표시) |
| [marketing-plan-alignment.md](marketing-plan-alignment.md) | 재헌의 마케팅 기획안 v3와 대조 + 공통안으로 닫힌 것 |
| [support-reference.pdf](support-reference.pdf) | 위 문서들을 그림과 함께 묶은 공유용 PDF |

## 흐름 그림 (`images/`, SVG와 PNG)

| 그림 | 파일 |
|---|---|
| support 연결 지도 (공통안 기준) | `support-connections` |
| 마케팅 ↔ 고객지원 대외 소통 루프 (①~⑤) | `marketing-support-loop` |
| 고객지원 Agent 자동화 흐름 | `support-automation-flow` |
| 대표 사건 흐름 (불량 신청 → 반품 입고 → 보상 지급) | `support-case-flow` |
| 폴더 배치: 모노레포 + 독립 패키지 | `support-repo-layout` |
