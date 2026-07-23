<!-- 역할: CatalogGuard Lite 프로젝트의 기능, 실행 방법, 구조를 설명하는 메인 문서입니다. -->

# CatalogGuard Lite

상품 카탈로그 CSV를 업로드해 누락, 형식 오류, 중복, 가격 이상치, 카테고리 불일치, 금지어와 개인정보 의심 정보를 검사하고, 검수 결과를 저장·검색·조회·다운로드하는 Python·FastAPI + PostgreSQL 기반 MVP입니다. Streamlit은 업로드 검증과 결과 화면을 담당하며, Redis·Celery 백그라운드 검수와 JSON 프로필 기반 공급사 CSV ETL도 제공합니다.

공개 Streamlit 앱은 아래 주소에서 확인할 수 있습니다.

https://catalogguard-lite-p6jtwmdhwqcapphpghfzduo.streamlit.app/

> 공개 Streamlit 앱과 로컬 전체 시스템의 기능 범위는 다를 수 있습니다. PostgreSQL 저장, 검수 이력 검색, 검수 이력 상세 조회 기능은 로컬 또는 별도 배포 환경에서 FastAPI 서버와 PostgreSQL이 함께 실행되어야 사용할 수 있습니다.

프로젝트의 설계·검증 과정은 [포트폴리오 상세 문서](docs/portfolio_project.md), 공급사 변환 흐름은 [ETL MVP 문서](docs/etl_mvp.md), PostgreSQL 쿼리 검증은 [SQL 성능 분석 문서](docs/sql_performance_analysis.md)에서 확인할 수 있습니다.

## 2. 프로젝트 목적

CatalogGuard Lite는 상품 운영자가 CSV로 관리하는 상품 목록을 업로드한 뒤, 등록 전에 발견해야 할 데이터 품질 문제를 빠르게 확인하도록 만든 경량 검수 도구입니다.

주요 목표는 다음과 같습니다.

- 필수 상품 정보가 빠진 행을 찾습니다.
- 잘못된 카테고리, 재고, 가격 값을 찾습니다.
- 같은 상품 ID, 비슷한 상품명, 완전히 같은 상품 내용을 찾습니다.
- 같은 상품 그룹에서 서로 다른 상품 ID가 공유하는 색상·사이즈 조합을 찾습니다.
- 같은 상품 그룹에서 서로 다른 카테고리가 함께 사용된 경우를 찾습니다.
- 상품명과 카테고리가 서로 어울리지 않는 경우를 찾습니다.
- 패션 상품의 알려진 색상·사이즈 별칭을 권장 표준값과 비교합니다.
- 금지어, 이메일, 전화번호, 주민등록번호 형식, 계좌번호 의심 정보를 찾습니다.
- 검수 결과를 화면, CSV 다운로드, PostgreSQL 이력으로 확인할 수 있게 합니다.
- 공급사별 JSON 매핑 프로필로 원본 CSV를 CatalogGuard 표준 CSV로 변환하고 오류 행을 별도 reject CSV로 분리합니다.

## 3. 주요 기능

- CSV 입력 템플릿 다운로드
- CSV 업로드와 상위 100행 미리보기
- 파일 확장자, 파일 크기, 인코딩, 헤더, 행 수 검증
- 개인정보 의심 값 마스킹
- 필수값 누락 탐지
- 잘못된 데이터 형식 탐지
- 상품 ID, 상품명, 상품 내용 중복 탐지
- 상품 그룹 내 색상·사이즈 옵션 조합 중복 탐지
- 상품 그룹 내 카테고리 일관성 검수
- 가격 오류와 카테고리별 가격 이상치 탐지
- 상품명과 카테고리 불일치 탐지
- 알려진 색상 별칭을 권장 표준 색상으로 안내
- 알려진 사이즈 별칭을 권장 표준 사이즈로 안내
- 금지어와 위험 표현 탐지
- 이메일, 전화번호, 주민등록번호, 계좌번호 의심 정보 탐지
- 상태, 오류 항목, 상품 ID 기준 검수 결과 필터
- 필터 적용 전 전체 결과 기준 오류 항목별·위험 수준별 발생 건수와 문제가 많은 상품 TOP 5 통계
- CSV 검수 화면과 검수 이력 상세 화면의 공통 통계 UI
- 문제 0건, 통계 생성 실패, 검수 요약과 상세 건수 불일치 시 안전한 안내
- 현재 필터 결과 CSV 다운로드
- 검수 결과 PostgreSQL 저장
- 검수 이력 목록 조회와 페이지 이동
- 파일명 부분 검색
- 검수 이력 상세 조회
- 상세 결과 CSV 다운로드
- 같은 Streamlit 세션 안에서 동일 CSV 중복 저장 방지
- PostgreSQL DB 수준 동일 CSV 중복 저장 방지
- 기본값인 `즉시 검수`와 Redis·Celery를 사용하는 `백그라운드 검수` 선택
- 백그라운드 작업의 `queued`, `running`, `succeeded`, `failed` 상태와 수동 새로고침
- 비동기 결과도 기존 검수 요약·통계·필터·다운로드 화면으로 표시
- Streamlit은 업로드 검증과 미리보기만 담당하고, 전체 검수의 단일 기준은 FastAPI 서버로 유지
- `POST /api/v1/inspections` 한 번으로 검수 실행과 이력 저장을 처리하고, `GET` 상세 응답을 화면에 재사용
- 서버 응답의 실행 ID·요약·상세 결과를 검증한 뒤에만 Streamlit 세션 상태에 저장
- FastAPI 오류 응답의 요청 ID를 API Client 예외까지 전달
- Streamlit API 오류 화면에 검증된 요청 ID 표시
- 요청 ID를 이용한 Railway 구조화 로그 추적
- `etl.cli`를 통한 공급사 CSV 표준화, reject CSV·요약 JSON 생성

## 4. 사용자 기능 흐름

```text
CSV 검수 탭
-> CSV 입력 템플릿 다운로드
-> 상품 CSV 작성
-> CSV 파일 업로드
-> 파일명, 크기, 인코딩, 헤더, 행 수 검증
-> 개인정보가 마스킹된 미리보기 확인
-> 즉시 검수(기본값) 또는 백그라운드 검수 선택
-> 백그라운드 검수는 상태 새로고침으로 진행 상태 확인
-> 검수 요약 확인
-> 필터 적용 전 전체 검수 결과 통계 확인
-> 오류/주의 상세 결과 확인
-> 상태, 오류 항목, 상품 ID로 필터
-> 현재 필터 결과 CSV 다운로드
-> 검수 실행 및 이력 저장 버튼 클릭
-> FastAPI가 검수·저장하고 상세 결과 반환
-> 반환된 결과를 화면에 표시
```

```text
검수 이력 탭
-> FastAPI 서버 연결
-> 저장된 검수 이력 목록 조회
-> 파일명 검색
-> 이전/다음 페이지 이동
-> 검수 실행 선택
-> 상세 결과 조회
-> 전체 검수 결과 통계 확인
-> 상세 결과 CSV 다운로드
-> 목록으로 돌아가기
```

검수 결과 저장이나 검수 이력 조회 중 API 오류가 발생하면 Streamlit의 안전한 오류 안내에서 요청 ID를 확인하고, 운영자는 Railway 로그에서 같은 `request_id`를 검색해 해당 요청을 추적할 수 있습니다. 서버 응답이 없는 timeout이나 연결 실패에는 요청 ID를 표시하지 않습니다.

```text
API 오류 발생
-> Streamlit 오류 안내 확인
-> 요청 ID 확인
-> Railway 로그에서 같은 request_id 검색
```

같은 CSV를 이미 저장한 경우에는 PostgreSQL에 저장된 파일 해시와 검수 규칙 버전을 기준으로 기존 실행 ID를 안내합니다. 같은 Streamlit 세션 안에서는 `saved_file_hash`, `saved_inspection_run_id` 상태값으로 저장 API 재호출을 줄이고, 브라우저나 Streamlit 서버를 재시작한 뒤에는 DB의 중복 제약조건으로 새 이력이 중복 생성되지 않도록 막습니다.

## 5. 전체 시스템 구조

CSV를 검수하는 기본 흐름은 FastAPI 서버와 공통 검수 서비스가 담당합니다. Streamlit은 파일 형식 검증, 개인정보 마스킹 미리보기, 요청·응답 표시를 담당하며 전체 규칙을 다시 실행하지 않습니다.

```text
CSV 업로드
-> Streamlit app.py: 업로드 사전 검증·마스킹 미리보기
-> 검수 실행 및 이력 저장 버튼
-> CatalogGuardApiClient
-> FastAPI POST /api/v1/inspections
-> core.upload_validator
-> core.inspection_service
-> core.rules
   -> core.fashion_attribute_validator
   -> core.group_category_consistency_detector
-> PostgreSQL 저장
-> FastAPI GET /api/v1/inspections/{inspection_run_id}
-> Streamlit이 상세 응답을 DataFrame으로 변환·표시
-> 현재 필터 결과 CSV 다운로드
```

서버 검수 응답은 `apply_inspection_save_response()`에서 실행 ID, `created`, 요약 수치, 상세 결과의 필수 필드를 검증한 뒤에만 세션 상태에 반영합니다. 따라서 부분적이거나 잘못된 응답을 성공 결과로 캐시하지 않습니다.

```text
Streamlit 사전 검증·미리보기
-> FastAPI POST /api/v1/inspections
-> FastAPI가 SHA-256·중복 조회·검수·저장
-> FastAPI GET 상세 응답
-> 기존 history detail 변환기 재사용
-> 결과·통계·필터·다운로드
```

검수 결과를 저장할 때는 Streamlit이 FastAPI에 원본 업로드 파일을 한 번 보내고, FastAPI가 CSV bytes의 SHA-256 해시를 직접 계산합니다. 서버는 `file_sha256`과 `inspection_version`으로 기존 이력을 먼저 조회하고, 같은 파일과 같은 검수 버전이 이미 있으면 새 실행을 만들지 않고 기존 ID를 반환합니다.

```text
CSV 업로드
-> 검수 실행 및 이력 저장 버튼
-> CatalogGuardApiClient
-> FastAPI POST /api/v1/inspections
-> CSV bytes의 SHA-256 계산
-> file_sha256 + inspection_version으로 기존 이력 조회
-> 기존 이력이 있으면 기존 ID 반환
-> 기존 이력이 없으면 검수·저장 후 상세 응답 반환
-> FastAPI GET /api/v1/inspections/{inspection_run_id}
-> Streamlit 결과 표시
-> PostgreSQL partial unique index가 동시 요청 중복 차단
```

세션 중복 방지는 같은 Streamlit 세션에서 같은 파일을 다시 제출할 때 POST·GET 재호출을 줄이는 장치입니다. DB 중복 방지는 PostgreSQL 저장 데이터를 기준으로 판단하므로 브라우저나 Streamlit을 재시작해도 동작하고, 동시에 들어오는 동일 저장 요청도 unique index로 최종 차단합니다.

CSV 검수 규칙은 서버에서만 실행됩니다. 아래의 공통 서비스와 규칙 모듈은 FastAPI 요청 경로에서 호출됩니다.
```text
FastAPI POST /api/v1/inspections
-> core.upload_validator
-> core.inspection_service
-> core.rules
   -> core.fashion_attribute_validator
   -> core.group_category_consistency_detector
-> core.presentation
-> API 응답의 요약·상세 결과
```

통계 집계는 화면 코드와 분리한 뒤 CSV 검수 화면과 검수 이력 상세 화면에서 같은 방식으로 사용합니다.

```text
필터 적용 전 전체 검수 결과 DataFrame
-> core.presentation.build_inspection_statistics(results_df)
-> 오류 항목별 / 위험 수준별 / 상품별 집계
-> app.render_inspection_statistics(results_df, expected_total_issues)
-> CSV 검수 화면과 검수 이력 상세 화면에 공통 표시
```

