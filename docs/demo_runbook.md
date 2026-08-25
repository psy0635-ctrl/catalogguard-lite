# CatalogGuard Lite Release / Portfolio Demo Runbook

> 공급사 상품 CSV는 형식과 품질이 제각각이다. CatalogGuard는 이를 검수·표준화하고, 문제가 있는 행은 reject로 분리하며, 확인된 staging batch만 사람이 승인해 catalog에 반영한다. 필요하면 변경 audit을 보며 rollback한다. 운영자가 판단에 쓰는 근거로 ETL 품질 요약·추이·직전 배치 대비 변화와 운영 catalog 대비 차이를 **조회 전용**으로 함께 제공한다. 이 문서는 기존 합성 fixture와 **격리된 local demo DB**로 이 MVP 흐름을 설명하는 발표용 런북이다.

## 1. 진행 범위

```text
[반영 경로]
품질 문제 확인 → ETL 변환 / reject 분리 → staging 적재
→ preview + 명시적 승인 → promotion audit → rollback audit

[관찰 경로] 조회 전용. 순서가 강제되지 않고, 필요할 때 확인한다.
ETL 품질 요약 / 최근 품질 추이 / 직전 배치 대비 변화·주요 오류 코드
운영 catalog와 이번 배치 staging 상품의 차이
```

- 실제 운영 데이터, 외부 공급사 URL, secret, raw database URL은 사용하거나 표시하지 않는다.
- staging은 운영 상품을 직접 덮어쓰지 않으며, promotion·rollback 모두 로그인한 `operator`의 확인이 필요하다.
- `ETL 품질 관찰`과 `상품 동기화 차이`는 **조회 전용**이다. promotion을 차단하거나 자동으로 되돌리지 않고, 임계값 판정·자동 알림도 하지 않는다. 반영 가능 여부는 기존 Promotion Preview 정책만 판단한다.
- Airflow HTTP feed DAG는 자동 실행이 아닌 선택적 manual trigger다.
- ETL 프로필의 **정의와 버전 archive**는 계속 `config/etl` JSON archive와 코드 registry가 source of truth다. PostgreSQL에 저장하는 것은 신규 실행에 적용할 **runtime current-state**와 **성공한 운영 명령의 append-only 이력** 두 가지뿐이며, 비활성화는 신규 ETL 실행만 막고 과거 이력과 조회 화면은 그대로 둔다.

| 구간 | 시간 | 핵심 |
|---|---:|---|
| A. Quick Demo | 3분 | 품질 관찰 → reject 이유 → clean batch 승인 → rollback |
| B. Full Demo | 6–8분 | Inspection → ETL/staging → 품질 관찰 → promotion → 동기화 차이 → rollback |
| C. Optional Profile Ops | 1–2분 | 프로필 runtime activation 조회·비활성화·reset·운영 이력 확인 |
| D. Optional Airflow | 1–2분 | configured HTTP feed의 manual orchestration |

C와 D는 선택 구간이다. Quick Demo 3분을 늘리지 않으며, 핵심 품질·promotion 흐름을 밀어내지 않는다.

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
| 품질 관찰 | 위 두 fixture로 만든 batch 2개(같은 profile) | 최신·직전 Reject 비율, 변화량 `%p`, 방향, 주요 오류 코드 |
| 동기화 차이 | promotion 이후 첫 batch의 `적재 배치 상세` | 신규/변경/동일/`이번 배치 미관측` 건수와 reject 경고 |

개인정보 의심 패턴 탐지와 마스킹은 다르다. 검수 규칙은 이메일·전화번호·식별번호 같은 패턴을 찾고, 화면 미리보기와 ETL reject 상세/API는 민감값을 그대로 보여 주지 않는다. 이는 모든 개인정보를 자동 익명화한다는 뜻이 아니다.

### ETL batch 준비 (타이머 시작 전)

아래 명령은 Full Demo에서 보여 줄 두 batch를 미리 만든다. **순서대로** 실행한다. 나중에 적재한 clean batch가 `ETL 품질 관찰`의 “최신 배치”가 되기 때문이다. `output\demo` 생성물은 local artefact이며 Git에 추가하지 않는다.

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

