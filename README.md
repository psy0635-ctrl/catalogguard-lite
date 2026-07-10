<!-- 역할: CatalogGuard Lite 프로젝트의 기능, 실행 방법, 구조를 설명하는 메인 문서입니다. -->

# CatalogGuard Lite

상품 카탈로그 CSV를 업로드해 누락, 형식 오류, 중복, 가격 이상치, 카테고리 불일치, 금지어와 개인정보 의심 정보를 검사하고, 검수 결과를 저장·검색·조회·다운로드하는 Streamlit + FastAPI 기반 MVP입니다.

공개 Streamlit 앱은 아래 주소에서 확인할 수 있습니다.

https://catalogguard-lite-p6jtwmdhwqcapphpghfzduo.streamlit.app/

> 공개 Streamlit 앱과 로컬 전체 시스템의 기능 범위는 다를 수 있습니다. PostgreSQL 저장, 검수 이력 검색, 검수 이력 상세 조회 기능은 로컬 또는 별도 배포 환경에서 FastAPI 서버와 PostgreSQL이 함께 실행되어야 사용할 수 있습니다.

## 2. 프로젝트 목적

CatalogGuard Lite는 상품 운영자가 CSV로 관리하는 상품 목록을 업로드한 뒤, 등록 전에 발견해야 할 데이터 품질 문제를 빠르게 확인하도록 만든 경량 검수 도구입니다.

주요 목표는 다음과 같습니다.

- 필수 상품 정보가 빠진 행을 찾습니다.
- 잘못된 카테고리, 재고, 가격 값을 찾습니다.
- 같은 상품 ID, 비슷한 상품명, 완전히 같은 상품 내용을 찾습니다.
- 상품명과 카테고리가 서로 어울리지 않는 경우를 찾습니다.
- 금지어, 이메일, 전화번호, 주민등록번호 형식, 계좌번호 의심 정보를 찾습니다.
- 검수 결과를 화면, CSV 다운로드, PostgreSQL 이력으로 확인할 수 있게 합니다.

## 3. 주요 기능

- CSV 입력 템플릿 다운로드
- CSV 업로드와 상위 100행 미리보기
- 파일 확장자, 파일 크기, 인코딩, 헤더, 행 수 검증
- 개인정보 의심 값 마스킹
- 필수값 누락 탐지
- 잘못된 데이터 형식 탐지
- 상품 ID, 상품명, 상품 내용 중복 탐지
- 가격 오류와 카테고리별 가격 이상치 탐지
- 상품명과 카테고리 불일치 탐지
- 금지어와 위험 표현 탐지
- 이메일, 전화번호, 주민등록번호, 계좌번호 의심 정보 탐지
- 상태, 오류 항목, 상품 ID 기준 검수 결과 필터
- 현재 필터 결과 CSV 다운로드
- 검수 결과 PostgreSQL 저장
- 검수 이력 목록 조회와 페이지 이동
- 파일명 부분 검색
- 검수 이력 상세 조회
- 상세 결과 CSV 다운로드
- 같은 Streamlit 세션 안에서 동일 CSV 중복 저장 방지
- PostgreSQL DB 수준 동일 CSV 중복 저장 방지

## 4. 사용자 기능 흐름

```text
CSV 검수 탭
-> CSV 입력 템플릿 다운로드
-> 상품 CSV 작성
-> CSV 파일 업로드
-> 파일명, 크기, 인코딩, 헤더, 행 수 검증
-> 개인정보가 마스킹된 미리보기 확인
-> 검수 요약 확인
-> 오류/주의 상세 결과 확인
-> 상태, 오류 항목, 상품 ID로 필터
-> 현재 필터 결과 CSV 다운로드
-> 검수 이력에 저장
```

```text
검수 이력 탭
-> FastAPI 서버 연결
-> 저장된 검수 이력 목록 조회
-> 파일명 검색
-> 이전/다음 페이지 이동
-> 검수 실행 선택
-> 상세 결과 조회
-> 상세 결과 CSV 다운로드
-> 목록으로 돌아가기
```

