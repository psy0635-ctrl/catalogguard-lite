<!-- 역할: CatalogGuard Lite를 포트폴리오용으로 소개하는 프로젝트 설명 문서입니다. -->

# CatalogGuard Lite 포트폴리오 소개

## 6.1 프로젝트 한 줄 소개

CatalogGuard Lite는 Python·FastAPI 백엔드와 PostgreSQL 저장 계층을 중심으로 상품 CSV의 데이터 품질을 검수하고, 적재된 결과를 운영 카탈로그와 비교하며, 공급사별 ETL 품질 변화와 주요 오류 원인을 관찰한 뒤 검증된 변경만 승인 기반으로 운영 상품에 반영하는 데이터 품질 서비스입니다. 공급사 CSV의 Profile 기반 표준화·적재는 CLI·Streamlit 웹 업로드·configured HTTP feed Airflow manual DAG가 같은 ETL Pipeline·loader를 공유하며, Streamlit은 저장된 batch를 선택해 preview·승인·promotion을 요청하고 FastAPI와 PostgreSQL이 반영·audit·conflict-safe rollback을 처리합니다.

- 배포 URL: https://catalogguard-lite-p6jtwmdhwqcapphpghfzduo.streamlit.app/
- 개발 언어: Python
- 화면 프레임워크: Streamlit
- 데이터 처리: pandas
- 테스트: pytest
- CI: GitHub Actions

## 이력서용 프로젝트 요약

### 프로젝트명

CatalogGuard Lite

### 한 줄 요약

Python·FastAPI와 PostgreSQL을 기반으로 상품 CSV의 형식·중복·가격·카테고리·개인정보 문제를 검수하고, 운영 카탈로그와의 정합성 차이와 공급사별 ETL 품질 변화까지 조회 전용으로 관찰하는 데이터 품질 서비스입니다.

### 기술 스택

Python, FastAPI, PostgreSQL, SQLAlchemy, Alembic, Redis, Celery, Airflow 3.3.0, Streamlit, Docker Compose, Kubernetes(kind), Terraform, GitHub Actions, Pytest

### 이력서용 핵심 문장

1. 상품 CSV의 필수값·형식·중복·가격·카테고리·개인정보 문제를 규칙으로 검출하고, 오류 이유와 수정 권장사항을 제공했으며 단위·API 테스트로 주요 흐름을 확인했습니다.
2. 검수 기준을 FastAPI 공통 서비스로 모으고 PostgreSQL에 실행 요약과 상세 결과를 저장했으며, API·저장 테스트로 응답과 이력 흐름을 검증했습니다.
3. 같은 CSV의 재검수를 줄이기 위해 파일 해시와 규칙 버전으로 기존 결과를 조회하고 partial unique index로 경쟁 요청을 막았으며, 중복 결과 재사용 테스트로 확인했습니다.
4. 긴 작업은 Redis·Celery로 상태를 분리하고 GitHub Actions에서 PostgreSQL·Redis·FastAPI·Worker를 연결한 비동기 E2E를 검증했습니다.
5. 공급사마다 코드를 따로 만들지 않고 JSON 프로필로 서로 다른 컬럼 구조를 표준 스키마에 매핑한 뒤, 표준 CSV와 summary JSON을 PostgreSQL staging에 배치 적재했습니다. 입력·프로필 identity 중복 방지와 transaction rollback을 구현하고 실제 PostgreSQL 18.4 임시 클러스터에서 검증했습니다.
6. PostgreSQL staging 적재 결과를 파일명·프로필명으로 검색하고 배치별 상품을 페이지 단위로 확인하는 FastAPI 조회 API를 구현했습니다. 목록 응답과 상세 응답의 범위를 분리하고 실제 PostgreSQL에서 필터·정렬·배치 격리를 검증했습니다.
7. Streamlit에 ETL 적재 이력 탭을 추가해 파일명·프로필명 AND 검색, 배치·상품 페이지네이션, 상세 SHA-256, nullable 필드와 request ID를 표시하고, AppTest로 stale 상태 초기화와 상세 오류 중복 호출 방지를 검증했습니다.
8. Playwright Chromium 실제 브라우저 E2E를 추가해 합성 공급사 CSV 변환·PostgreSQL 적재·FastAPI·Streamlit 실행부터 ETL 검색·상세·staging 상품·reject 마스킹·raw 원문 미노출까지 한 흐름으로 검증했습니다.
9. 운영 상품 persistence를 ETL staging과 분리하고, 공급사별 복합 identity·succeeded partial unique index·append-only JSONB audit·FK RESTRICT를 PostgreSQL 18에서 migration upgrade·downgrade·재-upgrade와 제약 테스트로 검증했습니다.
10. ETL batch 선택 → promotion preview → 변경 전·후 확인 → 명시적 승인 → preview hash 재검증 → 운영 상품 insert/update를 연결하고, transaction·stale 차단·중복 성공 방지·promotion run·append-only audit을 구현했습니다. Chromium E2E에서는 브라우저 메시지뿐 아니라 PostgreSQL 최종 상태까지 확인했습니다.
11. CLI 전용이던 ETL 실행을 Streamlit 업로드 화면과 FastAPI `POST /api/v1/etl-loads`로 확장하면서 변환·적재 로직(`run_pipeline()`, `load_standard_csv()`)은 새로 만들지 않고 CLI와 그대로 공유하도록 설계했으며, 배포 이미지에서 새 import 경로가 실제로 깨지는 packaging 결함과 신규 UI가 만든 접근성 이름 충돌을 CI runtime smoke·Browser E2E로 직접 잡아 최소 범위로 수정했습니다.
12. succeeded promotion을 되돌리는 rollback을 추가하면서 과거 값으로 단순 덮어쓰지 않고, 되돌리기 직전 현재 운영 상품이 해당 promotion이 만든 결과 그대로인지 재확인해 이후 발생한 정상 변경은 conflict로 보존하도록 구현했습니다. preview hash 재계산, confirmation 검증, 단일 transaction 원자성과 중복 rollback 이중 방어(service·DB unique index)를 PostgreSQL 통합 테스트로 검증했습니다. 되돌리기를 실행하는 데서 끝내지 않고 rollback 실행 이력·상세와 상품별 delete/restore change audit 조회 API를 추가해 Streamlit 상세 화면까지 연결했으며, 실제 Chromium E2E에서 Change Audit 화면 표시와 PostgreSQL audit 관계·최종 Catalog 상태를 함께 검증해 run 단위 결과에서 상품 단위 audit까지 검증 깊이를 넓혔습니다.
13. Streamlit 로그인과 FastAPI JWT Access Token 발급, viewer(조회)·operator(운영 데이터 변경) 2개 역할 분리를 구현했습니다. `get_current_user()`가 토큰의 role을 그대로 신뢰하지 않고 매 요청마다 PostgreSQL `users` 테이블에서 role·is_active를 다시 확인하도록 설계해, 계정을 비활성화하면 이미 발급된 토큰도 즉시 차단되게 했습니다. 검수·ETL·Promotion·Rollback 전체 endpoint에 401(인증 실패)/403(권한 부족) 경계를 적용하고 실제 PostgreSQL 사용자·JWT로 검증했습니다.
14. Authentication 도입 과정에서 인증 dependency가 route와 같은 SQLAlchemy Session을 공유하며 SELECT가 트랜잭션을 암묵적으로 시작(autobegin)시켜 이후 쓰기 트랜잭션과 충돌하는 문제를 실제 Browser E2E로 발견하고, 관련 없는 사전 조회에는 독립된 Session을 쓰도록 최소 범위로 수정했습니다. 같은 원인으로 이미 존재하던 sync inspection API의 PostgreSQL transaction 충돌도 실제 PostgreSQL regression test로 재현·수정하고, 기존 monkeypatch 기반 테스트가 놓친 Session 상호작용 검증 공백을 보완했습니다.
15. RBAC가 "누가 실행할 수 있는지"만 통제하고 "누가 실행했는지"는 남기지 않는다는 한계를 확인한 뒤, 새 범용 Audit 테이블 대신 기존 `ETLLoadRun`·`CatalogPromotionRun`·`CatalogPromotionRollback` 실행 이력에 `actor_user_id`(`users.id` FK, `ON DELETE SET NULL`)·`actor_username`(snapshot) 컬럼을 추가하는 Actor Audit MVP를 구현했습니다. actor는 request body가 아니라 인증된 JWT `current_user`에서만 가져오도록 해 위조를 원천적으로 차단했고, 실제 PostgreSQL로 JWT actor 기록·401/403·actor 위조 방지·Promotion 실패 시 기록·legacy row 호환을 검증하는 regression test 10개를 추가했습니다.
16. 로그와 `/health`·`/ready`만으로는 요청 수·응답 시간·오류율·ETL 처리량을 숫자로 비교할 수 없다는 한계를 확인한 뒤, 기존 요청 middleware가 계산하던 duration을 재사용해 Prometheus HTTP metric(요청 수·응답 시간·상태 계열)과 Web ETL metric(신규/중복/실패, 처리 행 수)을 `GET /metrics`로 노출했습니다. 동적 ID 대신 FastAPI route template을 label로 써서 cardinality 폭증을 막고, 동일 배치 재사용 시 행 수를 다시 집계하지 않도록 설계했으며, `CATALOGGUARD_METRICS_ENABLED` 미설정 시 endpoint와 instrumentation 모두 no-op임을 실제 PostgreSQL 포함 32개 테스트로 검증했습니다.
17. 기존 Dockerfile CMD가 컨테이너 시작마다 Alembic migration과 Uvicorn 실행을 함께 담당해, Kubernetes에서 API Pod가 여러 개면 migration이 중복 실행될 수 있다는 문제를 확인했습니다. 새 Kubernetes 전용 Dockerfile을 만들지 않고 기존 `Dockerfile.aws` image를 재사용하면서, `command` override로 migration 전용 Kubernetes Job과 Uvicorn 전용 Deployment로 책임을 분리했습니다. DB 연결을 확인하지 않는 `/health`는 liveness, PostgreSQL 연결까지 확인하는 `/ready`는 readiness로 연결했고, GitHub Actions에 kind 기반 실제 Kubernetes cluster를 만들어 PostgreSQL rollout·Migration Job 완료·FastAPI rollout·`/health`·`/ready` HTTP 200까지 자동 검증했습니다. kind·kubectl·node image는 최신 버전을 자동 조회하지 않고 SHA-256 digest까지 고정해, 같은 commit이 항상 같은 Kubernetes toolchain으로 재현되도록 했습니다.
18. 콘솔에서 수동으로 구성했던 AWS staging(EC2·RDS·Security Group·SSM 접근)을 Terraform 코드로 옮겨, 같은 구조를 다시 만들 때 필요한 수동 작업과 설정 누락 위험을 줄였습니다. 새 대규모 인프라를 만드는 대신 이미 검증한 구성의 코드화로 범위를 제한했고, EC2 inbound 규칙 0개·RDS `5432`의 Security Group 참조 전용 허용·`publicly_accessible=false` 고정·저장 암호화·SSM 전용 접근 같은 보안 조건을 mock provider 기반 `terraform test` 12개 assertion으로 고정했습니다. 실제 AWS 자격 증명 없이 동작하는 이 검증을 GitHub Actions `terraform-validate` job으로 자동화해, 누군가 `0.0.0.0/0` inbound를 추가하는 보안 회귀가 생기면 CI가 실패하도록 했습니다. 이번 범위는 코드화와 정적·mock 검증까지이며 실제 `terraform apply`는 수행하지 않았습니다.
19. 기존 Actor Audit을 Sync·Async Inspection까지 확장했습니다. `inspection_runs`에 nullable `actor_user_id`(`users.id`, `ON DELETE SET NULL`)와 `actor_username` snapshot을 추가하고, actor는 request form이 아니라 인증된 JWT `current_user`에서만 가져오도록 했습니다. 비동기 경로는 ORM 객체나 JWT 대신 두 scalar만 Redis job state와 Celery Worker로 전달했습니다. 동일 CSV·검수 버전의 기존 run을 재사용할 때는 최초 actor를 보존하며, 사용자 삭제 후 FK만 `NULL`이 되고 username snapshot은 남는 동작을 PostgreSQL 18 migration 왕복·Sync 통합 테스트·Redis/Celery/FastAPI E2E로 검증했습니다.
20. AWS S3의 합성 공급사 CSV를 EC2 Instance Role의 최소권한 IAM으로 읽고, FastAPI의 기존 ETL Pipeline을 통해 RDS PostgreSQL staging에 적재하는 전체 흐름을 실제 AWS staging 환경에서 검증했습니다. S3 연동을 위해 두 번째 ETL pipeline을 만들지 않고 `run_web_etl()` 앞에 붙는 source adapter로 설계해 변환·중복 판단·Actor Audit 로직을 그대로 재사용했으며, EC2 Role에는 `s3:GetObject` 하나만 그것도 정확한 prefix로 제한해 부여하고 컨테이너에 AWS access key를 주입하지 않아 실제 principal이 `assumed-role/CatalogGuardEC2SSMRole/<instance-id>`로 동작하는 것을 확인했습니다. 동일 S3 객체 재처리 시 SHA-256 기반 idempotency와 Actor Audit이 유지되는 것을 실제 staging DB에서 검증했고, anonymous 401·viewer 403·허용 prefix 밖 400 차단과 함께 `s3:ListBucket`을 주지 않은 최소권한 때문에 없는 key가 404가 아니라 안전한 502로 응답한다는 실제 AWS 동작 차이까지 기록했습니다.
21. 같은 상품 그룹에서 `S/M/L` 같은 문자형 사이즈와 `95/100` 같은 숫자형 사이즈가 함께 쓰이는 사이즈 체계 혼재를 탐지하는 검수 규칙을 추가했습니다. 기존 `SIZE_ALIASES`·`find_standard_size()`를 재사용해 표준화 로직을 새로 만들지 않고 문자형(ALPHA)·숫자형(NUMERIC)만 구분했으며, `95`나 `270`을 특정 카테고리로 단정하지 않고 명확히 판별 가능한 체계 혼합만 탐지하도록 범위를 제한했습니다. FREE·사용자 정의 값·빈 값은 체계 판정에서 제외해 정상 데이터의 오탐을 줄이고, 브랜드 정책상 혼용 가능성을 고려해 오류가 아닌 `warning`으로 설계했습니다. 정상 그룹, 혼재 그룹, FREE·custom·빈 값 제외, 빈 `product_group_id`를 하나의 가짜 그룹으로 묶지 않는 경계까지 단위·통합 회귀 테스트로 검증했습니다.
22. 상품명 키워드 사전과 카테고리 별칭 사전은 신발·가방을 이미 알고 있는데 공식 허용 카테고리는 `TOP`·`BOTTOM`·`OUTER` 3개뿐이어서, "남성 러닝 운동화 + SHOES"처럼 의미가 정확히 맞는 상품도 `카테고리 오류`가 나던 정합성 문제를 해결했습니다. 새 카테고리 체계를 만드는 대신 공식 허용 목록만 5개로 확장해 기존 matcher·detector·DB·API·ETL 구조를 그대로 두었고, 확장 전 전체 테스트를 확장 상태로 미리 돌려 영향받는 테스트가 3건뿐임을 확인한 뒤 진행했습니다. `shoes`·`신발` 같은 표기는 비교용 별칭으로만 유지하고 정식 입력값으로는 계속 거부해 입력 데이터의 표기를 하나로 관리하도록 했습니다. 후속 정책에서는 `BAG`의 `size`를 선택 값으로 두어 빈 값과 `FREE`를 모두 허용하되, 두 값을 같은 옵션으로 합치지 않습니다.
23. HTTP 공급사 ETL을 API 재호출에만 의존하면 일시적 네트워크 오류 때 운영자가 재실행을 판단해야 한다는 문제를 확인했습니다. 기존 `read_http_feed_csv()`·`run_web_etl()`·`run_pipeline()`·`load_standard_csv()`는 그대로 두고 Airflow 3.3.0의 manual single-task DAG가 실행·상태·retry만 orchestration하도록 분리했습니다. HTTP timeout/network/DNS·429·5xx와 제한된 transient DB 오류만 retry하고, SHA-256·프로필 identity로 동일 bytes의 두 번째 실행을 `created=false`로 재사용해 staging 중복을 막았습니다. Airflow metadata PostgreSQL과 CatalogGuard application PostgreSQL을 분리하고, URL 원문 대신 안전한 lineage와 NULL actor를 저장했으며, Linux CI에서 image·migration·DAG processor·실제 HTTP staging load·중복 실행을 검증했습니다.
24. ETL staging에 정상 적재된 공급사 상품과 현재 운영 카탈로그를 `profile_name`·상품 식별자 기준으로 비교해 `new`·`changed`·`unchanged`·`not_observed_in_batch`와 필드별 변경 건수를 보여 주는 조회 전용 보고서를 구현했습니다. 핵심 판단은 미관측 상품을 자동 삭제 후보로 다루지 않은 것입니다. 공급사 피드가 전체 snapshot인지 부분 delta인지 시스템이 확정할 수 없고, ETL에서 거부된 행 때문에도 카탈로그 상품이 미관측으로 보일 수 있어 두 경우를 구분할 수 없기 때문입니다. Promotion Preview와 상태 이름을 일부러 다르게(`insert`/`update`가 아니라 `new`/`changed`) 붙여 조회 보고서가 실행 계획처럼 읽히지 않게 했고, 배치 안 중복 상품 식별자는 임의로 한 행을 고르지 않고 `409`로 거부했으며, 카탈로그를 통째로 메모리에 올리지 않고 미관측 건수는 SQL `COUNT`, 목록은 `LIMIT`/`OFFSET`으로 처리했습니다.
25. 누적 품질 요약과 배치별 Reject 비율 추이 위에, 같은 공급사의 최신 배치와 직전 배치를 직접 비교하는 품질 관찰 기능을 추가했습니다. 서로 다른 공급사를 비교하면 품질 변화가 아니라 공급사 차이가 품질로 보이므로 `profile_name`을 부분 검색이 아닌 필수·정확 일치로 두었고, 변화량은 퍼센트 변화율이 아니라 퍼센트 포인트(%p)로 계산했으며, 품질 metadata가 `NULL`인 legacy 배치를 Reject 0건으로 읽지 않고 비교에서 제외했습니다. 같은 관찰 구간의 `error_counts`를 오류 코드별 발생 건수와 발생 배치 수로 집계해, 한 배치에서만 터진 사고인지 여러 배치에 걸친 문제인지 구분할 수 있게 했습니다. `worsened`는 관찰 결과로만 두고 위험 임계값·자동 차단·자동 알림은 만들지 않았습니다.
26. 위 품질 관찰의 공급사 선택 목록을 화면에 떠 있는 최근 적재 페이지에서 만들면, 오래전에만 데이터를 보낸 공급사는 백엔드 비교가 정상 동작하는데도 화면에서 고를 수 없다는 문제를 확인했습니다. 페이지네이션된 목록 API를 더 큰 `limit`으로 재호출하는 대신, 품질 metadata가 온전한 ETL 이력에서 `DISTINCT profile_name`을 DB가 직접 뽑아 정렬해 돌려주는 조회 전용 API로 분리했습니다. 기준을 설정 Registry가 아니라 실제 적재 이력으로 둔 덕분에 Registry에서 내려간 과거 공급사도 계속 관찰할 수 있고, API client가 이름의 공백·중복·정렬 계약까지 검증해 잘못된 응답이 선택 화면까지 흘러가지 않게 했습니다.
27. 프로필 activation이 코드 상수여서 공급사 하나를 내리거나 되돌리는 데도 코드 수정 → 테스트 → 배포가 필요하다는 한계를 확인한 뒤, 프로필 **정의**는 그대로 두고 **runtime activation 상태만** PostgreSQL `etl_profile_activations`로 분리했습니다. 프로세스 메모리에 두면 재시작하면 사라지고 worker마다 상태가 갈라지므로 DB 공용 상태로 저장했고, "row 없음(배포 기본값 사용)"과 "row 있음 + `active_version = NULL`(운영자의 명시적 비활성)"을 서로 다른 상태로 유지해 배포 기본값이 바뀔 때 운영자의 결정이 조용히 덮이거나 되살아나지 않게 했습니다. activation 조회 SELECT가 SQLAlchemy Session을 autobegin시켜 뒤따르는 loader의 `with session.begin()`과 충돌하는 문제는, 무조건 `rollback()`하는 대신 보류 중인 ORM 쓰기(`session.new`·`dirty`·`deleted`)가 있으면 먼저 실패시키고 안전한 read 트랜잭션만 정리하는 전용 함수로 해결했습니다.
28. 위 activation을 운영자가 실제로 다룰 수 있도록 `GET`/`PUT /api/v1/etl-profiles/{profile_id}/activation`과 Streamlit `ETL 프로필 운영 관리` 화면을 연결했습니다. 조회는 viewer, 변경은 operator로 나누고 actor는 요청 body가 아니라 인증된 `current_user`에서만 기록했습니다. 관리 목록은 `include_inactive=true`로 조회해 비활성 프로필을 계속 노출했는데, 감추면 한 번 내린 프로필을 다시 고를 수 없어 되살릴 방법이 사라지기 때문입니다. 실행 selector 상태(`etl_web_run_*`)와 관리 화면 상태(`etl_profile_admin_*`)의 session key를 분리해 관리 화면에서 프로필을 골라도 실행 selector가 함께 바뀌지 않게 했고, `active_version: null`이 배포 기본값 reset이 아니라 명시적 비활성임을 API·화면 문구 양쪽에 남겼습니다.
29. Airflow HTTP feed DAG가 비활성 프로필을 generic `catalogguard_etl_unexpected`로 실패시키던 것을 전용 코드 `etl_profile_inactive`(non-retryable)로 분리했습니다. 운영자가 의도적으로 내린 프로필은 network timeout·HTTP 5xx·일시적 DB 오류와 달리 재시도로 회복되지 않기 때문입니다. Airflow와 로그에는 `CatalogGuard HTTP feed ingestion failed [etl_profile_inactive]`처럼 안전한 코드 하나만 남기고 `profile_id`·feed URL·raw 예외는 노출하지 않았습니다. effective activation pre-check에서 이미 inactive면 `read_http_feed_csv()`를 호출하지 않으며, read transaction을 끝낸 뒤 fetch한다. 다만 그 직후 deactivate되는 race에서는 fetch가 시작될 수 있고 `run_web_etl()`의 최종 guard가 ETL load를 막는다.
30. runtime override를 한 번 만들면 배포 기본값으로 돌아갈 방법이 없다는 한계를, `PUT`에 `null`을 재사용하지 않고 `DELETE /api/v1/etl-profiles/{profile_id}/activation`을 별도 endpoint로 분리해 해결했습니다. `null`은 "운영자가 명시적으로 내렸다"는 상태를 저장하는 것이고 reset은 그 상태 자체를 지우는 것이라, 둘을 합치면 배포 기본값이 바뀔 때 운영자의 결정이 조용히 뒤집히기 때문입니다. reset은 명시적 비활성 override를 지우면서 프로필을 **다시 활성화할 수 있으므로** 단순한 정리 조작으로 보이지 않도록 Streamlit에서 되돌린 뒤 적용될 버전을 미리 표시하고 확인 checkbox를 거치게 했고, override가 이미 없어도 `200`을 주는 idempotent 계약으로 두되 없는 `profile_id`는 `404`로 구분했습니다. `204` 대신 기존 activation 응답을 그대로 돌려줘 호출자가 reset 직후 상태를 다시 조회하지 않게 했습니다.
31. reset이 current-state row를 지우면서 actor와 시각까지 함께 지운다는 한계를, current-state 표는 그대로 두고 성공한 activate·deactivate·reset 명령을 별도 append-only 표(`etl_profile_activation_events`)에 기록해 해결했습니다. 기록 단위를 "상태가 달라진 순간"이 아니라 "서버가 성공으로 처리한 운영 명령"으로 정해 같은 버전을 다시 활성화하거나 override 없는 프로필을 다시 reset해도 event를 남기고, 실패한 요청은 남기지 않았습니다. 상태 변경과 이력 INSERT를 같은 transaction으로 묶어 이력 기록이 실패하면 상태 변경도 rollback되게 했고, current-state row 하나로는 알 수 없는 과거 이력을 추측해 backfill하지 않아 이 기록은 마이그레이션 `20260823_0015` 적용 이후의 명령부터 시작합니다.

### Airflow ETL orchestration: 문제와 해결

**문제.** HTTP 공급사 feed는 일시적 통신 오류가 날 수 있지만, 기존 ETL service를 또 구현하거나
실패할 때마다 운영자가 수동으로 재처리하면 실행 이력과 중복 처리가 불명확해진다.

**해결.** Airflow는 manual trigger와 retry만 담당하고, 단일 task가 기존 ETL service를 호출한다.
`(input_file_sha256, profile_name, profile_version)` identity가 이미 committed된 batch를 재사용하므로
동일 bytes 재실행은 `created=false`가 되며 staging/reject row가 중복되지 않는다.

**핵심 설계.** Airflow metadata DB와 CatalogGuard DB를 분리했고, HTTP URL·token을 XCom/lineage에
남기지 않았다. Airflow는 데이터 pipeline orchestration, Celery는 사용자 검수의 비동기 API job이라는
서로 다른 역할을 유지한다. 실제 Linux CI에서 Airflow runtime·두 DB migration·DAG import·실제
staging load·idempotency·lineage를 함께 검증했다.

## 6.2 문제 정의

상품 CSV는 운영 업무에서 자주 쓰이지만, 사람이 직접 확인하면 다음 문제가 반복됩니다.

- 필수 컬럼이나 필수 값이 빠진 채 등록될 수 있습니다.
- 상품 ID, 상품명, 상품 내용이 중복될 수 있습니다.
- 재고와 가격이 숫자 형식에 맞지 않을 수 있습니다.
- 상품명은 상의인데 카테고리는 하의처럼 입력될 수 있습니다.
- 설명이나 판매자 정보에 전화번호, 이메일, 주민등록번호 형태, 계좌번호 의심 값이 섞일 수 있습니다.
- 검수 결과를 다시 공유할 때 CSV 한글 깨짐이나 수식 삽입 같은 문제가 생길 수 있습니다.
- Streamlit과 서버가 같은 CSV를 각각 검수하면 결과·저장·화면 표시가 어긋날 수 있고, 같은 검수를 두 번 수행하는 비용도 발생합니다.

이 프로젝트는 위 문제를 작은 웹 앱 안에서 업로드, 검수, 미리보기, 필터링, 다운로드까지 한 번에 처리하도록 만든 MVP입니다.

## 6.3 해결 목표

프로젝트의 목표는 단순한 CSV 뷰어가 아니라, 운영자가 바로 사용할 수 있는 검수 흐름을 만드는 것이었습니다.

- 사용자는 CSV만 업로드하면 됩니다.
- 앱은 검수 전에 파일 자체가 안전하고 읽을 수 있는지 확인합니다.
- 화면 미리보기에는 개인정보로 보이는 값을 가려서 보여줍니다.
- 실제 검수는 FastAPI 서버의 공통 서비스가 원본 데이터로 한 번 수행합니다.
- Streamlit은 업로드 검증과 개인정보 마스킹 미리보기를 담당하고, 서버의 상세 응답을 결과 화면에 재사용합니다.
- 서버 응답은 실행 ID, 요약, 상세 결과 필드를 검증한 뒤에만 화면 상태에 반영합니다.
- 검수 결과는 사용자가 이해할 수 있는 한글 메시지와 수정 권장사항으로 보여줍니다.
- 필터 적용 전 전체 결과를 오류 항목별, 위험 수준별, 상품별로 집계해 보여줍니다.
- 필터링한 결과만 CSV로 다운로드할 수 있습니다.

## 6.4 사용자 흐름

```text
앱 접속
-> CSV 입력 템플릿 다운로드
-> 상품 CSV 작성 또는 기존 CSV 준비
-> CSV 업로드
-> 상품 데이터 미리보기 확인
-> 검수 실행 및 이력 저장 버튼 클릭
-> FastAPI POST로 서버 검수·저장
-> FastAPI GET 상세 응답을 화면에 표시
-> 필터 적용 전 전체 검수 결과 통계 확인
-> 검수 결과 필터링
-> 현재 필터 결과 CSV 다운로드
```

업로드 후 앱 내부 흐름은 다음과 같습니다.

```text
업로드 파일 bytes
-> validate_and_read_uploaded_csv()
-> validated_df
-> create_masked_preview(validated_df)
-> 검수 실행 및 이력 저장 버튼
-> CatalogGuardApiClient
-> FastAPI POST /api/v1/inspections
-> 서버의 core.inspection_service와 core.rules
-> PostgreSQL 저장 또는 기존 실행 재사용
-> FastAPI GET /api/v1/inspections/{inspection_run_id}
-> 서버 상세 응답 검증
-> build_history_detail_dataframe()
-> build_inspection_statistics(result_df)
-> render_inspection_statistics(result_df)
-> build_validation_result_csv(filtered_result_df)
```

공급사 파일은 다음 CLI 흐름으로 표준화한 뒤 기존 업로드 검증·검수 서비스에 연결할 수 있습니다.

```text
공급사 CSV + JSON 매핑 프로필
-> etl.profile_loader
-> etl.transformer
-> catalogguard_ready.csv
-> rejected_rows.csv
-> etl_summary.json
-> 기존 validate_and_read_uploaded_csv()·inspect_dataframe()
```

같은 변환·적재 로직을 Streamlit 업로드 화면에서도 실행할 수 있습니다. CLI 전용 실행 구간을 없애기 위한 별도 ETL 엔진이 아니라, 아래 CLI 적재 흐름이 재사용하는 `run_pipeline()`·`load_standard_csv()`를 FastAPI를 통해 그대로 호출하는 웹 실행 경로입니다.

```text
Streamlit ETL 실행 영역
-> GET /api/v1/etl-profiles (서버 allowlist 프로필 목록)
-> 공급사 CSV 업로드 + "ETL 실행 프로필" 선택
-> ETL 실행 버튼 클릭
-> POST /api/v1/etl-loads
-> etl.web_service.run_web_etl() -> run_pipeline() -> load_standard_csv()
-> ETL 적재 이력 캐시 무효화
```

표준 CSV를 DB에 적재하는 흐름은 파일 변환과 분리합니다. CLI(`etl.load_cli`)와 웹 실행 모두 이 적재 계약을 공유합니다.

```text
catalogguard_ready.csv + etl_summary.json
-> etl.load_cli 또는 POST /api/v1/etl-loads
-> summary 필수 필드·output SHA-256·loaded_rows 검증
-> (input SHA-256, profile name, profile version) 중복 조회
-> etl_load_runs + catalog_products_staging 한 트랜잭션 저장
-> GET /api/v1/etl-loads로 배치 검색
-> GET /api/v1/etl-loads/{etl_load_run_id}로 배치별 상품 조회
-> Streamlit ETL 적재 이력 탭에서 목록·상세·페이지네이션 표시
-> 사용자가 batch 직접 선택
-> POST /api/v1/etl-loads/{etl_load_run_id}/promotion-preview
-> insert/update/unchanged·상품별 변경 전후·차단 사유 확인
-> 승인 checkbox와 preview hash 확인
-> POST /api/v1/etl-loads/{etl_load_run_id}/promotions
-> 운영 상품·promotion run·audit 저장
-> 필요 시 POST /api/v1/catalog-promotions/{promotion_run_id}/rollback-preview
-> 현재 상품 상태와 promotion 결과의 conflict 확인
-> confirmation + rollback preview hash 재검증
-> POST /api/v1/catalog-promotions/{promotion_run_id}/rollback
-> INSERT 상품 삭제 / UPDATE 상품 이전 값 복원, rollback run·audit 저장
```

ETL 프로필의 runtime activation은 위 실행 흐름과 분리된 별도 관리 흐름입니다. 프로필 정의를 바꾸는 것이 아니라, 이미 보존된 어떤 버전을 신규 실행에 쓸지만 정합니다.

