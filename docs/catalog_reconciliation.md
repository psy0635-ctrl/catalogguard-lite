# Catalog Reconciliation Report

## 1. 왜 필요한가

공급사가 보낸 CSV를 ETL로 적재하고 나면, 운영자가 실제로 묻는 질문은 하나다.

> **"이번 배치에서 정상 적재된 공급사 상품이 지금 운영 카탈로그와 어떻게 다른가?"**

**비교 기준은 원본 CSV 전체가 아니라 `CatalogProductStaging`에 정상 적재된 상품이다.** ETL 변환에서 거부된 행은 staging에 없으므로 비교 대상에 들어오지 않는다. 이 범위 차이는 5장에서 자세히 다룬다.

지금까지 이 질문에 답하는 화면이 없었다. Promotion Preview가 있지만 목적이 다르다. Preview는 **"이 배치를 반영해도 되는가"**를 판정하는 화면이고, 반영 대상인 staging 상품만 본다. 그래서 다음 두 가지를 알 수 없었다.

1. 카탈로그에는 있는데 **이번 배치에는 없던** 상품이 몇 개인가
2. 어떤 **필드가** 얼마나 자주 바뀌는가 (재고만 흔들리는가, 가격도 바뀌는가)

Catalog Reconciliation Report는 이 차이를 **조회 전용**으로 보여 준다. 운영 상품을 바꾸지 않는다.

### Promotion Preview와의 차이

| | Promotion Preview | Catalog Reconciliation Report |
| --- | --- | --- |
| 목적 | 이 배치를 반영해도 되는가(판정) | 지금 무엇이 다른가(설명) |
| 대상 | staging 상품만 | staging + 같은 공급사의 카탈로그 상품 전체 |
| 카탈로그에만 있는 상품 | 보이지 않음 | `not_observed_in_batch`로 보임 |
| 필드별 변경 집계 | 없음 | `field_change_counts` |
| 상태 이름 | `insert` / `update` / `unchanged` | `new` / `changed` / `unchanged` / `not_observed_in_batch` |
| 검수·차단 판정 | 있음(`promotion_eligible`, `blocked_reasons`) | 없음 |
| hash | `preview_hash` 있음 | 없음 |
| HTTP | `POST .../promotion-preview` | `GET .../catalog-reconciliation` |
| 부작용 | 없음(단, 실행 API의 입력이 됨) | 없음 |

상태 이름을 일부러 다르게 붙였다. `insert`/`update`는 **"반영하면 이렇게 된다"**는 행동이고, `new`/`changed`는 **"지금 이렇게 다르다"**는 관측이다. 같은 단어를 쓰면 조회 보고서가 실행 계획처럼 읽힌다.

**Promotion Preview의 계약·hash·eligibility·실행 동작은 이번 작업에서 한 줄도 바꾸지 않았다.**

---

## 2. Identity

두 값으로 상품을 맞춘다.

| 값 | 출처 |
| --- | --- |
| `supplier_key` | `ETLLoadRun.profile_name` |
| `external_product_id` | `CatalogProductStaging.product_id` ↔ `CatalogProduct.external_product_id` |

Promotion Preview와 같은 identity다. `catalog_products`에 `ux_catalog_products_supplier_external_product` unique index가 이미 이 조합으로 걸려 있다.

**다른 공급사의 카탈로그 상품은 보고서에 들어오지 않는다.** 모든 카탈로그 조회가 `supplier_key`로 먼저 좁혀진다.

---

## 3. 네 가지 상태

정확히 네 가지이며, 한 상품은 하나의 상태만 가진다.

| 상태 | 의미 |
| --- | --- |
| `new` | staging에는 있고 현재 카탈로그에는 없음 |
| `changed` | 둘 다 있고, 비교 대상 필드 중 하나 이상 다름 |
| `unchanged` | 둘 다 있고, 비교 대상 필드가 모두 같음 |
| `not_observed_in_batch` | 현재 카탈로그에는 있고, 선택한 staging 배치에는 없음 |

`not_observed_in_batch`는 정확히 **"정상 staging에서 관측되지 않았다"**는 뜻이다. 원본 feed에서 반드시 누락됐다는 뜻이 아니다. 자세한 내용은 5장에 있다.

