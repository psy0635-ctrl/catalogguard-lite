# CatalogGuard Lite 운영 상품 반영 설계

## 1. 목적과 범위

이 문서는 ETL staging 상품을 운영 상품으로 반영하는 기능의 설계와 현재 구현 경계를 설명한다. 저장소에는 `etl_load_runs`, `catalog_products_staging`, `etl_rejected_rows`, `inspection_runs`, `inspection_results`와 함께 운영 상품·promotion 실행·상품 변경 이력 persistence 모델이 구현되어 있다.

`catalog_products`, `catalog_promotion_runs`, `catalog_product_changes`의 SQLAlchemy 모델과 Alembic migration은 완료되었고, 현재 저장소에는 promotion preview service/API, 승인형 promotion transaction·upsert, preview hash 계산, promotion run·audit 조회 API, Streamlit UI와 Browser E2E도 구현되어 있다. 아래 5~11절은 설계 당시 정의한 품질 게이트·정책과 현재 구현 결과를 함께 기록한다.

이후 `catalog_promotion_rollbacks`, `catalog_promotion_rollback_changes` 모델과 Alembic migration, rollback preview/실행 service·API, rollback 실행 이력·상품별 change audit 조회 API, Streamlit rollback UI도 추가되었다. succeeded promotion run을 되돌리는 이 기능은 16~27절에서 다룬다.

## 2. 현재 구조

현재 흐름은 `공급사 CSV -> etl.pipeline -> 표준 CSV/reject CSV/summary JSON -> etl.load_cli -> PostgreSQL staging`이다.

- `etl_load_runs`는 `profile_name`, `profile_version`, 파일 해시, `total_rows`, `rejected_rows`, `error_counts`를 저장한다.
- `catalog_products_staging`은 정상 변환 상품을 `etl_load_run_id`에 연결한다.
- `etl_rejected_rows`는 reject CSV가 제공된 경우 오류 구조와 마스킹된 원본만 저장한다.
- `inspect_dataframe()`는 표준 컬럼 DataFrame을 현재 `INSPECTION_VERSION`으로 검사한다. inspection 이력은 ETL batch와 연결되지 않는다.
- staging에는 batch 내부 상품 identity unique constraint가 없으며, 운영 상품 persistence와 promotion은 별도 service/API가 담당한다. promotion은 staging 행을 직접 수정하지 않고 운영 상품 persistence에만 insert/update한다.

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

## 4. 구현된 persistence 모델

### `catalog_products`

| 컬럼 | 정책 |
| --- | --- |
| `id` | `BIGINT` primary key |
| `supplier_key`, `external_product_id` | `NOT NULL`, `UNIQUE (supplier_key, external_product_id)` |
| `product_group_id`, `product_name`, `category`, `color`, `size`, `image_path` | 표준 staging 필드, `NOT NULL` |
| `stock`, `price` | `NOT NULL`, 0 이상 |
| `sale_price` | nullable, 값이 있으면 0 이상 |
| `description`, `seller` | nullable 표준 staging 필드 |
| `source_etl_load_run_id` | 마지막 반영 batch FK, `ON DELETE RESTRICT` |
| `created_at`, `updated_at` | DB 서버 시간 |

staging 모델을 그대로 복사하지 않는다. staging의 `id`, `etl_load_run_id`, `created_at`은 적재 이력이고 운영 모델에는 안정적인 identity와 마지막 source batch가 필요하다.

### `catalog_promotion_runs`

한 ETL batch의 반영 시도를 기록한다. 상태는 `applying`, `succeeded`, `failed`, `blocked`이며, `succeeded`인 동일 `etl_load_run_id`는 PostgreSQL partial unique index로 한 건만 허용한다. 따라서 `failed`·`blocked` 실행은 다시 기록할 수 있다.

`inserted_count`, `updated_count`, `unchanged_count`, `blocked_count`, `inspection_version`, `preview_hash`, `preview_schema_version`, `error_count`, `warning_count`, `started_at`, `completed_at`, `failure_code`, `safe_failure_message`, `created_at`을 저장한다. count는 0 이상이고 `applying`은 미완료, 나머지 상태는 완료 시각을 요구한다. 실패 정보에는 SQL, DB URL, 내부 파일 경로, traceback을 저장하지 않는다.

### `catalog_product_changes`

