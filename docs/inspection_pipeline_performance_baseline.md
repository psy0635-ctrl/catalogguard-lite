# Inspection Pipeline Performance Baseline

## 1. 결론

이 문서는 SQL 조회 성능이 아니라 CSV 한 파일을 검수하는 application pipeline의 **Before baseline**이다. production code, 규칙, API, DB schema와 dependency는 바꾸지 않았다.

normal_unique 10,000행에서 validation 중앙값은 85.359ms, `inspect_dataframe()` 중앙값은 1,778.213ms, validation과 inspection을 연속 호출한 end-to-end(no DB) 중앙값은 2,025.284ms였다. 정상 데이터에서는 rule 실행이 inspection의 가장 큰 측정 단계였다. 반면 duplicate-concentrated 1,000행에서 rule 전체 중앙값은 1,238.939ms로, 정상 10,000행의 rule 전체 1,256.330ms에 가까웠다. 이 worst-case 관찰은 중복 bucket의 pair comparison을 다음 최적화 후보로 검토할 근거다.

이 수치는 이 문서의 환경·합성 데이터·warm run에서만 관찰한 값이며, 개선 결과나 운영 성능 보장이 아니다.

## 2. 측정 목적과 현재 pipeline

Sync route는 `UploadFile.read()` 뒤 `validate_and_read_uploaded_csv()` → SHA-256 → 별도 session의 dedup precheck → `inspect_dataframe()` → `save_inspection_report()` → response build 순서다. Async worker도 job file bytes를 읽은 뒤 validation, SHA-256, precheck, `inspect_dataframe()`, `save_inspection_report()`을 같은 핵심 경로로 재사용한다. 이 baseline은 네트워크, multipart parsing, authentication, DB precheck/write, response serialization, Redis/Celery 대기 시간을 섞지 않고 CSV validation과 `inspect_dataframe()`을 측정한다.

`validate_and_read_uploaded_csv()`는 decode 뒤 header reader, row-length reader, `pandas.read_csv()`를 차례로 사용한다. `read_csv_dataframe()`은 deep copy를 한 번 만든다. `inspect_dataframe()`에서는 `create_masked_preview()`와 `load_products_from_dataframe()`가 각각 deep copy를 한 번 더 만든다. 따라서 정상 production pipeline에서 확인한 전체 DataFrame deep copy는 세 번이다. 이 관찰은 변경 제안이 아니며 이번 PR에서는 copy를 제거하지 않는다.

## 3. 환경과 방법

- OS: Windows 11 `10.0.26200-SP0`
- Python: `3.14.7` (`py -3.11`은 이 host에서 발견되지 않음)
- Pandas: `3.0.3`
- Processor string: `Intel64 Family 6 Model 85 Stepping 7, GenuineIntel`; core count는 이번 측정에서 확인하지 않았다.
- PostgreSQL persistence benchmark: 미실행. `TEST_DATABASE_URL`가 없고, 안전한 isolated ORM schema helper를 이 baseline 범위에서 새로 만들지 않았다.
- Warmup: 1회, measured: 2회, `perf_counter_ns()` 중앙값(min/median/max)을 사용했다.
- 메모리: timing run과 별도로 `tracemalloc` peak를 측정했다.

`tracemalloc`은 Python allocator가 추적한 heap peak다. Pandas/NumPy의 native allocation과 OS process RSS 전체를 나타내지 않으므로 실제 총 메모리 사용량으로 해석하면 안 된다. Windows background process와 JIT/native cache 상태 때문에 수치는 실행마다 달라질 수 있다.

## 4. Dataset

모든 CSV는 코드가 만드는 deterministic synthetic data이며 실제 사용자·운영 CSV와 개인정보를 사용하지 않는다.

