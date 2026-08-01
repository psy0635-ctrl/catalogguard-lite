<!-- 역할: CatalogGuard Lite를 포트폴리오용으로 소개하는 프로젝트 설명 문서입니다. -->

# CatalogGuard Lite 포트폴리오 소개

## 6.1 프로젝트 한 줄 소개

CatalogGuard Lite는 Python·FastAPI 백엔드와 PostgreSQL 저장 계층을 중심으로 상품 CSV의 데이터 품질을 검수하고, ETL staging 결과를 선택적으로 운영 상품에 반영하는 품질 검사 도구입니다. ETL 변환·적재 실행은 CLI가 담당하고, Streamlit은 저장된 batch를 선택해 preview·승인·promotion을 요청하며 FastAPI와 PostgreSQL이 반영·audit을 처리합니다.

- 배포 URL: https://catalogguard-lite-p6jtwmdhwqcapphpghfzduo.streamlit.app/
- 개발 언어: Python
- 화면 프레임워크: Streamlit
- 데이터 처리: pandas
- 테스트: pytest
- CI: GitHub Actions

## 이력서용 프로젝트 요약

### 프로젝트명

CatalogGuard Lite

### 한 줄 요약

Python·FastAPI와 PostgreSQL을 기반으로 상품 CSV의 형식·중복·가격·카테고리·개인정보 문제를 검수하고 결과 이력까지 관리하는 데이터 품질 서비스입니다.

### 기술 스택

Python, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Redis, Celery, Streamlit, Docker Compose, GitHub Actions, Pytest

### 이력서용 핵심 문장

1. 상품 CSV의 필수값·형식·중복·가격·카테고리·개인정보 문제를 규칙으로 검출하고, 오류 이유와 수정 권장사항을 제공했으며 단위·API 테스트로 주요 흐름을 확인했습니다.
2. 검수 기준을 FastAPI 공통 서비스로 모으고 PostgreSQL에 실행 요약과 상세 결과를 저장했으며, API·저장 테스트로 응답과 이력 흐름을 검증했습니다.
3. 같은 CSV의 재검수를 줄이기 위해 파일 해시와 규칙 버전으로 기존 결과를 조회하고 partial unique index로 경쟁 요청을 막았으며, 중복 결과 재사용 테스트로 확인했습니다.
4. 긴 작업은 Redis·Celery로 상태를 분리하고 GitHub Actions에서 PostgreSQL·Redis·FastAPI·Worker를 연결한 비동기 E2E를 검증했습니다.
5. 공급사마다 코드를 따로 만들지 않고 JSON 프로필로 서로 다른 컬럼 구조를 표준 스키마에 매핑한 뒤, 표준 CSV와 summary JSON을 PostgreSQL staging에 배치 적재했습니다. 입력·프로필 identity 중복 방지와 transaction rollback을 구현하고 실제 PostgreSQL 18.4 임시 클러스터에서 검증했습니다.
6. PostgreSQL staging 적재 결과를 파일명·프로필명으로 검색하고 배치별 상품을 페이지 단위로 확인하는 FastAPI 조회 API를 구현했습니다. 목록 응답과 상세 응답의 범위를 분리하고 실제 PostgreSQL에서 필터·정렬·배치 격리를 검증했습니다.
7. Streamlit에 ETL 적재 이력 탭을 추가해 파일명·프로필명 AND 검색, 배치·상품 페이지네이션, 상세 SHA-256, nullable 필드와 request ID를 표시하고, AppTest로 stale 상태 초기화와 상세 오류 중복 호출 방지를 검증했습니다.
8. Playwright Chromium 실제 브라우저 E2E를 추가해 합성 공급사 CSV 변환·PostgreSQL 적재·FastAPI·Streamlit 실행부터 ETL 검색·상세·staging 상품·reject 마스킹·raw 원문 미노출까지 한 흐름으로 검증했습니다.
9. 운영 상품 persistence를 ETL staging과 분리하고, 공급사별 복합 identity·succeeded partial unique index·append-only JSONB audit·FK RESTRICT를 PostgreSQL 18에서 migration upgrade·downgrade·재-upgrade와 제약 테스트로 검증했습니다.
10. ETL batch 선택 → promotion preview → 변경 전·후 확인 → 명시적 승인 → preview hash 재검증 → 운영 상품 insert/update를 연결하고, transaction·stale 차단·중복 성공 방지·promotion run·append-only audit을 구현했습니다. Chromium E2E에서는 브라우저 메시지뿐 아니라 PostgreSQL 최종 상태까지 확인했습니다.

## 6.2 문제 정의

상품 CSV는 운영 업무에서 자주 쓰이지만, 사람이 직접 확인하면 다음 문제가 반복됩니다.

- 필수 컬럼이나 필수 값이 빠진 채 등록될 수 있습니다.
- 상품 ID, 상품명, 상품 내용이 중복될 수 있습니다.
- 재고와 가격이 숫자 형식에 맞지 않을 수 있습니다.
- 상품명은 상의인데 카테고리는 하의처럼 입력될 수 있습니다.
- 설명이나 판매자 정보에 전화번호, 이메일, 주민등록번호 형태, 계좌번호 의심 값이 섞일 수 있습니다.
- 검수 결과를 다시 공유할 때 CSV 한글 깨짐이나 수식 삽입 같은 문제가 생길 수 있습니다.
- Streamlit과 서버가 같은 CSV를 각각 검수하면 결과·저장·화면 표시가 어긋날 수 있고, 같은 검수를 두 번 수행하는 비용도 발생합니다.

이 프로젝트는 위 문제를 작은 웹 앱 안에서 업로드, 검수, 미리보기, 필터링, 다운로드까지 한 번에 처리하도록 만든 MVP입니다.

## 6.3 해결 목표

프로젝트의 목표는 단순한 CSV 뷰어가 아니라, 운영자가 바로 사용할 수 있는 검수 흐름을 만드는 것이었습니다.

- 사용자는 CSV만 업로드하면 됩니다.
- 앱은 검수 전에 파일 자체가 안전하고 읽을 수 있는지 확인합니다.
- 화면 미리보기에는 개인정보로 보이는 값을 가려서 보여줍니다.
- 실제 검수는 FastAPI 서버의 공통 서비스가 원본 데이터로 한 번 수행합니다.
- Streamlit은 업로드 검증과 개인정보 마스킹 미리보기를 담당하고, 서버의 상세 응답을 결과 화면에 재사용합니다.
- 서버 응답은 실행 ID, 요약, 상세 결과 필드를 검증한 뒤에만 화면 상태에 반영합니다.
- 검수 결과는 사용자가 이해할 수 있는 한글 메시지와 수정 권장사항으로 보여줍니다.
- 필터 적용 전 전체 결과를 오류 항목별, 위험 수준별, 상품별로 집계해 보여줍니다.
- 필터링한 결과만 CSV로 다운로드할 수 있습니다.

## 6.4 사용자 흐름

```text
앱 접속
-> CSV 입력 템플릿 다운로드
-> 상품 CSV 작성 또는 기존 CSV 준비
-> CSV 업로드
-> 상품 데이터 미리보기 확인
-> 검수 실행 및 이력 저장 버튼 클릭
-> FastAPI POST로 서버 검수·저장
-> FastAPI GET 상세 응답을 화면에 표시
-> 필터 적용 전 전체 검수 결과 통계 확인
-> 검수 결과 필터링
-> 현재 필터 결과 CSV 다운로드
```

업로드 후 앱 내부 흐름은 다음과 같습니다.

```text
업로드 파일 bytes
-> validate_and_read_uploaded_csv()
-> validated_df
-> create_masked_preview(validated_df)
-> 검수 실행 및 이력 저장 버튼
-> CatalogGuardApiClient
-> FastAPI POST /api/v1/inspections
-> 서버의 core.inspection_service와 core.rules
-> PostgreSQL 저장 또는 기존 실행 재사용
-> FastAPI GET /api/v1/inspections/{inspection_run_id}
-> 서버 상세 응답 검증
-> build_history_detail_dataframe()
-> build_inspection_statistics(result_df)
-> render_inspection_statistics(result_df)
-> build_validation_result_csv(filtered_result_df)
```

공급사 파일은 다음 별도 CLI 흐름으로 표준화한 뒤 기존 업로드 검증·검수 서비스에 연결할 수 있습니다.