append-only audit log다. `promotion_run_id`, `catalog_product_id`, `action`(`insert`/`update`), `changed_fields`, `before_data`, `after_data`, `created_at`을 저장한다. `changed_fields`는 비어 있지 않은 JSON object, `after_data`는 JSON object여야 한다. `insert`의 `before_data`는 SQL `NULL`, `update`의 `before_data`는 JSON object여야 하며, `JSONB(none_as_null=True)`로 Python `None`을 SQL `NULL`로 보존한다. `unchanged`는 변경 이력 행을 만들지 않는다.

모든 새 FK는 `ON DELETE RESTRICT`다. 운영 상품·promotion 실행·감사 이력의 출처를 보존하고, 부모 행이 참조 중일 때 삭제되지 않게 한다.

### Alembic migration과 검증

`20260728_0006_create_catalog_promotion_tables.py`는 revision `20260728_0006`, down revision `20260728_0005`다. upgrade는 `catalog_products` → `catalog_promotion_runs` → `catalog_product_changes` 순서로, downgrade는 역순으로 실행한다. 기존 inspection·ETL staging 테이블은 downgrade 대상이 아니다.

격리된 PostgreSQL 18 환경에서 빈 DB의 upgrade, `0006`에서 `0005` downgrade, 재-upgrade와 단일 Alembic head를 검증했다. promotion PostgreSQL 테스트 10건은 복합 unique, succeeded partial unique, JSONB object·빈 값·action 규칙, `ON DELETE RESTRICT`를 확인한다.

## 5. 설계 당시 품질 게이트와 현재 구현 정책

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

이 결과는 기존 `inspection_runs`에 저장하지 않으며 별도 promotion validation 테이블도 만들지 않는다. `catalog_promotion_runs`에는 실행 당시의 `inspection_version`, `preview_hash`, `error_count`, `warning_count`를 기록한다.

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

실제 반영 endpoint는 다음과 같다.

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

같은 batch가 이미 `succeeded`면 기존 run 결과를 반환하고 다시 반영하지 않는다. 동일 batch 동시 요청의 service-level 제어는 `SELECT ... FOR UPDATE`로 설계하며, DB는 succeeded 상태에 대한 partial unique index를 최종 보호선으로 사용한다. 서로 다른 batch의 같은 운영 상품 갱신은 identity 순서로 행을 잠그고 운영 상품 unique constraint를 최종 보호선으로 사용한다.

## 11. upsert와 삭제 정책

비교·반영 필드는 `product_name`, `product_group_id`, `category`, `color`, `size`, `stock`, `price`, `sale_price`, `image_path`, `description`, `seller`다.

- 운영 상품이 없으면 `insert`한다.
- identity가 있고 하나라도 다르면 `update`한다.
- 모두 같으면 `unchanged`이며 UPDATE, `updated_at` 변경, 변경 이력 행을 만들지 않는다.
- `supplier_key`, `external_product_id`, `created_at`은 update하지 않는다.
- staging은 공급사의 전체 최신 snapshot이다. optional `sale_price`, `description`, `seller`의 `NULL`은 기존 값을 유지하는 뜻이 아니라 값을 비우는 뜻이다.

새 batch에 없는 기존 운영 상품은 삭제·비활성화하지 않는다. hard delete, 자동 rollback, 선택 반영은 이번 MVP 범위 밖이다.

## 12. 완료된 검증과 회귀 테스트 범위

다음 persistence 범위는 구현·검증을 완료했다.

- migration의 upgrade/downgrade/재-upgrade와 단일 head
- `catalog_products` 복합 unique, 값 CHECK constraint, ETL 출처 FK RESTRICT
- `catalog_promotion_runs` 상태·count·완료 시각 CHECK constraint와 succeeded partial unique index
- `catalog_product_changes` JSONB shape·insert/update `before_data` 규칙과 audit FK RESTRICT
- Python `None`이 JSONB `null`이 아닌 SQL `NULL`로 저장되도록 한 `none_as_null=True` 회귀

현재 구현에서는 다음 회귀 동작을 테스트로 고정한다.

