# Category Mismatch Keyword Scan Performance Optimization

## 1. 결론

상품명 카테고리 불일치 검사는 keyword 검색값을 상품마다 다시 만들고 있었다. `find_category_mismatches()` 호출마다 keyword의 normalized/compact 값을 한 번 준비하고, 상품명은 상품당 한 번만 정규화하도록 바꿨다. normal_unique 10,000행에서 category mismatch 중앙값은 692.752ms에서 63.180ms로 90.9% 감소했다. 검수 결과 의미는 바꾸지 않았으므로 `INSPECTION_VERSION = "13"`을 유지한다.

## 2. 문제 정의

`CATEGORY_KEYWORDS`에는 5개 category, 41개 keyword entry가 있다. 기존 구현은 상품마다 product name을 두 번 정규화하고, 41개 keyword 각각을 정규화·compact 처리했다. normal_unique 데이터처럼 10,000개 상품이 모두 이 경로를 지나면 준비 비용이 누적된다.

## 3. 기존 알고리즘

각 상품에서 category를 정규화한 뒤 product name의 blank 여부를 확인했다. 이어서 keyword matcher가 product name을 다시 정규화하고, category/keyword 순서로 모든 keyword를 정규화·compact한 뒤 포함 여부를 검사했다.

## 4. 반복 비용이 발생한 이유

keyword 자체는 inspection 안에서 변하지 않지만 검색용 normalized/compact 값이 상품마다 새로 계산됐다. 또한 같은 product name이 blank 검사와 keyword matcher에서 두 번 정규화됐다.

## 5. 결과 contract

다음 계약을 회귀 테스트로 고정했다.

- mismatch 판단과 ambiguous multi-category 무결과 처리
- `ValidationIssue` 전체 payload와 입력 순서
- rule, severity, product ID, group ID와 message
- 같은 category에서 여러 keyword가 맞을 때 첫 원본 keyword 선택
- category alias와 product-name normalization 의미

## 6. 최적화 설계

`_build_category_keyword_search_index()`가 category와 keyword의 원래 순서를 유지한 채 `(original_keyword, normalized_keyword, compact_keyword)`를 만든다. `find_category_mismatches()`는 이 index를 한 번 만들고, 각 상품의 normalized name을 `_find_category_keyword_matches_from_normalized_name()`에 전달한다. 기존 standalone `_find_category_keyword_matches()`는 이름을 정규화한 뒤 같은 내부 helper를 호출하므로 기존 private helper의 반환 의미도 유지한다.

## 7. 왜 결과 의미가 같은가

검색 순서는 `CATEGORY_KEYWORDS.items()`와 각 keyword tuple의 순서를 그대로 따른다. message에는 precompute한 검색값이 아니라 보존한 원본 keyword를 사용한다. 같은 normalized/compact 문자열과 기존 substring 조건을 사용하고 early break, set 정렬, alias 변경은 추가하지 않았다.

## 8. 측정 환경

- OS: Windows-11-10.0.26200-SP0
- Python: 3.14.7
- pandas: 3.0.3
- dataset: 기존 opt-in benchmark의 `normal_unique` synthetic CSV
- warmup: 1회
- measured: 2회, `perf_counter_ns()` median

명세의 예상 Python 3.11.9와 달리 현재 `.venv`는 Python 3.14.7이었다. 이 문서의 Before/After는 같은 실제 환경에서, 기존 `HEAD` detector source를 독립적으로 실행한 Before와 변경 후 After를 비교한다. historical baseline 문서의 수치는 덮어쓰지 않는다.

## 9. Python 3.14 Before

| rows | category mismatch median | rules total median | inspection median |
|---:|---:|---:|---:|
| 1,000 | 52.576ms | 113.513ms | 146.464ms |
| 5,000 | 304.619ms | 590.568ms | 917.765ms |
| 10,000 | 692.752ms | 1,151.961ms | 1,798.485ms |

## 10. Python 3.14 After

| rows | category mismatch median | rules total median | inspection median |
|---:|---:|---:|---:|
| 1,000 | 4.889ms | 63.038ms | 137.349ms |
| 5,000 | 24.311ms | 297.770ms | 600.908ms |
| 10,000 | 63.180ms | 599.604ms | 1,252.040ms |

## 11. 1k / 5k / 10k 비교

| rows | Before | After | delta | reduction |
|---:|---:|---:|---:|---:|
| 1,000 | 52.576ms | 4.889ms | 47.687ms | 90.7% |
| 5,000 | 304.619ms | 24.311ms | 280.308ms | 92.0% |
| 10,000 | 692.752ms | 63.180ms | 629.572ms | 90.9% |

## 12. Normalization call 구조 비교

`CATEGORY_KEYWORDS`의 실제 entry 수는 41개다. no-keyword 상품 100개에서 기존 구조는 product name 2회와 keyword 41회씩, 총 `100 * (2 + 41) = 4,300`번의 product-name normalization을 수행했다. 변경 후 구조는 product 100회와 keyword 41회로 141번이다. 회귀 테스트는 정확한 구현 수치에 고정하지 않고 `products + keyword entries + small constant`라는 상한으로 product × keyword 형태의 재도입을 막는다.

## 13. 전체 pipeline 영향

normal_unique 10,000행에서 rules total은 1,151.961ms에서 599.604ms, inspection은 1,798.485ms에서 1,252.040ms로 감소했다. validation부터 포함한 end-to-end no DB 중앙값도 2,008.369ms에서 1,431.745ms였다. 두 번 측정한 개발 환경 수치이므로 작은 차이를 운영 보장으로 해석하지 않는다.

## 14. 테스트 결과

- category mismatch + rules: `197 passed`
- 결정론적 normalization-call regression, exact payload/order, first keyword contract를 추가했다.

## 15. 한계

substring 포함 검색 자체와 category별 모든 keyword scan은 그대로다. 실제 운영 상품명 분포와 CPU contention은 이 synthetic benchmark와 다를 수 있다.

## 16. 다음 후보

이번 결과를 바탕으로 다음 후보는 `check_prohibited_and_personal_information`이다. 이 작업에서는 구현하지 않았다.