`build_inspection_statistics()`는 입력 DataFrame을 변경하지 않고 상품별 전체 집계까지 반환하며, TOP 5 제한은 UI helper인 `render_inspection_statistics()`에서만 적용합니다. 통계에는 필터 전 `result_df`를 사용하고 상세 표와 CSV 다운로드에는 `filtered_result_df`를 사용하므로, 필터를 변경해도 전체 통계는 유지되고 상세 결과만 바뀝니다. 문제 0건, 집계 실패, 저장된 요약과 상세 문제 수 불일치 시에는 통계 표시를 중단하고 내부 예외 원문을 노출하지 않습니다. 이 기능은 기존 DB, API, Alembic migration을 변경하지 않고 추가했습니다.

저장된 이력을 조회할 때는 FastAPI와 PostgreSQL이 필요합니다.

```text
검수 이력 탭
-> Streamlit app.py
-> CatalogGuardApiClient
-> FastAPI GET /api/v1/inspections
-> db.persistence_service
-> db.repositories
-> PostgreSQL
```

FastAPI 오류 응답의 요청 ID는 다음 경로로 Streamlit까지 전달됩니다.

```text
Railway FastAPI
-> X-Request-ID 응답 헤더
-> CatalogGuardApiClient
-> CatalogGuardApiError.request_id
-> Streamlit 오류 화면
```

API Client는 헤더 값의 앞뒤 공백을 제거한 뒤 정확히 32자리인 소문자 16진수만 요청 ID로 인정합니다. 잘못된 형식은 표시하지 않으며, 서버 응답이 없는 timeout과 연결 실패에는 요청 ID가 없습니다. 클라이언트가 임의 요청 ID를 생성하지도 않습니다.

검수 이력 탭의 전체 요약 CSV 다운로드는 같은 목록 API를 재사용합니다. 화면에 보이는 현재 페이지 10건만 쓰지 않고, 사용자가 `CSV 다운로드 준비` 버튼을 누르면 검색 버튼으로 확정된 파일명·날짜·상태 조건을 유지한 채 `limit=100`, `offset=0`부터 반복 조회해 전체 결과를 모은 뒤 CSV로 변환합니다.

```text
현재 검색 조건
-> CSV 다운로드 준비 버튼 클릭
-> FastAPI GET /api/v1/inspections를 100건씩 반복 조회
-> 전체 검수 이력 요약 결합
-> UTF-8-SIG CSV 변환
-> Streamlit 다운로드 버튼
```

```text
검수 상세 결과
-> Streamlit app.py
-> CatalogGuardApiClient
-> FastAPI GET /api/v1/inspections/{inspection_run_id}
-> db.persistence_service
-> db.repositories
-> PostgreSQL
-> 상세 결과 CSV 다운로드
```

서버 검수 입력과 Streamlit 미리보기 입력은 분리합니다. Streamlit은 업로드 검증 뒤 미리보기 복사본을 만들고, 원본 bytes는 FastAPI 서버로 한 번 전달합니다.

```text
업로드 원본 bytes
-> FastAPI의 Product 변환
-> 서버의 실제 검수 규칙에 사용

마스킹된 DataFrame 복사본
-> Streamlit 미리보기에만 사용
```

패션 색상·사이즈 검수는 `core.rules`가 현재 입력값을 `core.fashion_attribute_validator`의 별칭 사전과 비교해 주의 항목을 만듭니다. 중복 옵션 검수는 같은 비교 함수를 재사용해 `product_group_id`, 색상 비교 키, 사이즈 비교 키가 같은 상품을 찾습니다. 권장 표준값과 비교 키는 검수에만 사용하며 원본 DataFrame, 마스킹 미리보기의 색상·사이즈, `Product.color`, `Product.size`는 변경하지 않습니다.

상품 그룹 카테고리 일관성 검수는 `core.group_category_consistency_detector`가 기존 `core.category_mismatch_detector.normalize_category()`를 재사용합니다. 이 비교는 원본 category를 고치지 않으며, 표시 계층에는 JSON 구조화 메시지로 값을 전달합니다. JSON이 손상되거나 예상 구조가 아니어도 내부 prefix, 영문 메시지나 JSON 원문 대신 안전한 한글 기본 문구를 표시합니다.

## 6. 실행 화면

### CSV 템플릿 및 파일 업로드

필수·선택 컬럼을 확인하고 CSV 입력 템플릿을 내려받을 수 있습니다. 작성한 상품 CSV 파일은 업로드 영역에서 검수를 시작할 수 있습니다.

![CatalogGuard Lite CSV 템플릿 및 파일 업로드 화면](docs/images/01_initial_upload.png)

### 개인정보 마스킹 미리보기

업로드한 데이터는 검수 전에 미리보기로 확인할 수 있습니다. 이메일, 전화번호, 주민등록번호 형태는 일부 문자를 가려서 표시합니다.

![CatalogGuard Lite 개인정보 마스킹 미리보기 화면](docs/images/02_masked_preview_summary.png)

> 위 화면은 개인정보 마스킹 기능을 확인하기 위해 가짜 이메일, 전화번호 및 주민등록번호 형태가 포함된 테스트 CSV를 사용한 예시입니다.

### 검수 결과 필터 및 CSV 다운로드

발견된 문제의 상태, 오류 항목과 상품 ID를 기준으로 결과를 필터링할 수 있습니다. 각 문제의 오류 이유, 수정 권장사항과 위험 수준을 확인하고 현재 필터 결과를 CSV로 내려받을 수 있습니다.

![CatalogGuard Lite 검수 결과 필터 및 CSV 다운로드 화면](docs/images/03_results_filter_download.png)

> 위 화면은 `data/dev/products_dev.csv`를 사용한 검수 예시이며, 상품 5개에서 오류 6건이 탐지된 결과입니다.

### 검수 이력 목록과 검색

저장된 검수 실행을 파일명, 날짜 범위와 검수 상태로 검색하고 페이지 단위로 확인할 수 있습니다. 현재 검색 조건에 맞는 전체 검수 이력 요약도 CSV로 준비해 내려받을 수 있습니다.

![CatalogGuard Lite 검수 이력 목록과 검색 화면](docs/images/04_history_list.png)

### 검수 이력 상세 결과

선택한 검수 실행의 파일명, 검수 시간과 요약 수치를 확인할 수 있습니다. 각 문제의 오류 이유, 수정 권장사항과 위험 수준을 조회하고 상세 결과를 CSV로 내려받을 수 있습니다.

![CatalogGuard Lite 검수 이력 상세 결과 화면](docs/images/05_history_detail.png)

### 검수 결과 통계

전체 검수 문제 6건을 오류 항목별, 위험 수준별, 상품별 통계로 한 화면에서 확인할 수 있습니다. 아래 예시는 오류 항목 필터에서 `가격 오류`를 선택해 상세 결과가 3건만 표시된 상태이며, 통계는 필터 적용 전 전체 결과를 기준으로 하므로 6건을 유지합니다.

![검수 결과 통계 화면](docs/images/06_inspection_statistics.png)

### 패션 색상·사이즈 표준화 검수 확인

로컬 업로드 검수 흐름에서 3행 패션 테스트 CSV를 확인한 결과, 비표준 색상 1건과 비표준 사이즈 1건을 찾아 오류 0건, 주의 2건으로 표시했습니다. `MELANGE GRAY`와 숫자 사이즈 `95`는 보수적인 MVP 판정 범위에서 제외되어 새 경고를 만들지 않았습니다. 기존 `data/dev/products_dev.csv`에서도 새 색상·사이즈 규칙으로 인한 불필요한 경고가 발생하지 않음을 확인했습니다.

완전 중복과 옵션 중복 우선순위를 확인하는 6행 CSV를 Streamlit 업로드 흐름에서 재검증한 결과는 전체 문제 7건, 오류 3건, 주의 4건입니다. 완전 중복은 P006에 1건, 실제 옵션만 중복인 P001/P002에는 2건이 표시되었으며, 완전 중복 관계인 P005/P006에는 옵션 중복이 다시 표시되지 않았습니다. 오류·오류 항목·상품 ID 필터와 필터 결과 CSV 다운로드가 정상 동작했고 원본 색상·사이즈·재고·이미지 경로도 유지되었습니다.

### 상품 그룹 카테고리 일관성 검수 확인

`data/dev/group_category_consistency_test.csv`와 실제 `app.py` Streamlit AppTest 경로로 6개 상품을 업로드해 확인했습니다. 전체 문제는 7건으로 오류 6건, 주의 1건이었고, G001의 `TOP`·`SHOES` 불일치가 비교에 참여한 P001, P002, P003 모두에 표시되었습니다. G002의 `BOTTOM`·`bottom`은 같은 비교값이므로 새 불일치가 없었고, G003은 상품 한 건이라 새 불일치가 없었습니다. 오류 필터는 6건, 카테고리 불일치 규칙 필터는 3건, P003 검색은 1건을 표시했으며 결과 CSV 다운로드 URL도 생성되었습니다. 미리보기의 소문자 `bottom` 원본 표기도 유지되었습니다. 검증 후 임시 CSV는 삭제했습니다.

## 7. 기술 스택

| 영역 | 기술 |
|---|---|
| 화면 | Streamlit `1.58.0` |
| API | FastAPI `0.139.0`, Uvicorn `0.49.0`, Pydantic |
| 데이터 처리 | Python `3.11`, pandas `3.0.3` |
| API 클라이언트 | requests `2.34.2` |
| 데이터베이스 | PostgreSQL, SQLAlchemy `2.0.51`, psycopg `3.3.4` |
| 마이그레이션 | Alembic `1.18.5` |
| 비동기 처리 | Redis `7.4`, Celery `5.6.3` |
| 로컬 실행 | Docker Compose |
| 테스트 | pytest |
| CI | GitHub Actions |
| CI 테스트 서비스 | PostgreSQL `18`·Redis `7.4` 서비스 컨테이너 |

`requirements.txt`에는 Streamlit 앱 실행에 필요한 기본 패키지가 있고, `requirements-api.txt`에는 FastAPI와 PostgreSQL 저장 계층에 필요한 패키지가 있습니다. FastAPI도 pandas 기반 검수 로직을 사용하므로 로컬 전체 시스템을 실행할 때는 두 파일을 모두 설치하는 것이 안전합니다.

GitHub Actions는 PostgreSQL·Redis 테스트 서비스, Alembic 마이그레이션, E2E를 제외한 전체 pytest, 실제 FastAPI·Celery Worker 비동기 CSV 검수 E2E 스모크 테스트, Streamlit 서버 시작과 Health 응답 확인에 사용하며 배포는 수행하지 않습니다.

## 8. 프로젝트 폴더 구조