```text
Streamlit ETL 프로필 운영 관리
-> GET /api/v1/etl-profiles?include_inactive=true (비활성 포함 관리 목록)
-> GET /api/v1/etl-profiles/{profile_id}/activation
-> viewer: 상태·실제 적용 버전·배포 기본 버전·runtime override·보존 버전·마지막 변경자/시각 조회
-> operator: PUT /api/v1/etl-profiles/{profile_id}/activation
-> PostgreSQL etl_profile_activations (프로필당 current-state row 1건)
   + 같은 transaction에서 etl_profile_activation_events에 성공한 명령 1건 INSERT
-> GET /api/v1/etl-profiles/{profile_id}/activation/history (성공한 운영 명령, 최신순)
-> 신규 ETL 실행이 effective activation을 따름
```

비활성화가 막는 것은 신규 ETL 실행뿐입니다. 과거 적재 이력, 품질 요약·추이·관찰, 동기화 차이, promotion·rollback 이력, 버전 archive는 그대로 남습니다.

웹 ETL 실행 성공이 promotion을 자동으로 시작하지는 않습니다. 사용자가 ETL 적재 이력에서 새 batch를 직접 선택해야 이후 preview·승인 흐름이 시작됩니다.

## 6.5 기술 스택과 검증 버전

| 항목 | 버전 또는 값 |
|---|---|
| Python | 3.11.15 |
| Streamlit | 1.58.0 |
| API | FastAPI, Uvicorn, Pydantic |
| pandas | 3.0.3 |
| 데이터베이스 | PostgreSQL, SQLAlchemy, psycopg |
| 마이그레이션 | Alembic |
| 비동기 처리 | Redis, Celery |
| 관측성 | prometheus-client 0.25.0 (HTTP·Web ETL metric instrumentation MVP, Prometheus 서버는 미구축) |
| Kubernetes(CI 검증) | kind v0.32.0, kubectl v1.36.2, node kindest/node:v1.36.1(SHA-256 digest 고정), FastAPI+PostgreSQL만 배포(Redis/Celery/Streamlit 미배포) |
| IaC(CI 검증) | Terraform 1.15.8, AWS Provider 6.55.0(`.terraform.lock.hcl` 고정), mock provider 기반 `terraform test`(apply 미수행, backend 미구성) |
| 로컬 실행 | Docker Compose |
| pytest | 일반 unit·integration 9.1.1 / Chromium E2E 8.4.1 |
| CI | GitHub Actions `Test` workflow |
| CI 테스트 서비스 | PostgreSQL 18·Redis 7.4 서비스 컨테이너 |
| CI 검증 범위 | 일반 `test` job의 Alembic·pytest·비동기 E2E·AWS Docker runtime smoke, `browser-e2e` job의 PostgreSQL·Chromium 실제 브라우저 ETL·promotion E2E, `kubernetes-smoke` job의 kind 실제 Kubernetes 배포·`/health`·`/ready` 검증, `terraform-validate` job의 fmt·init·validate·mock provider test, `airflow-smoke` job의 분리 Airflow image·metadata DB·DAG processor/import·deterministic HTTP staging/idempotency/lineage 검증 |
| 필수 컬럼 | 9개 |
| 선택 컬럼 | 3개 (`sale_price` 포함) |
| 등록된 검수 규칙 함수 | 15개 |
| 샘플 CSV 상품 수 | 5개 |
| 샘플 CSV 검수 결과 | 오류 6건, 주의 0건 |
| ETL API client·UI 검증 | 응답 schema, nullable, request ID, stale 상태와 Streamlit AppTest 범위 |
| promotion preview·service·API·concurrency 검증 | preview hash, 승인, 차단·stale·failed, transaction, 중복 성공 방지와 audit |
| Chromium 브라우저 E2E | ETL reject 마스킹, promotion 승인·반영·이력·audit, rollback 실행·이력·상세·상품 Rollback 변경 Audit, 브라우저 오류 및 PostgreSQL 최종 상태 |
| 로컬 데모 리허설 | Docker Desktop Linux engine과 PostgreSQL·Redis를 기동하고 FastAPI `/health`·`/ready`(database `ok`), Streamlit health, 기존 Chromium 2개 시나리오 성공을 확인. 합성 fixture 기반 로컬 검증이며 운영 환경 검증은 아님 |
| 샘플 ETL CLI 결과 | 전체 3건, 정상 변환 2건, 오류 행 1건, 종료 코드 0 |
| Web ETL·Rollback 검증 | `POST /api/v1/etl-loads`·`GET /api/v1/etl-profiles`, rollback preview/실행 API와 rollback 이력·상세·상품별 change audit 조회 API의 PostgreSQL 통합·API·client·UI 테스트 |
| Actor Audit 검증 | 기존 `tests/test_actor_audit.py` 10 scenarios에 Inspection migration·Sync actor·위조 방지·dedup 최초 actor·사용자 삭제 snapshot·Redis legacy payload·Celery Worker·실제 Async E2E 검증을 추가 |
| Prometheus Metrics 검증 | `tests/test_metrics.py` 32 scenarios: env parsing, `/metrics` disabled=404/no-op, route template cardinality 방지, `unmatched`/`5xx` 집계, 민감정보 미노출, Web ETL created/duplicate/failed와 row 중복 집계 방지, 실제 PostgreSQL 신규+중복 ETL |
| Kubernetes smoke 검증 | kind 실제 cluster에서 PostgreSQL rollout·Alembic Migration Job condition=complete·FastAPI rollout·Service 경유 `GET /health`·`GET /ready` HTTP 200(pytest 범위 밖, `kubernetes-smoke` job) |
| Terraform 검증 | `terraform fmt -check -recursive`·`init -backend=false -lockfile=readonly`·`validate` 성공과 mock provider `terraform test` `2 passed, 0 failed`(run 2개·assertion 12개, pytest 범위 밖, `terraform-validate` job) |
| AWS staging S3 ingestion 실제 E2E 검증 | 실제 private S3 -> EC2 Instance Role(`s3:GetObject` + 정확한 prefix) -> FastAPI `POST /api/v1/etl-loads/s3` -> 기존 ETL pipeline -> RDS PostgreSQL. 합성 fixture 1건 `created=true`/loaded 1/rejected 0, 재요청 `created=false`·동일 run, Actor Audit 일치, 401/403/400/502 경계, EC2 cold start 후 `/health`·`/ready` 200(pytest 범위 밖 수동 검증, CI 자동 재실행 없음) |
| Rollback Change Audit 기능 완료 commit 기준 전체 pytest | `1451 passed`, `0 skipped`, `4 deselected`, `0 failed`, warnings 0(일회성 PostgreSQL·Redis 서비스 컨테이너. Chromium E2E는 `-m "not e2e"`로 제외되어 별도 job에서 실행) |
| Rollback Change Audit 기능 완료 commit 기준 CI | commit `abcea748e299009b4889b0daa98ad4c9c97e770b`을 대상으로 한 GitHub Actions run `31487868946` success (`test`·`browser-e2e`·`kubernetes-smoke`·`terraform-validate` 4개 job) |
| Catalog Reconciliation 검증 | staging↔카탈로그 identity 매칭, 네 가지 상태 분류, `field_change_counts`, 미관측 상품을 삭제로 해석하지 않는 정책, 중복 identity `409`, 카탈로그 전체 미적재(`COUNT` + `LIMIT`/`OFFSET`)를 service·API·Streamlit 테스트로 확인 |
| ETL 품질 관찰 검증 | 같은 `profile_name` 정확 일치 비교, legacy(`NULL`) 배치 제외, `total_rows=0` 처리, `created_at` 동률 시 `id` 정렬, %p delta와 `improved`/`unchanged`/`worsened`/`no_baseline`, 오류 코드 `total_count`·`affected_batch_count` 집계와 결정론적 정렬, 배치 0건·1건 구분을 service·API·RBAC·client·UI 테스트로 확인 |
| 관찰 가능 공급사 목록 검증 | 품질 metadata가 온전한 이력 기준 `DISTINCT profile_name` 오름차순, legacy-only 프로필 제외, Registry에 없는 과거 프로필 포함, 원본 값 보존, client의 공백·중복·정렬 계약 검증을 PostgreSQL 통합·API·client·UI 테스트로 확인 |
| Observability supplier profile listing 기능 완료 commit 기준 전체 pytest | PostgreSQL 통합 환경에서 `2256 passed`, `2 skipped`, `6 deselected`, `0 failed`. `2 skipped`는 전용 image에서만 도는 격리 Airflow DAG 테스트이며 pass가 아닙니다. `TEST_DATABASE_URL`이 없으면 `2038 passed`, `220 skipped`, `6 deselected`로 PostgreSQL 통합 테스트가 함께 skip됩니다 |
| Observability supplier profile listing 기능 완료 commit 기준 CI | commit `de3933b5dec622fd54d2d8cbfc08506da721f918`을 대상으로 한 GitHub Actions run `32450500140` success (`test`·`airflow-smoke`·`browser-e2e`·`kubernetes-smoke`·`terraform-validate` 5개 job) |
| ETL Profile Runtime Activation 검증 | 3-state 해석(row 없음 / 버전 / `NULL`), registry versions 밖 버전 `422`, viewer `GET`·operator `PUT` RBAC, 비활성 프로필도 activation `GET` 200, `include_inactive` 목록 분리, actor는 `current_user`에서만 기록, `ON CONFLICT DO UPDATE` 동시 변경, activation read 트랜잭션 정리와 보류 ORM 쓰기 검출을 service·API·client·Streamlit AppTest·PostgreSQL 통합 테스트로 확인 |
| Activation 관련 파일별 수집 규모 | 최신 기준 `tests/test_api_etl_profile_activation.py` 69 · `tests/test_catalogguard_api_client.py` 369 · `tests/test_etl_load_history_ui.py` 154 · `tests/test_etl_profile_activation_history_service.py` 35 · `tests/test_etl_profile_activation_history_migration.py` 5. 운영 관리 화면(운영 이력 포함)은 `tests/e2e/test_etl_profile_ops_browser_e2e.py`의 전용 Chromium E2E가 현재 상태·세 event·cleanup을 추가 검증 |
| Airflow inactive profile 분류 검증 | `etl_profile_inactive` 전용 코드, `AirflowFailException`(non-retryable), `etl_profile_invalid`·`catalogguard_etl_unexpected`와의 구분, 메시지에 `profile_id`·feed 파일명 미노출을 `airflow-smoke` job의 격리 Airflow image에서 `python -m unittest discover`로 확인(`Ran 12 tests` / `OK`). 일반 pytest run에서는 Airflow 미설치로 module 단위 skip됩니다 |
| ETL Profile Runtime Activation 기능 완료 commit 기준 전체 pytest | PostgreSQL 통합 환경에서 `2369 passed`, `2 skipped`, `6 deselected`, `0 failed`, 5 warnings. `2 skipped`는 전용 image에서만 도는 격리 Airflow DAG 테스트이며 pass가 아닙니다. `TEST_DATABASE_URL`이 없으면 `2090 passed`, `281 skipped`, `6 deselected`로 PostgreSQL 통합 테스트가 함께 skip됩니다 |
| ETL Profile Runtime Activation 기능 완료 commit 기준 CI | commit `06215ec2b6104a5dedf85eb5d839bf654a5481dc`을 대상으로 한 GitHub Actions run `32571400595` success (`test`·`airflow-smoke`·`browser-e2e`·`kubernetes-smoke`·`terraform-validate` 5개 job) |
| ETL Profile Runtime Override Reset 검증 | `DELETE .../activation`의 row 삭제와 배포 기본값 복귀, 명시적 비활성 override reset이 프로필을 재활성화하는 동작, override가 없을 때의 idempotent `200`과 없는 프로필 `404`, operator `403`/viewer 구분, `PUT` `null`이 여전히 명시적 비활성이라는 회귀, reset이 과거 ETL 이력·프로필 정의를 건드리지 않는다는 확인, reset 성공 뒤 화면 예외 없음을 service·API·client·Streamlit AppTest·PostgreSQL 통합 테스트로 확인 |
| Reset 기능 commit `0a2a80f` 기준 로컬 테스트 | 로컬 PostgreSQL 통합 환경에서 `python -m pytest tests/` 결과 `2427 passed`, `6 deselected`, `0 failed`, 5 warnings. 관련 5개 파일 묶음은 `603 passed`(service 37 · API 49 · client 325 · Streamlit AppTest 141 · RBAC 51). `6 deselected`는 `pytest.ini`의 기본 `-m "not e2e and not performance"`입니다. **이 commit에 대한 CI run은 아직 없습니다.** CI는 `python -m pytest -q`로 저장소 전체를 수집해 `airflow/tests/`까지 포함하므로 이 로컬 수치와 직접 비교할 수 없습니다 |
| ETL Profile Activation History 검증 | 성공한 activate·deactivate·reset 명령마다 event 1건, 같은 `PUT`·no-op reset도 기록, 실패 요청은 기록 없음, 상태 변경과 event INSERT의 same-transaction rollback, reset event의 실제 적용 버전이 배포 기본값, 사용자 삭제 후 `actor_user_id` `NULL`·이름 snapshot 유지, 응답에 `actor_user_id` 미노출, `0015` upgrade의 backfill 없음, 화면이 reset을 비활성화로 표시하지 않음, 이력 조회 실패의 화면 격리를 migration·service·API·client·Streamlit AppTest·PostgreSQL 통합 테스트로 확인 |
| History 기능 commit `b14e16f` 기준 로컬 테스트 | 로컬 PostgreSQL 16 통합 환경에서 `python -m pytest tests/`(e2e·performance 제외) 결과 `2543 passed`, `0 failed`. 핵심 7개 파일 묶음은 `723 passed`(history migration 5 · history service 35 · activation service 37 · API 69 · client 369 · Streamlit AppTest 154 · RBAC 54). **이 commit에 대한 CI run은 아직 없습니다.** CI는 저장소 전체를 수집해 `airflow/tests/`까지 포함하므로 이 로컬 수치와 직접 비교할 수 없습니다 |
| 최신 Alembic head | `20260823_0015`(ETL profile activation events, single head) |
| 최신 CI Streamlit 시작 검사 | Health HTTP 200, body `ok` |

## 6.6 핵심 구현 구조

| 파일 | 역할 |
|---|---|
| `app.py` | 업로드 검증·마스킹 미리보기, 검수 화면, 검수 이력과 ETL 적재 이력 탭 연결 |
| `clients/catalogguard_api.py` | FastAPI 검수·ETL·promotion API 호출과 응답 schema·오류 mapping |
| `ui/etl_load_history.py` | ETL 목록·검색·페이지네이션·상세·promotion 승인 UI와 session state 관리 |
| `api/main.py`, `api/routes/` | FastAPI 앱, Health·readiness, 동기 검수·이력·비동기 작업 및 ETL 배치 조회 API |
| `api/routes/etl_loads.py`, `api/schemas.py` | 웹 ETL 실행·프로필 목록, ETL 조회, promotion·rollback endpoint, 오류 처리와 Pydantic 응답 계약 |
| `config/settings.py` | 컬럼, 허용 카테고리, 업로드 제한, 금지어 설정 |
| `config/metrics.py` | Prometheus 전용 `CollectorRegistry`, HTTP·Web ETL metric 4개 정의, `CATALOGGUARD_METRICS_ENABLED` 기반 no-op instrumentation helper |
| `core/upload_validator.py` | CSV 업로드 사전 검증 |
| `core/loader.py` | DataFrame을 Product 객체로 변환 |
| `core/models.py` | Product, ValidationIssue 데이터 모델 |
| `core/rules.py` | 전체 검수 규칙 실행 |
| `core/privacy.py` | 개인정보 정규식, 마스킹, 미리보기 복사본 생성 |
| `core/presentation.py` | 검수 결과 한글화, 필터링, 화면용 DataFrame 생성과 통계 집계 |
| `core/result_exporter.py` | 결과 CSV 생성과 수식 삽입 방어 |
| `core/product_template.py` | 입력 템플릿 CSV 생성 |
| `core/duplicate_detector.py` | 상품 ID와 상품명 중복 탐지 |
| `core/price_anomaly_detector.py` | 카테고리별 가격 이상치 탐지 |
| `core/category_mismatch_detector.py` | 상품명 키워드 기반 카테고리 불일치 탐지 |
| `db/etl_query_service.py` | ETL 배치 필터·정렬·count와 배치별 상품 SQL 페이지네이션을 담당하는 읽기 전용 query service |
| `db/catalog_promotion_rollback_service.py` | rollback preview 계산, conflict 판정, transaction 기반 실행(삭제/복원)과 duplicate rollback 방어 |
| `db/` | 검수 실행·상세 결과, ETL staging, 운영 상품 promotion·rollback의 PostgreSQL 모델, Repository, 저장 Service |
| `services/` | Redis 작업 상태 저장, 비동기 작업 파일 관리와 제출 Service |
| `workers/` | Celery 앱과 CSV 검수 Worker 작업 |
| `etl/web_service.py` | 업로드 bytes를 `TemporaryDirectory`로 옮겨 기존 `run_pipeline()`·`load_standard_csv()`를 실행하는 웹 ETL 진입점(`run_web_etl()`) |
| `etl/` | JSON 프로필 로딩·`profile_id` allowlist, 공급사 행 변환, reject 분리, 파일 변환 CLI와 PostgreSQL staging loader |
| `k8s/dev-postgres.yaml`, `k8s/migration-job.yaml`, `k8s/catalogguard-api.yaml` | kind CI 전용 PostgreSQL Deployment/Service, Alembic Migration Job, FastAPI Deployment/Service manifest(기존 `Dockerfile.aws` image 재사용, command override) |
| `terraform/versions.tf`, `terraform/variables.tf`, `terraform/main.tf`, `terraform/outputs.tf` | 수동 구성했던 AWS staging(Default VPC 조회, EC2·RDS Security Group, SSM IAM Role·Instance Profile, EC2, DB Subnet Group, RDS)의 Terraform 코드와 provider 버전 고정 |
| `terraform/tests/staging.tftest.hcl` | mock provider 기반 보안 정책 test(run 2개, assertion 12개, 실제 AWS 자격 증명·리소스 없음) |

## 6.7 데이터 보호 설계

개인정보 미리보기 기능에서 가장 중요하게 본 점은 원본 데이터와 표시용 데이터를 분리하는 것이었습니다.

```text
validated_df
-> 원본 DataFrame
-> Product 변환과 검수 규칙 실행에 사용

masked_preview_df
-> validated_df.copy(deep=True)로 만든 복사본
-> Streamlit 미리보기 표에만 사용
```

마스킹 대상은 전화번호, 이메일, 주민등록번호 형태입니다.

```text
010-1234-5678 -> 010-****-5678
sample@test.com -> sa****@test.com
900101-1234567 -> 900101-*******
```

숫자형 업무 컬럼인 `product_group_id`, `product_id`, `stock`, `price`는 미리보기 마스킹 대상에서 제외했습니다. 이 결정은 상품 ID, 가격, 재고가 전화번호나 주민등록번호 형태로 잘못 가려지는 위험을 줄이기 위한 것입니다.

## 6.8 검수 규칙 설계

현재 검수 규칙은 `core/rules.py`의 `RULES` 리스트에 등록된 함수 순서대로 실행됩니다.

- 상품 ID 중복
- 상품 그룹 카테고리 불일치
- 상품 그룹 사이즈 체계 불일치
- 상품 옵션 조합 중복
- 상품명 중복 후보
- 완전 중복 상품
- 필수 값 누락
- 색상·사이즈 표기 비표준
- 카테고리 오류
- 재고 오류와 품절 상품
- 가격 오류와 할인가 오류
- 카테고리별 가격 이상치
- 상품명과 카테고리 불일치
- 금지어와 개인정보 형태

규칙 실행 결과는 `ValidationIssue` 객체로 통일했습니다. 이 덕분에 어떤 규칙에서 발견된 문제든 `severity`, `product_id`, `product_group_id`, `message`라는 같은 형태로 화면과 CSV 다운로드에 전달할 수 있습니다.

## 6.9 CSV 검증과 템플릿

CSV 업로드는 `core/upload_validator.py`에서 사전에 검사합니다.

- CSV 확장자 검사
- 5MB 크기 제한
- UTF-8 BOM, UTF-8, CP949 인코딩 지원
- 빈 파일 차단
- 일반 텍스트가 아닌 파일 차단
- 빈 컬럼명 차단
- 중복 컬럼명 차단
- 필수 컬럼 누락 차단
- 행별 열 개수 불일치 차단
- 10,000행 초과 차단

입력 템플릿은 `core/product_template.py`에서 메모리상 CSV bytes로 생성합니다. 템플릿에는 실제 개인정보가 아닌 가짜 예시 상품 1개만 포함합니다.

## 6.10 결과 표시와 다운로드

검수 결과 화면은 사용자가 바로 조치할 수 있도록 한글 문장 중심으로 구성했습니다.

- 검수 상태
- 오류 항목
- 상품 그룹 ID
- 상품 ID
- 오류 이유
- 수정 권장사항
- 위험 수준

CSV 다운로드는 `core/result_exporter.py`에서 처리합니다. 다운로드 전 결과 DataFrame을 복사하고, Excel에서 수식으로 해석될 수 있는 문자열을 안전하게 바꾼 뒤 UTF-8 BOM CSV bytes로 변환합니다.

검수 통계에서는 필터 적용 전 전체 결과를 기준으로 다음 항목을 분석합니다.

- 오류 항목별 문제 건수
- 위험 수준별 문제 건수
- 문제가 많은 상품 TOP 5

CSV 검수 화면과 저장된 검수 이력 상세 화면은 같은 통계 UI를 재사용합니다. CSV 검수 화면에서 상세 결과 필터를 바꿔도 전체 통계는 유지되고, 상세 결과 표와 현재 필터 결과 CSV만 선택한 조건에 따라 달라집니다.

### 검수 이력 저장과 조회

FastAPI와 PostgreSQL이 함께 실행되는 로컬 또는 별도 배포 환경에서는 검수 결과를 PostgreSQL에 이력으로 저장할 수 있습니다. 검수 이력 화면에서는 파일명, 날짜 범위와 검수 상태로 저장된 실행을 검색하고 페이지 단위로 조회하며, 현재 검색 조건에 맞는 전체 이력 요약을 CSV로 내려받을 수 있습니다. 현재 목록의 두 실행은 버튼을 눌렀을 때만 비교 API를 호출해 요약 변화, 오류 항목별 변화, 공통 문제와 각 실행에만 있는 문제를 확인할 수 있습니다.

검수 이력은 현재 application 삭제 API나 자동 TTL 없이 보관합니다. 부모 `InspectionRun`을 DB에서 지울 때 자식 `InspectionResult`를 orphan으로 남기지 않는 FK CASCADE는 존재하지만, 사용자용 삭제 기능을 뜻하지는 않습니다. 물리 삭제는 목록·CSV·추세·비교와 `(file_sha256, inspection_version)` dedup 상태를 함께 바꾸므로, 실제 삭제 요구가 생기면 audit·권한·보관 기준을 먼저 설계해야 합니다. 자세한 판단은 [Inspection History Retention Policy](inspection_history_retention_policy.md)를 따릅니다.

### 검수 품질 추세 MVP

단건 검수 결과와 목록만으로는 시간 흐름에 따른 품질 변화를 파악하기 어렵습니다. 이를 위해 `inspection_runs`를 PostgreSQL에서 `Asia/Seoul` 일자별로 직접 aggregate하고, 현재 `INSPECTION_VERSION`만 조건으로 고립해 신규 검수·전체 상품·전체 문제와 오류·주의·정상 검수 수를 표시했습니다. 이 지표는 dedup 후 새로 생성된 `InspectionRun`의 품질 추세이며 요청량·업로드 횟수 통계가 아닙니다. 과거 버전 혼합 비교와 0건 날짜 bucket 생성은 이 MVP 범위에 포함하지 않았습니다.

### 검수 실행 비교 MVP

`GET /api/v1/inspections/comparison?base_run_id=&target_run_id=`는 같은 `inspection_version`의 두 저장 실행만 비교합니다. `InspectionResult`에 독립 rule code가 없으므로 `product_group_id`, `product_id`, `status`, `error_field`, `reason`, `recommendation`, `risk_level` 전체를 signature로 삼아 `Counter` multiset으로 계산합니다. 따라서 같은 signature가 한 실행에 여러 번 있어도 공통/기준 실행에만 있음/비교 실행에만 있음 개수를 보존합니다.

이 기능은 저장된 issue row 비교이지 전체 상품 row diff가 아닙니다. 정상 상품 row와 비교 파일에서 빠진 상품을 보관하지 않으므로 `base_only`를 해결됨으로, `target_only`를 신규 오류로 해석하지 않습니다. 파일 규모와 구성이 다르면 단순 문제 수 변화로 품질 향상·악화를 자동 판정하지 않으며, changed issue item pagination도 아직 제공하지 않습니다.

사용자는 저장된 실행을 검색하고 하나를 선택한 뒤 문제별 오류 이유와 수정 권장사항을 확인하고 상세 결과를 CSV로 내려받습니다. 상세 화면에서는 파일명, 검수 시간, 요약 수치와 문제별 위험 수준도 함께 확인할 수 있습니다.

![검수 이력 검색 및 목록 화면](images/04_history_list.png)

![검수 이력 상세 결과 화면](images/05_history_detail.png)

### 검수 결과 통계

아래 화면에는 검수 요약과 오류 항목별·위험 수준별·상품별 통계 3종이 표시됩니다. `가격 오류` 필터를 적용해 상세 결과는 3건만 보이지만, 통계는 필터 적용 전 전체 문제 6건을 기준으로 유지됩니다.

![검수 결과 통계 화면](images/06_inspection_statistics.png)

## 6.11 테스트 전략

테스트는 기능 단위로 분리했습니다.

| 테스트 파일 | 검증 대상 |
|---|---|
| `tests/test_upload_validator.py` | CSV 업로드 사전 검증 |
| `tests/test_loader.py` | CSV와 DataFrame 로딩 |
| `tests/test_rules.py` | 전체 검수 규칙 |
| `tests/test_duplicate_detector.py` | 중복 상품 탐지 |
| `tests/test_price_anomaly_detector.py` | 가격 이상치 탐지 |
| `tests/test_category_mismatch_detector.py` | 상품명과 카테고리 불일치 탐지 |
| `tests/test_group_size_consistency_detector.py` | 상품 그룹 사이즈 체계 혼재 탐지와 FREE·사용자 정의·빈 값·빈 그룹 ID 제외 |
| `tests/test_privacy.py` | 개인정보 마스킹과 원본 보존 |
| `tests/test_presentation.py` | 결과 표시, 필터링, 한글 메시지, 통계 집계 |
| `tests/test_result_exporter.py` | 결과 CSV 다운로드 |
| `tests/test_product_template.py` | 입력 템플릿 |
| `tests/test_inspection_service.py` | 선택 `sale_price`와 정상가·할인가 관계 검수 |
| `tests/test_app_smoke.py` | AppTest 기반 초기 렌더링과 API 주소 누락 시 안전한 화면 처리 |
| `tests/test_database_connection.py` | PostgreSQL 연결과 테스트 DB 보호 조건 |
| `tests/test_database_models.py` | PostgreSQL 모델과 제약 조건 |
| `tests/test_inspection_persistence.py` | 검수 이력 저장·조회 통합 흐름 |
| `tests/etl/test_web_service.py` | `run_web_etl()`의 정상 적재, 부분/전체 reject, 중복 재사용, profile allowlist 위반, 업로드 검증 실패, 임시 파일 정리 |
| `tests/test_api_etl_web_run.py` | `POST /api/v1/etl-loads` HTTP 상태·오류 code·응답 계약 |
| `tests/etl/test_s3_source.py` | fake S3 client로 `read_s3_csv_object()`의 prefix 위반 차단, HeadObject 크기 검증, bounded read, 없는 객체·읽기 실패의 안전한 예외 변환 |
| `tests/test_api_etl_s3_load.py` | `POST /api/v1/etl-loads/s3`의 요청 계약과 `s3_key_not_allowed`·`s3_object_not_found`·`s3_read_failed`·`s3_not_configured` 오류 매핑 |
| `tests/test_api_etl_loads.py` | ETL 배치 목록·상세 HTTP 응답과 파라미터·404 계약 |
| `tests/test_etl_query_service.py` | 실제 PostgreSQL의 ETL 검색·정렬·페이지네이션·NULL·배치 격리 |
| `tests/test_catalogguard_api_client.py` | ETL·Promotion·Rollback client 전체의 파라미터·pagination validation, 응답 shape·SHA-256·nullable 검증, rollback change의 `delete`/`restore` action 검증과 404/request ID mapping |
| `tests/test_etl_load_history_ui.py` | ETL 순수 helper와 Streamlit AppTest 검증 |
| `tests/test_api_catalog_promotion_preview.py` | promotion preview endpoint와 응답·차단 조건 검증 |
| `tests/test_api_catalog_promotions.py` | 승인·hash·blocked/stale/failed 응답과 promotion endpoint 검증 |
| `tests/test_catalog_promotion_preview_service.py` | insert/update/unchanged, before/after와 preview hash 계산 검증 |
| `tests/test_catalog_promotion_service.py` | transaction upsert, run 상태와 append-only audit 검증 |
| `tests/test_catalog_promotion_concurrency.py` | 동시 promotion의 lock·중복 성공 방지·안전한 실패 검증 |
| `tests/test_catalog_promotion_rollback_contract.py` | rollback preview·conflict 판정·실행 transaction·duplicate rollback 방어의 PostgreSQL 통합 검증 |
| `tests/test_catalog_promotion_rollback_query_service.py` | rollback 목록·상세·change 조회의 정렬·pagination·읽기 전용 동작과 "parent 없음(`None`)"·"change 0건" 구분을 실제 PostgreSQL로 검증 |
| `tests/test_api_catalog_promotion_rollbacks.py` | rollback 조회 endpoint 3개의 기본 page·pagination 전달·잘못된 파라미터 422·안전한 404와 parent 존재 시 빈 목록 200 검증 |
| `tests/test_catalog_promotion_rollback_history_ui.py` | Rollback History·Detail·Change Audit의 표 구성과 Streamlit AppTest 렌더링, 빈 상태·안전한 오류, change page 이동 시 상세 재조회 없음, 선택 변경 시 stale 상태 제거 검증 |
| `tests/e2e/test_etl_browser_e2e.py` | 실제 Chromium의 ETL 탭·검색·상세, promotion 승인·반영·이력·audit, rollback preview·승인·실행·이력·상세와 상품 Rollback 변경 Audit 표시, reject 마스킹·브라우저 오류와 PostgreSQL 최종 상태 검증 |
| `scripts/run_etl_browser_e2e.py` | 테스트 DB migration, ETL CLI·Loader, FastAPI·Streamlit readiness, Playwright 실행과 cleanup |
| `tests/etl/` | 공급사 프로필 검증, 행 변환, 파일 교체, CLI와 기존 검수 흐름 호환성 |
| `tests/test_api_inspections.py` | ETL 출력과 연동되는 FastAPI CSV 검수·중복 결과 재사용·응답 계약 |
| `tests/test_api_inspection_jobs.py`, `tests/test_inspection_tasks.py` | 비동기 작업 API, Celery task 상태 전이와 임시 파일 정리 |
| `tests/test_actor_audit.py` | Web ETL·Promotion·Rollback의 `actor_user_id`·`actor_username`이 JWT `current_user`에서만 기록되는지, viewer 403(세 endpoint)·Web ETL anonymous 401, request body 위조 무시, Promotion 실패 기록, legacy row 호환을 실제 PostgreSQL로 검증(10 scenarios) |
| `tests/test_api_etl_profile_activation.py` | activation `GET`/`PUT` 계약, viewer/operator RBAC, 3-state(row 없음 / 버전 / `NULL`), 비활성 프로필의 activation `GET` 200, registry versions 밖 버전 `422`와 `available_versions`, 관리 목록을 통한 비활성 → 재활성 왕복(35개 수집) |
| `tests/test_etl_profile_activation_service.py`, `tests/etl/test_profile_activation.py` | current-state upsert와 동시 변경(last-write-wins), effective activation 해석, activation read 트랜잭션 정리와 보류 ORM 쓰기 검출 |
| `airflow/tests/test_catalogguard_http_feed_to_staging.py` | `etl_profile_inactive` 전용 코드와 non-retryable(`AirflowFailException`), `etl_profile_invalid`·`catalogguard_etl_unexpected`와의 구분, 실패 메시지에 `profile_id`·feed 파일명 미노출. 격리 Airflow image의 `airflow-smoke` job에서 실행되며, Airflow가 없는 일반 pytest run에서는 module 단위로 skip됩니다 |
| `tests/test_metrics.py` | `CATALOGGUARD_METRICS_ENABLED` parsing, `/metrics` disabled=404·instrumentation no-op, HTTP request counter·duration histogram, 동적 ID route template 집계와 `unmatched`/`5xx` 고정 label, 민감정보 미노출, Web ETL created/duplicate/failed와 row 중복 집계 방지를 실제 PostgreSQL 포함해 검증(32 scenarios) |