```text
공급사 CSV + JSON 매핑 프로필
-> etl.profile_loader
-> etl.transformer
-> catalogguard_ready.csv
-> rejected_rows.csv
-> etl_summary.json
-> 기존 validate_and_read_uploaded_csv()·inspect_dataframe()
```

표준 CSV를 DB에 적재하는 흐름은 파일 변환과 분리합니다.

```text
catalogguard_ready.csv + etl_summary.json
-> etl.load_cli
-> summary 필수 필드·output SHA-256·loaded_rows 검증
-> (input SHA-256, profile name, profile version) 중복 조회
-> etl_load_runs + catalog_products_staging 한 트랜잭션 저장
-> GET /api/v1/etl-loads로 배치 검색
-> GET /api/v1/etl-loads/{etl_load_run_id}로 배치별 상품 조회
-> Streamlit ETL 적재 이력 탭에서 목록·상세·페이지네이션 표시
-> 사용자가 batch 직접 선택
-> POST /api/v1/etl-loads/{etl_load_run_id}/promotion-preview
-> insert/update/unchanged·상품별 변경 전후·차단 사유 확인
-> 승인 checkbox와 preview hash 확인
-> POST /api/v1/etl-loads/{etl_load_run_id}/promotions
-> 운영 상품·promotion run·audit 저장
```

## 6.5 기술 스택과 검증 버전

| 항목 | 버전 또는 값 |
|---|---|
| Python | 3.11.15 |
| Streamlit | 1.58.0 |
| API | FastAPI, Uvicorn, Pydantic |
| pandas | 3.0.3 |
| 데이터베이스 | PostgreSQL, SQLAlchemy, psycopg |
| 마이그레이션 | Alembic |
| 비동기 처리 | Redis, Celery |
| 로컬 실행 | Docker Compose |
| pytest | 일반 unit·integration 9.1.1 / Chromium E2E 8.4.1 |
| CI | GitHub Actions `Test` workflow |
| CI 테스트 서비스 | PostgreSQL 18·Redis 7.4 서비스 컨테이너 |
| CI 검증 범위 | 일반 `test` job의 Alembic·pytest·비동기 E2E와 별도 `browser-e2e` job의 PostgreSQL·Chromium 실제 브라우저 ETL·promotion E2E |
| 필수 컬럼 | 9개 |
| 선택 컬럼 | 3개 (`sale_price` 포함) |
| 등록된 검수 규칙 함수 | 15개 |
| 샘플 CSV 상품 수 | 5개 |
| 샘플 CSV 검수 결과 | 오류 6건, 주의 0건 |
| ETL API client·UI 검증 | 응답 schema, nullable, request ID, stale 상태와 Streamlit AppTest 범위 |
| promotion preview·service·API·concurrency 검증 | preview hash, 승인, 차단·stale·failed, transaction, 중복 성공 방지와 audit |
| Chromium 브라우저 E2E | ETL reject 마스킹과 promotion 승인·반영, 브라우저 오류 및 PostgreSQL 최종 상태 |
| 샘플 ETL CLI 결과 | 전체 3건, 정상 변환 2건, 오류 행 1건, 종료 코드 0 |
| 최신 기준 CI | GitHub Actions run #55 success |
| 최신 CI Streamlit 시작 검사 | Health HTTP 200, body `ok` |

## 6.6 핵심 구현 구조

| 파일 | 역할 |
|---|---|
| `app.py` | 업로드 검증·마스킹 미리보기, 검수 화면, 검수 이력과 ETL 적재 이력 탭 연결 |
| `clients/catalogguard_api.py` | FastAPI 검수·ETL·promotion API 호출과 응답 schema·오류 mapping |
| `ui/etl_load_history.py` | ETL 목록·검색·페이지네이션·상세·promotion 승인 UI와 session state 관리 |
| `api/main.py`, `api/routes/` | FastAPI 앱, Health·readiness, 동기 검수·이력·비동기 작업 및 ETL 배치 조회 API |
| `api/routes/etl_loads.py`, `api/schemas.py` | ETL 조회와 promotion endpoint, 오류 처리와 Pydantic 응답 계약 |
| `config/settings.py` | 컬럼, 허용 카테고리, 업로드 제한, 금지어 설정 |
| `core/upload_validator.py` | CSV 업로드 사전 검증 |
| `core/loader.py` | DataFrame을 Product 객체로 변환 |
| `core/models.py` | Product, ValidationIssue 데이터 모델 |
| `core/rules.py` | 전체 검수 규칙 실행 |
| `core/privacy.py` | 개인정보 정규식, 마스킹, 미리보기 복사본 생성 |
| `core/presentation.py` | 검수 결과 한글화, 필터링, 화면용 DataFrame 생성과 통계 집계 |
| `core/result_exporter.py` | 결과 CSV 생성과 수식 삽입 방어 |
| `core/product_template.py` | 입력 템플릿 CSV 생성 |
| `core/duplicate_detector.py` | 상품 ID와 상품명 중복 탐지 |
| `core/price_anomaly_detector.py` | 카테고리별 가격 이상치 탐지 |
| `core/category_mismatch_detector.py` | 상품명 키워드 기반 카테고리 불일치 탐지 |
| `db/etl_query_service.py` | ETL 배치 필터·정렬·count와 배치별 상품 SQL 페이지네이션을 담당하는 읽기 전용 query service |
| `db/` | 검수 실행·상세 결과와 ETL staging 배치·상품의 PostgreSQL 모델, Repository, 저장 Service |
| `services/` | Redis 작업 상태 저장, 비동기 작업 파일 관리와 제출 Service |
| `workers/` | Celery 앱과 CSV 검수 Worker 작업 |
| `etl/` | JSON 프로필 로딩, 공급사 행 변환, reject 분리, 파일 변환 CLI와 PostgreSQL staging loader |

## 6.7 데이터 보호 설계

개인정보 미리보기 기능에서 가장 중요하게 본 점은 원본 데이터와 표시용 데이터를 분리하는 것이었습니다.

```text
validated_df
-> 원본 DataFrame
-> Product 변환과 검수 규칙 실행에 사용

masked_preview_df
-> validated_df.copy(deep=True)로 만든 복사본
-> Streamlit 미리보기 표에만 사용
```

마스킹 대상은 전화번호, 이메일, 주민등록번호 형태입니다.

```text
010-1234-5678 -> 010-****-5678
sample@test.com -> sa****@test.com
900101-1234567 -> 900101-*******
```

숫자형 업무 컬럼인 `product_group_id`, `product_id`, `stock`, `price`는 미리보기 마스킹 대상에서 제외했습니다. 이 결정은 상품 ID, 가격, 재고가 전화번호나 주민등록번호 형태로 잘못 가려지는 위험을 줄이기 위한 것입니다.

## 6.8 검수 규칙 설계

현재 검수 규칙은 `core/rules.py`의 `RULES` 리스트에 등록된 함수 순서대로 실행됩니다.

- 상품 ID 중복
- 상품명 중복 후보
- 완전 중복 상품
- 필수 값 누락
- 카테고리 오류
- 재고 오류와 품절 상품
- 가격 오류
- 카테고리별 가격 이상치
- 상품명과 카테고리 불일치
- 금지어와 개인정보 형태

규칙 실행 결과는 `ValidationIssue` 객체로 통일했습니다. 이 덕분에 어떤 규칙에서 발견된 문제든 `severity`, `product_id`, `product_group_id`, `message`라는 같은 형태로 화면과 CSV 다운로드에 전달할 수 있습니다.

## 6.9 CSV 검증과 템플릿

CSV 업로드는 `core/upload_validator.py`에서 사전에 검사합니다.

- CSV 확장자 검사
- 5MB 크기 제한
- UTF-8 BOM, UTF-8, CP949 인코딩 지원
- 빈 파일 차단
- 일반 텍스트가 아닌 파일 차단
- 빈 컬럼명 차단
- 중복 컬럼명 차단
- 필수 컬럼 누락 차단
- 행별 열 개수 불일치 차단
- 10,000행 초과 차단

입력 템플릿은 `core/product_template.py`에서 메모리상 CSV bytes로 생성합니다. 템플릿에는 실제 개인정보가 아닌 가짜 예시 상품 1개만 포함합니다.

## 6.10 결과 표시와 다운로드

검수 결과 화면은 사용자가 바로 조치할 수 있도록 한글 문장 중심으로 구성했습니다.

- 검수 상태
- 오류 항목
- 상품 그룹 ID
- 상품 ID
- 오류 이유
- 수정 권장사항
- 위험 수준