```text
catalogguard-lite/
  .github/
    workflows/
      test.yml
  README.md
  app.py
  clients/
    __init__.py
    catalogguard_api.py
  api/
    __init__.py
    main.py
    schemas.py
    routes/
      __init__.py
      inspections.py
      inspection_jobs.py
  config/
    database.py
    settings.py
    etl/
      sample_fashion_vendor_v1.json
  core/
    __init__.py
    category_mismatch_detector.py
    duplicate_detector.py
    fashion_attribute_validator.py
    inspection_service.py
    loader.py
    models.py
    presentation.py
    price_anomaly_detector.py
    privacy.py
    product_template.py
    result_exporter.py
    rules.py
    upload_validator.py
  db/
    __init__.py
    base.py
    models.py
    persistence_service.py
    repositories.py
    session.py
  services/
    inspection_job_service.py
    job_files.py
    redis_job_store.py
  workers/
    celery_app.py
    inspection_tasks.py
  etl/
    cli.py
    models.py
    pipeline.py
    profile_loader.py
    transformer.py
  compose.local.yaml
  alembic/
    env.py
    script.py.mako
    versions/
      20260703_0001_create_inspection_tables.py
      20260705_0002_add_inspection_file_identity.py
  data/
    dev/
      category_mismatch_test.csv
      price_anomaly_test.csv
      privacy_masking_test.csv
      products_dev.csv
  docs/
    images/
      01_initial_upload.png
      02_masked_preview_summary.png
      03_results_filter_download.png
      04_history_list.png
      05_history_detail.png
      06_inspection_statistics.png
    portfolio_project.md
    etl_mvp.md
    sql_performance_analysis.md
  tests/
    test_api_health.py
    test_api_logging.py
    test_api_inspections.py
    test_app_history_download_helpers.py
    test_app_history_helpers.py
    test_app_inspection_save_helpers.py
    test_app_smoke.py
    test_catalogguard_api_client.py
    test_category_mismatch_detector.py
    test_database_connection.py
    test_database_models.py
    test_duplicate_detector.py
    test_fashion_attribute_validator.py
    test_inspection_persistence.py
    test_inspection_service.py
    test_loader.py
    test_presentation.py
    test_price_anomaly_detector.py
    test_privacy.py
    test_product_template.py
    test_result_exporter.py
    test_rules.py
    test_upload_validator.py
    etl/
      test_cli.py
      test_pipeline.py
      test_profile_loader.py
      test_transformer.py
  .env.example
  alembic.ini
  requirements.txt
  requirements-api.txt
```

## 9. 주요 파일 역할

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit 화면, CSV 검수·이력 탭, 공통 통계 UI, 검수 저장, 목록·상세·CSV 다운로드, API 오류 안내와 요청 ID 표시 |
| `clients/catalogguard_api.py` | FastAPI 검수 이력 API 호출, `X-Request-ID` 검증, HTTP·404·JSON 오류의 요청 ID 보존, timeout·연결 실패 구분 |
| `api/main.py` | FastAPI 앱 생성, 라우터 등록, `/health`와 `/ready`, 요청 ID 및 요청 단위 로그 처리 |
| `api/routes/inspections.py` | 검수 생성, 서버 SHA-256 계산, 중복 이력 응답, 검수 이력 목록, 검수 상세 조회 API |
| `api/schemas.py` | `created` 필드를 포함한 API 응답 Pydantic 모델 |
| `config/logging.py` | 중복 handler 없이 한 줄 JSON 운영 로그를 기록하는 표준 라이브러리 유틸리티 |
| `config/settings.py` | CSV 컬럼, 허용 카테고리, 업로드 제한, 금지어, API 클라이언트 환경변수, `INSPECTION_VERSION` |
| `config/database.py` | `DATABASE_URL`, `TEST_DATABASE_URL` 환경변수 읽기와 검증 |
| `core/inspection_service.py` | FastAPI 요청에서 실행되는 공통 CSV 검수 서비스 |
| `core/upload_validator.py` | 업로드 CSV 파일명, 크기, 인코딩, 헤더, 행 수 검증 |
| `core/rules.py` | 전체 검수 규칙 실행 |
| `core/duplicate_detector.py` | 상품 ID·상품명과 상품 그룹 내 색상·사이즈 옵션 조합 중복 탐지 |
| `core/group_category_consistency_detector.py` | 상품 그룹별 카테고리 정규화 비교, 입력 순서 유지와 안전한 JSON 메시지 생성·검증 |
| `core/fashion_attribute_validator.py` | 패션 색상·사이즈 별칭을 권장 표준값으로 찾고 원본을 바꾸지 않는 비교 키를 만드는 순수 함수 |
| `core/presentation.py` | 내부 검수 문제를 화면용 한글 결과표로 변환하고 전체 검수 결과 통계를 집계 |
| `core/result_exporter.py` | 검수 결과 CSV 다운로드 데이터와 파일명 생성 |
| `core/product_template.py` | CSV 입력 템플릿 생성 |
| `core/privacy.py` | 개인정보 정규식과 마스킹 처리 |
| `db/models.py` | 파일 해시와 검수 버전 컬럼을 포함한 `inspection_runs`, `inspection_results` SQLAlchemy 모델 |
| `db/repositories.py` | 검수 실행과 상세 결과 저장·조회, 파일 identity 조회 Repository |
| `db/persistence_service.py` | 검수 결과 저장 트랜잭션, 중복 조회, 경쟁 상태 처리, 목록 조회, 상세 조회 Service |
| `db/session.py` | SQLAlchemy 엔진, 세션 팩토리, DB 연결 확인, FastAPI 세션 의존성 |
| `services/redis_job_store.py` | Redis에 비동기 검수 작업 상태와 TTL 저장 |
| `services/inspection_job_service.py`, `services/job_files.py` | 작업 제출, 서버 생성 job 파일 저장·검증·정리 |
| `workers/celery_app.py`, `workers/inspection_tasks.py` | Celery Worker 실행과 비동기 CSV 검수·결과 저장 |
| `etl/profile_loader.py`, `etl/transformer.py`, `etl/pipeline.py` | JSON 프로필 검증, 공급사 행 변환, reject 분리와 원자적 출력 저장 |
| `etl/cli.py` | 공급사 CSV ETL CLI 진입점 |
| `config/etl/sample_fashion_vendor_v1.json` | 샘플 공급사 컬럼과 CatalogGuard 표준 컬럼 매핑 프로필 |
| `compose.local.yaml` | PostgreSQL·Redis·FastAPI·Celery Worker 로컬 실행 구성 |
| `alembic/versions/20260703_0001_create_inspection_tables.py` | 검수 이력 저장 테이블 생성 마이그레이션 |
| `alembic/versions/20260705_0002_add_inspection_file_identity.py` | 파일 해시와 검수 버전 컬럼, CHECK constraint, partial unique index 추가 마이그레이션 |
| `.github/workflows/test.yml` | PostgreSQL 18·Redis 7.4 테스트 서비스에서 마이그레이션, E2E 제외 pytest, FastAPI·Celery 비동기 E2E, Streamlit 시작 스모크 테스트를 실행하는 GitHub Actions workflow |
| `.env.example` | 로컬 PostgreSQL 연결 환경변수 예시 |
| `requirements.txt` | Streamlit 앱 기본 실행 패키지 |
| `requirements-api.txt` | FastAPI, PostgreSQL, Alembic 관련 패키지 |

## 10. CSV 입력 컬럼

필수 컬럼은 9개입니다.

| 컬럼 | 설명 |
|---|---|
| `product_group_id` | 옵션 상품을 묶는 상품 그룹 ID |
| `product_id` | 개별 상품 ID |
| `product_name` | 상품명 |
| `category` | 상품 카테고리 |
| `color` | 색상 |
| `size` | 사이즈 |
| `stock` | 재고 수량 |
| `price` | 판매 가격 |
| `image_path` | 상품 이미지 경로 |

선택 컬럼은 3개입니다.

| 컬럼 | 설명 |
|---|---|
| `sale_price` | 할인가. 비어 있으면 할인하지 않는 상품으로 처리하며, 입력된 경우 `price`보다 클 수 없습니다. |
| `description` | 상품 설명 |
| `seller` | 판매자 정보 |

허용 카테고리는 다음 3개입니다.

```text
TOP
BOTTOM
OUTER
```

CSV 템플릿 다운로드 파일명은 `catalogguard_product_template.csv`입니다.

### 패션 색상·사이즈 표준화 기준

색상 검수는 다음 권장 표준값을 지원합니다.

```text
BLACK, WHITE, GRAY, NAVY, BEIGE, BROWN, RED, BLUE,
GREEN, YELLOW, PINK, PURPLE, ORANGE, KHAKI, IVORY, CREAM
```

사이즈 검수는 다음 권장 표준값을 지원합니다.

```text
XXS, XS, S, M, L, XL, XXL, XXXL, FREE
```

알려진 별칭은 다음과 같이 안내합니다.

```text
블랙, black, Black -> BLACK
grey, 회색 -> GRAY
medium, m -> M
2XL, xx-large -> XXL
프리사이즈, one size -> FREE
```

판정 방식은 다음과 같습니다.

- 입력값의 앞뒤 공백을 제거하고 영문 대소문자를 무시해 별칭 사전을 조회합니다.
- 별칭 사전의 키와 정확히 일치하는 값만 판정하며 부분 문자열이나 유사도 검사는 사용하지 않습니다.
- 찾은 표준값과 현재 입력값이 완전히 다르면 `주의`(`warning`)로 표시하며 위험 수준은 `낮음`입니다.
- 원본 CSV, 원본 DataFrame과 `Product`의 색상·사이즈를 자동으로 수정하지 않습니다.
- 결과표의 오류 이유에 현재 값과 권장 표준값을 함께 표시합니다.

색상·사이즈 비표준 표기 검수에서는 오탐을 줄이기 위해 `MELANGE GRAY`, `OATMEAL`, `DUSTY PINK` 같은 사용자 정의·복합 색상과 `95`, `100`, `28`, `30` 같은 숫자 사이즈를 표준화 대상으로 판단하지 않습니다. 별칭 사전에 없는 값 자체만으로는 비표준 오류나 주의를 만들지 않습니다. 이는 정상값을 잘못 경고하는 일을 줄이기 위한 보수적인 MVP 방식이며, 아래 중복 옵션 검수에서는 정리된 비교 키로 사용할 수 있습니다.

### 상품 그룹 내 중복 색상·사이즈 옵션 기준

다음 조건을 모두 만족하면 `상품 옵션 조합 중복` 오류로 표시합니다.

- `product_group_id`가 같습니다.
- 색상 비교 키와 사이즈 비교 키가 모두 같습니다.
- 중복 묶음에 서로 다른 `product_id`가 두 개 이상 있습니다.
- 색상과 사이즈가 모두 비어 있지 않습니다.

알려진 별칭은 표준값으로 비교합니다. 예를 들어 `블랙`, `black`, `BLACK`은 모두 `BLACK`이고 `medium`, `M`은 모두 `M`입니다. 별칭 사전에 없는 사용자 정의 값도 앞뒤 공백과 영문 대소문자를 정리한 비교 키를 사용하므로 `MELANGE GRAY`와 `melange gray`, `95`와 ` 95 `를 같은 값으로 비교할 수 있습니다. 사용자 정의 값이라는 이유만으로 색상·사이즈 비표준 경고를 추가하지는 않습니다.

다른 상품 그룹의 같은 옵션은 중복이 아닙니다. 색상이나 사이즈가 비어 있으면 새 중복 옵션 규칙에서 제외하고 기존 필수 값 누락 규칙이 처리합니다. 같은 `product_id`만 반복된 경우도 새 규칙에서 제외하고 기존 상품 ID 중복 규칙이 처리합니다. 중복에 포함된 서로 다른 상품 ID의 모든 행에 결과를 연결하며 입력 순서를 유지합니다.

`완전 중복 상품`은 `상품 옵션 조합 중복`보다 우선합니다. 기존 완전 중복 기준인 정규화된 상품명·카테고리·색상·사이즈·가격이 같은 상품 관계는 완전 중복으로만 표시하고, 같은 관계를 옵션 중복으로 다시 표시하지 않습니다. 완전 중복 판정에는 재고와 이미지 경로를 사용하지 않습니다. 색상·사이즈 비교 키만 같고 가격 등 다른 완전 중복 기준이 다르면 옵션 중복은 그대로 표시합니다. 세 상품 이상이 같은 옵션을 공유할 때도 그룹 전체를 제거하지 않고 상품 관계별로 판정하므로, 일부 상품만 완전 중복이어도 나머지 상품과의 실제 옵션 중복은 유지됩니다.