- migration의 upgrade/downgrade/재-upgrade, unique/FK/CHECK/index, promotion run의 succeeded partial unique
- 품질 summary 누락, reject 존재, empty staging, batch 내부 identity 중복, inspection error의 전체 차단
- warning만 있는 batch의 허용과 warning count 반환
- preview의 insert/update/unchanged와 필드별 before/after, preview 호출의 DB 무변경
- canonical hash의 정렬·JSON·SHA-256 재현성, staging/규칙/운영 before 상태 변경 시 `preview_stale`
- insert/update/unchanged, 단일 transaction commit, 중간 실패 rollback, audit append
- 동일 batch 재요청·동시 요청의 idempotency, 다른 batch의 동일 identity 경합
- 기존 ETL CLI, staging 적재, ETL 조회/reject API, inspection API/jobs, Streamlit 읽기 화면, Playwright ETL E2E 회귀

## 13. 설계 당시 구현 순서

다음 순서는 현재 구현이 완료되기 전의 설계 기록이다. 현재 저장소에서는 아래 항목을 모두 구현하고 CI·Chromium E2E로 검증했다.

```text
1. promotion preview service
2. promotion preview FastAPI endpoint
3. 실제 승인형 promotion transaction과 `catalog_product_changes` audit 저장
4. 중복 요청·동시성 PostgreSQL 통합 테스트
5. Streamlit preview·승인 UI
6. Playwright promotion E2E
```

설계 당시 다음 코딩 작업은 **promotion preview dry-run service**였다. 현재 저장소에서는 preview가 운영 상품 테이블 비교, hash 재검증, 승인형 반영까지 구현되어 있다.

## 14. 현재 단계와 후속 범위

현재 MVP에서는 개별 상품 선택 반영, 자동 삭제·비활성화, hard delete, 예약 반영, 권한 관리, promotion 자체의 Redis/Celery 처리, streaming·증분 ETL, preview 영구 저장을 제외한다. 실제 Railway/운영 DB가 아닌 합성 fixture와 테스트 PostgreSQL에서 promotion을 검증했다.

succeeded promotion run 단위의 되돌리기는 16~27절의 rollback 기능으로 구현했다. 다만 이는 하나의 promotion run을 대상으로 한 사후 되돌리기이며, promotion 실행 자체를 취소하거나 미래 시점에 예약 실행하는 기능, 여러 promotion을 한 번에 되돌리는 일괄 rollback, 임의 시점으로 되돌리는 point-in-time recovery는 여전히 범위 밖이다.

## 15. 최종 결정

운영 상품 identity는 `(profile_name, product_id)`를 `(supplier_key, external_product_id)`라는 운영 모델 이름으로 표현한다. 이를 보장하는 persistence 모델·migration과 PostgreSQL 제약 검증은 완료했다. 현재 promotion은 품질 summary, reject, empty staging, batch 내부 중복, 재검수 오류를 배치 전체 차단 사유로 사용하고, preview와 실제 반영에서 동일 staging을 재검수하며 canonical preview hash로 stale 상태를 막는다.

promotion 실행 후 잘못된 반영을 되돌려야 하는 문제는 rollback 기능으로 해결했다. rollback도 promotion과 같은 원칙을 따른다. preview 단계에서는 DB를 바꾸지 않고, 실행 직전 서버가 현재 상태를 다시 확인하며, 하나의 transaction으로 전체를 성공시키거나 전혀 반영하지 않는다. 자세한 설계와 검증은 16~27절에 기록한다.

## 16. Rollback 문제 정의

promotion만 있으면 `staging 데이터 -> 운영 Catalog 반영`은 가능하지만, 잘못된 데이터를 반영한 경우 안전하게 되돌릴 방법이 없었다. 단순히 audit에 저장된 과거 값으로 덮어쓰는 방식은 위험하다.

```text
Promotion A: price 10000 -> 12000
이후 다른 변경: price 12000 -> 15000
Promotion A를 단순 되돌리면: price 15000 -> 10000
```

이 경우 Promotion A 시점 이후에 발생한 정상적인 최신 변경(12000 -> 15000)까지 사라진다. 따라서 rollback 실행 직전에 현재 Catalog 상태가 해당 promotion이 만든 결과 그대로인지 다시 확인해야 한다는 것이 이 기능의 핵심 문제다.

## 17. Rollback Preview 설계

`db/catalog_promotion_rollback_service.py`의 `preview_catalog_promotion_rollback()`은 다음 순서로 동작한다.