통계 집계 함수와 서버 응답 적용 helper에는 정렬, 빈 값 처리, 필수 컬럼 검증, 입력 불변성, TOP 5 적용 위치, malformed 응답 차단을 확인하는 테스트를 추가했습니다. Rollback Change Audit 기능 완료 commit 기준 CI 결과는 6.5절 표의 run `31487868946`이며, 아래는 ETL·promotion 기능을 처음 CI에서 연결해 확인하던 시점의 run 기록입니다.

```text
당시 기준 저장소의 GitHub Actions run `30972097167`: success
AWS Docker runtime smoke: image build·import(`api`·`services`·`workers`·`etl` 포함)·UID 10001·migration·기본 CMD Uvicorn·`/health` HTTP 200 확인
Web ETL·promotion·rollback preview·service·API·client·UI·concurrency 검증 파일 포함
Chromium promotion E2E: 실제 반영 후 PostgreSQL 최종 상태 확인
Streamlit startup smoke: `/_stcore/health` 범위는 workflow 결과로 확인
```

ETL 적재에서는 표준 CSV 2행을 최초 적재하고 같은 파일을 재실행해 `created=False`와 중복 상품 미생성을 확인했습니다. promotion에서는 합성 batch를 preview한 뒤 승인과 hash를 함께 보내 운영 상품 insert/update, `succeeded` run, audit 저장을 확인하고, 같은 batch의 두 번째 성공 요청은 기존 결과를 재사용하는지 확인했습니다. stale hash, 검수 오류·reject·중복 identity 차단, transaction rollback, malformed API 응답 거부와 Streamlit 상태 초기화도 검증했습니다. 모든 PostgreSQL 결과는 운영 DB가 아닌 테스트 환경의 결과입니다.

GitHub Actions CI에서는 `main` 브랜치 push 또는 `main` 대상 pull request마다 일회성 PostgreSQL 18·Redis 7.4 서비스 컨테이너를 시작합니다. 두 서비스는 workflow 실행 중에만 사용할 테스트용 구성으로 Railway나 운영 DB·Redis와 분리됩니다. 당시 기준이던 run `30972097167`은 성공했으며, Alembic·pytest·AWS Docker runtime smoke·FastAPI·Celery 비동기 E2E·Streamlit startup과 별도 Chromium E2E의 세부 결과는 workflow 실행 로그를 기준으로 확인합니다.

```text
main push 또는 main 대상 pull request
-> GitHub Actions Test workflow
-> 일회성 PostgreSQL 18·Redis 7.4 서비스 컨테이너
-> Alembic upgrade head
-> Dockerfile.aws image build·import(`etl` package 포함)·UID 10001 확인
-> PostgreSQL migration·기본 CMD Uvicorn·`/health` HTTP 200 확인
-> E2E 제외 전체 pytest 1회 실행
-> Celery Worker·FastAPI 프로세스 시작
-> /health·/ready 확인
-> 비동기 CSV E2E: 신규 생성·상태 polling·결과 조회·동일 파일 재사용·임시 파일 정리
-> 실패 시 FastAPI·Celery 로그 출력, 성공·실패 모두 프로세스 정리
-> Streamlit 서버 시작
-> /_stcore/health 응답 확인
-> Streamlit 프로세스 종료
```

run `30972097167`의 workflow 로그를 직접 확인한 결과 `Run tests` 단계는 `1189 passed, 4 deselected in 32.22s`로 종료되었으며(`0 skipped`, `0 failed`), AWS Docker runtime smoke와 별도 `browser-e2e` job도 모두 success였습니다. 이 숫자는 해당 커밋·run 시점의 실제 실행 결과이며, 이후 커밋에서 테스트가 추가·삭제되면 달라질 수 있으므로 실행마다 실제 CI 로그를 기준으로 확인합니다. Rollback Change Audit 기능 완료 commit 기준 run `31487868946`의 같은 단계는 `1451 passed, 4 deselected`로 종료되었습니다.

## 6.12 샘플 데이터 기준 결과

`data/dev/products_dev.csv`는 개발 중 기본 동작을 확인하기 위한 샘플입니다.

```text
전체 상품 수: 5
전체 문제 수: 6
오류 수: 6
주의 수: 0
```

이 샘플은 앱 화면에서 검수 요약, 결과 표, 필터, CSV 다운로드가 연결되어 있는지 확인하는 기준 데이터로 사용할 수 있습니다.

## 6.13 구현 중 해결한 문제

### 원본 데이터와 미리보기 데이터 분리

개인정보 마스킹을 적용할 때 원본 DataFrame을 직접 수정하면 실제 검수 결과도 마스킹된 값으로 바뀔 수 있습니다. 이를 막기 위해 `create_masked_preview()`는 `dataframe.copy(deep=True)`로 복사본을 만든 뒤 미리보기용 DataFrame에만 마스킹을 적용합니다.

### 숫자형 컬럼 오탐 방지

전화번호와 주민등록번호 형태는 숫자 패턴이 많기 때문에 가격, 재고, 상품 ID를 잘못 가릴 위험이 있습니다. 그래서 `product_group_id`, `product_id`, `stock`, `price` 컬럼은 미리보기 마스킹 대상에서 제외했습니다.

### 가격 오류와 가격 이상치 분리

0원, 음수, 숫자가 아닌 가격은 통계 계산에 넣으면 중앙값이 왜곡됩니다. 그래서 `check_price()`에서 가격 오류를 먼저 잡고, `core/price_anomaly_detector.py`에서는 양수 가격만 중앙값 계산에 사용하도록 분리했습니다.

### 같은 상품 그룹의 정상 옵션 처리

같은 상품명이라도 같은 그룹 안에서 색상이나 사이즈가 다른 상품은 정상 옵션일 수 있습니다. `core/duplicate_detector.py`는 같은 그룹의 다른 상품 ID이고 색상 또는 사이즈가 명확히 다르면 상품명 중복 후보에서 제외합니다.

### 사이즈 체계 혼재 판정에서 오탐을 줄인 기준

패션 카탈로그에서 같은 상품의 옵션은 보통 하나의 사이즈 체계를 사용하지만, 공급사나 운영 데이터 입력 과정에서 `M`과 `100`처럼 서로 다른 체계가 한 그룹에 섞이는 경우가 있습니다. 다만 브랜드나 운영 정책에 따라 서로 다른 체계를 함께 쓸 가능성을 완전히 배제할 수는 없다고 판단해, 확정 오류가 아니라 `warning`으로 구현했습니다.

여기서 가장 중요한 판단은 무엇을 탐지하지 않을지였습니다. 숫자 사이즈를 보고 `95`는 상의, `270`은 신발, `30`은 하의처럼 카테고리를 단정하면 오탐이 크게 늘어납니다. 그래서 카테고리 추정, KR·US·UK·EU 변환, 성별·브랜드별 사이즈 차트는 구현하지 않고, 명확히 판별 가능한 사이즈 체계 혼합만 탐지했습니다.

`core/group_size_consistency_detector.py`는 기존 `SIZE_ALIASES`와 `find_standard_size()`를 재사용하는 `find_size_system()`으로 각 값을 문자형(ALPHA)·숫자형(NUMERIC)으로만 분류합니다. `medium`, `2XL` 같은 별칭은 기존 표준화 로직을 그대로 써서 ALPHA로 인식하므로 사이즈 표준화 규칙을 새로 구현하지 않았습니다. `FREE` 계열과 `1호`, `custom size`, `M-L` 같은 사용자 정의·범위 표기, 빈 값은 체계를 단정할 수 없으므로 비교에서 제외하고, 그 상품에는 이 주의를 붙이지 않습니다. 빈 값은 기존 `필수 값 누락` 규칙이 그대로 담당합니다.

`product_group_id`가 비어 있는 상품들을 하나의 그룹으로 묶으면 서로 관계없는 상품이 같은 그룹으로 오인되어 경고가 생깁니다. 그래서 빈 그룹 ID는 비교 대상에서 제외했고, 이 동작을 고정하는 회귀 테스트를 detector 단위와 `run_all_rules()` 통합 양쪽에 두었습니다.

이 규칙은 기존 규칙을 대체하지 않습니다. `사이즈 표기 비표준`은 `medium`을 `M`으로 통일하라는 표기 표준화이고, 새 규칙은 같은 그룹에서 사이즈 체계가 섞였는지를 봅니다. `medium / L / 100` 그룹에서는 두 주의가 각각의 이유로 함께 표시됩니다.

### 카테고리 정책의 내부 모순을 설정 확장으로 해결한 판단

시스템 안에 서로 어긋나는 두 기준이 있었습니다. 상품명 키워드 사전과 카테고리 별칭 사전은 신발·가방을 이미 알고 있어서 "남성 러닝 운동화 + SHOES"를 의미상 맞는 조합으로 판단하는데, 공식 허용 카테고리 목록에는 `TOP`·`BOTTOM`·`OUTER` 3개뿐이라 같은 상품에 `카테고리 오류`가 함께 붙었습니다. 신발·가방 상품은 그 오류 때문에 promotion preview의 검수 오류 차단 조건에도 걸렸습니다.

새 카테고리 체계를 만드는 대신 공식 허용 목록을 5개로 확장하는 쪽을 택했습니다. 판단 근거를 만들기 위해 구현 전에 허용 목록을 확장한 상태로 전체 테스트를 한 번 돌려, 영향을 받는 테스트가 3건뿐이고 모두 "SHOES를 미허용 표본으로 쓰던" 테스트임을 먼저 확인했습니다. 실제 production 변경은 설정 두 줄이었고 matcher·detector·DB·API·ETL 코드는 그대로 두었습니다.

`shoes`, `신발`, `bag`, `가방` 같은 표기를 정식 입력값으로 함께 열어 주지는 않았습니다. 비교 과정에서는 기존처럼 같은 의미로 다루되 CSV 입력값은 대문자 canonical 하나로 유지해, 같은 상품이 여러 표기로 저장되는 것을 막는 편이 데이터 품질 관리에 낫다고 판단했습니다.

가방은 일반 의류 사이즈가 없을 수 있지만 `size`를 카테고리별 선택 값으로 바꾸면 loader, 검수 규칙, ETL, DB `nullable` 정의까지 영향이 번집니다. 이번 범위에서는 `size=FREE`를 "별도 사이즈 없음"의 표현으로 유지하고, 카테고리별 필수 값 정책은 후속 과제로 분리했습니다. 이 시점까지 `BAG` + 빈 `size`는 필수 값 누락 오류였고, 뒤에 나오는 후속 과제에서 선택 값으로 바뀝니다.

허용 목록이 넓어지면서 기존 완전 중복 검사가 신발·가방에도 적용되기 시작했습니다. 완전 중복 판정은 category가 허용 목록 안에 있을 때만 수행하기 때문인데, 새 중복 탐지 방식을 만든 것이 아니라 기존 규칙의 적용 범위가 넓어진 것입니다. 검수 결과가 실제로 달라지므로 `INSPECTION_VERSION`을 올려 같은 CSV도 새 기준으로 다시 검수할 수 있게 했습니다.

경계는 테스트로 고정했습니다. `SHOES` 정상 입력, `BAG` + `FREE` 정상 입력, "티셔츠 + SHOES"와 "청바지 + BAG"의 상품명 의미 불일치 경고 유지, `ACCESSORY` 같은 미등록 값의 오류 유지, lowercase·한글 표기의 정식 입력 거부 유지, 신발·가방 완전 중복 활성화, `BAG` 빈 사이즈 오류 유지, `SHOES` 그룹의 숫자 사이즈 정상 판정과 문자·숫자 혼재 경고를 각각 검증했습니다.

### 선택 값 사이즈를 중복 검사에서 어떻게 볼지 정한 기준

앞의 후속 과제로 `FASHION_CATEGORY_ATTRIBUTE_RULES`를 추가해 `BAG`의 `size`를 선택 값으로 바꾸면서, `BAG` + 빈 `size`는 더 이상 필수 값 누락 오류가 아니게 되었습니다. 그런데 이때 빈 `size`가 "정상 값"인지 "판단할 수 없는 값"인지가 규칙마다 달라지는 문제가 생겼습니다. 완전 중복 검사는 빈 `size`를 비교에서 빼고 있었고, 옵션 조합 중복 검사도 빈 사이즈 비교 키를 만들 수 없어 그 행을 통째로 건너뛰고 있었습니다.

두 규칙을 차례로 정리했습니다. 먼저 완전 중복 검사에서 `is_field_required_for_category()`를 그대로 재사용해, `size`가 선택 값인 카테고리의 빈 `size`를 정상 비교값으로 인정했습니다. 그다음 같은 기준을 옵션 조합 중복 검사에도 적용했습니다. `core/fashion_attribute_validator.py`에 `build_variant_size_comparison_key()`를 추가해 기존 `build_size_comparison_key()`의 의미는 그대로 두고, 빈 사이즈일 때만 카테고리 정책을 확인해 선택 값이면 빈 문자열을 비교값으로 돌려주도록 했습니다. 정책 판단은 여전히 설정 표 한 곳에서만 나옵니다.

이 판단의 근거는 두 가지였습니다. 첫째, 같은 상품 그룹에 색상이 같고 사이즈가 모두 비어 있는 상품이 둘 있으면 마켓플레이스 옵션 목록에 구분되지 않는 항목이 두 번 노출됩니다. 사이즈 컬럼이 비어 있다는 사실이 이 문제를 없애 주지 않습니다. 둘째, 변경 전에는 이 데이터가 완전 중복도 아니고 옵션 중복도 아니어서 어떤 오류도 만들지 않는 사각지대였습니다. "빈 값은 필수 값 누락 규칙이 대신 잡는다"는 기존 전제가 `BAG`에서만 성립하지 않았기 때문입니다.

경계는 좁게 유지했습니다. `size`가 필수인 `TOP`·`BOTTOM`·`OUTER`·`SHOES`와 `ACCESSORY`·소문자 `bag` 같은 canonical이 아닌 값은 기존처럼 옵션 중복 비교에서 제외해 필수 값 누락 오류가 담당하게 두었고, 빈 `size`와 `FREE`도 계속 다른 값으로 구분합니다. 완전 중복이 옵션 중복보다 우선한다는 기존 순서도 그대로여서, 상품명과 가격까지 같은 관계에는 옵션 중복 오류를 다시 붙이지 않습니다. 화면에는 `사이즈 ''` 대신 `사이즈 없음`으로 표시하되, 비교값과 저장값은 빈 문자열 그대로 두었습니다. 검수 결과가 실제로 달라지므로 `INSPECTION_VERSION`을 `"11"`로 올렸고, DB 스키마와 ETL 산출물은 바뀌지 않아 migration과 `profile_version`은 그대로 두었습니다.

### 문자열 비교와 의미 비교를 분리한 기준

중복 검수를 정리하면서 "문자열이 같은가"와 "실제 의미가 같은가"를 같은 질문으로 다루지 않기로 했습니다. `완전 중복 상품`은 같은 상품 행을 두 번 등록했는지 찾는 규칙이라 공백과 대소문자만 정리한 값으로 비교하고, `상품 옵션 조합 중복`은 사용자가 보기에 같은 옵션인지 찾는 규칙이라 `SIZE_ALIASES`·`COLOR_ALIASES` 표준값으로 비교합니다. 그래서 `FREE`와 `free size`는 완전 중복으로는 다른 상품, 옵션 중복으로는 같은 옵션입니다.

두 기준을 통일할지 검토했지만 통일하지 않았습니다. 완전 중복은 위험 수준이 `높음`이고 권장 조치가 상품 삭제·통합이어서, 표기가 다른 두 행을 "모든 값이 같습니다"라고 설명하면 근거보다 강한 조치를 권하게 됩니다. 표기 차이 자체는 `사이즈 표기 비표준` 주의가 원본 값과 권장 표준값을 함께 알려 주므로, 표기를 통일한 뒤 다시 검수하면 완전 중복 여부가 새 기준으로 판정되는 단계적 흐름이 됩니다.

이 기준을 테스트로 고정하는 과정에서 별칭 비교의 경계 사례를 하나 발견했습니다. 별칭 조회는 앞뒤 공백만 없앴기 때문에 `free  size`처럼 공백이 두 번 들어간 값은 `SIZE_ALIASES`의 `free size`와 매칭되지 않았습니다. 그 결과 같은 그룹에 `FREE`와 `free  size`가 있어도 옵션 중복 오류는 물론 비표준 표기 주의까지 아무것도 나오지 않는 사각지대가 있었습니다. 완전 중복 비교는 이미 내부 공백을 한 칸으로 줄이고 있어서, 오히려 의미 비교 쪽이 더 엄격한 반대 방향의 불일치였습니다.

`core/fashion_attribute_validator.py`에 `collapse_comparison_whitespace()`를 두고 별칭 조회와 사용자 정의 값 비교가 같은 기준을 쓰도록 했습니다. 공백만 정리할 뿐 `OS`, `ONE`처럼 사전에 없는 표현을 새로 표준화하지는 않으며, 공백만 있는 값은 그대로 빈 값이므로 `""`와 `FREE`를 구분하는 기존 정책도 유지됩니다. 완전 중복이 별칭을 쓰지 않는다는 정책도 그대로 두었습니다. 검수 결과가 달라지므로 `INSPECTION_VERSION`을 `"12"`로 올렸고, DB 스키마와 ETL 산출물은 바뀌지 않아 migration과 `profile_version`은 그대로 두었습니다.

### 별칭 구분자 표기 흔들림을 어디까지 허용할지 정한 기준

공급사마다 같은 옵션을 `free size`, `free-size`, `free_size`, `freesize`처럼 다르게 입력합니다. 그런데 `SIZE_ALIASES`를 조사해 보니 사전이 체계적으로 채워져 있지 않았습니다. `one-size`는 등록되어 있는데 `free-size`는 없고, `extra large`는 있는데 `extra-large`는 없는 식이었습니다. 그래서 같은 `FREE` 값인데도 어떤 표기는 잡히고 어떤 표기는 아무 오류도 만들지 않는 사각지대가 10건 있었습니다.

구분자를 공백으로 바꾸는 단순한 방법을 먼저 검토했지만, 시뮬레이션에서 기존 별칭 4개(`x-large`, `x-small`, `xx-large`, `xxx-large`)가 매칭에 실패하는 회귀가 확인되어 채택하지 않았습니다. 사전이 이 표기들을 하이픈이 포함된 형태로 등록하고 있어서, 하이픈을 공백으로 바꾸면 사전에 없는 문자열이 되기 때문입니다.

대신 **별칭 사전을 조회할 때만 공백·하이픈·언더스코어를 제거한 키로 비교**하는 방식을 택했습니다. 사전의 key에도 같은 정규화를 적용해 조회 표를 만들었으므로, `x-large`는 `xlarge`가 되어 이미 등록된 `xlarge`와 연결되고 기존 별칭이 하나도 깨지지 않습니다. 시뮬레이션으로 기존 별칭 32개 중 깨지는 것이 0건, 서로 다른 표준값이 같은 조회 키로 합쳐지는 충돌도 0건임을 확인한 뒤 구현했습니다.

핵심은 이 관대함을 **사전 범위 안으로 제한**한 것입니다. 구분자를 무시한 결과가 등록된 별칭과 정확히 일치할 때만 표준값으로 인정하므로, `S-M`이나 `36-38`처럼 구분자에 의미가 있는 값은 그대로 사용자 정의 값으로 남습니다. `/`와 `.`는 `BLACK/WHITE`, `10.5`처럼 값 자체의 의미일 수 있어 제거 대상에서 뺐고, 사전 밖 사용자 정의 값의 비교 키에는 이 정책을 적용하지 않아 `MELANGE-GRAY`와 `MELANGE GRAY`는 계속 다른 값입니다. 앞으로 별칭을 추가하다가 서로 다른 표준값이 같은 조회 키로 합쳐지면 조회 표를 만드는 시점에 오류로 막고, 같은 상황을 테스트로도 고정했습니다.

정리하면 **사전 안에서는 관대하게, 사전 밖에서는 보수적으로** 비교하는 정책입니다. 오탐을 늘리지 않으면서 검수 사각지대만 줄이는 것이 목표였습니다. 완전 중복은 여전히 별칭을 쓰지 않는 엄격 비교이고, `""`와 `FREE`를 구분하는 정책도 그대로입니다. 검수 결과가 달라지므로 `INSPECTION_VERSION`을 `"13"`으로 올렸으며, DB 스키마와 ETL 산출물은 바뀌지 않아 migration과 `profile_version`은 유지했습니다.

### 모르는 사이즈 값을 어디까지 검수할지 정한 기준

별칭 조회를 계속 넓히면서 마지막으로 남은 질문은 "사전에 없는 값은 어떻게 할 것인가"였습니다. `FREEE`, `MEDUM` 같은 값은 오타로 보이고, 실제로 지금은 아무 경고도 나오지 않습니다. 이것을 검수 사각지대로 볼지 판단해야 했습니다.

먼저 사전에 없는 값을 전부 경고하는 방식을 검토했습니다. 그런데 실제로 돌려 보니 경고 대상에 `95`, `100`, `270` 같은 숫자 사이즈가 그대로 들어왔습니다. 이 값들은 `find_size_system()`이 `NUMERIC` 체계로 분류하는, 프로젝트가 이미 정상으로 인정한 값입니다. `95호`, `270mm`, `1호`, `여성용`처럼 공급사가 실제로 쓸 법한 표기도 함께 걸렸습니다. 많이 잡는 대신 정상 데이터를 잘못 잡는 쪽이 데이터 품질 도구에서는 더 나쁘다고 판단해 이 방식은 택하지 않았습니다.

다음으로 문자열 유사도로 오타 후보만 고르는 방식을 검토했습니다. 편집 거리 1 기준으로 시뮬레이션해 보니 `FREEE`와 `MEDUM`은 잡혔지만 `OS`가 `S`로, `SM`이 `M`으로, `ML`이 `L`로 매칭됐습니다. `OS`는 단일 사이즈를 뜻하는 표기인데 `S`(Small)로 고치라고 안내하면 오히려 데이터를 망가뜨립니다. 길이 조건을 걸어 짧은 값을 제외해도 `XXXS`가 `XXS`로, `XXXXL`이 `XXXL`로 매칭되는 문제가 남았습니다. 사이즈 어휘는 한 단계 위아래가 한 글자 차이여서, 유사도만으로는 오타와 사전에 없는 실제 사이즈를 원리적으로 구분할 수 없다는 결론이었습니다.

그래서 현재 정책을 유지하기로 했습니다. 표준값을 아는 값은 표기를 교정해 주고, 모르는 값은 판단을 보류합니다. `find_standard_size()`가 `None`이라는 것은 정상이라는 확정이 아니라 판단 근거가 없다는 뜻이라는 점을 문서에 명확히 남겼습니다. 대신 `FREEE` 같은 오타를 놓친다는 한계도 함께 적었습니다. 이 한계는 감춘 것이 아니라 정상 데이터를 오탐하지 않기 위해 의식적으로 감수한 트레이드오프입니다.

정리하면 **확실히 아는 값은 교정하고, 모르는 값은 억지로 추측하지 않는다**는 원칙입니다. 앞서 별칭 조회에서 정한 "사전 안에서는 관대하게, 사전 밖에서는 보수적으로"와 같은 방향이며, 새 의존성이나 임계값을 도입하지 않고 기존 규칙 구조를 그대로 유지했습니다.

### 사이즈 사전을 어디까지 확장할지 정한 기준

unknown으로 남는 사이즈가 있다는 사실만으로 사전을 크게 넓히지는 않았습니다. 현재 사전에는 `2XL`→`XXL`, `3XL`→`XXXL`, `ONE SIZE` 계열→`FREE`, `F`→`FREE`처럼 canonical 관계가 이미 명시된 표기만 있습니다. 반면 `XXXS`, `XXXXL`, `4XL`, `5XL`, `2XS`, `3XS`, `OS`, `ONE`, `FS`는 현 저장소의 코드·fixture만으로 기존 canonical과 동치라고 확인할 수 없었습니다. 특히 `2XL`과 `3XL`이 등록되어 있다고 해서 `4XL`을 `XXXL`로 합치면, 더 큰 별도 사이즈일 수 있는 값을 잃을 수 있습니다.

그래서 Policy C, 즉 **근거가 있는 값만 사전에 넣고 근거가 없는 값은 unknown으로 유지한다**는 결론을 택했습니다. `XXXS`와 `XXXXL`은 별도 canonical 후보일 수 있지만, 기존 값으로 합치지 않고 실제 공급사 데이터 또는 승인된 size taxonomy가 확보될 때까지 보류합니다. `OS`·`ONE`·`FS`도 FREE를 뜻할 가능성만으로 추정 alias를 만들지 않습니다. 현재 fixture에는 이 확장 후보들의 실제 입력 사례가 없어 공급사 실사용 근거로 삼을 수 없었습니다.

이는 Policy E의 "모른다는 것은 틀렸다는 뜻이 아니다"를 사전 관리에도 적용한 것입니다. 지원 범위를 넓히는 것보다 서로 다른 사이즈를 같은 값으로 잘못 합치지 않는 것을 우선했고, 근거가 확보되면 작은 범위의 canonical·alias 확장을 다시 검토하기로 했습니다.

### Policy C 검토를 위한 미판정 사이즈 빈도 관측

unknown을 오류로 바꾸거나 추정 alias를 추가하지 않은 대신, 운영자가 실제 공급사 데이터의 빈도를 보고 다음 vocabulary 검토 대상을 고를 수 있도록 현재 `catalog_products`에서 미판정 raw `size`를 DB `GROUP BY`로 집계하는 읽기 전용 보고서를 추가했습니다. 별칭과 숫자형 사이즈, 빈 값은 제외하고, 공백·대소문자만 같은 `4XL` 계열은 합산합니다. 그러나 사전 밖 `4XL`·`4 XL`·`4-XL`·`4/XL`은 의미 근거가 없으므로 서로 다른 후보로 남깁니다.

FastAPI의 viewer 이상 조회 API와 기존 ETL 적재 이력 화면에 상위 20개를 표시하되, 조회 실패도 ETL 이력과 운영 반영 흐름을 멈추지 않게 독립적으로 처리했습니다. 이 값은 현재 운영 카탈로그 스냅샷일 뿐 미승격 staging·inspection 전용 데이터나 과거 추이를 뜻하지 않으며, 결과만으로 alias·canonical·검수 버전·DB 스키마를 자동 변경하지 않습니다.

### 다운로드 CSV 안전 처리

검수 결과를 CSV로 내려받을 때 셀이 `=`, `+`, `-`, `@`로 시작하면 Excel에서 수식처럼 해석될 수 있습니다. `core/result_exporter.py`는 다운로드용 복사본에서만 값을 안전하게 바꿔 원본 결과 DataFrame을 보존합니다.

### 필터와 독립된 통계와 공통 UI

상세 결과 필터를 통계에도 적용하면 전체 데이터의 문제 분포를 파악하기 어렵고, CSV 검수 화면과 이력 상세 화면에서 직접 집계하면 같은 기능이 중복될 수 있습니다. 이를 해결하기 위해 집계 로직을 입력 DataFrame을 변경하지 않는 순수 함수 `build_inspection_statistics()`로 분리하고, 공통 UI helper `render_inspection_statistics()`를 구현하였습니다.

```text
필터 전 전체 결과 result_df
-> build_inspection_statistics()
-> 오류 항목별 / 위험 수준별 / 상품별 집계
-> render_inspection_statistics()
-> CSV 검수 화면과 검수 이력 상세 화면에 공통 표시

필터 결과 filtered_result_df
-> 상세 결과 표와 현재 필터 결과 CSV에 사용
```

TOP 5 제한은 집계 함수가 아닌 UI에서 적용하였습니다. 통계 합계와 저장된 요약의 전체 문제 수가 다르면 표시를 중단하고, 통계 생성 예외 원문이나 API 응답 원문, DB 정보는 사용자 화면에 노출하지 않습니다. 그 결과 필터를 변경해도 전체 통계 수치는 유지되고 상세 표만 바뀝니다. 이 통계 기능 자체는 기존 검수 DB·API·Alembic 구조를 변경하지 않고 두 화면에서 재사용하였습니다.

### 동기 검수 성능 측정과 의사결정

동기 검수의 비용을 확인하기 위해 `scripts/benchmark_inspection.py`를 추가했습니다. 재현 가능한 합성 CSV를 행 수 100, 1,000, 5,000, 10,000으로 생성하고, 워밍업 1회·반복 3회의 중앙값과 `tracemalloc` Python peak를 측정했습니다.

측정 환경은 Python 3.11.9, Windows 10.0.26200, Intel Core i7-14700F 기반의 개발 PC입니다.

| 행 수 | 입력 크기 | 문제 수 | 1회 중앙값 | 연속 2회 중앙값 | Python peak |
|---:|---:|---:|---:|---:|---:|
| 100 | 0.016 MiB | 15 | 0.009544초 | 0.018815초 | 0.177 MiB |
| 1,000 | 0.156 MiB | 149 | 0.074266초 | 0.150817초 | 1.603 MiB |
| 5,000 | 0.781 MiB | 757 | 0.371740초 | 0.867245초 | 6.485 MiB |
| 10,000 | 1.563 MiB | 1,507 | 0.875495초 | 1.645721초 | 12.939 MiB |

시간과 Python 추적 메모리는 행 수에 따라 대체로 선형으로 증가했고, 같은 검수를 두 번 수행하면 1회 대비 약 1.88~2.33배가 걸렸습니다. 10,000행 1회 검수는 개발 PC에서 약 0.88초였지만, 이 결과는 AWS 인스턴스나 대규모 트래픽 성능을 보증하지 않습니다. DB·네트워크 시간과 실제 동시성은 제외했으며 `tracemalloc`은 Pandas/C 확장 및 OS 전체 프로세스 메모리를 포함하지 않을 수 있습니다.

이 측정으로 Streamlit과 FastAPI가 각각 전체 검수를 수행하는 구조보다 서버를 단일 검수 기준으로 두는 작업을 우선했습니다. 이후 긴 검수를 요청 수명과 분리할 수 있도록 Redis Job Store와 Celery Worker를 추가했고, Streamlit에서는 즉시 검수를 기본값으로 유지하면서 백그라운드 검수를 선택할 수 있게 연결했습니다. 백그라운드 상태는 무한 폴링 없이 사용자가 새로고침 버튼을 눌러 확인합니다.

후속 Before baseline은 SQL query plan과 application pipeline을 분리해 1,000·5,000·10,000행 합성 CSV의 validation·masking·product loading·rule·presentation 단계를 측정했습니다. 일반 normal dataset에서는 rule 실행이 가장 큰 단계였고, 같은 name/variant bucket을 집중한 별도 데이터에서는 duplicate pair comparison 증가가 두드러졌습니다. 이후 결과 contract를 고정한 뒤 이미 duplicate 후보인 pair를 생략해, Python 3.11.9 기준 concentrated 1,000행의 duplicate-name 중앙값을 351.588ms에서 9.322ms로 낮췄습니다. 상세 수치·환경·한계는 [Inspection Pipeline Performance Baseline](inspection_pipeline_performance_baseline.md)과 [Duplicate Product Name Performance Optimization](duplicate_product_name_performance_optimization.md)에 정리했습니다.

### Streamlit·FastAPI 이중 검수 제거와 비동기 선택

기존 흐름은 Streamlit에서 업로드한 DataFrame을 먼저 전체 검수한 뒤 저장 시 FastAPI에 같은 파일을 다시 보내 서버가 다시 검수하는 구조였습니다. 최신 흐름은 다음과 같이 바꾸었습니다.