검수 과정은 비교 키만 별도로 만들고 원본 CSV, 원본 DataFrame, 미리보기와 `Product.color`·`Product.size`를 자동 수정하지 않습니다.

### 상품 그룹 내 카테고리 일관성 기준

같은 `product_group_id` 안에서 비어 있지 않은 category 정규화 결과가 두 개 이상이면 `상품 그룹 카테고리 불일치` 오류로 표시합니다. 비교할 때 앞뒤 공백과 영문 대소문자를 무시하고 기존 카테고리 별칭을 재사용하므로 `TOP`, `top`, `상의`는 같은 값으로 판단합니다. 사용자에게는 정규화 키가 아니라 각 비교값이 최초로 등장했을 때의 원본 대표 표기를 최초 입력 순서대로 보여 줍니다.

빈 category는 비교에서 제외하고 기존 `필수 값 누락` 오류가 처리합니다. 허용 목록에 없는 category도 그룹 안에서 모두 같은 비교값이면 새 일관성 오류를 만들지 않지만, 서로 다른 값과 섞이면 기존 `카테고리 오류`와 새 그룹 일관성 오류가 함께 표시될 수 있습니다. 기존 상품명·카테고리 불일치 규칙도 의미가 다르므로 필요한 경우 함께 표시됩니다.

어느 category가 정답인지 다수결이나 상품명 추론으로 결정하지 않습니다. 불일치 그룹에서 비어 있지 않은 비교에 참여한 모든 상품에 결과를 연결하고 전체 입력 순서를 유지합니다. 따라서 그룹 한 곳의 카테고리 문제 하나가 참여 상품 수만큼 결과 행으로 생성될 수 있습니다. 이 방식은 특정 상품만 자동으로 잘못됐다고 단정하지 않고 그룹 전체를 함께 점검하게 하기 위한 정책입니다.

비교용 정규화는 원본 category를 자동 수정하지 않습니다. 입력 DataFrame과 `report.source_dataframe`은 업로드 원본을 보존하고, 탐지기에 직접 전달한 `Product`도 변경하지 않습니다. 단, `report.products`는 기존 loader 계약에 따라 문자열 앞뒤 공백이 제거된 상태입니다. 구조화 JSON에는 그룹, 최초 대표 category와 상품 ID를 저장하므로 작은따옴표, 큰따옴표, 쉼표, 한글과 공백이 있어도 문자열 정규식 파싱 없이 안전하게 표시할 수 있습니다.

## 11. CSV 업로드 검증 기준

업로드된 파일은 검수 규칙 실행 전에 먼저 검증됩니다.

- 파일명이 없거나 `.csv` 확장자가 아니면 차단합니다.
- 빈 파일은 차단합니다.
- 최대 파일 크기는 `5MB`입니다.
- NUL 바이트가 포함된 파일은 일반 CSV 텍스트 파일이 아닌 것으로 보고 차단합니다.
- 지원 인코딩은 `utf-8-sig`, `utf-8`, `cp949`입니다.
- 내용이 공백뿐인 파일은 차단합니다.
- 헤더가 없거나 CSV 따옴표 형식이 깨진 파일은 차단합니다.
- 빈 컬럼명이 있으면 차단합니다.
- 대소문자만 다른 중복 컬럼명도 중복으로 보고 차단합니다.
- 필수 컬럼이 빠지면 차단합니다.
- 데이터 행의 열 개수가 헤더와 다르면 차단합니다.
- 데이터 행이 없는 헤더 전용 CSV는 차단합니다.
- 최대 데이터 행 수는 `10,000`행입니다.

## 12. 설치 방법

Windows PowerShell 또는 VS Code 터미널에서 저장소 루트로 이동한 뒤 가상환경을 만듭니다.

```powershell
cd C:\study\catalogguard-lite
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Streamlit CSV 검수 화면만 실행하려면 기본 패키지를 설치합니다.

```powershell
python -m pip install -r requirements.txt
```

FastAPI, PostgreSQL 저장, 검수 이력 기능까지 로컬에서 함께 실행하려면 API 패키지도 설치합니다.

```powershell
python -m pip install -r requirements-api.txt
```

테스트 실행에 `pytest`가 없다면 별도로 설치합니다.

```powershell
python -m pip install pytest==9.1.1
```

## 13. PostgreSQL 개발 DB와 테스트 DB 준비 방법

PostgreSQL이 설치되어 있고 `psql` 명령을 PowerShell에서 사용할 수 있어야 합니다. 아래 예시는 PostgreSQL 18 기준으로 사용할 수 있는 개발 DB와 테스트 DB 이름입니다.

| 용도 | 데이터베이스 | 사용자 |
|---|---|---|
| 개발 | `catalogguard_lite` | `catalogguard_user` |
| 테스트 | `catalogguard_lite_test` | `catalogguard_test_user` |

관리자 권한으로 PostgreSQL에 접속한 뒤 사용자와 데이터베이스를 만듭니다.

```powershell
psql -U postgres
```

`psql` 안에서 아래 SQL을 실행합니다. `CHANGE_ME`는 실제 로컬 비밀번호로 바꾸세요.

```sql
CREATE USER catalogguard_user WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE catalogguard_lite OWNER catalogguard_user;
CREATE USER catalogguard_test_user WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE catalogguard_lite_test OWNER catalogguard_test_user;
```

생성이 끝나면 `\q`로 `psql`을 종료합니다.

```sql
\q
```

이미 사용자나 데이터베이스가 있다면 환경에 맞게 비밀번호 변경, 권한 부여, 기존 DB 재사용 중 하나를 선택하면 됩니다.

## 14. 환경변수 설정

`.env.example`에는 PostgreSQL 연결 문자열 예시가 있습니다.

```text
DATABASE_URL=postgresql+psycopg://catalogguard_user:CHANGE_ME@localhost:5432/catalogguard_lite
TEST_DATABASE_URL=postgresql+psycopg://catalogguard_test_user:CHANGE_ME@localhost:5432/catalogguard_lite_test
```

현재 코드에는 `.env` 파일을 자동으로 읽는 `python-dotenv` 설정이 없습니다. 로컬 실행 시에는 PowerShell 환경변수로 직접 설정하세요.

```powershell
$env:DATABASE_URL="postgresql+psycopg://catalogguard_user:CHANGE_ME@localhost:5432/catalogguard_lite"
$env:TEST_DATABASE_URL="postgresql+psycopg://catalogguard_test_user:CHANGE_ME@localhost:5432/catalogguard_lite_test"
```

Streamlit에서 검수 이력 저장·목록·상세 조회 기능을 사용하려면 FastAPI 주소도 설정합니다.

```powershell
$env:CATALOGGUARD_API_BASE_URL="http://127.0.0.1:8001"
$env:CATALOGGUARD_API_TIMEOUT_SECONDS="5.0"
```

`CATALOGGUARD_API_TIMEOUT_SECONDS`는 생략하거나 잘못된 값이 들어가면 기본값 `5.0`초를 사용합니다. `CATALOGGUARD_API_BASE_URL`이 없으면 Streamlit의 CSV 검수 자체는 가능하지만, 검수 이력 저장과 조회는 사용할 수 없습니다.

## 15. Alembic 마이그레이션

마이그레이션은 `DATABASE_URL`이 설정된 PowerShell에서 저장소 루트 기준으로 실행합니다.

```powershell
cd C:\study\catalogguard-lite
.\.venv\Scripts\Activate.ps1
python -m alembic current
python -m alembic upgrade head
python -m alembic history
```

현재 적용된 최신 Alembic revision은 `20260705_0002`입니다.

`20260703_0001_create_inspection_tables.py`는 다음 테이블을 만듭니다.

- `inspection_runs`
- `inspection_results`

`20260705_0002_add_inspection_file_identity.py`는 동일 CSV 중복 저장을 DB 수준에서 막기 위해 `inspection_runs`에 파일 identity 정보를 추가합니다.

upgrade 동작은 다음 순서입니다.

1. `file_sha256` nullable 컬럼 추가
2. `inspection_version`을 임시 nullable 상태로 추가
3. 기존 행의 `inspection_version IS NULL` 값을 문자열 `"1"`로 backfill
4. `inspection_version`을 `NOT NULL`로 변경
5. `file_sha256` 길이와 `inspection_version` 빈 문자열 방지 CHECK constraint 추가
6. `(file_sha256, inspection_version)` partial unique index 추가

중요한 점은 기존 이력의 `file_sha256`을 NULL로 유지한다는 것입니다. DB에는 과거 원본 CSV bytes가 저장되어 있지 않으므로 과거 파일 해시를 추측해서 채우지 않습니다. 또한 `inspection_version`에는 DB `server_default`를 두지 않고, 애플리케이션이 현재 검수 규칙 버전을 명시적으로 저장합니다.

테이블이 만들어졌는지 확인하려면 아래 명령을 실행합니다.

```powershell
psql "$env:DATABASE_URL" -c "\dt"
psql "$env:DATABASE_URL" -c "\d inspection_runs"
psql "$env:DATABASE_URL" -c "\d inspection_results"
```

## 16. FastAPI 실행 방법

FastAPI는 검수 이력 저장, 목록 조회, 상세 조회를 담당합니다. 실행 전에 `DATABASE_URL`이 설정되어 있고 Alembic 마이그레이션이 적용되어 있어야 합니다.

```powershell
cd C:\study\catalogguard-lite
.\.venv\Scripts\Activate.ps1
python -m uvicorn api.main:app --host 127.0.0.1 --port 8001 --reload
```

브라우저에서 아래 주소를 확인합니다.

- Health check: http://127.0.0.1:8001/health
- Readiness check: http://127.0.0.1:8001/ready
- API docs: http://127.0.0.1:8001/docs

CSV 검수 저장 API는 `multipart/form-data` 요청을 사용하며 파일 필드명은 `file`입니다.

```powershell
curl.exe -X POST "http://127.0.0.1:8001/api/v1/inspections" `
  -H "accept: application/json" `
  -F "file=@data/dev/products_dev.csv;type=text/csv"
```

서버는 실행 중인 PowerShell에서 `Ctrl+C`로 종료합니다.

### FastAPI + PostgreSQL + Redis + Celery Docker Compose 로컬 실행

이 절은 `compose.local.yaml`로 FastAPI, PostgreSQL, Redis, Celery Worker를 실행합니다. Streamlit은 호스트에서 실행하며 컨테이너화하지 않습니다. API와 Worker 이미지는 기존 `Dockerfile.local`을 재사용하고, 컨테이너 내부 API 포트 `8000`은 Windows 호스트의 기본 `8001`에 연결합니다. PostgreSQL은 CI와 같은 메이저 버전 18을 사용하며, Windows PostgreSQL의 기본 포트 `5432`와 겹치지 않도록 호스트의 `5433`에 연결합니다.

#### 로컬 환경변수 파일 준비

저장소 루트에서 예시 파일을 복사하고 `.env.local`의 `CHANGE_ME`만 URL-safe 임의 문자열로 바꿉니다. 실제 비밀번호나 전체 DB 연결 문자열은 문서, 명령 출력 또는 Git에 기록하지 않습니다. `.env.local`과 일반 `.env`는 `.gitignore` 및 `.dockerignore`에서 제외됩니다.

```powershell
cd C:\study\catalogguard-lite
Copy-Item .env.local.example .env.local
notepad .env.local
```

호스트 포트가 이미 사용 중이면 `.env.local`의 `POSTGRES_HOST_PORT` 또는 `API_HOST_PORT`만 다른 빈 포트로 바꿉니다. 컨테이너끼리는 호스트 포트와 관계없이 API가 `db` 서비스의 PostgreSQL `5432` 포트에 연결합니다.

#### 빌드와 실행

```powershell
docker compose --env-file .env.local -f compose.local.yaml build
docker compose --env-file .env.local -f compose.local.yaml up -d
```

`db`와 `redis` healthcheck가 통과한 뒤 `api`가 시작되고, API가 healthy 상태가 되면 `worker`가 시작됩니다. API 시작 명령은 먼저 `python -m alembic upgrade head`를 적용하고, 성공한 경우에만 Uvicorn을 `--no-access-log`로 실행합니다. 임의의 `sleep`은 사용하지 않습니다.

서비스 상태와 필요한 로그만 확인합니다. 정상 기동이면 `db`, `redis`, `api`가 healthy이고 Worker 로그에 `ready`가 표시됩니다.

```powershell
docker compose --env-file .env.local -f compose.local.yaml ps
docker compose --env-file .env.local -f compose.local.yaml logs --tail 100 db redis api worker
```

마이그레이션의 현재 revision과 head가 같은지 확인합니다.

```powershell
docker compose --env-file .env.local -f compose.local.yaml exec api `
  python -m alembic current
docker compose --env-file .env.local -f compose.local.yaml exec api `
  python -m alembic heads
