# CatalogGuard Lite v0.1.0 Fact Consistency Matrix

기준: Portfolio MVP Release v0.1.0, Release SHA `be0f380a79d6a8a48b07f663473ba904bb34019f`, Inspection Version 14, Alembic head `20260908_0019`.

| 사실 | Official Fact Sheet | Python FastAPI | 패션 이커머스 | 데이터 품질 ETL | 면접 치트시트 | 상태 |
| --- | --- | --- | --- | --- | --- | --- |
| v0.1.0 | Portfolio MVP Release | 반영 | 반영 | 반영 | 반영 | 일치 |
| Inspection Version 14 | 현재 검수 결과 계약 | 반영 | 반영 | 반영 | 반영 | 일치 |
| Alembic 0019 | `20260908_0019` | 반영 | 반영 | 반영 | 반영 | 일치 |
| Source Row Identity | header=1, 첫 상품=2, 빈·중복 ID 구분 | 재사용 경계 설명 | 핵심 사례 | 핵심 사례 | 핵심 Q&A | 일치 |
| Correction Worksheet | 원본 논리 행 기준 issue 작업표 CSV | 자동 수정 아님 명시 | 핵심 사례 | 핵심 사례 | 핵심 Q&A | 일치 |
| ETL rejection CSV | 전체 pagination, masked data, partial fetch 차단, BOM/formula-safe | 보조 설명 | 보조 설명 | 핵심 사례 | 핵심 Q&A | 일치 |
| 24 active rule codes | 기능군으로 묶어 설명 | 과도한 숫자 강조 안 함 | 과도한 숫자 강조 안 함 | 과도한 숫자 강조 안 함 | 과도한 숫자 강조 안 함 | 일치 |
| Redis Celery | 비동기 inspection | 핵심 기술 | 보조 근거 | 역할 구분 | 핵심 Q&A | 일치 |
| Promotion Rollback | preview, hash, transaction, audit, conflict-aware rollback | 핵심 사례 | 핵심 사례 | 보조 근거 | 핵심 Q&A | 일치 |
| CI 5개 | test, browser-e2e, kubernetes-smoke, terraform-validate, airflow-smoke | 반영 | 반영 | 반영 | 반영 | 일치 |
| Semantic duplicate 미지원 | ID·정규화 상품명·옵션·내용 기반 중복 탐지 | 미주장 | 금지 표현 명시 | 미주장 | 핵심 Q&A | 일치 |
| Production 운영 제한 | 상용 서비스 아님 | 제한 명시 | 제한 명시 | 제한 명시 | 제한 명시 | 일치 |

## Archive 후보

- 2026-08-17 PDF/DOCX 지원자료: 당시 기준과 레이아웃 참고용으로 보존. v0.1.0 현재 사실을 설명하는 제출본으로는 사용하지 않음.
- 2026-08-27 통합본: Feature Freeze 시점의 상세 참고용으로 보존. 이번 동기화본의 직무별 패키지와 면접 치트시트를 우선 사용.
