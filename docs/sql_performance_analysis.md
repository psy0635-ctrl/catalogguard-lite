# CatalogGuard Lite SQL 쿼리·인덱스 성능 분석

## 1. 결론

- 병목으로 판단할 쿼리는 발견되지 않았다.
- 새 인덱스와 쿼리 변경은 적용하지 않았다.
- 동일 CSV 조회는 기존 partial unique 복합 인덱스, 목록 조회는 기존 `created_at` 인덱스, 상세 조회는 PK와 기존 FK 조회 인덱스를 실제 planner가 사용했다.
- 상세 API는 결과 수와 무관하게 SELECT 2회로 끝나며 N+1이 발생하지 않는다.
- 목록 정렬용 복합 인덱스 후보는 정렬 노드를 없앴지만 10,000건에서 중앙값 차이가 0.022ms에 불과했다. 상세 결과용 복합 인덱스 후보는 planner가 선택하지 않았고 더 느리며 더 컸다.
- 이후 추가 측정에서 깊은 OFFSET의 비용 증가를 실험 환경에서 확인했다. 현재 10,000건 규모에서는 절대 시간이 작아 production 변경을 보류했고, 대신 이 비용 특성을 opt-in 회귀 테스트로 고정했다(11절).

## 2. 분석 대상과 호출 위치

| 기능 | 호출 위치 | WHERE | JOIN | ORDER BY | LIMIT/OFFSET |
|---|---|---|---|---|---|
| 동일 CSV 조회 | `POST /api/v1/inspections` → `find_existing_inspection_run()` → `get_inspection_run_by_file_identity()` | `file_sha256 = ? AND inspection_version = ?` | 없음 | 없음 | `LIMIT 1` |
| 이력 목록 | `GET /api/v1/inspections` → `list_inspections()` → `list_inspection_runs()` | 선택적 filename/date/status | 없음 | `created_at DESC, id DESC` | 사용 |
| 이력 전체 건수 | 목록 API의 `count_inspection_runs()` | 목록과 같은 선택적 필터 | 없음 | 없음 | 없음 |
| 상세 실행 | `GET /api/v1/inspections/{id}` → `get_inspection_run_by_id()` | PK `id = ?` | 없음 | 없음 | 없음 |
| 상세 결과 | 같은 상세 API → `get_inspection_results_by_run_id()` | `inspection_run_id = ?` | 없음 | `id ASC` | 없음 |

목록 API는 목록과 전체 건수를 각각 조회하므로 SELECT 2회다. 상세 API도 실행 요약과 상세 결과를 각각 조회하므로 SELECT 2회다. 목록에서 관계 객체를 순회하지 않고 상세 결과도 한 번에 조회하므로 N+1 구조가 아니다.

## 3. 테이블과 기존 인덱스

| 테이블 | 주요 컬럼 | PK | FK | 기존 인덱스 |
|---|---|---|---|---|
| `inspection_runs` | `id`, `source_filename`, `file_sha256`, `inspection_version`, 집계 컬럼, `created_at` | `id` | 없음 | PK, `created_at`, partial unique `(file_sha256, inspection_version)` |
| `inspection_results` | `id`, `inspection_run_id`, 상품 식별자, 상태·오류·권장사항, `created_at` | `id` | `inspection_run_id → inspection_runs.id ON DELETE CASCADE` | PK, `inspection_run_id`, `product_id`, `status` |

PostgreSQL `pg_indexes`에서 model과 migration에 선언된 인덱스가 실제로 생성된 것을 확인했다. 외래 키는 인덱스를 자동 생성하지 않지만 `inspection_results.inspection_run_id`에는 이미 명시적 인덱스가 있다.

현재 Repository에서는 `inspection_results.product_id`와 `inspection_results.status` 인덱스를 사용하는 조회가 없다. 이번 작업은 기존 migration 수정·삭제를 금지하므로 제거하지 않았으며, 실제 운영 쿼리 통계를 확보한 뒤 별도 변경으로 검토해야 한다.

## 4. 측정 환경과 데이터

- PostgreSQL 18, Windows 로컬 개발 PC
- 기존 개발 DB 자격정보를 사용하지 않고 포트 `55432`의 격리 클러스터와 전용 `catalogguard_perf` DB 사용
- Alembic `upgrade head` 적용
- `inspection_runs` 10,000건
- `inspection_results` 100,000건(실행당 10건)
- hash는 대부분 고유하고 version 4 중심, 일부 version 3
- `created_at`은 약 30일 범위에 분산
- filename, 오류/경고/정상 집계값은 여러 패턴으로 분산
- 각 쿼리 워밍업 2회 후 7회 측정, 중앙값 기록
- seed 후 각 테이블에 `ANALYZE` 실행
- `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)` 사용
- `enable_seqscan` 등 planner 설정은 변경하지 않음

측정 데이터는 합성 데이터이며 운영 데이터나 개인정보를 사용하지 않았다.

## 5. 현재 실행 계획