```

#### Health와 readiness 확인

`/health`는 API 프로세스를, `/ready`는 PostgreSQL 연결까지 확인합니다. 두 응답이 HTTP `200`이고 `/ready` 본문의 `database`가 `ok`인지, 두 응답에 `X-Request-ID`가 있는지 확인합니다.

```powershell
$healthResponse = Invoke-WebRequest `
  -Uri "http://127.0.0.1:8001/health" `
  -UseBasicParsing
$readyResponse = Invoke-WebRequest `
  -Uri "http://127.0.0.1:8001/ready" `
  -UseBasicParsing

$healthResponse.StatusCode
$healthResponse.Content
$healthResponse.Headers["X-Request-ID"]
$readyResponse.StatusCode
$readyResponse.Content
$readyResponse.Headers["X-Request-ID"]
```

API 문서는 http://127.0.0.1:8001/docs 에서 확인할 수 있습니다. CSV 저장·목록·상세 조회 API는 위의 기존 FastAPI 사용법과 동일합니다.

#### 중지, 삭제, 데이터 보존

다음 명령은 컨테이너와 네트워크만 제거합니다. `postgres_data`, `redis_data`, `inspection_jobs` named volume은 남으므로 같은 Compose 프로젝트를 다시 실행하면 검수 이력과 로컬 비동기 작업 데이터가 유지됩니다.

```powershell
docker compose --env-file .env.local -f compose.local.yaml down
```

컨테이너만 잠시 멈추고 나중에 그대로 재개하려면 `stop`과 `start`를 사용합니다.

```powershell
docker compose --env-file .env.local -f compose.local.yaml stop
docker compose --env-file .env.local -f compose.local.yaml start
```

아래 명령의 `-v`는 PostgreSQL, Redis, 작업 파일 named volume과 모든 로컬 검수·작업 데이터를 삭제합니다. 복구할 수 없는 로컬 전체 초기화가 목적일 때만 실행합니다.

```powershell
> 주의: 로컬 PostgreSQL·Redis·비동기 작업 데이터를 영구 삭제합니다.
docker compose --env-file .env.local -f compose.local.yaml down -v
```

데이터를 보존하려면 `down -v`와 named volume 수동 삭제를 피하고, 동일한 저장소 경로와 `compose.local.yaml`을 사용합니다. 볼륨 존재 여부는 `docker volume ls --filter "name=catalogguard-lite-local"`로 확인할 수 있습니다.

#### 오류 확인 항목

- Docker Desktop이 실행 중이고 `docker version`에서 Server 정보가 보이는지 확인합니다.
- `docker compose ... ps`에서 `db`, `redis`, `api` healthcheck와 `worker` 상태를 확인합니다.
- `docker compose ... logs --tail 100 db redis api worker`에서 PostgreSQL·Redis 초기화, Alembic, Uvicorn, Celery 시작 오류를 확인합니다.
- Windows에서 `5433` 또는 `8001`이 사용 중이면 `.env.local`의 호스트 포트를 바꿉니다.
- `.env.local`의 필수 값이 비어 있지 않은지 확인하되, 비밀번호나 DB 연결 문자열을 터미널에 출력하지 않습니다.
- migration 오류가 있으면 `alembic current`와 `alembic heads`를 비교합니다.

`compose.local.yaml`, `.env.local.example`, `Dockerfile.local`은 로컬 개발 전용입니다. 루트 `Dockerfile`을 추가하지 않고 Railway 설정도 수정하지 않으므로 기존 Railpack 빌드, Pre-deploy Command, Start Command, 운영 `DATABASE_URL`과 Railway 배포 방식에는 영향을 주지 않습니다.

### AWS EC2·RDS staging 수동 배포 및 검증

2026-07-19 AWS 서울 리전에서 Amazon Linux 2023 EC2의 Docker 기반 FastAPI와
PostgreSQL RDS를 사용한 staging 수동 배포를 검증했습니다.
TLS 기반 RDS 연결과 Alembic migration을 적용하고 `/health`와 `/ready`의 HTTP 200 응답을 확인했으며,
CSV 저장·목록·상세 조회와 동일 CSV 중복 저장 방지를 검증했습니다.
별도 Streamlit AWS 검증 앱에서도 화면 저장과 검수 이력 조회를 확인했습니다.
상세 배포 절차와 재시작·중지 방법은 [AWS staging 배포 런북](docs/aws-staging-deployment.md)을 참고합니다.
기존 Railway production과 production Streamlit 설정은 변경하지 않았습니다.

### Railway FastAPI 배포 설정

production 환경에는 `catalogguard-lite` FastAPI 서비스와 `Postgres` PostgreSQL 서비스가 배포되어 있습니다. API 의존성은 `requirements-api.txt`에 분리되어 있으므로 Railway 대시보드에서 Build Command는 비워 두고, 다음 설정을 사용합니다.

```text
Root Directory: /
Build Command: (비워 둠)
RAILPACK_INSTALL_CMD: python -m venv /app/.venv && /app/.venv/bin/python -m pip install -r requirements-api.txt
Pre-deploy Command: cd /app && /app/.venv/bin/alembic upgrade head
Start Command: cd /app && /app/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port $PORT --no-access-log
Healthcheck Path: /health
DATABASE_URL: Postgres 서비스의 DATABASE_URL을 Reference Variable로 연결
```

실제 `DATABASE_URL` 값이나 비밀번호는 저장소에 기록하지 않습니다. Start Command에는 운영 배포용으로 `--reload`, `127.0.0.1`, 고정 포트 `8000`을 넣지 않습니다. `--no-access-log`는 query string을 포함할 수 있는 Uvicorn 기본 요청 접근 로그만 비활성화하며, FastAPI 서버 시작 로그와 애플리케이션이 직접 기록하는 요청별 구조화 로그는 계속 유지합니다. `/health`는 FastAPI 프로세스 상태만 빠르게 확인하며 PostgreSQL 연결까지 확인하지 않습니다.

Railway Healthcheck Path는 계속 `/health`로 유지합니다. `/ready`는 FastAPI와 PostgreSQL 연결 상태를 함께 확인하며, 코드 배포 후 `/ready` 응답을 별도로 확인해야 합니다.

Railway가 제공하는 driverless `postgresql://` 형식의 `DATABASE_URL`은 애플리케이션에서 `postgresql+psycopg://`로 정규화해 SQLAlchemy가 설치된 `psycopg` 드라이버를 사용하게 합니다.

공개 API 주소와 확인 경로는 다음과 같습니다.

- API Base URL: https://catalogguard-lite-production.up.railway.app
- Health: https://catalogguard-lite-production.up.railway.app/health
- Readiness (코드 배포 후 확인): https://catalogguard-lite-production.up.railway.app/ready
- Swagger Docs: https://catalogguard-lite-production.up.railway.app/docs

Streamlit Community Cloud의 Secrets에는 다음 값을 설정합니다.

```toml
CATALOGGUARD_API_BASE_URL = "https://catalogguard-lite-production.up.railway.app"
CATALOGGUARD_API_TIMEOUT_SECONDS = "10"
```

현재 배포에서는 `/health`, `/docs`, Streamlit Community Cloud 연결, CSV 검수, PostgreSQL 검수 이력 저장, 목록·상세 조회, 상세·전체 CSV 다운로드와 동일 파일 중복 저장 방지를 확인했습니다.

#### 첫 배포 오류 해결

- 첫 빌드에서는 Railway가 `requirements.txt`를 설치해 FastAPI, SQLAlchemy, Alembic, psycopg 등 API·DB 패키지가 누락되었습니다.
- `RAILPACK_INSTALL_CMD`로 `requirements-api.txt`를 설치하도록 바꿨지만, 설치 명령을 덮어쓰면서 `/app/.venv`가 생성되지 않았습니다. 현재 명령은 `python -m venv /app/.venv`로 가상환경을 먼저 생성합니다.
- Pre-deploy에서 `alembic command not found`가 발생해 `/app/.venv/bin/alembic` 절대 경로를 사용하도록 수정했습니다.
- Start Command의 `uvicorn`도 같은 이유로 `/app/.venv/bin/uvicorn` 절대 경로를 사용합니다.

## 17. Streamlit 실행 방법

Streamlit 화면만 실행하려면 아래 명령을 사용합니다.

```powershell
cd C:\study\catalogguard-lite
.\.venv\Scripts\Activate.ps1
python -m streamlit run app.py
```

검수 이력까지 사용하려면 다른 PowerShell 창에서 FastAPI 서버를 먼저 실행하고, Streamlit을 실행하는 PowerShell에도 API 주소를 설정합니다.

```powershell
$env:CATALOGGUARD_API_BASE_URL="http://127.0.0.1:8001"
python -m streamlit run app.py
```

브라우저가 자동으로 열리지 않으면 터미널에 표시되는 Streamlit 주소를 열면 됩니다.

## 18. API 목록

### `GET /health`

FastAPI 서버 상태를 확인합니다. PostgreSQL 연결을 확인하는 엔드포인트는 아닙니다.

응답 예시는 다음과 같습니다.

```json
{
  "status": "ok",
  "service": "catalogguard-lite-api"
}
```

### `GET /ready`

FastAPI 프로세스와 PostgreSQL 연결 상태를 함께 확인합니다. 기존 SQLAlchemy 엔진으로 `SELECT 1`을 실행하며, 성공하면 HTTP `200`과 `database: "ok"`를 반환하고 연결 또는 쿼리가 실패하면 내부 오류 내용을 노출하지 않고 HTTP `503`과 `database: "unavailable"`을 반환합니다.

공개 확인 주소는 https://catalogguard-lite-production.up.railway.app/ready 입니다. 운영 배포에서 `/health`와 `/ready`가 HTTP `200`을 반환하고 `/ready`의 `database`가 `"ok"`인지 확인합니다. Railway Healthcheck Path는 `/health`로 유지합니다.

### 요청 ID와 운영 구조화 로그

FastAPI는 클라이언트의 `X-Request-ID`를 재사용하지 않고 요청마다 새 ID를 생성해 모든 응답의 `X-Request-ID` 헤더에 넣습니다. 요청 ID는 인증 정보나 보안 토큰이 아니라 문제 추적용 식별값입니다.

Streamlit의 `CatalogGuardApiClient`는 응답 헤더의 앞뒤 공백을 제거한 뒤 `^[0-9a-f]{32}$`에 일치하는 정확히 32자리 소문자 16진수만 허용합니다. 검증된 요청 ID는 HTTP 오류와 GET·POST JSON 응답 해석 실패에서 `CatalogGuardApiError.request_id`에 보존되며, 상세 조회 HTTP `404`의 `InspectionNotFoundError`에도 유지됩니다. timeout과 연결 실패는 서버 응답이 없으므로 요청 ID가 없고, 클라이언트가 임의 값을 생성하지 않습니다.

