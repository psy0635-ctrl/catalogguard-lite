# CatalogGuard Lite Release / Portfolio Demo Runbook

> 공급사 상품 CSV는 형식과 품질이 제각각이다. CatalogGuard는 이를 검수·표준화하고, 문제가 있는 행은 reject로 분리하며, 확인된 staging batch만 사람이 승인해 catalog에 반영한다. 필요하면 변경 audit을 보며 rollback한다. 이 문서는 기존 합성 fixture와 **격리된 local demo DB**로 이 MVP 흐름을 설명하는 발표용 런북이다.

## 1. 진행 범위

```text
품질 문제 확인 → ETL 변환 / reject 분리 → staging 적재
→ preview + 명시적 승인 → promotion audit → rollback audit
```

- 실제 운영 데이터, 외부 공급사 URL, secret, raw database URL은 사용하거나 표시하지 않는다.
- staging은 운영 상품을 직접 덮어쓰지 않으며, promotion·rollback 모두 로그인한 `operator`의 확인이 필요하다.
- Airflow HTTP feed DAG는 자동 실행이 아닌 선택적 manual trigger다.

| 구간 | 시간 | 핵심 |
|---|---:|---|
| A. Quick Demo | 3분 | 품질 gate/reject 이유 → clean batch 승인 → rollback |
| B. Full Demo | 5–7분 | Inspection → ETL/staging → promotion/rollback |
| C. Optional Airflow | 1–2분 | configured HTTP feed의 manual orchestration |

준비 시간은 시연 시간에 포함하지 않는다.

## 2. 시연 전 준비

### 안전한 local 환경

1. local demo DB만 사용한다. `docker compose down`은 container와 network만 종료하며 named volume의 데이터는 남는다. 이 경로를 “매번 초기화되는 DB”라고 부르지 않는다.
2. `.env.local`과 `.env`는 Git에 추가하지 않고, secret·database URL은 출력·스크린샷·문서에 남기지 않는다.
3. `CHANGE_ME`는 JWT secret으로 사용할 수 없다. 아래 `<…>`는 현재 터미널에서만 넣는 placeholder다.

```powershell
cd C:\study\catalogguard-lite
.\.venv\Scripts\Activate.ps1
Copy-Item .env.local.example .env.local
notepad .env.local
docker compose --env-file .env.local -f compose.local.yaml up -d db redis
```

현재 `compose.local.yaml`은 API service에 `CATALOGGUARD_JWT_SECRET`을 전달하지 않는다. 따라서 로그인까지 보여 주는 데모에서는 API를 호스트 프로세스로 시작한다. 이는 설정 누락을 숨기지 않기 위한 현재 제약이다.

```powershell
# 현재 PowerShell에서만 설정하고 출력하지 않는다.
$env:DATABASE_URL = "<LOCAL_DEMO_POSTGRES_URL>"
$env:CATALOGGUARD_JWT_SECRET = "<YOUR_LOCAL_JWT_SECRET>"

python -m alembic upgrade head
python scripts/create_user.py --username demo_operator --role operator
python -m uvicorn api.main:app --host 127.0.0.1 --port 8001 --no-access-log
```

별도 PowerShell에서 Streamlit을 시작한다.

```powershell
cd C:\study\catalogguard-lite
.\.venv\Scripts\Activate.ps1
$env:CATALOGGUARD_API_BASE_URL = "http://127.0.0.1:8001"
python -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501
```

`http://127.0.0.1:8001/ready`에서 `database: ok`를 먼저 확인한 뒤 `http://127.0.0.1:8501`을 연다. `create_user.py`는 비밀번호를 대화형으로 입력받을 수 있으므로 shell history에 비밀번호를 넣지 않는다.

### 사용할 기존 데이터