```text
target CatalogPromotionRun 조회
-> 상태가 succeeded가 아니면 blocked reason 추가
-> 이미 succeeded 상태의 CatalogPromotionRollback이 있으면 blocked reason 추가
-> 해당 promotion_run_id의 CatalogProductChange(promotion audit) 전체 조회
-> audit이 없으면 blocked reason 추가
-> 대상 catalog_product_id의 현재 CatalogProduct 조회
-> build_rollback_preview_items()로 상품별 rollback_action·conflict 계산
-> build_rollback_preview_hash()로 preview hash 계산
```

이 함수는 SELECT만 수행하며 어떤 테이블도 변경하지 않는다. 반환하는 `CatalogPromotionRollbackPreview`의 주요 필드는 `target_promotion_run_id`, `preview_schema_version`, `preview_hash`, `rollback_eligible`, `blocked_reasons`, `restore_count`, `delete_count`, `conflict_count`, `items`이며, `items`의 각 항목은 `audit_id`, `catalog_product_id`, `external_product_id`, `rollback_action`(`delete`/`restore`), `current_data`, `restore_data`, `conflict`, `conflict_reason`을 갖는다. 이 필드는 `api/schemas.py`의 `CatalogPromotionRollbackPreviewResponse`/`CatalogPromotionRollbackPreviewItemResponse`와 그대로 대응한다.

## 18. INSERT / UPDATE 복원 전략

`build_rollback_preview_items()`는 promotion audit의 `action`을 기준으로 두 경우를 나눈다.

INSERT promotion 상품(audit.action == `"insert"`)은 `rollback_action = "delete"`이며 `restore_data`는 없다. 실행 시 `session.delete(product)`로 실제 삭제한다.

UPDATE promotion 상품(audit.action == `"update"`)은 `rollback_action = "restore"`이며 `restore_data = audit.before_data`다. 실행 시 `COMPARISON_FIELDS`(`product_name`, `product_group_id`, `category`, `color`, `size`, `stock`, `price`, `sale_price`, `image_path`, `description`, `seller`) 전체를 `before_data` 값으로 되돌리고 `updated_at`도 갱신한다. `before_data`는 promotion 실행 당시 이미 JSONB로 저장해 둔 값이므로, 별도 계산 없이 그 값을 그대로 복원한다.

두 경우 모두 아래 conflict 조건을 만족할 때만 허용한다.

```text
현재 catalog_products 상태 == 해당 promotion audit의 after_data
```

## 19. Conflict Detection

이 기능에서 가장 중요한 안전장치다. `_product_data()` 함수는 `CatalogProduct`에서 정확히 다음 business field만 추출한다.

```text
external_product_id, product_group_id, product_name, category,
color, size, stock, price, sale_price, image_path, description, seller
```

`id`, `created_at`, `updated_at`, `source_etl_load_run_id` 같은 ORM 내부·운영 메타 필드는 비교에 포함하지 않는다. promotion 당시 저장해 둔 `audit.after_data`도 같은 필드 집합의 JSONB이므로, 현재 값과 `after_data`를 dict로 직접 비교(`current != expected`)할 수 있다.

두 값이 다르면 `rollback_conflict` blocked reason을 추가하고 해당 상품의 rollback을 막는다. 취지는 명확하다. 과거 promotion을 되돌린다는 이유로 그 이후에 발생한 정상적인 최신 변경까지 덮어써서는 안 된다. preview의 `conflict_count`가 하나라도 있으면 `rollback_eligible`은 `False`가 된다.

## 20. Rollback Preview Hash와 stale 방어

promotion preview와 마찬가지로 rollback preview에도 TOCTOU(preview 확인 시점과 실제 실행 시점 사이의 간극) 문제가 있다. `build_rollback_preview_hash()`는 다음 canonical JSON을 SHA-256으로 계산한 64자리 소문자 hex다.

```text
preview_schema_version (현재 1)
target_promotion_run_id
items: [
  { audit_id, catalog_product_id, action, expected_after(after_data), restore_before(before_data), current }
  ...
]
```

`items`는 `(catalog_product_id, audit_id)` 오름차순으로 정렬한 뒤 `json.dumps(sort_keys=True, separators=(",", ":"), ensure_ascii=False)`로 직렬화한다. 정렬 기준을 고정해 DB 조회 순서나 Python dict 순서에 관계없이 같은 데이터면 항상 같은 hash가 나오게 한다. 대상 promotion audit이 없으면 `preview_hash`는 `None`이며 이 경우 rollback을 허용하지 않는다.

