# Post-Optimization Inspection Rule Profile

## 1. 결론

PR #61~#63의 최적화가 반영된 current main에서 `normal_unique` 10,000행의 가장 느린 rule은 `check_prohibited_and_personal_information`이었다. median은 289.189ms로 독립 측정한 `run_all_rules()` 중앙값 571.644ms의 약 50.6%에 해당한다. 다음 최적화 후보는 이 rule의 **원문 PII regex scan 반복**으로 선정하지만, 이번 작업에서는 측정·문서화만 했고 production 동작은 변경하지 않았다.

## 2. 측정 목적

historical baseline의 순위를 재사용하지 않고, duplicate product name·category mismatch·content safety preprocessing 최적화 뒤의 현재 `RULES` 순위를 다시 측정했다. 목표는 일반 no-issue 입력에서 다음 후보 하나를 근거 있게 고르는 것이다.

## 3. 기준 main SHA

- main SHA: `74c1da2527088f474a3ca688a833a376a7bc64aa`
- latest commit: `perf: reduce content safety normalization work`
- inspection version: `13`

## 4. 이미 완료된 성능 최적화

- duplicate product name의 concentrated duplicate candidate pair 비교 축소
- category mismatch의 keyword normalization/compact 전처리 재사용
- content safety의 prohibited/context policy normalization과 field normalization 재사용

이 문서는 위 작업의 Before/After를 다시 계산하지 않는다.

## 5. 측정 환경

- OS: Windows-11-10.0.26200-SP0
- Python: 3.14.7
- pandas: 3.0.3
- warmup: 1회
- measured: 2회
- timer: `perf_counter_ns()`

## 6. Dataset

기존 `build_synthetic_rows()`와 loader를 그대로 사용했다.

- `normal_unique` 10,000행: unique group/product/name, issue 0건인 일반 경로
- `issue_heavy` 10,000행: 같은 fixture에서 `price=0`, 총 issue 10,000건인 참고 경로

## 7. 측정 방법

각 dataset에서 CSV validation과 product loading을 끝낸 뒤 같은 `Product` list를 각 rule에 전달했다. 각 rule은 warmup 1회 후 2회 측정하고 min/median/max를 기록했다. `run_all_rules()` 전체 timing도 별도로 측정했다. 따라서 independent rule median의 합계와 `run_all_rules()` median은 동일한 값으로 해석하지 않는다.

## 8. normal_unique 10k 전체 rule profile

`run_all_rules()` median은 571.644ms, independent rule median 합계는 528.807ms였다. 아래 순위는 median 내림차순이다.

| rank | rule | median_ms | min_ms | max_ms | issues |
|---:|---|---:|---:|---:|---:|
| 1 | `check_prohibited_and_personal_information` | 289.189 | 275.979 | 302.399 | 0 |
| 2 | `check_duplicate_variant_combination` | 63.881 | 63.045 | 64.717 | 0 |
| 3 | `check_product_category_mismatch` | 57.821 | 47.669 | 67.972 | 0 |
| 4 | `check_duplicate_product_name` | 18.922 | 16.789 | 21.054 | 0 |
| 5 | `check_inconsistent_group_size_system` | 18.409 | 17.931 | 18.886 | 0 |
| 6 | `check_price_outliers` | 18.136 | 11.259 | 25.013 | 0 |
| 7 | `check_inconsistent_group_category` | 15.858 | 14.635 | 17.081 | 0 |
| 8 | `check_duplicate_product_content` | 14.929 | 14.670 | 15.188 | 0 |
| 9 | `check_non_standard_color` | 10.823 | 10.617 | 11.028 | 0 |
| 10 | `check_non_standard_size` | 7.677 | 7.333 | 8.020 | 0 |
| 11 | `check_duplicate_product_id` | 6.725 | 6.401 | 7.050 | 0 |
| 12 | `check_missing_required_fields` | 4.521 | 4.418 | 4.624 | 0 |
| 13 | `check_stock` | 0.549 | 0.532 | 0.565 | 0 |
| 14 | `check_invalid_category` | 0.541 | 0.514 | 0.567 | 0 |
| 15 | `check_sale_price` | 0.444 | 0.439 | 0.449 | 0 |
| 16 | `check_price` | 0.382 | 0.380 | 0.384 | 0 |

## 9. Top 5