| 목적 | fixture | 실제로 확인할 것 |
|---|---|---|
| Inspection | `data/dev/category_mismatch_test.csv` | 허용 category 검증, 상품명·category 불일치, 상품 group category 일관성 |
| 선택 Inspection | `data/dev/price_anomaly_test.csv` | 가격 이상치 2건; 다른 category 오류와 구분해 설명 |
| 선택 Inspection | `data/dev/privacy_masking_test.csv` | 이메일·전화번호·식별번호 **의심 패턴 탐지**와 화면 미리보기 마스킹 |
| ETL reject | `tests/fixtures/e2e/etl_browser_vendor.csv` | 3행 중 2행 staging, 1행 reject; reject 상세의 민감값 비노출 |
| Promotion | `tests/fixtures/e2e/etl_browser_promotion_vendor.csv` | clean 2행 batch의 preview, 승인, audit, rollback |

개인정보 의심 패턴 탐지와 마스킹은 다르다. 검수 규칙은 이메일·전화번호·식별번호 같은 패턴을 찾고, 화면 미리보기와 ETL reject 상세/API는 민감값을 그대로 보여 주지 않는다. 이는 모든 개인정보를 자동 익명화한다는 뜻이 아니다.

### ETL batch 준비 (타이머 시작 전)

아래 명령은 Full Demo에서 보여 줄 두 batch를 미리 만든다. `output\demo` 생성물은 local artefact이며 Git에 추가하지 않는다.

```powershell
New-Item -ItemType Directory -Force .\output\demo | Out-Null

python -m etl.cli `
  --input .\tests\fixtures\e2e\etl_browser_vendor.csv `
  --profile .\config\etl\sample_marketplace_vendor\v2.json `
  --output .\output\demo\catalogguard_ready.csv `
  --rejects .\output\demo\rejected_rows.csv `
  --summary .\output\demo\etl_summary.json
python -m etl.load_cli --input .\output\demo\catalogguard_ready.csv --rejects .\output\demo\rejected_rows.csv --summary .\output\demo\etl_summary.json

python -m etl.cli `
  --input .\tests\fixtures\e2e\etl_browser_promotion_vendor.csv `
  --profile .\config\etl\sample_marketplace_vendor\v2.json `
  --output .\output\demo\catalogguard_promotion_ready.csv `
  --rejects .\output\demo\promotion_rejected_rows.csv `
  --summary .\output\demo\promotion_etl_summary.json
python -m etl.load_cli --input .\output\demo\catalogguard_promotion_ready.csv --rejects .\output\demo\promotion_rejected_rows.csv --summary .\output\demo\promotion_etl_summary.json
```

첫 fixture의 예상 요약은 `3 / 2 / 1`(전체/정상/reject)이고, clean fixture는 `2 / 2 / 0`이다. 같은 input·profile name·version을 다시 적재하면 SHA-256 identity 때문에 `신규 적재: no`가 정상이다.

## A. 3-minute Quick Demo

시작 전 두 ETL batch와 로그인은 준비한다.

| 시간 | 실행 · 화면에서 확인 | 설명 · 정상 결과 |
|---|---|---|
| 0:00–0:25 | “공급사 CSV는 바로 운영 catalog로 가지 않는다”를 말하고 `ETL 적재 이력`을 연다. | 변환·품질 gate를 거쳐 staging에 먼저 저장한다. |
| 0:25–1:05 | `etl_browser_vendor.csv` batch의 `3 / 2 / 1`, reject 오류 코드·필드·마스킹된 원본을 보여 준다. | 가격을 숫자로 바꿀 수 없고 음수 재고인 행은 staging에 들어가지 않는다. reject 상세에는 원문 이메일·전화번호·계좌/식별번호 형태를 노출하지 않는다. |
| 1:05–2:05 | `etl_browser_promotion_vendor.csv` clean batch를 직접 선택해 `운영 반영 미리보기`를 연다. checkbox 전 비활성 버튼과 상품별 변경 전·후를 보인다. | preview는 DB를 바꾸지 않는다. 확인 뒤에만 `운영 상품에 반영`이 가능하고, 성공하면 promotion audit이 남는다. |
| 2:05–2:50 | 성공 Promotion의 `Rollback Preview`를 열고 checkbox 후 실행한 뒤 rollback change audit을 연다. | rollback도 preview와 별도 승인 절차를 거친다. delete/restore와 실행 사용자가 audit에 남는다. |
| 2:50–3:00 | 한 줄로 마무리한다. | “문제를 분리하고, 사람이 확인한 변경만 반영하며, 되돌린 기록도 남깁니다.” |