| 쿼리 | Plan | 실행 중앙값 | Planning 중앙값 | Shared hit/read | 반환 행 | Filter 제거 행 | Sort |
|---|---|---:|---:|---:|---:|---:|---|
| 동일 CSV | `Limit → Index Scan` | 0.018ms | 0.058ms | 4 / 0 | 1 | 0 | 없음 |
| 이력 목록 20건 | `Limit → Incremental Sort → Index Scan` | 0.044ms | 0.048ms | 3 / 0 | 20 | 0 | incremental |
| 이력 전체 건수 | `Aggregate → Seq Scan` | 0.872ms | 0.057ms | 182 / 0 | 1 | 0 | 없음 |
| 상세 실행 | `Index Scan` | 0.016ms | 0.039ms | 3 / 0 | 1 | 0 | 없음 |
| 상세 결과 10건 | `Sort → Bitmap Heap Scan → Bitmap Index Scan` | 0.029ms | 0.048ms | 12 / 0 | 10 | 0 | 10행 정렬 |

전체 건수 조회의 Seq Scan은 조건 없는 정확한 `count(*)`가 10,000행을 읽는 정상 계획이다. 목록 API 전체 응답에서도 이 쿼리의 중앙값은 1ms 미만이었다. 추정치나 캐시 카운터로 API 계약을 바꾸는 것은 이번 MVP 범위에서 이득보다 복잡도가 크다.

## 6. 인덱스 후보 실험과 판단

후보 인덱스는 같은 DB의 트랜잭션 안에서 기존 단일 인덱스를 교체해 측정하고 모두 롤백했다. 실제 migration에는 반영하지 않았다.

| 쿼리 | 현재 | 실험 후보 | 현재 중앙값 | 후보 중앙값 | 계획 변화 | 판단 |
|---|---|---|---:|---:|---|---|
| 동일 CSV | unique `(file_sha256, inspection_version)` | 추가 없음 | 0.018ms | 해당 없음 | 기존 Index Scan | 기존 인덱스 유지 |
| 이력 목록 | `(created_at)` | `(created_at DESC, id DESC)` | 0.044ms | 0.022ms | Incremental Sort 제거 | 절대 0.022ms 차이로 추가하지 않음 |
| 상세 결과 | `(inspection_run_id)` | `(inspection_run_id, id)` | 0.029ms | 0.044ms | 후보도 Bitmap Scan + Sort | 후보 기각 |

목록 후보는 50%의 상대 차이지만 측정 단위가 수십 마이크로초이고 현재 계획도 첫 20행을 인덱스로 즉시 찾는다. 비슷한 비율을 운영 개선율로 표현하면 과장될 수 있어 절대값을 기준으로 판단했다.

상세 후보는 다음 이유로 추가하지 않았다.

- 실행당 결과가 10건인 분포에서 10행 정렬 비용이 매우 작다.
- planner가 복합 인덱스를 순서 조회에 사용하지 않고 Bitmap Scan과 Sort를 계속 선택했다.
- 기존 단일 인덱스 크기 1,146,880 bytes에 비해 후보는 3,178,496 bytes였다.
- INSERT마다 더 큰 인덱스를 갱신해야 하지만 조회 이득은 확인되지 않았다.

목록 인덱스는 245,760 bytes, 후보 복합 인덱스는 335,872 bytes였다. 공간 증가는 작지만 현재 병목이 아니므로 쓰기 비용과 migration 운영 부담을 추가하지 않았다.

## 7. 발견한 문제와 적용한 개선

| 문제 | 원인 | 영향 | 개선 필요 여부 |
|---|---|---|---|
| 목록의 Incremental Sort | 정렬 tie-breaker인 `id`가 기존 인덱스에 없음 | 중앙값 약 0.022ms 추가 | 현재 불필요 |
| 상세 결과의 10행 Sort | 기존 인덱스가 `inspection_run_id`만 포함 | 중앙값 0.029ms 전체 | 현재 불필요 |
| 전체 건수 Seq Scan | 정확한 조건 없는 `count(*)` | 10,000건에서 0.872ms | 현재 불필요 |
| 큰 OFFSET | OFFSET 이전 행을 실제로 읽고 버려야 함 | 10,000건 기준 OFFSET 5,000에서 buffer 약 28배 증가(11절) | 현재 규모에서는 불필요, 회귀 테스트로 고정 |
| filename `%...%` 검색 | 선행 wildcard ILIKE는 일반 btree 사용 곤란 | 데이터 증가 시 Seq Scan 가능 | 운영 검색 빈도 확인 후 trigram 검토 |

쿼리나 migration을 바꾸지 않은 대신 다음 회귀 방지 장치를 추가했다.

- opt-in `performance` pytest marker
- 실제 migration 테이블을 격리 schema로 복제하는 10,000/100,000행 성능 테스트
- 핵심 쿼리의 `EXPLAIN ANALYZE BUFFERS` 계획 검증과 JSON 측정 출력
- 상세 조회가 결과 수와 무관하게 SELECT 2회인지 확인하는 SQL 횟수 테스트
- 깊은 OFFSET의 buffer 증가를 고정하는 회귀 테스트(11절)

## 8. 재현 명령