---

## 4. 비교 필드

`db.catalog_promotion_preview_service.COMPARISON_FIELDS`를 **그대로 재사용한다.**

```text
product_group_id, product_name, category, color, size,
stock, price, sale_price, image_path, description, seller
```

값 정규화(`_product_data()`, `_normalize_integer()`)도 같은 함수를 쓴다. 복제하지 않은 이유는, 복제하면 Promotion Preview 화면과 Reconciliation 화면이 서로 다른 "변경"을 말하게 되기 때문이다. 두 화면이 같은 배치에서 다른 결론을 내면 어느 쪽도 믿을 수 없다.

`external_product_id`는 **identity이므로 변경 필드가 아니다.** 값이 다르면 같은 상품이 아니다.

`changed` 항목만 `changed_fields`를 가진다.

```json
{
  "stock": {"before": 10, "after": 7}
}
```

`before`는 **현재 운영 카탈로그**, `after`는 **이번 배치**다.

`field_change_counts`는 배치 전체 기준으로 "이 필드가 바뀐 상품이 몇 개인가"를 센다. 페이지 기준이 아니다. 한 상품이 두 필드를 바꾸면 두 필드 모두 1씩 올라간다.

---

## 5. `not_observed_in_batch`의 의미

**이 상태는 삭제·판매 종료·품절을 뜻하지 않는다.** 그리고 공급사가 그 상품을 보내지 않았다는 뜻도 아니다.

이 상태가 뜻하는 것은 정확히 하나다.

> **선택한 배치의 정상 staging에서 관측되지 않았다.**

상품이 여기에 들어오는 경로는 최소 두 가지이고, 현재 시스템은 **둘을 구분하지 못한다.**

### (1) ETL reject 때문에 staging에 없는 경우

원본 CSV에는 있었지만 변환에서 거부되어 staging에 적재되지 않았을 수 있다.

```text
원본 CSV      운영 catalog     결과
P001 정상  →  P001         →  changed / unchanged
P002 정상  →  P002         →  changed / unchanged
P003 INVALID_PRICE (reject)   P003  →  not_observed_in_batch
```

`P003`은 공급사가 **보냈다.** 다만 가격이 잘못되어 ETL이 거부했을 뿐이다. 그런데 보고서에는 "이번 배치 미관측"으로 나온다.

이 오해를 막기 위해 응답에 `total_rows`/`loaded_rows`/`rejected_rows`를 함께 싣고, `rejected_rows > 0`이면 UI가 경고한다. 거부 행이 있었다는 사실을 알면 운영자가 "미관측 = 공급사가 안 보냄"으로 단정하지 않는다.

**reject된 행의 상품 식별자를 원본에서 다시 추론하지는 않는다.** `not_observed_in_batch`를 하위 상태로 쪼개지도 않는다. reject raw data에는 마스킹 대상 원본 값이 들어 있어, 이 보고서와 join하면 PII·원본 데이터 노출 위험이 생긴다. 정확도를 조금 올리려고 노출 경로를 만드는 것은 나쁜 거래다.

### (2) 공급사가 이번 피드에 담지 않은 경우

현재 시스템은 공급사 피드가 **전체 snapshot인지 부분(delta) feed인지 보장하지 않는다.** 프로필에도, `ETLLoadRun`에도 그 정보가 없다. 공급사가 이번에 재고 변동분만 보냈다면 나머지 상품이 전부 `not_observed_in_batch`로 나온다. 그 상품들은 멀쩡히 판매 중이다.

### 정리

`not_observed_in_batch`가 보장하는 것은 **관측 사실 하나뿐이다.** 원인은 reject일 수도, 부분 feed일 수도, 실제 단종일 수도 있고, 지금 데이터로는 셋을 구분할 수 없다.

### 왜 자동 삭제하지 않는가

부분 feed 한 번을 전체 snapshot으로 오해하면 **판매 중인 상품이 통째로 사라진다.** 가격 오류로 reject된 상품을 "공급사가 내렸다"고 읽어도 결과는 같다. 되돌리려면 rollback이 필요하고, 그 사이 매출이 빠진다. 관측되지 않았다는 사실만으로는 삭제를 정당화할 수 없다.

