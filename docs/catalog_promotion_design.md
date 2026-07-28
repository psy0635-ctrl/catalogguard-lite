# CatalogGuard Lite 운영 상품 반영 설계

## 1. 목적과 범위

이 문서는 ETL staging 상품을 운영 상품으로 반영하는 후속 기능의 최종 설계다. 현재 저장소에는 `etl_load_runs`, `catalog_products_staging`, `etl_rejected_rows`, `inspection_runs`, `inspection_results`가 있으며 운영 상품, promotion 실행 이력, 변경 이력은 아직 구현되어 있지 않다.

이번 작업은 이 문서만 보완한다. 런타임 코드, SQLAlchemy 모델, Alembic migration, API, UI, 테스트는 구현하지 않는다. 아래 테이블·API는 후속 구현 계약이고 이미 존재하는 기능이 아니다.

## 2. 현재 구조

현재 흐름은 `공급사 CSV -> etl.pipeline -> 표준 CSV/reject CSV/summary JSON -> etl.load_cli -> PostgreSQL staging`이다.

- `etl_load_runs`는 `profile_name`, `profile_version`, 파일 해시, `total_rows`, `rejected_rows`, `error_counts`를 저장한다.
- `catalog_products_staging`은 정상 변환 상품을 `etl_load_run_id`에 연결한다.
- `etl_rejected_rows`는 reject CSV가 제공된 경우 오류 구조와 마스킹된 원본만 저장한다.
- `inspect_dataframe()`는 표준 컬럼 DataFrame을 현재 `INSPECTION_VERSION`으로 검사한다. inspection 이력은 ETL batch와 연결되지 않는다.
- staging에는 batch 내부 상품 identity unique constraint가 없고, 운영 상품 upsert나 promotion API도 없다.

현재 샘플 프로필은 `sample_fashion_vendor`와 `sample_marketplace_vendor`이며 version은 각각 `1`이다.

## 3. 상품 식별 정책

이번 MVP에서 아래 계약을 사용한다.

```text
supplier_key = etl_load_runs.profile_name
external_product_id = catalog_products_staging.product_id
운영 상품 unique key = (supplier_key, external_product_id)
```

`catalog_products.id`는 내부 primary key다. `product_group_id`는 스타일/그룹 정보이므로 identity에 넣지 않는다. 색상·사이즈가 다른 옵션을 별도 운영 상품으로 다루려면 ETL이 다른 `product_id`를 제공해야 한다.

다음은 MVP 불변 조건이다.

- `profile_name`은 공급사를 구분하는 안정적인 불변 식별자로 사용한다.
- 같은 공급사의 변환 규칙 변경은 `profile_name`이 아니라 `profile_version`을 올린다.
- `product_id` 단독 unique는 사용하지 않는다.
- 동일 공급사가 여러 독립 입력 형식을 사용해야 하는 시점에는 supplier registry를 별도 도입한다. 이번 단계에서는 supplier 테이블과 staging의 `supplier_key` 컬럼을 만들지 않는다.

## 4. 후속 데이터 모델

### `catalog_products`

| 컬럼 | 정책 |
| --- | --- |
| `id` | `BIGINT` primary key |
| `supplier_key`, `external_product_id` | `NOT NULL`, `UNIQUE (supplier_key, external_product_id)` |
| `product_group_id`, `product_name`, `category`, `color`, `size`, `image_path` | 표준 staging 필드, `NOT NULL`, 공백 금지 |
| `stock`, `price` | `NOT NULL`, 0 이상 |
| `sale_price` | nullable, 값이 있으면 0 이상 |
| `description`, `seller` | nullable 표준 staging 필드 |
| `source_etl_load_run_id` | 마지막 반영 batch FK, `ON DELETE RESTRICT` |
| `created_at`, `updated_at` | DB 서버 시간; 실제 변경 때만 `updated_at` 갱신 |

staging 모델을 그대로 복사하지 않는다. staging의 `id`, `etl_load_run_id`, `created_at`은 적재 이력이고 운영 모델에는 안정적인 identity와 마지막 source batch가 필요하다.

### `catalog_promotion_runs`

한 ETL batch의 반영 수명 주기를 기록한다. `etl_load_run_id`는 `NOT NULL UNIQUE`로 두어 DB idempotency key로 사용한다. 상태는 `pending`, `applying`, `succeeded`, `failed`, `blocked`다.