두 batch 모두 같은 profile(`sample_marketplace_vendor` v2)로 실행한다. `etl.load_cli`가 summary JSON의 `total_rows`·`rejected_rows`·`error_counts`를 함께 저장하므로, 이 두 batch는 품질 집계가 가능하고 **같은 공급사 이름 아래 비교 가능한 batch 2개**가 된다. `ETL 품질 관찰`은 이 두 batch를 최신/직전으로 비교한다. 품질 요약 저장 이전에 만들어진 legacy batch는 이 비교에서 제외된다.

새로 준비한 demo DB에서 위 두 batch만 적재했다면 화면 값은 다음과 같다.

| 화면 | 예상 값 |
|---|---|
| `ETL 품질 요약` | 실행 배치 2 · 품질 집계 가능 배치 2 · 전체 입력 5 · 정상 적재 4 · Reject 1 · Reject 비율 20.00% |
| `최근 ETL 품질 추이` | 배치 두 점: 33.33% → 0.00% |
| `ETL 품질 관찰`(`sample_marketplace_vendor`) | 최신 0.00% · 직전 33.33% · 변화량 `-33.33%p` · 방향 `개선` |
| `주요 오류 코드` | `INVALID_PRICE` 1건(발생 배치 1) · `NEGATIVE_STOCK` 1건(발생 배치 1) |

이미 다른 batch가 들어 있는 DB에서는 값이 달라진다. 숫자를 외워 말하지 말고 화면에 보이는 값을 그대로 읽는다.

### ETL 프로필 activation 확인 (타이머 시작 전)

Quick Demo와 Full Demo가 모두 `sample_marketplace_vendor_v1` 프로필을 쓰므로, 시작 전에 이 프로필의 **effective activation이 active v2인지** 확인한다. 비활성 상태로 남아 있으면 준비 단계의 `etl.load_cli`는 통과하더라도 화면에서 신규 ETL 실행이 `409`로 막힌다.

`ETL 적재 이력` 탭 → `ETL 프로필 운영 관리`에서 다음을 본다.

| 항목 | 기대 값 |
|---|---|
| 상태 | `🟢 활성` |
| 실제 적용 버전 | `v2` |
| 배포 기본 버전 | `v2` |
| 런타임 설정 | `런타임 override 없음 (배포 기본값 사용)` 또는 `v2` |

아래 `C. Optional Profile Ops`를 시연하지 않는다면, **데모 시작 직전에 이 프로필을 비활성화하지 않는다.** C를 시연했다면 마지막 단계에서 `실제 적용 버전`이 `v2`로 돌아왔는지 확인하고 다음 구간으로 넘어간다.

## A. 3-minute Quick Demo

시작 전 두 ETL batch와 로그인은 준비한다. 장면은 네 개로 유지한다. `상품 동기화 차이`는 Full Demo에서만 보여 준다. 운영 catalog가 비어 있는 상태에서는 보여 줄 차이가 거의 없기 때문이다.

`ETL 적재 이력` 탭은 위에서부터 `ETL 품질 요약` → `최근 ETL 품질 추이` → `ETL 품질 관찰` → 적재 이력 목록 순서다. 화면 순서대로 내려가면 스크롤을 되돌리지 않아도 된다.

| 시간 | 실행 · 화면에서 확인 | 설명 · 정상 결과 |
|---|---|---|
| 0:00–0:40 | “공급사 CSV는 바로 운영 catalog로 가지 않는다”를 말하고 `ETL 적재 이력`을 연다. 상단의 `ETL 품질 요약`·`최근 ETL 품질 추이`를 보고, `ETL 품질 관찰`에서 `sample_marketplace_vendor`를 선택한다. | 변환·품질 gate를 거쳐 staging에 먼저 저장한다. 최신 배치와 직전 배치의 Reject 비율, 변화량 `%p`, 방향, 주요 오류 코드가 보인다. 준비한 두 batch만 있으면 `-33.33%p`·`개선`이다. |
| 0:40–1:20 | 목록에서 `etl_browser_vendor.csv` batch를 선택해 `상세 조회`를 누르고, `3 / 2 / 1`과 오류 코드별 건수, reject 상세의 마스킹된 원본을 보여 준다. | 가격을 숫자로 바꿀 수 없고 음수 재고인 행은 staging에 들어가지 않는다. reject 상세에는 원문 이메일·전화번호·계좌/식별번호 형태를 노출하지 않는다. |
| 1:20–2:20 | `etl_browser_promotion_vendor.csv` clean batch를 직접 선택해 `운영 반영 미리보기`를 연다. checkbox 전 비활성 버튼과 상품별 변경 전·후를 보인다. | preview는 DB를 바꾸지 않는다. 확인 뒤에만 `운영 상품에 반영`이 가능하고, 성공하면 promotion audit이 남는다. |
| 2:20–2:50 | 성공 Promotion의 `Rollback Preview`를 열고 checkbox 후 실행한 뒤 rollback change audit을 연다. | rollback도 preview와 별도 승인 절차를 거친다. delete/restore와 실행 사용자가 audit에 남는다. |
| 2:50–3:00 | 한 줄로 마무리한다. | “문제를 분리하고, 사람이 확인한 변경만 반영하며, 되돌린 기록도 남깁니다.” |