그래서 이번 MVP는 다음을 **하지 않는다.**

- 자동 catalog delete
- 자동 품절 / discontinued 처리
- 삭제 후보 목록 제공

API와 UI 문구 모두 이 점을 명시한다.

> "이번 ETL 배치에서 관측되지 않은 운영 상품입니다. 삭제 또는 판매 종료를 의미하지 않으며, 자동 삭제 대상으로 판단하지 않습니다."

거부 행이 있는 배치에는 다음 경고를 함께 띄운다.

> "원본 입력 중 N개 행이 ETL 변환 과정에서 제외되었습니다. 이 보고서는 정상 staging 상품만 운영 카탈로그와 비교하므로, '이번 배치 미관측'에는 reject 때문에 비교에서 빠진 상품이 포함될 수 있습니다."

전체 snapshot 여부를 프로필이 선언하게 되면 그때 "삭제 후보" 판정을 별도 단계로 검토할 수 있다. 지금은 근거가 없다.

---

## 6. 중복 identity

한 staging 배치에 같은 `external_product_id`가 둘 이상 있으면 **보고서를 만들지 않고 거부한다.**

어느 행이 진짜인지 시스템이 알 수 없다. 첫 번째나 마지막 행을 임의로 고르면 운영자가 보는 diff가 실제와 달라지고, **그 사실이 화면에 드러나지도 않는다.** Promotion Preview가 `duplicate_product_identity`로 반영을 막는 것과 같은 안전 철학이다.

`CatalogReconciliationDuplicateIdentityError` → HTTP `409` (`duplicate_product_identity`). 응답에는 SQL·내부 경로·staging row id를 노출하지 않는다.

---

## 7. API

```text
GET /api/v1/etl-loads/{etl_load_run_id}/catalog-reconciliation
```

조회 전용이며 viewer 이상 권한이 필요하다. `CatalogProduct`·`CatalogProductStaging`·`ETLLoadRun` 어느 것도 수정하지 않는다.

| Query | 기본값 | 조건 |
| --- | ---: | --- |
| `limit` | `50` | `1` 이상 `100` 이하 |
| `offset` | `0` | `0` 이상 |

| 상황 | HTTP |
| --- | ---: |
| 정상 | `200` |
| 없는 `etl_load_run_id` | `404` |
| `etl_load_run_id <= 0`, 잘못된 `limit`/`offset` | `422` |
| staging 배치에 중복 identity | `409` (`duplicate_product_identity`) |

### 응답

```json
{
  "etl_load_run_id": 42,
  "supplier_key": "sample_fashion_vendor",
  "total_rows": 15,
  "loaded_rows": 13,
  "rejected_rows": 2,
  "new_count": 1,
  "changed_count": 2,
  "unchanged_count": 10,
  "not_observed_in_batch_count": 1,
  "field_change_counts": {"stock": 15, "price": 3},
  "items": [
    {
      "external_product_id": "P001",
      "status": "changed",
      "changed_fields": {"stock": {"before": 10, "after": 7}}
    },
    {
      "external_product_id": "P900",
      "status": "not_observed_in_batch",
      "changed_fields": {}
    }
  ],
  "total": 14,
  "limit": 50,
  "offset": 0
}
```

### 품질 메타데이터

`ETLLoadRun`이 이미 가진 값을 그대로 전달한다. 새 컬럼·테이블·migration은 없다.

| 필드 | 의미 | nullable |
| --- | --- | --- |
| `total_rows` | ETL이 받은 전체 데이터 행 수 | O (legacy 배치) |
| `loaded_rows` | staging에 정상 적재된 행 수 | X |
| `rejected_rows` | ETL 변환에서 제외된 행 수 | O (legacy 배치) |

품질 요약 저장 기능 도입 이전 배치는 `total_rows`/`rejected_rows`가 `null`이다. **이를 `0`으로 바꾸지 않는다.** "거부 행이 없었다"와 "알 수 없다"는 다른 사실이고, 전자로 표시하면 보고서가 거짓말을 한다. 이 경우 UI는 비교 범위를 확인할 수 없다고 안내한다.