최소 필드는 `inserted_count`, `updated_count`, `unchanged_count`, `blocked_count`, `inspection_version`, `preview_hash`, `error_count`, `warning_count`, `started_at`, `completed_at`, `failure_code`, `safe_failure_message`, `created_at`이다. count는 0 이상이며 실패 정보에는 SQL, DB URL, 내부 파일 경로, traceback을 저장하지 않는다.

### `catalog_product_changes`

append-only audit log다. `promotion_run_id`, `catalog_product_id`, `action`(`insert`/`update`), `changed_fields`, 변경 필드만 담은 `before_data`·`after_data`, `created_at`을 저장한다. `unchanged`는 변경 이력 행을 만들지 않고 promotion run count와 preview item으로 설명한다.

## 5. 품질 게이트와 reject 정책

preview와 실제 promotion은 같은 순서로 판단한다.

```text
ETL batch 존재 확인
-> 품질 summary 존재 확인
-> reject 행 존재 확인
-> staging 상품 존재 확인
-> batch 내부 운영 상품 key 중복 확인
-> 현재 INSPECTION_VERSION으로 staging 재검수
-> insert / update / unchanged 계산
```

다음 중 하나라도 해당하면 전체 batch를 `blocked`한다.

| 코드 | 조건 | 안전한 메시지 예시 |
| --- | --- | --- |
| `quality_summary_missing` | `total_rows`, `rejected_rows`, `error_counts` 중 하나라도 `NULL` | ETL 품질 요약이 없는 배치는 운영 반영할 수 없습니다. |
| `etl_rejections_present` | `rejected_rows > 0` 또는 저장된 reject 행 존재 | 변환이 거부된 상품 행이 있어 운영 반영을 진행할 수 없습니다. |
| `empty_staging_batch` | staging 상품 수가 0 | 반영할 정상 staging 상품이 없습니다. |
| `duplicate_product_identity` | 한 batch에 같은 `(profile_name, product_id)`가 둘 이상 존재 | 같은 공급사 상품 식별자가 배치 안에 중복되어 있습니다. |
| `inspection_errors_present` | 재검수 결과 `error_count > 0` | 상품 검수 오류가 있어 운영 반영을 진행할 수 없습니다. |

과거처럼 품질 summary가 없는 batch는 허용하지 않는다. `rejected_rows > 0`이면 정상 staging 행이 있어도 부분 반영하지 않는다. reject CSV 상세가 저장되지 않은 과거 batch도 summary의 `rejected_rows`로 차단한다.

`warning_count > 0`이고 `error_count = 0`이면 warning 코드 요약을 preview에 포함하고 promotion을 허용한다. 오류와 warning이 모두 없을 때도 허용한다. 별도의 “사전 검수됨” 상태는 두지 않으며 promotion 과정이 staging을 직접 재검수한다.

## 6. staging 재검수

preview와 실제 promotion은 아래를 수행한다.

```text
catalog_products_staging 조회
-> 현재 표준 컬럼 DataFrame 생성
-> inspect_dataframe() 호출
-> error_count와 warning_count 계산
```

이 결과는 기존 `inspection_runs`에 저장하지 않으며 별도 promotion validation 테이블도 만들지 않는다. 후속 `catalog_promotion_runs`에는 실행 당시의 `inspection_version`, `preview_hash`, `error_count`, `warning_count`만 기록할 수 있도록 한다.

## 7. batch 내부 중복 정책

같은 batch에 `(profile_name, product_id)`, 즉 `(supplier_key, external_product_id)`가 두 번 이상 있으면 전체 preview를 `blocked` 처리한다. 첫 번째/마지막 행 선택, 재고 합산, 자동 병합은 사용하지 않는다.

preview는 중복 identity와 staging row ID 목록만 안전하게 반환할 수 있다. 상품 설명, 판매자 자유 입력, reject 원본·개인정보는 오류 메시지에 넣지 않는다.

## 8. preview hash 계약

`preview_schema_version`의 초기값은 `1`이다. preview hash는 다음 canonical JSON을 SHA-256으로 계산한 64자리 소문자 hex다.

```text
preview_schema_version
inspection_version
etl_load_run_id
supplier_key (= profile_name)
promotion 대상 상품 전체
```

상품은 `supplier_key` 오름차순, `external_product_id` 오름차순으로 정렬한다. 각 대상 상품의 hash 입력 필드는 아래로 고정한다.

```text
external_product_id
product_group_id
product_name
category
color
size
stock
price
sale_price
image_path
description
seller
```

preview와 실행 사이의 운영 상품 변경도 감지하기 위해, 각 identity의 현재 운영 값(없으면 `null`)을 위와 같은 필드 집합으로 canonical payload에 포함한다. 이는 preview가 본 before 상태이며 내부 catalog ID·시간값이 아니다.