실제 실행 endpoint(`execute_catalog_promotion_rollback()`)는 preview 값을 신뢰하지 않는다. 요청을 받으면 대상 promotion run·기존 rollback 여부·audit·현재 상품을 다시 조회해 preview를 새로 계산하고, 새 hash를 요청의 `expected_preview_hash`와 비교한다. 다르면 `preview_stale`로 실행을 막고 운영 상품을 변경하지 않는다.

```text
Rollback Preview 생성 -> canonical payload -> hash 생성
(사용자 확인 중 Catalog 변경 가능)
실제 Rollback 요청 -> 같은 세션에서 preview 재계산 -> hash 재계산 -> 기존 hash와 비교
불일치 -> preview_stale -> DB 변경 없음
```

## 21. 서버 Confirmation

`_validate_request()`는 DB에 접근하기 전에 두 조건을 확인한다.

```text
confirmation이 True가 아니면 CatalogPromotionRollbackConfirmationRequiredError
expected_preview_hash가 64자리 소문자 SHA-256 hex가 아니면 CatalogPromotionRollbackInvalidPreviewHashError
```

FastAPI route는 이 두 예외를 각각 HTTP `400`(`confirmation_required`)과 `422`(`invalid_preview_hash`)로 변환한다. Streamlit의 확인 checkbox는 사용자 실수를 막는 1차 안전장치일 뿐이며, API를 직접 호출해도 서버가 같은 조건을 다시 검증한다. 즉 안전성은 `UI 안전장치 + API 서버 안전장치`의 조합으로 보장한다.

## 22. Transaction Atomicity와 실패 기록

rollback 대상 상품이 여러 개일 수 있으므로 전체 실행은 하나의 `with session.begin():` 블록 안에서 처리한다. 이 블록 안에서 대상 promotion run, 기존 rollback 여부, 대상 audit, 대상 상품을 모두 `SELECT ... FOR UPDATE`로 잠근 뒤 preview를 다시 계산한다.

conflict가 있거나 hash가 다르면 상품은 전혀 변경하지 않고, 그 사실을 기록하는 `CatalogPromotionRollback`(상태 `blocked`) 한 건만 같은 transaction 안에서 추가한 뒤 정상 반환한다.

조건을 통과하면 `CatalogPromotionRollback`(상태 `applying`)을 만들고, 상품마다 삭제 또는 필드 복원을 수행하면서 `CatalogPromotionRollbackChange` 감사 행을 함께 추가한다. 모든 상품 처리가 끝나면 상태를 `succeeded`로 갱신하고 `with` 블록이 정상 종료되며 commit된다.

도중 어떤 예외든 발생하면(예: 상품 값 CHECK constraint 위반) `with` 블록이 예외로 종료되며 그 transaction의 모든 변경, 즉 이미 반영한 상품 복원·삭제와 방금 만든 `applying` rollback run까지 전부 rollback된다. 이후 별도의 새 짧은 transaction 하나로 상태 `failed`인 `CatalogPromotionRollback` 한 건만 기록하고, 호출자에게는 `CatalogPromotionRollbackExecutionFailedError`를 발생시킨다.

```text
상품 A 복원 (세션 내)
상품 B 복원 (세션 내)
상품 C 처리 중 예외
-> 전체 transaction rollback (A, B도 취소)
-> 별도 transaction으로 failed run 1건만 기록
-> 성공 rollback run 없음, 부분 audit 없음
```

이 all-or-nothing 동작은 로컬 disposable PostgreSQL에서 상품 하나의 복원값이 `catalog_products`의 `price >= 0` CHECK constraint를 위반하도록 강제한 뒤, 두 상품 모두 원래 값(rollback 시도 전 값)을 그대로 유지하고 `catalog_promotion_rollback_changes`가 0건, `catalog_promotion_rollbacks`에 `failed` 상태 1건만 남는 것을 확인해 검증했다.

## 23. Duplicate Rollback Protection

같은 promotion run을 두 번 되돌릴 수 없도록 두 layer로 방어한다.

