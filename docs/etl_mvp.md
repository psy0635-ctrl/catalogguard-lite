# 공급사 상품 CSV ETL MVP

## 목적

샘플 패션 공급사의 CSV를 CatalogGuard Lite 검수기가 읽을 수 있는 표준 CSV로 변환하고, 변환 결과와 요약 JSON을 PostgreSQL staging에 배치 적재한다. 파일 변환과 DB 적재는 별도 CLI로 실행한다.

## 지원 프로필

`config/etl/sample_fashion_vendor_v1.json`은 첫 번째 합성 공급사 컬럼을 지원한다.

| 원본 컬럼 | CatalogGuard 대상 컬럼 | 처리 |
|---|---|---|
| `vendor_sku` | `product_group_id`, `product_id` | 공백 제거, 앞자리 0 유지 |
| `item_name` | `product_name` | 공백 제거 |
| `main_category` | `category` | 공백 제거 |
| `brand_name` | `seller` | 공백 제거 |
| `list_price` | `price` | `12,000`, `₩12,000`을 정수 문자열로 변환 |
| `discount_price` | `sale_price` | 비어 있으면 빈 값으로 유지하고, 입력되면 `price`와 같은 가격 파서로 변환 |
| `colour`, `size_name` | `color`, `size` | 공백 제거만 수행 |
| `quantity` | `stock` | 음수가 아닌 정수로 변환, 빈 값은 `0` |
| `description_text` | `description` | 공백 제거 |
| `image_link` | `image_path` | 공백 제거 |

샘플 공급사에는 별도 상품 그룹 컬럼이 없으므로 `vendor_sku`를 `product_group_id`와 `product_id`에 함께 매핑한다. 따라서 서로 다른 SKU가 하나의 그룹으로 잘못 묶이지 않는다. 동일 상품의 옵션 행을 그룹으로 묶어야 하는 공급사는 실제 그룹 식별 컬럼을 두 대상에 맞게 별도 프로필로 매핑해야 한다. 원본 `discount_price`는 표준 CSV의 선택 컬럼 `sale_price`로 변환되며, 기존 CSV에 해당 컬럼이 없어도 업로드·검수할 수 있다.

현재 저장소에는 서로 다른 컬럼 구조를 검증하기 위한 합성 공급사 프로필 2종이 있다.

| 프로필 | 그룹·SKU 구조 | 확인한 범위 |
|---|---|---|
| `sample_fashion_vendor_v1.json` | `vendor_sku` 하나를 `product_group_id`와 `product_id`에 함께 매핑 | 단일 공급사 SKU 기반 변환 |
| `sample_marketplace_vendor_v1.json` | `style_id`와 `sku_code`를 각각 `product_group_id`, `product_id`에 매핑 | 그룹 ID와 개별 SKU가 분리된 변환 |

### 두 번째 프로필 매핑

`config/etl/sample_marketplace_vendor_v1.json`은 다음 매핑을 사용한다.

| 원본 컬럼 | CatalogGuard 컬럼 |
|---|---|
| `style_id` | `product_group_id` |
| `sku_code` | `product_id` |
| `title` | `product_name` |
| `category_code` | `category` |
| `label` | `seller` |
| `regular_price` | `price` |
| `promo_price` | `sale_price` |
| `tone` | `color` |
| `fit_size` | `size` |
| `available_qty` | `stock` |
| `details` | `description` |
| `photo` | `image_path` |

`promo_price`와 `available_qty`는 선택 입력이다. 빈 `promo_price`는 빈 `sale_price`로 출력하고, 빈 `available_qty`는 기본값 `0`을 적용한다.

## 프로필 형식

```json
{
  "profile_name": "sample_fashion_vendor",
  "profile_version": "1",
  "source_columns": {"vendor_sku": ["product_group_id", "product_id"]},
  "required_source_columns": ["vendor_sku"],
  "defaults": {"stock": 0}
}
```

프로필은 CatalogGuard의 실제 표준 컬럼만 대상으로 허용한다. 대상 컬럼 중복, 필수 출력 컬럼 누락, 잘못된 JSON과 허용되지 않은 기본값은 파이프라인 전체 오류가 된다. 프로필은 단순 JSON 데이터만 해석하며 동적 코드 실행을 사용하지 않는다.