## B. 5–7-minute Full Demo

### 1. Inspection으로 문제를 먼저 보인다 (약 1분)

- **실행:** `CSV 검수`에서 `data/dev/category_mismatch_test.csv`를 업로드하고 `즉시 검수`를 선택한다.
- **화면에서 확인:** 업로드 미리보기, 검수 요약, `카테고리 오류`·`상품명·카테고리 불일치`·`상품 그룹 카테고리 불일치` 필터를 보여 준다.
- **설명:** CatalogGuard는 정답 category를 추론하거나 자동 수정하지 않고, 사람이 확인할 품질 근거를 남긴다.
- **정상 결과:** 세 rule의 결과가 필터와 상세 목록에서 보인다.

시간이 남으면 `price_anomaly_test.csv`의 가격 이상치 2건, 또는 `privacy_masking_test.csv`의 의심 패턴 탐지와 미리보기 마스킹을 **별도 1분**으로 보여 준다. 이는 기본 흐름에 중복해 넣지 않는다.

### 2. ETL 결과와 staging을 확인한다 (약 1–2분)

- **실행:** 준비한 첫 batch를 `ETL 적재 이력`에서 선택한다.
- **화면에서 확인:** `전체 행 3 / 정상 적재 2 / 변환 거부 1`, staging 상품, reject 오류와 마스킹된 원본을 연다.
- **설명:** `etl.cli`의 `run_pipeline()`이 standard/reject CSV를 만들고, `etl.load_cli`의 `load_standard_csv()`가 batch 단위 staging 적재를 한다.
- **정상 결과:** 같은 bytes를 다시 적재해도 기존 batch를 재사용하며 staging/reject 행을 중복하지 않는다.

### 3. clean batch만 promotion한다 (약 2분)

- **실행:** `etl_browser_promotion_vendor.csv` clean batch를 직접 선택하고 `운영 반영 미리보기`를 누른다.
- **화면에서 확인:** 반영 가능 상태, 신규/수정/변경 없음, 상품별 전·후 값, checkbox 전 비활성 버튼을 확인한다.
- **설명:** reject 또는 품질 조건을 만족하지 못한 batch는 promotion 대상이 아니다. preview hash는 승인 시점의 데이터가 바뀌지 않았는지 확인한다.
- **정상 결과:** 확인 뒤에만 promotion이 성공하고, `Promotion 실행 이력`에 `succeeded`와 변경 audit이 보인다.

### 4. rollback을 audit으로 마무리한다 (약 1–2분)

- **실행:** 성공 Promotion에서 `Rollback Preview`를 확인하고 별도 checkbox로 승인해 실행한다.
- **화면에서 확인:** 복구·삭제·충돌 수, 실행 사용자, `상품 Rollback 변경 Audit`을 연다.
- **설명:** rollback은 undo 버튼이 아니라 현재 상태를 다시 확인하는 안전한 변경 절차다.
- **정상 결과:** `succeeded` rollback run과 original audit에 연결된 delete/restore 기록이 남는다.

## C. Optional Airflow: manual trigger only

Airflow는 configured HTTP feed를 기존 ETL/staging 경로로 orchestration하는 선택 기능이다. `catalogguard_http_feed_to_staging`은 `schedule=None`인 manual DAG이며, application DB와 Airflow metadata DB는 분리된다. promotion을 자동화하지 않는다.

Airflow용 `.env`가 이미 안전하게 구성된 경우에만 실행한다.