CSV 다운로드는 `core/result_exporter.py`에서 처리합니다. 다운로드 전 결과 DataFrame을 복사하고, Excel에서 수식으로 해석될 수 있는 문자열을 안전하게 바꾼 뒤 UTF-8 BOM CSV bytes로 변환합니다.

검수 통계에서는 필터 적용 전 전체 결과를 기준으로 다음 항목을 분석합니다.

- 오류 항목별 문제 건수
- 위험 수준별 문제 건수
- 문제가 많은 상품 TOP 5

CSV 검수 화면과 저장된 검수 이력 상세 화면은 같은 통계 UI를 재사용합니다. CSV 검수 화면에서 상세 결과 필터를 바꿔도 전체 통계는 유지되고, 상세 결과 표와 현재 필터 결과 CSV만 선택한 조건에 따라 달라집니다.

### 검수 이력 저장과 조회

FastAPI와 PostgreSQL이 함께 실행되는 로컬 또는 별도 배포 환경에서는 검수 결과를 PostgreSQL에 이력으로 저장할 수 있습니다. 검수 이력 화면에서는 파일명, 날짜 범위와 검수 상태로 저장된 실행을 검색하고 페이지 단위로 조회하며, 현재 검색 조건에 맞는 전체 이력 요약을 CSV로 내려받을 수 있습니다.

사용자는 저장된 실행을 검색하고 하나를 선택한 뒤 문제별 오류 이유와 수정 권장사항을 확인하고 상세 결과를 CSV로 내려받습니다. 상세 화면에서는 파일명, 검수 시간, 요약 수치와 문제별 위험 수준도 함께 확인할 수 있습니다.

![검수 이력 검색 및 목록 화면](images/04_history_list.png)

![검수 이력 상세 결과 화면](images/05_history_detail.png)

### 검수 결과 통계

아래 화면에는 검수 요약과 오류 항목별·위험 수준별·상품별 통계 3종이 표시됩니다. `가격 오류` 필터를 적용해 상세 결과는 3건만 보이지만, 통계는 필터 적용 전 전체 문제 6건을 기준으로 유지됩니다.

![검수 결과 통계 화면](images/06_inspection_statistics.png)

## 6.11 테스트 전략

테스트는 기능 단위로 분리했습니다.

| 테스트 파일 | 검증 대상 |
|---|---|
| `tests/test_upload_validator.py` | CSV 업로드 사전 검증 |
| `tests/test_loader.py` | CSV와 DataFrame 로딩 |
| `tests/test_rules.py` | 전체 검수 규칙 |
| `tests/test_duplicate_detector.py` | 중복 상품 탐지 |
| `tests/test_price_anomaly_detector.py` | 가격 이상치 탐지 |
| `tests/test_category_mismatch_detector.py` | 상품명과 카테고리 불일치 탐지 |
| `tests/test_privacy.py` | 개인정보 마스킹과 원본 보존 |
| `tests/test_presentation.py` | 결과 표시, 필터링, 한글 메시지, 통계 집계 |
| `tests/test_result_exporter.py` | 결과 CSV 다운로드 |
| `tests/test_product_template.py` | 입력 템플릿 |
| `tests/test_inspection_service.py` | 선택 `sale_price`와 정상가·할인가 관계 검수 |
| `tests/test_app_smoke.py` | AppTest 기반 초기 렌더링과 API 주소 누락 시 안전한 화면 처리 |
| `tests/test_database_connection.py` | PostgreSQL 연결과 테스트 DB 보호 조건 |
| `tests/test_database_models.py` | PostgreSQL 모델과 제약 조건 |
| `tests/test_inspection_persistence.py` | 검수 이력 저장·조회 통합 흐름 |
| `tests/test_api_etl_loads.py` | ETL 배치 목록·상세 HTTP 응답과 파라미터·404 계약 |
| `tests/test_etl_query_service.py` | 실제 PostgreSQL의 ETL 검색·정렬·페이지네이션·NULL·배치 격리 |
| `tests/test_catalogguard_api_client.py` | ETL client 파라미터·응답 shape·SHA-256·nullable·404/request ID 검증 |
| `tests/test_etl_load_history_ui.py` | ETL 순수 helper와 Streamlit AppTest 검증 |
| `tests/test_api_catalog_promotion_preview.py` | promotion preview endpoint와 응답·차단 조건 검증 |
| `tests/test_api_catalog_promotions.py` | 승인·hash·blocked/stale/failed 응답과 promotion endpoint 검증 |
| `tests/test_catalog_promotion_preview_service.py` | insert/update/unchanged, before/after와 preview hash 계산 검증 |
| `tests/test_catalog_promotion_service.py` | transaction upsert, run 상태와 append-only audit 검증 |
| `tests/test_catalog_promotion_concurrency.py` | 동시 promotion의 lock·중복 성공 방지·안전한 실패 검증 |
| `tests/e2e/test_etl_browser_e2e.py` | 실제 Chromium의 ETL 탭·검색·상세·promotion 승인·반영·reject 마스킹·브라우저 오류와 PostgreSQL 최종 상태 검증 |
| `scripts/run_etl_browser_e2e.py` | 테스트 DB migration, ETL CLI·Loader, FastAPI·Streamlit readiness, Playwright 실행과 cleanup |
| `tests/etl/` | 공급사 프로필 검증, 행 변환, 파일 교체, CLI와 기존 검수 흐름 호환성 |
| `tests/test_api_inspections.py` | ETL 출력과 연동되는 FastAPI CSV 검수·중복 결과 재사용·응답 계약 |
| `tests/test_api_inspection_jobs.py`, `tests/test_inspection_tasks.py` | 비동기 작업 API, Celery task 상태 전이와 임시 파일 정리 |

통계 집계 함수와 서버 응답 적용 helper에는 정렬, 빈 값 처리, 필수 컬럼 검증, 입력 불변성, TOP 5 적용 위치, malformed 응답 차단을 확인하는 테스트를 추가했습니다. 최신 기능은 GitHub Actions의 PostgreSQL 18 서비스에서 migration과 ETL staging 적재까지 실행해 다음 결과를 확인했습니다.

```text
기준 저장소의 GitHub Actions run #55: success
promotion preview·service·API·client·UI·concurrency 검증 파일 포함
Chromium promotion E2E: 실제 반영 후 PostgreSQL 최종 상태 확인
Streamlit startup smoke: `/_stcore/health` 범위는 workflow 결과로 확인
```

ETL 적재에서는 표준 CSV 2행을 최초 적재하고 같은 파일을 재실행해 `created=False`와 중복 상품 미생성을 확인했습니다. promotion에서는 합성 batch를 preview한 뒤 승인과 hash를 함께 보내 운영 상품 insert/update, `succeeded` run, audit 저장을 확인하고, 같은 batch의 두 번째 성공 요청은 기존 결과를 재사용하는지 확인했습니다. stale hash, 검수 오류·reject·중복 identity 차단, transaction rollback, malformed API 응답 거부와 Streamlit 상태 초기화도 검증했습니다. 모든 PostgreSQL 결과는 운영 DB가 아닌 테스트 환경의 결과입니다.

GitHub Actions CI에서는 `main` 브랜치 push 또는 `main` 대상 pull request마다 일회성 PostgreSQL 18·Redis 7.4 서비스 컨테이너를 시작합니다. 두 서비스는 workflow 실행 중에만 사용할 테스트용 구성으로 Railway나 운영 DB·Redis와 분리됩니다. 기준 저장소 상태의 run #55는 성공했으며, Alembic·pytest·FastAPI·Celery 비동기 E2E·Streamlit startup과 별도 Chromium promotion E2E의 세부 결과는 workflow 실행 로그를 기준으로 확인합니다.

```text
main push 또는 main 대상 pull request
-> GitHub Actions Test workflow
-> 일회성 PostgreSQL 18·Redis 7.4 서비스 컨테이너
-> Alembic upgrade head
-> E2E 제외 전체 pytest 1회 실행
-> Celery Worker·FastAPI 프로세스 시작
-> /health·/ready 확인
-> 비동기 CSV E2E: 신규 생성·상태 polling·결과 조회·동일 파일 재사용·임시 파일 정리
-> 실패 시 FastAPI·Celery 로그 출력, 성공·실패 모두 프로세스 정리
-> Streamlit 서버 시작
-> /_stcore/health 응답 확인
-> Streamlit 프로세스 종료
```

