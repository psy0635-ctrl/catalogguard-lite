# 공급사 상품 CSV ETL MVP

## 목적

샘플 패션 공급사의 CSV를 CatalogGuard Lite 검수기가 읽을 수 있는 표준 CSV로 변환한다. 이 MVP는 웹 수집, 외부 API 연동, 데이터베이스 적재 없이 파일 변환 결과만 저장한다.

## 지원 프로필

`config/etl/sample_fashion_vendor_v1.json`은 다음 공급사 컬럼을 지원한다.

| 원본 컬럼 | CatalogGuard 대상 컬럼 | 처리 |
|---|---|---|
| `vendor_sku` | `product_group_id`, `product_id` | 공백 제거, 앞자리 0 유지 |
| `item_name` | `product_name` | 공백 제거 |
| `main_category` | `category` | 공백 제거 |
| `brand_name` | `seller` | 공백 제거 |
| `list_price` | `price` | `12,000`, `₩12,000`을 정수 문자열로 변환 |
| `colour`, `size_name` | `color`, `size` | 공백 제거만 수행 |
| `quantity` | `stock` | 음수가 아닌 정수로 변환, 빈 값은 `0` |
| `description_text` | `description` | 공백 제거 |
| `image_link` | `image_path` | 공백 제거 |

샘플 공급사에는 별도 상품 그룹 컬럼이 없으므로 `vendor_sku`를 `product_group_id`와 `product_id`에 함께 매핑한다. 따라서 서로 다른 SKU가 하나의 그룹으로 잘못 묶이지 않는다. 동일 상품의 옵션 행을 그룹으로 묶어야 하는 공급사는 실제 그룹 식별 컬럼을 두 대상에 맞게 별도 프로필로 매핑해야 한다. 현재 CatalogGuard 표준 스키마에는 `sale_price`가 없으므로, 원본 `discount_price`는 표준 CSV로 내보내지 않는다. 할인 가격 저장과 `price` 비교 검수는 표준 스키마가 확장될 때 별도 작업으로 추가한다.

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

정상 행은 표준 CSV에 저장한다. 상품 ID·필수 원본값 누락, 가격 변환 실패·음수, 재고 정수 변환 실패·음수는 reject CSV에 저장한다. 한 행에 여러 오류가 있으면 `error_code`, `error_message`에 JSON 배열로 함께 기록한다. 중복 상품 ID, 비표준 색상·사이즈, 가격 이상치처럼 기존 검수 규칙의 대상인 품질 문제는 정상 행으로 남긴다.

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

## 안전성과 호환성

입력은 CSV 확장자, 크기, 인코딩, NUL 바이트, 헤더, 중복 컬럼, 행 수와 행 형식을 확인한다. 입력 파일과 출력 파일이 같거나 출력 파일끼리 겹치면 거부한다. 각 출력은 임시 파일 작성 후 원자적으로 교체한다.

표준 CSV는 `product_group_id`부터 `seller`까지 기존 컬럼 순서를 지키고 pandas index를 쓰지 않는다. `tests/etl/test_pipeline.py`는 생성된 파일을 실제 `validate_and_read_uploaded_csv()`와 `inspect_dataframe()`에 전달해 기존 검수 흐름과의 호환성을 확인한다.

## 제한사항

- 샘플 패션 공급사 프로필 1종만 지원한다.
- 웹 수집, 이미지 다운로드, PostgreSQL 직접 적재와 비동기 실행은 지원하지 않는다.
- 대용량 streaming·증분 처리·자동 공급사 감지는 지원하지 않는다.
- 현재 표준 스키마에 할인 가격 필드가 없어 `discount_price`를 저장하거나 검수하지 않는다.