## 변환과 reject 기준

정상 행은 표준 CSV에 저장한다. 상품 ID·필수 원본값 누락, `price` 또는 `sale_price`로 매핑된 `discount_price`·`promo_price`의 가격 변환 실패·음수, 재고 정수 변환 실패·음수는 reject CSV에 저장한다. 할인 가격 원본이 비어 있으면 reject하지 않고 `sale_price`를 빈 값으로 출력한다. 한 행에 여러 오류가 있으면 `error_code`, `error_field`, `error_message`에 같은 순서의 JSON 배열로 함께 기록한다. 중복 상품 ID, 비표준 색상·사이즈, 가격 이상치, `sale_price`가 `price`보다 큰 상품 품질 문제는 정상 행으로 남겨 기존 CatalogGuard 검수기가 처리한다.

`rejected_rows.csv`는 오류가 없어도 헤더를 포함해 생성한다. `etl_summary.json`에는 프로필 이름·버전, 입력 파일명, 입력·출력·reject CSV SHA-256, 처리 건수, 오류 코드별 건수와 UTC 시각을 기록하며 절대 경로나 비밀값을 기록하지 않는다.

## CLI

```powershell
python -m etl.cli `
  --input .\tests\fixtures\etl\sample_vendor_mixed.csv `
  --profile .\config\etl\sample_fashion_vendor_v1.json `
  --output .\output\catalogguard_ready.csv `
  --rejects .\output\rejected_rows.csv `
  --summary .\output\etl_summary.json
```

정상 처리(오류 행 포함)는 종료 코드 0이다. 입력·프로필·출력 경로 오류는 안전한 메시지와 종료 코드 1로 끝난다. 인수 누락은 `argparse`의 종료 코드 2를 사용한다.

### 두 번째 공급사 CLI 예시

```powershell
.\.venv\Scripts\python.exe -m etl.cli `
  --input .\tests\fixtures\etl\sample_marketplace_vendor_mixed.csv `
  --profile .\config\etl\sample_marketplace_vendor_v1.json `
  --output .\.tmp_etl_marketplace\catalogguard_ready.csv `
  --rejects .\.tmp_etl_marketplace\rejected_rows.csv `
  --summary .\.tmp_etl_marketplace\etl_summary.json
```

`tests/fixtures/etl/sample_marketplace_vendor_mixed.csv`의 처리 결과는 입력 3행, 정상 변환 2행, reject 1행이다. 두 정상 행은 같은 `STYLE-100` 그룹 아래 `SKU-100-BLK-M`과 `SKU-100-WHT-L`을 각각 유지하며, 빈 `available_qty`는 stock `0`으로 변환된다. `가격문의`와 `-1` 재고가 함께 있는 행은 `INVALID_PRICE`와 `NEGATIVE_STOCK`로 reject된다. `59000`과 `69000`은 모두 변환 가능한 숫자이므로 정상 CSV에 남고, `69000 > 59000` 관계는 CatalogGuard 검수 단계에서 `sale_price_greater_than_price`로 탐지된다.

## 안전성과 호환성

입력은 CSV 확장자, 크기, 인코딩, NUL 바이트, 헤더, 중복 컬럼, 행 수와 행 형식을 확인한다. 입력 파일과 출력 파일이 같거나 출력 파일끼리 겹치면 거부한다. 각 출력은 임시 파일 작성 후 원자적으로 교체한다.

표준 CSV는 `product_group_id`부터 `seller`까지 기존 컬럼 순서를 지키며 `price` 다음에 선택 컬럼 `sale_price`를 출력하고 pandas index를 쓰지 않는다. `tests/etl/test_pipeline.py`는 생성된 파일을 실제 `validate_and_read_uploaded_csv()`와 `inspect_dataframe()`에 전달해 `discount_price` 변환과 할인가 관계 검수의 호환성을 확인한다.

## PostgreSQL staging 적재

파일 변환이 끝나면 `catalogguard_ready.csv`와 `etl_summary.json`을 별도 Load 단계에 전달할 수 있다.