run #55의 성공 여부는 기준 작업 상태 확인 시점의 저장소 정보에 근거합니다. 실행별 테스트 수와 warning 세부 내역은 해당 workflow 로그를 확인하지 않은 상태에서는 문서에 추가하지 않습니다.

## 6.12 샘플 데이터 기준 결과

`data/dev/products_dev.csv`는 개발 중 기본 동작을 확인하기 위한 샘플입니다.

```text
전체 상품 수: 5
전체 문제 수: 6
오류 수: 6
주의 수: 0
```

이 샘플은 앱 화면에서 검수 요약, 결과 표, 필터, CSV 다운로드가 연결되어 있는지 확인하는 기준 데이터로 사용할 수 있습니다.

## 6.13 구현 중 해결한 문제

### 원본 데이터와 미리보기 데이터 분리

개인정보 마스킹을 적용할 때 원본 DataFrame을 직접 수정하면 실제 검수 결과도 마스킹된 값으로 바뀔 수 있습니다. 이를 막기 위해 `create_masked_preview()`는 `dataframe.copy(deep=True)`로 복사본을 만든 뒤 미리보기용 DataFrame에만 마스킹을 적용합니다.

### 숫자형 컬럼 오탐 방지

전화번호와 주민등록번호 형태는 숫자 패턴이 많기 때문에 가격, 재고, 상품 ID를 잘못 가릴 위험이 있습니다. 그래서 `product_group_id`, `product_id`, `stock`, `price` 컬럼은 미리보기 마스킹 대상에서 제외했습니다.

### 가격 오류와 가격 이상치 분리

0원, 음수, 숫자가 아닌 가격은 통계 계산에 넣으면 중앙값이 왜곡됩니다. 그래서 `check_price()`에서 가격 오류를 먼저 잡고, `core/price_anomaly_detector.py`에서는 양수 가격만 중앙값 계산에 사용하도록 분리했습니다.

### 같은 상품 그룹의 정상 옵션 처리

같은 상품명이라도 같은 그룹 안에서 색상이나 사이즈가 다른 상품은 정상 옵션일 수 있습니다. `core/duplicate_detector.py`는 같은 그룹의 다른 상품 ID이고 색상 또는 사이즈가 명확히 다르면 상품명 중복 후보에서 제외합니다.

### 다운로드 CSV 안전 처리

검수 결과를 CSV로 내려받을 때 셀이 `=`, `+`, `-`, `@`로 시작하면 Excel에서 수식처럼 해석될 수 있습니다. `core/result_exporter.py`는 다운로드용 복사본에서만 값을 안전하게 바꿔 원본 결과 DataFrame을 보존합니다.

### 필터와 독립된 통계와 공통 UI

상세 결과 필터를 통계에도 적용하면 전체 데이터의 문제 분포를 파악하기 어렵고, CSV 검수 화면과 이력 상세 화면에서 직접 집계하면 같은 기능이 중복될 수 있습니다. 이를 해결하기 위해 집계 로직을 입력 DataFrame을 변경하지 않는 순수 함수 `build_inspection_statistics()`로 분리하고, 공통 UI helper `render_inspection_statistics()`를 구현하였습니다.

```text
필터 전 전체 결과 result_df
-> build_inspection_statistics()
-> 오류 항목별 / 위험 수준별 / 상품별 집계
-> render_inspection_statistics()
-> CSV 검수 화면과 검수 이력 상세 화면에 공통 표시

필터 결과 filtered_result_df
-> 상세 결과 표와 현재 필터 결과 CSV에 사용
```

TOP 5 제한은 집계 함수가 아닌 UI에서 적용하였습니다. 통계 합계와 저장된 요약의 전체 문제 수가 다르면 표시를 중단하고, 통계 생성 예외 원문이나 API 응답 원문, DB 정보는 사용자 화면에 노출하지 않습니다. 그 결과 필터를 변경해도 전체 통계 수치는 유지되고 상세 표만 바뀝니다. 이 통계 기능 자체는 기존 검수 DB·API·Alembic 구조를 변경하지 않고 두 화면에서 재사용하였습니다.

### 동기 검수 성능 측정과 의사결정

동기 검수의 비용을 확인하기 위해 `scripts/benchmark_inspection.py`를 추가했습니다. 재현 가능한 합성 CSV를 행 수 100, 1,000, 5,000, 10,000으로 생성하고, 워밍업 1회·반복 3회의 중앙값과 `tracemalloc` Python peak를 측정했습니다.

측정 환경은 Python 3.11.9, Windows 10.0.26200, Intel Core i7-14700F 기반의 개발 PC입니다.

| 행 수 | 입력 크기 | 문제 수 | 1회 중앙값 | 연속 2회 중앙값 | Python peak |
|---:|---:|---:|---:|---:|---:|
| 100 | 0.016 MiB | 15 | 0.009544초 | 0.018815초 | 0.177 MiB |
| 1,000 | 0.156 MiB | 149 | 0.074266초 | 0.150817초 | 1.603 MiB |
| 5,000 | 0.781 MiB | 757 | 0.371740초 | 0.867245초 | 6.485 MiB |
| 10,000 | 1.563 MiB | 1,507 | 0.875495초 | 1.645721초 | 12.939 MiB |

시간과 Python 추적 메모리는 행 수에 따라 대체로 선형으로 증가했고, 같은 검수를 두 번 수행하면 1회 대비 약 1.88~2.33배가 걸렸습니다. 10,000행 1회 검수는 개발 PC에서 약 0.88초였지만, 이 결과는 AWS 인스턴스나 대규모 트래픽 성능을 보증하지 않습니다. DB·네트워크 시간과 실제 동시성은 제외했으며 `tracemalloc`은 Pandas/C 확장 및 OS 전체 프로세스 메모리를 포함하지 않을 수 있습니다.

이 측정으로 Streamlit과 FastAPI가 각각 전체 검수를 수행하는 구조보다 서버를 단일 검수 기준으로 두는 작업을 우선했습니다. 이후 긴 검수를 요청 수명과 분리할 수 있도록 Redis Job Store와 Celery Worker를 추가했고, Streamlit에서는 즉시 검수를 기본값으로 유지하면서 백그라운드 검수를 선택할 수 있게 연결했습니다. 백그라운드 상태는 무한 폴링 없이 사용자가 새로고침 버튼을 눌러 확인합니다.

### Streamlit·FastAPI 이중 검수 제거와 비동기 선택

기존 흐름은 Streamlit에서 업로드한 DataFrame을 먼저 전체 검수한 뒤 저장 시 FastAPI에 같은 파일을 다시 보내 서버가 다시 검수하는 구조였습니다. 최신 흐름은 다음과 같이 바꾸었습니다.

```text
Streamlit: 업로드 검증·마스킹 미리보기
-> 즉시 검수(기본): FastAPI POST /api/v1/inspections
-> 백그라운드 검수: FastAPI POST /api/v1/inspection-jobs
-> 상태 새로고침: GET /api/v1/inspection-jobs/{job_id}
-> 성공 시 FastAPI GET /api/v1/inspections/{inspection_run_id}
-> Streamlit이 상세 응답을 화면·통계·필터·다운로드에 재사용
```

따라서 전체 규칙은 요청당 서버에서 한 번만 실행됩니다. 즉시 검수는 POST 한 번과 상세 GET 한 번으로 동작하고, 백그라운드 검수는 작업 제출 뒤 명시적인 상태 GET으로 완료를 확인합니다. 완료된 두 흐름은 같은 상세 결과 렌더러를 사용합니다. 같은 세션에서는 업로드 bytes의 SHA-256과 활성 `job_id`로 불필요한 재제출을 막고, DB의 파일 해시·검수 버전 중복 제약은 세션 밖에서도 최종 방어선으로 유지합니다.

### 서버 응답 방어 검증

서버 상세 응답을 성공으로 간주하기 전에 실행 ID가 생성 응답과 일치하는지, `created`가 Boolean인지, 요약 수치가 음이 아닌 정수인지, 상세 결과 각 행에 필요한 문자열 필드가 있는지 검증합니다. 검증을 통과한 뒤에만 Streamlit 세션 상태와 화면 DataFrame을 갱신하므로 malformed 응답이 성공 결과로 캐시되는 경로를 차단했습니다.

### PostgreSQL 통합 테스트의 CI 자동화