Streamlit은 다음 오류 흐름에서 검증된 요청 ID가 있을 때만 기존 사용자 안내 뒤에 한 번 표시합니다.

- 검수 결과 저장
- 검수 이력 목록 조회
- 검수 상세 결과 조회
- 전체 검수 이력 CSV 준비
- 상세 조회 HTTP `404`

가상의 요청 ID를 사용한 표시 예시는 다음과 같습니다.

```text
검수 이력을 불러오는 중 오류가 발생했습니다.

요청 ID: a29ae9a1c62f4152bb96f6513c323d96
```

화면에는 원본 예외 메시지, 응답 본문, stack trace, DB URL, 비밀번호와 내부 호스트를 표시하지 않습니다. 운영 문제를 추적할 때는 사용자에게 안내된 요청 ID를 Railway 로그의 같은 `request_id`와 대조합니다.

- 라우트가 응답을 반환하면 상태 코드와 관계없이 `http_request_completed`를 한 번 기록합니다.
- 처리되지 않은 일반 예외는 `http_request_failed`로 기록하며, 안전한 기존 HTTP `500` 응답에도 `X-Request-ID`를 포함합니다.
- `/ready`의 DB 확인 실패는 `database_readiness_failed`와 처리된 HTTP `503` 완료 이벤트로 구분해 기록합니다.
- 로그에는 요청 본문과 CSV 내용, query parameter, 요청 헤더, DB URL, 비밀번호, 호스트, 원본 예외 메시지와 stack trace를 기록하지 않습니다.
- Uvicorn 기본 access log는 URL의 query string을 포함할 수 있으므로 Railway Start Command의 `--no-access-log`로 비활성화합니다. 이 옵션은 Uvicorn의 기본 요청 접근 로그만 끄며 FastAPI 서버 시작 로그와 애플리케이션 구조화 로그에는 영향을 주지 않습니다.
- 민감정보, 토큰, 비밀번호는 로그 설정과 관계없이 URL query string에 넣지 않습니다.

Railway Healthcheck Path는 계속 `/health`로 유지합니다. 운영 검증에서 `/health`와 `/ready`의 HTTP `200`, `/ready`의 `database: "ok"`, 정상적인 `X-Request-ID` 생성과 구조화 로그 유지를 확인했습니다. Uvicorn access log를 비활성화한 뒤 검사 query string이 Deploy Logs에 남지 않고 구조화 로그의 `path`가 `/health`로만 기록되는 것도 확인했습니다.

### `POST /api/v1/inspections`

CSV 파일을 업로드해 검수하고, 검수 실행과 상세 결과를 PostgreSQL에 저장합니다.

- 요청 형식: `multipart/form-data`
- 파일 필드명: `file`
- 정상 응답: `inspection_run_id`, `created`, `summary`, `results`
- 잘못된 CSV: HTTP `400`
- 파일 필드 누락: HTTP `422`

새로 저장된 경우 응답 예시는 다음과 같습니다.

```json
{
  "inspection_run_id": 123,
  "created": true,
  "summary": {
    "total_products": 5,
    "total_issues": 6,
    "error_count": 6,
    "warning_count": 0
  },
  "results": [
    {
      "status": "오류",
      "product_group_id": "G002",
      "product_id": "P003",
      "error_field": "가격 오류",
      "reason": "상품 가격이 0 이하입니다. 현재 가격: -5,000원.",
      "recommendation": "0보다 큰 정상 판매 가격을 입력하십시오.",
      "risk_level": "높음"
    }
  ]
}
```

같은 CSV bytes와 같은 검수 규칙 버전이 이미 저장되어 있으면 새 `inspection_run`과 `inspection_results`를 만들지 않고 기존 실행 ID를 반환합니다.

```json
{
  "inspection_run_id": 123,
  "created": false,
  "summary": {
    "total_products": 5,
    "total_issues": 6,
    "error_count": 6,
    "warning_count": 0
  },
  "results": []
}
```

`created=false`일 때는 새로 계산한 결과와 기존 ID를 섞지 않고, 기존 DB에 저장된 요약과 상세 결과를 반환합니다. API Client는 구버전 서버 호환을 위해 `created`가 없는 응답은 `true`로 처리하지만, `created`가 존재할 때는 실제 boolean 값만 허용합니다.

### `GET /api/v1/inspections`

저장된 검수 이력 목록을 조회합니다.

| Query | 기본값 | 조건 |
|---|---:|---|
| `limit` | `20` | `1` 이상 `100` 이하 |
| `offset` | `0` | `0` 이상 |
| `filename` | 없음 | 선택값, 최대 `100`자 |
| `start_date` | 없음 | 선택값, `YYYY-MM-DD` |
| `end_date` | 없음 | 선택값, `YYYY-MM-DD` |
| `status` | 없음 | 선택값, `error`, `warning`, `normal` |

응답 예시는 다음과 같습니다.

```json
{
  "items": [
    {
      "inspection_run_id": 11,
      "source_filename": "products_dev.csv",
      "created_at": "2026-07-04T13:42:39.495949+09:00",
      "total_products": 5,
      "total_issues": 6,
      "error_count": 6,
      "warning_count": 0
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### `GET /api/v1/inspections/{inspection_run_id}`

저장된 검수 실행 1건의 상세 결과를 조회합니다.

- `inspection_run_id`가 없으면 HTTP `404`
- 숫자가 아닌 ID는 HTTP `422`
- 응답에는 파일명, 저장 시각, 요약, 상세 결과 목록이 포함됩니다.

## 19. 검수 이력 검색과 전체 요약 CSV 다운로드

검수 이력 목록 API와 Streamlit 검수 이력 탭은 파일명, 날짜, 검수 상태 검색을 지원합니다.

- `filename` 검색어는 앞뒤 공백을 제거합니다.
- 공백뿐인 검색어는 검색 조건 없이 전체 목록을 조회합니다.
- 최대 길이는 `100`자입니다.
- 대소문자를 구분하지 않는 부분 검색입니다.
- 파일명 앞, 중간, 뒤 어디에 검색어가 있어도 찾습니다.
- `%`, `_`, `\` 문자는 SQL wildcard가 아니라 일반 문자로 검색되도록 이스케이프합니다.
- 정렬은 `created_at DESC`, `id DESC`입니다.
- `total`과 `items`에는 같은 검색 조건이 적용됩니다.
- `start_date`와 `end_date`는 한국 시간 기준 날짜 범위로 검색합니다.
- `status`는 `error`, `warning`, `normal` 중 하나이며, 오류는 `error_count > 0`, 주의는 `error_count == 0 and warning_count > 0`, 정상은 `error_count == 0 and warning_count == 0` 기준입니다.
- Streamlit에서 검색 버튼을 누르면 `offset`이 `0`으로 초기화됩니다.
- 상세 화면에서 목록으로 돌아오면 검색 조건과 현재 페이지 offset은 유지됩니다.
- 전체 요약 CSV 다운로드는 현재 페이지 offset을 바꾸지 않고, 검색 버튼으로 실제 적용된 조건만 사용합니다.
- 전체 요약 CSV는 `CSV 다운로드 준비` 버튼을 누를 때만 전체 조회를 실행하고, 준비된 결과를 세션에 저장한 뒤 다운로드 버튼을 표시합니다.
- API 최대 `limit=100`에 맞춰 100건씩 반복 조회하므로 검색 결과가 100건을 초과해도 전체 이력이 CSV에 포함됩니다.
- 검색 결과가 0건이면 전체 요약 CSV 다운로드 버튼을 표시하지 않고 다운로드할 이력이 없다는 안내를 보여줍니다.

예시는 다음과 같습니다.

```powershell
curl.exe "http://127.0.0.1:8001/api/v1/inspections?limit=10&offset=0&filename=products"
```

## 20. 동일 CSV 중복 저장 방지

동일 CSV 중복 저장 방지는 파일명보다 CSV bytes를 기준으로 판단합니다. FastAPI 서버가 업로드된 CSV bytes로 SHA-256 해시를 직접 계산하므로 클라이언트가 보낸 해시를 신뢰하지 않습니다.

`inspection_runs`에 저장되는 identity 컬럼은 다음과 같습니다.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `file_sha256` | `String(64)`, nullable | CSV bytes의 SHA-256 hex 문자열입니다. migration 이전 기존 이력은 NULL입니다. |
| `inspection_version` | `String(20)`, nullable 아님 | 검수 규칙 버전입니다. 현재 `INSPECTION_VERSION` 값은 `"5"`입니다. DB `server_default`는 없습니다. |

중복 판단 기준은 같은 `file_sha256`과 같은 `inspection_version`입니다.

- 파일명이 달라도 CSV bytes와 검수 버전이 같으면 같은 파일로 봅니다.
- 파일명이 같아도 CSV bytes가 다르면 새로운 이력으로 저장합니다.
- 같은 CSV라도 검수 규칙 버전이 달라지면 다시 검수하고 새 이력으로 저장할 수 있습니다.

상품 그룹 내 중복 색상·사이즈 옵션 규칙을 추가할 때 검수 버전을 `"3"`으로 올렸고, 상품 그룹 카테고리 일관성 규칙을 추가하면서 `"4"`로 올렸습니다. 이번에 선택적 `sale_price`와 정상가·할인가 관계 규칙을 추가하면서 현재 `INSPECTION_VERSION`을 `"5"`로 올렸습니다. 동일 CSV라도 버전 4와 버전 5는 별도 검수 결과로 저장할 수 있습니다. 파일 해시와 검수 버전을 함께 사용하는 기존 중복 저장 방지 기준은 그대로 유지됩니다. DB 스키마 변경은 없어 이 기능을 위한 Alembic migration은 추가하지 않았으며, 과거 이력과 기존 migration의 `"1"` backfill 값은 그대로 유지합니다.

PostgreSQL에는 다음 partial unique index가 있습니다.

```text
ux_inspection_runs_file_sha256_inspection_version
columns: file_sha256, inspection_version
where: file_sha256 IS NOT NULL
```

이 index의 의미는 다음과 같습니다.

- 기존 `file_sha256=NULL` 행은 여러 개 존재할 수 있습니다.
- migration 이후 저장되는 같은 파일과 같은 검수 버전은 한 건만 허용합니다.
- 동시에 같은 파일 저장 요청이 들어와도 DB에서 최종 차단합니다.
- 같은 파일이라도 `inspection_version`이 다르면 새 저장이 가능합니다.

추가 CHECK constraint도 있습니다.

- `file_sha256`이 NULL이 아니면 길이가 정확히 64여야 합니다.
- `inspection_version`은 빈 문자열이나 공백만 있는 문자열일 수 없습니다.

기존 migration 이전 이력은 `inspection_version="1"`로 채워지지만 `file_sha256`은 NULL입니다. 과거 원본 CSV bytes가 DB에 없으므로 해시 재생성이 불가능하고, 신규 CSV 저장 시 과거 이력과 자동으로 중복 비교되지는 않습니다. 따라서 migration 이후 같은 CSV를 처음 저장할 때는 새로운 실행 ID가 한 번 생성될 수 있습니다. 그 다음부터는 Streamlit이나 브라우저를 재시작해도 기존 실행 ID가 반환됩니다.

개발 DB에서 수동 확인한 예로, `products_dev.csv`를 최초 저장했을 때 실행 ID `6`이 생성되었고 Streamlit 재시작 후 같은 CSV를 다시 저장하자 새 실행 ID를 만들지 않고 기존 실행 ID `6`을 반환했습니다. 이 숫자는 해당 개발 DB에서의 예시일 뿐 고정된 시스템 값은 아닙니다.

## 21. 검수 결과와 CSV 다운로드 형식

검수 결과 화면과 다운로드 CSV는 다음 컬럼을 사용합니다.

```text
검수 상태, 오류 항목, 상품 그룹 ID, 상품 ID, 오류 이유, 수정 권장사항, 위험 수준
```

Streamlit CSV 검수 탭에서는 다음 필터를 적용할 수 있습니다.

- 검수 상태: `전체`, `오류`, `주의`
- 오류 항목: 전체 또는 발견된 오류 항목
- 상품 ID 검색: 대소문자 구분 없는 부분 검색

CSV 다운로드 동작은 다음과 같습니다.

- 현재 필터 결과만 CSV로 다운로드합니다.
- 다운로드 CSV는 Windows Excel에서 한글이 깨지지 않도록 UTF-8 BOM으로 생성합니다.
- DataFrame index는 CSV에 포함하지 않습니다.
- `=`, `+`, `-`, `@`로 시작하는 문자열은 CSV 수식 삽입을 막기 위해 앞에 작은따옴표를 붙입니다.
- 업로드 파일이 `products_dev.csv`이면 기본 결과 파일명은 `products_dev_validation_results.csv`입니다.
- 파일명에 Windows 예약 문자가 있으면 `_`로 바꿉니다.
- 검수 이력 상세 CSV 파일명은 `inspection_<실행ID>_<원본파일명>_results.csv` 형식입니다.
- 상세 결과가 없는 검수 실행은 상세 CSV 다운로드 버튼을 표시하지 않습니다.

검수 이력 전체 요약 CSV 다운로드는 현재 검색 조건에 맞는 모든 이력의 요약을 내려받습니다.

- 파일명 예시는 `inspection_history_20260707_153000.csv`입니다.
- CSV 인코딩은 Windows Excel 호환을 위해 UTF-8-SIG입니다.
- CSV 컬럼은 `실행 ID`, `파일명`, `검수 시간`, `전체 상품`, `전체 문제`, `오류`, `주의`, `검수 상태`입니다.
- `검수 상태`는 숫자가 아니라 `오류`, `주의`, `정상` 한글 값으로 표시합니다.
- 전체 조회 중 API 연결 실패, timeout, 서버 오류, 잘못된 응답 형식이 발생하면 일부 데이터만 담은 CSV는 제공하지 않습니다.

## 22. 샘플 데이터 검수 결과

`data/dev/products_dev.csv`를 현재 코드로 검수하면 다음 결과가 나옵니다.

```text
전체 상품 수: 5
전체 문제 수: 6
오류 수: 6
주의 수: 0
```

API로 확인하려면 FastAPI 서버를 실행한 뒤 아래 명령을 사용합니다.

```powershell
curl.exe -X POST "http://127.0.0.1:8001/api/v1/inspections" `
  -H "accept: application/json" `
  -F "file=@data/dev/products_dev.csv;type=text/csv"