```powershell
docker compose --env-file .env -f airflow/compose.yaml up --build -d
docker compose --env-file .env -f airflow/compose.yaml exec airflow-scheduler airflow dags list-import-errors
docker compose --env-file .env -f airflow/compose.yaml exec airflow-scheduler airflow dags trigger catalogguard_http_feed_to_staging --conf '{"profile_id":"sample_fashion_vendor_v1"}'
```

- **화면에서 확인:** Airflow UI/API `http://localhost:8088`에서 DAG와 단일 task `ingest_configured_http_feed_to_staging`를 확인한다.
- **설명:** configured feed만 읽고 기존 ETL을 재사용한다. retry는 transient HTTP/network와 제한적인 transient DB 오류만 대상으로 한다.
- **정상 결과:** 같은 bytes면 기존 staging batch를 재사용한다. Airflow는 기본 데모와 독립적으로 종료한다.

## 3. 검증 근거와 최소 troubleshooting

이 흐름은 `scripts/run_etl_browser_e2e.py`와 `tests/e2e/test_etl_browser_e2e.py`의 Chromium 검증에 근거한다. E2E는 격리 test DB에서 migration, ETL/staging, FastAPI·Streamlit health, reject masking, promotion/rollback과 PostgreSQL audit을 확인한다. 이는 수동 demo의 사전 검증 근거이지, E2E 전용 setup을 면접 시연의 필수 조건으로 만들지는 않는다. Web ETL 업로드 화면 자체는 별도 Chromium E2E 범위가 아니다.

| 증상 | 확인 / 조치 |
|---|---|
| `/ready` 실패 | local demo DB 연결과 Alembic 적용 여부를 확인한다. 값을 출력하지 않는다. |
| 로그인 실패 | API 프로세스의 실제 JWT secret, `CHANGE_ME` 미사용, operator 존재 여부를 확인한다. |
| promotion 차단 | reject·품질 조건·duplicate identity의 차단 사유를 보여 주고 clean fixture를 사용한다. DB를 직접 수정하지 않는다. |
| rollback 충돌 | 새 preview를 열고 conflict count를 설명한다. 강제 재시도하지 않는다. |
| Airflow DAG 미노출 | `airflow dags list-import-errors`와 DAG processor를 확인한다. raw URL·secret을 CLI argument로 넘기지 않는다. |

## 4. 종료, 인터뷰 메시지, 한계

서비스 종료는 데이터 초기화가 아니다.

```powershell
docker compose --env-file .env.local -f compose.local.yaml down
docker compose --env-file .env -f airflow/compose.yaml down
```

자동 reset, volume 삭제, `DROP DATABASE` 명령은 제공하지 않는다. 깨끗한 재시연은 별도 local demo DB를 준비해 진행한다.

면접에서는 다음 순서로 말한다.

1. 상품 데이터의 형식·품질 문제를 먼저 찾는다.
2. 검수·표준화와 reject 분리로 문제가 있는 행을 운영 반영 경로에서 제외한다.
3. SHA-256 identity로 같은 input의 staging 중복을 막는다.
4. preview와 명시적 승인으로 변경을 통제한다.
5. rollback과 append-only audit으로 변경·복구 이력을 남긴다.

이 프로젝트는 검증된 MVP다. 대용량 운영 데이터·실제 외부 공급사·운영 catalog 반영을 검증했다고 주장하지 않는다. 규칙 기반 검수는 AI 자동 수정이나 최종 업무 판단을 대체하지 않으며, 의심 패턴 탐지는 오탐·미탐 가능성이 있다.

최신 main에서는 `test`, `browser-e2e`, `kubernetes-smoke`, `terraform-validate`, `airflow-smoke` 다섯 CI job의 success를 확인한다. 세부 설계와 최신 실행 결과는 아래 문서를 기준으로 한다.

- [README](../README.md)
- [ETL MVP 문서](etl_mvp.md)
- [Catalog promotion 설계](catalog_promotion_design.md)
- [포트폴리오 상세 문서](portfolio_project.md)