같은 CSV를 이미 저장한 경우에는 PostgreSQL에 저장된 파일 해시와 검수 규칙 버전을 기준으로 기존 실행 ID를 안내합니다. 같은 Streamlit 세션 안에서는 `saved_file_hash`, `saved_inspection_run_id` 상태값으로 저장 API 재호출을 줄이고, 브라우저나 Streamlit 서버를 재시작한 뒤에는 DB의 중복 제약조건으로 새 이력이 중복 생성되지 않도록 막습니다.

## 5. 전체 시스템 구조

CSV를 검수하는 기본 흐름은 Streamlit과 공통 검수 서비스가 담당합니다.

```text
CSV 업로드
-> Streamlit app.py
-> core.upload_validator
-> core.inspection_service
-> core.rules
-> core.presentation
-> 검수 결과 화면
-> 현재 필터 결과 CSV 다운로드
```

검수 결과를 저장할 때는 Streamlit이 FastAPI에 원본 업로드 파일을 다시 보내고, FastAPI가 CSV bytes의 SHA-256 해시를 직접 계산합니다. 서버는 `file_sha256`과 `inspection_version`으로 기존 이력을 먼저 조회하고, 같은 파일과 같은 검수 버전이 이미 있으면 새 실행을 만들지 않고 기존 ID를 반환합니다.

```text
CSV 업로드
-> Streamlit에서 검수 실행
-> 저장 버튼 클릭
-> CatalogGuardApiClient
-> FastAPI POST /api/v1/inspections
-> CSV bytes의 SHA-256 계산
-> file_sha256 + inspection_version으로 기존 이력 조회
-> 기존 이력이 있으면 기존 ID 반환
-> 기존 이력이 없으면 새 실행과 상세 결과 저장
-> PostgreSQL partial unique index가 동시 요청 중복 차단
```

세션 중복 방지는 같은 Streamlit 세션에서 같은 버튼을 반복 클릭할 때 API 요청을 줄이는 장치입니다. DB 중복 방지는 PostgreSQL 저장 데이터를 기준으로 판단하므로 브라우저나 Streamlit을 재시작해도 동작하고, 동시에 들어오는 동일 저장 요청도 unique index로 최종 차단합니다.

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

검수 로직에서는 원본 DataFrame과 마스킹된 미리보기 DataFrame을 분리합니다.

```text
원본 DataFrame
-> Product 객체 변환
-> 실제 검수 규칙에 사용

마스킹된 DataFrame 복사본
-> Streamlit 미리보기에만 사용
```

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

현재 저장소에는 검수 이력 화면 이미지가 없습니다. 추후 화면 캡처를 추가하면 이 섹션에 검수 이력 목록, 파일명 검색, 상세 결과 화면을 함께 넣을 수 있습니다.

## 7. 기술 스택

| 영역 | 기술 |
|---|---|
| 화면 | Streamlit `1.58.0` |
| API | FastAPI `0.139.0`, Uvicorn `0.49.0`, Pydantic |
| 데이터 처리 | Python `3.11`, pandas `3.0.3` |
| API 클라이언트 | requests `2.34.2` |
| 데이터베이스 | PostgreSQL, SQLAlchemy `2.0.51`, psycopg `3.3.4` |
| 마이그레이션 | Alembic `1.18.5` |
| 테스트 | pytest |

`requirements.txt`에는 Streamlit 앱 실행에 필요한 기본 패키지가 있고, `requirements-api.txt`에는 FastAPI와 PostgreSQL 저장 계층에 필요한 패키지가 있습니다. FastAPI도 pandas 기반 검수 로직을 사용하므로 로컬 전체 시스템을 실행할 때는 두 파일을 모두 설치하는 것이 안전합니다.

## 8. 프로젝트 폴더 구조

```text
catalogguard-lite/
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
  config/
    database.py
    settings.py
  core/
    __init__.py
    category_mismatch_detector.py
    duplicate_detector.py
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
    portfolio_project.md
  tests/
    test_api_health.py
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
    test_inspection_persistence.py
    test_loader.py
    test_presentation.py
    test_price_anomaly_detector.py
    test_privacy.py
    test_product_template.py
    test_result_exporter.py
    test_rules.py
    test_upload_validator.py
  .env.example
  alembic.ini
  requirements.txt
  requirements-api.txt
```