| Dataset | 행 수 | 구조 | bytes |
|---|---:|---|---:|
| normal_unique | 1,000 / 5,000 / 10,000 | 고유 group/product/name, 정상 값, PII·금지어 없음 | 138,114 / 690,114 / 1,380,114 |
| issue_heavy | 1,000 / 5,000 / 10,000 | normal_unique와 같고 `price=0`, 행당 안정적인 가격 오류 1건 | 134,114 / 670,114 / 1,340,114 |
| duplicate_concentrated | 250 / 500 / 1,000 | 같은 group/name/color/size bucket, product ID와 price만 다름 | 37,614 / 75,114 / 150,114 |

10,000행 두 pipeline dataset은 `MAX_CSV_ROWS=10,000`과 `MAX_UPLOAD_SIZE_BYTES=5,242,880` 이하를 benchmark assertion으로 확인했다. Rule 수는 실제 `RULES` 목록의 16개다.

## 5. Pipeline 시간 결과

| Dataset | rows | issues | validation median | inspection median | end-to-end no DB median |
|---|---:|---:|---:|---:|---:|
| normal_unique | 1,000 | 0 | 14.127ms | 152.178ms | 218.046ms |
| normal_unique | 5,000 | 0 | 34.314ms | 924.472ms | 1,114.897ms |
| normal_unique | 10,000 | 0 | 85.359ms | 1,778.213ms | 2,025.284ms |
| issue_heavy | 1,000 | 1,000 | 12.936ms | 180.285ms | 196.388ms |
| issue_heavy | 5,000 | 5,000 | 40.787ms | 993.568ms | 1,100.660ms |
| issue_heavy | 10,000 | 10,000 | 87.317ms | 2,051.801ms | 2,069.186ms |

각 median은 2회의 measured run에서 나온 값이다. stage별 독립 측정은 production `inspect_dataframe()` 호출을 분해해 관찰한 것이므로, 아래 단계 중앙값을 합쳐 inspection 중앙값과 같다고 가정하지 않는다.

## 6. inspect_dataframe 단계별 결과

| Dataset | masked preview | product loading | rules total | presentation | summary |
|---|---:|---:|---:|---:|---:|
| normal_unique 10,000 | 257.040ms | 275.853ms | 1,256.330ms | 0.366ms | 0.003ms |
| issue_heavy 10,000 | 244.169ms | 315.840ms | 1,233.357ms | 86.564ms | 미측정(비교상 무시 가능한 수준) |

issue_heavy에서는 10,000개의 `ValidationIssue`를 result DataFrame으로 만드는 시간이 86.564ms로 나타났다. normal_unique의 issue가 0개일 때 presentation이 0.366ms인 것과 대비되므로, issue volume은 presentation과 이후 persistence write 비용을 해석할 때 함께 봐야 한다.

## 7. Rule별 성능

normal_unique 10,000행에서 rule별 중앙값 상위는 다음과 같다.

| Rule | median | issues |
|---|---:|---:|
| `check_product_category_mismatch` | 641.440ms | 0 |
| `check_prohibited_and_personal_information` | 428.604ms | 0 |
| `check_duplicate_variant_combination` | 49.800ms | 0 |
| `check_inconsistent_group_category` | 46.916ms | 0 |
| `check_inconsistent_group_size_system` | 19.949ms | 0 |
| `check_duplicate_product_name` | 15.283ms | 0 |

나머지 10개 rule은 모두 15ms 미만이었다. 이 표는 normal_unique에서 issue 0건인 경우의 실행 비용이며, 결과 생성이 많은 concentrated dataset의 rule 비용을 대표하지 않는다.

## 8. Duplicate concentrated 결과

| rows | issues | rules total median | duplicate name median | duplicate variant median |
|---:|---:|---:|---:|---:|
| 250 | 500 | 152.648ms | 67.272ms | 10.572ms |
| 500 | 1,000 | 321.178ms | 236.185ms | 55.942ms |
| 1,000 | 2,000 | 1,238.939ms | 1,044.298ms | 207.595ms |

250 → 500 → 1,000행에서 증가폭은 선형으로 보이지 않는다. 특히 `check_duplicate_product_name`은 같은 normalized name bucket의 product pair를 비교하므로, 이 합성 concentrated shape에서 크게 증가했다. 10,000행 한 bucket은 과도한 pair 수와 issue/message allocation을 만들 수 있어 실행하지 않았다. 이 표만으로 운영 데이터의 실제 bucket 분포나 10,000행 worst-case 시간을 추정하지 않는다.

