# 공급사 상품 CSV ETL MVP

## 목적

샘플 패션 공급사의 CSV를 CatalogGuard Lite 검수기가 읽을 수 있는 표준 CSV로 변환한다. 이 MVP는 웹 수집, 외부 API 연동, 데이터베이스 적재 없이 파일 변환 결과만 저장한다.

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

## 제한사항

- 합성 패션 공급사 프로필 2종을 지원한다.
- 실제 외부 공급사 운영 데이터 연동은 지원하지 않는다.
- 자동 공급사 감지는 지원하지 않으며, 공급사별 프로필은 수동 선택한다.
- 웹 수집, 외부 API, PostgreSQL 직접 적재는 지원하지 않는다.
- streaming·증분 ETL은 지원하지 않는다.
- `sale_price`는 단일 할인 가격만 지원하며 할인율, 기간, 쿠폰·회원 가격, 최저가 추천은 제공하지 않는다.