- Service level: 실행 transaction 안에서 같은 `target_promotion_run_id`의 `succeeded` 상태 `CatalogPromotionRollback`을 `SELECT ... FOR UPDATE`로 조회하고, 있으면 `CatalogPromotionRollbackAlreadyExecutedError`를 발생시킨다.
- DB level: `catalog_promotion_rollbacks`에 `target_promotion_run_id`, `status = 'succeeded'` 조건의 partial unique index(`ux_catalog_promotion_rollbacks_target_promotion_run`)가 있다.

service level 확인은 사용자에게 바로 이해할 수 있는 오류(`already_rolled_back`, HTTP `409`)를 주기 위한 것이고, DB unique index는 동시에 두 요청이 들어오는 경쟁 조건에 대한 최종 방어선이다. 애플리케이션 검증만으로는 두 요청이 거의 동시에 `FOR UPDATE` 잠금을 얻으려는 경우까지 완전히 막는다고 보장할 수 없으므로, DB 제약을 최종 보호선으로 유지한다.

## 24. Rollback Audit 모델과 Migration

`CatalogPromotionRollback`은 rollback 실행 한 건을 기록한다.

| 필드 | 설명 |
| --- | --- |
| `id` | `BIGINT` primary key |
| `target_promotion_run_id` | 대상 `catalog_promotion_runs.id`, FK `ON DELETE RESTRICT` |
| `status` | `applying` / `succeeded` / `failed` / `blocked` |
| `preview_hash`, `preview_schema_version` | 실행 시점에 확정된 rollback preview hash와 schema 버전 |
| `restored_count`, `deleted_count`, `conflict_count` | 처리 결과 count |
| `failure_code`, `safe_failure_message` | blocked/failed 상태의 안전한 사유 |
| `started_at`, `completed_at`, `created_at` | 실행 시각 |

`CatalogPromotionRollbackChange`는 rollback이 상품별로 만든 변경을 기록하는 append-only audit이다.

| 필드 | 설명 |
| --- | --- |
| `id` | `BIGINT` primary key |
| `rollback_run_id` | 대상 `catalog_promotion_rollbacks.id`, FK `ON DELETE RESTRICT` |
| `original_audit_id` | 원본 `catalog_product_changes.id`, FK `ON DELETE RESTRICT` |
| `catalog_product_id` | 대상 상품 ID, FK 없음 |
| `action` | `delete` / `restore` |
| `changed_fields`, `before_data`, `after_data` | JSONB, `delete`는 `after_data`가 `NULL`, `restore`는 `NULL`이 아님 |

`20260803_0007_create_catalog_promotion_rollback_tables.py`는 이 두 테이블과 관련 CHECK constraint·index·FK를 생성한다. 이 시점에는 `catalog_promotion_rollback_changes.catalog_product_id`에도 `catalog_products.id`를 향한 `ON DELETE RESTRICT` FK가 있었다.

`20260803_0008_allow_catalog_product_audit_detach.py`는 `catalog_product_changes.catalog_product_id`와 `catalog_promotion_rollback_changes.catalog_product_id`의 FK를 모두 제거한다. INSERT promotion을 rollback하면 해당 상품을 실제로 삭제하는데, 그 상품을 가리키는 `RESTRICT` FK가 남아 있으면 두 감사 이력 중 하나가 그 상품을 참조하고 있다는 이유로 삭제 자체가 거부된다. 이 migration은 `Catalog Product의 생명주기`와 `Audit 기록의 생명주기`를 분리하기 위한 것이며, 상품이 삭제되어도 원본 promotion audit과 rollback audit 모두 그대로 남도록 한다. downgrade는 두 FK를 다시 `RESTRICT`로 만든다. 이미 삭제된 상품을 참조하는 audit 행이 존재하는 상태에서 이 downgrade를 실행하면 실패할 수 있다는 점은 의도된 제약이며, 검증은 데이터가 없는 빈 DB에서만 수행했다.

## 25. Rollback 완료된 검증 범위

로컬 disposable PostgreSQL(운영·Railway DB와 분리된 컨테이너)과 GitHub Actions PostgreSQL 서비스 양쪽에서 `tests/test_catalog_promotion_rollback_contract.py`의 PostgreSQL 통합 테스트로 다음을 확인했다.