## 9. Memory 관찰

| Dataset | rows | peak tracemalloc |
|---|---:|---:|
| normal_unique | 10,000 | 12.004 MiB |
| issue_heavy | 10,000 | 14.729 MiB |

issue-heavy가 더 높은 것은 result issue와 presentation object가 추가되기 때문이다. 그러나 native memory/RSS가 포함되지 않으며, DataFrame deep copy 세 번이라는 코드 관찰과 함께 해석해야 한다.

## 10. Persistence

`save_inspection_report()` persistence benchmark는 수행하지 않았다. 안전한 `TEST_DATABASE_URL`가 없고, 기존 SQL query benchmark의 Core connection + temporary schema 방식을 ORM session write 경로에 억지로 결합하면 baseline보다 DB helper 설계가 커진다. 따라서 `products`, `issues`, `db_write_ms` 비교는 후속 후보로 남긴다. 이 문서의 `end-to-end no DB`에는 DB write와 dedup precheck가 포함되지 않는다.

## 11. 확인된 병목 후보와 아닌 항목

확인된 후보는 두 종류다.

- representative normal_unique 10,000행에서는 rules total이 독립 stage 중 가장 크고, category mismatch와 prohibited/PII scan이 대부분을 차지했다.
- concentrated worst-case에서는 duplicate name pair comparison이 1,000행에서 rule 전체의 대부분을 차지했고 증가 형태가 비선형이었다.

아직 병목이라고 단정할 수 없는 항목은 DB persistence, API multipart/auth/serialization, async queue latency, process RSS, 운영 데이터의 duplicate bucket 분포다. validation의 header/row-length/read_csv 반복 파싱과 세 deep copy도 코드상 후보지만, 이 실험만으로 가장 가치 높은 개선이라고 확정하지 않는다.

## 12. 다음 최적화 추천 1개

**추천: duplicate-concentrated bucket의 `check_duplicate_product_name` pair comparison을 별도 설계 검토한다.**

근거는 같은 1,000행 concentrated dataset에서 해당 rule 중앙값이 1,044.298ms이고 rules total 1,238.939ms의 대부분을 차지했다는 점이다. 다만 normal_unique 10,000행에서는 15.283ms뿐이므로, 다음 PR은 실제 grouping·정상 옵션 예외·issue ordering contract를 보존하는지 먼저 검증한 뒤 알고리즘을 변경해야 한다. 이번 PR은 그 최적화를 구현하지 않는다.

후속 작업은 이 Before baseline의 Python 3.14.7 수치를 변경하지 않고, 별도 Python 3.11.9 환경에서 contract와 비교 횟수 감소를 재검증했다. 결과와 재현 조건은 [Duplicate Product Name Performance Optimization](duplicate_product_name_performance_optimization.md)에 기록한다. 같은 historical baseline을 유지한 category mismatch keyword 전처리 최적화의 별도 측정은 [Category Mismatch Keyword Scan Performance Optimization](category_mismatch_performance_optimization.md)에 기록한다. content-safety normalization 전처리 최적화의 별도 측정은 [Content Safety Scan Preprocessing Performance Optimization](content_safety_performance_optimization.md)에 기록한다.

## 13. 재현과 한계

```powershell
$env:RUN_INSPECTION_PERFORMANCE="1"
python -m pytest -m performance tests/performance/test_inspection_pipeline_performance.py -s -q
```

`performance` marker는 기본 pytest에서 제외된다. PR CI 5/5 regression이 성공하더라도 이 opt-in benchmark가 CI에서 실행됐다는 뜻은 아니다. 기존 [SQL 성능 분석](sql_performance_analysis.md)은 PostgreSQL query plan·index를, 이 문서는 CPU/heap 중심의 CSV inspection pipeline을 다룬다.