첫 구간 대사 예시: “이 화면은 전체 품질 점수가 아니라 최근 ETL 배치의 Reject 흐름을 보는 화면입니다. 방향이 좋아졌다·나빠졌다로만 표시되고, 자동으로 막거나 되돌리지는 않습니다.”

## B. 6–8-minute Full Demo

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

### 3. 품질을 한 흐름으로 관찰한다 (약 30–60초)

세 화면을 따로 설명하지 않고 한 번에 이어서 말한다. 모두 조회 전용이며 promotion 순서를 강제하지 않는다.

- **실행:** 탭 상단으로 올라가 `ETL 품질 요약` → `최근 ETL 품질 추이` → `ETL 품질 관찰` 순으로 본다. `ETL 품질 관찰`의 `관찰할 공급사`에서 `sample_marketplace_vendor`를 선택한다.
- **화면에서 확인:** 요약에서 전체 Reject 비율, 추이에서 배치별 Reject 비율 변화, 관찰에서 최신·직전 Reject 비율과 변화량 `%p`, 방향, `주요 오류 코드`(발생 건수·발생 배치 수)를 본다.
- **설명:** “전체적으로 Reject가 얼마나 나오는지, 배치별로 어떻게 움직였는지, 그리고 같은 공급사의 최신 배치가 직전보다 좋아졌는지 나빠졌는지를 순서대로 봅니다.”
- **정상 결과:** 준비한 두 batch만 있으면 요약 `20.00%`, 추이 `33.33% → 0.00%`, 관찰 `-33.33%p / 개선`, 오류 코드 `INVALID_PRICE`·`NEGATIVE_STOCK` 각 1건이다.

`관찰할 공급사` 목록은 위 검색어와 무관하다. 품질 정보가 기록된 ETL 적재 이력 전체에서 공급사 이름을 그대로 가져와 정확히 일치하는 이름으로만 비교한다. 화면 목록 10건 안에 없는 과거 공급사도 품질 데이터가 있으면 고를 수 있다. 면접 답변용 한 줄: “화면 pagination과 비교 대상 identity를 분리한 설계입니다.”

방향이 `악화`로 나오는 경우의 대사: “악화라고 표시돼도 자동 장애 판정은 하지 않습니다. 직전 배치보다 Reject 비율이 올랐다는 관찰 결과일 뿐이고, 공급사나 시즌마다 기준이 다르기 때문입니다.” 자동 차단·자동 rollback·자동 알림·임계값 판정은 없다.

### 4. clean batch만 promotion한다 (약 2분)

- **실행:** `etl_browser_promotion_vendor.csv` clean batch를 직접 선택하고 `운영 반영 미리보기`를 누른다.
- **화면에서 확인:** 반영 가능 상태, 신규/수정/변경 없음, 상품별 전·후 값, checkbox 전 비활성 버튼을 확인한다.
- **설명:** reject 또는 품질 조건을 만족하지 못한 batch는 promotion 대상이 아니다. preview hash는 승인 시점의 데이터가 바뀌지 않았는지 확인한다.
- **정상 결과:** 확인 뒤에만 promotion이 성공하고, `Promotion 실행 이력`에 `succeeded`와 변경 audit이 보인다.

### 5. 운영 catalog와의 차이를 확인한다 (약 1분)