- INSERT promotion rollback: 상품 삭제, 원본 promotion audit과 rollback audit 모두 보존
- UPDATE promotion rollback: `COMPARISON_FIELDS` 전체가 promotion 이전 값으로 정확히 복원
- Conflict: promotion 이후 직접 수정된 상품에 대한 rollback 차단과 최신 값 유지
- Preview stale: 오래된 `expected_preview_hash`로는 실행되지 않고 운영 상품 무변경
- Duplicate rollback: service 예외와 DB unique constraint 위반 양쪽에서 차단
- Transaction atomicity: 강제 실패 시 부분 변경 없음, `failed` run 1건만 기록
- Alembic upgrade head, `0007`/`0006`으로의 downgrade와 재-upgrade, 단일 head

이후 rollback 실행 이력과 상품별 change audit 조회(27절)를 추가하면서 검증 범위를 다음 계층까지 넓혔다.

| 계층 | 검증 파일 | 확인 내용 |
| --- | --- | --- |
| Query service | `tests/test_catalog_promotion_rollback_query_service.py` | 목록·상세·change 조회의 정렬·pagination·읽기 전용(쓰기 없음)과 parent 없음 / change 0건 구분 |
| API | `tests/test_api_catalog_promotion_rollbacks.py` | 세 GET endpoint의 기본 page·pagination 전달·잘못된 파라미터 `422`·안전한 `404`·parent 존재 시 빈 목록 |
| API Client | `tests/test_catalogguard_api_client.py` | ID·pagination validation, 응답 shape validation, `delete`/`restore` action validation, `404` -> `CatalogPromotionRollbackNotFoundError` |
| Streamlit | `tests/test_catalog_promotion_rollback_history_ui.py` | History·Detail·Change Audit 표 구성과 AppTest 렌더링, 빈 상태·안전한 오류, change pagination 시 상세 재조회 없음, 선택 변경 시 stale 상태 제거 |
| RBAC | `tests/test_api_rbac.py` | 세 조회 endpoint의 `401`/`403` 경계 |
| Actor Audit | `tests/test_actor_audit.py` | rollback run의 `actor_user_id`·`actor_username`이 JWT `current_user`에서만 기록 |
| Browser E2E | `tests/e2e/test_etl_browser_e2e.py` | 실제 Chromium에서 Promotion -> Rollback -> History -> Detail -> 상품 Rollback 변경 Audit 렌더링과 PostgreSQL 최종 상태 |

기준 저장소 상태의 GitHub Actions run `30888320849`이 성공했으며, 이 run의 `test` job 로그에서 위 PostgreSQL 통합 테스트가 skip 없이 실제로 실행되고 통과한 것을 확인했다. FastAPI 서버·PostgreSQL·`clients/catalogguard_api.py`를 실제로 연결해 rollback-preview/rollback API의 404·stale·중복 응답도 확인했다.

Rollback 조회 계층까지 포함한 검증은 Rollback Change Audit 기능 완료 commit `abcea748e299009b4889b0daa98ad4c9c97e770b`을 대상으로 한 GitHub Actions run `31487868946`에서 확인했으며, 이 run의 `test`(`1451 passed`, `4 deselected`)·`browser-e2e`·`terraform-validate`·`kubernetes-smoke` 4개 job이 모두 성공했다. Browser E2E의 통과 test 수(2건)는 로컬 verbose 실행에서 확인한 값이고, CI에서는 같은 runner가 exit 0으로 끝나 `browser-e2e` job이 success인 것으로 확인한다. runner가 성공 시 pytest 출력을 보존하지 않기 때문이다.

## 26. Rollback 현재 한계

- `already_rolled_back`, `rollback_not_eligible`, `rollback_failed` 같은 실행 계열 오류 코드는 `clients/catalogguard_api.py`에서 전용 예외가 아닌 일반 오류로 처리된다. 전용 예외는 `preview_stale`과 조회 계층의 `404`(`CatalogPromotionRollbackNotFoundError`)뿐이다.
- 여러 promotion을 한 번에 되돌리는 일괄 rollback은 지원하지 않는다.
- 임의 시점으로 되돌리는 point-in-time recovery는 지원하지 않으며, rollback은 하나의 succeeded promotion run 단위로만 동작한다.
- Change Audit 조회는 `limit`/`offset` pagination만 제공하고, action(`delete`/`restore`)·상품·기간 filter나 검색·export는 지원하지 않는다.
- Browser E2E fixture는 INSERT promotion 2건을 되돌리는 delete-only 시나리오다. `restore` change가 화면에 표시되는 경로는 AppTest와 service·API 테스트로만 확인했고 실제 브라우저 시나리오는 없다.

