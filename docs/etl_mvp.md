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

정상 행은 표준 CSV에 저장한다. 상품 ID·필수 원본값 누락, `price` 또는 입력된 `discount_price`의 가격 변환 실패·음수, 재고 정수 변환 실패·음수는 reject CSV에 저장한다. `discount_price`가 비어 있으면 reject하지 않고 `sale_price`를 빈 값으로 출력한다. 한 행에 여러 오류가 있으면 `error_code`, `error_message`에 JSON 배열로 함께 기록한다. 중복 상품 ID, 비표준 색상·사이즈, 가격 이상치, `sale_price`가 `price`보다 큰 상품 품질 문제는 정상 행으로 남겨 기존 CatalogGuard 검수기가 처리한다.

`rejected_rows.csv`는 오류가 없어도 헤더를 포함해 생성한다. `etl_summary.json`에는 입력·출력 SHA-256, 처리 건수, 오류 코드별 건수와 UTC 시각만 기록하며 절대 경로나 비밀값을 기록하지 않는다.

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
-> summary 필드·SHA-256·행 수·표준 CSV 검증
-> 중복 배치 조회
-> etl_load_runs + catalog_products_staging 저장
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
- `loaded_rows`

profile 이름·버전과 파일명을 정규화하고, SHA-256 형식과 `loaded_rows`의 음수가 아닌 정수 여부를 확인한다. 실제 표준 CSV bytes의 SHA-256이 summary의 `output_file_sha256`과 같은지, 실제 CSV 행 수가 `loaded_rows`와 같은지도 확인한다. 검증에 실패하면 DB를 변경하지 않는다.

같은 원본을 같은 프로필 버전으로 다시 적재했는지는 다음 세 값으로 판단한다.

```text
(input_file_sha256, profile_name, profile_version)
```

이미 같은 조합의 `etl_load_runs`가 있으면 상품 행을 추가하지 않고 기존 배치 ID와 `created=False`를 반환한다. 프로필 버전이 다르면 별도 배치로 저장한다.

### Staging 테이블 구조

`etl_load_runs`는 한 번의 ETL 적재를 나타내며 원본 파일명, 프로필, 입력·출력 해시, 적재 행 수와 생성 시각을 저장한다. `catalog_products_staging`은 배치에 속한 정상 표준 CSV 행을 저장한다.

```text
etl_load_runs (1)
        |
        | etl_load_run_id, ON DELETE CASCADE
        v
catalog_products_staging (N)
```

`etl_load_runs`에는 `(input_file_sha256, profile_name, profile_version)` unique index가 있고, 상품 테이블의 `etl_load_run_id`에는 조회용 index와 외래 키가 있다. `stock`, `price`, `sale_price`는 음수가 될 수 없으며 빈 `sale_price`는 DB `NULL`로 저장한다. 부모 배치를 삭제하면 연결된 상품 행도 cascade로 삭제된다.

### 트랜잭션과 CLI

신규 배치와 모든 상품 행은 하나의 SQLAlchemy 트랜잭션 안에서 저장한다. 상품 행 저장 중 오류가 발생하면 배치와 상품 행을 함께 rollback하며, upsert나 기존 운영 상품 덮어쓰기는 수행하지 않는다. reject CSV 행도 staging에 저장하지 않는다.

```powershell
python -m etl.load_cli `
  --input .\output\catalogguard_ready.csv `
  --summary .\output\etl_summary.json
```

신규 적재 예시는 다음과 같다. 배치 ID는 DB의 현재 sequence 상태에 따라 달라진다.

```text
DB 적재 완료
적재 배치 ID: 1
신규 적재: yes
상품 행: 2
```

같은 파일을 다시 실행하면 다음과 같이 기존 배치를 재사용한다.

```text
DB 적재 완료
적재 배치 ID: 1
신규 적재: no
상품 행: 2
```

### Migration 검증

다음 순서로 staging migration의 upgrade, downgrade, 재upgrade를 확인했다.

```powershell
python -m alembic upgrade head
python -m alembic downgrade 20260705_0002
python -m alembic upgrade head
```

`20260725_0003` upgrade 후 `etl_load_runs`, `catalog_products_staging`과 unique index, FK 조회 index, 음수 방지 CHECK constraint, `ON DELETE CASCADE`가 생성된다. downgrade 후에는 두 staging 테이블만 제거되고 기존 `inspection_runs`, `inspection_results`는 유지되며, 재upgrade로 staging 구조를 다시 만들 수 있다.

실제 PostgreSQL 18.4 임시 클러스터에서 2행 표준 CSV를 최초 적재하고, 같은 파일을 재실행해 `created=False`와 중복 상품 미생성을 확인했다. 운영 DB가 아닌 테스트용 환경에서만 수행한 검증이다. 신규 ETL loader/migration 테스트는 `16 passed`, DB persistence는 `52 passed`, API inspection은 `66 passed`, 전체 pytest는 `874 passed, 2 deselected`였고 GitHub Actions Test #32도 성공했다. 이 기능은 `de51b3878194af51e74b729aa9c9ba9c7f74a833`에 반영되어 있다.

## 제한사항

- 합성 패션 공급사 프로필 2종을 지원한다.
- 실제 외부 공급사 운영 데이터 연동은 지원하지 않는다.
- 자동 공급사 감지는 지원하지 않으며, 공급사별 프로필은 수동 선택한다.
- 웹 수집과 외부 API 연동은 지원하지 않는다.
- 운영 상품 테이블 upsert, 기존 상품 갱신·덮어쓰기와 reject 행 DB 저장은 지원하지 않는다.
- 증분 ETL과 streaming은 지원하지 않는다.
- 운영 DB 적재는 검증하지 않았으며, PostgreSQL staging 적재는 임시 테스트 PostgreSQL 환경에서만 검증했다.
- `sale_price`는 단일 할인 가격만 지원하며 할인율, 기간, 쿠폰·회원 가격, 최저가 추천은 제공하지 않는다.