```text
Streamlit: 업로드 검증·마스킹 미리보기
-> 즉시 검수(기본): FastAPI POST /api/v1/inspections
-> 백그라운드 검수: FastAPI POST /api/v1/inspection-jobs
-> 상태 새로고침: GET /api/v1/inspection-jobs/{job_id}
-> 성공 시 FastAPI GET /api/v1/inspections/{inspection_run_id}
-> Streamlit이 상세 응답을 화면·통계·필터·다운로드에 재사용
```

따라서 전체 규칙은 요청당 서버에서 한 번만 실행됩니다. 즉시 검수는 POST 한 번과 상세 GET 한 번으로 동작하고, 백그라운드 검수는 작업 제출 뒤 명시적인 상태 GET으로 완료를 확인합니다. 완료된 두 흐름은 같은 상세 결과 렌더러를 사용합니다. 같은 세션에서는 업로드 bytes의 SHA-256과 활성 `job_id`로 불필요한 재제출을 막고, DB의 파일 해시·검수 버전 중복 제약은 세션 밖에서도 최종 방어선으로 유지합니다.

### 서버 응답 방어 검증

서버 상세 응답을 성공으로 간주하기 전에 실행 ID가 생성 응답과 일치하는지, `created`가 Boolean인지, 요약 수치가 음이 아닌 정수인지, 상세 결과 각 행에 필요한 문자열 필드가 있는지 검증합니다. 검증을 통과한 뒤에만 Streamlit 세션 상태와 화면 DataFrame을 갱신하므로 malformed 응답이 성공 결과로 캐시되는 경로를 차단했습니다.

### PostgreSQL 통합 테스트의 CI 자동화

로컬 개발 환경에서는 `TEST_DATABASE_URL`이 없으면 운영 DB 오연결을 막기 위해 PostgreSQL 통합 테스트를 건너뜁니다. 이 보호 조건을 완화하지 않고도 전체 통합 테스트를 반복 실행할 수 있도록 GitHub Actions와 별도 로컬 검증에서 PostgreSQL 테스트 환경만 사용했습니다.

기존 CI와 이번 작업의 migration chain은 `20260703_0001`, `20260705_0002`, `20260725_0003`, `20260727_0004`로 이어집니다. 격리된 PostgreSQL 18.4 테스트 클러스터에서 새 migration의 upgrade·downgrade·재upgrade, PostgreSQL 적재와 조회를 확인했습니다. 운영 DB 적재는 검증하지 않습니다.

### Streamlit 서버 시작 스모크 테스트

#### 문제

기존 CI는 함수, DB, API 테스트를 확인했지만 실제 Streamlit 서버가 시작되는지는 확인하지 못하였습니다. 모든 pytest가 통과해도 Streamlit 실행 프로세스가 시작 단계에서 종료되는 문제는 놓칠 수 있었습니다.

#### 해결 방법

기존 pytest Step 뒤에 Streamlit 시작 스모크 테스트를 추가하였습니다. Streamlit을 백그라운드에서 실행하고 `/_stcore/health`를 최대 30초 동안 반복 확인한 뒤, HTTP `200` 이후에도 프로세스가 살아 있는지 추가로 확인하였습니다. 성공과 실패 모두 cleanup 처리를 거쳐 프로세스를 종료하고, 실패 시에는 실행 로그와 마지막 HTTP 결과를 출력하도록 하였습니다.

이 검사에서는 `CATALOGGUARD_API_BASE_URL`, `CATALOGGUARD_API_TIMEOUT_SECONDS`, `DATABASE_URL`, `TEST_DATABASE_URL`을 빈 값으로 덮어써 Railway 운영 API와 운영 PostgreSQL 접근을 차단하였습니다. 따라서 운영 데이터나 검수 이력을 읽거나 저장하지 않고 Streamlit 서버 자체의 시작 가능 여부만 확인합니다.

#### 설계 판단

별도 스크립트 파일을 추가하지 않고 기존 Workflow의 Bash Step으로 구현하였습니다. 단순한 고정 대기 대신 최대 30초 동안 반복 요청해 준비 시간이 달라지는 상황에 대응하고, 실패 원인을 확인할 수 있도록 로그를 남겼습니다. 또한 AppTest 기반 초기 화면 검사와 실제 서버 프로세스·포트·Health 검사를 분리해 검증 범위를 보완하였습니다.

#### 결과

최신 CI에서 PostgreSQL 마이그레이션과 Streamlit 서버 시작 스모크 테스트가 성공했으며, Health HTTP `200`과 `ok` 응답을 반환하였습니다. Actions의 테스트 개수와 실행 시간은 해당 workflow 상세 결과를 기준으로 확인합니다.

이 검사는 Streamlit 실행 명령과 서버 Health endpoint를 확인하는 시작 단계 검사입니다. 브라우저 기능 전체나 CSV 검수 흐름, 운영 배포 환경을 자동으로 검증한다는 의미는 아닙니다.

### Catalog promotion E2E와 동시성에서 해결한 문제

promotion 기능을 붙이면서 단순히 브라우저에 성공 문구가 나타나는지만 확인하지 않고, 다음 문제를 실제 원인·수정·재발 방지 기준으로 정리했습니다.

1. **문제:** batch 자동 선택을 제거한 뒤 기존 E2E가 선택 없이 상세 조회를 시도했습니다.
   - **실제 원인:** UI가 사용자의 명시적 batch 선택을 요구하도록 바뀌었지만 테스트 흐름은 이전 자동 선택 가정에 남아 있었습니다.
   - **수정 방법:** 파일명·프로필명으로 batch를 검색한 뒤 `적재 배치 선택` combobox에서 option을 직접 선택하도록 시나리오를 수정했습니다.
   - **재발 방지 기준:** promotion E2E는 preview 전에 선택된 batch의 `aria-label`이 검색한 파일명과 일치하는지 확인합니다.
2. **문제:** Streamlit combobox에서 보이는 option text가 아니라 내부 text를 기준으로 선택하면 실제 선택이 검증되지 않았습니다.
   - **실제 원인:** Streamlit이 선택값을 접근성 이름인 `aria-label`로 렌더링하는 경우가 있어 내부 DOM text와 사용자에게 보이는 선택값이 달랐습니다.
   - **수정 방법:** role·label 기반 selector로 option을 선택하고 combobox의 `aria-label`을 검증했습니다.
   - **재발 방지 기준:** `nth-child`나 내부 CSS 구조가 아니라 role·label·aria-label 같은 사용자 관점 selector를 사용합니다.
3. **문제:** 숨겨진 checkbox input에 `.check()`를 호출하면 timeout이 발생했습니다.
   - **실제 원인:** Streamlit checkbox는 실제 input과 보이는 label이 분리되어 렌더링될 수 있습니다.
   - **수정 방법:** 보이는 승인 label을 클릭한 뒤 checkbox가 checked인지 확인하도록 바꿨습니다.
   - **재발 방지 기준:** 접근성 이름을 가진 사용자 노출 요소를 조작하고, 클릭 후 상태까지 검증합니다.
4. **문제:** 브라우저에서 성공 메시지가 보여도 DB 반영이나 `applying` 잔존 여부를 알 수 없었습니다.
   - **실제 원인:** UI assertion만으로는 transaction commit, audit 저장, 경쟁 요청 결과를 확인할 수 없습니다.
   - **수정 방법:** E2E 종료 후 API와 SQLAlchemy로 succeeded run 1건, 운영 상품, audit, `applying` 0건을 PostgreSQL에서 직접 확인했습니다.
   - **재발 방지 기준:** promotion E2E의 완료 조건은 브라우저 메시지와 PostgreSQL 최종 상태를 모두 만족해야 합니다.

### Web ETL AWS runtime packaging 회귀

#### 문제

Web ETL 기능 commit 병합 뒤 GitHub Actions에서 `test` job의 `Verify AWS image imports` 단계가 다음 오류로 실패했습니다. 로컬 전체 pytest(`1189 passed`)와 `docker build` 자체는 모두 통과한 상태였습니다.

```text
File "/app/api/routes/etl_loads.py", line 55, in <module>
    from etl.db_loader import ETLLoadError
ModuleNotFoundError: No module named 'etl'
```

#### 실제 원인

`Dockerfile.aws`가 `alembic`·`api`·`config`·`core`·`db`·`services`·`workers` package만 runtime image에 `COPY`하고 `etl/`은 포함하지 않았습니다. Web ETL 이전에는 API가 `etl.*`를 직접 import하지 않아 이 누락이 드러나지 않았는데, `api.routes.etl_loads`가 처음으로 `etl.db_loader`/`etl.pipeline`/`etl.profile_loader`/`etl.web_service`를 import하면서 실제 배포 이미지에서만 재현되는 결함이 되었습니다. 로컬 소스 트리에는 `etl/`이 항상 있으므로 `pytest`와 `docker build`만으로는 잡히지 않았습니다.

#### 수정 방법

`Dockerfile.aws`의 기존 COPY 순서에 맞춰 `etl` package COPY 한 줄만 추가했습니다. 이후 로컬에서 이미지를 다시 빌드해 `import etl`·`etl.web_service`·`api.main`, UID `10001`, disposable PostgreSQL 대상 `alembic upgrade head` → Uvicorn → `/health` HTTP 200까지 재현해 확인한 뒤 CI에서도 통과를 확인했습니다.

#### 재발 방지 기준

`docker build` 성공만으로는 배포 이미지의 import 정상 동작을 보장하지 않습니다. CI runtime smoke가 실제 `api.main` import 체인(`api.routes.etl_loads -> etl.*`)까지 컨테이너 안에서 실행해야 이런 packaging 누락을 잡을 수 있습니다.

### Browser E2E accessible label 충돌

#### 문제

신규 Web ETL selectbox와 기존 ETL 적재 이력 검색 필터가 둘 다 `"공급사 프로필"`이라는 같은 accessible label을 사용해, 기존 Chromium E2E의 `page.get_by_label("공급사 프로필")`가 두 요소에 매칭되며 strict-mode violation으로 실패했습니다.

#### 실제 원인

Streamlit이 combobox의 accessible name을 `"Selected {선택값}. {label}"` 형태로 만듭니다. 1차 수정으로 selectbox label을 `"실행할 공급사 프로필"`로 바꿨지만, Playwright `get_by_label()`은 기본적으로 부분 문자열(substring) 매칭이라 여전히 `"공급사 프로필"`을 포함해 같은 위반이 재현됐습니다.

#### 수정 방법

라벨을 `"공급사 프로필"` 문자열 자체를 포함하지 않는 `"ETL 실행 프로필"`로 다시 바꿔 accessible name 충돌 자체를 없앴습니다. 테스트 selector를 `.first()`나 `nth()`로 우회하지 않고, UI의 접근성 이름을 실제로 분리했습니다.

#### 재발 방지 기준

새 위젯을 추가할 때 기존 label과의 accessible name 중복 여부를 문자열 포함 관계까지 확인합니다. 테스트가 실패하면 selector를 완화하기 전에 UI 쪽 접근성 이름 충돌인지 먼저 확인합니다.

### 가상 스크롤 표에서 Browser 검증과 DB 검증의 책임 분리

#### 문제

Rollback Change Audit을 Chromium E2E에 추가하면서, 되돌린 상품 2개가 모두 화면에 보이는지 확인하려 했습니다. 그런데 Streamlit `st.dataframe`은 가상 스크롤을 사용해 브라우저 DOM에 표의 모든 행이 항상 존재하지는 않습니다. 두 상품의 변경 필드를 행으로 펼치면 22행이 되는데, 첫 화면에 노출되는 것은 그중 앞부분뿐이었고 두 번째 상품은 렌더링 경계에 걸쳐 있었습니다.

#### 판단

두 번째 상품 행에 의존하는 assertion은 로컬에서는 통과하지만 CI의 렌더링 차이로 간헐 실패(flaky)할 수 있고, 실패해도 제품 결함이 아니라 테스트 문제입니다. 그래서 그 assertion을 제거하고 검증 책임을 나눴습니다.

```text
Browser  -> 사용자가 Change Audit 화면을 실제로 볼 수 있는가
            (제목, 표 컬럼, 상품 삭제 표시, 삭제됨 표시, 전체 건수, 안정적으로 렌더링되는 상품·필드)

PostgreSQL -> 되돌린 대상 전체가 정확히 기록됐는가
            (change 2건이 모두 delete, before_data의 상품 ID 집합이 대상 상품 집합과 일치,
             original_audit_id 집합이 원본 promotion audit ID 집합과 일치)
```

#### 함께 고친 것

처음에는 표가 그려지기 전에 화면 텍스트를 읽어 간헐 실패가 났습니다. 임의 대기(`time.sleep`)를 넣는 대신, 표 안에만 존재하는 문자열이 나타날 때까지 Playwright의 auto-wait로 기다린 뒤 읽도록 바꿨습니다.

#### 결과

수정 후 로컬에서 7회 연속, Linux CI에서 1회 성공했습니다. "브라우저는 사용자가 보는 것을, DB는 데이터 정합성을 검증한다"는 기준을 세워 두면 UI 렌더링 세부 구현에 테스트가 끌려다니지 않는다는 점을 확인했습니다.

### SQLAlchemy autobegin과 sync inspection transaction 충돌

#### 문제

Authentication 작업을 검증하던 중, 로그인한 operator가 실제 신규 CSV로 `POST /api/v1/inspections`를 호출하면 `sqlalchemy.exc.InvalidRequestError: A transaction is already begun on this Session.`으로 500이 발생했습니다. Auth를 적용하기 이전 커밋(`git show HEAD:...`로 추출한, auth 코드가 전혀 없는 원본 파일)에 동일 입력으로 재현해 본 결과 똑같이 500이 발생해, 이 결함이 Authentication 때문에 생긴 회귀가 아니라 그 이전부터 있던 독립된 버그임을 먼저 확인했습니다.

#### 실제 원인

`create_inspection()`이 중복 여부를 빠르게 확인하기 위한 `find_existing_inspection_run()` 조회와, 실제 저장을 담당하는 `save_inspection_report()` 호출에 **같은 요청 범위 SQLAlchemy Session**을 전달하고 있었습니다. 앞의 SELECT가 SQLAlchemy 2.x의 autobegin으로 그 Session에 암묵적 트랜잭션을 열었고, 뒤이어 `save_inspection_report()`가 자신의 트랜잭션 경계로 `with session.begin()`을 다시 호출하면서 "이미 시작된 트랜잭션" 충돌이 발생했습니다. `save_inspection_report()` 자체는 dedupe 조회 → `begin_nested()`(SAVEPOINT)로 run·results 삽입 → unique 충돌 시 재조회까지 이미 하나의 완결된 트랜잭션 소유자로 설계되어 있었으므로, 문제는 오직 그 앞 단계에서 같은 Session을 먼저 건드린 것이었습니다.

#### 왜 기존 테스트가 못 잡았는가

`tests/test_api_inspections.py`는 `find_existing_inspection_run`과 `save_inspection_report`를 둘 다 monkeypatch로 대체하기 때문에, 실제 SQLAlchemy Session이 두 함수 사이에서 어떻게 상호작용하는지 한 번도 검증한 적이 없었습니다. `tests/test_inspection_persistence.py`는 `save_inspection_report`의 원자성을 실제 PostgreSQL로 이미 검증하고 있었지만, 이는 함수를 직접 호출하는 테스트였고 `find_existing_inspection_run`을 먼저 거치는 route 경로를 재현하지 않았습니다.

#### 수정 방법

`db/persistence_service.py`는 전혀 수정하지 않았습니다. 대신 `api/routes/inspections.py`의 `create_inspection()`에 `precheck_session: Session = Depends(get_session, use_cache=False)`를 추가해, 사전 중복조회만 완전히 독립된 Session에서 실행하도록 분리했습니다. 실제 저장은 원래의 요청 Session으로 그대로 전달해 `save_inspection_report()`가 그 Session에서 처음이자 유일하게 `session.begin()`을 호출합니다. `nullcontext()`나 `session.in_transaction()` 조건부 `begin()`, SELECT 직후 임시 `commit()`/`rollback()` 같은 우회는 commit/rollback 책임을 불명확하게 만들 수 있어 사용하지 않았습니다.

#### 검증

monkeypatch 없이 실제 PostgreSQL Session·실제 route·실제 persistence service를 사용하는 `tests/test_api_inspections_transaction_regression.py`를 새로 추가해 신규 CSV 저장(새 Session으로 재조회해 commit 확인), 동일 CSV 재사용(신규 row 없음), 저장 도중 강제 실패 시 전체 rollback(부분 row 0건), anonymous 401, viewer 403을 확인했습니다.

#### 재발 방지 기준

한 요청 안에서는 하나의 Session에 대해 하나의 트랜잭션 소유자만 두는 것을 원칙으로 합니다. 쓰기 트랜잭션을 시작하기 전에 같은 Session으로 부수적인 조회를 먼저 실행하지 않으며, 필요하면 `Depends(get_session, use_cache=False)`로 완전히 독립된 Session을 사용합니다.

### 컨테이너 안에만 있던 RDS CA bundle과 재배포 재현성

#### 문제

AWS staging에서 S3 ingestion을 실제로 검증하려면 EC2 runtime을 현재 `main` image로 교체해야 했습니다. 교체 전 기존 컨테이너를 `docker inspect`로 확인했더니 **bind mount가 하나도 없었는데**, 컨테이너 안에는 `PGSSLROOTCERT`가 가리키는 RDS CA bundle이 존재했습니다. 같은 파일이 호스트에는 없었고 `Dockerfile.aws`도 인증서를 복사하지 않습니다.

즉 CA bundle이 그 컨테이너의 writable layer 안에만 남아 있었습니다. 이 상태로 새 컨테이너를 만들면 `PGSSLMODE=verify-full` 조건에서 신뢰 앵커를 찾지 못해 RDS 연결이 끊기고, 컨테이너를 지우는 순간 인증서도 함께 사라집니다.

#### 판단

동작 중인 서버만 보면 `/ready`가 200이라 아무 문제가 없어 보였습니다. 하지만 이것은 "지금 돌아간다"와 "다시 만들어도 돌아간다"가 다른 경우였습니다. 재배포·재시작·인스턴스 교체 중 어느 것이든 발생하면 복구가 불가능해지므로, 기능 결함이 아니라 배포 재현성 결함으로 분류했습니다.

`PGSSLMODE=verify-full`을 낮추거나 인증서 검증을 우회하는 선택은 하지 않았습니다. TLS 검증 강도를 줄이는 것은 재현성 문제의 해결이 아니라 보안 후퇴이기 때문입니다.

#### 수정 방법

애플리케이션 코드는 수정하지 않았습니다. CA bundle을 컨테이너에서 호스트로 분리해 저장하고, 새 컨테이너에는 read-only로 마운트했습니다.

```text
컨테이너 layer 안에만 있던 CA bundle
-> 호스트로 분리 저장 (/etc/catalogguard/rds-ca-bundle.pem, root:root 644)
-> 새 컨테이너에 read-only mount (:ro)
```

`PGSSLROOTCERT` 값은 그대로 두고 마운트 지점을 맞췄기 때문에 환경파일은 이 목적으로 바꾸지 않았고, 인증서 신뢰 설정도 그대로 유지했습니다.

#### 검증

EC2를 완전히 `stopped` 상태로 만든 뒤 다시 시작해, 사람이 개입하지 않아도 최신 컨테이너가 `restart=unless-stopped`로 자동 기동되고 `/health`·`/ready`가 모두 200을 반환하는 것을 확인했습니다. `/ready`는 RDS 연결까지 확인하는 endpoint이므로, 이 200이 곧 read-only 마운트 기반 TLS 연결이 재현된다는 증거입니다.

#### 배운 것

살아 있는 서버의 상태를 곧 재현 가능한 상태로 착각하지 않아야 한다는 점입니다. 배포 산출물(image)과 호스트에 남지 않고 실행 중인 컨테이너에만 존재하는 값이 있으면, 그 값은 다음 배포에서 사라집니다. 이후로는 runtime을 교체하기 전에 컨테이너의 mount와 image 내용을 먼저 대조해, 어디에도 기록되지 않은 상태가 있는지 확인합니다.

### 운영 카탈로그와의 차이를 "삭제 후보"로 읽지 않기로 한 기준

ETL 적재가 끝나면 운영자가 실제로 묻는 질문은 "이번 배치가 지금 운영 카탈로그와 어떻게 다른가"였는데, 기존 Promotion Preview는 반영 대상인 staging 상품만 보기 때문에 카탈로그에는 있는데 이번 배치에 없던 상품을 아예 보여 주지 못했습니다.

조회 전용 Catalog Reconciliation Report를 추가하면서 가장 오래 고민한 것은 `not_observed_in_batch`를 무엇으로 해석할지였습니다. "카탈로그에 있는데 이번 피드에 없다"를 판매 종료나 삭제 후보로 읽으면 화면이 곧바로 유용해지지만, 그 해석이 성립하려면 공급사 피드가 항상 전체 snapshot이어야 합니다. 지금 시스템은 피드가 snapshot인지 부분 delta인지 보장하지 않습니다. 게다가 비교 기준이 정상 staging 상품이라, 원본 CSV에는 있었지만 ETL에서 거부된 행 때문에도 카탈로그 상품이 미관측으로 보일 수 있습니다. 두 경우를 데이터만으로 구분할 수 없어서 상태 이름을 관측 사실 그대로(`not_observed_in_batch`) 두고, API 문서와 화면 문구 양쪽에 삭제·판매 종료가 아니라고 명시했습니다.

상태 이름도 Promotion Preview와 일부러 다르게 붙였습니다. `insert`/`update`는 "반영하면 이렇게 된다"는 행동이고 `new`/`changed`는 "지금 이렇게 다르다"는 관측입니다. 같은 단어를 쓰면 조회 보고서가 실행 계획처럼 읽힙니다. 배치 안에 같은 상품 식별자가 두 번 있으면 어느 행이 맞는지 알 수 없으므로 첫 행을 임의로 고르지 않고 `409`로 거부했고, 운영 카탈로그를 통째로 메모리에 올리는 대신 미관측 건수는 SQL `COUNT`, 목록은 요청한 페이지 구간만 `LIMIT`/`OFFSET`으로 읽도록 했습니다.

### 품질 수치를 나열하는 것과 "좋아졌는가"에 답하는 것을 나눈 기준

품질 요약은 여러 배치를 하나의 누적 비율로 합치고, 품질 추이는 배치별 비율을 나열합니다. 둘 다 숫자는 보여 주지만 "직전보다 좋아졌는가"와 "나빠졌다면 무엇 때문인가"에는 답하지 못해서, 운영자가 차트를 눈으로 비교해야 했습니다.

품질 관찰을 추가하면서 정한 판단은 다음과 같습니다.

**공급사를 섞지 않는다.** 목록 API의 `profile_name`은 부분 검색이라 `sample` 하나가 `sample_fashion_vendor`와 `sample_marketplace_vendor`를 함께 잡습니다. 그 상태로 최신·직전을 고르면 공급사 A(2%)와 공급사 B(8%)를 비교해 "6%p 악화"가 나오는데, 이건 품질 변화가 아니라 공급사 차이입니다. 이 조회에서만 `profile_name`을 필수·정확 일치로 두고, 부분 검색 문자열이 비교 입력으로 흘러가지 않는 것을 테스트로 고정했습니다.

**모르는 값을 0으로 읽지 않는다.** 품질 요약 기능 도입 전 배치는 `total_rows`·`rejected_rows`·`error_counts`가 모두 `NULL`입니다. 이를 Reject 0건으로 읽으면 "거부가 한 건도 없던 완벽한 배치"라는 거짓 개선이 만들어지므로, 기존 요약·추이와 같은 조건으로 비교 대상에서 제외했습니다. 세 조회가 같은 배치에 다른 숫자를 말하지 않도록 비율 계산은 공용 helper 한 곳에만 두었습니다.

**변화량 단위를 명확히 한다.** 4%에서 9%가 된 것을 "125% 증가"로 쓰면 실제 변화 크기를 완전히 잘못 읽게 됩니다. 퍼센트 포인트(%p)로 계산하고 화면에도 `+5.00%p`로 표시했습니다.

**관찰을 판정으로 확대하지 않는다.** `worsened`는 Reject 비율이 올랐다는 관찰 결과이지 장애 판정이 아닙니다. "5% 이상 경고" 같은 임계값은 공급사·시즌·상품군마다 달라서 시스템이 임의로 정하면 운영자가 틀린 기준을 믿게 되므로, 방향만 말하고 임계값·자동 차단·자동 rollback·자동 알림은 만들지 않았습니다. 오류 코드 집계도 `total_count`와 `affected_batch_count`를 함께 보여 주어 한 배치의 사고와 여러 배치에 걸친 문제를 구분할 수 있게 하는 데까지이며, 근본 원인을 자동으로 확정한다고 말하지 않습니다.

### 선택 후보를 화면 목록이 아니라 DB 질의로 분리한 기준

품질 관찰을 처음 붙였을 때는 공급사 선택 후보를 화면에 이미 떠 있는 최근 적재 목록에서 만들었습니다. 추가 API 호출이 없어 가장 작은 변경이었지만, 그 목록은 한 페이지에 10건만 보여 주므로 오래전에만 데이터를 보낸 공급사는 후보에 나타나지 못했습니다. 백엔드 비교는 그 공급사에 대해 정상 동작하는데 화면에서 고를 방법만 없는 상태였습니다.

목록 API를 더 큰 `limit`으로 재호출하는 방법도 검토했지만 세 가지 이유로 쓰지 않았습니다. 목록 `limit` 상한이 100이라 공급사 전체를 보장하지 못하고, 이름만 필요한데 파일명·해시·actor·lineage까지 전부 전송하며, 그 필터는 애초에 부분 검색 의미라 정확 일치 목적과 맞지 않습니다. 무엇보다 이력이 늘면 같은 문제가 다시 생깁니다.

그래서 품질 metadata가 온전한 ETL 이력에서 `DISTINCT profile_name`을 뽑아 정렬까지 DB가 처리하는 조회 전용 API로 분리했습니다. 전체 행을 읽어 Python `set`으로 줄이지 않았고, 저장된 이름을 `strip`이나 `lower` 없이 그대로 반환해 정확 일치 비교에 다시 넣을 수 있게 했습니다. 후보 기준을 설정 Registry가 아니라 실제 적재 이력으로 둔 것도 의도적입니다. Registry에서 내려간 과거 공급사라도 품질 데이터가 남아 있으면 계속 비교할 수 있어야 하고, 반대로 Registry에 있어도 legacy 배치뿐이면 고를 이유가 없습니다. 화면 쪽에서는 선택한 공급사가 목록에서 사라졌을 때 첫 항목으로 자동 대체하지 않고 미선택으로 되돌리도록 했습니다. 자동으로 바꾸면 이전 공급사의 숫자가 다른 공급사 이름 아래 남을 수 있기 때문입니다.


## 6.14 면접 예상 질문과 답변

### Q1. 왜 Streamlit을 사용했나요?

CSV 업로드, 표 표시, 요약 지표, 다운로드 버튼을 빠르게 구현할 수 있고 Python 데이터 처리 코드와 자연스럽게 연결되기 때문입니다. 이 프로젝트의 목적은 복잡한 프론트엔드보다 검수 로직과 사용자 흐름 검증에 가까웠습니다.

### Q2. 왜 원본 DataFrame을 직접 마스킹하지 않았나요?

미리보기 보안과 검수 정확도는 서로 다른 요구사항입니다. 원본을 마스킹하면 검수 규칙이 실제 입력값을 보지 못할 수 있으므로, 원본은 검수에 쓰고 복사본만 화면 표시용으로 사용했습니다.

### Q3. 개인정보 탐지는 완벽한가요?

아닙니다. 현재는 정규식 기반이므로 오탐과 미탐 가능성이 있습니다. 다만 MVP 단계에서는 전화번호, 이메일, 주민등록번호 형태처럼 명확한 패턴을 우선 처리하고, 테스트로 원본 보존과 문장 내부 마스킹을 검증했습니다.

### Q4. 가격 이상치는 어떤 기준인가요?

같은 카테고리의 유효 가격이 5개 이상일 때 중앙값을 계산합니다. 현재 가격이 중앙값의 0.25배보다 낮거나 4배보다 높으면 주의 항목으로 표시합니다.

### Q5. 상품명 중복과 완전 중복의 차이는 무엇인가요?

상품명 중복은 정규화된 상품명이 같은 후보를 찾는 규칙이고, 완전 중복은 상품명, 카테고리, 색상, 사이즈, 가격까지 모두 같은 상품을 찾는 규칙입니다. 완전 중복은 더 강한 근거가 있으므로 오류로 봅니다.

### Q6. 업로드 검증을 검수 규칙과 분리한 이유는 무엇인가요?

파일 형식 문제와 상품 데이터 품질 문제는 성격이 다릅니다. 파일을 읽을 수 없거나 필수 컬럼이 없으면 Product 객체를 만들 수 없으므로, 검수 규칙 실행 전에 `upload_validator`에서 먼저 차단했습니다.

### Q7. 결과 메시지를 왜 별도 파일에서 한글화했나요?

검수 규칙은 내부적으로 안정적인 rule 이름과 message를 만들고, 화면 표시용 문장은 `core/presentation.py`에서 변환합니다. 이렇게 하면 규칙 로직과 사용자 표시 문구를 독립적으로 관리할 수 있습니다.

### Q8. 테스트는 어떤 기준으로 나눴나요?

파일 업로드, 로딩, 규칙, 개인정보, 결과 표시, 다운로드, 템플릿처럼 책임 단위로 나눴습니다. 기능이 늘어날 때 어느 영역이 깨졌는지 빠르게 찾기 위한 구조입니다.

### Q9. 결과 CSV에서 수식 삽입을 고려한 이유는 무엇인가요?

운영자는 결과 CSV를 Excel에서 열 가능성이 높습니다. CSV 셀이 수식으로 해석되면 의도하지 않은 동작이 생길 수 있어 다운로드용 데이터에서 수식 접두 문자를 안전하게 처리했습니다.

### Q10. 데이터베이스 테스트를 어떻게 자동화했나요?

`main` push와 `main` 대상 pull request에서 GitHub Actions가 일회성 PostgreSQL 18·Redis 7.4 서비스 컨테이너를 시작하도록 구성했습니다. `DATABASE_URL`과 `TEST_DATABASE_URL`은 CI 테스트 DB만 가리키고, Celery Broker와 Job Store는 각각 Redis DB 0·1을 사용합니다. Alembic 마이그레이션 뒤 E2E를 제외한 pytest를 실행하고, FastAPI·Celery Worker를 실제 프로세스로 시작해 비동기 CSV E2E를 별도 실행합니다. 따라서 로컬에서 테스트 DB가 없어 skipped되는 PostgreSQL 통합 테스트 25개도 CI에서는 실행되며, 운영 DB·Redis와 분리됩니다.

### Q11. 이 프로젝트의 다음 개선점은 무엇인가요?

실제 운영 데이터가 충분하다면 카테고리별 가격 기준을 설정 파일로 분리하고, 개인정보 탐지 패턴을 운영 정책에 맞게 확장할 수 있습니다. 검수 이력 삭제는 보관 요구가 확정될 때 audit event와 실행 방식을 별도 설계한 뒤에만 검토합니다.

### Q12. 왜 preview와 실제 promotion을 분리했나요?

ETL staging과 운영 상품은 책임과 위험이 다르기 때문입니다. preview에서 insert/update/unchanged와 변경 전후를 보여 주고 사용자가 승인한 뒤에만 실제 transaction을 실행하면, 반영 대상과 차단 사유를 확인한 다음 운영 데이터를 변경할 수 있습니다.

### Q13. preview hash는 어떤 문제를 막나요?

preview 이후 staging이나 현재 운영 상품이 바뀌었는데 오래된 화면의 승인으로 반영되는 stale preview를 막습니다. hash는 canonical preview 데이터의 SHA-256 비교값이며, 보안 토큰이나 원본 복원 수단은 아닙니다.

### Q14. 성공 메시지만 아니라 DB 상태까지 확인한 이유는 무엇인가요?