## 27. Rollback 실행 이력과 상품별 Change Audit 조회

실행 API만 있을 때는 rollback 직후 응답으로만 결과를 알 수 있었다. 나중에 "언제 누가 무엇을 되돌렸는지"를 다시 확인하려면 DB를 직접 조회해야 했으므로, 읽기 전용 조회 endpoint 3개를 추가했다.

| Endpoint | 권한 | 반환 |
| --- | --- | --- |
| `GET /api/v1/catalog-promotion-rollbacks` | viewer 이상 | rollback 실행 목록(상태 filter, `limit`/`offset`) |
| `GET /api/v1/catalog-promotion-rollbacks/{rollback_run_id}` | viewer 이상 | 단일 rollback 실행 상세와 `preview_hash`·`preview_schema_version` |
| `GET /api/v1/catalog-promotion-rollbacks/{rollback_run_id}/changes` | viewer 이상 | 그 실행이 상품별로 만든 change audit(`limit` 기본 `20`, 최대 `100`) |

세 endpoint 모두 DB를 변경하지 않으므로 viewer도 조회할 수 있다. 실제 되돌리기(`POST .../rollback`)만 operator로 제한한다.

### 27.1 run-level count와 item-level audit

`restored_count`·`deleted_count`·`conflict_count`는 "몇 건을 되돌렸는가"만 알려준다. `/changes`는 그 아래 단계를 보여준다.

```text
어떤 catalog product가
어떤 원본 promotion audit(original_audit_id)을 되돌린 것이고
delete인지 restore인지
어떤 필드가 바뀌었고
그 필드의 변경 전·후 값이 무엇인지
```

응답 항목은 `rollback_change_id`, `rollback_run_id`, `original_audit_id`, `catalog_product_id`, `action`, `changed_fields`, `before_data`, `after_data`, `created_at`이다. `original_audit_id`가 원본 `catalog_product_changes.id`를 가리키므로, rollback audit에서 원본 promotion audit으로 역추적할 수 있다.

### 27.2 parent 없음과 빈 audit 구분

빈 결과를 오류로 다루지 않는다.

```text
rollback run 자체가 없음        -> 404
rollback run은 있고 change 0건  -> 200 + items=[]
```

`blocked`·`failed` rollback은 상품을 전혀 바꾸지 않으므로 change가 0건인 것이 정상이다. 이를 404로 해석하면 정상 상태를 오류로 표시하게 되므로, query service는 parent가 없을 때만 `None`을 반환하고 route는 그 경우에만 `404`로 변환한다.

### 27.3 정렬과 pagination

`created_at DESC, id DESC`로 정렬한다. 같은 transaction에서 만들어진 change들은 `created_at`이 같을 수 있으므로, `id`를 tie-breaker로 두어 page 사이에 순서가 흔들리거나 같은 행이 중복·누락되지 않게 한다. pagination은 `limit`/`offset` 방식의 MVP다.

### 27.4 Streamlit 표시

Rollback 실행 상세 아래에 `상품 Rollback 변경 Audit` 영역이 있고, 표는 `Change ID`, `원본 Audit ID`, `상품 ID`, `외부 상품 ID`, `변경 유형`, `변경 필드`, `변경 전`, `변경 후`, `변경 시각` 컬럼으로 구성한다. `changed_fields`는 필드마다 한 행으로 펼친다.

action은 사용자 표현으로 바꾼다.

```text
delete  -> 상품 삭제
restore -> 이전 상태 복원
```

`delete`는 `after_data`가 `NULL`이므로 외부 상품 ID를 `before_data`에서 가져오고, 변경 후 값은 빈 칸 대신 `삭제됨`으로 표시한다.

상태 관리에서 중요한 것은 stale 방지다. 선택한 rollback이 바뀌면 이전 실행의 change 응답 cache와 offset을 함께 초기화해 다른 rollback의 audit이 화면에 남지 않게 하고, Change Audit page만 이동할 때는 상세 응답 cache를 재사용해 불필요한 재조회를 하지 않는다.