```

### 패션 색상·사이즈 검수 예시

다음 상품은 알려진 별칭인 `블랙`과 `medium`을 사용합니다.

```csv
product_group_id,product_id,product_name,category,color,size,stock,price,image_path
G001,P001,오버핏 반팔 티셔츠,TOP,블랙,medium,10,19900,image.jpg
```

색상 검수 결과는 다음과 같습니다.

```text
검수 상태: 주의
오류 항목: 색상 표기 비표준
오류 이유: 색상 '블랙'은 표준값 'BLACK'으로 통일하는 것이 좋습니다.
수정 권장사항: 오류 이유에 표시된 표준 색상값으로 수정하세요.
위험 수준: 낮음
```

사이즈 검수 결과는 다음과 같습니다.

```text
검수 상태: 주의
오류 항목: 사이즈 표기 비표준
오류 이유: 사이즈 'medium'은 표준값 'M'으로 통일하는 것이 좋습니다.
수정 권장사항: 오류 이유에 표시된 표준 사이즈값으로 수정하세요.
위험 수준: 낮음
```

### 상품 그룹 내 중복 옵션 검수 예시

다음 두 행은 원본 표기는 다르지만 비교 키가 모두 `BLACK / M`입니다.

```csv
product_group_id,product_id,product_name,category,color,size,stock,price,image_path
G001,P001,기본 반팔 티셔츠 A,TOP,BLACK,M,10,19900,image1.jpg
G001,P002,기본 반팔 티셔츠 B,TOP,black,medium,10,19900,image2.jpg
```

두 상품 모두 다음 오류 결과에 연결됩니다.

```text
검수 상태: 오류
오류 항목: 상품 옵션 조합 중복
오류 이유: 상품 그룹 'G001'에서 색상 'BLACK', 사이즈 'M' 조합이 상품 ID 'P001', 'P002'에 중복되어 있습니다.
수정 권장사항: 같은 상품 그룹 안에서 색상과 사이즈 조합이 한 번만 사용되도록 중복 상품을 통합하거나 옵션 값을 수정하세요.
위험 수준: 중간
```

검수 후에도 P002의 원본 `color=black`, `size=medium` 값은 그대로 유지됩니다.

## 23. 테스트 실행 방법

DB가 필요 없는 단위 테스트와 API 테스트는 일반 환경에서 실행할 수 있습니다.

```powershell
cd C:\study\catalogguard-lite
.\.venv\Scripts\Activate.ps1
python -m pytest tests/test_api_health.py -q
python -m pytest tests/test_api_logging.py -q
python -m pytest tests/test_api_inspections.py -q
python -m pytest tests/test_catalogguard_api_client.py -q
python -m pytest tests/test_app_history_helpers.py -q
python -m pytest tests/test_app_history_download_helpers.py -q
python -m pytest tests/test_app_inspection_save_helpers.py -q
```

요청 ID 전달 관련 테스트는 다음 명령으로 한 번에 실행합니다.

```powershell
python -m pytest tests/test_catalogguard_api_client.py tests/test_app_history_helpers.py tests/test_app_smoke.py -q
```

PostgreSQL 통합 테스트를 포함하려면 `TEST_DATABASE_URL`을 설정하고 테스트 DB에 마이그레이션을 적용합니다.

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://catalogguard_test_user:CHANGE_ME@localhost:5432/catalogguard_lite_test"
$env:DATABASE_URL=$env:TEST_DATABASE_URL
python -m alembic upgrade head
python -m pytest tests/test_inspection_persistence.py -q
```

전체 테스트는 다음 명령으로 실행합니다.

```powershell
python -m pytest -q
```

### 로컬 테스트 결과

현재 로컬 환경에서 확인된 테스트 결과는 다음과 같습니다.

```text
831 passed, 26 skipped, 2 deselected
```

이 수치는 현재 개발 PC에서 기본 pytest 설정으로 실행한 로컬 결과입니다. `e2e`·`performance` marker는 기본 실행에서 제외되고, PostgreSQL·Redis 등 별도 서비스가 필요한 일부 검증은 로컬 환경에 따라 skipped 처리됩니다. ETL 테스트와 `tests/test_api_inspections.py`를 함께 실행한 통합 검증은 `89 passed`였고, 샘플 공급사 CSV CLI는 전체 3건 중 정상 2건·오류 1건을 종료 코드 0으로 처리했습니다. GitHub Actions의 실행 결과와 테스트 개수는 별도로 확인해야 하며, 이 문서의 로컬 수치를 CI 수치로 해석하면 안 됩니다.

### 동기 검수 성능 측정

`scripts/benchmark_inspection.py`는 합성 CSV를 사용해 동기 검수 1회와 같은 입력을 연속 2회 검수하는 경우의 중앙 실행 시간과 Python 추적 메모리를 비교합니다. 기본 설정은 행 수 `100, 1,000, 5,000, 10,000`, 워밍업 1회, 반복 3회이며, 결과는 `tests/test_benchmark_inspection.py`로 검증합니다.

측정 환경은 Python 3.11.9, Windows 10.0.26200, Intel Core i7-14700F 기반의 개발 PC입니다.

개발 PC에서 측정한 대표 결과는 다음과 같습니다.

| 행 수 | 입력 크기 | 문제 수 | 1회 중앙값 | 연속 2회 중앙값 | Python peak |
|---:|---:|---:|---:|---:|---:|
| 100 | 0.016 MiB | 15 | 0.009544초 | 0.018815초 | 0.177 MiB |
| 1,000 | 0.156 MiB | 149 | 0.074266초 | 0.150817초 | 1.603 MiB |
| 5,000 | 0.781 MiB | 757 | 0.371740초 | 0.867245초 | 6.485 MiB |
| 10,000 | 1.563 MiB | 1,507 | 0.875495초 | 1.645721초 | 12.939 MiB |

측정상 시간과 Python 추적 메모리는 행 수에 따라 대체로 선형으로 증가했고, 같은 검수를 두 번 수행하면 1회 대비 약 1.88~2.33배가 걸렸습니다. 10,000행 1회 검수는 개발 PC에서 약 0.88초였습니다. 이 결과는 동기 검수 중복 제거를 우선한 근거이며, AWS나 대규모 트래픽 성능을 보증하는 수치는 아닙니다. `tracemalloc`은 Python이 추적한 메모리만 포함하므로 Pandas/C 확장과 OS 전체 프로세스 메모리는 포함하지 않을 수 있습니다.

재현 명령:

```powershell
python scripts/benchmark_inspection.py --rows 100 1000 5000 10000 --repeat 3 --warmup 1 --output artifacts/inspection_benchmark.json
```

측정 환경은 로컬 개발 PC이며 DB·네트워크 시간, 실제 동시 접속과 운영 트래픽은 포함하지 않습니다. 이 측정은 Streamlit과 FastAPI의 이중 검수를 제거하는 근거로 사용했습니다. 현재 비동기 경로는 Redis/Celery로 요청 수명과 검수 작업을 분리하지만, 대규모 트래픽 성능을 입증하는 자료로 해석하지 않습니다.

### GitHub Actions 자동 테스트

`.github/workflows/test.yml`의 `Test` workflow는 `main` 브랜치 push와 `main` 브랜치를 대상으로 한 pull request에서 실행됩니다. `ubuntu-latest` 환경에 Python 3.11을 준비하고 PostgreSQL 18·Redis 7.4 서비스 컨테이너를 시작한 뒤, 의존성을 설치하고 Alembic 마이그레이션을 적용합니다. 이어서 E2E를 제외한 전체 pytest, 실제 Celery Worker와 FastAPI 프로세스, 비동기 CSV 검수 E2E 스모크 테스트, Streamlit 시작 스모크 테스트를 실행합니다.

```text
main push 또는 main 대상 pull request
-> GitHub Actions Test workflow
-> PostgreSQL 18·Redis 7.4 서비스 컨테이너
-> Python 3.11과 의존성 설치
-> Alembic upgrade head
-> E2E 제외 전체 pytest 1회 실행
-> Celery Worker와 FastAPI 프로세스 시작
-> /health·/ready 확인
-> 비동기 CSV 제출, 상태 polling, 결과·중복 재사용·임시 파일 정리 E2E 확인
-> 실패 시 FastAPI·Celery 로그 출력 및 프로세스 정리
-> Streamlit 서버 시작
-> /_stcore/health 응답 확인
-> Streamlit 프로세스 종료
```

서비스 컨테이너는 workflow가 실행되는 동안만 사용하는 일회성 PostgreSQL·Redis CI 테스트 구성입니다. Railway나 운영 PostgreSQL·Redis에 연결하지 않으며, E2E를 제외한 단위 테스트와 실제 PostgreSQL 연결·저장 통합 테스트를 함께 실행합니다.

비동기 E2E 테스트는 기본 `pytest`에서 `e2e` marker로 제외하고, workflow에서만 다음 명령으로 명시 실행합니다. 이 검사는 테스트용 PostgreSQL·Redis, FastAPI, Celery Worker가 모두 준비된 환경을 요구하며 운영 Redis·Celery 배포 검증과는 구분됩니다.