## 9. 주요 파일 역할

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit 화면, CSV 검수 탭, 검수 이력 탭, 검수 저장 버튼, 이력 목록·상세 화면, CSV 다운로드 연결 |
| `clients/catalogguard_api.py` | Streamlit에서 FastAPI 검수 이력 API를 호출하는 클라이언트 |
| `api/main.py` | FastAPI 앱 생성, 라우터 등록, `/health`와 `/ready` 등록 |
| `api/routes/inspections.py` | 검수 생성, 서버 SHA-256 계산, 중복 이력 응답, 검수 이력 목록, 검수 상세 조회 API |
| `api/schemas.py` | `created` 필드를 포함한 API 응답 Pydantic 모델 |
| `config/settings.py` | CSV 컬럼, 허용 카테고리, 업로드 제한, 금지어, API 클라이언트 환경변수, `INSPECTION_VERSION` |
| `config/database.py` | `DATABASE_URL`, `TEST_DATABASE_URL` 환경변수 읽기와 검증 |
| `core/inspection_service.py` | Streamlit과 FastAPI가 함께 쓰는 CSV 검수 전체 흐름 |
| `core/upload_validator.py` | 업로드 CSV 파일명, 크기, 인코딩, 헤더, 행 수 검증 |
| `core/rules.py` | 전체 검수 규칙 실행 |
| `core/presentation.py` | 내부 검수 문제를 화면용 한글 결과표로 변환 |
| `core/result_exporter.py` | 검수 결과 CSV 다운로드 데이터와 파일명 생성 |
| `core/product_template.py` | CSV 입력 템플릿 생성 |
| `core/privacy.py` | 개인정보 정규식과 마스킹 처리 |
| `db/models.py` | 파일 해시와 검수 버전 컬럼을 포함한 `inspection_runs`, `inspection_results` SQLAlchemy 모델 |
| `db/repositories.py` | 검수 실행과 상세 결과 저장·조회, 파일 identity 조회 Repository |
| `db/persistence_service.py` | 검수 결과 저장 트랜잭션, 중복 조회, 경쟁 상태 처리, 목록 조회, 상세 조회 Service |
| `db/session.py` | SQLAlchemy 엔진, 세션 팩토리, DB 연결 확인, FastAPI 세션 의존성 |
| `alembic/versions/20260703_0001_create_inspection_tables.py` | 검수 이력 저장 테이블 생성 마이그레이션 |
| `alembic/versions/20260705_0002_add_inspection_file_identity.py` | 파일 해시와 검수 버전 컬럼, CHECK constraint, partial unique index 추가 마이그레이션 |
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

선택 컬럼은 2개입니다.

| 컬럼 | 설명 |
|---|---|
| `description` | 상품 설명 |
| `seller` | 판매자 정보 |

허용 카테고리는 다음 3개입니다.

```text
TOP
BOTTOM
OUTER
```

CSV 템플릿 다운로드 파일명은 `catalogguard_product_template.csv`입니다.

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

### Railway FastAPI 배포 설정

production 환경에는 `catalogguard-lite` FastAPI 서비스와 `Postgres` PostgreSQL 서비스가 배포되어 있습니다. API 의존성은 `requirements-api.txt`에 분리되어 있으므로 Railway 대시보드에서 Build Command는 비워 두고, 다음 설정을 사용합니다.

```text
Root Directory: /
Build Command: (비워 둠)
RAILPACK_INSTALL_CMD: python -m venv /app/.venv && /app/.venv/bin/python -m pip install -r requirements-api.txt
Pre-deploy Command: cd /app && /app/.venv/bin/alembic upgrade head
Start Command: cd /app && /app/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port $PORT
Healthcheck Path: /health
DATABASE_URL: Postgres 서비스의 DATABASE_URL을 Reference Variable로 연결
```

실제 `DATABASE_URL` 값이나 비밀번호는 저장소에 기록하지 않습니다. Start Command에는 운영 배포용으로 `--reload`, `127.0.0.1`, 고정 포트 `8000`을 넣지 않습니다. `/health`는 FastAPI 프로세스 상태만 빠르게 확인하며 PostgreSQL 연결까지 확인하지 않습니다.

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

