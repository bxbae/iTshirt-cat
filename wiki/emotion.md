# Emotion (한국어 감정 분류)

## 결정
- 기본: `GGARA02/kcelectra-korean-emotion` - beomi/KcELECTRA-base-v2022를 AI-Hub 감성대화 말뭉치로 파인튜닝한 6 클래스 모델 (웹 검색 결과 요약으로만 확인).
- `MODEL_ID`로 교체 가능, 라벨은 `config.id2label`에서 읽으므로 코드 수정 불필요. softmax/sigmoid는 `config.problem_type` 또는 `MULTI_LABEL=1`로 결정.

## 후보 (검색으로 존재 확인, 직접 다운로드/실행은 못 함)
| 모델 ID | 베이스 | 클래스 | 비고 |
|---|---|---|---|
| GGARA02/kcelectra-korean-emotion | KcELECTRA-base-v2022 | 6 | 기본값 |
| hyunwoo1107/Multi_Emotion_Model | KoELECTRA(base 계열로 보임) | 5 | 미확인 세부 |
| AKS-DHLAB/KPoEM | KcELECTRA, KOTE 후 KPoEM 학습 | 시(poetry) 도메인 | 도메인 특화 |
| LimYeri/HowRU-KoELECTRA-Emotion-Classifier | KoELECTRA | 미확인 | 검색에 파일만 노출 |
- KOTE 데이터셋(arXiv 2205.05300): 온라인 댓글 5만 건, 43 감정+무감정. 공개된 KOTE 체크포인트는 검색으로 확인 못 함(미확인).
- KoELECTRA-small 기반 감정 모델은 찾지 못함(small은 NSMC 이진 감성 모델만 확인). 진짜 경량이 필요하면 koelectra-small을 직접 파인튜닝해야 함.

## 미확인 사항
- 이 컨테이너에서 huggingface.co 접근 불가(프록시 403)라 모델 카드, 실제 라벨명, 라이선스, 파일 크기, 정확도 모두 직접 확인하지 못했다. 파라미터 수/용량은 KcELECTRA-base 일반 지식 기반 추정(약 0.4~0.5GB).
- 라이선스: 미확인(배포 전 모델 카드 확인).

## 검증 범위
- 실행함: mock 기반 API 계약 테스트 10건 통과, 로컬에서 만든 무작위 가중치 tiny ELECTRA + 가짜 토크나이저로 Predictor 후처리(softmax 합 1, sigmoid, top-k 정렬, id2label 매핑) 확인.
- 못 함: 실제 HF 모델 다운로드/추론, GPU 실행, Windows 실행.

## Windows 함정
- 첫 호출 시 HF 다운로드(수백 MB): 사용자 프로필에 한글이 있으면 HF 캐시 경로 문제 가능(미확인) -> `HF_HOME`을 ASCII 경로로.
- symlink 경고: 개발자 모드 없으면 캐시가 복사 방식이 됨(동작엔 문제 없음, 용량만 증가).
- torch는 requirements에 핀하지 않음; CUDA 12.6 빌드를 먼저 설치.

## 출처
- https://huggingface.co/GGARA02/kcelectra-korean-emotion
- https://huggingface.co/hyunwoo1107/Multi_Emotion_Model
- https://huggingface.co/AKS-DHLAB/KPoEM
- https://arxiv.org/abs/2205.05300 (KOTE)