share는 independent rule median을 independently measured `run_all_rules()` median 571.644ms로 나눈 참고 비율이다. 서로 다른 호출의 median이므로 합계가 100%가 되거나 정확한 attribution을 뜻하지 않는다.

| rank | rule | median_ms | share / note |
|---:|---|---:|---|
| 1 | `check_prohibited_and_personal_information` | 289.189 | 50.6% |
| 2 | `check_duplicate_variant_combination` | 63.881 | 11.2% |
| 3 | `check_product_category_mismatch` | 57.821 | 10.1% |
| 4 | `check_duplicate_product_name` | 18.922 | 3.3% |
| 5 | `check_inconsistent_group_size_system` | 18.409 | 3.2% |

## 10. issue_heavy 참고 결과

`issue_heavy` 10,000행의 `run_all_rules()` median은 574.117ms, 전체 issue 수는 10,000이었다. Top 5는 다음과 같다.

| rank | rule | median_ms | issues |
|---:|---|---:|---:|
| 1 | `check_prohibited_and_personal_information` | 232.116 | 0 |
| 2 | `check_duplicate_variant_combination` | 61.646 | 0 |
| 3 | `check_inconsistent_group_size_system` | 58.076 | 0 |
| 4 | `check_product_category_mismatch` | 49.630 | 0 |
| 5 | `check_duplicate_product_name` | 19.289 | 0 |

`check_price`는 이 fixture의 10,000 issue를 만들었지만 median은 8.898ms였다. issue allocation 비용만으로 normal path의 Top 1이 바뀌지는 않았다.

## 11. 이전 historical baseline과의 구분

`inspection_pipeline_performance_baseline.md`는 PR #60 당시 Before 기록이며 덮어쓰지 않았다. 현재 값은 여러 후속 최적화와 측정 노이즈가 함께 반영된 post-optimization snapshot이다. 특정 PR 하나의 절대 개선 효과는 각 PR의 자체 Before/After 문서를 기준으로 해석한다.

## 12. 현재 병목 분석

현재 1위 rule은 product마다 `product_name`, `description`, `seller` 세 non-empty field를 순서대로 돈다. PR #63으로 policy term과 field normalization 반복은 줄었지만, 각 field의 원문에는 email, mobile phone, landline phone, RRN, bank-account pattern 탐색이 여전히 수행된다. phone은 mobile·landline 두 pattern을 모두 scan하고, raw phone/RRN span은 bank overlap 판단을 위해 유지된다. 이 rule은 normal 10k에서 issue 0건이어도 이 검사 경로를 반복하므로 일반 입력 비용이 크다.

## 13. 다음 최적화 후보 선정

- selected rule: `check_prohibited_and_personal_information`
- current rank: 1
- normal_unique 10k median: 289.189ms

선정 이유는 가장 큰 실제 normal-path 비용, 모든 상품의 세 text field에 반복되는 scan 경로, 그리고 PR #63 뒤에도 남은 명확한 raw regex 반복 구조다. 새 dependency나 결과 정렬 변경 없이 별도 범위로 검토할 수 있고, masking·dedup·raw span·issue order contract를 중심으로 회귀를 고정할 수 있다.

## 14. 선정하지 않은 후보와 이유

- `check_duplicate_variant_combination` (2위, 63.881ms): variant key grouping과 duplicate-content exception, issue ordering이 얽혀 있어 current 1위보다 비용은 작지만 contract 검증 범위가 더 넓다.
- `check_product_category_mismatch` (3위, 57.821ms): keyword 전처리 재사용은 이미 적용됐다. 추가 후보가 있는지는 별도 input-shape와 contract 분석이 필요하며, 현재 1위 비용보다 작다.

## 15. 측정 한계

이 결과는 synthetic dataset, 개발 PC, warmup 1회·measured 2회의 local timing이다. 실제 production traffic, 텍스트 길이·PII 발생률·duplicate bucket 분포, 동시 사용자와 DB/network latency를 나타내지 않는다.

## 16. 다음 작업

다음 PR에서는 `check_prohibited_and_personal_information`의 PII regex scan을 세부 profile로 분해한 뒤, 원문 기준 결과·masking·dedup·span overlap을 보존하는 필요한-character guard 같은 가장 작은 scan 절감안을 별도 계약 테스트와 함께 검토한다. 이 문서는 코드를 구현하지 않는다.