canonical payload의 root object는 정확히 `preview_schema_version`, `inspection_version`, `etl_load_run_id`, `supplier_key`, `products` 키로 구성한다. `products`의 각 object는 `external_product_id`, `target`, `current_catalog` 키를 갖는다. `target`과 null이 아닌 `current_catalog`은 위의 상품별 hash 대상 필드를 정확히 한 번씩 갖는 object다. 운영 상품이 없으면 `current_catalog`은 빈 object가 아니라 JSON `null`이다.

```json
{
  "preview_schema_version": 1,
  "inspection_version": "5",
  "etl_load_run_id": 42,
  "supplier_key": "sample_fashion_vendor",
  "products": [
    {
      "external_product_id": "P001",
      "target": {
        "external_product_id": "P001",
        "product_group_id": "G001",
        "product_name": "상품",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": 7,
        "price": 21900,
        "sale_price": null,
        "image_path": "https://example.test/p001.jpg",
        "description": null,
        "seller": "Sample"
      },
      "current_catalog": {
        "external_product_id": "P001",
        "product_group_id": "G001",
        "product_name": "상품",
        "category": "TOP",
        "color": "BLACK",
        "size": "M",
        "stock": 10,
        "price": 19900,
        "sale_price": null,
        "image_path": "https://example.test/p001.jpg",
        "description": null,
        "seller": "Sample"
      }
    }
  ]
}
```

`stock`, `price`, `sale_price`는 정수 JSON number 또는 `null`로 직렬화하며 float·문자열 숫자·누락 키를 허용하지 않는다. 나머지 필드는 staging에서 정규화된 문자열 또는 nullable 필드의 `null`을 사용한다.

생성 절차는 `정해진 필드 dict 구성 -> identity 정렬 -> JSON key 정렬 -> 공백 없는 UTF-8 JSON 직렬화 -> SHA-256`이다. 시간값, DB 내부 catalog product ID, SQL 조회 순서, Python 객체 표현 문자열은 hash에 넣지 않는다.

실제 promotion은 `expected_preview_hash`와 현재 재계산 hash를 비교한다. 다르면 운영 상품을 수정하지 않고 `HTTP 409 Conflict`, 코드 `preview_stale`를 반환하며 새 preview를 안내한다.

## 9. preview API와 응답 계약

최종 endpoint는 다음이다.

```http
POST /api/v1/etl-loads/{etl_load_run_id}/promotion-preview
```

POST를 선택한 이유는 staging 전체 검수와 운영 상품 비교라는 비용 있는 계산이고, 향후 option request body로 확장할 수 있으며, 중간 cache가 오래된 preview를 반환하지 않게 하기 위해서다. 응답에는 `Cache-Control: no-store`를 사용한다.

preview는 `catalog_products`, `catalog_promotion_runs`, `catalog_product_changes`, `catalog_products_staging`, `etl_load_runs`, `inspection_runs` 중 어느 것도 변경하지 않는다.

최소 응답 필드는 `etl_load_run_id`, `supplier_key`, `inspection_version`, `preview_hash`, `promotion_eligible`, `blocked_reasons`, `insert_count`, `update_count`, `unchanged_count`, `warning_count`, `items`다. `items` action은 `insert`, `update`, `unchanged`, `blocked` 중 하나이며 대량 batch에서는 페이지 처리한다.

```json
{
  "etl_load_run_id": 42,
  "supplier_key": "sample_fashion_vendor",
  "inspection_version": "5",
  "preview_hash": "0123456789abcdef0123456789abcdef0123456789abcdef0123456789abcdef",
  "promotion_eligible": false,
  "blocked_reasons": [
    {
      "code": "etl_rejections_present",
      "message": "변환이 거부된 상품 행이 있어 운영 반영을 진행할 수 없습니다."
    }
  ],
  "insert_count": 0,
  "update_count": 0,
  "unchanged_count": 0,
  "warning_count": 0,
  "items": []
}
```

사용자 메시지와 응답에는 DB URL, SQL, 내부 파일 경로, 예외 traceback, 마스킹 전 개인정보를 넣지 않는다.

## 10. 실제 promotion과 stale 방어

후속 실제 반영 endpoint는 다음으로 유지한다.

```http
POST /api/v1/etl-loads/{etl_load_run_id}/promotions
```

```json
{
  "confirmation": true,
  "expected_preview_hash": "64자리 SHA-256"
}
```

