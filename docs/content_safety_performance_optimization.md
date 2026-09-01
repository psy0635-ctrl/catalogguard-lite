# Content Safety Scan Preprocessing Performance Optimization

## 1. 결론

`check_prohibited_and_personal_information()`은 각 non-empty field마다 금지어와 계좌 문맥어의 검색용 normalization을 반복했다. 이번 변경은 rule 호출당 정책 term을 한 번만 준비하고, field value를 한 번만 normalize해 내부 helper에서 재사용한다. Python 3.14.7 / pandas 3.0.3의 focused no-issue synthetic benchmark에서 1,000 / 5,000 / 10,000행 중앙값은 각각 38.920ms → 20.544ms, 190.558ms → 124.593ms, 371.574ms → 252.273ms로 감소했다. 결과 의미를 바꾸지 않았으므로 `INSPECTION_VERSION = "13"`을 유지한다.

## 2. 문제 정의

현재 정책에는 금지어 7개와 계좌 문맥어 5개가 있다. 기존 흐름은 non-empty field마다 `find_prohibited_terms()`에서 field 1회와 금지어 7회를 normalize하고, `has_bank_account_context()`에서 다시 field 1회와 문맥어 5회를 normalize했다. product name, description, seller가 모두 있는 100개 no-issue 상품은 실제 4,200회 호출했다.

## 3. 기존 스캔 흐름

상품 입력 순서와 `CONTENT_SCAN_FIELDS` 순서(`product_name`, `description`, `seller`)를 따른다. 한 field 안에서는 prohibited term, email address, phone number, resident registration number, suspected bank account 순서로 issue를 추가한다. 이메일·전화·주민번호·계좌 검색은 원문에만 수행한다.

## 4. 반복 normalization 비용

정책 term은 한 `check_prohibited_and_personal_information()` 호출 동안 변하지 않지만 field마다 다시 정규화됐다. field text도 금지어 검사와 계좌 문맥 검사에서 두 번 정규화됐다. 이 작업은 정규식 패턴, span, masking을 건드리지 않고 이 문자열 전처리 반복만 줄인다.

## 5. 결과 contract

- 상품·field·issue type·금지어 tuple의 기존 순서
- whitespace collapse와 `casefold()`의 기존 normalization 의미
- 금지어 substring 기준 및 같은 금지어의 field 내 1회 issue
- 이메일 case-insensitive dedup과 masking, phone numeric dedup, RRN exact dedup
- 원문의 모든 phone/RRN span을 사용한 bank-account overlap 방지
- issue payload, severity, message, product/group ID

## 6. 최적화 설계

`_build_normalized_terms()`가 원본 term과 normalized term을 policy 순서대로 보관한다. rule 시작 시 prohibited term과 bank context term 목록을 한 번 만들고, non-empty field마다 `normalized_value`를 한 번 만든다. `_find_prohibited_terms_from_normalized_text()`와 `_has_bank_account_context_from_normalized_text()`가 그 값을 재사용한다. public `find_prohibited_terms()`, `has_bank_account_context()`, `find_suspected_bank_account_matches()`는 기존 signature와 standalone 의미를 유지하는 wrapper다.

## 7. 의미가 같은 이유

precompute한 것은 검색용 normalized 문자열뿐이며 message에는 원본 policy term과 원문 regex match만 사용한다. regex, masking, dedup key, raw span collection, overlap 판단의 입력은 모두 기존처럼 원문이다. set 순회나 sort, regex shortcut, policy 변경을 추가하지 않았다.

## 8. 환경

- OS: Windows 11 `10.0.26200-SP0`
- Python: 3.14.7
- pandas: 3.0.3
- warmup: 1회, measured: 2회, `perf_counter_ns()` median
- data: 미리 만들어 둔 no-issue synthetic `Product`; 세 scan field 모두 non-empty

## 9. Before

| rows | focused content-safety median |
|---:|---:|
| 1,000 | 38.920ms |
| 5,000 | 190.558ms |
| 10,000 | 371.574ms |

Before는 production optimization 전, 같은 branch와 같은 focused benchmark에서 측정했다.

## 10. After

| rows | focused content-safety median |
|---:|---:|
| 1,000 | 20.544ms |
| 5,000 | 124.593ms |
| 10,000 | 252.273ms |

## 11. 비교

| rows | Before | After | delta | reduction |
|---:|---:|---:|---:|---:|
| 1,000 | 38.920ms | 20.544ms | 18.376ms | 47.2% |
| 5,000 | 190.558ms | 124.593ms | 65.965ms | 34.6% |
| 10,000 | 371.574ms | 252.273ms | 119.301ms | 32.1% |

두 번 측정한 local median은 host load에 따라 달라질 수 있으며 production latency 보장이 아니다.

## 12. Normalization call 구조

100개 상품의 세 field가 모두 non-empty일 때 실제 count는 `4,200 → 312`다. Before는 `100 * 3 * (1 field + 7 prohibited terms + 1 field + 5 context terms)`이고, After는 `100 * 3 + 7 + 5`다. regression test는 정확한 implementation count 대신 `products * fields + policy terms + small constant` 상한을 확인한다.

## 13. Focused regression

`tests/test_rules.py tests/test_privacy.py`는 `187 passed`였다. mixed multi-product payload/order, 금지어 순서·whitespace, 이메일/phone/RRN dedup, bank context 및 raw phone/RRN overlap contract를 확인한다.

## 14. Full pytest status

Local full pytest는 실행 환경의 30초 command limit 때문에 완료되지 않았다. 실패로 종료된 것은 아니며, 완료 전 progress만 확인됐다.

## 15. Performance test scope

focused benchmark는 `check_prohibited_and_personal_information(products)`만 측정하며 product 생성은 timing 밖에서 수행한다. opt-in `performance` marker이므로 GitHub 기본 CI에서는 실행되지 않는다. Local full opt-in performance pytest도 같은 30초 command limit 때문에 완료되지 않았으며, focused benchmark PASS를 전체 opt-in benchmark PASS로 표현하지 않는다.

## 16. 한계

금지어 substring scan, email/phone/RRN/bank regex, account candidate scan은 그대로다. issue-heavy 입력의 allocation 비용과 실제 운영 텍스트 분포, 전체 inspection latency는 이 focused no-issue benchmark로 보장하지 않는다.

## 17. 다음 후보

후속 후보는 실제 issue-heavy content-safety input의 regex/match allocation을 별도 baseline으로 관찰하는 일이다. 이번 변경에서는 시작하지 않았다.