로컬 개발 환경에서는 `TEST_DATABASE_URL`이 없으면 운영 DB 오연결을 막기 위해 PostgreSQL 통합 테스트를 건너뜁니다. 이 보호 조건을 완화하지 않고도 전체 통합 테스트를 반복 실행할 수 있도록 GitHub Actions와 별도 로컬 검증에서 PostgreSQL 테스트 환경만 사용했습니다.

기존 CI와 이번 작업의 migration chain은 `20260703_0001`, `20260705_0002`, `20260725_0003`, `20260727_0004`로 이어집니다. 격리된 PostgreSQL 18.4 테스트 클러스터에서 새 migration의 upgrade·downgrade·재upgrade, PostgreSQL 적재와 조회를 확인했습니다. 운영 DB 적재는 검증하지 않습니다.

### Streamlit 서버 시작 스모크 테스트

#### 문제

기존 CI는 함수, DB, API 테스트를 확인했지만 실제 Streamlit 서버가 시작되는지는 확인하지 못하였습니다. 모든 pytest가 통과해도 Streamlit 실행 프로세스가 시작 단계에서 종료되는 문제는 놓칠 수 있었습니다.

#### 해결 방법

기존 pytest Step 뒤에 Streamlit 시작 스모크 테스트를 추가하였습니다. Streamlit을 백그라운드에서 실행하고 `/_stcore/health`를 최대 30초 동안 반복 확인한 뒤, HTTP `200` 이후에도 프로세스가 살아 있는지 추가로 확인하였습니다. 성공과 실패 모두 cleanup 처리를 거쳐 프로세스를 종료하고, 실패 시에는 실행 로그와 마지막 HTTP 결과를 출력하도록 하였습니다.

이 검사에서는 `CATALOGGUARD_API_BASE_URL`, `CATALOGGUARD_API_TIMEOUT_SECONDS`, `DATABASE_URL`, `TEST_DATABASE_URL`을 빈 값으로 덮어써 Railway 운영 API와 운영 PostgreSQL 접근을 차단하였습니다. 따라서 운영 데이터나 검수 이력을 읽거나 저장하지 않고 Streamlit 서버 자체의 시작 가능 여부만 확인합니다.

#### 설계 판단

별도 스크립트 파일을 추가하지 않고 기존 Workflow의 Bash Step으로 구현하였습니다. 단순한 고정 대기 대신 최대 30초 동안 반복 요청해 준비 시간이 달라지는 상황에 대응하고, 실패 원인을 확인할 수 있도록 로그를 남겼습니다. 또한 AppTest 기반 초기 화면 검사와 실제 서버 프로세스·포트·Health 검사를 분리해 검증 범위를 보완하였습니다.

#### 결과

최신 CI에서 PostgreSQL 마이그레이션과 Streamlit 서버 시작 스모크 테스트가 성공했으며, Health HTTP `200`과 `ok` 응답을 반환하였습니다. Actions의 테스트 개수와 실행 시간은 해당 workflow 상세 결과를 기준으로 확인합니다.

이 검사는 Streamlit 실행 명령과 서버 Health endpoint를 확인하는 시작 단계 검사입니다. 브라우저 기능 전체나 CSV 검수 흐름, 운영 배포 환경을 자동으로 검증한다는 의미는 아닙니다.

### Catalog promotion E2E와 동시성에서 해결한 문제

promotion 기능을 붙이면서 단순히 브라우저에 성공 문구가 나타나는지만 확인하지 않고, 다음 문제를 실제 원인·수정·재발 방지 기준으로 정리했습니다.

1. **문제:** batch 자동 선택을 제거한 뒤 기존 E2E가 선택 없이 상세 조회를 시도했습니다.
   - **실제 원인:** UI가 사용자의 명시적 batch 선택을 요구하도록 바뀌었지만 테스트 흐름은 이전 자동 선택 가정에 남아 있었습니다.
   - **수정 방법:** 파일명·프로필명으로 batch를 검색한 뒤 `적재 배치 선택` combobox에서 option을 직접 선택하도록 시나리오를 수정했습니다.
   - **재발 방지 기준:** promotion E2E는 preview 전에 선택된 batch의 `aria-label`이 검색한 파일명과 일치하는지 확인합니다.
2. **문제:** Streamlit combobox에서 보이는 option text가 아니라 내부 text를 기준으로 선택하면 실제 선택이 검증되지 않았습니다.
   - **실제 원인:** Streamlit이 선택값을 접근성 이름인 `aria-label`로 렌더링하는 경우가 있어 내부 DOM text와 사용자에게 보이는 선택값이 달랐습니다.
   - **수정 방법:** role·label 기반 selector로 option을 선택하고 combobox의 `aria-label`을 검증했습니다.
   - **재발 방지 기준:** `nth-child`나 내부 CSS 구조가 아니라 role·label·aria-label 같은 사용자 관점 selector를 사용합니다.
3. **문제:** 숨겨진 checkbox input에 `.check()`를 호출하면 timeout이 발생했습니다.
   - **실제 원인:** Streamlit checkbox는 실제 input과 보이는 label이 분리되어 렌더링될 수 있습니다.
   - **수정 방법:** 보이는 승인 label을 클릭한 뒤 checkbox가 checked인지 확인하도록 바꿨습니다.
   - **재발 방지 기준:** 접근성 이름을 가진 사용자 노출 요소를 조작하고, 클릭 후 상태까지 검증합니다.
4. **문제:** 브라우저에서 성공 메시지가 보여도 DB 반영이나 `applying` 잔존 여부를 알 수 없었습니다.
   - **실제 원인:** UI assertion만으로는 transaction commit, audit 저장, 경쟁 요청 결과를 확인할 수 없습니다.
   - **수정 방법:** E2E 종료 후 API와 SQLAlchemy로 succeeded run 1건, 운영 상품, audit, `applying` 0건을 PostgreSQL에서 직접 확인했습니다.
   - **재발 방지 기준:** promotion E2E의 완료 조건은 브라우저 메시지와 PostgreSQL 최종 상태를 모두 만족해야 합니다.

## 6.14 면접 예상 질문과 답변

### Q1. 왜 Streamlit을 사용했나요?

CSV 업로드, 표 표시, 요약 지표, 다운로드 버튼을 빠르게 구현할 수 있고 Python 데이터 처리 코드와 자연스럽게 연결되기 때문입니다. 이 프로젝트의 목적은 복잡한 프론트엔드보다 검수 로직과 사용자 흐름 검증에 가까웠습니다.

### Q2. 왜 원본 DataFrame을 직접 마스킹하지 않았나요?

미리보기 보안과 검수 정확도는 서로 다른 요구사항입니다. 원본을 마스킹하면 검수 규칙이 실제 입력값을 보지 못할 수 있으므로, 원본은 검수에 쓰고 복사본만 화면 표시용으로 사용했습니다.

### Q3. 개인정보 탐지는 완벽한가요?

아닙니다. 현재는 정규식 기반이므로 오탐과 미탐 가능성이 있습니다. 다만 MVP 단계에서는 전화번호, 이메일, 주민등록번호 형태처럼 명확한 패턴을 우선 처리하고, 테스트로 원본 보존과 문장 내부 마스킹을 검증했습니다.

### Q4. 가격 이상치는 어떤 기준인가요?

같은 카테고리의 유효 가격이 5개 이상일 때 중앙값을 계산합니다. 현재 가격이 중앙값의 0.25배보다 낮거나 4배보다 높으면 주의 항목으로 표시합니다.

### Q5. 상품명 중복과 완전 중복의 차이는 무엇인가요?

상품명 중복은 정규화된 상품명이 같은 후보를 찾는 규칙이고, 완전 중복은 상품명, 카테고리, 색상, 사이즈, 가격까지 모두 같은 상품을 찾는 규칙입니다. 완전 중복은 더 강한 근거가 있으므로 오류로 봅니다.

### Q6. 업로드 검증을 검수 규칙과 분리한 이유는 무엇인가요?

파일 형식 문제와 상품 데이터 품질 문제는 성격이 다릅니다. 파일을 읽을 수 없거나 필수 컬럼이 없으면 Product 객체를 만들 수 없으므로, 검수 규칙 실행 전에 `upload_validator`에서 먼저 차단했습니다.

### Q7. 결과 메시지를 왜 별도 파일에서 한글화했나요?

검수 규칙은 내부적으로 안정적인 rule 이름과 message를 만들고, 화면 표시용 문장은 `core/presentation.py`에서 변환합니다. 이렇게 하면 규칙 로직과 사용자 표시 문구를 독립적으로 관리할 수 있습니다.