`not_observed_in_batch` 항목은 `changed_fields`가 빈 dict다. **상품이 배치에 없다는 뜻으로 빈 문자열 상품 객체를 만들어 내지 않는다.** 없는 값을 있는 것처럼 표현하면 그 자체가 잘못된 데이터다.

카운트 4개는 **배치 전체 기준**이고 페이지와 무관하다. `total`은 네 카운트의 합이다.

### 정렬

`items`는 결정론적이다.

```text
status 우선순위(new → changed → unchanged → not_observed_in_batch)
  → external_product_id ASC
```

운영자가 먼저 봐야 할 차이가 위로 온다. 순서는 `tests/test_catalog_reconciliation_service.py`가 고정한다.

### 왜 카탈로그를 통째로 읽지 않는가

운영 카탈로그는 배치보다 훨씬 커질 수 있다. 서비스는 다음처럼 나눠 읽는다.

- staging 배치 크기만큼만 메모리에서 `new`/`changed`/`unchanged`로 분류한다
- `not_observed_in_batch`는 **SQL `COUNT`로 개수만** 세고, 요청한 페이지 구간만 `LIMIT`/`OFFSET`으로 읽는다

`not_observed_in_batch`가 정렬 우선순위에서 마지막이므로 전체 순서는 `[staging 기반 항목] + [미관측 항목]`이 된다. 덕분에 페이지를 두 조각으로 나눠 읽을 수 있고, 카탈로그 전체를 Python list로 올리지 않아도 된다.

---

## 8. UI

ETL 적재 이력에서 배치를 선택하면 **"상품 동기화 차이"** 영역이 나온다.

- 신규 / 변경 / 동일 / 이번 배치 미관측 **4개 metric**
- **필드별 변경 건수** 표 (건수 내림차순, 동수면 필드명 오름차순)
- 상품 표: 상품 ID · 상태 · 변경 필드
- `not_observed_in_batch`가 하나라도 있으면 위의 안내 문구를 표시
- `rejected_rows > 0`이면 비교 범위 경고를 **추가로** 표시(미관측 안내와 별개다)
- `rejected_rows`가 `null`인 legacy 배치는 비교 범위를 확인할 수 없다고 안내

다른 배치를 선택하면 캐시된 보고서를 버리고 다시 조회한다.

---

## 9. 현재 한계

- **전체 snapshot 여부를 모른다.** 이것이 `not_observed_in_batch`를 삭제 후보로 쓸 수 없는 근본 이유다. 프로필이 snapshot/delta를 선언하기 전에는 해결되지 않는다.
- **미관측의 원인을 구분하지 못한다.** reject 때문인지, 부분 feed 때문인지, 실제 단종인지 알 수 없다. `rejected_rows`로 "reject가 있었다"까지만 알린다. 원인을 상품 단위로 구분하려면 reject 행의 상품 식별자가 필요한데, 원본 데이터 노출 위험 때문에 이번에는 하지 않았다.
- **status filter가 없다.** 이번 MVP는 `limit`/`offset`만 받는다. `new`만 보는 식의 필터는 다음 단계다.
- **보고서를 저장하지 않는다.** 매 요청마다 계산하며 이력 테이블이 없다. "지난주 대비 변경 추세" 같은 질문에는 답하지 못한다.
- **검수 결과를 포함하지 않는다.** 차이만 설명하고 그 차이가 정상인지 판정하지 않는다. 판정은 Promotion Preview의 몫이다.
- **필드별 변경의 방향을 집계하지 않는다.** "가격이 오른 상품 수"는 없고 "가격이 바뀐 상품 수"만 있다.
- 카탈로그가 매우 크면 `not_observed_in_batch`의 `COUNT`가 느려질 수 있다. 현재 규모에서는 문제되지 않으며, 필요해지면 인덱스를 검토한다.

---

## 참고

- `db/catalog_reconciliation_service.py` — 보고서 계산
- `db/catalog_promotion_preview_service.py` — 재사용하는 비교 필드·값 정규화
- `docs/catalog_promotion_design.md` — Promotion Preview/실행 설계
- `docs/etl_mvp.md` — ETL 적재와 staging 구조