promotion으로 운영 catalog에 같은 공급사 상품이 생긴 뒤에 보여 준다. 그래야 `이번 배치 미관측`이 실제로 나타난다. 이 순서는 절차상의 gate가 아니라 화면을 의미 있게 만들기 위한 시연 순서일 뿐이다.

- **실행:** 목록에서 첫 batch(`etl_browser_vendor.csv`)를 선택하고 `상세 조회`를 누른 뒤, `적재 배치 상세` 안의 `상품 동기화 차이`를 연다.
- **화면에서 확인:** `신규`·`변경`·`동일`·`이번 배치 미관측`(API 상태 이름 `new`/`changed`/`unchanged`/`not_observed_in_batch`) 건수, 필드별 변경 건수, 상품별 상태 목록을 본다. reject가 있는 batch에서는 “원본 입력 중 N개 행이 ETL 변환 과정에서 제외되었습니다” 경고가 함께 뜬다.
- **설명:** “정상 staging에 적재된 상품만 지금 운영 catalog와 비교한 조회 전용 보고서입니다. 이 화면은 운영 상품을 바꾸지 않습니다.”
- **정상 결과:** 위 순서로 진행하면 `신규 2 / 변경 0 / 동일 0 / 이번 배치 미관측 2`와 reject 경고가 보인다. 미관측 2건은 앞 단계에서 반영한 promotion batch의 상품이다.

`이번 배치 미관측`에 대한 대사: “이 상품이 이번 배치에서 안 보인다고 삭제된 상품으로 판단하지 않습니다. 현재 feed가 전체 스냅샷인지 변경분인지 알 수 없고, reject된 행 때문에 빠졌을 수도 있기 때문입니다.” 삭제·판매 종료·재고 없음을 뜻하지 않고, 자동 삭제 대상도 아니다.

### 6. rollback을 audit으로 마무리한다 (약 1–2분)

- **실행:** 성공 Promotion에서 `Rollback Preview`를 확인하고 별도 checkbox로 승인해 실행한다.
- **화면에서 확인:** 복구·삭제·충돌 수, 실행 사용자, `상품 Rollback 변경 Audit`을 연다.
- **설명:** rollback은 undo 버튼이 아니라 현재 상태를 다시 확인하는 안전한 변경 절차다.
- **정상 결과:** `succeeded` rollback run과 original audit에 연결된 delete/restore 기록이 남는다.

## C. Optional Profile Ops: runtime activation과 운영 이력 (1–2분)

선택 구간이다. Quick Demo에 넣지 않는다. 보여 주는 것은 "프로필을 운영자가 재배포 없이 내리고 되돌릴 수 있고, 그 명령이 기록으로 남는다"는 것이며, 프로필 JSON을 편집하는 화면이 아니다. 중간에 **Deactivate와 Reset이 다른 동작**이라는 점이 드러나고, 마지막에 두 명령이 이력에 어떻게 남는지 확인한다.