### Q8. 테스트는 어떤 기준으로 나눴나요?

파일 업로드, 로딩, 규칙, 개인정보, 결과 표시, 다운로드, 템플릿처럼 책임 단위로 나눴습니다. 기능이 늘어날 때 어느 영역이 깨졌는지 빠르게 찾기 위한 구조입니다.

### Q9. 결과 CSV에서 수식 삽입을 고려한 이유는 무엇인가요?

운영자는 결과 CSV를 Excel에서 열 가능성이 높습니다. CSV 셀이 수식으로 해석되면 의도하지 않은 동작이 생길 수 있어 다운로드용 데이터에서 수식 접두 문자를 안전하게 처리했습니다.

### Q10. 데이터베이스 테스트를 어떻게 자동화했나요?

`main` push와 `main` 대상 pull request에서 GitHub Actions가 일회성 PostgreSQL 18·Redis 7.4 서비스 컨테이너를 시작하도록 구성했습니다. `DATABASE_URL`과 `TEST_DATABASE_URL`은 CI 테스트 DB만 가리키고, Celery Broker와 Job Store는 각각 Redis DB 0·1을 사용합니다. Alembic 마이그레이션 뒤 E2E를 제외한 pytest를 실행하고, FastAPI·Celery Worker를 실제 프로세스로 시작해 비동기 CSV E2E를 별도 실행합니다. 따라서 로컬에서 테스트 DB가 없어 skipped되는 PostgreSQL 통합 테스트 25개도 CI에서는 실행되며, 운영 DB·Redis와 분리됩니다.

### Q11. 이 프로젝트의 다음 개선점은 무엇인가요?

실제 운영 데이터가 충분하다면 카테고리별 가격 기준을 설정 파일로 분리하고, 개인정보 탐지 패턴을 운영 정책에 맞게 확장하며, 저장된 검수 이력의 삭제와 보관 정책을 추가할 수 있습니다.

### Q12. 왜 preview와 실제 promotion을 분리했나요?

ETL staging과 운영 상품은 책임과 위험이 다르기 때문입니다. preview에서 insert/update/unchanged와 변경 전후를 보여 주고 사용자가 승인한 뒤에만 실제 transaction을 실행하면, 반영 대상과 차단 사유를 확인한 다음 운영 데이터를 변경할 수 있습니다.

### Q13. preview hash는 어떤 문제를 막나요?

preview 이후 staging이나 현재 운영 상품이 바뀌었는데 오래된 화면의 승인으로 반영되는 stale preview를 막습니다. hash는 canonical preview 데이터의 SHA-256 비교값이며, 보안 토큰이나 원본 복원 수단은 아닙니다.

### Q14. 성공 메시지만 아니라 DB 상태까지 확인한 이유는 무엇인가요?

브라우저 메시지는 HTTP 흐름과 화면 렌더링만 증명합니다. 실제 promotion의 완료 조건은 운영 상품 insert/update, succeeded run, append-only audit이 저장되고 applying 상태가 남지 않는 것이므로 PostgreSQL 최종 상태를 함께 확인해야 합니다.

## 6.15 포트폴리오 소개 문구

### 이력서용 짧은 설명

Python·FastAPI와 PostgreSQL을 기반으로 CSV 상품 데이터의 필수 값, 형식, 카테고리, 재고, 가격, 중복 상품과 개인정보 포함 여부를 자동 검수하고, Redis·Celery 백그라운드 작업과 공급사 CSV ETL까지 연결한 데이터 품질 서비스를 구현했습니다.

### 포트폴리오용 설명

CatalogGuard Lite는 상품 운영자가 CSV 상품 데이터를 검수하고, ETL staging 결과를 확인한 뒤 운영 상품에 안전하게 반영할 수 있도록 만든 품질 검사 앱입니다. 업로드 검증, 원본 보존형 개인정보 마스킹 미리보기, 중복 상품 탐지, 가격 이상치 탐지, 정상가·할인가 관계 검수, 상품명과 카테고리 불일치 탐지, 필터와 독립된 전체 결과 통계, 결과 필터링, CSV 다운로드를 제공합니다. 합성 공급사 CSV를 JSON 프로필로 표준화하고 PostgreSQL staging에 배치 적재한 뒤, Streamlit에서 사용자가 batch를 직접 선택해 promotion preview를 실행합니다. preview는 insert/update/unchanged와 상품별 변경 전후를 보여 주고, 명시적 승인과 SHA-256 preview hash 재검증을 통과한 경우에만 FastAPI transaction이 운영 상품을 insert/update하며 promotion run과 append-only audit을 저장합니다. Playwright Chromium E2E는 승인 전 버튼 상태와 실제 UI 선택을 확인한 뒤 브라우저 성공 메시지뿐 아니라 PostgreSQL 최종 상태까지 검증했습니다. 이 검증은 합성 공급사 fixture와 테스트 PostgreSQL 환경에서 수행했으며, 실제 외부 공급사 운영 데이터나 production catalog에 반영한 것은 아닙니다. 공개 Streamlit 앱의 배포 기능 범위는 로컬 전체 시스템과 다를 수 있습니다.

### 면접에서 강조할 포인트

- 원본 데이터와 표시용 데이터를 분리해 개인정보 노출 위험과 검수 정확도를 함께 관리했습니다.
- CSV 업로드 검증, 규칙 실행, 결과 표시, 다운로드를 책임별 모듈로 나눴습니다.
- 정규식 기반 탐지의 한계를 인정하고, 숫자형 컬럼 오탐 방지와 원본 보존 테스트를 추가했습니다.
- 운영자가 이해할 수 있도록 내부 오류를 한글 메시지와 수정 권장사항으로 바꿨습니다.
- 일회성 PostgreSQL 18·Redis 7.4 테스트 서비스에 Alembic 마이그레이션을 적용하고, E2E 제외 pytest와 FastAPI·Celery 비동기 E2E를 분리해 운영 DB·Redis와 격리된 검증 흐름을 구성했습니다.
- 비동기 E2E 뒤에 운영 서비스와 분리된 Streamlit 시작 검사를 실행해 실제 서버 프로세스와 Health 응답까지 검증 범위를 보완했습니다.

## 6.16 PostgreSQL 쿼리·인덱스 성능 검증

검수 실행 10,000건과 상세 결과 100,000건의 합성 데이터를 격리 PostgreSQL 18 DB에 생성한 뒤 동일 CSV, 이력 목록·count, 상세 조회를 `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`으로 측정했습니다. 기존 partial unique 복합 인덱스와 PK·외래 키 조회 인덱스가 실제 planner에 선택되었고, 목록용 복합 인덱스 후보는 절대 0.022ms 차이에 그쳤으며 상세용 후보는 사용되지 않고 크기만 증가했습니다. 따라서 보여주기식 migration은 추가하지 않고 opt-in 성능 테스트와 상세 조회 SELECT 2회 회귀 테스트를 추가했습니다.

측정 환경, 실행 계획, buffer, 인덱스 크기, 재현 명령과 한계는 [SQL 쿼리·인덱스 성능 분석](sql_performance_analysis.md)에 기록했습니다.

## 6.17 공급사 상품 CSV ETL MVP

서로 다른 공급사 컬럼명을 CatalogGuard 표준 스키마로 변환하는 설정 기반 ETL MVP를 구현했습니다. 합성 공급사 프로필 2종으로 `discount_price` 또는 `promo_price`를 `sale_price`에 연결하고, 상품 그룹 ID와 개별 SKU가 분리된 구조까지 공통 흐름에서 처리했습니다. 가격·재고 형식을 안전하게 변환했으며, 변환할 수 없는 행은 오류 코드와 사용자용 메시지를 포함한 별도 CSV로 분리했습니다. 정상가보다 큰 할인가처럼 변환은 가능한 상품 품질 문제는 reject하지 않고 `inspect_dataframe()`에서 검수합니다. 변환 결과를 실제 기존 업로드 검증과 `inspect_dataframe()`에 전달하는 통합 테스트로 호환성을 확인했습니다. 상세한 프로필 형식, reject 기준, CLI와 제한사항은 [ETL MVP 문서](etl_mvp.md)에 기록했습니다.

### PostgreSQL staging 적재 설계

#### 문제