```bash
python -m pytest -m e2e tests/e2e/test_async_inspection_ci.py -q
```

Streamlit 시작 스모크 테스트는 `python -m streamlit run app.py`로 실제 서버를 `127.0.0.1:8501`에서 실행하고, 최대 30초 동안 `/_stcore/health`를 반복 확인합니다. 각 요청에는 1초의 연결 제한과 2초의 전체 제한을 적용합니다. HTTP `200`을 받은 뒤에도 2초 동안 프로세스가 살아 있는지 확인하므로, Streamlit 실행 명령이 성공하고 서버 Health endpoint가 응답하는 시작 단계를 검사합니다.

성공과 실패 경로 모두 `trap cleanup EXIT`로 프로세스를 정리합니다. 먼저 SIGTERM을 보낸 뒤 최대 5초 동안 기다리고, 종료되지 않으면 SIGKILL을 보낸 다음 `wait`로 프로세스를 회수합니다. 실패 시에는 마지막 `curl` 종료 코드, HTTP 상태, 응답 본문, 오류와 Streamlit 시작 로그를 출력해 원인을 확인할 수 있게 합니다.

이 Step에서는 `CATALOGGUARD_API_BASE_URL`, `CATALOGGUARD_API_TIMEOUT_SECONDS`, `DATABASE_URL`, `TEST_DATABASE_URL`을 빈 값으로 덮어씁니다. 따라서 Railway 운영 API나 운영 PostgreSQL에 연결하거나 운영 데이터와 검수 이력을 읽고 저장하지 않고, Streamlit 서버 자체가 시작되는지만 확인합니다. 환경변수의 실제 값과 Secret은 workflow 로그나 문서에 기록하지 않습니다.

`tests/test_app_smoke.py`의 AppTest는 `app.py`의 초기 화면이 예외 없이 렌더링되고 API 주소가 없을 때 안전한 안내가 표시되는지 확인합니다. 또한 6행 카테고리 일관성 CSV를 실제 업로드해 요약 수치, 원본 미리보기, 참여 상품별 한글 결과, 상태·규칙·상품 ID 필터와 결과 CSV 다운로드 생성을 확인합니다. GitHub Actions의 시작 스모크 테스트는 실제 Streamlit 서버 프로세스, 포트와 Health 응답을 확인하므로 두 검사는 서로 다른 범위를 보완합니다.

AppTest는 실제 `app.py` 실행 경로의 CSV 업로드와 검수·필터 위젯을 검증하지만 실제 브라우저의 파일 선택 창이나 픽셀 렌더링까지 자동화하지는 않습니다. GitHub Actions 스모크 테스트도 Railway API 실제 통신, 운영 Secrets 설정, Streamlit Community Cloud 전용 장애나 모든 Segmentation fault를 검증하지 않습니다.

GitHub Actions에서는 PostgreSQL 테스트 DB를 제공하므로 로컬에서 건너뛴 DB 통합 테스트까지 실행합니다. 실제 CI 통과 여부와 실행 시간은 해당 커밋의 `Test` workflow 결과에서 확인해야 하며, 위 로컬 테스트 수치와 구분합니다.

## 24. 데이터 저장 범위와 보안

PostgreSQL에는 검수 실행 요약, 표시용 상세 결과, 파일 동일성 확인용 해시와 검수 규칙 버전을 저장합니다.

저장하는 값은 다음과 같습니다.

- 업로드 파일의 파일명
- SHA-256 파일 해시
- 검수 규칙 버전
- 전체 상품 수
- 전체 문제 수
- 오류 수
- 주의 수
- 검수 실행 생성 시각
- 상세 결과의 상품 그룹 ID
- 상세 결과의 상품 ID
- 검수 상태
- 오류 항목
- 오류 이유
- 수정 권장사항
- 위험 수준

저장하지 않는 값은 다음과 같습니다.

- 원본 CSV 파일 bytes
- 원본 CSV 전체 내용
- 상품 설명 원문 전체
- 판매자 정보 원문 전체
- 이메일 원문
- 전화번호 원문
- 주민등록번호 형태 원문
- 이미지 파일

개인정보 의심 값은 검수 결과 메시지에 마스킹된 형태로 들어갑니다. 예를 들어 `demo.user@example.com`, `010-1234-5678`, `900101-1234567` 같은 값은 API 응답과 DB 저장 결과에서 각각 `de*******@example.com`, `010-****-5678`, `900101-*******`처럼 표시됩니다.

SHA-256 해시는 파일 동일성 확인용입니다. 해시만으로 원본 CSV를 복원할 수 없으며, 원본 CSV bytes나 전체 원문은 DB에 저장하지 않습니다.

파일명 저장 시 경로가 들어와도 파일명만 남깁니다. 파일명이 비어 있으면 `uploaded.csv`를 사용하고, 최대 `255`자로 제한합니다.

API 클라이언트는 연결 실패, timeout, 서버 오류를 사용자용 메시지로 바꾸며 내부 URL이나 서버 응답 본문을 그대로 노출하지 않도록 테스트되어 있습니다.

## 25. 현재 한계

- MVP 단계의 규칙 기반 검사이므로 실제 운영 정책에 맞춘 금지어와 개인정보 탐지 조정이 필요합니다.
- 개인정보 탐지는 정규식 기반이므로 오탐과 미탐 가능성이 있습니다.
- 허용 카테고리는 현재 `TOP`, `BOTTOM`, `OUTER` 3개입니다.
- 패션 색상·사이즈 검수는 별칭 사전의 정확 일치만 지원하며 오타 유사도는 검사하지 않습니다.
- 사용자 정의·복합 색상과 숫자 사이즈는 비표준 표기 경고 대상으로 판단하지 않습니다.
- 중복 옵션 조합을 자동 병합하거나 중복 상품을 자동 삭제하지 않습니다.
- 누락된 색상·사이즈 옵션 조합을 추론하지 않습니다.
- 중복 옵션별 재고를 합산하지 않습니다.
- 상품명과 상품 그룹의 일치 여부를 판단하지 않습니다.
- 그룹에서 정답 category를 자동 선택하거나 category 값을 자동 수정하지 않습니다.
- 상품명에서 그룹의 category를 자동 추론하지 않습니다.
- category 계층 관계를 비교하거나 상품 그룹을 자동 분리하지 않습니다.
- 카테고리별 가격 이상치는 같은 카테고리의 유효 가격이 5개 이상일 때만 계산됩니다.
- migration 이전 기존 이력은 `file_sha256=NULL`이라 과거 이력까지 소급해 중복 판단할 수 없습니다.
- `INSPECTION_VERSION`은 검수 규칙이 변경될 때 개발자가 직접 올려야 합니다.
- 공개 Streamlit 앱에서는 FastAPI와 PostgreSQL 연동 상태에 따라 검수 이력 기능을 사용할 수 없을 수 있습니다.
- 인증과 권한 관리는 구현되어 있지 않습니다.
- 저장된 검수 이력 삭제 기능은 구현되어 있지 않습니다.
- 전체 요약 CSV는 목록 API를 반복 조회하므로 다운로드 중 DB 내용이 바뀌는 상황의 완전한 스냅샷 보장은 별도 트랜잭션/내보내기 API가 필요합니다.
- `.env` 자동 로딩은 구현되어 있지 않으므로 로컬에서는 PowerShell 환경변수를 직접 설정해야 합니다.

## 26. 향후 개선 방향

- 운영 정책에 맞는 금지어, 개인정보, 카테고리 규칙 확장
- 검수 규칙 변경 시 `inspection_version` 관리 정책 수립
- 과거 이력 backfill 정책 검토
- 검수 이력 삭제와 보관 정책
- 인증과 사용자별 이력 분리
- 중복 저장 이벤트 로그 또는 감사 기록 검토
- 기간별 검수 추세와 파일 간 비교 통계 추가
- 대용량 CSV 처리 성능 개선
- 카테고리와 가격 이상치 기준을 설정 파일이나 관리 화면에서 조정
- 상품 그룹 내 상품명 일관성 검수
- 카테고리별 사이즈 형식 검수
- 브랜드 표준화
- `gender` 선택 컬럼과 표준화

## 27. 개발 시 주의사항

- 원본 CSV 파일과 원문 개인정보를 DB에 저장하지 않는 현재 원칙을 유지합니다.
- 검수 결과 컬럼을 바꾸면 `core/presentation.py`, `api/routes/inspections.py`, `db/persistence_service.py`, `app.py`의 상세 CSV 변환 로직과 관련 테스트를 함께 확인합니다.
- DB 모델을 바꾸면 SQLAlchemy 모델과 Alembic 마이그레이션을 함께 수정합니다.
- 검수 규칙을 바꿔 같은 CSV도 다시 검수해야 하는 경우 `config/settings.py`의 `INSPECTION_VERSION`을 함께 올립니다.
- `inspection_version`에는 DB `server_default`를 두지 않고 애플리케이션에서 명시적으로 저장합니다.
- `DATABASE_URL`, `TEST_DATABASE_URL` 같은 비밀번호 포함 환경변수는 저장소에 커밋하지 않습니다.
- `requirements.txt`와 `requirements-api.txt`의 역할이 나뉘어 있으므로 로컬 전체 시스템에서는 두 파일을 모두 설치합니다.
- 파일명 검색을 수정할 때는 `%`, `_`, `\`가 일반 문자처럼 검색되는지 확인합니다.
- Streamlit 세션 중복 방지와 DB 수준 중복 방지는 역할이 다르므로 둘 다 유지합니다.
- 문서에 새 기능을 추가하기 전에는 실제 코드와 테스트가 먼저 구현되어 있는지 확인합니다.
## SQL 쿼리·인덱스 성능 분석

PostgreSQL 18의 격리 테스트 DB에서 검수 실행 10,000건과 상세 결과 100,000건을 생성하고 동일 CSV, 이력 목록·count, 상세 조회를 `EXPLAIN ANALYZE BUFFERS`로 측정했습니다. 기존 인덱스가 핵심 조회에 사용되었고 새 후보 인덱스의 실질 이득이 확인되지 않아 migration과 Repository 쿼리는 변경하지 않았습니다.

재현 가능한 opt-in 성능 테스트와 실행 계획, 후보 인덱스를 기각한 근거는 [SQL 성능 분석 문서](docs/sql_performance_analysis.md)에 정리했습니다. 기본 pytest에서는 성능 테스트를 제외하며, 전용 test/perf DB에서만 다음과 같이 실행합니다.

```powershell
$env:RUN_SQL_PERFORMANCE="1"
python -m pytest -m performance tests/performance/test_inspection_query_performance.py -s -q
```

## 공급사 CSV ETL MVP

`etl.cli`는 샘플 패션 공급사 CSV를 CatalogGuard 표준 CSV로 변환합니다. JSON 프로필로 공급사 컬럼을 매핑하고, `discount_price`를 선택 표준 컬럼 `sale_price`로 변환합니다. 변환할 수 없는 행은 오류 코드와 함께 별도 CSV로 분리하며, 정상가보다 큰 할인가 같은 상품 품질 문제는 정상 행으로 남겨 기존 검수기가 처리하도록 합니다. 결과 CSV는 기존 업로드 검증과 검수 서비스에 그대로 전달할 수 있습니다.

```powershell
python -m etl.cli `
  --input .\tests\fixtures\etl\sample_vendor_mixed.csv `
  --profile .\config\etl\sample_fashion_vendor_v1.json `
  --output .\output\catalogguard_ready.csv `
  --rejects .\output\rejected_rows.csv `
  --summary .\output\etl_summary.json
```

프로필 구조, 변환·오류 기준, 생성 파일과 제한사항은 [ETL MVP 문서](docs/etl_mvp.md)를 참고하세요.