| 단계 | 실행 · 화면에서 확인 | 설명 |
|---|---|---|
| 1 | `ETL 적재 이력` 탭에서 `ETL 프로필 운영 관리`를 연다. | 실행 화면과 분리된 별도 관리 구획이다. |
| 2 | `관리할 ETL 프로필`에서 `마켓플레이스 공급사 샘플`(`sample_marketplace_vendor_v1`)을 고른다. | 이 목록은 비활성 프로필까지 포함한다. 위쪽 `ETL 실행 프로필` selector는 함께 바뀌지 않는다. |
| 3 | `상태`를 본다. | 지금 활성인지 비활성인지. |
| 4 | `배포 기본 버전`을 본다. | 코드/배포 registry가 정한 기본값이다. |
| 5 | `실제 적용 버전`을 본다. | 지금 신규 실행에 실제로 쓰이는 값이다. |
| 6 | `런타임 설정`을 본다. | override가 없는지, 특정 버전인지, 명시적 비활성인지. |
| 7 | operator 확인 checkbox를 선택한다. | 신규 ETL을 즉시 막는 조작이라 확인을 한 번 더 받는다. |
| 8 | `비활성화`를 누른다. | `PUT .../activation`에 `active_version: null`을 보낸다. |
| 9 | 무엇이 막히는지 설명한다. | 막히는 것은 **신규 ETL 실행**뿐이다(업로드·S3·HTTP feed·Airflow). |
| 10 | 무엇이 남는지 설명한다. | 과거 적재 이력, staging 조회, 품질 요약·추이·관찰, 동기화 차이, promotion·rollback 이력, 버전 archive는 그대로다. |
| 11 | `런타임 설정 초기화` 구획의 안내를 읽는다. | `되돌린 뒤 실제 적용 버전: v2 — 지금 비활성인 이 프로필이 다시 활성화됩니다.` 누르기 전에 결과를 먼저 보여 준다. |
| 12 | 확인 checkbox를 선택하고 `배포 기본값으로 되돌리기`를 누른다. | `DELETE .../activation`이 나간다. 비활성화와 달리 **override row 자체를 지운다**. |
| 13 | `런타임 설정`과 `실제 적용 버전`을 다시 본다. | `런타임 override 없음 (배포 기본값 사용)` / `v2`. 배포 기본값이 `v2`이므로 프로필이 다시 활성이고, 다음 구간을 이어서 시연할 수 있는 상태다. |
| 14 | 아래 `Activation 운영 이력`을 본다. | 방금 실행한 두 명령이 최신순으로 보인다. `배포 기본값으로 되돌리기`가 위, `비활성화`가 그 아래다. |
| 15 | 이력의 `사용자`와 `시각`을 짚는다. | 누가 언제 그 명령을 실행했는지 남는다. reset은 current-state row를 지우지만, 명령 자체는 이 이력에 보존된다. |
| 16 | reset 행의 `실제 적용 버전`을 짚는다. | `v2`다. 되돌리기는 비활성화가 **아니라** override 제거이므로, 배포 기본값이 활성이면 실제 적용 버전이 남는다. |

대사 예시: “프로필 정의 JSON을 수정한 것이 아니라 PostgreSQL에 신규 실행 상태만 저장했습니다. 서버를 재시작해도 같은 상태를 사용합니다.”

`런타임 설정`에 대한 대사: “값을 `null`로 보낸 것은 배포 기본값으로 되돌리는 reset이 아니라 ‘운영자가 명시적으로 내렸다’는 별도 상태입니다. 배포 기본값으로 되돌리는 것은 override row 자체를 지우는 별도 `DELETE`이고, 그래서 두 동작을 다른 버튼으로 나눴습니다.”

reset을 누르기 전 대사: “이 버튼은 단순한 정리가 아닙니다. 지금 이 프로필은 운영자가 명시적으로 내려 둔 상태인데, override를 지우면 배포 기본값 `v2`가 다시 적용되어 **바로 실행 가능해집니다.** 그래서 화면이 되돌린 뒤 적용될 버전을 먼저 보여 주고, 비활성화와 같은 확인 절차를 거칩니다.”

운영 이력에 대한 대사: “위쪽 현재 상태는 지금 무엇이 적용되는지를 보여 주고, 아래 운영 이력은 누가 어떤 성공한 명령을 실행했는지를 보여 줍니다. reset은 현재 상태 row를 지우기 때문에 위쪽 `마지막 변경 사용자`는 비지만, 그 reset을 누가 실행했는지는 아래 이력에 남습니다.”

새 DB이거나 `20260823_0015`를 막 적용한 직후라면 이력이 비어 있을 수 있다. 그때는 화면 안내 그대로 “**이 기능이 추가된 이후의 성공한 운영 명령부터 기록됩니다**”라고 말한다. 과거 기록이 자동으로 복원됐다고 말하지 않는다. 위 12~13단계를 먼저 실행하면 이력 두 줄이 생기므로, 비어 있는 상태로 시작했다면 그 순서로 보여 준다.

면접에서 더 물어보면 답할 내용(발표 대사로는 길다): 기록 단위가 “상태가 달라진 순간”이 아니라 “서버가 성공으로 처리한 운영 명령”이라, 같은 값을 다시 저장하거나 override가 없는 상태에서 reset해도 이력 한 줄이 남는다. 실패한 요청은 남지 않는다.

viewer 계정으로 로그인해 같은 화면을 열면 상태와 운영 이력은 모두 보이지만 변경 컨트롤이 없다는 점을 함께 보여 줄 수 있다. 화면에서 감추는 것은 편의 기능이고 실제 차단은 FastAPI가 한다.