기존 ETL은 표준 CSV, reject CSV, summary JSON을 파일로 생성했지만, 정상 상품 행을 DB에서 배치 단위로 확인하는 Load 단계는 없었습니다. 파일 변환과 DB 적재를 한 CLI에 섞으면 변환 실패와 적재 실패의 책임 경계가 흐려지므로 별도 loader를 두었습니다.

#### 구현

`etl.load_cli`는 표준 CSV bytes, 선택적 reject CSV bytes와 summary JSON을 읽고 기존 `validate_and_read_uploaded_csv()`를 재사용합니다. summary의 `profile_name`, `profile_version`, `input_filename`, 입력·출력·reject CSV SHA-256, `total_rows`, `loaded_rows`, `rejected_rows`, `error_counts`를 확인한 뒤 실제 파일 해시와 행 수를 비교하고 reject CSV의 오류 배열·동적 원본 컬럼·마스킹 결과를 검증합니다. 정상 상품 행은 `catalog_products_staging`에, reject 행은 구조화된 오류 배열과 개인정보가 마스킹된 동적 원본 JSONB로 `etl_rejected_rows`에 저장하며 빈 `sale_price`는 `NULL`로 변환합니다. 행 수는 `total_rows = loaded_rows + rejected_rows`를 만족해야 하고, 한 행에 여러 오류 코드가 있을 수 있으므로 오류 건수 합계는 reject 행 수 이상이면 허용합니다.

`etl_load_runs`는 ETL 배치 메타데이터와 품질 요약을, `catalog_products_staging`은 해당 배치의 정상 상품 행을, `etl_rejected_rows`는 reject 행의 오류·마스킹 원본을 저장합니다. 품질 요약은 `total_rows`·`rejected_rows` INTEGER와 `error_counts` JSONB로 저장하며, 기능 도입 전 배치는 세 값을 `NULL`로 유지하고 reject 상세도 자동 backfill하지 않습니다. 배치·정상 상품·reject 행은 하나의 트랜잭션으로 저장해 일부만 남지 않게 합니다. 사용자용 배치 삭제 API와 staging 상품 직접 수정 API는 없으며, 운영 반영은 별도의 promotion API가 담당합니다.

#### 중복과 rollback 판단

`(input_file_sha256, profile_name, profile_version)`을 원본·프로필 identity로 사용했습니다. 이 조합의 배치가 있으면 기존 배치 ID와 `created=False`를 반환하고 상품·reject 행을 추가하지 않습니다. 프로필 버전이 다르면 별도 배치로 저장합니다. 신규 배치·정상 상품 행·reject 행은 한 트랜잭션에 넣어 저장 중 예외가 나면 배치와 두 자식 테이블을 함께 rollback합니다. 부모 배치 삭제 시 `ON DELETE CASCADE`로 상품·reject 행도 삭제되며, `stock`, `price`, `sale_price` 음수는 DB CHECK constraint로 거부됩니다.

#### 실행과 검증

```powershell
python -m etl.load_cli `
  --input .\output\catalogguard_ready.csv `
  --rejects .\output\rejected_rows.csv `
  --summary .\output\etl_summary.json