공개 확인 주소는 https://catalogguard-lite-production.up.railway.app/ready 입니다. 아직 이 코드가 운영에 배포되기 전이므로, 코드 배포 후 `/ready` 응답을 별도로 확인해야 합니다. 안정성이 확인될 때까지 Railway Healthcheck Path는 `/health`로 유지합니다.

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
| `inspection_version` | `String(20)`, nullable 아님 | 검수 규칙 버전입니다. 현재 `INSPECTION_VERSION` 값은 `"1"`입니다. DB `server_default`는 없습니다. |

중복 판단 기준은 같은 `file_sha256`과 같은 `inspection_version`입니다.

- 파일명이 달라도 CSV bytes와 검수 버전이 같으면 같은 파일로 봅니다.
- 파일명이 같아도 CSV bytes가 다르면 새로운 이력으로 저장합니다.
- 같은 CSV라도 검수 규칙 버전이 달라지면 다시 검수하고 새 이력으로 저장할 수 있습니다.

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

## 23. 테스트 실행 방법

DB가 필요 없는 단위 테스트와 API 테스트는 일반 환경에서 실행할 수 있습니다.

```powershell
cd C:\study\catalogguard-lite
.\.venv\Scripts\Activate.ps1
python -m pytest tests/test_api_health.py -q
python -m pytest tests/test_api_inspections.py -q
python -m pytest tests/test_catalogguard_api_client.py -q
python -m pytest tests/test_app_history_helpers.py -q
python -m pytest tests/test_app_history_download_helpers.py -q
python -m pytest tests/test_app_inspection_save_helpers.py -q
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

현재 확인된 테스트 결과는 다음과 같습니다.

```text
534 passed, 25 skipped, 1 warning
```

이 결과는 `python -m pytest -q -rs`로 확인했습니다. 현재 환경에는 `TEST_DATABASE_URL`이 설정되지 않아 PostgreSQL 연결 및 저장 통합 테스트 25개는 skipped 처리되었습니다. warning은 기능 실패가 아니라 `.pytest_cache` 디렉터리 생성 권한과 관련된 `PytestCacheWarning`입니다.

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
- 카테고리별 가격 이상치는 같은 카테고리의 유효 가격이 5개 이상일 때만 계산됩니다.
- migration 이전 기존 이력은 `file_sha256=NULL`이라 과거 이력까지 소급해 중복 판단할 수 없습니다.
- `INSPECTION_VERSION`은 검수 규칙이 변경될 때 개발자가 직접 올려야 합니다.
- 공개 Streamlit 앱에서는 FastAPI와 PostgreSQL 연동 상태에 따라 검수 이력 기능을 사용할 수 없을 수 있습니다.
- 인증과 권한 관리는 구현되어 있지 않습니다.
- 저장된 검수 이력 삭제 기능은 구현되어 있지 않습니다.
- 전체 요약 CSV는 목록 API를 반복 조회하므로 다운로드 중 DB 내용이 바뀌는 상황의 완전한 스냅샷 보장은 별도 트랜잭션/내보내기 API가 필요합니다.
- 검수 이력 화면 이미지는 아직 저장소에 없습니다.
- `.env` 자동 로딩은 구현되어 있지 않으므로 로컬에서는 PowerShell 환경변수를 직접 설정해야 합니다.

## 26. 향후 개선 방향

- 운영 정책에 맞는 금지어, 개인정보, 카테고리 규칙 확장
- 검수 규칙 변경 시 `inspection_version` 관리 정책 수립
- 과거 이력 backfill 정책 검토
- 날짜 범위와 상태별 이력 검색
- 검수 이력 삭제와 보관 정책
- 인증과 사용자별 이력 분리
- 중복 저장 이벤트 로그 또는 감사 기록 검토
- 검수 이력 화면 스크린샷 문서화
- 원본 CSV를 저장하지 않는 범위 안에서 통계 리포트 강화
- 테스트 DB 준비 자동화와 CI 연동
- 대용량 CSV 처리 성능 개선
- 카테고리와 가격 이상치 기준을 설정 파일이나 관리 화면에서 조정

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