### 말하면 안 되는 표현

| 하지 말 것 | 실제 |
|---|---|
| “비활성화하면 프로필이 삭제됩니다.” | Deactivate ≠ Delete. registry 항목과 버전 archive는 그대로 남는다. |
| “비활성화하면 과거 ETL 이력도 안 보입니다.” | 과거 적재 이력·품질·동기화·promotion/rollback 조회는 모두 유지된다. |
| “`null`을 보내면 deployment default로 reset됩니다.” | `null`은 명시적 비활성이다. 배포 기본값으로 되돌리려면 별도 `DELETE .../activation`을 쓴다. |
| “reset은 그냥 프로필을 끄는 기능입니다.” | 반대다. reset은 override를 **제거**하는 것이라, 배포 기본값이 활성이면 프로필이 다시 활성화된다. |
| “reset하면 현재 상태 화면에 마지막 변경자가 그대로 남습니다.” | 지우는 것은 current-state row 하나이므로 그 row의 마지막 변경자·시각은 함께 사라진다. 그 reset 명령을 누가 실행했는지는 아래 `Activation 운영 이력`에 남는다. |
| “프로필 정의를 PostgreSQL에서 CRUD합니다.” | 정의와 버전 archive는 계속 `config/etl` JSON과 코드 registry다. Profile CRUD는 없다. |
| “`0015`를 적용하면 과거 activation 명령까지 복원됩니다.” | backfill하지 않는다. 이력은 `20260823_0015` 적용 이후의 성공한 명령부터 기록한다. current-state row 하나로는 과거에 무슨 일이 있었는지 알 수 없어 추측해 채우지 않았다. |
| “append-only라 DB에서 누구도 절대 수정·삭제할 수 없습니다.” | 애플리케이션에 이력 수정·삭제·purge API가 없다는 MVP 계약이다. DB superuser의 직접 `UPDATE`/`DELETE`까지 막는 WORM 저장소를 구현한 것은 아니다. |
| “같은 상태로 다시 저장하면 이력에는 아무것도 남지 않습니다.” | 기록 단위가 성공한 운영 명령이라 event가 추가된다. 상태 idempotency와 이력 idempotency는 다른 개념이다. |
| “Airflow는 어떤 경우에도 HTTP feed를 읽지 않습니다.” | pre-check 시점에 이미 inactive인 프로필은 `read_http_feed_csv()`를 호출하지 않는다. 다만 pre-check 뒤 deactivate되는 race에서는 fetch가 시작될 수 있고, `run_web_etl()`의 최종 activation 검사가 ETL load를 막는다. |

## D. Optional Airflow: manual trigger only

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

### 비활성 프로필과 retry 정책

이 DAG는 `sample_fashion_vendor_v1`을 trigger하므로, C 구간에서 내린 `sample_marketplace_vendor_v1`과는 다른 프로필이다. 같은 동작을 실제로 보이려면 관리 화면에서 `패션 공급사 샘플`을 먼저 비활성화한 뒤 trigger하고, 끝나면 v2로 되돌린다.

비활성 프로필로 이 DAG를 trigger하면 task는 전용 코드 `etl_profile_inactive`로 실패하고 **재시도하지 않는다**(`AirflowFailException`).

```text
inactive profile
-> etl_profile_inactive
-> no retry
```

Airflow와 로그에 노출되는 메시지는 안전한 코드 하나뿐이다.

```text
CatalogGuard HTTP feed ingestion failed [etl_profile_inactive]
```

`profile_id`, feed URL과 query, token, DB URL, 원본 예외는 노출하지 않는다.

대사 예시: “운영자가 일부러 내린 프로필은 network timeout이나 HTTP 5xx 같은 일시 장애와 다릅니다. 사람이 다시 켜기 전까지 재시도로 회복되지 않으므로 재시도하지 않습니다.”

Airflow HTTP feed 경로는 실행 전에 effective activation을 확인한다. 이미 inactive인 프로필이면 `read_http_feed_csv()`를 호출하지 않고 `etl_profile_inactive`로 끝난다. 다만 pre-check 뒤 운영자가 deactivate하면 HTTP fetch가 이미 시작될 수 있다. 이 race에서는 `run_web_etl()`의 최종 activation 재검사가 ETL load를 차단하며, 외부 HTTP 요청 동안 DB transaction이나 lock을 유지하지 않는 MVP 정책은 그대로다.