```

실행 예시는 다음과 같습니다.

```text
DB 적재 완료
적재 배치 ID: 1
신규 적재: yes
전체 행: 2
정상 상품 행: 2
거부 행: 0
```

같은 파일의 두 번째 실행은 같은 배치 ID, `신규 적재: no`, 품질 요약과 상품 행을 중복 생성하지 않으며 저장된 품질 정보를 그대로 반환합니다. 격리된 PostgreSQL 18.4 테스트 클러스터에서 배치 품질 값과 staging 상품 2건을 확인했습니다.

#### 범위와 한계

실제 외부 공급사 운영 데이터, 운영 DB 적재, 증분 ETL과 streaming은 검증하지 않았습니다. ETL 적재 실행용 웹 API, staging 상품 수정·삭제, 상품 변경 이력 조회 API와 자동 공급사 감지는 지원하지 않습니다. 운영 상품 promotion은 합성 공급사 fixture와 테스트 PostgreSQL 환경에서만 검증했으며, production catalog 반영이나 공개 Streamlit 앱의 배포 범위까지 보증하지 않습니다. reject 행은 `etl_rejected_rows`에 마스킹된 원본과 구조화된 오류로 저장합니다. Streamlit 적재 이력 화면의 조회는 읽기 전용이고, promotion은 선택한 batch에 대해 FastAPI POST API를 호출합니다.

### 운영 상품 promotion persistence

#### 문제

ETL staging 행은 변환·검증 결과를 보관하는 중간 데이터이므로 운영 카탈로그와 같은 identity나 삭제 정책을 사용할 수 없었습니다. 같은 외부 상품 ID가 공급사마다 충돌할 수 있고, 동일 ETL batch의 성공 반영은 한 번만 허용하면서 실패·차단 시도는 감사 목적으로 남겨야 했습니다.

#### 해결

`catalog_products`를 staging과 분리하고 `(supplier_key, external_product_id)`를 운영 상품 identity로 고정했습니다. `supplier_key`는 ETL batch의 `profile_name`, `external_product_id`는 staging의 `product_id`에 대응합니다. `product_id` 단독 unique나 `profile_version`을 identity에 포함하지 않았습니다.

`catalog_promotion_preview_service.py`는 staging 상품과 현재 운영 상품을 비교해 `insert`·`update`·`unchanged`와 상품별 before/after를 만들고, inspection 오류·reject·중복 identity·품질 summary 누락을 차단 사유로 반환합니다. canonical JSON의 SHA-256 `preview_hash`를 preview와 실제 반영 시점에 재계산해 stale preview를 차단합니다. 이 hash는 암호화나 인증 토큰이 아니라 두 시점의 데이터가 같은지 확인하는 비교값입니다.

`catalog_promotion_service.py`는 `confirmation=true`와 `expected_preview_hash`를 요구하고, batch·staging·운영 상품을 잠근 하나의 transaction 안에서 preview를 재검증합니다. hash가 일치하면 `catalog_products`에 insert/update하고 `catalog_promotion_runs`를 `applying`에서 `succeeded`로 완료합니다. 조건 불충족은 `blocked`, hash 불일치는 `preview_stale`, 예외는 rollback과 안전한 `failed` run으로 기록합니다.

`catalog_promotion_runs`는 `applying`·`succeeded`·`failed`·`blocked` 상태와 insert/update/unchanged/blocked/error/warning count, preview 메타데이터와 안전한 실패 정보를 저장합니다. 같은 `etl_load_run_id`의 `succeeded` 행만 PostgreSQL partial unique index로 한 건을 허용해 성공 반영 중복을 막고, `failed`·`blocked` 재시도 기록은 허용합니다. `catalog_product_changes`는 `insert`·`update`만 기록하는 append-only JSONB audit 모델이며, before/after와 changed fields를 저장합니다.

#### 검증과 범위

Alembic revision `20260728_0006`에서 `catalog_products` → `catalog_promotion_runs` → `catalog_product_changes` 순서의 upgrade와 역순 downgrade를 구성했습니다. 격리된 PostgreSQL 18에서 빈 DB upgrade, `0005` downgrade, 재-upgrade, 단일 head를 확인하고 promotion PostgreSQL 테스트로 복합 unique·partial index·JSONB shape·action 규칙·FK RESTRICT를 검증했습니다.

promotion run·audit 조회 전용 API와 운영 배포 migration 적용은 별도 범위입니다. 현재 검증은 preview API, 승인 promotion API, Streamlit 승인 UI, transaction upsert, 동시성 차단과 Chromium E2E에 집중하며, 실제 외부 운영 catalog에는 반영하지 않았습니다.

### ETL 적재 배치 조회 API

#### 문제

PostgreSQL staging에 상품을 저장할 수 있었지만, 어떤 공급사 파일이 언제 적재되었는지 외부에서 확인할 API가 없었습니다. 프로필별 적재 이력을 검색하거나 특정 배치의 상품을 확인할 수 없어 추후 Streamlit 관리 화면을 연결할 명확한 조회 계약도 부족했습니다.

#### 해결

`GET /api/v1/etl-loads`는 파일명과 프로필명의 대소문자 구분 없는 부분 검색, `limit`·`offset` 페이지네이션, 최신 적재 우선 정렬과 전체·정상·거부 행 수를 제공합니다. 두 검색 조건은 AND로 적용하며 목록과 `total`이 같은 필터를 사용합니다. `GET /api/v1/etl-loads/{etl_load_run_id}`는 여기에 오류 코드별 건수, reject 상세 저장 여부, input/output SHA-256, 해당 배치의 staging 상품을 `product_limit`·`product_offset`으로 반환하고 없는 배치는 HTTP 404로 처리합니다. `GET /api/v1/etl-loads/{etl_load_run_id}/rejections`는 구조화된 오류와 마스킹된 원본을 페이지 단위로 반환하며, 과거 미저장 배치는 빈 목록으로 표시합니다.

#### 기술적 판단

- 목록에는 긴 SHA-256과 상품 전체를 제외해 이력 탐색 응답의 크기를 줄이고, 상세 요청에서만 해시와 상품을 제공합니다.
- 상품 전체를 메모리에 올린 뒤 자르지 않고 SQL `LIMIT`·`OFFSET`과 staging 행 기본 키 `id` 오름차순을 적용합니다.
- 목록과 count가 어긋나지 않도록 같은 필터 함수를 재사용하고, 모든 상품 쿼리에 배치 ID를 적용합니다.
- SQLAlchemy ORM 객체를 직접 반환하지 않고 읽기 전용 query service의 dataclass와 API의 Pydantic 모델로 응답 계약을 고정합니다.
- `%`, `_`, `\`는 SQL LIKE wildcard가 아니라 실제 문자로 검색되도록 escape합니다.
- 조회 함수는 relationship 전체 lazy loading, 상품별 추가 SELECT, `commit`과 `rollback`을 사용하지 않습니다.

#### 검증

PostgreSQL 테스트 클러스터에서 정렬, 파일명·프로필명 검색과 AND 조건, 대소문자 무시, LIKE 특수문자, 목록·count 일치, 상품 페이지네이션과 배치 격리, nullable 값, reject 상세 페이지네이션, 마스킹 원본, 없는 배치를 확인했습니다. promotion 관련 PostgreSQL 테스트에서는 transaction, partial unique index, before/after audit, stale·동시 요청 결과를 확인했으며, 전체 실행 수는 workflow별 로그를 기준으로 관리합니다.

### Streamlit ETL 적재 이력 화면

Streamlit의 `ETL 적재 이력` 탭은 `CatalogGuardApiClient`를 통해 목록·상세 조회 API와 promotion POST API를 호출합니다. ETL 실행과 staging 수정·삭제는 수행하지 않지만, 사용자가 선택한 batch의 preview·승인·운영 상품 반영은 이 화면에서 요청할 수 있습니다.

| 기능 | 구현 범위 |
|---|---|
| 목록 | 10건 단위 페이지네이션, 전체 건수, 빈 목록 안내 |
| 검색 | filename·profile_name 부분 검색과 두 조건 AND |
| 상세 | 배치 메타데이터, 전체·정상·거부 행, 정상 처리율, 오류 코드 통계, input/output SHA-256 전체 값, 적재 시각, reject 상세와 마스킹된 원본 |
| 상품 | 선택한 배치의 staging 상품 20건 단위 페이지네이션 |
| promotion | 선택한 batch의 insert/update/unchanged, 변경 전후, 반영 가능 여부와 차단 사유 표시 |
| 승인 | 승인 checkbox와 preview hash가 모두 유효할 때만 운영 반영 버튼 활성화 |
| nullable | `sale_price`, `description`, `seller`의 `null` 안전 표시 |
| 오류 | 404와 유효한 request ID 표시 |
| 상태 | 검색·배치 변경 시 stale 상세·상품·reject 제거, 실패 상세 요청 중복 호출 방지 |

순수 helper 테스트와 Streamlit AppTest로 목록·검색·빈 결과·페이지 이동·상세·SHA-256·reject 상세·마스킹 원본·nullable·404·request ID·promotion preview·승인·stale 상태 초기화를 검증했습니다. 실제 브라우저 전체 상호작용은 아래 별도 Chromium E2E에서 검증하며, GitHub Actions의 Streamlit startup smoke는 서버 startup과 `/_stcore/health` HTTP 200을 확인합니다.

### 실제 Chromium ETL 브라우저 E2E

계층별 pytest와 Streamlit AppTest만으로는 실제 접근성 이름, rerun 이후 상태, 동적 표·expander 렌더링, 승인 checkbox 동작과 HTML 내부 raw 민감정보 노출을 확인할 수 없었습니다. 전용 `requirements-e2e.txt`와 ETL·promotion 합성 fixture를 사용하고, `scripts/run_etl_browser_e2e.py`가 테스트 PostgreSQL migration, `etl.cli`, `etl.load_cli`, FastAPI, Streamlit, readiness 대기와 Playwright pytest를 한 번에 관리하도록 구성했습니다.

브라우저 시나리오는 reject fixture에서 ETL 검색·상세·마스킹을 확인하고, promotion fixture에서 파일명·프로필명 검색, batch combobox의 실제 선택, preview, 상품별 변경 전후, 승인 전 반영 버튼 disabled, 승인 checkbox, 실제 promotion과 성공·중복 메시지를 확인한다. promotion 종료 후에는 PostgreSQL에서 succeeded run 1건, 운영 상품 insert/update, audit 존재, applying 0건을 직접 조회한다. reject 원본 expander의 네 가지 원문은 body text와 HTML에 없음을 확인하고, 두 시나리오 모두 console error·page error 0건을 요구한다.

로컬 Chromium 실행은 `python scripts/run_etl_browser_e2e.py`로 수행하며 `DATABASE_URL`은 loopback 테스트 PostgreSQL만 허용한다. 실패 시 screenshot·HTML·FastAPI·Streamlit·Playwright 로그를 `artifacts/browser-e2e/`에 보존하고 runner가 시작한 프로세스와 임시 파일을 정리한다. GitHub Actions에는 기존 Redis 기반 일반 테스트와 분리된 PostgreSQL·Chromium `browser-e2e` job을 추가했으며, 실패 artifact만 업로드하도록 구성했다. 운영 DB·실제 공급사·모바일 브라우저는 범위에서 제외했다.

### 두 번째 합성 공급사로 검증한 확장성

#### 문제

첫 번째 프로필만으로는 ETL이 `vendor_sku` 컬럼 구조에 묶여 있지 않은지 증명하기 어려웠다.

#### 해결

`style_id`와 `sku_code`가 분리된 두 번째 합성 공급사 프로필 `config/etl/sample_marketplace_vendor_v1.json`과 `tests/fixtures/etl/sample_marketplace_vendor_mixed.csv`를 추가했다.

#### 결과

`etl/profile_loader.py`, `etl/transformer.py`, `etl/pipeline.py`를 수정하지 않고 JSON 매핑 프로필과 fixture, Repository 통합 테스트만으로 3행 중 2행을 변환하고 1행을 reject했다. 같은 `STYLE-100` 그룹 아래 서로 다른 SKU를 유지했으며, 정상가보다 큰 할인가 관계는 기존 CatalogGuard 검수 결과로 연결했다.

#### 의미

공급사별 데이터 구조 차이를 공급사명 조건문이나 전용 transformer가 아니라 설정 데이터로 분리하는 설계를 검증했다. 상품 그룹 ID와 개별 SKU가 별도 컬럼인 구조도 동일한 공통 ETL 흐름으로 처리할 수 있음을 확인했다.

### ETL 설계 판단

- 공급사별 Python 변환 코드를 따로 만들면 컬럼 변경 때마다 배포가 필요하므로, 허용된 표준 컬럼만 가리키는 JSON 프로필로 매핑을 분리했습니다. 프로필은 단순 데이터로만 해석하고 동적 코드는 실행하지 않습니다.
- 가격·재고 파싱 실패는 상품 품질 규칙의 오류와 성격이 다르므로 `rejected_rows.csv`로 분리하고, 정상 행만 기존 CatalogGuard 검수기에 전달합니다.
- 입력·프로필을 보호하고 출력 세 파일의 일관성을 유지하기 위해 임시 파일을 같은 디렉터리에 쓴 뒤 `os.replace()`로 교체합니다. 기존 출력이 있다면 백업 후 교체하고, 중간 실패 시 기존 파일을 복구합니다.
- `etl_summary.json`에는 입력·출력 SHA-256과 처리 건수를 남겨 변환 결과를 추적할 수 있게 했으며, 생성된 표준 CSV는 기존 `validate_and_read_uploaded_csv()`와 `inspect_dataframe()`에 연결해 호환성을 확인했습니다.