브라우저 메시지는 HTTP 흐름과 화면 렌더링만 증명합니다. 실제 promotion의 완료 조건은 운영 상품 insert/update, succeeded run, append-only audit이 저장되고 applying 상태가 남지 않는 것이므로 PostgreSQL 최종 상태를 함께 확인해야 합니다.

### Q15. Web ETL을 왜 CLI와 별도 엔진으로 새로 만들지 않았나요?

컬럼 변환, normal/reject 판단, summary 생성, SHA-256 계산, staging 저장 로직을 두 번 만들면 한쪽만 고치고 다른 쪽을 놓치는 위험이 커집니다. 그래서 `etl/web_service.py`의 `run_web_etl()`은 CLI가 호출하는 `run_pipeline()`·`load_standard_csv()`를 그대로 호출하는 얇은 orchestration만 추가했습니다. 업로드 bytes를 `TemporaryDirectory`로 임시 파일화해 기존 Path 기반 계약에 연결하는 adapter 역할입니다.

### Q16. Rollback이 왜 단순히 과거 값으로 되돌리지 않나요?

Promotion A가 가격을 10,000원에서 12,000원으로 바꾼 뒤 다른 작업이 12,000원을 15,000원으로 바꿨다면, Promotion A를 단순히 되돌려 10,000원으로 만드는 것은 그 사이의 정상적인 최신 변경(15,000원)까지 지우는 것입니다. 그래서 rollback 실행 직전에 현재 값이 해당 promotion의 after 값과 같은지 다시 비교하고, 다르면 conflict로 그 상품의 rollback을 막아 최신 값을 보존합니다.

### Q17. viewer/operator 2개 역할만 만들고 admin은 왜 만들지 않았나요?

현재 endpoint를 전부 분석한 결과 admin만 접근해야 하는 기능이 하나도 없었습니다(회원가입·사용자 관리 화면 자체가 이번 범위 밖입니다). 역할 수를 늘리는 것이 목표가 아니라 실제 필요한 최소 역할을 만드는 것이 목표였으므로, 조회(viewer)와 운영 데이터 변경(operator) 2개로 충분하다고 판단했습니다.

### Q18. JWT의 role을 그대로 믿지 않고 왜 매 요청마다 DB를 다시 조회하나요?

토큰에 있는 role만 믿으면 이미 발급된 토큰을 가진 사용자를 비활성화하거나 역할을 바꿔도 토큰이 만료될 때까지 예전 권한이 그대로 유지됩니다. 현재 프로젝트는 PostgreSQL이 이미 있고 사용자 수도 매우 적은 MVP이므로, `get_current_user()`가 매 요청마다 `users` 테이블에서 최신 role·is_active를 다시 확인하는 방식을 선택했습니다. 요청마다 조회가 한 번 더 늘어나지만 이 규모에서는 무시할 수 있고, 계정 비활성화를 즉시 반영할 수 있다는 이점이 더 크다고 판단했습니다.

### Q19. 왜 activation을 메모리에 저장하지 않았나요?

재시작하면 사라지기 때문입니다. 운영자가 문제 있는 공급사를 내려 뒀는데 배포나 재시작 한 번으로 조용히 다시 켜지면, 관리 기능이 있는 것이 오히려 더 위험합니다. Uvicorn worker를 여러 개 띄우면 worker마다 상태가 달라져 같은 프로필이 요청에 따라 활성으로도 비활성으로도 보입니다. 그래서 PostgreSQL에 공통 runtime 상태로 저장했고, 그 대신 옮긴 범위는 activation 상태 하나로 제한해 프로필 정의와 버전 archive는 계속 code/config에 뒀습니다.

### Q20. row가 없는 것과 row가 있고 `active_version`이 `NULL`인 것은 왜 다릅니까?

**row 없음**은 아무도 손대지 않아 배포 registry의 기본값을 그대로 쓰는 상태이고, **row 있음 + `NULL`**은 운영자가 명시적으로 내린 상태입니다. 둘을 하나로 합치면 배포 기본값이 바뀔 때 운영자의 결정이 조용히 뒤집힙니다. 예를 들어 운영자가 내려 둔 프로필을 "override 없음"과 같게 취급하면, 다음 배포에서 registry 기본값이 활성으로 바뀌는 순간 아무도 켜지 않았는데 다시 실행되기 시작합니다. 같은 이유로 `active_version: null`은 reset이 아니라 명시적 비활성이며, 배포 기본값으로 되돌릴 때는 `PUT`에 `null`을 보내는 것이 아니라 override row를 지우는 `DELETE .../activation`을 씁니다. 두 상태를 합치지 않았기 때문에 되돌리는 동작도 별도 endpoint가 됐습니다.

### Q21. Airflow에서 inactive profile은 왜 retry하지 않나요?

일시적 장애가 아니라 운영 정책 상태이기 때문입니다. network timeout이나 HTTP 5xx, 일시적 DB 오류는 시간이 지나면 회복될 수 있지만, 운영자가 의도적으로 내린 프로필은 사람이 다시 켜기 전까지 재시도로 회복되지 않습니다. 재시도해 봐야 같은 결과를 반복하며 로그만 실패로 채웁니다. 그래서 `AirflowFailException`으로 non-retryable 전용 코드 `etl_profile_inactive`를 주고, 설정 오류를 뜻하는 `etl_profile_invalid`나 예기치 못한 장애를 뜻하는 `catalogguard_etl_unexpected`와 구분했습니다. 운영자가 할 일이 각각 다릅니다. 이미 inactive인 경우에는 pre-check가 `read_http_feed_csv()` 전에서 끝내지만, pre-check 뒤 deactivate되는 race에서는 `run_web_etl()`의 최종 guard가 ETL load를 차단합니다.

### Q22. 왜 reset을 `PUT` `null`이 아니라 `DELETE`로 분리했나요?

두 동작이 **저장하는 상태가 다르기** 때문입니다. `PUT {"active_version": null}`은 "운영자가 이 프로필을 명시적으로 내렸다"는 결정을 row로 남기고, `DELETE`는 그 row 자체를 지워 배포 기본값을 다시 따르게 합니다. 같은 endpoint로 합치면 두 상태를 구분할 수 없게 되고, 그러면 Q20에서 구분한 이유가 그대로 무너집니다 — 배포 기본값이 바뀌는 순간 운영자가 내려 둔 프로필이 아무도 켜지 않았는데 되살아납니다.

그래서 기존 `PUT` `null`의 의미는 한 줄도 바꾸지 않고 `DELETE`를 따로 만들었습니다. 이 선택에는 대가도 있습니다. reset은 배포 기본값이 활성이면 프로필을 **다시 활성화**하므로 단순한 정리 조작이 아닙니다. 화면에서 되돌린 뒤 실제 적용될 버전을 미리 보여 주고, 비활성화와 같은 수준의 확인 checkbox를 거치게 한 것은 그 때문입니다.

`DELETE`는 idempotent하게 두되(override가 없어도 `200`) 없는 `profile_id`는 `404`로 남겼습니다. "지울 것이 없다"와 "그런 프로필이 없다"는 운영자가 해야 할 일이 다르고, 합치면 오타로 친 `profile_id`가 성공으로 보입니다. 응답은 `204`가 아니라 기존 activation 응답인데, `204`면 화면이 reset 직후 상태를 알기 위해 `GET`을 한 번 더 해야 하고 그 사이 다른 operator의 변경이 끼면 방금 만든 상태를 잘못 설명하게 되기 때문입니다.

### Q23. 왜 현재 상태 테이블에 이력을 계속 쌓지 않고 별도 event table을 만들었나요?

**두 표가 답하는 질문이 다르기 때문입니다.** "지금 무엇이 적용되는가"와 "지금까지 무엇을 했는가"는 조회 패턴도, 쓰기 패턴도, row 수도 다릅니다.

current-state를 event log에서 매번 재구성하면 activation을 확인할 때마다 이력 전체에서 최신 행을 골라야 하고, 그 계산이 `resolve_etl_profile_activation()` 밖으로 새어 나갑니다. 지금은 effective active version을 계산하는 곳이 한 곳뿐이고 신규 ETL 실행 경로가 그것 하나만 보는데, 그 구조가 무너집니다. 그래서 `etl_profile_activations`는 프로필당 row 하나인 현재 상태로 두고, `etl_profile_activation_events`를 성공한 명령의 append-only 이력으로 따로 뒀습니다.

대신 두 표가 어긋나면 이력을 믿을 수 없게 되므로, 상태 변경과 event INSERT를 **같은 transaction**으로 묶었습니다. 이력 기록이 실패하면 상태 변경도 rollback됩니다. 나누면 "상태만 바뀌고 기록이 없는" 순간이 생기고, 그러면 "기록에 없으니 아무도 안 했다"가 거짓이 되어 감사 기록 전체의 값이 사라집니다.

기록 단위를 "상태 변화"가 아니라 "성공한 운영 명령"으로 정한 것도 같은 이유입니다. 같은 버전을 다시 활성화해 상태가 그대로여도 운영자는 실제로 명령을 내렸고, 그 사실이 남아야 "이 시각에 누가 무엇을 확인했는가"에 답할 수 있습니다.

## 6.15 포트폴리오 소개 문구

### 이력서용 짧은 설명

Python·FastAPI와 PostgreSQL을 기반으로 CSV 상품 데이터의 필수 값, 형식, 카테고리, 재고, 가격, 중복 상품과 개인정보 포함 여부를 자동 검수하고, Redis·Celery 백그라운드 작업과 CLI/Web 공용 공급사 CSV ETL, 승인 기반 Promotion·conflict-safe Rollback까지 연결한 데이터 품질 백엔드 서비스를 구현했습니다.

### 포트폴리오용 설명

CatalogGuard Lite는 상품 운영자가 CSV 상품 데이터를 검수하고, ETL staging 결과를 확인한 뒤 운영 상품에 안전하게 반영할 수 있도록 만든 품질 검사 앱입니다. 업로드 검증, 원본 보존형 개인정보 마스킹 미리보기, 중복 상품 탐지, 가격 이상치 탐지, 정상가·할인가 관계 검수, 상품명과 카테고리 불일치 탐지, 필터와 독립된 전체 결과 통계, 결과 필터링, CSV 다운로드를 제공합니다. 합성 공급사 CSV는 JSON 프로필로 표준화한 뒤 PostgreSQL staging에 배치 적재하며, CLI와 Streamlit 웹 업로드가 같은 ETL Pipeline·loader를 공유합니다. Streamlit에서 사용자가 batch를 직접 선택해 promotion preview를 실행하면 insert/update/unchanged와 상품별 변경 전후를 보여 주고, 명시적 승인과 SHA-256 preview hash 재검증을 통과한 경우에만 FastAPI transaction이 운영 상품을 insert/update하며 promotion run과 append-only audit을 저장합니다. succeeded promotion은 이후 발생한 정상 변경을 conflict로 보존하는 rollback으로 되돌릴 수 있습니다. Playwright Chromium E2E는 승인 전 버튼 상태와 실제 UI 선택을 확인한 뒤 브라우저 성공 메시지뿐 아니라 PostgreSQL 최종 상태까지 검증했으며, 별도로 Web ETL이 추가한 UI 접근성 이름 충돌과 AWS 배포 이미지의 package 누락도 이 브라우저 E2E와 CI runtime smoke가 실제로 발견해 수정했습니다. 이 검증은 합성 공급사 fixture와 테스트 PostgreSQL 환경에서 수행했으며, 실제 외부 공급사 운영 데이터나 production catalog에 반영한 것은 아닙니다. 공개 Streamlit 앱의 배포 기능 범위는 로컬 전체 시스템과 다를 수 있습니다. Sync·Async Inspection과 Web ETL·Promotion·Rollback이 새 실행 이력 row를 만들면 요청을 처리한 JWT 사용자를 actor로 함께 기록하며, 이 값은 request body가 아니라 인증된 `current_user`에서만 채워집니다. Inspection은 Async 경로에서도 사용자 객체나 JWT가 아니라 actor scalar만 Redis·Celery 경계를 통과시키고, 동일 CSV·검수 버전 재요청에는 최초 실행 row와 최초 actor를 유지합니다. 기존 요청 middleware의 duration 측정을 재사용해 Prometheus HTTP·Web ETL metric(`GET /metrics`, 기본 비활성)을 노출하는 Observability MVP도 추가했으며, route template 기반 label로 cardinality를 제한하고 동일 ETL 배치 재사용 시 행 수를 다시 집계하지 않도록 설계했습니다. 이후 기존 `Dockerfile.aws` image를 그대로 재사용해 kind 기반 GitHub Actions에서 실제 Kubernetes cluster에 PostgreSQL·Alembic Migration Job·FastAPI Deployment를 배포하고 `/health`(liveness)·`/ready`(readiness)까지 검증하는 Kubernetes Deployment Readiness MVP를 추가했습니다. 마지막으로 콘솔에서 수동 구성했던 AWS staging(EC2·RDS·Security Group·SSM 접근)을 Terraform 코드로 옮기고, EC2 inbound 규칙 0개·RDS `5432`의 Security Group 참조 전용 허용·`publicly_accessible=false` 고정 같은 보안 조건을 mock provider 기반 `terraform test`로 고정한 뒤 GitHub Actions `terraform-validate` job으로 자동 검증하는 IaC Validation MVP를 추가했습니다. 이 단계는 코드화와 정적·mock 검증까지이며 실제 `terraform apply`로 AWS 리소스를 만들지는 않았습니다.

### 면접에서 강조할 포인트

- 원본 데이터와 표시용 데이터를 분리해 개인정보 노출 위험과 검수 정확도를 함께 관리했습니다.
- CSV 업로드 검증, 규칙 실행, 결과 표시, 다운로드를 책임별 모듈로 나눴습니다.
- 정규식 기반 탐지의 한계를 인정하고, 숫자형 컬럼 오탐 방지와 원본 보존 테스트를 추가했습니다.
- 운영자가 이해할 수 있도록 내부 오류를 한글 메시지와 수정 권장사항으로 바꿨습니다.
- 일회성 PostgreSQL 18·Redis 7.4 테스트 서비스에 Alembic 마이그레이션을 적용하고, E2E 제외 pytest와 FastAPI·Celery 비동기 E2E를 분리해 운영 DB·Redis와 격리된 검증 흐름을 구성했습니다.
- 비동기 E2E 뒤에 운영 서비스와 분리된 Streamlit 시작 검사를 실행해 실제 서버 프로세스와 Health 응답까지 검증 범위를 보완했습니다.
- ETL 실행 인터페이스를 CLI/API/UI마다 따로 만들지 않고 하나의 ETL Core(`run_pipeline()`, `load_standard_csv()`)를 재사용해, 로직 중복과 그로 인한 불일치 위험을 없앴습니다.
- 승인 없이 되돌리는 rollback이 최신 정상 변경을 지울 수 있다는 위험을 conflict 판정으로 차단했습니다.
- 테스트는 통과했지만 실제 배포 이미지에서만 재현되는 package 누락과, 신규 UI가 만든 접근성 이름 충돌을 CI runtime smoke와 기존 Browser E2E가 실제로 잡아 재발 방지 기준까지 정리했습니다.
- Prometheus metric label에 동적 ID 대신 route template을 써서 high-cardinality 문제를 사전에 차단했고, 새 timing middleware를 추가하는 대신 기존 요청 로그가 이미 계산하던 duration을 재사용했습니다.
- Actor Audit은 새 범용 Audit 테이블 대신 기존 실행 이력 테이블에 컬럼만 추가해 복잡도를 최소화했고, actor 값은 클라이언트 입력이 아니라 인증된 JWT `current_user`에서만 가져오도록 설계해 위조를 원천 차단했습니다.
- Docker 이미지가 실행되는 것에서 끝내지 않고, GitHub Actions에 kind로 실제 Kubernetes cluster를 만들어 배포까지 검증했습니다. migration과 API 실행 책임을 Job/Deployment로 분리했고, kind·kubectl·node image 버전을 SHA-256 digest까지 고정해 같은 commit이 항상 같은 toolchain으로 재현되게 했습니다.
- 프로필 activation을 재배포 없이 바꿀 수 있게 하면서도, 프로필 **정의**는 code/config에 남기고 runtime 상태 하나만 DB로 분리해 범위를 제한했습니다. "row 없음(배포 기본값)"과 "row + `NULL`(명시적 비활성)"을 다른 상태로 유지해 배포 기본값 변경이 운영자의 결정을 조용히 덮지 않게 했고, 나중에 배포 기본값으로 되돌리는 기능이 필요해졌을 때도 `PUT` `null`을 재해석하는 대신 `DELETE`를 따로 만들어 그 구분을 지켰습니다. append-only history가 없다는 사실은 당시 API·UI·문서에 함께 남겼고, 그 한계는 이후 6.26에서 별도 표로 해소했습니다.
- activation 조회 SELECT가 만든 autobegin 트랜잭션을 무조건 `rollback()`으로 지우지 않고, 보류 중인 ORM 쓰기가 있으면 먼저 실패시키도록 했습니다. 짧은 우회가 나중에 추가될 쓰기를 조용히 삼키는 것을 막기 위해 검사 비용을 감수한 선택입니다.
- Airflow에서 운영자가 의도적으로 내린 프로필을 일시 장애와 같은 실패로 다루지 않고 non-retryable 전용 코드로 분리했습니다. pre-check 시점에 이미 inactive면 HTTP feed를 시작하지 않되, pre-check 뒤 deactivate되는 race에서는 `run_web_etl()`의 최종 guard가 ETL load를 막는 경계를 문서에 남겼습니다.
- 콘솔에서 수동 구성한 AWS staging을 Terraform으로 코드화할 때, 검증한 적 없는 새 인프라를 만드는 대신 이미 검증한 구성의 코드화로 범위를 제한했습니다. `terraform validate`로는 알 수 없는 "RDS가 인터넷에 열려 있는지" 같은 조건을 mock provider test의 assertion으로 고정해, 이후 `0.0.0.0/0` inbound가 추가되면 CI가 막도록 했습니다. 실제 `apply`를 하지 않은 것과 mock provider가 검증할 수 없는 항목도 문서에 그대로 남겼습니다.

## 6.16 PostgreSQL 쿼리·인덱스 성능 검증

검수 실행 10,000건과 상세 결과 100,000건의 합성 데이터를 격리 PostgreSQL 18 DB에 생성한 뒤 동일 CSV, 이력 목록·count, 상세 조회를 `EXPLAIN (ANALYZE, BUFFERS, FORMAT JSON)`으로 측정했습니다. 기존 partial unique 복합 인덱스와 PK·외래 키 조회 인덱스가 실제 planner에 선택되었고, 목록용 복합 인덱스 후보는 절대 0.022ms 차이에 그쳤으며 상세용 후보는 사용되지 않고 크기만 증가했습니다. 따라서 보여주기식 migration은 추가하지 않고 opt-in 성능 테스트와 상세 조회 SELECT 2회 회귀 테스트를 추가했습니다.

측정 환경, 실행 계획, buffer, 인덱스 크기, 재현 명령과 한계는 [SQL 쿼리·인덱스 성능 분석](sql_performance_analysis.md)에 기록했습니다.

## 6.17 공급사 상품 CSV ETL MVP

서로 다른 공급사 컬럼명을 CatalogGuard 표준 스키마로 변환하는 설정 기반 ETL MVP를 구현했습니다. 합성 공급사 프로필 2종으로 `discount_price` 또는 `promo_price`를 `sale_price`에 연결하고, 상품 그룹 ID와 개별 SKU가 분리된 구조까지 공통 흐름에서 처리했습니다. 가격·재고 형식을 안전하게 변환했으며, 변환할 수 없는 행은 오류 코드와 사용자용 메시지를 포함한 별도 CSV로 분리했습니다. 정상가보다 큰 할인가처럼 변환은 가능한 상품 품질 문제는 reject하지 않고 `inspect_dataframe()`에서 검수합니다. 변환 결과를 실제 기존 업로드 검증과 `inspect_dataframe()`에 전달하는 통합 테스트로 호환성을 확인했습니다. 상세한 프로필 형식, reject 기준, CLI와 제한사항은 [ETL MVP 문서](etl_mvp.md)에 기록했습니다.

### PostgreSQL staging 적재 설계

#### 문제

기존 ETL은 표준 CSV, reject CSV, summary JSON을 파일로 생성했지만, 정상 상품 행을 DB에서 배치 단위로 확인하는 Load 단계는 없었습니다. 파일 변환과 DB 적재를 한 CLI에 섞으면 변환 실패와 적재 실패의 책임 경계가 흐려지므로 별도 loader를 두었습니다.

#### 구현

`etl.load_cli`는 표준 CSV bytes, 선택적 reject CSV bytes와 summary JSON을 읽고 기존 `validate_and_read_uploaded_csv()`를 재사용합니다. summary의 `profile_name`, `profile_version`, `input_filename`, 입력·출력·reject CSV SHA-256, `total_rows`, `loaded_rows`, `rejected_rows`, `error_counts`를 확인한 뒤 실제 파일 해시와 행 수를 비교하고 reject CSV의 오류 배열·동적 원본 컬럼·마스킹 결과를 검증합니다. 정상 상품 행은 `catalog_products_staging`에, reject 행은 구조화된 오류 배열과 개인정보가 마스킹된 동적 원본 JSONB로 `etl_rejected_rows`에 저장하며 빈 `sale_price`는 `NULL`로 변환합니다. 행 수는 `total_rows = loaded_rows + rejected_rows`를 만족해야 하고, 한 행에 여러 오류 코드가 있을 수 있으므로 오류 건수 합계는 reject 행 수 이상이면 허용합니다.

`etl_load_runs`는 ETL 배치 메타데이터와 품질 요약을, `catalog_products_staging`은 해당 배치의 정상 상품 행을, `etl_rejected_rows`는 reject 행의 오류·마스킹 원본을 저장합니다. 품질 요약은 `total_rows`·`rejected_rows` INTEGER와 `error_counts` JSONB로 저장하며, 기능 도입 전 배치는 세 값을 `NULL`로 유지하고 reject 상세도 자동 backfill하지 않습니다. 배치·정상 상품·reject 행은 하나의 트랜잭션으로 저장해 일부만 남지 않게 합니다. 사용자용 배치 삭제 API와 staging 상품 직접 수정 API는 없으며, 운영 반영은 별도의 promotion API가 담당합니다.

#### 중복과 rollback 판단

`(input_file_sha256, profile_name, profile_version)`을 원본·프로필 identity로 사용했습니다. 이 조합의 배치가 있으면 기존 배치 ID와 `created=False`를 반환하고 상품·reject 행을 추가하지 않습니다. 프로필 버전이 다르면 별도 배치로 저장합니다. 신규 배치·정상 상품 행·reject 행은 한 트랜잭션에 넣어 저장 중 예외가 나면 배치와 두 자식 테이블을 함께 rollback합니다. 부모 배치 삭제 시 `ON DELETE CASCADE`로 상품·reject 행도 삭제되며, `stock`, `price`, `sale_price` 음수는 DB CHECK constraint로 거부됩니다.

#### 실행과 검증

```powershell
python -m etl.load_cli `
  --input .\output\catalogguard_ready.csv `
  --rejects .\output\rejected_rows.csv `
  --summary .\output\etl_summary.json