## 3. 검증 근거와 최소 troubleshooting

사전 검증 근거는 세 갈래다. 모두 수동 demo의 근거일 뿐이고, E2E 전용 setup을 면접 시연의 필수 조건으로 만들지는 않는다.

**A. ETL / Promotion / Rollback 브라우저 E2E** — `scripts/run_etl_browser_e2e.py`, `tests/e2e/test_etl_browser_e2e.py`. 격리 test DB에서 migration, ETL/staging 적재, FastAPI·Streamlit health, reject 상세 마스킹, promotion preview·승인·실행, rollback preview·실행과 PostgreSQL audit을 Chromium으로 확인한다.

**B. Web ETL CSV 업로드 브라우저 E2E** — `tests/e2e/test_web_etl_upload_browser_e2e.py`. operator 로그인, `ETL 실행 프로필` 선택(`sample_marketplace_vendor` v2), 공급사 CSV 파일 업로드, ETL 실행, 성공 batch ID 확인, PostgreSQL `ETLLoadRun`과 staging 상품 2건 확인, ETL 이력 검색, 배치 상세 조회를 Chromium으로 확인한다. `scripts/run_etl_browser_e2e.py`가 A와 함께 실행한다. 업로드 화면의 모든 기능이 아니라 위 경로만 검증한다.

**C. ETL 프로필 runtime activation과 운영 이력** — API integration test(`tests/test_api_etl_profile_activation.py`), API Client test(`tests/test_catalogguard_api_client.py`), Streamlit AppTest(`tests/test_etl_load_history_ui.py`), PostgreSQL 통합 테스트와 migration/service 테스트에 더해 전용 Chromium E2E(`tests/e2e/test_etl_profile_ops_browser_e2e.py`)가 있다. 실제 operator 로그인 뒤 `sample_fashion_vendor_v1`을 deployment default v2에서 deactivate하고, archived v1을 activate한 뒤 reset하여 v2로 복귀하는 UI 흐름을 검증한다. 각 단계에서 현재 상태와 append-only history를 화면과 PostgreSQL에서 함께 확인하고, test-only local DB cleanup으로 원래 current-state와 기존 history를 복원·보존한다. Profile CRUD, 동시 update 경쟁, production DB 또는 Chromium 외 브라우저는 이 E2E 범위가 아니다. Airflow의 `etl_profile_inactive` 분류는 `airflow/tests/test_catalogguard_http_feed_to_staging.py`에 있고, 전용 `airflow-smoke` job의 격리 Airflow image에서 실행된다(Airflow가 없는 일반 pytest run에서는 module 단위로 skip된다).

**D. ETL 품질 관찰 · 상품 동기화 차이** — ETL 품질 관찰은 전용 Chromium E2E(`tests/e2e/test_etl_quality_observability_browser_e2e.py`)로 확인한다. local disposable PostgreSQL에서 E2E 전용 공급사 품질 batch 두 건을 만든 뒤, operator 로그인 → 공급사 선택 → 최신/직전 Reject 비율·`%p` 변화량·방향·주요 오류 코드·관찰 batch를 실제 FastAPI·Streamlit에서 확인하고 DB/API 응답도 대조한다. fixture는 생성한 정확한 batch ID만 `finally`에서 정리한다. 상품 동기화 차이는 아직 Chromium E2E가 없으며 service 단위 테스트(`tests/test_catalog_reconciliation_service.py`, `tests/test_etl_query_service.py`), API 테스트(`tests/test_api_catalog_reconciliation.py`), Streamlit AppTest 기반 UI 테스트(`tests/test_etl_load_history_ui.py`)로 검증한다.