성능 테스트에는 이름에 `test` 또는 `perf`가 포함된 전용 PostgreSQL DB만 사용할 수 있다. 테스트는 UUID 기반 schema를 만들고 종료 전에 삭제하며 public 업무 데이터에는 행을 쓰지 않는다.

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://USER:PASSWORD@localhost:5432/catalogguard_perf"
$env:RUN_SQL_PERFORMANCE="1"

python -m alembic upgrade head
python -m pytest -m performance tests/performance/test_inspection_query_performance.py -s -q
```

현재 인덱스 확인:

```sql
SELECT schemaname, tablename, indexname, indexdef
FROM pg_indexes
WHERE schemaname = 'public'
ORDER BY tablename, indexname;
```

기본 전체 pytest에서는 `performance`와 `e2e` marker가 제외된다.

## 9. 한계

- 합성 데이터 분포는 운영 분포와 다를 수 있다.
- 모든 read가 shared buffer hit인 warm-cache 측정이며 디스크 cold-cache 성능을 대표하지 않는다.
- 동시 사용자, connection pool 경쟁, 네트워크 왕복, 운영 PostgreSQL 통계는 측정하지 않았다.
- 큰 OFFSET은 11절에서 측정했지만 filename 부분 문자열 검색은 여전히 대규모 운영 데이터에서 별도 측정이 필요하다.
- 11절의 배수는 이 합성 데이터와 이 실험 환경에서 관찰한 값이며, 운영 하드웨어와 데이터 분포에서는 달라진다.
- 운영 DB에는 `EXPLAIN ANALYZE`를 실행하지 않았고 운영 데이터를 복사하지 않았다.

## 10. 다음 권장 작업

다음 한 단계로는 데이터 수집·ETL MVP를 권장한다. 실제 유입 파일 크기, 실행당 결과 수, filename/status/date 필터 사용 빈도, 페이지 깊이를 개인정보 없이 집계하면 다음 인덱스 판단을 합성 데이터가 아니라 운영 분포에 근거해 다시 내릴 수 있다.

## 11. 깊은 OFFSET 비용 측정과 회귀 테스트

9절이 남긴 "큰 OFFSET" 항목을 별도로 측정했다. 측정 조건은 4절과 같고, 목록 조회만 보므로 `inspection_results`는 만들지 않았다.

`inspection_runs` 10,000건, `ORDER BY created_at DESC, id DESC LIMIT 20` 기준이다.

| OFFSET | Plan | 사용 인덱스 | 실행 중앙값 | Shared hit | 첫 페이지 대비 buffer |
|---:|---|---|---:|---:|---:|
| 0 | `Limit → Incremental Sort → Index Scan` | `created_at` | 0.025ms | 4 | 1배 |
| 1,000 | 동일 | `created_at` | 0.331ms | 26 | 6.5배 |
| 5,000 | 동일 | `created_at` | 1.522ms | 114 | 28.5배 |

세 구간의 실행 계획은 같다. 느려지는 원인은 planner의 계획 선택이나 인덱스 부족이 아니라, `Limit` 노드가 버릴 행을 인덱스로 실제로 읽어야 하는 OFFSET pagination 자체의 구조다. buffer 수가 OFFSET에 거의 비례해 증가하는 것이 그 직접 근거다.

별도 실험에서 같은 페이지 위치를 `WHERE (created_at, id) < (?, ?)` 형태의 keyset 조건으로 조회하면 기존 `created_at` 인덱스만으로 첫 페이지 수준의 buffer만 읽었다. 즉 cursor/keyset pagination이 구조적 해결책이고 새 인덱스는 필요하지 않다.

그럼에도 production 변경은 보류했다.

- 현재 10,000건 규모에서 OFFSET 5,000은 페이지 251에 해당하고 절대 시간은 1.5ms 수준이다. 사람이 도달하는 페이지 깊이가 아니다.
- cursor pagination은 API contract, Streamlit pagination UI, 전체 건수 표시 방식까지 함께 바꿔야 하고 "N페이지로 점프" 기능을 잃는다.
- 실제 운영에서 깊은 페이지 요청이 존재하는지에 대한 근거가 아직 없다.

대신 이 비용 특성을 `test_inspection_history_deep_offset_cost_growth`로 고정했다. 실행 시간은 CPU, 캐시 상태, PostgreSQL 버전에 흔들리므로 보고용으로만 출력하고, 계약은 buffer 사용량으로 검증한다.

- 세 OFFSET 모두 요청한 20행을 정상 반환한다.
- buffer 사용량이 OFFSET 순서대로 단조 증가한다.
- 가장 깊은 페이지가 첫 페이지의 10배를 넘는 buffer를 읽는다. 실측은 28.5배이며, 환경 차이로 깨지지 않도록 하한을 낮게 잡았다.

특정 plan node를 계약으로 고정하지는 않았다. `Seq Scan`과 `Index Scan` 중 무엇을 고르는지는 PostgreSQL 버전, 통계, 데이터 분포에 따라 정상적으로 달라질 수 있고, 이 테스트가 지키려는 것은 노드 이름이 아니라 페이지 깊이에 따른 처리량 증가이기 때문이다. 같은 이유로 filename 부분 문자열 검색은 측정값만 report에 남기고 계획을 단언하지 않는다.
