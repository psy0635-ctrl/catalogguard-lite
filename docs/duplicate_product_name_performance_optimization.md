# Duplicate Product Name Performance Optimization

## 결론

`find_duplicate_product_names()`에서 이미 duplicate 후보가 된 두 index의 pair 비교를 건너뛰고, 한 normalized name bucket의 모든 index가 후보가 되면 즉시 종료했다. `is_same_group_normal_option()`과 product name/option 정규화는 변경하지 않았으며, issue 개수·순서·message·row number·product ID 순서를 고정한 회귀 테스트를 추가했다.

동일한 Python 3.11.9 / pandas 3.0.3 환경에서 기존 concentrated dataset을 다시 측정한 결과, duplicate-name rule 중앙값은 250/500/1,000행에서 각각 24.401/86.122/351.588ms에서 0.669/2.028/8.009ms로 감소했다. 이 문서는 SQL query 성능과 분리된 application inspection rule 측정이다. 기존 Python 3.14.7 Before baseline은 [Inspection Pipeline Performance Baseline](inspection_pipeline_performance_baseline.md)에 그대로 보존한다.

## 변경 범위와 계약

- 변경 대상은 `core/duplicate_detector.py`의 `find_duplicate_product_names()` 내부 pair loop뿐이다.
- 이미 후보인 두 index pair는 새 candidate를 만들 수 없으므로 비교를 생략한다.
- candidate set이 현재 name bucket 전체를 덮으면 이후 pair는 결과에 영향을 주지 않으므로 종료한다.
- `is_same_group_normal_option()`의 정상 옵션 예외 의미, product name/option normalization, `INSPECTION_VERSION = "13"`, API, DB schema, migration, dependency와 다른 rule은 변경하지 않았다.
- mixed bucket의 전체 `ValidationIssue` payload와 입력 순서, 세 가지 이상 정상 옵션 bucket의 무결과, 100개 concentrated bucket의 비교 횟수 감소를 테스트로 고정했다.

## 측정 방법

기존 opt-in benchmark의 `duplicate_concentrated` 250/500/1,000행 데이터를 그대로 사용했다. 각 callable은 warmup 1회 뒤 2회 측정하고 `perf_counter_ns()`의 min/median/max를 기록한다.

```powershell
$env:RUN_INSPECTION_PERFORMANCE="1"
.\.venv\Scripts\python.exe -m pytest -m performance tests\performance\test_inspection_pipeline_performance.py -s -q
```

- Python: 3.11.9
- pandas: 3.0.3
- Platform: Windows-10-10.0.26200-SP0
- Dataset: same group/name/color/size, product ID와 price만 다른 concentrated bucket

## Before / After

| rows | issue count | Before duplicate-name median | After duplicate-name median | reduction | Before rules total median | After rules total median |
|---:|---:|---:|---:|---:|---:|---:|
| 250 | 500 | 24.401ms | 0.669ms | 97.3% | 57.443ms | 16.398ms |
| 500 | 1,000 | 86.122ms | 2.028ms | 97.6% | 128.744ms | 41.094ms |
| 1,000 | 2,000 | 351.588ms | 8.009ms | 97.7% | 456.913ms | 122.713ms |

After official benchmark는 `1 passed in 47.19s`였고, `duplicate_concentrated` report는 `top_rules`와 별도로 `duplicate_product_name` 전용 timing/result field를 출력한다. 따라서 표의 duplicate-name 값은 위 명령의 JSON으로 재현할 수 있다. normal_unique 10,000행의 duplicate-name 중앙값은 Before 15.399ms, After 16.412ms였다. 이 입력은 duplicate bucket이 없으며, 두 번 측정한 로컬 중앙값은 작은 차이에 영향을 받을 수 있으므로 이 값은 운영 성능 보장이 아니다.

## 결정론적 비교 횟수와 회귀 검증

100개가 모두 duplicate 후보가 되는 concentrated bucket에서 실제 `is_same_group_normal_option()` 호출은 99회였다. 기존 전체 pair scan은 `100 * 99 / 2 = 4,950`회이므로, 결과 계약을 유지하면서 4,851회(98.0%)를 줄였다. 테스트는 구현 세부 수치에 과도하게 묶이지 않도록 `comparison_count < full_pair_count`를 검증한다.

검증 결과는 다음과 같다.

- 새 duplicate-name 계약 테스트: `3 passed`
- 관련 detector/rules 테스트: `280 passed`
- 전체 pytest: `2299 passed, 382 skipped, 10 deselected, 1 warning in 43.67s`
- opt-in performance benchmark: `1 passed in 45.29s`

전체 pytest는 실행 sandbox가 기본 `%TEMP%\\pytest-of-user`를 읽지 못해 프로젝트 안 전용 `--basetemp`를 지정했다. 동일한 `tmp_path` fixture를 쓰는 단일 실패 케이스가 그 경로에서 통과한 뒤 전체 suite를 실행했다. 이는 production code 변경이 아니다.

## 한계와 다음 후보

이 변경은 이미 후보가 된 pair만 생략한다. 정상 옵션 예외가 많은 mixed bucket처럼 모든 index가 후보가 되지 않는 입력에서는 여전히 많은 pair 비교가 필요할 수 있다. 따라서 이 결과만으로 모든 duplicate-name 입력의 선형 시간 복잡도를 주장하지 않는다.

다음 성능 후보는 normal 10,000행 rule profile에서 큰 비중을 보인 category mismatch 또는 prohibited/PII scan을 별도 baseline과 결과 contract로 검토하는 것이다.