| 증상 | 확인 / 조치 |
|---|---|
| `/ready` 실패 | local demo DB 연결과 Alembic 적용 여부를 확인한다. 값을 출력하지 않는다. |
| 로그인 실패 | API 프로세스의 실제 JWT secret, `CHANGE_ME` 미사용, operator 존재 여부를 확인한다. |
| promotion 차단 | reject·품질 조건·duplicate identity의 차단 사유를 보여 주고 clean fixture를 사용한다. DB를 직접 수정하지 않는다. |
| rollback 충돌 | 새 preview를 열고 conflict count를 설명한다. 강제 재시도하지 않는다. |
| Airflow DAG 미노출 | `airflow dags list-import-errors`와 DAG processor를 확인한다. raw URL·secret을 CLI argument로 넘기지 않는다. |
| 신규 ETL 실행이 `inactive_profile`(`409`)로 막힘 | `ETL 프로필 운영 관리`에서 해당 프로필의 effective activation을 먼저 확인한다. DB를 직접 `UPDATE`하지 않는다. operator로 로그인해 보존 버전 중 하나를 다시 활성화한다. |
| 내린 프로필이 실행 selector에서 사라짐 | 정상 동작이다. 실행 목록은 지금 실행할 수 있는 프로필만 보여 준다. 관리 목록(`include_inactive=true`)에는 계속 남아 있으므로 거기서 다시 활성화한다. |
| Airflow task가 `etl_profile_inactive`로 실패 | retry 대상이 아니다. 장애가 아니라 의도적으로 내린 상태인지 관리 화면에서 확인하고, 맞다면 그대로 두거나 operator로 재활성화한 뒤 다시 trigger한다. |
| `ETL 품질 관찰`의 공급사 목록이 비어 있음 | 품질 정보가 기록된 ETL batch가 있는지 확인한다. 품질 요약 저장 이전 legacy batch만 있으면 후보에 나오지 않는다. |
| 방향이 `비교 데이터 없음`(no_baseline) | 같은 공급사 이름으로 품질 집계가 가능한 batch가 1개뿐인지 확인한다. 준비 명령 두 개를 모두 실행했는지 본다. |
| `이번 배치 미관측`이 많음 | reject 건수와 이 feed가 전체 snapshot인지 부분 feed인지 함께 확인한다. 삭제·판매 종료로 단정하지 않는다. |
| 새로 적재한 공급사가 관찰 목록에 없음 | Streamlit 화면을 다시 그린 뒤(rerun/새로고침) 확인한다. 목록은 조회 시점 값으로 캐시된다. |

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
6. 품질 관찰과 동기화 차이는 조회 전용으로 두어, 판단은 사람이 하고 시스템은 근거만 남긴다.
7. 프로필의 신규 실행 여부는 운영자가 재배포 없이 바꿀 수 있게 하되, 프로필 정의는 계속 code/config에 두고 비활성화는 삭제가 아니라 신규 실행 차단으로만 다룬다.

이 프로젝트는 검증된 MVP다. 대용량 운영 데이터·실제 외부 공급사·운영 catalog 반영을 검증했다고 주장하지 않는다. 규칙 기반 검수는 AI 자동 수정이나 최종 업무 판단을 대체하지 않으며, 의심 패턴 탐지는 오탐·미탐 가능성이 있다. 품질 관찰과 동기화 차이는 변화를 보여 줄 뿐 위험 임계값을 정하지 않고, 자동 차단·자동 rollback·자동 알림도 하지 않는다. Runtime activation은 신규 실행 상태만 다룬다. 성공한 activate·deactivate·reset 명령은 append-only 이력으로 남지만, 그 기록은 마이그레이션 `20260823_0015` 적용 이후의 명령부터이며 과거 이력을 backfill하지 않았다. 운영 관리·운영 이력의 Chromium E2E는 local disposable PostgreSQL과 Chromium 한 경로만 검증한다. Airflow는 pre-check 시점에 이미 inactive인 프로필의 외부 fetch를 시작하지 않지만, 직후 상태 변경 race에서 fetch 0회를 보장하지는 않으며 최종 guard가 ETL load를 차단한다.

최신 main에서는 `test`, `browser-e2e`, `kubernetes-smoke`, `terraform-validate`, `airflow-smoke` 다섯 CI job의 success를 확인한다. 세부 설계와 최신 실행 결과는 아래 문서를 기준으로 한다.

- [README](../README.md)
- [ETL MVP 문서](etl_mvp.md)
- [Catalog promotion 설계](catalog_promotion_design.md)
- [포트폴리오 상세 문서](portfolio_project.md)