```text
공급사 CSV + JSON 프로필
-> etl.cli
-> 표준 CSV + reject CSV + summary JSON
-> etl.load_cli
-> summary 필드·SHA-256·품질 요약·표준 CSV 검증
-> 중복 배치 조회
-> etl_load_runs + catalog_products_staging 저장
-> FastAPI 배치 목록·상세 조회
```

두 CLI의 책임은 분리되어 있다.

| CLI | 책임 |
|---|---|
| `python -m etl.cli` | 공급사 CSV를 표준 CSV, reject CSV, summary JSON으로 변환 |
| `python -m etl.load_cli` | 표준 CSV와 summary JSON을 검증한 뒤 PostgreSQL staging에 적재 |

### 적재 검증과 중복 판단

`etl.db_loader.load_standard_csv()`는 기존 `validate_and_read_uploaded_csv()`를 재사용해 표준 CSV를 읽는다. 이어서 summary JSON에 다음 필드가 있는지 확인한다.

- `profile_name`
- `profile_version`
- `input_filename`
- `input_file_sha256`
- `output_file_sha256`
- `total_rows`
- `loaded_rows`
- `rejected_rows`
- `error_counts`
- `rejects_file_sha256` (신규 summary에서 필수)

profile 이름·버전과 파일명을 정규화하고, SHA-256 형식과 세 행 수의 음수가 아닌 정수 여부를 확인한다. `total_rows = loaded_rows + rejected_rows`를 강제하며, `error_counts`의 key·값과 reject 행 수의 관계를 검증한다. 신규 summary에 `rejects_file_sha256`가 있으면 `--rejects`가 반드시 필요하며, 실제 reject CSV의 hash·행 수·헤더·JSON 오류 배열·동적 원본 컬럼을 모두 검증한다. 한 행에 여러 오류 코드가 있을 수 있으므로 오류 건수 합계는 reject 행 수 이상이면 허용한다. 실제 표준 CSV bytes의 SHA-256이 summary의 `output_file_sha256`과 같은지, 실제 CSV 행 수가 `loaded_rows`와 같은지도 확인한다. 검증에 실패하면 DB를 변경하지 않는다. 과거 summary에 reject hash가 없으면 `--rejects` 없이 기존 방식으로 적재할 수 있고 자동 backfill은 수행하지 않는다.

같은 원본을 같은 프로필 버전으로 다시 적재했는지는 다음 세 값으로 판단한다.

```text
(input_file_sha256, profile_name, profile_version)
```

이미 같은 조합의 `etl_load_runs`가 있으면 상품 행을 추가하지 않고 기존 배치 ID와 `created=False`를 반환한다. 프로필 버전이 다르면 별도 배치로 저장한다.

### Staging 테이블 구조

`etl_load_runs`는 한 번의 ETL 적재를 나타내며 원본 파일명, 프로필, 입력·출력·reject CSV 해시, 적재 행 수와 생성 시각을 저장한다. 신규 배치는 `total_rows`, `rejected_rows`, `error_counts`를 각각 INTEGER·INTEGER·PostgreSQL JSONB로 저장하고 `reject_details_stored`와 `rejects_file_sha256`로 reject 상세 저장 여부를 표시한다. 품질 요약 기능 도입 전 배치는 과거 값을 추정하지 않고 nullable 품질 필드를 유지하며, reject 상세도 자동 backfill하지 않는다. `catalog_products_staging`은 배치에 속한 정상 표준 CSV 행을, `etl_rejected_rows`는 검증된 오류 객체와 개인정보가 마스킹된 동적 원본 컬럼 JSONB를 저장한다.

```text
etl_load_runs (1)
        |
        | etl_load_run_id, ON DELETE CASCADE
        +-----------------------> catalog_products_staging (N)
        |
        +-----------------------> etl_rejected_rows (N)
```

`etl_load_runs`에는 `(input_file_sha256, profile_name, profile_version)` unique index가 있고, 상품 테이블의 `etl_load_run_id`에는 조회용 index와 외래 키가 있다. `stock`, `price`, `sale_price`는 음수가 될 수 없으며 빈 `sale_price`는 DB `NULL`로 저장한다. 부모 배치를 삭제하면 연결된 상품 행도 cascade로 삭제된다.

