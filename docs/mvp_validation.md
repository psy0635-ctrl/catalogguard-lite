# MVP 검증 근거와 기능 동결 기준

## 기준과 해석

2026-10-10 현재 `main`의 `3ea24147fcaf5ab636cc56dc19fc645593fd8bdd`를 기준으로 정리한 로컬 검증 기록이다. Python 3.11.9와 독립 PostgreSQL 18.4에서 합성 공급사 데이터로 실행했다. 현재 `INSPECTION_VERSION`은 `17`, Alembic 단일 head는 `20260915_0020`이다.

정식 릴리스는 [v0.3.0](https://github.com/psy0635-ctrl/catalogguard-lite/releases/tag/v0.3.0)이며, 현재 main의 미출시 변경과 구분한다. 이 문서는 릴리스·Tag 발행이나 프로젝트 버전 변경을 의미하지 않는다. 기존 릴리스 기능과 main의 차이는 [README](../README.md#1-현재-상태와-최근-검증)와 [포트폴리오](portfolio_project.md)에 유지한다.

아래 수치는 서로 다른 실행의 결과다. **67 passed, API 시나리오 35건, Chromium 8 passed, Runner 4 passed를 하나의 pytest 결과로 합산하지 않는다.** 이번 문서 최신화에서는 테스트·데모·DB 작업을 다시 실행하지 않고 기존 실행 보고서와 JSON·JUnit 결과를 대조했다. 원본 로컬 로그·보고서·스크린샷은 공개 저장소에 업로드된 자료가 아니며, 이 문서는 공개 가능한 결과와 재현 대상 파일만 요약한다.

## 검증 환경 분리

| 환경 | 사용 범위 | 데이터 보호 |
|---|---|---|
| 보존형 통합 테스트 DB, 로컬 포트 `55434` | ETL·Service Promotion/Rollback·JWT TestClient API | 각 단계에서 기존 데이터와 허용한 신규 변경을 구분하고 전후 행 수·전체 데이터 해시 비교 |
| 별도 Chromium E2E DB, 로컬 포트 `55435` | 기존 Browser Runner의 Migration·합성 적재·실제 웹 실행 | 새로운 Container·DB·User·Volume·Network·서버 식별자 확인; 기존 `55434` DB에 연결하지 않음 |

두 환경의 Run ID가 같아도 같은 기록이 아니다. 예를 들어 각 DB의 Promotion Run 1은 서로 다른 서버에 저장됐다. 기존 검증 DB에 Browser Runner를 실행하지 않는다. Runner는 계정을 만들고 일부 프로필 상태를 바꾸며 자체 Fixture를 정리하므로 새로 만든 빈 E2E DB가 필요하다.

## 검증 결과 요약

| 실행 | 결과 | 실제로 확인한 범위 |
|---|---|---|
| PostgreSQL ETL DB Loader | 67 passed, failed/errors/skipped 0, 2 deselected, warnings 0 | 파일 해시·상품·Reject 저장, 중복 배치 재사용, 저장 실패 시 트랜잭션 Rollback, 음수 값 제약조건 |
| Service Promotion Preview | 기존 Reject 배치 2개 차단, 신규 정상 배치 반영 가능 | 읽기 전용 트랜잭션, 동일 상태의 전체 결과·Hash 반복 일치, DB 무변경 |
| Service Promotion | 신규 Run 1건, INSERT 2건·Audit 2건 | 상품 값·출처·Before/After·중복 성공 Run 재사용 |
| Service Rollback | 신규 Run 1건, DELETE 2건·Audit 2건 | 삭제 대상 ID, 원본 Promotion/Audit 보존, 원본 Audit 참조, 중복 실행 예외 |
| 실제 JWT API 통합 | 35개 시나리오 예상 응답 일치, 32개 요청 DB 무변경 | TestClient로 실제 라우팅·JWT·권한·DB Service·Actor 기록 통과 |
| 실제 Chromium E2E | 8 passed, failed/errors/skipped 0 | FastAPI·Streamlit·Chromium·별도 PostgreSQL을 실행한 웹 흐름 |
| Browser Runner 안전성 단위 테스트 | 별도 4 passed | 로컬 테스트 URL 허용, 비로컬·운영처럼 보이는 URL 차단 |

ETL 테스트의 2개 제외 항목은 Alembic Downgrade 테스트와 배치 삭제 테스트다. 테스트가 생성한 고유 배치의 제한된 정리 동작은 독립 DB에서 실행했으며, 공급사 배치가 보존됐음을 확인했다. 과거 다른 head에서 수행한 69/37 passed 등 기존 기록은 [포트폴리오의 당시 검증 조건](portfolio_project.md#627-현재-유지개발과-postgresql-transaction-검증)을 유지한다.

## ETL과 상품 품질 검수의 관계

ETL은 JSON Profile로 컬럼을 매핑하고 숫자 형식·필수 입력을 검사해 표준 상품과 Reject를 나눈다. 형식 변환이 성공했다고 상품 품질 검수를 모두 통과한 것은 아니다. 할인 가격이 정가보다 높은 값, 비표준 색상·사이즈 등은 정상 staging에 남을 수 있고 Promotion Preview의 규칙 기반 검수가 별도로 확인한다.

```text
공급사 CSV / Web multipart XLSX + JSON Profile
  → 표준 상품 / Reject / Summary
  → 해시·행 수 검증 및 PostgreSQL staging 적재
  → 사용자가 배치 선택
  → Promotion Preview에서 현재 상품 품질 검수와 Catalog 비교
  → 최신 Hash와 명시적 승인
  → Catalog INSERT/UPDATE + Promotion Run + Audit
  → 필요 시 Rollback Preview에서 현재 상태 충돌 확인
  → 최신 Hash와 명시적 승인
  → INSERT 상품 삭제 / UPDATE 상품 이전 값 복원 + Rollback Run + Audit
```

별도의 Inspection 업로드·이력 저장 경로도 있다. ETL batch가 Inspection 실행 이력에 자동 연결되거나 모든 단계가 자동 실행되는 구조로 설명하지 않는다. XLSX 지원은 Web multipart에 한정하며 CLI·S3·HTTP feed·Airflow 입력은 CSV 전용이다. 코드 계약은 [ETL MVP](etl_mvp.md), [Promotion 설계](catalog_promotion_design.md), [Inspection Version 정책](inspection_version_policy.md)을 따른다.

### PostgreSQL ETL 및 Preview

Fashion과 Marketplace의 합성 Fixture를 각각 입력 3행·정상 2행·Reject 1행으로 변환·저장했다. 입력·표준·Reject SHA-256, 가격·재고·상품 ID, 오류 코드·필드·메시지와 마스킹된 원본을 확인했다. 동일 결과 재적재는 `created=False`로 배치 ID를 재사용하며 상품·Reject 행을 추가하지 않았다.

| 보존형 DB 배치 | Eligible | Errors | Warnings | 차단 사유 |
|---|---|---:|---:|---|
| Fashion 1 | False | 1 | 3 | `etl_rejections_present`, `inspection_errors_present` |
| Marketplace 2 | False | 1 | 1 | `etl_rejections_present`, `inspection_errors_present` |
| 신규 정상 Fashion 25 | True | 0 | 0 | 없음 |

두 Reject 배치의 정상 staging 상품에서도 `sale_price_greater_than_price` 오류가 나왔다. Fashion은 색상·사이즈 표준화 및 재고 0 경고, Marketplace는 재고 0 경고를 확인했다. Reject 행 수와 검수 오류 수는 서로 다른 지표다. 한 Reject에 오류 코드가 여러 개 있어도 Reject 행은 한 건일 수 있다.

### 실제 Promotion과 Rollback

정상 배치 25의 최신 Preview가 INSERT 2·UPDATE 0·UNCHANGED 0을 반환한 뒤 Service Promotion을 실행했다. 보존형 DB의 Promotion Run 1은 succeeded이며 상품 2건과 INSERT Audit 2건을 저장했다. 재요청은 `created=False`로 기존 성공 Run을 반환했다.

새 Rollback Preview를 두 번 확인한 뒤 해당 Run을 되돌렸다. Rollback Run 1은 succeeded, DELETE 2·RESTORE 0·CONFLICT 0이며 상품 2건은 삭제됐다. 원본 Promotion Run과 INSERT Audit의 ID·상품 식별값·Before/After는 그대로 남고 DELETE Audit 2건이 원본 Audit을 참조했다. 중복 요청은 `CatalogPromotionRollbackAlreadyExecutedError`로 거부됐다.

실제 Catalog 행의 삭제와 Audit의 생명주기는 분리돼 있다. Audit의 `catalog_product_id`는 삭제된 원래 상품의 식별값으로 남으며, 현재 상품 행이 존재한다는 뜻이 아니다. 이번 성공 흐름은 INSERT/DELETE다. UPDATE/RESTORE의 구현·기존 테스트와 별개로 이 로컬 실행에서 해당 성공 흐름까지 확인했다고 주장하지 않는다.

## 실제 JWT API 통합 검증

합성 viewer/operator 계정을 기존 bootstrap CLI로 생성하고 실제 로그인 API로 JWT를 발급받았다. **FastAPI TestClient 기반 프로세스 내부 ASGI 검증**이며 외부 HTTP 서버나 브라우저 테스트가 아니다. 인증 dependency override, 가짜 DB Session, Promotion/Rollback Service mocking은 사용하지 않았다.

- 인증 토큰 없음·잘못된 토큰은 HTTP 401, viewer의 변경 요청은 HTTP 403이었다.
- confirmation 누락은 422, `False`는 400, 형식이 잘못된 Hash는 422로 거부됐으며 DB는 변하지 않았다.
- 신규 ETL 배치 26 → Promotion Run 2 → Rollback Run 2를 API로 실행했다. 상품 2건과 INSERT/DELETE Audit 각각 2건의 값·참조를 확인했다.
- ETL·Promotion·Rollback의 Actor ID와 이름이 로그인한 JWT operator와 일치했다.
- 중복 Promotion은 기존 Run을 재사용하고 중복 Rollback은 409 `already_rolled_back`으로 종료했다. 추가 데이터 변경은 없었다.

35건은 HTTP 시나리오 수이며 `pytest 35 passed`가 아니다. 형식은 유효하지만 오래된 Hash의 요청은 blocked Run을 저장하는 계약이므로 이 최소 변경 검증에서 실행하지 않았다. Redis 로그인 제한은 비활성 설정으로 진행했으며 이번 결과에 포함하지 않는다. 실제 역할 계약은 [인증 dependency](../api/dependencies.py)와 [ETL·Promotion API](../api/routes/etl_loads.py)를 따른다.

## 실제 Chromium 브라우저 E2E

외부 E2E Python 환경에서 저장소의 `requirements-e2e.txt`를 사용했다. pytest 8.4.1·Playwright 1.55.0·pytest-playwright 0.7.0·Chromium 140.0.7339.16으로 기존 Runner를 한 번 실행했다. 기존 개발 가상환경의 pytest 9.1.1은 유지했다.

| 기존 테스트 파일 | Passed | Failed | Skipped |
|---|---:|---:|---:|
| [ETL Browser](../tests/e2e/test_etl_browser_e2e.py) | 2 | 0 | 0 |
| [Web ETL Upload](../tests/e2e/test_web_etl_upload_browser_e2e.py) | 2 | 0 | 0 |
| [Profile Ops](../tests/e2e/test_etl_profile_ops_browser_e2e.py) | 1 | 0 | 0 |
| [Quality Observability](../tests/e2e/test_etl_quality_observability_browser_e2e.py) | 2 | 0 | 0 |
| [Reconciliation](../tests/e2e/test_catalog_reconciliation_browser_e2e.py) | 1 | 0 | 0 |
| 합계 | 8 | 0 | 0 |

Errors 0, Console Error·Page Error·HTTP 오류·요청 실패 모두 0이었다. 숫자는 개별 pytest 결과와 JUnit XML에서 확인했다. [Runner 안전성 단위 테스트](../tests/e2e/test_browser_runner.py) 4 passed는 별도 실행이다.

FastAPI health/readiness와 Streamlit health 확인 후 실제 operator 로그인, Reject 마스킹·필터·CSV 다운로드, CSV/XLSX 업로드, Promotion 승인 전후 버튼 상태와 실행, 변경 Audit, Rollback Preview·승인·삭제·DELETE Audit 표시를 검증했다. Profile Ops는 deactivate/activate/reset 후 상태를 복원하며, Quality/Reconciliation은 자신이 만든 합성 행만 정확한 ID로 정리한다.

새 E2E DB의 최종 상태는 ETL 배치 4개·staging 8행·Reject 2행·Catalog 0행·Promotion/INSERT Audit 1/2행·Rollback/DELETE Audit 1/2행이었다. 원본 Audit 참조와 Reject 마스킹, 실제 FK 관계의 고립 행 0을 확인했다. 성공 스크린샷 8개와 로그를 로컬 외부 폴더에 보존했고, 서버 프로세스를 종료한 뒤 새 DB 컨테이너만 정상 중지했다. Volume·Network·설정·데이터는 유지했다.

### 재현할 때 지킬 조건

기존 [Browser Runner](../scripts/run_etl_browser_e2e.py)와 [CI 정의](../.github/workflows/test.yml)를 사용하되, 매 실행에 별도의 빈 PostgreSQL DB와 충돌하지 않는 로컬 API/Streamlit 포트를 준비한다. Runner의 localhost 검사만으로 보존형 DB와의 분리가 보장되지는 않으므로 Container·DB·User·포트·서버 식별자를 실행 전에 확인한다. DB URL은 명령행 인수 대신 현재 실행 프로세스의 환경변수로 전달하고 출력하지 않는다.

Windows에서는 UTF-8 요구 파일을 읽도록 `PYTHONUTF8=1` 또는 `-X utf8`을 적용한다. `PYTEST_ADDOPTS`에 넣는 경로는 shlex의 역슬래시 해석을 피하도록 forward slash를 사용한다. Runner는 성공 시 임시 로그를 지우므로 외부 JUnit 결과와 필요한 로그 보존을 준비한다. 이번 실행의 인코딩·산출물 경로 문제는 외부 환경/호출 보정으로 해결했고 제품·Runner·테스트를 수정하거나 브라우저 검증을 반복하지 않았다.

## 기능 동결 기준

2026-10-10 기준 핵심 범위는 상품 품질 검수·결과 제공, 공급사 ETL·Reject/Summary, PostgreSQL 저장, JWT viewer/operator 권한, 승인형 Promotion/Rollback, 실행·변경 이력, Streamlit 웹 화면과 기존 브라우저 회귀 테스트다. 별도 인프라·Copilot 기능과 설계 기록은 유지하되 핵심 로컬 성공 흐름과 같은 수준으로 새로 검증했다고 표현하지 않는다.

| 구분 | 작업 범위 |
|---|---|
| 허용 | 재현된 오류·보안·데이터 무결성·기존 기능 회귀 수정, 필요한 테스트 보강, 문서 개선, 재현 가능한 실행 절차 정리 |
| 보류 | 근거 없는 신규 기능, 새로운 인프라, 기존 ETL 중복 구현, 과도한 UI 재설계, 필요성이 확인되지 않은 AI 확장 |
| 변경 판단 | 문제·영향·기존 계약·최소 수정 범위·검증 계획을 먼저 확인하며 데이터 판정 의미가 바뀌면 Inspection Version 정책 검토 |

기능 동결은 유지보수를 멈춘다는 뜻이 아니다. 기존 구현을 관리하는 개발 기준이며 새 Release나 버전 번호를 만들지 않는다.

## 구현 사례와 확인 수준

| 문제 | 해결 방법·주요 코드 | 이번 로컬 검증 및 한계 |
|---|---|---|
| 같은 공급사 파일의 반복 적재 | [Loader](../etl/db_loader.py)의 입력 SHA·프로필·버전 identity와 DB unique index | 실제 재적재 시 기존 배치 재사용; 모든 경쟁 상황의 검증으로 확대하지 않음 |
| 일부 Reject가 있는 배치의 운영 반영 | [Promotion Preview](../db/catalog_promotion_preview_service.py)의 배치 전체 품질 게이트 | Reject 배치 1/2 차단, 정상 배치 25 통과 |
| Preview 이후 데이터가 바뀜 | [Promotion Service](../db/catalog_promotion_service.py)의 재조회·Hash 검증 | 최신 Hash로 성공 및 잘못된 형식 차단; 유효한 stale Hash 실행은 별도 기존 코드/테스트 계약 |
| 상품 저장과 Audit 일부만 남음 | 같은 Service의 하나의 트랜잭션 | 상품·Run·Audit commit 일치; ETL 저장 실패 Rollback은 DB Loader 테스트에서 확인 |
| 변경된 현재 상품을 과거 값으로 덮어씀 | [Rollback Service](../db/catalog_promotion_rollback_service.py)의 현재 상태와 원본 Audit 비교 | 삭제 전 충돌 0, 이미 삭제된 상태는 차단; 임의 강제 복구 없음 |
| 상품 삭제로 이력도 사라짐 | Audit 상품 식별값 보존, Rollback Change의 원본 Audit 참조 | INSERT/DELETE Audit 및 원본 Run 보존, Before/After 일치 |
| 조회 사용자가 상품을 변경함 | JWT와 viewer/operator 권한 분리, 토큰 사용자의 Actor 기록 | 실제 JWT API의 401/403 및 Actor 대조; 브라우저는 operator 성공 경로 중심 |
| Service 성공과 화면 흐름이 다름 | 기존 Chromium 테스트와 실제 API·PostgreSQL 결과 대조 | 승인 버튼·실행·이력·Audit 화면 확인; 다른 브라우저/모바일은 미검증 |

세부 기술 선택과 문제 해결 기록은 [포트폴리오](portfolio_project.md), 발표 흐름은 [데모 Runbook](demo_runbook.md)을 참고한다. Python/pandas는 변환·검수, FastAPI는 서버 계약·권한·실행, SQLAlchemy/Alembic/PostgreSQL은 모델·트랜잭션·스키마·이력 저장, Streamlit은 사용자 화면, pytest/Playwright/Docker/GitHub Actions는 검증과 환경 재현을 담당한다.

## 한계와 유지보수 우선순위

- 실제 외부 공급사 CSV 전체 호환성, 운영 고객 데이터, 대용량 성능·장기 운영 안정성은 미검증이다.
- Redis/Celery·Airflow·S3·Kubernetes·Terraform/AWS의 기존 구현·CI·수동 검증 기록은 각 문서의 범위를 따른다. 이번 로컬 검증에서 모두 다시 실행하지 않았다.
- UPDATE 상품과 RESTORE Rollback의 브라우저 성공 경로, Firefox/WebKit·모바일, 동시성·장애 복구·추가 JWT 경계조건은 이번 실행 범위 밖이다.
- Inspection Copilot은 저장된 검사 결과를 설명하는 읽기 전용 보조 기능이다. Rule Engine의 오류 판정을 대신하거나 상품을 자동 수정하지 않는다.
- 품질 관측·Supplier Coverage·미판정 토큰·Reconciliation은 조회 근거를 제공한다. 자동 수정·자동 차단·자동 삭제·자동 Rollback 기능으로 소개하지 않는다.
- 기존 성능 수치는 원래 fixture·하드웨어·실행 조건을 유지하며 이번 테스트 수나 모든 환경의 성능 보장으로 확대하지 않는다.

다음 유지보수는 문서 변경 검토와 공개 검증 근거 정리를 우선한다. 실제 공급사 파일이 확보되면 개인정보 범위와 입력 계약을 확인한 뒤 매핑 호환성을 별도로 검증한다. 근거 없이 새 기능·인프라를 추가하지 않는다.