```

실행 예시는 다음과 같습니다.

```text
DB 적재 완료
적재 배치 ID: 1
신규 적재: yes
전체 행: 2
정상 상품 행: 2
거부 행: 0
```

같은 파일의 두 번째 실행은 같은 배치 ID, `신규 적재: no`, 품질 요약과 상품 행을 중복 생성하지 않으며 저장된 품질 정보를 그대로 반환합니다. 격리된 PostgreSQL 18.4 테스트 클러스터에서 배치 품질 값과 staging 상품 2건을 확인했습니다.

#### 범위와 한계

실제 외부 공급사 운영 데이터, 운영 DB 적재, 증분 ETL과 streaming은 검증하지 않았습니다. staging 상품 수정·삭제, 상품 변경 이력 조회 API와 자동 공급사 감지는 지원하지 않습니다. 운영 상품 promotion은 합성 공급사 fixture와 테스트 PostgreSQL 환경에서만 검증했으며, production catalog 반영이나 공개 Streamlit 앱의 배포 범위까지 보증하지 않습니다. reject 행은 `etl_rejected_rows`에 마스킹된 원본과 구조화된 오류로 저장합니다. Streamlit 적재 이력 화면의 배치·상품·reject 조회는 읽기 전용이며, ETL 실행(아래 절)과 promotion은 각각 FastAPI POST API를 호출합니다.

### 웹 ETL 실행

#### 문제

파일 변환과 PostgreSQL 적재는 CLI로 가능했지만, 사용자가 웹 화면에서 CSV 선택부터 staging 적재까지 직접 수행할 수는 없었습니다. 그 결과 "ETL 시작은 CLI, 조회·운영 반영은 웹"으로 사용자 흐름이 갈라져 있었습니다.

#### 구현

새 ETL 엔진을 만드는 대신 `etl/web_service.py`의 `run_web_etl()`이 CLI(`etl.cli`/`etl.load_cli`)와 같은 `run_pipeline()`·`load_standard_csv()`를 그대로 호출하는 얇은 orchestration을 추가했습니다. 업로드 bytes는 `TemporaryDirectory`에 임시 저장해 기존 `Path` 기반 Pipeline 계약에 연결하고, 종료 시 자동 정리됩니다. 외부에는 `profile_id` 문자열만 노출하고, `etl.profile_loader`의 서버 allowlist(`get_profile_path()`)로만 실제 `config/etl/*.json` 파일을 찾아 임의 filesystem 경로 입력을 차단합니다. 업로드는 기존 `core.upload_validator`의 5MB 제한과 CSV 검증을 그대로 재사용합니다. FastAPI는 `POST /api/v1/etl-loads`(업로드+실행)와 `GET /api/v1/etl-profiles`(허용 프로필 목록) 두 endpoint를 추가했고, Streamlit은 명시적 버튼 클릭에서만 이 API를 호출합니다.

#### 설계 판단

CLI ETL 엔진, API ETL 엔진, UI ETL 엔진을 각각 만들면 transformer 매핑·reject 판단·summary 생성·SHA-256 계산·staging 저장 로직이 두 배로 늘어납니다. 대신 CLI와 Web이 실행 인터페이스만 다르고 핵심 ETL Core(`run_pipeline()`, `load_standard_csv()`)는 하나만 두어, 같은 `(input_file_sha256, profile_name, profile_version)` 중복 판단과 새 DB 테이블·Alembic migration 없이 기존 `etl_load_runs`/`catalog_products_staging`/`etl_rejected_rows`를 그대로 재사용하도록 했습니다. 웹 ETL 성공은 promotion을 자동으로 시작하지 않으며, 사용자가 ETL 적재 이력에서 새 batch를 직접 선택해야 기존 promotion preview·승인 흐름으로 이어집니다.

#### 검증

`tests/etl/test_web_service.py`가 정상 적재, 부분/전체 reject, 동일 입력 재사용(`created=False`), profile allowlist 위반(path traversal 시도 포함, DB에 아무 것도 쓰지 않음까지 확인), 빈/과대/손상 업로드, 성공·실패 모든 경로에서의 임시 파일 정리를 PostgreSQL 통합 테스트로 확인했습니다. `tests/test_api_etl_web_run.py`는 HTTP 상태·오류 code·응답 계약을, `tests/test_etl_load_history_ui.py`는 Streamlit이 파일 선택·프로필 변경만으로는 API를 호출하지 않고 버튼 클릭에서만 요청하는지, 성공 후 ETL 적재 이력 캐시만 무효화하고 promotion 캐시는 건드리지 않는지를 확인했습니다.

### 운영 상품 promotion persistence

#### 문제

ETL staging 행은 변환·검증 결과를 보관하는 중간 데이터이므로 운영 카탈로그와 같은 identity나 삭제 정책을 사용할 수 없었습니다. 같은 외부 상품 ID가 공급사마다 충돌할 수 있고, 동일 ETL batch의 성공 반영은 한 번만 허용하면서 실패·차단 시도는 감사 목적으로 남겨야 했습니다.

#### 해결

`catalog_products`를 staging과 분리하고 `(supplier_key, external_product_id)`를 운영 상품 identity로 고정했습니다. `supplier_key`는 ETL batch의 `profile_name`, `external_product_id`는 staging의 `product_id`에 대응합니다. `product_id` 단독 unique나 `profile_version`을 identity에 포함하지 않았습니다.

`catalog_promotion_preview_service.py`는 staging 상품과 현재 운영 상품을 비교해 `insert`·`update`·`unchanged`와 상품별 before/after를 만들고, inspection 오류·reject·중복 identity·품질 summary 누락을 차단 사유로 반환합니다. canonical JSON의 SHA-256 `preview_hash`를 preview와 실제 반영 시점에 재계산해 stale preview를 차단합니다. 이 hash는 암호화나 인증 토큰이 아니라 두 시점의 데이터가 같은지 확인하는 비교값입니다.

`catalog_promotion_service.py`는 `confirmation=true`와 `expected_preview_hash`를 요구하고, batch·staging·운영 상품을 잠근 하나의 transaction 안에서 preview를 재검증합니다. hash가 일치하면 `catalog_products`에 insert/update하고 `catalog_promotion_runs`를 `applying`에서 `succeeded`로 완료합니다. 조건 불충족은 `blocked`, hash 불일치는 `preview_stale`, 예외는 rollback과 안전한 `failed` run으로 기록합니다.

`catalog_promotion_runs`는 `applying`·`succeeded`·`failed`·`blocked` 상태와 insert/update/unchanged/blocked/error/warning count, preview 메타데이터와 안전한 실패 정보를 저장합니다. 같은 `etl_load_run_id`의 `succeeded` 행만 PostgreSQL partial unique index로 한 건을 허용해 성공 반영 중복을 막고, `failed`·`blocked` 재시도 기록은 허용합니다. `catalog_product_changes`는 `insert`·`update`만 기록하는 append-only JSONB audit 모델이며, before/after와 changed fields를 저장합니다.

#### 검증과 범위

Alembic revision `20260728_0006`에서 `catalog_products` → `catalog_promotion_runs` → `catalog_product_changes` 순서의 upgrade와 역순 downgrade를 구성했습니다. 격리된 PostgreSQL 18에서 빈 DB upgrade, `0005` downgrade, 재-upgrade, 단일 head를 확인하고 promotion PostgreSQL 테스트로 복합 unique·partial index·JSONB shape·action 규칙·FK RESTRICT를 검증했습니다.

promotion run·audit 조회 전용 API와 운영 배포 migration 적용은 별도 범위입니다. 현재 검증은 preview API, 승인 promotion API, Streamlit 승인 UI, transaction upsert, 동시성 차단과 Chromium E2E에 집중하며, 실제 외부 운영 catalog에는 반영하지 않았습니다.

### Catalog Promotion Rollback

#### 문제

promotion으로 운영 상품에 반영은 가능했지만, 잘못 반영한 경우 되돌릴 방법이 없었습니다. 더 위험한 점은 단순히 audit에 남긴 과거 값으로 덮어쓰는 rollback입니다.

```text
Promotion A: price 10,000 -> 12,000
이후 다른 변경: price 12,000 -> 15,000
Promotion A를 단순 되돌리면: price 15,000 -> 10,000
```

이렇게 하면 Promotion A 이후에 생긴 정상적인 최신 변경(12,000 -> 15,000)까지 사라집니다. rollback 실행 직전에 현재 운영 상품이 해당 promotion이 만든 결과 그대로인지 다시 확인해야 한다는 것이 핵심 문제였습니다.

#### 구현

`db/catalog_promotion_rollback_service.py`의 `preview_catalog_promotion_rollback()`은 대상 promotion run이 `succeeded` 상태인지, 이미 rollback되지 않았는지 확인한 뒤 상품별 `rollback_action`(`insert` 상품은 `delete`, `update` 상품은 `restore`)과 conflict 여부를 계산합니다. conflict 판정은 현재 상품 값과 해당 promotion의 after 값을 비교해, 다르면(위 예시의 15,000 ≠ 12,000) `rollback_conflict`로 그 상품의 rollback을 막고 최신 값을 보존합니다. 하나라도 conflict가 있으면 `rollback_eligible=False`입니다.

promotion과 같은 원칙으로 preview hash(canonical JSON SHA-256)를 계산하고, 실행 endpoint(`execute_catalog_promotion_rollback()`)는 이 값을 신뢰하지 않고 `SELECT ... FOR UPDATE`로 대상을 다시 잠근 뒤 preview를 재계산해 hash를 재검증합니다. 조건을 통과하면 하나의 transaction 안에서 INSERT promotion 상품은 삭제하고 UPDATE promotion 상품은 이전 값으로 복원하며, 상품마다 `CatalogPromotionRollbackChange` append-only audit을 함께 기록합니다. 원본 `catalog_product_changes` audit은 상품이 삭제되어도 삭제하지 않고 보존합니다.

#### 검증

로컬 disposable PostgreSQL에서 상품 하나가 CHECK constraint를 위반하도록 강제해, 두 상품 모두 rollback 시도 전 값을 그대로 유지하고 `catalog_promotion_rollback_changes`가 0건, `failed` run 1건만 남는 all-or-nothing 동작을 확인했습니다. `tests/test_catalog_promotion_rollback_contract.py`는 INSERT 삭제·UPDATE 복원·conflict 차단과 최신 값 유지·stale hash 차단·duplicate rollback을 service 예외와 DB partial unique index 양쪽에서 방어하는지를 실제 PostgreSQL 통합 테스트로 확인했습니다. 이후 rollback 실행 이력·상세와 상품별 change audit 조회를 추가하면서 검증도 함께 넓혔습니다. `tests/test_catalog_promotion_rollback_query_service.py`와 `tests/test_api_catalog_promotion_rollbacks.py`가 조회 계층의 정렬·pagination과 "rollback run 없음(404)" / "change 0건(200 + 빈 목록)" 구분을 확인하고, `tests/test_catalog_promotion_rollback_history_ui.py`가 Streamlit History·Detail·Change Audit 화면을 AppTest로 확인합니다. 실제 Chromium E2E(`tests/e2e/test_etl_browser_e2e.py`)는 Promotion 반영부터 Rollback 실행, Rollback 이력·상세, `상품 Rollback 변경 Audit` 표시까지 한 흐름으로 진행한 뒤 PostgreSQL에서 rollback change 2건이 모두 `delete`인지, `original_audit_id` 집합이 원본 `catalog_product_changes.id` 집합과 일치하는지, 되돌린 뒤 운영 상품이 0건인지를 확인합니다. 이 수치는 합성 E2E fixture(INSERT promotion 2건) 기준 결과이며 제품이 항상 보장하는 값이 아닙니다.

### ETL 적재 배치 조회 API

#### 문제

PostgreSQL staging에 상품을 저장할 수 있었지만, 어떤 공급사 파일이 언제 적재되었는지 외부에서 확인할 API가 없었습니다. 프로필별 적재 이력을 검색하거나 특정 배치의 상품을 확인할 수 없어 추후 Streamlit 관리 화면을 연결할 명확한 조회 계약도 부족했습니다.

#### 해결

`GET /api/v1/etl-loads`는 파일명과 프로필명의 대소문자 구분 없는 부분 검색, `limit`·`offset` 페이지네이션, 최신 적재 우선 정렬과 전체·정상·거부 행 수를 제공합니다. 두 검색 조건은 AND로 적용하며 목록과 `total`이 같은 필터를 사용합니다. `GET /api/v1/etl-loads/{etl_load_run_id}`는 여기에 오류 코드별 건수, reject 상세 저장 여부, input/output SHA-256, 해당 배치의 staging 상품을 `product_limit`·`product_offset`으로 반환하고 없는 배치는 HTTP 404로 처리합니다. `GET /api/v1/etl-loads/{etl_load_run_id}/rejections`는 구조화된 오류와 마스킹된 원본을 페이지 단위로 반환하며, 과거 미저장 배치는 빈 목록으로 표시합니다.

#### 기술적 판단

- 목록에는 긴 SHA-256과 상품 전체를 제외해 이력 탐색 응답의 크기를 줄이고, 상세 요청에서만 해시와 상품을 제공합니다.
- 상품 전체를 메모리에 올린 뒤 자르지 않고 SQL `LIMIT`·`OFFSET`과 staging 행 기본 키 `id` 오름차순을 적용합니다.
- 목록과 count가 어긋나지 않도록 같은 필터 함수를 재사용하고, 모든 상품 쿼리에 배치 ID를 적용합니다.
- SQLAlchemy ORM 객체를 직접 반환하지 않고 읽기 전용 query service의 dataclass와 API의 Pydantic 모델로 응답 계약을 고정합니다.
- `%`, `_`, `\`는 SQL LIKE wildcard가 아니라 실제 문자로 검색되도록 escape합니다.
- 조회 함수는 relationship 전체 lazy loading, 상품별 추가 SELECT, `commit`과 `rollback`을 사용하지 않습니다.

#### 검증

PostgreSQL 테스트 클러스터에서 정렬, 파일명·프로필명 검색과 AND 조건, 대소문자 무시, LIKE 특수문자, 목록·count 일치, 상품 페이지네이션과 배치 격리, nullable 값, reject 상세 페이지네이션, 마스킹 원본, 없는 배치를 확인했습니다. promotion 관련 PostgreSQL 테스트에서는 transaction, partial unique index, before/after audit, stale·동시 요청 결과를 확인했으며, 전체 실행 수는 workflow별 로그를 기준으로 관리합니다.

### Streamlit ETL 적재 이력 화면

Streamlit은 `CatalogGuardApiClient`를 통해 웹 ETL 실행, 목록·상세 조회, promotion·rollback POST API를 호출합니다. staging 상품 직접 수정·삭제는 수행하지 않지만, 공급사 CSV 업로드부터 batch preview·승인·운영 상품 반영·필요 시 rollback까지 이 화면들에서 요청할 수 있습니다.

| 기능 | 구현 범위 |
|---|---|
| ETL 실행 | 공급사 CSV 업로드와 "ETL 실행 프로필" 선택, 버튼 클릭으로 `POST /api/v1/etl-loads` 실행, 정상/거부 행 수와 배치 ID 표시 |
| 목록 | 10건 단위 페이지네이션, 전체 건수, 빈 목록 안내 |
| 검색 | filename·profile_name 부분 검색과 두 조건 AND |
| 상세 | 배치 메타데이터, 전체·정상·거부 행, 정상 처리율, 오류 코드 통계, input/output SHA-256 전체 값, 적재 시각, reject 상세와 마스킹된 원본 |
| lineage 비교 | 같은 Profile의 두 batch에서 입력 SHA-256·definition fingerprint·application commit과 저장된 semantic snapshot 차이를 확인 |
| 상품 | 선택한 배치의 staging 상품 20건 단위 페이지네이션 |
| promotion | 선택한 batch의 insert/update/unchanged, 변경 전후, 반영 가능 여부와 차단 사유 표시 |
| 승인 | 승인 checkbox와 preview hash가 모두 유효할 때만 운영 반영 버튼 활성화 |
| rollback | succeeded promotion의 rollback preview, restore/delete/conflict count, 승인 checkbox와 hash 재검증 후 실행 버튼 |
| nullable | `sale_price`, `description`, `seller`의 `null` 안전 표시 |
| 오류 | 404와 유효한 request ID 표시 |
| 상태 | 검색·배치·프로필 변경 시 stale 상세·상품·reject·ETL 실행 결과 제거, 실패 상세 요청 중복 호출 방지 |

순수 helper 테스트와 Streamlit AppTest로 목록·검색·빈 결과·페이지 이동·상세·SHA-256·reject 상세·마스킹 원본·nullable·404·request ID·promotion preview·승인·stale 상태 초기화를 검증했습니다. 실제 브라우저 전체 상호작용은 아래 별도 Chromium E2E에서 검증하며, GitHub Actions의 Streamlit startup smoke는 서버 startup과 `/_stcore/health` HTTP 200을 확인합니다.

### Historical ETL lineage comparison

**문제.** `profile_name`과 `profile_version`만으로는 과거 batch가 실제 어떤 Profile semantic definition과 application code로 실행됐는지 충분히 조사하기 어려웠습니다.

**구현.** batch lineage에 Profile definition fingerprint와 snapshot, application Git commit SHA를 저장하고, Streamlit ETL 상세에서 같은 Profile의 다른 batch를 선택해 입력 데이터·Profile 정의·application commit을 비교하게 했습니다. 양쪽 snapshot이 있으면 컬럼 매핑, 필수 원본 컬럼, 기본값의 semantic 차이까지 확인합니다.

**운영 경계.** legacy `NULL`은 변경으로 오판하지 않고 알 수 없음으로 표시합니다. 이 비교는 저장된 lineage metadata를 읽는 조사 도구이며, Docker image·dependency·OS/environment·당시 DB 상태·원본 bytes를 보존하지 않으므로 결과 원인을 자동으로 증명하거나 완전한 실행 재현을 주장하지 않습니다.

### 실제 Chromium ETL 브라우저 E2E

계층별 pytest와 Streamlit AppTest만으로는 실제 접근성 이름, rerun 이후 상태, 동적 표·expander 렌더링, 승인 checkbox 동작과 HTML 내부 raw 민감정보 노출을 확인할 수 없었습니다. 전용 `requirements-e2e.txt`와 ETL·promotion 합성 fixture를 사용하고, `scripts/run_etl_browser_e2e.py`가 테스트 PostgreSQL migration, `etl.cli`, `etl.load_cli`, FastAPI, Streamlit, readiness 대기와 Playwright pytest를 한 번에 관리하도록 구성했습니다.

브라우저 시나리오는 reject fixture에서 ETL 검색·상세·마스킹을 확인하고, promotion fixture에서 파일명·프로필명 검색, batch combobox의 실제 선택, preview, 상품별 변경 전후, 승인 전 반영 버튼 disabled, 승인 checkbox, 실제 promotion과 성공·중복 메시지를 확인한다. promotion 종료 후에는 PostgreSQL에서 succeeded run 1건, 운영 상품 insert/update, audit 존재, applying 0건을 직접 조회한다. reject 원본 expander의 네 가지 원문은 body text와 HTML에 없음을 확인하고, 두 시나리오 모두 console error·page error 0건을 요구한다.

로컬 Chromium 실행은 `python scripts/run_etl_browser_e2e.py`로 수행하며 `DATABASE_URL`은 loopback 테스트 PostgreSQL만 허용한다. 실패 시 screenshot·HTML·FastAPI·Streamlit·Playwright 로그를 `artifacts/browser-e2e/`에 보존하고 runner가 시작한 프로세스와 임시 파일을 정리한다. GitHub Actions에는 기존 Redis 기반 일반 테스트와 분리된 PostgreSQL·Chromium `browser-e2e` job을 추가했으며, 실패 artifact만 업로드하도록 구성했다. 운영 DB·실제 공급사·모바일 브라우저는 범위에서 제외했다.

이 E2E는 ETL 검색·상세, promotion 화면과 rollback 실행·이력·상세·상품 Rollback 변경 Audit 화면을 다루며, 웹 ETL CSV 업로드 화면 자체를 처음부터 끝까지 조작하는 전용 시나리오는 아직 없다. 다만 웹 ETL selectbox 추가로 이 기존 E2E가 실제 회귀를 잡은 사례가 있다(6.13 "구현 중 해결한 문제" 참고). 웹 ETL 핵심 실행 로직은 이 브라우저 E2E가 아니라 API·client·PostgreSQL 통합 테스트와 Streamlit AppTest로 검증한다.

### 두 번째 합성 공급사로 검증한 확장성

#### 문제

첫 번째 프로필만으로는 ETL이 `vendor_sku` 컬럼 구조에 묶여 있지 않은지 증명하기 어려웠다.

#### 해결

`style_id`와 `sku_code`가 분리된 두 번째 합성 공급사 프로필 `config/etl/sample_marketplace_vendor_v1.json`과 `tests/fixtures/etl/sample_marketplace_vendor_mixed.csv`를 추가했다.

#### 결과

`etl/profile_loader.py`, `etl/transformer.py`, `etl/pipeline.py`를 수정하지 않고 JSON 매핑 프로필과 fixture, Repository 통합 테스트만으로 3행 중 2행을 변환하고 1행을 reject했다. 같은 `STYLE-100` 그룹 아래 서로 다른 SKU를 유지했으며, 정상가보다 큰 할인가 관계는 기존 CatalogGuard 검수 결과로 연결했다.

#### 의미

공급사별 데이터 구조 차이를 공급사명 조건문이나 전용 transformer가 아니라 설정 데이터로 분리하는 설계를 검증했다. 상품 그룹 ID와 개별 SKU가 별도 컬럼인 구조도 동일한 공통 ETL 흐름으로 처리할 수 있음을 확인했다.

### ETL 설계 판단

- 공급사별 Python 변환 코드를 따로 만들면 컬럼 변경 때마다 배포가 필요하므로, 허용된 표준 컬럼만 가리키는 JSON 프로필로 매핑을 분리했습니다. 프로필은 단순 데이터로만 해석하고 동적 코드는 실행하지 않습니다.
- 가격·재고 파싱 실패는 상품 품질 규칙의 오류와 성격이 다르므로 `rejected_rows.csv`로 분리하고, 정상 행만 기존 CatalogGuard 검수기에 전달합니다.
- 입력·프로필을 보호하고 출력 세 파일의 일관성을 유지하기 위해 임시 파일을 같은 디렉터리에 쓴 뒤 `os.replace()`로 교체합니다. 기존 출력이 있다면 백업 후 교체하고, 중간 실패 시 기존 파일을 복구합니다.
- `etl_summary.json`에는 입력·출력 SHA-256과 처리 건수를 남겨 변환 결과를 추적할 수 있게 했으며, 생성된 표준 CSV는 기존 `validate_and_read_uploaded_csv()`와 `inspect_dataframe()`에 연결해 호환성을 확인했습니다.

## 6.18 Authentication과 RBAC

### 문제

검수·ETL·Promotion·Rollback 기능은 모두 완성되어 있었지만, "누가 조회만 할 수 있고 누가 실제 운영 데이터를 변경할 수 있는가"를 서버가 통제하는 계층이 없었습니다. 누구나 Streamlit이나 API를 직접 호출해 Promotion·Rollback 같은 운영 데이터 변경 작업을 실행할 수 있는 상태였습니다.

### 역할 설계

전체 endpoint를 조회(Public/Authenticated read)와 운영 데이터 변경(Write)으로 분류한 뒤, 조회는 로그인한 사용자면 누구나, 변경은 별도 역할만 가능하도록 최소 역할을 설계했습니다. admin 전용 기능이 없어 admin 역할은 만들지 않고 `viewer`(조회)·`operator`(운영 데이터 변경) 2개로 확정했습니다.

| Endpoint | anonymous | viewer | operator |
|---|---|---|---|
| `GET /health`, `GET /ready` | 200 | 200 | 200 |
| `POST /api/v1/auth/login` | 200(자격 증명 유효 시) | - | - |
| `GET /api/v1/auth/me` | 401 | 200 | 200 |
| 검수·ETL·Promotion/Rollback 이력·History/Audit 조회, Promotion/Rollback Preview | 401 | 200 | 200 |
| CSV 검수 실행, 비동기 검수 실행, Web ETL 실행, Promotion 실행, Rollback 실행 | 401 | 403 | 200 |

Promotion Preview·Rollback Preview는 DB를 변경하지 않고 "무엇이 바뀔지"만 보여주므로 viewer에게도 허용했고, 실제 반영·되돌리기만 operator로 제한해 조회와 실행의 경계를 분명히 했습니다.

### 인증 설계

- **User model**: `id`, `username`(unique), `password_hash`, `role`, `is_active`, `created_at`만 저장합니다. email·전화번호·마지막 로그인 시각·OAuth provider처럼 이번 MVP에 필요하지 않은 필드는 넣지 않았습니다.
- **비밀번호**: bcrypt로 hash만 저장합니다. hash는 복호화하는 방식이 아니라, 로그인할 때마다 같은 알고리즘으로 재계산해 저장된 hash와 비교하는 단방향 함수입니다.
- **JWT**: PyJWT, `HS256` 서버 고정, payload는 `sub`(username)·`role`·`iat`·`exp`만 포함합니다. secret은 `CATALOGGUARD_JWT_SECRET` 환경변수로 관리하며 기본값을 두지 않아, 값이 없으면 로그인·토큰 검증이 fail-fast로 실패합니다. `/health`, `/ready`, CLI ETL, Alembic migration은 이 값을 요구하지 않도록 설정 로딩 시점을 분리했습니다.
- **current user 조회**: `get_current_user()`는 토큰의 role을 그대로 신뢰하지 않고 매 요청마다 `sub`로 PostgreSQL `users`를 다시 조회해 최신 role·is_active를 확인합니다. 이미 발급된 토큰이 있어도 계정을 비활성화하면 다음 요청부터 즉시 차단됩니다.
- **401/403**: 401은 로그인되지 않았거나 토큰이 없거나 무효/만료됐거나 계정이 비활성인 경우, 403은 로그인은 됐지만 role이 부족한 경우입니다. 로그인 실패는 아이디 없음/비밀번호 오류/비활성 계정을 모두 같은 `invalid_credentials` 메시지로 응답해 계정 존재 여부를 노출하지 않습니다.
- **초기 계정 생성**: 회원가입 API는 만들지 않았습니다. `scripts/create_user.py` bootstrap CLI로만 계정을 만들며, 비밀번호는 인자·환경변수·대화형 prompt 중 하나로 받고 코드에 하드코딩하지 않습니다.

### Streamlit 연동

`ui/auth.py`가 사이드바 로그인·로그아웃 폼과 `session_state` 기반 Access Token 저장을 담당합니다. `CatalogGuardApiClient`는 로그인 성공 시 `Authorization: Bearer` 헤더를 세션에 한 번 설정해 이후 모든 요청에 자동으로 붙입니다. 로그인 전에는 어떤 탭도 렌더링하지 않고, viewer로 로그인하면 ETL 실행·Promotion·Rollback 버튼이 비활성화됩니다. 다만 이 비활성화는 편의 기능일 뿐이고, 실제 권한 검사는 항상 FastAPI가 수행합니다 — viewer가 API를 직접 호출해도 403으로 차단됩니다.

### 검증

`get_current_user()`, `require_viewer`/`require_operator` dependency, 로그인/현재 사용자 API, Streamlit 로그인 UI를 각각 단위 테스트로 검증한 뒤, 실제 PostgreSQL 사용자·JWT로 401/403/성공 경계 전체를 `tests/test_api_rbac.py`로 검증했습니다. 기존 Async Inspection E2E와 Chromium Browser E2E(Promotion, ETL reject 시나리오)에는 synthetic operator 계정 생성과 로그인 단계를 추가해 Auth 도입 후에도 기존 흐름이 그대로 성공하는지 확인했습니다. AWS Docker runtime에서는 build·import·migration·Uvicorn·`/health`가 정상 동작하는지 확인했습니다. 이 과정에서 인증 dependency가 route와 Session을 공유해 쓰기 트랜잭션과 충돌하는 문제와, 그 조사 중 발견한 이미 존재하던 sync inspection의 별도 transaction 결함을 함께 해결했습니다(6.13 "SQLAlchemy autobegin과 sync inspection transaction 충돌" 참고).

### 현재 한계

Refresh Token 없음(만료 시 재로그인), 회원가입/password reset/OAuth/MFA/SSO 없음, 로그인 rate limit 없음. 이번 기능은 "누가 실행할 수 있는지"만 통제하며, "누가 실행했는지"를 기록하는 Actor Audit은 6.19절에서 별도로 다룹니다. 모두 이번 MVP에서 의도적으로 제외한 범위입니다.

## 6.19 Actor Audit

이 절은 Actor Audit을 Web ETL·Promotion·Rollback에 처음 도입한 단계의 설계와 검증을 기록합니다. 이후 Sync·Async Inspection으로 확장한 결과는 6.23절에서 별도로 다룹니다.

### 문제 정의

RBAC로 "누가 실행할 수 있는지"는 통제할 수 있었지만, 실제로 Web ETL·Promotion·Rollback을 누가 실행했는지는 실행 이력 어디에도 남지 않았습니다.

```text
기존: 운영 작업을 실행할 권한은 RBAC로 제어 가능
문제: 실제로 어느 사용자가 실행했는지는 기록되지 않음
개선: JWT current_user를 기준으로 Web ETL/Promotion/Rollback 실행자를 기록
```

### 설계 결정

새로운 범용 Audit 테이블을 만드는 대신 기존 `ETLLoadRun`·`CatalogPromotionRun`·`CatalogPromotionRollback` 실행 이력에 `actor_user_id`·`actor_username` 컬럼만 추가했습니다.

- 기존 History 조회 API·Streamlit 화면 구조를 그대로 재사용할 수 있습니다.
- 별도 Audit 테이블과 새 JOIN, 범용 audit framework를 만들지 않아 복잡도가 늘지 않습니다.
- 이 최초 단계에서는 검수(Inspection)를 제외하고 변경 범위를 Web ETL·Promotion·Rollback 3곳으로 한정했습니다. 이후 Sync·Async Inspection 확장은 6.23절에서 다룹니다.

### 보안 설계

actor 값을 클라이언트가 보내는 값이 아니라 서버가 인증한 사용자에서만 가져오는 것이 핵심입니다.

```text
잘못된 방식: 클라이언트 -> actor_username 전송
현재 방식:   JWT -> FastAPI current_user -> actor 기록
```

`api/routes/etl_loads.py`는 `require_operator`로 인증을 통과한 `current_user.id`·`current_user.username`만 `actor_user_id`·`actor_username`으로 전달합니다. `api/schemas.py`의 요청 모델(`CatalogPromotionRequest`, `CatalogPromotionRollbackRequest` 등)에는 actor를 지정하는 필드 자체가 없으므로, 클라이언트가 `actor_username` 같은 값을 함께 보내도 서버가 받는 필드가 없어 무시됩니다. `tests/test_actor_audit.py`의 `test_actor_cannot_be_forged_via_request_body`는 실제로 `actor_username="someone_else"`를 함께 보내도 저장된 값은 요청 토큰의 실제 사용자 이름과 같은지를 실제 PostgreSQL로 확인합니다.

### Migration 호환성

이 migration 실행 이전에 만들어진 row는 실행한 사용자를 알 방법이 없습니다. 그렇다고 특정 사용자(예: 첫 번째 관리자 계정)로 임의 backfill하면 실제로 그 사람이 실행하지 않은 작업까지 실행한 것으로 잘못 기록하게 됩니다. 그래서 `actor_user_id`·`actor_username` 모두 `NULL`로 남기는 쪽을 선택했습니다.

```text
DB: actor_user_id = NULL, actor_username = NULL
UI: "알 수 없음"
```

DB에는 실제 값이 없다는 사실(`NULL`)을 그대로 저장하고, 사용자에게 보여줄 때만 `ui/etl_load_history.py`의 `format_actor_username()`이 `NULL`을 "알 수 없음" 문구로 바꿉니다. DB 저장값과 화면 표시 문구의 책임을 분리해, 나중에 다른 화면(API 소비자 등)에서 `NULL`을 다르게 표시하고 싶어도 DB 값 자체는 건드리지 않아도 됩니다.

### Transaction 설계

Actor Audit을 위해 새 transaction 구조를 만들지 않았습니다. `actor_user_id`·`actor_username`은 각 실행이 원래 만들던 row(`ETLLoadRun`, `CatalogPromotionRun`, `CatalogPromotionRollback`)에 다른 컬럼과 함께 같은 insert/update 문으로 저장되며, 별도 후속 쓰기나 두 번째 commit이 필요하지 않습니다. Promotion·Rollback이 실패해 `failed` run을 남기는 기존 설계도 그대로 유지하면서 그 `failed` run에도 actor를 함께 기록하도록 인자만 추가했습니다. `tests/test_actor_audit.py`의 `test_promotion_failure_records_failed_status_not_false_success`는 저장 도중 강제로 예외를 발생시켜도 `catalog_promotion_runs`에 `failed` row 1건과 정확한 actor가 남고, 운영 상품(`catalog_products`)은 생성되지 않는지 확인합니다. Actor Audit 작업 중 Sync Inspection transaction 구조와 `workers/inspection_tasks.py`는 수정하지 않았습니다.

### 테스트 전략

`tests/test_actor_audit.py`는 monkeypatch로 대체하지 않고 실제 PostgreSQL과 실제 JWT를 사용하는 10개 통합 테스트입니다.

- JWT actor 기록: 응답 값뿐 아니라 새 Session으로 재조회해 실제 commit된 `actor_user_id`·`actor_username`을 확인합니다.
- viewer(403, 세 endpoint 모두)·Web ETL anonymous(401): 요청이 차단되고 실행 이력 row 자체가 생성되지 않는지 확인합니다.
- actor 위조 방지: request body에 다른 사용자 이름을 함께 보내도 무시되는지 확인합니다.
- legacy row 호환: actor 컬럼이 `NULL`인 row도 조회 API가 예외 없이 반환하는지 확인합니다.
- Promotion 실패 기록: 저장 도중 강제 실패에도 `failed` run에 actor가 정확히 남고 운영 상품은 생성되지 않는지(false success 방지) 확인합니다.

단순히 "테스트 10개를 추가했다"는 숫자보다, 이 테스트들이 "actor가 위조될 수 없다"와 "권한 없는 요청은 이력조차 남기지 않는다"는 보안 속성을 실제 PostgreSQL commit 결과로 증명한다는 점이 중요합니다.

## 6.20 Prometheus Observability

### 기존 상태

Actor Audit까지 구현한 시점에 이미 다음이 있었습니다.

```text
Request ID
구조화 로그(요청 완료/실패 이벤트)
/health, /ready
```

개별 요청의 상세 기록과 서비스 생존 여부는 확인할 수 있었습니다.

### 문제

로그와 health check만으로는 다음을 숫자로 답할 수 없었습니다.

```text
요청이 얼마나 들어오는가?
응답 시간은 어느 정도인가?
4xx/5xx가 얼마나 발생하는가?
Web ETL 신규/중복/실패가 얼마나 발생하는가?
```

로그를 하나씩 세어 집계하는 것은 운영 관측 방법이 아니므로, 요청·응답 시간·ETL 실행 결과를 누적 집계하는 계층이 필요했습니다.

### 설계 선택

새 timing middleware를 추가하지 않고 기존 `log_http_request` middleware가 이미 계산하던 duration을 그대로 재사용해 로그와 Prometheus metric 양쪽에 씁니다.

```text
기존 FastAPI request middleware
-> duration 1회 계산
-> 구조화 로그 기록
-> Prometheus Counter/Histogram 기록(같은 duration 값 재사용)
```

Web ETL은 `run_web_etl()`이 성공하거나 특정 예외로 실패를 반환한 뒤, route(`api/routes/etl_loads.py`)에서 metric을 기록합니다.

```text
Web ETL Service(run_pipeline -> load_standard_csv, transaction 확정)
-> route가 결과(성공/특정 예외) 수신
-> created/duplicate/failed metric 기록
```

`etl/web_service.py`·`etl/db_loader.py`의 transaction 소유 구조는 전혀 건드리지 않았습니다. metric 증가와 DB commit 성공 여부가 어긋나는(metric은 증가했는데 실제 DB 반영은 실패한) 상태를 피하기 위해서입니다. 다만 이는 완전한 distributed transaction이 아니라, "결과가 확정된 뒤에만 기록한다"는 순서 보장일 뿐입니다.

### Cardinality 문제

단순히 Prometheus를 붙이는 것보다 중요했던 설계 결정입니다. 실제 요청 경로를 label로 그대로 쓰면 다음처럼 ID마다 새 time series가 생겨 Prometheus 메모리와 조회 비용이 계속 늘어납니다.

```text
잘못된 방법: route="/api/v1/catalog-promotions/1", route="/api/v1/catalog-promotions/2", ...
현재 방법:   route="/api/v1/catalog-promotions/{promotion_run_id}"
```

`request.scope["route"]`는 Starlette가 라우팅을 마친 뒤(`call_next()` 반환 후) 채워지므로, 이 값의 `.path`(route template)를 label로 사용합니다. 매칭되는 route가 없는 404(예: 존재하지 않는 임의 경로)는 원본 경로 대신 고정 label `unmatched`를 씁니다. `/api/v1/catalog-promotions/1`과 `/api/v1/catalog-promotions/999`를 실제로 요청해 두 요청이 하나의 route template label로 집계되고 원본 경로가 별도 label로 남지 않는지 직접 확인했습니다. 기능을 추가하면서 운영 비용과 metric cardinality까지 함께 고려한 결정입니다.

### Web ETL 중복 집계 방지

CatalogGuard는 이미 동일 CSV 재요청을 기존 배치 재사용(`created=False`)으로 처리합니다. Observability를 붙이면서 이 기존 동작과 metric을 맞춰야 했습니다.

```text
첫 번째 요청 -> 새 ETLLoadRun -> runs_total{outcome="created"} +1 -> rows_total에 실제 행 수 반영
두 번째 동일 요청 -> 기존 배치 재사용 -> runs_total{outcome="duplicate"} +1 -> rows_total은 증가하지 않음
```

`record_web_etl_rows()`는 `outcome.created is True`일 때만 호출합니다. 그렇지 않으면 같은 ETL 결과(같은 `loaded_rows`/`rejected_rows`)가 재요청마다 Prometheus counter에 반복 합산되는 오류가 생깁니다.

### 보안과 Actor Audit·DB History와의 구분

metric label은 `method`, `route`(template 또는 `unmatched`), `status_class`, `outcome`, `result` 5종의 작은 고정 범주만 사용합니다. 사용자명, `actor_username`, `request_id`, JWT, `Authorization` 헤더, 실제 run ID, 상품 ID, 파일명, CSV 내용, `DATABASE_URL`은 label에도 metric 출력에도 넣지 않았습니다. 이 결정은 민감정보 노출 방지와 high-cardinality 방지라는 두 이유를 모두 가집니다. `tests/test_metrics.py::test_metrics_body_never_contains_pii_or_dynamic_ids`가 `/metrics` 응답 본문에 사용자명·요청 ID·동적 ID가 실제로 없는지 확인합니다.

세 개념을 분리해서 문서화했습니다.

```text
DB History          = 재시작 후에도 유지되는 영구 실행 기록
Actor Audit         = DB 실행 이력에 누가 작업했는지 기록
Prometheus Metrics  = 현재 실행 중인 프로세스의 운영 지표(재시작 시 초기화)
```

Web ETL이 실패하면 `ETLLoadRun` row 자체가 생성되지 않아 Actor Audit 기록은 없지만(6.18·6.19절 참고), Prometheus는 API 실행 시도 자체를 세므로 `catalogguard_web_etl_runs_total{outcome="failed"}`는 증가할 수 있습니다. 이 둘을 같은 개념으로 섞어 쓰지 않았습니다.

### 테스트 전략

`tests/test_metrics.py`는 32개 시나리오입니다. 단순히 metric 이름 문자열이 존재하는지 확인하는 수준이 아니라, 실제 HTTP 요청 전후 값의 차이(delta)로 검증합니다. Prometheus counter는 프로세스 전역 상태라 테스트 실행 순서에 따라 절대값이 달라질 수 있으므로 `counter == 1` 같은 취약한 assertion 대신 before/after delta만 사용했고, 앱 기본 `REGISTRY` 대신 `config/metrics.py` 전용 `CollectorRegistry`를 써서 다른 라이브러리의 collector와 섞이지 않게 했습니다.

- `CATALOGGUARD_METRICS_ENABLED`의 true/false 계열 값 parsing과 미설정 시 기본 비활성.
- `/metrics` 비활성 시 404, 그리고 비활성 상태에서는 `record_http_request()` 등이 실제로 counter를 증가시키지 않는지(no-op)까지 확인.
- HTTP request counter·duration histogram이 실제 요청 후 증가하는지, `method`/`route`/`status_class` label이 정확한지.
- 동적 ID route가 template 하나로 집계되고 원본 경로가 label로 남지 않는지, 매칭되지 않는 경로는 `unmatched`로만 집계되는지.
- `/health`·`/ready`·`/metrics` 요청이 HTTP metric 집계에서 제외되는지.
- unhandled exception이 기존 안전한 500 응답·요청 ID·구조화 로그를 그대로 유지하면서 `5xx` metric도 증가시키는지.
- `/metrics` 응답 본문에 사용자명·요청 ID·동적 ID가 없는지.
- Web ETL의 created/duplicate/failed 각 outcome과, `duplicate`·`failed`에서 row counter가 증가하지 않는지.
- 실제 PostgreSQL로 로그인 후 같은 CSV를 두 번 요청해 신규 1회·중복 1회·행 수가 정확히 한 번만 반영되는지(마지막 시나리오).

### 현재 한계

현재 구현은 애플리케이션이 Prometheus가 읽어갈 수 있는 형식으로 값을 노출하는 instrumentation MVP입니다. Prometheus 서버가 주기적으로 scrape하는 운영 환경, Grafana 대시보드, Alertmanager는 구축하지 않았습니다. metric registry가 프로세스 하나 안에서만 유지되므로 여러 Uvicorn worker를 띄우는 환경에서는 worker별로 값이 나뉘며, 이번 MVP는 이를 통합하지 않습니다("multi-worker 완벽 지원"이 아닙니다). Async Inspection/Celery, Redis queue depth, Promotion·Rollback 실행, Actor Audit, DB connection pool 관련 domain metric도 아직 없습니다. Prometheus metric은 DB 실행 이력처럼 영구 저장되지 않으며, 프로세스가 재시작되면 초기화됩니다.

## 6.21 Kubernetes Deployment Readiness

### 기존 상태

`Dockerfile.aws`와 GitHub Actions AWS Runtime smoke, `/health`·`/ready`까지는 이미 구현·검증되어 있었습니다. 즉 "Docker container가 정상 실행되는가"는 확인했지만, "실제 Kubernetes cluster에 배포할 수 있는가"는 검증하지 않은 상태였습니다.

### 문제

두 가지 문제를 중심으로 작업했습니다.

**문제 1 — migration과 API 실행이 결합**

```text
Dockerfile.aws CMD
= alembic upgrade head && uvicorn ...
```

Kubernetes는 API Pod가 여러 개(replica)일 수 있습니다. 이 CMD를 그대로 쓰면 각 Pod가 시작할 때마다 migration을 실행하게 되어, replica를 늘리는 순간 여러 Pod가 동시에 같은 migration을 실행할 수 있는 구조가 됩니다.

**문제 2 — "Running"과 "요청을 받을 준비"는 다름**

Pod 상태가 `Running`인 것만으로는 실제로 요청을 처리할 수 있는 상태인지 알 수 없습니다. 프로세스 자체는 떠 있어도 PostgreSQL에 아직 연결하지 못했을 수 있습니다.

### 설계 판단

**문제 1 해결**: 새 Kubernetes 전용 Dockerfile을 만들지 않고 기존 `Dockerfile.aws` image를 그대로 재사용했습니다. 대신 Kubernetes manifest의 `command`로 역할을 분리했습니다.

```text
k8s/migration-job.yaml (Job)
-> command override: python -m alembic upgrade head만 실행

k8s/catalogguard-api.yaml (Deployment)
-> command override: uvicorn만 실행
```

`Dockerfile.aws`의 CMD 자체는 수정하지 않았습니다. Docker/AWS Runtime과 Kubernetes가 같은 image를 공유하면서도, "migration 책임"과 "API 실행 책임"만 manifest 수준에서 분리한 것입니다. 이 분리가 모든 분산 migration race condition을 완벽히 해결한다고 보지는 않습니다 — Job이 `backoffLimit: 2`로 1회 실행되고 API Deployment가 그 뒤에 배포되는 순서를 보장하는 수준의, CI/kind MVP 범위의 책임 분리입니다.

**문제 2 해결**: 기존 `/health`·`/ready`의 의미 차이를 그대로 Kubernetes probe에 연결했습니다.

```text
GET /health = FastAPI 프로세스 생존 여부만 확인(PostgreSQL 미확인)
           -> livenessProbe

GET /ready  = FastAPI 실행 중 + PostgreSQL 연결(SELECT 1) 확인
           -> readinessProbe
```

`/health`를 readiness에 쓰면 DB 장애 때는 애초에 그 사실을 Kubernetes가 알 수 없고, `/ready`를 liveness에 쓰면 DB가 잠깐 끊겼다는 이유만으로 정상적인 FastAPI 프로세스까지 계속 재시작당할 수 있습니다. 두 endpoint의 Python 로직은 이번 작업에서 변경하지 않았습니다. `catalogguard-api` `Service`(ClusterIP `:8000`)로 Pod를 Kubernetes 내부에 노출했습니다.

### 실제 Kubernetes 검증

manifest 작성에서 끝내지 않고 GitHub Actions에 `kubernetes-smoke` job을 추가해 실제 kind cluster에서 검증했습니다.

```text
Dockerfile.aws image build
-> kind cluster 생성(node image SHA-256 digest 고정)
-> kind load docker-image
-> catalogguard namespace 생성
-> kubectl create secret generic으로 CI 런타임 Secret 생성
-> PostgreSQL Deployment 배포 + rollout 대기
-> Alembic Migration Job 실행 + condition=complete 대기
-> FastAPI Deployment 배포 + rollout 대기
-> Service port-forward로 GET /health, GET /ready 확인
-> 실패 시 kubectl get/describe/logs 진단(Secret 값 미출력)
-> kind cluster 삭제
```

Kubernetes 기능 검증 commit(`c5c84d17`)의 GitHub Actions run `31156108895`에서 실제로 확인한 결과입니다.

```text
kind v0.32.0, kubectl client v1.36.2, node kindest/node:v1.36.1
deployment "postgres" successfully rolled out
job.batch/catalogguard-migrate condition met
deployment "catalogguard-api" successfully rolled out
GET /health -> {"status":"ok","service":"catalogguard-lite-api"}
GET /ready  -> {"status":"ready","service":"catalogguard-lite-api","database":"ok"}
```

같은 Run에서 기존 `test`(pytest `1309 passed`, AWS Runtime, Async Inspection E2E, Streamlit smoke 포함)·`browser-e2e` job도 모두 성공해, 이번 작업이 기존 API·DB·Celery·Browser E2E·AWS Runtime 검증을 깨뜨리지 않았음을 같은 Run에서 함께 확인했습니다.

### CI 재현성 — toolchain 버전 고정

처음에는 kind를 GitHub API의 `releases/latest`, kubectl을 Kubernetes 공식 `stable.txt`로 실행 시점마다 동적 조회했습니다. 이 방식은 당장은 동작하지만, 나중에 새 kind/Kubernetes 버전이 나오면 저장소 코드 변경 없이 CI 결과가 달라질 수 있다는 문제가 있었습니다. Docker/AWS Runtime에서도 재현성을 중요하게 다뤄 온 프로젝트 방향에 맞춰, Kubernetes toolchain도 다음처럼 고정했습니다.

```text
KIND_VERSION=v0.32.0
KIND_NODE_IMAGE=kindest/node:v1.36.1@sha256:3489c7674813ba5d8b1a9977baea8a6e553784dab7b84759d1014dbd78f7ebd5
KUBECTL_VERSION=v1.36.2
```

node image는 tag뿐 아니라 SHA-256 digest까지 고정했습니다. kubectl 바이너리는 공식 `kubectl.sha256`으로 checksum까지 검증합니다. 같은 commit이 미래의 최신 버전 변경과 무관하게 항상 같은 Kubernetes toolchain에서 재현되도록 하는 것이 목적입니다.

### 보안

```text
Secret YAML 미commit
-> GitHub Actions 실행마다 openssl rand로 disposable 값 생성
-> kubectl create secret generic catalogguard-secrets
-> manifest는 secretKeyRef(name+key)만 참조, 실제 값 없음
```

API·Migration container 모두 기존 Dockerfile의 UID와 동일한 `runAsNonRoot: true`, `runAsUser/Group: 10001`, `allowPrivilegeEscalation: false`로 실행됩니다. 실패 진단 단계는 `kubectl get/describe/logs`만 사용하고 `kubectl get secret -o yaml`처럼 Secret 값이 노출될 수 있는 명령은 포함하지 않았습니다. External Secrets, Vault, Sealed Secrets, NetworkPolicy, Pod Security Admission 전체 구성은 구현하지 않았습니다.

### 테스트 전략

Kubernetes 작업의 핵심 검증은 Python unit test 추가가 아니라 실제 배포 smoke입니다. YAML 문법(pyyaml parse)과 workflow shell 문법(`bash -n`, 실제 commit될 LF blob 기준)을 로컬에서 정적으로 확인한 뒤, 실제 검증은 GitHub Actions의 `kubernetes-smoke` job이 실제 kind cluster·실제 PostgreSQL·실제 Alembic migration·실제 FastAPI container·실제 Service HTTP 요청으로 수행합니다. YAML 문자열을 Python에서 검색하는 형태의 테스트를 대량으로 추가하지 않았습니다.

### 현재 한계

kind 기반 CI/local smoke 검증까지이며 실제 EKS/GKE/AKS 등 production 클러스터에는 배포하지 않았습니다. Kubernetes에는 FastAPI·PostgreSQL만 배포했고 Redis/Celery Async Inspection과 Streamlit은 배포하지 않았습니다. Service는 ClusterIP만 사용하며 Ingress·TLS는 없고, `replicas: 1` 고정으로 HorizontalPodAutoscaler·PodDisruptionBudget도 없습니다. dev PostgreSQL은 PersistentVolume이 없는 CI 전용 disposable 구성이라 cluster 삭제 시 데이터가 함께 사라지며, NetworkPolicy와 세분화된 ServiceAccount도 없습니다. manifest의 resource requests/limits는 CI/개발용 초기값이며 실측 production sizing이 아닙니다.

## 6.22 Terraform AWS Staging IaC Validation

### 문제

AWS staging(EC2 + RDS PostgreSQL)은 2026-07-19에 AWS 콘솔에서 직접 클릭해 만들고 검증했습니다. 동작은 확인했지만, 그 구성은 [AWS staging 배포 런북](aws-staging-deployment.md)의 문장으로만 남아 있었습니다. 즉 같은 구조를 다시 만들려면 사람이 문서를 읽고 다시 클릭해야 하고, "RDS Public access는 No였는가", "SSH 22번이 열려 있지는 않은가" 같은 보안 조건도 사람이 매번 눈으로 확인해야 하는 상태였습니다. 설정 항목이 하나 빠지거나 순서가 달라져도 CI가 알려 주지 못합니다.

### 판단 — 범위를 어디까지 할 것인가

이미 EC2·RDS 수동 배포와 kind 기반 Kubernetes 배포까지 검증한 상태였기 때문에, 여기서 새 대규모 인프라(custom VPC, private subnet, EKS)를 Terraform으로 만드는 방향도 선택지에 있었습니다. 그렇게 하지 않은 이유는 두 가지입니다.

- 실제로 검증한 적 없는 구조를 코드로 먼저 만들면, 그 코드가 맞다는 근거가 문서에도 CI에도 남지 않습니다.
- 개인 프로젝트에서 실제 `apply`를 반복하면 AWS 비용과 삭제 누락 위험이 계속 발생합니다.

그래서 범위를 "이미 수동으로 검증한 staging 구성을 그대로 코드로 옮기고, 그 코드의 보안 조건을 자동 검증하는 것"까지로 제한했습니다. 실제 `apply`·`destroy`·기존 리소스 `import`는 이번 범위에서 의도적으로 제외했습니다. 새 인프라를 만드는 작업이 아니라, 이미 있는 것을 재현 가능하고 검증 가능한 형태로 바꾸는 작업으로 정의한 것입니다.

### 구현

기존 런북에 기록된 실제 구성을 그대로 따라 `terraform/`을 작성했습니다. Default VPC와 subnet은 새로 만들지 않고 `data`로 조회해, 수동 구성과 같은 네트워크 위에 올라가도록 했습니다.

```text
data     : aws_vpc.default, aws_subnets.default,
           aws_ami.amazon_linux_2023, aws_iam_policy_document.ec2_assume_role
resource : aws_security_group.ec2, aws_security_group.rds,
           aws_iam_role.ec2_ssm, aws_iam_role_policy_attachment.ec2_ssm_core,
           aws_iam_instance_profile.ec2_ssm, aws_instance.api,
           aws_db_subnet_group.staging, aws_db_instance.staging
```

보안 관련 결정은 다음과 같습니다.

- **EC2 Security Group에 `ingress` 블록을 아예 두지 않았습니다.** 수동 구성에서도 22·80·443·8000 모두 inbound 규칙이 없었고, 접근은 SSM Session Manager로만 했습니다. "22번을 특정 IP에만 여는" 절충안을 쓰지 않고 규칙 자체를 만들지 않는 쪽을 택했습니다.
- **RDS는 `5432` 하나만, 그것도 CIDR이 아니라 EC2 Security Group 참조로 허용했습니다**(`cidr_blocks = []`). IP 대역이 바뀌어도 규칙을 고칠 필요가 없고, 실수로 넓은 대역을 넣을 여지도 줄어듭니다.
- **`publicly_accessible = false`는 변수로 노출하지 않고 코드에 고정했습니다.** 변수로 만들면 언젠가 `true`가 들어올 수 있는 값이 되기 때문입니다.
- **DB 비밀번호는 `default` 없이 `sensitive = true`로 두었습니다.** 기본값을 주면 그 값이 저장소에 남고, 아무도 값을 주입하지 않아도 조용히 실행됩니다. 기본값을 없애면 값을 주입하지 않았을 때 Terraform이 먼저 실패합니다.
- **SSM 접근은 IAM Role + `AmazonSSMManagedInstanceCore` 관리형 정책 1개 + Instance Profile로만 구성하고, `key_name`을 지정하지 않았습니다.** SSH key pair가 아예 만들어지지 않으므로 키 관리 문제 자체가 사라집니다.
- **`output`에는 EC2 instance ID, Security Group ID 2개, RDS 식별자만 남겼습니다.** RDS endpoint와 비밀번호는 출력하지 않아, 저장소 문서와 같은 원칙(실제 endpoint·비밀번호 미기록)을 코드에서도 유지했습니다.

Terraform CLI는 `~> 1.15.0`, AWS provider는 `~> 6.55.0`으로 제한하고 `.terraform.lock.hcl`을 commit해 실제 선택 버전(`6.55.0`)까지 고정했습니다. `apply`를 하지 않으므로 backend는 구성하지 않았습니다. `.gitignore`에는 `.terraform/`, `*.tfstate*`, `*.tfplan`, `terraform.tfvars`, `override.tf` 계열을 추가하고, 버전 고정 역할을 하는 lock 파일만 commit 대상으로 남겼습니다.

IMDSv2 강제(`http_tokens = "required"`)와 루트 볼륨 암호화는 수동 구성에는 없던 값이지만 코드화 시 표준 보안 기본값으로 추가했고, apply하지 않았으므로 실제 인스턴스에는 아직 반영되지 않았다는 점을 코드 주석과 README에 함께 남겼습니다.

### 테스트의 의미 — "작성했다"가 아니라 "깨지면 CI가 막는다"

`terraform validate`는 문법과 타입만 확인합니다. "RDS가 인터넷에 열려 있는지"는 알려 주지 않습니다. 그래서 `terraform/tests/staging.tftest.hcl`에 `mock_provider "aws" {}`와 `override_data` 4개를 두고, 실제 AWS 자격 증명·리소스 없이 계산된 설정값만으로 보안 조건을 검증하도록 했습니다. `run` 블록은 2개이고 assertion은 모두 12개입니다.

| run 블록 | assertion | 검증 내용 |
|---|---:|---|
| `plan_staging_infrastructure` | 9 | EC2 inbound 규칙 0개, RDS ingress 정확히 1개, 그 규칙이 `5432`·CIDR 0개·Security Group 1개인지, RDS `publicly_accessible=false`·Single-AZ·`storage_encrypted=true`·`skip_final_snapshot=false`, EC2의 SSM instance profile 사용과 `AmazonSSMManagedInstanceCore` 정책 연결 |
| `no_open_internet_ingress` | 3 | `publicly_accessible`이 계속 `false`로 고정되어 있는지, EC2·RDS Security Group 어느 쪽에도 `0.0.0.0/0` inbound가 없는지 |

두 번째 run 블록의 목적은 현재 상태 확인이 아니라 **회귀 방지**입니다. 나중에 누군가 "잠깐 디버깅용으로" SSH `22`를 `0.0.0.0/0`으로 여는 `ingress` 블록을 추가하면 이 assertion이 실패하고, `main` push나 pull request 단계에서 CI가 막습니다. 사람이 리뷰에서 놓쳐도 자동으로 걸리는 지점을 하나 만들어 둔 것입니다.

mock provider의 한계도 그대로 인정했습니다. mock provider는 코드에서 설정하지 않은 속성에도 임의 값을 채우기 때문에, "`key_name`을 지정하지 않았다"는 사실은 test로 검증할 수 없습니다. 이 부분은 test에서 억지로 확인하는 대신 코드 리뷰로 확인한다고 test 파일 주석에 남겼습니다.

### 검증

`.github/workflows/test.yml`에 네 번째 job `terraform-validate`를 추가했습니다. Terraform 버전은 kind/kubectl과 같은 방식으로 `TERRAFORM_VERSION: "1.15.8"`에 고정했고, AWS 자격 증명은 사용하지 않습니다.

```text
hashicorp/setup-terraform (1.15.8 고정, terraform_wrapper: false)
-> terraform fmt -check -recursive
-> terraform init -backend=false -input=false -lockfile=readonly
-> terraform validate
-> terraform test (mock provider)
```

`-backend=false`로 remote state를 만들지 않고, `-lockfile=readonly`로 CI가 lock 파일의 provider 버전을 임의로 갱신하지 못하게 했습니다. commit `38385f0`의 GitHub Actions run `31160915277`에서 확인한 결과입니다.

```text
Installed hashicorp/aws v6.55.0 (signed by HashiCorp)
terraform validate -> Success! The configuration is valid.
run "plan_staging_infrastructure"... pass
run "no_open_internet_ingress"... pass
terraform test -> Success! 2 passed, 0 failed.
```

같은 run에서 기존 `test`(pytest `1309 passed`, `4 deselected`, `0 failed`)·`browser-e2e`·`kubernetes-smoke` job도 모두 성공해, IaC 추가가 기존 API·DB·Celery·Browser E2E·Kubernetes 검증을 깨뜨리지 않았음을 같은 Run에서 함께 확인했습니다. 이번 작업은 Python 코드를 변경하지 않았으므로 pytest 수치는 직전 commit과 동일합니다.

### 현재 한계

이번 범위는 코드화와 정적·mock 검증까지입니다. 실제 `terraform apply`·`destroy`를 실행하지 않았으므로 이 코드로 만들어진 AWS 리소스는 없고, 2026-07-19에 콘솔로 만든 기존 EC2·RDS도 `import`하지 않아 Terraform state와 실제 AWS 상태가 연결되어 있지 않습니다. backend를 구성하지 않았으므로 S3 remote state와 state locking도 없습니다. 기존 Default VPC·subnet을 조회해 쓰므로 custom VPC와 private subnet 기반 네트워크 구성은 코드에 없으며, Kubernetes/EKS 리소스와 production(Railway) 환경도 Terraform으로 관리하지 않습니다. mock provider 기반 test는 계산된 설정값만 검증하므로 실제 AWS API 응답, 계정 quota, IAM 권한 부족 같은 문제는 확인할 수 없습니다.

이 한계는 숨겨야 할 결함이라기보다, 비용과 검증 근거를 함께 고려해 MVP 범위를 의도적으로 제한한 결과입니다. 다음 단계로는 remote state·locking 구성과 기존 리소스 import 후 실제 `apply` 기반 재현이 자연스럽게 이어집니다.

## 6.23 Inspection Actor Audit 확장

### 문제와 범위

6.19절의 최초 Actor Audit은 Web ETL·Promotion·Rollback만 다뤘기 때문에 Sync·Async Inspection 실행 이력에는 실행자가 남지 않았습니다. 이번 확장은 기존 검수 흐름과 dedup 계약을 유지하면서 `inspection_runs`에도 인증된 실행자를 기록하고, API·Streamlit 이력·요약 CSV에서 확인할 수 있게 하는 데 범위를 한정했습니다.

### 설계

- `inspection_runs`에 nullable `actor_user_id`와 `actor_username`을 추가했습니다. `actor_user_id`는 `users.id`를 참조하고 사용자 삭제 시 `ON DELETE SET NULL`이 적용되며, `actor_username` snapshot은 당시 실행자를 보존합니다. 기존 row는 사실과 다른 사용자를 임의로 채우지 않고 `NULL`로 둡니다.
- actor의 출처는 Sync·Async 모두 인증된 JWT의 `current_user`입니다. 요청 form의 동명 필드는 신뢰하지 않으며, 위조 값을 보내도 저장에 사용하지 않습니다.
- Sync 경로는 actor scalar를 저장 함수에 직접 전달합니다. Async 경로는 ORM 객체나 JWT 전체가 아니라 `actor_user_id`·`actor_username` scalar만 Redis job state와 Celery worker 경계를 통과시키며, 기존 payload에는 두 필드가 없어도 `None`으로 처리됩니다.
- 동일 CSV와 검수 버전에 대한 dedup은 기존 실행 row를 재사용하고 최초 actor를 유지합니다. 재요청자별 이벤트를 별도로 쌓는 범용 Audit Event 모델은 이번 MVP 범위가 아닙니다.
- API는 Sync 생성·목록·상세 응답에 `actor_username`만 노출하고 내부 FK인 `actor_user_id`는 노출하지 않습니다. Async job status 응답에는 actor를 추가하지 않았으며, 완료 후 Inspection 상세에서 확인합니다.
- Streamlit 실행 이력 목록·상세·요약 CSV에 실행자를 표시하고, migration 이전 row처럼 값이 없으면 `알 수 없음`으로 렌더링합니다.

### 검증

`20260810_0012_add_inspection_actor_audit.py`는 `20260808_0011`을 `down_revision`으로 갖는 single-head migration입니다. 일회성 PostgreSQL 18.4 환경에서 `upgrade -> downgrade -> re-upgrade`를 실행하고 최종 head와 Inspector 기준 컬럼·FK·nullable 계약을 확인했습니다.

Sync 통합 검증은 실제 JWT actor 저장, form 위조 무시, 동일 파일·버전 재요청 시 최초 actor 유지, 사용자 삭제 뒤 FK는 `NULL`이지만 username snapshot은 남는 동작을 실제 PostgreSQL commit 결과로 확인했습니다. Async 검증은 실제 Redis·Celery worker·FastAPI 요청을 연결해 job 완료, 단일 Inspection row 생성, actor 저장과 dedup을 확인했습니다.

이 작업 시점의 전체 검증 결과는 다음과 같습니다(Rollback Change Audit 기능 완료 commit 기준 수치는 6.5절 표를 따릅니다).

```text
1359 passed
0 failed
0 skipped
4 deselected
warnings 0
```

이 수치는 일회성 로컬 PostgreSQL·Redis 검증 환경의 결과이며 AWS나 production 환경 검증을 뜻하지 않습니다. 문서 정리 단계에서는 코드·migration·test를 변경하지 않았으므로 전체 suite를 다시 실행하지 않고 이미 완료된 위 결과를 문서에 반영했습니다.

### 현재 한계와 별도 결함

Inspection dedup은 최초 실행자만 보존하므로 같은 결과를 나중에 요청한 사용자의 시도까지 감사 이벤트로 남기지는 않습니다. 또한 Async job status 응답에는 actor가 없고 완료된 Inspection 상세에서만 확인할 수 있습니다.

`TEST_DATABASE_URL` 등 DB 설정이 없는 상태에서 anonymous Sync Inspection 요청은 기대한 `401`보다 먼저 DB 의존성 초기화가 실패해 `500 DatabaseConfigurationError`가 됩니다. DB가 구성된 환경에서는 같은 요청이 `401`을 반환합니다. 이는 기존 의존성 평가 순서에서 발생하던 결함이며 Inspection Actor Audit의 저장·전파 계약을 막는 blocker는 아니어서 이번 문서 단계에서 수정하지 않았습니다.

이번 단계에서는 AWS API를 호출하거나 SSM을 추가 조사하지 않았습니다. 따라서 별도로 기록된 SSM root cause는 계속 **K. INCONCLUSIVE**이며 해결되었다고 판단하지 않습니다.

## 6.24 ETL Profile Runtime Activation과 운영 관리

### 1. 문제

Phase 5A까지 프로필 activation은 코드 상수였습니다. 공급사 하나의 신규 ETL 실행을 잠시 멈추거나 이전 버전으로 되돌리는 데도 코드 수정 → 테스트 → 배포가 필요했고, 그 사이 문제 있는 공급사 데이터는 계속 들어왔습니다. 운영자가 판단할 수 있는 상태 변경인데 개발·배포 사이클을 거쳐야 한다는 점이 실제 병목이었습니다.

프로세스 메모리에 flag를 두는 방법은 쓰지 않았습니다. 재시작하면 사라지고 Uvicorn worker가 여러 개면 worker마다 상태가 갈라집니다. "관리 기능처럼 보이지만 관리되지 않는" 상태는 아무 상태도 없는 것보다 나쁩니다.

### 2. PostgreSQL runtime activation 설계

옮긴 것은 activation 상태 하나뿐입니다. 프로필 **정의**(`source_columns`·`required_source_columns`·`defaults`)와 버전 archive의 source of truth는 계속 `config/etl`의 버전별 JSON archive와 코드 registry이며, Policy A(Published Version Immutable)도 그대로입니다. 새 프로필을 등록하거나 삭제하지 않고 allowlist도 계속 코드 registry입니다.

`etl_profile_activations`는 `profile_id`에 unique index를 걸어 **프로필당 정확히 한 행**만 허용합니다. `profile_id`에 FK는 걸지 않았습니다. 프로필이 아직 DB entity가 아니라 코드 registry의 key이므로 존재하지 않는 대상을 가리키는 FK를 만들 수 없고, 대신 쓰기 경로가 registry allowlist와 `versions`를 검증합니다.

effective active version 계산은 `etl.profile_loader.resolve_etl_profile_activation()` **한 곳**에서만 합니다. Web·S3·HTTP feed·Airflow가 각자 DB를 읽어 각자 판단하면 같은 프로필이 경로마다 다르게 활성으로 보일 수 있기 때문입니다.

### 3. 3-state model

| runtime row | `active_version` | effective | 의미 |
|---|---|---|---|
| 없음 | — | 배포 registry의 `active_version` | runtime override 없음. 아무도 손대지 않은 상태 |
| 있음 | `"2"` | `"2"` | runtime에서 v2를 명시적으로 사용 |
| 있음 | `NULL` | `None` | 운영자의 명시적 비활성 |

"row 없음"과 "row 있음 + `NULL`"을 합치지 않은 것이 이 설계의 핵심입니다. 전자는 배포 기본값을 따르는 상태이고 후자는 사람이 내린 결정입니다. 둘을 하나로 뭉개면 배포 기본값이 바뀔 때 운영자의 결정이 조용히 뒤집히거나 조용히 되살아납니다.

비활성을 뜻하는 값은 JSON `null` 하나뿐입니다. `''`나 공백만 있는 값은 DB CHECK constraint가 막아 "비활성인가 잘못된 pointer인가"가 모호해지지 않게 했습니다. 값이 있을 때는 registry `versions`의 정확한 key여야 합니다. 임의 문자열(`"999"`)을 허용하면 존재하지 않는 버전이 활성으로 저장되고, 그 프로필의 다음 실행이 실행 시점에 가서야 실패합니다. 그 실패는 운영자가 방금 한 행동과 멀리 떨어져 있어 원인을 찾기 어렵습니다.

### 4. transaction 문제 — autobegin과 `session.begin()` 충돌

신규 ETL 실행 경로는 activation을 확인한 뒤 곧바로 쓰기 트랜잭션을 엽니다(`load_standard_csv()`의 `with session.begin()`). 그런데 확인용 SELECT가 SQLAlchemy 2.x의 autobegin으로 같은 Session에 암묵적 트랜잭션을 열어 두면, 그 `begin()`이 `A transaction is already begun on this Session.`으로 실패합니다. 6.13절의 sync inspection 충돌과 같은 계열의 문제입니다.

가장 짧은 해결은 SELECT 뒤에 무조건 `session.rollback()`을 부르는 것입니다. 그렇게 하지 않았습니다. 나중에 누군가 이 앞에 쓰기를 추가하면 그 쓰기가 **조용히** 사라지기 때문입니다. 지금까지 같은 상황은 `load_standard_csv()`의 `begin()`이 `InvalidRequestError`로 시끄럽게 실패시켜 줬는데, 무조건 rollback이 바로 그 신호를 지웁니다.

그래서 `end_activation_read_transaction()`은 rollback 전에 `session.new`·`session.dirty`·`session.deleted`를 먼저 봅니다. 보류 중인 ORM 쓰기가 있으면 조용히 버리지 않고 전용 예외로 실패시키고, 없을 때만 안전한 read 트랜잭션을 정리합니다. 한계도 그대로 적어 뒀습니다. 이 검사는 ORM 단위 작업만 보므로 `session.execute(insert(...))` 같은 Core 쓰기는 감지되지 않고 함께 rollback됩니다. 다만 그런 호출자는 이 함수 이전부터 계약상 허용되지 않았습니다.

### 5. API

| Endpoint | 권한 | 역할 |
|---|---|---|
| `GET /api/v1/etl-profiles/{profile_id}/activation` | viewer 이상 | 배포 기본값·runtime override·실제 적용 값을 함께 반환 |
| `PUT /api/v1/etl-profiles/{profile_id}/activation` | operator | 보존 버전 활성화 또는 `null`로 비활성화 |

`PUT`을 쓴 것은 이 요청이 새 자원을 만드는 것이 아니라 하나뿐인 상태를 통째로 바꾸기 때문입니다. 같은 body를 두 번 보내면 결과가 같습니다.

body에는 `active_version` 하나만 둡니다. actor는 인증된 `current_user`에서만 가져오므로 사용자 이름을 **받을 자리 자체가 없습니다.** 받아 두고 무시하면 다음 사람이 "왜 반영되지 않지"를 디버깅하게 됩니다. `extra="forbid"`로 모르는 필드를 거부해, 이 endpoint를 Profile Update API로 오해하고 `source_columns`를 보내면 조용히 무시되지 않고 `422`로 실패합니다.

응답이 세 값을 함께 돌려주는 이유는 "지금 왜 이 상태인가"에 답하기 위해서입니다. effective 하나만 주면 배포가 그렇게 정한 것인지 운영자가 내린 것인지 알 수 없고, 다음에 해야 할 일이 달라집니다. `actor_username`·`updated_at`은 runtime override가 있을 때만 채웁니다. override가 없는데 값이 있으면 아무도 바꾼 적 없는 상태를 누군가 바꾼 것처럼 보입니다.

오류는 상태별로 나눴습니다. 없는 프로필은 `404`, 프로필은 있는데 그 버전이 보존 목록에 없으면 `422`(`unknown_profile_version`)에 `available_versions`를 함께 담습니다. 운영자가 해야 할 일이 "프로필을 고쳐야 하는가"와 "버전을 고쳐야 하는가"로 다르기 때문에, service 계층에서도 두 예외를 상속으로 묶지 않았습니다.

동시에 두 operator가 같은 프로필을 바꾸면 INSERT가 unique index에서 충돌합니다. `ON CONFLICT DO UPDATE`로 한 문장에서 처리해 `IntegrityError`를 사용자에게 노출하지 않으며, 결과는 last-write-wins입니다.

### 6. Streamlit 관리 UI

`ETL 적재 이력` 탭 안에 divider로 구분된 `ETL 프로필 운영 관리` 영역을 뒀습니다. viewer는 현재 활성/비활성 상태, 실제 적용 버전, 배포 기본 버전, runtime override 여부, 선택 가능한 보존 버전, 마지막 변경 사용자와 시각을 봅니다. operator는 보존 버전 중 하나를 활성화하거나, 확인 checkbox를 거쳐 신규 ETL 실행을 비활성화합니다.

**프로필 JSON 자체를 수정하는 UI가 아닙니다.** 화면 caption에도 "프로필 정의 자체는 여기서 바꾸지 않습니다"를 명시했습니다.

실행 화면 state와 관리 화면 state는 session key로 분리했습니다(`etl_web_run_*` / `etl_profile_admin_*`). 관리 화면에서 프로필을 골랐다고 위쪽 Web ETL 실행 selector가 함께 바뀌면, 운영자가 관리 목적으로 선택한 프로필로 실수로 ETL을 실행할 수 있습니다. 반대로 activation을 **실제로 변경**했을 때는 실행 selector 목록과 프로필 상세 캐시를 명시적으로 무효화합니다. 방금 내린 프로필이 실행 목록에 남아 있으면 안 되고, 버전을 바꿨다면 상세가 옛 버전을 가리키기 때문입니다.

상태 갱신은 **서버가 성공을 응답한 뒤에만** 합니다. 서버가 실패했는데 화면만 바뀌면 운영자가 내리지 않은 프로필을 내렸다고 믿게 됩니다.

### 7. RBAC

조회(`GET`)는 DB를 바꾸지 않으므로 viewer 이상, 신규 ETL 실행 대상을 바꾸는 변경(`PUT`)만 operator입니다. Promotion Preview / Promotion 실행을 나눈 것과 같은 기준입니다. Streamlit에서 viewer에게 변경 컨트롤을 감추는 것은 편의 기능이고, 실제 경계는 항상 `require_operator`입니다.

actor는 요청 body가 아니라 인증된 `current_user`에서만 기록합니다. 요청 body의 사용자 이름을 그대로 저장하면 누구든 다른 사람 이름으로 기록을 남길 수 있습니다. 기존 Actor Audit(6.19·6.23절)과 같은 원칙입니다.

### 8. `include_inactive`가 필요한 이유

실행 화면과 관리 화면은 서로 다른 질문을 합니다.

- 실행 selector: "지금 **실행할 수 있는** 프로필은 무엇인가" → 기본값 `include_inactive=false`. 비활성 프로필이 남아 있으면 사용자는 고를 수는 있는데 실행만 `409`로 막히는 화면을 보게 됩니다.
- 관리 화면: "**관리할 수 있는** 프로필은 무엇인가" → `include_inactive=true`. 비활성 프로필을 목록에서 감추면 한 번 내린 프로필을 다시 고를 수 없어 영영 되살릴 방법이 없어집니다.

기본값을 `false`로 둔 덕분에 이 parameter를 넘기지 않는 기존 호출자는 지금까지와 완전히 같은 응답을 받습니다. 응답 shape도 두 경우가 같고, 각 프로필의 실제 상태는 activation endpoint로 따로 조회합니다. `include_inactive`는 필터를 끄는 것이지 allowlist 밖의 후보를 넓히지 않습니다.

같은 이유로 activation `GET`은 **비활성 프로필도 `200`으로 조회됩니다.** 이 endpoint의 목적이 바로 "지금 활성인가"를 묻는 것이므로, 비활성이라고 `409`를 내면 운영자가 상태를 확인할 방법이 없어집니다.

### 9. Deactivate ≠ Delete

비활성화가 막는 것은 **신규 ETL 실행**뿐입니다. 업로드·S3·HTTP feed·Airflow 네 경로 모두 해당됩니다.

삭제되거나 막히지 않는 것: 과거 ETL 적재 이력, staging 상품 조회, ETL 품질 요약·추이·품질 관찰, 상품 동기화 차이(Catalog Reconciliation), promotion 이력, rollback 이력, `config/etl`의 버전별 프로필 archive. Policy G("Delete 대신 Deactivate")를 그대로 따른 것입니다. 뒤에 추가한 `DELETE .../activation`(6.25)도 프로필이나 archive를 지우는 것이 아니라 runtime override row 하나만 지웁니다.

### 10. reset / history 한계

이 시점에는 두 가지를 만들지 않았고, 그 사실을 API·UI·문서에 함께 남겼습니다. 그중 reset은 이후 6.25에서 별도 endpoint로 추가했습니다.

**reset이 없었습니다.** `active_version: null`은 배포 기본값으로 되돌리는 reset이 아니라 명시적 비활성화입니다. 이 요청 뒤에도 `runtime_override_exists`는 `true`로 남습니다. 이 의미는 지금도 그대로이고, runtime override row 자체를 삭제하는 것은 6.25에서 추가한 별도 `DELETE`입니다.

**append-only history가 아닙니다.** 이 표는 프로필당 current-state row 하나입니다. A가 deactivate하고 B가 v2를 activate하면 최종 row에는 B의 값만 남고 A의 이전 결정은 보존되지 않습니다. `actor_username`과 `updated_at`은 "현재 상태를 마지막으로 만든 것이 누구/언제인가"일 뿐이며, 그것으로 activation 변경 이력을 되짚을 수는 없습니다. 완전한 감사 이력이 필요하면 별도 표가 있어야 하고, 이 표를 그 용도로 읽으면 안 됩니다. Streamlit 화면에도 "변경 이력은 저장하지 않습니다"를 caption으로 남겼습니다.

> **갱신(6.26)**: current-state 표에 대한 위 설명은 지금도 그대로 맞습니다. 다만 성공한 운영 명령의 append-only 이력은 6.26에서 별도 표 `etl_profile_activation_events`로 추가됐습니다.

### 11. Airflow inactive 분류

Airflow DAG는 비활성 프로필을 generic `catalogguard_etl_unexpected`로 실패시키고 있었습니다. 이를 전용 코드 `etl_profile_inactive`로 분리하고 **retry하지 않도록**(`AirflowFailException`) 했습니다.

운영자가 의도적으로 내린 프로필은 network timeout, HTTP 5xx, 일시적 DB 오류 같은 장애와 의미가 다릅니다. 일시 장애는 재시도로 회복될 수 있지만 운영 정책 상태는 사람이 다시 켜기 전까지 회복되지 않습니다. 재시도해 봐야 같은 결과를 반복하며 로그만 실패로 채웁니다. 설정 오류를 뜻하는 `etl_profile_invalid`(없는 `profile_id`)와도 구분했습니다. 앞은 설정을 고쳐야 하고 뒤는 사람이 켤 때까지 그대로 두는 것이 맞아서, 운영자가 할 일이 다르기 때문입니다.

Airflow와 로그에는 안전한 코드 하나만 노출합니다.

```text
CatalogGuard HTTP feed ingestion failed [etl_profile_inactive]
```

`profile_id`, 프로필 JSON 원문, feed URL과 query, token, DB URL, 원본 예외는 넣지 않고 `__cause__`도 남기지 않습니다. 다른 실패 분기와 같은 규칙입니다.

### 12. Airflow pre-fetch guard와 남은 race

현재 DAG의 실제 순서는 effective activation pre-check → `end_activation_read_transaction()` → `read_http_feed_csv()` → `run_web_etl()`입니다. **pre-check 시점에 이미 inactive인 프로필은 HTTP feed를 시작하지 않고** `etl_profile_inactive`의 non-retryable failure가 됩니다.

다만 DB transaction이나 lock을 외부 HTTP 요청 동안 유지하지 않으므로, pre-check 뒤 운영자가 deactivate하면 fetch가 이미 시작될 수 있습니다. 이 경우에도 `run_web_etl()`의 최종 activation 재검사가 ETL load를 차단합니다. 따라서 pre-check 시점의 inactive에 대해서는 fetch 0회를 보장하지만, 상태 변경 race까지 포함해 어떤 fetch도 발생하지 않는다고 말하지는 않습니다.

### 13. 검증

Activation 검증 근거는 다섯 갈래다.

- **API integration test** — `tests/test_api_etl_profile_activation.py`(35개 수집). `GET`/`PUT` 계약, viewer/operator RBAC, 3-state, 비활성 프로필의 activation `GET` 200, registry versions 밖 버전 `422`와 `available_versions`, 관리 목록을 통한 비활성 → 재활성 왕복
- **API Client test** — `tests/test_catalogguard_api_client.py`(313개 수집). activation 응답 shape 검증과 `include_inactive` 파라미터 전달, `PUT` 오류 매핑
- **Streamlit AppTest** — `tests/test_etl_load_history_ui.py`(120개 수집). 운영 관리 화면의 상태 표시, viewer/operator 컨트롤 분리, 실행/관리 state 분리, 성공 응답 뒤에만 캐시 무효화
- **PostgreSQL 통합** — `tests/test_etl_profile_activation_service.py`, `tests/etl/test_profile_activation.py`. current-state upsert, 동시 변경, read 트랜잭션 정리와 보류 ORM 쓰기 검출
- **전용 Chromium E2E** — `tests/e2e/test_etl_profile_ops_browser_e2e.py`. operator가 `sample_fashion_vendor_v1`을 deployment default v2에서 deactivate하고 archived v1을 activate한 뒤 reset해 v2로 돌아오는 UI를 Chromium에서 검증한다. current-state와 `deactivate`·`activate`·`reset` history를 PostgreSQL에서도 확인하고, disposable local DB에서만 snapshot 기반 cleanup을 수행한다.

Airflow의 `etl_profile_inactive` 분류는 `airflow/tests/test_catalogguard_http_feed_to_staging.py`에 있고, 전용 `airflow-smoke` job의 격리 Airflow image가 `python -m unittest discover`로 실행합니다. 같은 run의 결과는 `Ran 12 tests` / `OK`이며, Airflow가 없는 일반 pytest run에서는 module 단위로 skip되어 위 `2 skipped`에 포함됩니다.

기능 완료 commit `06215ec`를 대상으로 한 GitHub Actions run `32571400595`은 `test`·`airflow-smoke`·`browser-e2e`·`kubernetes-smoke`·`terraform-validate` 5개 job이 모두 success였고, `Run tests` 단계는 다음과 같이 종료됐습니다.

```text
2369 passed
2 skipped
6 deselected
5 warnings
0 failed
```

`2 skipped`는 Airflow가 설치된 전용 image에서만 실행되는 격리 DAG 테스트 module 2개이며 **통과가 아닙니다.** 같은 commit을 `TEST_DATABASE_URL` 없이 실행하면 `2090 passed`, `281 skipped`, `6 deselected`가 됩니다. 모든 PostgreSQL 결과는 운영 DB가 아니라 일회성 테스트 환경의 결과입니다.

### 14. 후속 개선

1. ~~runtime override를 제거해 배포 기본값으로 되돌리는 reset endpoint~~ → 6.25에서 구현했습니다
2. ~~append-only activation history 전용 표~~ → 6.26에서 구현했습니다
3. 운영 관리 화면의 Chromium 브라우저 E2E
4. Airflow DAG의 feed fetch 전 inactive guard
5. activation 실패와 source 실패가 겹칠 때의 failure precedence 정책
6. 사용자 정의 Profile CRUD
7. DB-backed Profile / ProfileVersion 모델 도입 여부 검토

1~5는 이 시점에서 의도적으로 남긴 항목이고, 6~7은 프로필 정의를 code/config에 두는 현재 구조를 바꿀지에 대한 별도 판단입니다.

## 6.25 ETL Profile Runtime Override Reset

6.24가 남긴 후속 개선 1번을 구현한 단계입니다. **없던 상태 전환 하나**를 더한 것이 전부이고, 기존 API 계약·DB 스키마·Alembic head(`20260822_0014`)는 바꾸지 않았습니다.

### 1. 문제

6.24에서 만든 runtime override는 한 번 만들면 지울 방법이 없었습니다. 즉 `배포 기본값 사용 → 명시적 override`는 가능한데 그 반대가 없었고, 한 번 손댄 프로필은 계속 명시적으로 관리해야 했습니다. 배포 기본값이 바뀌어도 그 프로필만 따라가지 않습니다.

### 2. 검토했지만 택하지 않은 대안: `PUT` `null` 재사용

가장 적은 코드로 끝내는 방법은 `PUT {"active_version": null}`을 "override 제거"로 재해석하는 것이었습니다. 새 endpoint도, 새 RBAC도, 새 client method도 필요 없습니다.

**택하지 않았습니다.** 그 순간 6.24의 3-state model이 2-state로 무너지기 때문입니다. `row 없음`(아무도 손대지 않아 배포 기본값을 따름)과 `row + NULL`(운영자가 명시적으로 내림)이 같은 요청으로 만들어지면 둘을 구분할 수 없고, 다음 배포에서 registry 기본값이 활성으로 바뀌는 순간 운영자가 내려 둔 프로필이 아무도 켜지 않았는데 다시 실행되기 시작합니다.

기존 계약을 바꾸지 않는 쪽을 택했습니다. `PUT` `null`은 지금도 명시적 비활성이고, 되돌리는 것은 별도 `DELETE`입니다.

### 3. 상태 전환

| 동작 | `etl_profile_activations` row | effective |
| --- | --- | --- |
| `PUT {"active_version": "2"}` | 있음 (`active_version = '2'`) | `"2"` |
| `PUT {"active_version": null}` | 있음 (`active_version = NULL`) | `None` — 명시적 비활성 |
| `DELETE` (이번 단계) | **없음** | registry의 `active_version` |

reset 뒤 응답은 `runtime_override_exists: false`, `runtime_active_version: null`, `actor_username: null`, `updated_at: null`이고 `effective_active_version`은 배포 기본값입니다.

### 4. DB

Service는 current-state row 하나를 지웁니다. 검증(allowlist 확인)을 트랜잭션 밖에서 먼저 해 없는 `profile_id`가 쓰기 트랜잭션을 열지 않게 했고, 삭제는 `with session.begin()` 안에서 Core `delete(...).where(profile_id == ...)` 한 문장입니다. 지우는 대상은 `etl_profile_activations`의 그 row **하나뿐**이며 스키마 변경도 migration도 없습니다.

`DELETE ... WHERE`가 0 row에도 성공하므로 별도 존재 확인이 필요 없고, 그래서 "확인했더니 있었는데 지우려니 없더라" 같은 race도 생기지 않습니다.

### 5. API

`DELETE /api/v1/etl-profiles/{profile_id}/activation` — operator, 기존 `require_operator` dependency 그대로.

| 요청 | 응답 |
| --- | --- |
| allowlist 프로필 + override 있음 | `200` (row 삭제 후 배포 기본값 상태) |
| allowlist 프로필 + override 없음 | `200` (idempotent) |
| 없는 `profile_id` | `404` |
| viewer | `403` |
| 미인증 | `401` |

idempotent로 둔 이유는 DELETE를 두 번 보내는 것이 재시도이지 오류가 아니기 때문입니다. 다만 없는 프로필까지 `200`으로 뭉개지는 않았습니다. "지울 것이 없다"와 "그런 프로필이 없다"는 운영자가 할 일이 다르고, 합치면 오타로 친 `profile_id`가 성공으로 보입니다.

request body는 받지 않습니다. 지울 대상은 경로가 정하고, actor는 저장할 row 자체가 없어집니다.

`204`가 아니라 기존 `ETLProfileActivationResponse`를 돌려줍니다. `204`면 화면이 reset 직후 effective 상태를 알기 위해 `GET`을 한 번 더 해야 하고, 그 사이 다른 operator의 변경이 끼면 방금 만든 상태를 잘못 설명하게 됩니다. 새 응답 schema는 만들지 않았고 API client도 기존 응답 검증을 그대로 재사용합니다.

### 6. `[안전]` reset은 프로필을 되살릴 수 있다

이번 단계에서 가장 중요한 판단입니다.

배포 기본값이 `v2` 활성인 프로필에 명시적 비활성 override가 걸려 있을 때 reset을 누르면, override가 사라지면서 `v2`가 다시 적용되어 그 프로필의 신규 실행이 **즉시 가능해집니다.** 화면에서 "정리" 버튼처럼 보이면 운영자가 결과를 모르고 프로필을 되살리게 됩니다.

그래서 Streamlit `런타임 설정 초기화` 구획은:

- override가 없으면 버튼 자체를 만들지 않고 "되돌릴 설정이 없다"고만 안내합니다. 지울 것이 없는데 버튼을 보여 주면 무언가 남아 있다고 잘못 말하게 됩니다
- override가 있으면 **되돌린 뒤 실제 적용될 버전**을 먼저 보여 줍니다(`되돌린 뒤 실제 적용 버전: v2`)
- 지금 비활성인 프로필이면 "다시 활성화됩니다"를 덧붙이고, 배포 기본값 자체가 비활성이면 "reset 뒤에도 계속 비활성"임을 정확히 말합니다
- 비활성화와 같은 수준의 확인 checkbox를 거치고, 전송 직전에 값을 한 번 더 봅니다

성공 메시지는 서버가 돌려준 effective 값으로 만듭니다. UI가 결과를 추측하지 않습니다.

### 7. 발견한 버그 — Streamlit widget key 재대입

reset의 AppTest를 쓰다가 **기존 비활성화 경로의 버그**가 드러났습니다.

성공 처리에서 확인 checkbox를 `session_state["etl_profile_admin_deactivate_confirmed"] = False`로 초기화하고 있었는데, Streamlit은 이번 run에서 이미 생성된 widget의 key에 값을 **대입**하면 `StreamlitAPIException`을 냅니다. checkbox는 실행 버튼보다 먼저 그려지므로 성공 처리는 언제나 그 뒤에 오고, 결과적으로 **비활성화에 성공하면 화면이 예외로 끝나고 있었습니다.**

드러나지 않은 이유는 기존 AppTest가 `activation_update_calls`만 확인하고 `app.exception`을 보지 않았기 때문입니다. API 호출은 예외 직전에 이미 끝나 있어서 단언은 통과했습니다. 이전 commit을 그대로 체크아웃해 재현해 확인했습니다.

대입 대신 삭제(`pop`)로 바꿨습니다. 삭제에는 같은 제약이 없고, 다음 run에서 checkbox가 기본값으로 다시 만들어집니다. reset과 비활성화가 같은 성공 경로를 공유하므로 한 곳만 고쳐 둘 다 낫습니다. `app.exception`을 확인하는 회귀 테스트를 비활성화·reset 양쪽에 추가했습니다.

### 8. 검증

로컬 PostgreSQL 통합 환경에서 관련 테스트를 실행했습니다. 이 commit에 대한 CI run은 아직 없으므로 "CI 통과"라고 쓰지 않습니다.

`python -m pytest tests/` 전체는 `2427 passed`, `6 deselected`, `0 failed`였고, 관련 5개 파일 묶음은 다음과 같습니다.

| 대상 | 결과 |
| --- | --- |
| `tests/test_etl_profile_activation_service.py` | 37 passed |
| `tests/test_api_etl_profile_activation.py` | 49 passed |
| `tests/test_catalogguard_api_client.py` | 325 passed |
| `tests/test_etl_load_history_ui.py` | 141 passed |
| `tests/test_api_rbac.py` | 51 passed |
| 위 5개 묶음 | **603 passed, 0 failed, 0 skipped** |

고정한 것: reset 후 row가 실제로 사라지는지, 명시적 비활성 override reset이 프로필을 되살리는지, 두 번째 DELETE가 오류가 아닌지, 없는 프로필이 `404`인지, viewer가 `403`인지, `PUT` `null`이 여전히 명시적 비활성인지, reset이 과거 ETL 이력과 프로필 정의를 건드리지 않는지, 관리 화면 reset이 실행 selector 상태와 과거 이력 조회 상태를 섞지 않는지.

### 9. 한계

- **activation history는 (이 단계 시점에는) 여전히 없었습니다.** 이 표는 current-state row 하나이므로 reset하면 그 row의 `active_version`·`actor_username`·`updated_at`도 함께 사라집니다. "누가 언제 이 override를 만들었는가"는 reset과 동시에 어디에도 남지 않았습니다. → **6.26에서 별도 append-only 표로 해소했습니다.** current-state 응답의 actor가 reset 후 `null`인 것은 지금도 그대로이고, 그 명령을 누가 내렸는지는 이력 쪽에 남습니다
- **Profile CRUD는 없습니다.** 프로필 정의와 버전 archive의 source of truth는 계속 `config/etl` JSON archive와 코드 registry입니다
- 운영 관리 화면(운영 이력 포함)은 service·API·client·AppTest·PostgreSQL 통합 테스트에 더해 전용 Chromium E2E로 검증합니다. 범위는 disposable local PostgreSQL과 Chromium 한 경로입니다
- Airflow의 feed fetch 전 inactive guard와 failure precedence 정책은 6.24 시점 그대로 남아 있습니다

## 6.26 ETL Profile Activation Append-only History

6.25가 남긴 한계 1번을 구현한 단계입니다. **current-state 구조는 한 줄도 바꾸지 않았습니다.** `PUT` `null`은 여전히 명시적 비활성이고 `DELETE`는 여전히 reset이며, 더한 것은 표 하나와 읽기 endpoint 하나입니다. Alembic head는 `20260823_0015`입니다.

### 1. 문제

`etl_profile_activations`는 프로필당 current-state row 하나입니다. A가 v2를 활성화하고 B가 비활성화하고 C가 reset하면, 표에 남는 것은 마지막 상태뿐입니다. 특히 reset은 row 자체를 지우므로 `actor_username`과 `updated_at`까지 함께 사라져 **누가 무엇을 했는지 아무것도 남지 않았습니다.**

### 2. current-state와 history를 왜 나눴나

이 표를 history 표로 바꾸는 것은 선택지가 아니었습니다. 바꾸면 "지금 무엇이 적용되는가"를 물을 때마다 이력 전체에서 최신 행을 골라야 하고, 그 계산이 `resolve_etl_profile_activation()` 밖으로 새어 나갑니다. 두 표는 답하는 질문이 다릅니다.

| 표 | 답하는 질문 | 쓰기 | row 수 |
| --- | --- | --- | --- |
| `etl_profile_activations` | 지금 무엇이 적용되는가 | upsert / delete | 프로필당 0 또는 1 |
| `etl_profile_activation_events` | 지금까지 무엇을 했는가 | **INSERT만** | 명령마다 1, 누적 |

### 3. event의 기록 단위

**"상태가 실제로 달라진 순간"이 아니라 "서버가 성공으로 처리한 operator 명령"입니다.**

| 요청 | 상태 변화 | event |
| --- | --- | --- |
| `PUT {"active_version": "2"}` | 있음 | `activate` 1건 |
| 같은 `PUT`을 한 번 더 | **없음** | `activate` 1건 더 |
| `PUT {"active_version": null}` | 있음 | `deactivate` 1건 |
| 이미 비활성인데 같은 `PUT` | **없음** | `deactivate` 1건 더 |
| `DELETE` | 있음 | `reset` 1건 |
| override 없는데 `DELETE`(idempotent `200`) | **없음** | `reset` 1건 더 |
| 없는 프로필 / 없는 버전 / `401` / `403` | 없음 | **없음** |

즉 state idempotency와 audit event idempotency는 다른 개념입니다. API가 idempotent한 것은 결과 상태에 대한 성질이고, 이 표가 답하는 질문은 "누가 무엇을 시도해 서버가 받아들였는가"입니다. 같은 명령을 두 번 내린 것은 실제로 두 번 일어난 일입니다.

실패한 요청이 흔적을 남기지 않는 것은 검증 순서 덕분입니다. allowlist와 보존 버전 검증은 지금도 쓰기 transaction을 열기 **전에** 끝나므로, 없는 프로필이나 버전은 이 표에 도달하지 못합니다. `401`/`403`은 애초에 service까지 오지 않습니다.

### 4. DB와 migration

`etl_profile_activation_events`에는 `profile_id`, `action`, 명령 직후 상태 snapshot 네 개(`deployment_active_version`·`runtime_override_exists`·`runtime_active_version`·`effective_active_version`), actor 두 개, `created_at`을 둡니다. 상태 값을 snapshot으로 저장한 이유는, 나중에 registry를 다시 읽어 계산하면 배포 기본값이 바뀔 때 과거 기록의 뜻이 조용히 달라지기 때문입니다. `profile_id`에 FK를 걸지 않은 이유는 current-state 표와 같습니다.

CHECK constraint 하나가 **명령과 결과 상태가 모순되는 행**을 막습니다.

```text
activate   : override 있음 AND runtime IS NOT NULL AND effective = runtime
deactivate : override 있음 AND runtime IS NULL     AND effective IS NULL
reset      : override 없음 AND runtime IS NULL     AND effective IS NOT DISTINCT FROM deployment
```

reset 비교에 일반 `=`를 쓰지 않았습니다. 배포 기본값 자체가 비활성이면 양쪽이 `NULL`인데, PostgreSQL에서 `NULL = NULL`은 참이 아니라 `NULL`이고 CHECK는 `NULL`을 통과시켜 제약이 **조용히 무력화**됩니다. `IS NOT DISTINCT FROM`이 그 경우까지 정확히 봅니다.

### 5. Atomicity

이 단계에서 가장 중요한 설계 판단입니다. 단순히 로그 테이블을 추가한 것이 아닙니다.

```python
with session.begin():
    <current-state upsert 또는 delete>
    <같은 transaction에서 resolve>
    <event INSERT>
```

두 쓰기를 다른 transaction으로 나누면 둘 중 하나가 반드시 생깁니다. **상태만 바뀌고 기록이 없으면** "기록에 없으니 아무도 안 했다"가 거짓이 되어 이력 전체를 믿을 수 없게 되고, **기록만 있고 상태가 안 바뀌면** 일어나지 않은 일이 기록에 남습니다. 그래서 event helper는 `session.add()`만 하고 commit하지 않으며, transaction 경계는 호출자가 소유합니다. 이력 INSERT가 실패하면 상태 변경도 함께 rollback됩니다.

event에 담는 상태는 같은 transaction 안에서 `resolve_etl_profile_activation()`으로 얻습니다. effective 계산을 다시 구현하지 않는다는 6.24의 규칙은 그대로입니다.

### 6. API와 RBAC

`GET /api/v1/etl-profiles/{profile_id}/activation/history`(viewer 이상)로 조회합니다. `limit`(기본 `20`, `1`~`100`)·`offset`(기본 `0`) pagination과 `created_at DESC, id DESC` 정렬을 쓰고, 없는 프로필은 `404`, 기록이 없으면 `200` + 빈 목록입니다. 운영 기록을 읽는 것은 상태를 바꾸는 것이 아니므로 새 role을 만들지 않았고, 상태를 바꿀 수 없는 사람도 "왜 지금 이렇게 되어 있는가"는 확인할 수 있어야 합니다.

**`actor_user_id`는 응답에 노출하지 않습니다.** DB 관계용 ID이고, 화면에 필요한 것은 사용자가 삭제된 뒤에도 남는 `actor_username` snapshot입니다. service view dataclass에도 그 필드를 두지 않아 실수로 새어 나갈 자리 자체를 없앴습니다. 기존 `PUT`/`DELETE` 응답에는 이력을 끼워 넣지 않아 `ETLProfileActivationResponse` 계약이 그대로입니다.

이력에는 수정·삭제·purge API가 없고 client에도 조회 method 하나만 뒀습니다. 다만 append-only는 **애플리케이션 계약**이지, DB superuser의 직접 `UPDATE`/`DELETE`까지 막는 WORM 저장소를 구현한 것은 아닙니다.

### 7. Streamlit

`ETL 프로필 운영 관리` 아래에 read-only `Activation 운영 이력` 표를 더했습니다. 시각·동작·런타임 결과·실제 적용 버전·배포 기본 버전·사용자를 함께 보여 주고, 동작은 `버전 활성화`·`비활성화`·`배포 기본값으로 되돌리기`로 구분합니다. **reset을 비활성화로 표시하지 않습니다** — override가 사라졌을 뿐이고 배포 기본값이 활성이면 실제 적용 버전이 있으므로 두 값을 한 행에서 함께 보여 줍니다.

activate/deactivate/reset 성공 뒤에는 기존 공통 경로(`_commit_etl_profile_activation_change()`) **한 곳**에서 이력 캐시까지 함께 비웁니다. 같은 무효화를 세 군데 복사하면 나중에 한쪽만 고쳐져 이력만 옛 화면으로 남습니다. 이력 조회가 실패해도 관리 화면 전체가 사라지지 않고 그 구획에만 오류를 표시해, 상태 확인과 조작은 계속 쓸 수 있습니다.

### 8. reset actor: 모순이 아니다

reset 직후 current-state 응답의 `actor_username`과 `updated_at`은 여전히 `null`입니다. 그 값을 들고 있던 row가 없어졌기 때문이고, 이 계약은 6.25 그대로입니다. 동시에 이력의 `reset` event에는 actor가 남습니다.

두 값은 서로 다른 질문에 답합니다. 앞은 "지금 이 override를 만든 사람"이라 override가 없으면 없는 것이 맞고, 뒤는 "그 override를 지운 명령을 내린 사람"입니다. 그래서 `DELETE` route가 이번에 인증된 `current_user`에서 actor를 받도록 확장됐고, request body에는 여전히 actor를 넣을 자리가 없습니다.

### 9. 과거 이력을 만들어 내지 않았다

migration은 **빈 표를 만듭니다.** 기존 current-state row를 보고 과거 event를 채우지 않았습니다. row 하나로는 누가 처음 활성화했는지, 몇 번 바꿨는지, 언제 내렸다 올렸는지 알 수 없기 때문입니다. 모르는 것을 추측해 채우면 없는 기록보다 나쁜 **틀린 기록**이 남고, 나중에 읽는 사람이 그것을 사실로 믿습니다.

그래서 이력은 `0015` 적용 **이후의 명령부터** 시작하며, 화면·API 문서도 그렇게 말합니다. 실제 PostgreSQL migration 테스트에서 `0014` 상태에 override row를 넣고 `0015`로 올린 뒤 event 0건과 current-state row 보존을 함께 확인했습니다.

### 10. 검증

로컬 PostgreSQL 16 통합 환경에서 실행한 결과입니다. **이 commit에 대한 CI run은 아직 없으므로 "CI 통과"라고 쓰지 않습니다.**

`python -m pytest tests/` 전체(e2e·performance 제외)는 `2543 passed`, `0 failed`였고, 핵심 묶음은 다음과 같습니다.

| 대상 | 결과 |
| --- | --- |
| `tests/test_etl_profile_activation_history_migration.py` | 5 passed |
| `tests/test_etl_profile_activation_history_service.py` | 35 passed |
| `tests/test_etl_profile_activation_service.py` | 37 passed |
| `tests/test_api_etl_profile_activation.py` | 69 passed |
| `tests/test_catalogguard_api_client.py` | 369 passed |
| `tests/test_etl_load_history_ui.py` | 154 passed |
| `tests/test_api_rbac.py` | 54 passed |
| 위 7개 묶음 | **723 passed, 0 failed, 0 skipped** |

고정한 것: 세 명령이 각각 event 하나를 남기는지, 같은 `PUT`·no-op reset도 event를 추가하는지, 실패한 요청이 아무것도 남기지 않는지, 이력 INSERT가 실패할 때 상태 변경까지 rollback되는지, reset event의 실제 적용 버전이 배포 기본값인지, 사용자를 지워도 이름 snapshot이 남는지, 응답에 `actor_user_id`가 없는지, `0015` upgrade가 기존 row로 이력을 만들지 않는지, 화면이 reset을 비활성화로 표시하지 않는지, 이력 조회 실패가 관리 화면을 깨지 않는지.

### 11. 한계

- **`0015` 이전의 운영 명령은 이력에 없습니다.** backfill하지 않았습니다
- 이력 조회도 현재 registry allowlist를 기준으로 검증하므로, registry에서 완전히 제거된 과거 프로필의 event는 표에 남아 있어도 프로필별 endpoint로는 읽을 수 없습니다(`404`). 여러 프로필을 한 번에 보는 조회도 없습니다
- append-only는 애플리케이션 계약이며 WORM 저장소가 아닙니다. retention/purge 정책도 없어 event는 계속 누적됩니다
- 동시성 정책은 6.24 그대로 last-write-wins입니다. 정렬은 결정적이지만 분산 환경의 절대적 인과 순서는 아닙니다
- **Profile CRUD는 없습니다.** 프로필 정의와 버전 archive의 source of truth는 계속 `config/etl` JSON archive와 코드 registry입니다
- 운영 관리 화면(운영 이력 포함)은 전용 Chromium E2E로 검증합니다. 이 시나리오는 disposable local PostgreSQL에서 snapshot 기반 cleanup을 수행합니다
- Airflow의 feed fetch 전 inactive guard와 failure precedence 정책은 6.24 시점 그대로 남아 있습니다