### 트랜잭션과 CLI

신규 배치와 모든 상품 행·reject 행은 하나의 SQLAlchemy 트랜잭션 안에서 저장한다. 상품 또는 reject 행 저장 중 오류가 발생하면 배치와 두 자식 테이블의 데이터를 함께 rollback하며, upsert나 기존 운영 상품 덮어쓰기는 수행하지 않는다. reject CSV 자체는 파일 검증 후 원본 값을 저장하지 않고 마스킹된 JSONB만 저장한다.

```powershell
python -m etl.load_cli `
  --input .\output\catalogguard_ready.csv `
  --rejects .\output\rejected_rows.csv `
  --summary .\output\etl_summary.json
```

신규 적재 예시는 다음과 같다. 배치 ID는 DB의 현재 sequence 상태에 따라 달라진다.

```text
DB 적재 완료
적재 배치 ID: 1
신규 적재: yes
전체 행: 2
정상 상품 행: 2
거부 행: 0
```

같은 파일을 다시 실행하면 다음과 같이 기존 배치를 재사용한다.

```text
DB 적재 완료
적재 배치 ID: 1
신규 적재: no
전체 행: 2
정상 상품 행: 2
거부 행: 0
```

## 적재 배치 조회 API

ETL 실행과 PostgreSQL 적재는 CLI의 책임으로 유지하고, FastAPI는 저장된 배치와 상품을 읽기 전용으로 조회한다.

### 적재 배치 목록

```http
GET /api/v1/etl-loads
```

| Query | 기본값 | 조건과 의미 |
|---|---:|---|
| `limit` | `20` | 한 페이지의 배치 수, `1` 이상 `100` 이하 |
| `offset` | `0` | 앞에서 건너뛸 배치 수, `0` 이상 |
| `filename` | 없음 | 별도 길이 제한 없는 원본 파일명 부분 검색 |
| `profile_name` | 없음 | 별도 길이 제한 없는 프로필 이름 부분 검색 |

`filename`과 `profile_name`은 앞뒤 공백을 제거하며, 공백만 남는 값은 필터로 사용하지 않는다. 검색은 대소문자를 구분하지 않는 부분 일치이고 두 필터를 함께 보내면 AND 조건으로 적용한다. `%`, `_`, `\`는 SQL LIKE의 wildcard나 escape 문법이 아니라 실제 문자로 검색하도록 escape한다.

목록은 `created_at DESC`, `id DESC` 순으로 최신 배치를 먼저 반환한다. 페이지의 `items`와 전체 건수 `total`은 같은 필터 함수를 사용하므로 검색 조건이 서로 달라지지 않는다. 목록 응답에는 배치 ID, 원본 파일명, 프로필 이름·버전, 전체·정상·거부 행 수와 생성 시각을 포함하며 SHA-256·오류 코드·상품 목록은 제외한다.

### 적재 배치 상세

```http
GET /api/v1/etl-loads/{etl_load_run_id}
```

| Query | 기본값 | 조건과 의미 |
|---|---:|---|
| `product_limit` | `50` | 한 페이지의 상품 수, `1` 이상 `100` 이하 |
| `product_offset` | `0` | 앞에서 건너뛸 상품 수, `0` 이상 |

```http
GET /api/v1/etl-loads/{etl_load_run_id}/rejections?limit=20&offset=0
```

reject 상세 응답은 저장 여부, 전체 reject 행 수, 페이지 단위의 원본 행 번호·구조화된 오류 배열·마스킹된 동적 원본 컬럼을 반환한다. reject 상세가 저장되지 않은 과거 배치는 `available=false`와 빈 목록을 반환하며, 배치가 없으면 HTTP `404`를 반환한다.

상세 응답에는 배치 기본 정보, 전체·정상·거부 행 수, `error_counts`, reject 상세 저장 여부, 원본·출력 파일 SHA-256과 해당 배치의 staging 상품 목록이 포함된다. 기존 배치는 품질 필드를 `null`로 반환한다. 상품은 staging 상품 `id ASC`로 정렬하며 SQL `LIMIT`·`OFFSET`에서 페이지를 나눈다. 모든 상품 조회와 count에는 요청한 `etl_load_run_id` 조건을 적용해 다른 배치의 상품이 섞이지 않게 한다. 배치가 없으면 HTTP `404`를 반환한다.

Path의 `etl_load_run_id`는 `1` 이상의 정수만 허용한다. `0`, 음수와 숫자가 아닌 값은 요청 검증 단계에서 HTTP `422`가 된다. nullable 컬럼인 `sale_price`, `description`, `seller`는 값이 없을 때 JSON `null`로 유지한다.

### 구현 구조

| 파일 | 역할 |
|---|---|
| `api/routes/etl_loads.py` | HTTP 요청과 Query·Path 범위 검증, 404 처리, 응답 모델 변환 |
| `api/schemas.py` | 배치 목록·상세·reject 상세와 staging 상품의 Pydantic 응답 구조 |
| `db/etl_query_service.py` | SQLAlchemy 기반 읽기 전용 필터·정렬·count·페이지 조회와 reject 상세 조회 |
| `tests/test_api_etl_loads.py` | HTTP 상태, 파라미터 전달, 응답 필드와 nullable 값 계약 |
| `tests/test_etl_query_service.py` | 실제 PostgreSQL의 검색·정렬·페이지네이션·NULL·배치 격리 |

라우터는 ORM 객체를 API 응답으로 직접 내보내지 않고 query service의 dataclass 결과를 Pydantic 모델로 변환한다. 따라서 DB 모델 변경이 HTTP 응답 계약을 암묵적으로 바꾸지 않는다.

## Streamlit ETL 적재 이력 화면

Streamlit에는 저장된 ETL 배치와 staging 상품을 확인하고 선택한 batch를 운영 상품에 반영하는 `ETL 적재 이력` 탭을 제공한다. 배치·상품·reject 조회는 읽기 전용이며, promotion preview와 실제 반영은 `CatalogGuardApiClient`가 FastAPI의 별도 POST API를 호출한다. Streamlit이 DB에 직접 쓰지는 않는다.

| 화면 기능 | 동작 |
|---|---|
| 배치 목록 | 최신 적재부터 10건씩 표시하고 전체 행·정상 적재·변환 거부 행과 전체 건수를 표시 |
| 검색 | 파일명과 프로필명 검색을 함께 적용하는 AND 조건 |
| 배치 페이지 | 이전·다음 버튼으로 목록 offset 이동 |
| 배치 상세 | 배치 ID, 파일명, 프로필, 버전, 전체 입력·정상 적재·변환 거부·정상 처리율, 적재 시각과 input/output SHA-256 전체 표시 |
| 오류 통계 | 오류 코드별 발생 건수를 발생 건수 내림차순·코드 오름차순으로 표시하고 reject 0건은 안내 |
| reject 상세 | reject 행 페이지네이션, 오류 코드·필드·메시지와 마스킹된 원본 값 표시; 과거 미저장 배치는 안내 |
| 상품 목록 | 선택한 배치의 staging 상품을 20건씩 표시 |
| promotion | 선택한 batch의 preview 실행, 반영 가능 여부·차단 사유·변경 전후·insert/update/unchanged 표시 |
| 승인 반영 | 승인 checkbox 선택 전 반영 버튼 비활성화; 승인 후 `expected_preview_hash`와 함께 FastAPI promotion 요청 |
| nullable | `sale_price`, `description`, `seller`의 `null`을 빈 값으로 표시 |
| 빈 결과·404 | 빈 목록 안내와 존재하지 않는 배치의 오류 안내 표시 |
| 요청 추적 | 유효한 `X-Request-ID`를 오류 화면에 표시 |

```text
ETL 적재 이력 탭
-> GET /api/v1/etl-loads (limit=10)
-> 파일명·프로필명 검색(AND)
-> 배치 이전·다음
-> 배치 상세 선택
-> GET /api/v1/etl-loads/{etl_load_run_id} (product_limit=20)
-> SHA-256·배치 상품·nullable 필드 표시
-> GET /api/v1/etl-loads/{etl_load_run_id}/rejections (limit=20)
-> reject 오류 배열·마스킹된 원본·페이지 표시
-> 상품 이전·다음
-> 선택한 batch의 promotion preview
-> insert/update/unchanged·상품별 변경 전후·차단 사유 확인
-> 승인 checkbox 선택
-> POST /api/v1/etl-loads/{etl_load_run_id}/promotions
-> 운영 상품 반영 결과와 promotion run 확인
```

Streamlit rerun에 대비해 목록·상세·reject 응답과 선택 상태를 ETL 전용 `session_state`에 보관한다. 검색 조건이나 batch가 바뀌면 이전 상세·상품·reject 상태와 promotion preview·승인 상태를 초기화해 stale 데이터가 남거나 다른 batch에 반영되지 않게 한다. preview 요청 중에는 중복 요청을 막고, preview hash가 없거나 승인하지 않은 상태에서는 반영 버튼을 비활성화한다. 성공 후에는 preview·승인 상태를 제거하고 결과만 보존하며, `preview_stale`가 발생하면 이전 preview를 제거해 새 preview를 요구한다. API Client는 preview·promotion 응답의 필수 key, count, action, before/after shape, SHA-256을 검증하고 HTTP 오류를 안전한 사용자 메시지로 변환한다. 순수 helper 테스트와 Streamlit AppTest로 목록·검색·페이지 이동·상세·품질 지표·오류 코드·SHA-256·reject 상세·nullable·404·request ID·promotion 상태 초기화를 검증한다.

## Catalog promotion preview와 승인 반영

ETL staging은 운영 상품을 바로 덮어쓰는 테이블이 아니므로, 사용자가 반영 대상을 확인하고 명시적으로 승인하는 두 단계 workflow를 둔다. ETL batch를 자동으로 고르지 않고 Streamlit에서 사용자가 직접 선택해야 하며, preview 단계에서는 DB의 운영 상품을 변경하지 않는다.

### Preview API

```http
POST /api/v1/etl-loads/{etl_load_run_id}/promotion-preview
```

preview service는 선택한 batch의 staging 상품과 같은 공급사·외부 상품 ID를 가진 운영 상품을 비교한다. 각 상품을 `insert`, `update`, `unchanged`로 분류하고, update에는 변경 필드별 `before`·`after` 값을, insert에는 `before_data: null`과 전체 `after_data`를 반환한다. 응답에는 다음 정보가 포함된다.

- `insert_count`, `update_count`, `unchanged_count`
- `items`의 공급사, 외부 상품 ID, action, 변경 필드와 전후 데이터
- `promotion_eligible`와 구조화된 `blocked_reasons`
- `preview_hash`, `preview_schema_version`, `inspection_version`
- ETL 검수에서 계산한 `error_count`, `warning_count`

품질 summary가 없는 과거 batch, reject 행이 있는 batch, 빈 staging batch, 같은 공급사 상품 ID가 중복된 batch, 상품 검수 오류가 있는 batch는 `promotion_eligible=false`가 된다. 차단 사유가 있으면 상품별 반영 목록은 제공하지 않고, preview hash는 데이터 상태를 설명하는 값으로만 반환할 수 있다.

`preview_hash`는 canonical JSON으로 정렬한 batch ID, 공급사, inspection version, staging 상품과 현재 운영 상품의 값을 SHA-256으로 계산한 것이다. 암호화나 인증 토큰이 아니라 preview 시점과 실제 반영 시점의 데이터가 같은지 비교하는 stale 감지용 값이다.

### 승인과 실제 promotion

```http
POST /api/v1/etl-loads/{etl_load_run_id}/promotions
```

```json
{
  "confirmation": true,
  "expected_preview_hash": "64자리 소문자 SHA-256 hex"
}
```

서버는 `confirmation=true`와 형식이 맞는 hash를 먼저 검증한다. 그 뒤 하나의 transaction 안에서 ETL batch와 staging·현재 운영 상품을 잠그고 preview를 다시 계산한다.

1. 이미 같은 batch의 `succeeded` run이 있으면 기존 성공 결과를 반환하고 새 반영·audit을 만들지 않는다.
2. 품질·reject·검수·중복 identity 조건이 맞지 않으면 `promotion_blocked` run을 기록하고 `409`를 반환한다.
3. 재계산한 hash와 `expected_preview_hash`가 다르면 `preview_stale` run을 기록하고 `409`를 반환한다.
4. hash가 일치하면 `catalog_products`에 insert/update하고 `catalog_promotion_runs`를 `applying`에서 `succeeded`로 완료한다.
5. insert/update마다 `catalog_product_changes`에 before/after와 변경 필드를 append-only audit으로 기록한다.
6. 반영 중 예외가 발생하면 transaction을 rollback하고 안전한 `promotion_failed` 오류와 failed run을 남긴다. 내부 SQL·DB 연결 정보는 사용자에게 노출하지 않는다.

같은 ETL batch의 성공 run은 PostgreSQL partial unique index로 한 건만 허용한다. batch row와 운영 상품 row를 잠그고, 상품 identity를 공급사와 외부 상품 ID의 조합으로 관리해 서로 다른 공급사의 같은 ID가 충돌하지 않게 한다. 동시 요청 테스트는 한 요청만 성공하고 다른 요청은 stale 또는 안전한 failed 결과가 되며, `applying` 상태가 남지 않고 운영 상품과 audit이 한 번만 생성되는지 확인한다.

## 실제 Chromium 브라우저 E2E

계층별 테스트만으로는 Streamlit rerun, 실제 접근성 이름, 동적 표·expander 렌더링과 브라우저의 raw 개인정보 노출을 확인할 수 없으므로 별도 Playwright E2E를 둔다. `scripts/run_etl_browser_e2e.py`가 테스트 PostgreSQL에 migration을 적용하고 전용 합성 fixture를 ETL CLI·Load CLI로 처리한 뒤 FastAPI와 Streamlit을 시작한다. readiness가 확인되면 `tests/e2e/test_etl_browser_e2e.py`가 Chromium에서 reject 조회와 promotion 성공 흐름을 실행한다.

```text
ETL fixture 3행
-> 표준 CSV·reject CSV·summary JSON
-> PostgreSQL 배치·상품·reject 적재
-> FastAPI /health·/ready
-> Streamlit /_stcore/health
-> ETL 적재 이력 탭·검색·상세 조회
-> 품질 3행/2행/1행/66.7%
-> staging 상품 2개
-> reject 오류 배열과 마스킹 원본
-> promotion fixture batch 직접 선택
-> preview와 상품별 변경 전후 확인
-> 승인 checkbox 선택 전 반영 버튼 disabled 확인
-> 실제 promotion 실행
-> succeeded run·운영 상품·audit·applying 0건을 PostgreSQL에서 확인
```

브라우저 테스트는 `test@example.com`, `010-1234-5678`, `123-456-789012`, `900101-1234567`이 body text와 HTML에 존재하지 않는지 확인하고, 마스킹된 값·오류 코드·필드·메시지·console error 0·page error 0을 확인한다. 실패 시 `artifacts/browser-e2e/failure.png`, `page.html`, FastAPI·Streamlit·Playwright 로그를 보존하며 runner가 시작한 프로세스와 임시 디렉터리는 성공·실패 모두 정리한다.

로컬 실행에는 `requirements-e2e.txt` 설치와 Chromium 설치가 필요하다. GitHub Actions에서는 일반 테스트와 분리된 `browser-e2e` job이 PostgreSQL 18 service, Playwright Chromium과 실패 artifact 업로드를 담당한다.

### 전체 상품 로딩과 N+1 방지

배치 상세를 조회할 때 SQLAlchemy relationship의 상품 전체를 자동으로 읽지 않는다. 배치 정보와 현재 상품 페이지를 별도 SELECT로 조회하고, 전체 상품 수는 별도 count 쿼리로 계산한다. 상품 페이지네이션은 전체 행을 Python 메모리에 올린 뒤 자르는 방식이 아니라 DB 쿼리의 `LIMIT`·`OFFSET`에서 처리한다.

N+1 문제는 배치 한 번을 조회한 뒤 상품마다 DB에 다시 질문하여 DB 요청 횟수가 지나치게 늘어나는 문제다. 현재 상세 조회는 상품마다 추가 SELECT를 실행하지 않으며, 조회 함수 안에서 `commit`이나 `rollback`도 실행하지 않는다. 트랜잭션 수명은 세션을 제공한 상위 계층이 관리한다.

### 특수문자 검색 검증

실제 PostgreSQL 18.4 테스트에서 SQL LIKE 특수문자를 다음과 같이 일반 문자로 처리하는지 확인했다.

- `%` 검색은 여러 글자 wildcard가 아니라 실제 `%`가 포함된 파일만 반환한다.
- `_` 검색은 한 글자 wildcard가 아니라 실제 `_`가 포함된 파일만 반환한다.
- `\` 검색은 escape 처리 중 사라지거나 패턴을 바꾸지 않고 실제 `\`가 포함된 파일만 반환한다.

각 테스트는 해당 문자를 실제로 포함한 fixture와 포함하지 않은 fixture를 함께 사용해, wildcard로 처리하는 잘못된 구현이 통과하지 않도록 배치 ID 목록과 `total`을 확인한다.

### Migration 검증

다음 순서로 staging migration의 upgrade, downgrade, 재upgrade를 확인했다.

```powershell
python -m alembic upgrade head
python -m alembic downgrade 20260728_0005
python -m alembic upgrade head
```

`20260727_0004`에 이어 `20260728_0005` upgrade는 `etl_load_runs`에 reject 상세 저장 여부·reject CSV SHA-256과 all-or-none CHECK constraint를 추가하고, 오류 배열·마스킹된 원본 JSONB를 저장하는 `etl_rejected_rows`와 unique/index/FK를 만든다. downgrade는 새 컬럼·constraint·테이블·index만 제거하며 기존 배치·상품·inspection 데이터는 삭제하지 않는다.

현재 Alembic head는 `20260728_0006`이다. 이 revision은 ETL staging을 변경하지 않고, 별도의 운영 상품·promotion persistence 테이블을 추가한다. 격리된 PostgreSQL 18 테스트 클러스터에서 빈 DB upgrade, `20260728_0006` → `20260728_0005` downgrade, 재-upgrade와 단일 head를 확인했으며, 이후 promotion service·API·UI가 이 테이블을 사용하는 흐름을 검증했다.

현재 기준 저장소의 GitHub Actions run `30736845060`은 성공했다. 문서에는 실행별 전체 pytest 수를 고정하지 않고, promotion preview·service·API·client·UI·concurrency 테스트와 Chromium promotion E2E가 검증하는 동작 범위를 기록한다. E2E는 브라우저 메시지뿐 아니라 PostgreSQL의 최종 운영 상품·run·audit 상태도 확인한다.

## 제한사항

- 합성 패션 공급사 프로필 2종을 지원한다.
- 실제 외부 공급사 운영 데이터 연동은 지원하지 않는다.
- 자동 공급사 감지는 지원하지 않으며, 공급사별 프로필은 수동 선택한다.
- 웹 수집과 외부 API 연동은 지원하지 않는다.
- ETL 적재 실행용 웹 API는 지원하지 않는다. Streamlit 적재 이력 화면의 배치·상품·reject 조회는 읽기 전용이지만, 선택한 batch의 promotion preview와 승인된 운영 상품 반영은 FastAPI POST API를 호출한다.
- staging 상품 수정·삭제와 상품 변경 이력 조회 API는 지원하지 않는다.
- promotion은 외부 공급사 운영 데이터나 production catalog가 아닌 합성 fixture·테스트 PostgreSQL 환경에서만 검증했다. reject 행은 별도 `etl_rejected_rows`에 오류 배열과 마스킹된 동적 원본 컬럼으로 저장한다.
- 증분 ETL과 streaming은 지원하지 않는다.
- 운영 DB 적재는 검증하지 않았으며, PostgreSQL staging 적재는 임시 테스트 PostgreSQL 환경에서만 검증했다.
- 실제 브라우저 E2E는 Chromium 한 종류와 합성 fixture만 검증하며, 운영 환경·모바일 브라우저·외부 공급사는 검증하지 않는다.
- `sale_price`는 단일 할인 가격만 지원하며 할인율, 기간, 쿠폰·회원 가격, 최저가 추천은 제공하지 않는다.