실행은 `confirmation == true` 확인, staging 재조회, 품질 게이트 재실행, hash 재계산, `expected_preview_hash` 비교, DB transaction, upsert/audit/성공 이력 저장 순서다. hash가 다르면 409으로 끝내며 운영 상품을 수정하지 않는다.

성공 반영은 하나의 PostgreSQL transaction으로 `catalog_products` insert/update, `catalog_product_changes` append, promotion run의 count·`succeeded` 상태 갱신을 함께 commit한다. 중간 실패 시 모두 rollback하고, 별도 짧은 transaction으로 run을 `failed`와 안전한 실패 정보로 갱신한다.

같은 batch가 이미 `succeeded`면 기존 run 결과를 반환하고 다시 반영하지 않는다. 동일 batch 동시 요청은 `catalog_promotion_runs.etl_load_run_id UNIQUE`와 `SELECT ... FOR UPDATE`로 한 요청만 `applying`으로 전이시킨다. 서로 다른 batch의 같은 운영 상품 갱신은 identity 순서로 행을 잠그고 운영 상품 unique constraint를 최종 보호선으로 사용한다.

## 11. upsert와 삭제 정책

비교·반영 필드는 `product_name`, `product_group_id`, `category`, `color`, `size`, `stock`, `price`, `sale_price`, `image_path`, `description`, `seller`다.

- 운영 상품이 없으면 `insert`한다.
- identity가 있고 하나라도 다르면 `update`한다.
- 모두 같으면 `unchanged`이며 UPDATE, `updated_at` 변경, 변경 이력 행을 만들지 않는다.
- `supplier_key`, `external_product_id`, `created_at`은 update하지 않는다.
- staging은 공급사의 전체 최신 snapshot이다. optional `sale_price`, `description`, `seller`의 `NULL`은 기존 값을 유지하는 뜻이 아니라 값을 비우는 뜻이다.

새 batch에 없는 기존 운영 상품은 삭제·비활성화하지 않는다. hard delete, 자동 rollback, 선택 반영은 이번 MVP 범위 밖이다.

## 12. TDD·migration 검증 계획

후속 구현 전에는 다음을 테스트로 고정한다.

- migration의 upgrade/downgrade/재-upgrade, unique/FK/CHECK/index, promotion run의 ETL batch unique
- 품질 summary 누락, reject 존재, empty staging, batch 내부 identity 중복, inspection error의 전체 차단
- warning만 있는 batch의 허용과 warning count 반환
- preview의 insert/update/unchanged와 필드별 before/after, preview 호출의 DB 무변경
- canonical hash의 정렬·JSON·SHA-256 재현성, staging/규칙/운영 before 상태 변경 시 `preview_stale`
- insert/update/unchanged, 단일 transaction commit, 중간 실패 rollback, audit append
- 동일 batch 재요청·동시 요청의 idempotency, 다른 batch의 동일 identity 경합
- 기존 ETL CLI, staging 적재, ETL 조회/reject API, inspection API/jobs, Streamlit 읽기 화면, Playwright ETL E2E 회귀

## 13. 최종 구현 순서

```text
1. catalog_products와 promotion 관련 DB 모델·migration
2. promotion preview service
3. promotion preview FastAPI endpoint
4. 실제 승인형 promotion transaction
5. catalog_product_changes audit 저장
6. 중복 요청·동시성 PostgreSQL 통합 테스트
7. Streamlit preview·승인 UI
8. Playwright promotion E2E
```

다음 코딩 작업 1개는 **운영 상품 identity와 promotion 기록용 DB 모델·Alembic migration MVP**다. preview는 운영 상품 테이블과 비교해야 하므로 migration보다 먼저 구현하지 않는다.

## 14. 이번 단계와 후속 범위

이번 문서 작업에서는 설계만 확정한다. 후속 MVP에서도 개별 상품 선택 반영, 자동 삭제·비활성화, hard delete, 취소·예약 반영, 권한·승인, Redis/Celery, streaming·증분 ETL, preview 영구 저장, 실제 Railway/운영 DB 연결은 제외한다.

## 15. 최종 결정

운영 상품 identity는 `(profile_name, product_id)`를 `(supplier_key, external_product_id)`라는 운영 모델 이름으로 표현한다. promotion은 품질 summary, reject, empty staging, batch 내부 중복, 재검수 오류를 모두 배치 전체 차단 사유로 사용한다. preview와 실제 반영은 동일 staging을 재검수하고 canonical preview hash로 stale 상태를 막는다. 구현은 DB 모델·migration부터 시작한다.
