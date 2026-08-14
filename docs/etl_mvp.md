# 공급사 상품 CSV ETL MVP

## 목적

샘플 패션 공급사의 CSV를 CatalogGuard Lite 검수기가 읽을 수 있는 표준 CSV로 변환하고, 변환 결과와 요약 JSON을 PostgreSQL staging에 배치 적재한다. 파일 변환과 DB 적재는 CLI로 실행할 수 있고, 같은 로직을 Streamlit 업로드 화면과 FastAPI를 통해 웹에서도 실행할 수 있다.

기존 구조에서는 공급사 CSV를 CLI로 변환·적재한 뒤에야 ETL 적재 이력·promotion을 웹에서 확인할 수 있었다. 즉 ETL 실행은 CLI, ETL 이후의 조회·운영 반영은 웹으로 사용자 흐름이 나뉘어 있었다. Web ETL은 이 CLI 전용 구간을 없애기 위한 새 ETL 엔진이 아니라, 기존 `run_pipeline()`·`load_standard_csv()`를 FastAPI/Streamlit에 연결해 CSV 선택부터 staging 적재까지 웹 화면에서 끝낼 수 있게 만든 얇은 실행 경로다.

## 지원 프로필

`config/etl/sample_fashion_vendor_v1.json`은 첫 번째 합성 공급사 컬럼을 지원한다.

| 원본 컬럼 | CatalogGuard 대상 컬럼 | 처리 |
|---|---|---|
| `vendor_sku` | `product_group_id`, `product_id` | 공백 제거, 앞자리 0 유지 |
| `item_name` | `product_name` | 공백 제거 |
| `main_category` | `category` | 공백 제거 |
| `brand_name` | `seller` | 공백 제거 |
| `list_price` | `price` | `12,000`, `₩12,000`을 정수 문자열로 변환 |
| `discount_price` | `sale_price` | 비어 있으면 빈 값으로 유지하고, 입력되면 `price`와 같은 가격 파서로 변환 |
| `colour`, `size_name` | `color`, `size` | 공백 제거만 수행 |
| `quantity` | `stock` | 음수가 아닌 정수로 변환, 빈 값은 `0` |
| `description_text` | `description` | 공백 제거 |
| `image_link` | `image_path` | 공백 제거 |

샘플 공급사에는 별도 상품 그룹 컬럼이 없으므로 `vendor_sku`를 `product_group_id`와 `product_id`에 함께 매핑한다. 따라서 서로 다른 SKU가 하나의 그룹으로 잘못 묶이지 않는다. 동일 상품의 옵션 행을 그룹으로 묶어야 하는 공급사는 실제 그룹 식별 컬럼을 두 대상에 맞게 별도 프로필로 매핑해야 한다. 원본 `discount_price`는 표준 CSV의 선택 컬럼 `sale_price`로 변환되며, 기존 CSV에 해당 컬럼이 없어도 업로드·검수할 수 있다.

현재 저장소에는 서로 다른 컬럼 구조를 검증하기 위한 합성 공급사 프로필 2종이 있다.

| 프로필 | 그룹·SKU 구조 | 확인한 범위 |
|---|---|---|
| `sample_fashion_vendor_v1.json` | `vendor_sku` 하나를 `product_group_id`와 `product_id`에 함께 매핑 | 단일 공급사 SKU 기반 변환 |
| `sample_marketplace_vendor_v1.json` | `style_id`와 `sku_code`를 각각 `product_group_id`, `product_id`에 매핑 | 그룹 ID와 개별 SKU가 분리된 변환 |

### 두 번째 프로필 매핑

`config/etl/sample_marketplace_vendor_v1.json`은 다음 매핑을 사용한다.

| 원본 컬럼 | CatalogGuard 컬럼 |
|---|---|
| `style_id` | `product_group_id` |
| `sku_code` | `product_id` |
| `title` | `product_name` |
| `category_code` | `category` |
| `label` | `seller` |
| `regular_price` | `price` |
| `promo_price` | `sale_price` |
| `tone` | `color` |
| `fit_size` | `size` |
| `available_qty` | `stock` |
| `details` | `description` |
| `photo` | `image_path` |

`promo_price`와 `available_qty`는 선택 입력이다. 빈 `promo_price`는 빈 `sale_price`로 출력하고, 빈 `available_qty`는 기본값 `0`을 적용한다.

## 프로필 형식

```json
{
  "profile_name": "sample_fashion_vendor",
  "profile_version": "2",
  "source_columns": {"vendor_sku": ["product_group_id", "product_id"]},
  "required_source_columns": ["vendor_sku"],
  "defaults": {"stock": 0}
}
```

두 샘플 프로필의 `profile_version`은 카테고리별 필수 속성 정책을 적용하면서 `"1"`에서 `"2"`로 올렸다. 중복 배치 판정 기준이 `(input_file_sha256, profile_name, profile_version)`이므로, 버전을 그대로 두면 이미 적재한 공급사 CSV를 다시 올렸을 때 새 정책이 적용되지 않은 기존 배치가 그대로 반환된다. 같은 프로필로 같은 입력을 변환한 결과가 달라지므로 버전을 올린 것이며, 기존 `"1"` 배치 이력은 그대로 남는다. 파일명과 `profile_id` allowlist key는 API·UI 호환을 위해 `_v1`을 유지한다.

프로필은 CatalogGuard의 실제 표준 컬럼만 대상으로 허용한다. 대상 컬럼 중복, 필수 출력 컬럼 누락, 잘못된 JSON과 허용되지 않은 기본값은 파이프라인 전체 오류가 된다. 프로필은 단순 JSON 데이터만 해석하며 동적 코드 실행을 사용하지 않는다.

## 변환과 reject 기준

정상 행은 표준 CSV에 저장한다. 상품 ID·필수 원본값 누락, `price` 또는 `sale_price`로 매핑된 `discount_price`·`promo_price`의 가격 변환 실패·음수, 재고 정수 변환 실패·음수는 reject CSV에 저장한다.

### 카테고리별 필수 속성 정책

`required_source_columns`의 값이 비었는지는 그 컬럼이 매핑된 표준 컬럼과 행의 표준 카테고리를 함께 보고 판단한다. 정책의 단일 기준은 검수와 같은 `config/settings.py`의 `FASHION_CATEGORY_ATTRIBUTE_RULES`이며, 변환기는 `core/fashion_attribute_validator.py`의 `is_field_required_for_category()`를 호출하기만 한다. ETL이 같은 정책을 다시 구현하지 않는다.

따라서 `size`로 매핑된 원본 컬럼(`size_name`, `fit_size`)이 비어 있어도 `category`가 `BAG`이면 reject하지 않는다. `TOP`·`BOTTOM`·`OUTER`·`SHOES`는 기존과 같이 `MISSING_SOURCE_VALUE`로 reject한다. 카테고리가 비었거나 허용 목록에 없으면 어떤 패션 카테고리인지 추정하지 않고 기존처럼 필수로 처리하며, `bag`처럼 canonical 대문자가 아닌 표기도 별칭으로 정규화하지 않으므로 계속 필수다.

`size` 원본 컬럼은 `required_source_columns`에서 제거하지 않았다. 이 목록은 행 값 검사뿐 아니라 `run_pipeline()`의 공급사 CSV 헤더 존재 검사에도 쓰이므로, 제거하면 컬럼 자체가 없는 CSV를 걸러내지 못한다.

표준 CSV를 DB에 적재하는 `etl/db_loader.py`도 같은 함수를 사용한다. `config/settings.py`의 `REQUIRED_FIELDS`는 그대로 두고, 카테고리 정책에서 선택 값인 필드만 예외로 판단한다. `BAG`의 빈 `size`는 `catalog_products_staging.size`에 빈 문자열로 저장한다. 이 컬럼은 `NOT NULL`이지만 빈 문자열은 저장할 수 있어 DB migration은 추가하지 않았다. 할인 가격 원본이 비어 있으면 reject하지 않고 `sale_price`를 빈 값으로 출력한다. 한 행에 여러 오류가 있으면 `error_code`, `error_field`, `error_message`에 같은 순서의 JSON 배열로 함께 기록한다. 중복 상품 ID, 비표준 색상·사이즈, 가격 이상치, `sale_price`가 `price`보다 큰 상품 품질 문제는 정상 행으로 남겨 기존 CatalogGuard 검수기가 처리한다.

`rejected_rows.csv`는 오류가 없어도 헤더를 포함해 생성한다. `etl_summary.json`에는 프로필 이름·버전, 입력 파일명, 입력·출력·reject CSV SHA-256, 처리 건수, 오류 코드별 건수와 UTC 시각을 기록하며 절대 경로나 비밀값을 기록하지 않는다.

## CLI

```powershell
python -m etl.cli `
  --input .\tests\fixtures\etl\sample_vendor_mixed.csv `
  --profile .\config\etl\sample_fashion_vendor_v1.json `
  --output .\output\catalogguard_ready.csv `
  --rejects .\output\rejected_rows.csv `
  --summary .\output\etl_summary.json
```

정상 처리(오류 행 포함)는 종료 코드 0이다. 입력·프로필·출력 경로 오류는 안전한 메시지와 종료 코드 1로 끝난다. 인수 누락은 `argparse`의 종료 코드 2를 사용한다.

### 두 번째 공급사 CLI 예시

```powershell
.\.venv\Scripts\python.exe -m etl.cli `
  --input .\tests\fixtures\etl\sample_marketplace_vendor_mixed.csv `
  --profile .\config\etl\sample_marketplace_vendor_v1.json `
  --output .\.tmp_etl_marketplace\catalogguard_ready.csv `
  --rejects .\.tmp_etl_marketplace\rejected_rows.csv `
  --summary .\.tmp_etl_marketplace\etl_summary.json
```

`tests/fixtures/etl/sample_marketplace_vendor_mixed.csv`의 처리 결과는 입력 3행, 정상 변환 2행, reject 1행이다. 두 정상 행은 같은 `STYLE-100` 그룹 아래 `SKU-100-BLK-M`과 `SKU-100-WHT-L`을 각각 유지하며, 빈 `available_qty`는 stock `0`으로 변환된다. `가격문의`와 `-1` 재고가 함께 있는 행은 `INVALID_PRICE`와 `NEGATIVE_STOCK`로 reject된다. `59000`과 `69000`은 모두 변환 가능한 숫자이므로 정상 CSV에 남고, `69000 > 59000` 관계는 CatalogGuard 검수 단계에서 `sale_price_greater_than_price`로 탐지된다.

## 웹 ETL 실행

### 공통 ETL 재사용 구조

CLI와 Web은 실행 인터페이스만 다르고 핵심 ETL 로직은 하나다.

```text
CLI:
  etl/cli.py       -> run_pipeline()
  etl/load_cli.py  -> load_standard_csv()

Web:
  Streamlit -> CatalogGuardApiClient -> FastAPI
  -> etl/web_service.py: run_web_etl()
  -> run_pipeline()
  -> load_standard_csv()
```

`run_web_etl()`은 `etl.cli`/`etl.load_cli`가 호출하는 `run_pipeline()`·`load_standard_csv()`를 그대로 호출한다. transformer 매핑, normal/reject 판단, summary 생성, SHA-256 계산, staging 저장 로직은 복제하지 않는다. 새 함수는 in-memory 업로드 bytes를 기존 Path 기반 Pipeline 계약에 연결하는 adapter 역할만 한다.

### `run_web_etl()` 역할

`etl/web_service.py`의 `run_web_etl()`은 얇은 orchestration 계층이다.

```text
upload bytes
-> validate_csv_filename() / validate_csv_file_size()로 선검증
-> profile_id를 서버 allowlist로 해석 (get_profile_path())
-> TemporaryDirectory 생성
-> 업로드 CSV를 임시 입력 파일로 저장
-> run_pipeline(input_path, profile_path, output_path, rejects_path, summary_path)
-> output/rejects/summary 파일을 bytes로 다시 읽음
-> load_standard_csv(session, output_bytes, summary_bytes, ...)
-> TemporaryDirectory 종료 시 임시 파일 자동 삭제
-> ETLWebRunOutcome 반환
```

### S3 source adapter

`POST /api/v1/etl-loads/s3`는 입력을 업로드 대신 S3에서 가져오는 경로다. 두 번째 ETL pipeline이 아니라 `run_web_etl()` 앞단에 붙는 source adapter이며, 그 뒤 흐름은 업로드 경로와 완전히 같다.

```text
S3 object
-> etl/s3_source.py: read_s3_csv_object()
-> (source_filename, content bytes)
-> run_web_etl()          <- 업로드 경로와 동일한 함수
-> run_pipeline()
-> load_standard_csv()
```

`read_s3_csv_object()`가 하는 일은 bytes를 안전하게 가져오는 것까지다.

```text
서버 환경변수에서 bucket/prefix 확인 (요청은 bucket을 고를 수 없음)
-> object_key가 허용 prefix로 시작하는지 검사 (아니면 S3 호출 전에 차단)
-> head_object()로 크기를 먼저 확인하고 업로드와 같은 상한으로 검증
-> get_object() 후 상한+1 bytes까지만 bounded read
-> 실제 읽은 길이를 다시 검증
```

호출하는 AWS API는 `head_object()`·`get_object()` 두 개뿐이고 list 계열은 쓰지 않는다. 그래서 필요한 권한도 `s3:GetObject` 하나로 끝난다. 자격증명은 요청이나 환경변수로 받지 않고 boto3 기본 credential chain을 그대로 사용한다.

전환·중복 판단·Actor Audit을 재구현하지 않았으므로, 같은 파일이 업로드로 들어오든 S3에서 들어오든 `input_file_sha256`·`profile_name`·`profile_version` 기준 중복 판단 결과가 같다.

### HTTP feed source adapter

`POST /api/v1/etl-loads/http`는 입력을 신뢰 공급사 HTTP feed에서 가져오는 경로다. S3와 마찬가지로 두 번째 ETL pipeline이 아니라 `run_web_etl()` 앞단에 붙는 source adapter이며, 그 뒤 흐름은 업로드·S3 경로와 완전히 같다.

```text
Trusted HTTP Supplier Feed
-> etl/http_source.py: read_http_feed_csv()
-> (source_filename, content bytes)
-> run_web_etl()          <- 업로드·S3 경로와 동일한 함수
-> run_pipeline()
-> load_standard_csv()
```

세 source는 bytes를 가져오는 방법만 다르고 core ETL은 하나다.

| source | 입력 경로 | 클라이언트가 정하는 것 | 서버가 정하는 것 |
|---|---|---|---|
| Upload | multipart 업로드 | 파일, `profile_id` | 없음 |
| S3 | `read_s3_csv_object()` | `object_key`, `profile_id` | bucket, 허용 prefix |
| HTTP Feed | `read_http_feed_csv()` | `profile_id`만 | feed URL, 저장할 파일명 |

`read_http_feed_csv()`가 하는 일도 bytes를 안전하게 가져오는 것까지다.

```text
서버 환경변수에서 feed URL 확인 (요청은 URL을 고를 수 없음)
-> 허용 scheme 검사 (https, 또는 loopback host의 http)
-> 설정 파일명을 기존 CSV 파일명 규칙으로 검증
-> redirect를 따르지 않는 opener로 bounded timeout 요청
-> Content-Length가 있으면 본문을 읽기 전에 먼저 크기 검증
-> 상한+1 bytes까지만 bounded read
-> 실제 읽은 길이를 다시 검증
```

가장 중요한 설계 결정은 **클라이언트가 URL을 고를 수 없다는 것**이다. 요청 본문은 `profile_id` 하나뿐이고 schema가 `extra="forbid"`이므로 `url` 같은 필드를 넣으면 `422`가 된다. 사용자가 내부망 주소나 cloud metadata 주소를 서버에 요청시키는 SSRF 구조를 만들지 않기 위해서다.

redirect는 따라가지 않는다. 신뢰 URL이 다른 host로 redirect되면 결국 그 host를 사용자가 아닌 공급사가 고르게 되는 셈이라, MVP에서는 가장 단순한 "따라가지 않음"을 택했다. 평문 `http`는 서버를 떠나지 않는 loopback host에서만 허용하고, 외부 host는 `https`만 허용한다.

feed URL과 응답 본문은 credential을 담을 수 있으므로 오류 메시지와 구조화 로그에는 코드만 남긴다.

새 HTTP 라이브러리는 추가하지 않았다. Python 표준 라이브러리 `urllib.request`로 timeout, bounded read, redirect 차단이 모두 가능하다.

전환·중복 판단·Actor Audit을 재구현하지 않았으므로, 같은 CSV가 업로드로 들어오든 S3나 HTTP feed로 들어오든 `input_file_sha256`·`profile_name`·`profile_version` 기준 중복 판단 결과가 같다. 같은 feed를 두 번 가져오면 두 번째 요청은 `created=false`와 같은 `etl_load_run_id`를 돌려준다.

### HTTP feed 테스트 구조

단위 테스트(`tests/etl/test_http_source.py`)는 fake opener를 주입해 응답 계약·오류 매핑·크기 제한·URL 허용 정책을 검증하고, API 테스트(`tests/test_api_etl_http_load.py`)는 source adapter를 대체해 권한·오류 매핑·metric·중복 계약을 검증한다. 어느 테스트도 실제 인터넷에 접속하지 않으므로 CI 결과는 외부 사이트 상태에 영향을 받지 않는다.

실제 소켓 통신은 저장소 밖 임시 스크립트에서 로컬 `http.server`를 띄워 별도로 확인했다.

### 실제 AWS staging 검증과 fake client 테스트의 구분

이 기능의 단위·API 테스트(`tests/etl/test_s3_source.py`, `tests/test_api_etl_s3_load.py`)는 fake S3 client를 주입해 응답 계약·오류 매핑·크기 제한을 검증한다. 실제 AWS 자격증명이나 네트워크를 쓰지 않으므로 CI에서 항상 돌지만, 실제 S3의 동작까지 보장하지는 않는다.

2026-08-12에 별도로 실제 AWS staging(private S3 + EC2 Instance Role + RDS PostgreSQL)에 연결해 ETL 관점의 결과를 확인했다.

| 확인 | 실제 결과 |
|---|---|
| 합성 fixture 1건(`sample_vendor_valid.csv`) | `created=true`, total 1 / loaded 1 / rejected 0 |
| 가격 표준화 | 입력 `"12,000"` -> staging `price=12000` |
| 동일 객체·프로필 재요청 | `created=false`, 같은 `etl_load_run_id`, run 총 1건 유지 |
| Actor Audit | `actor_user_id`·`actor_username`이 실제 사용자 row와 일치, dedup에서도 최초 actor 유지 |
| 필요 권한 | `s3:GetObject` + 정확한 prefix만으로 충분 |
| 허용 prefix 안의 없는 key | `502 s3_read_failed` |

마지막 줄은 fake client 테스트와 실제 AWS가 갈리는 지점이다. fake client는 `NoSuchKey`를 주입하므로 `404 s3_object_not_found`가 나오지만, 실제 S3는 `s3:ListBucket` 권한이 없는 principal에게 없는 key를 `403 AccessDenied`로 응답한다. 애플리케이션은 이를 안전한 `s3_read_failed`로 매핑하며, `404`를 얻기 위해 `ListBucket`을 추가하지는 않았다. 최소권한을 유지한 결과다.

AWS 인프라 구성과 배포 절차는 [AWS staging 배포 런북](aws-staging-deployment.md) 17절에 기록한다.

### Profile allowlist 설계

`etl.profile_loader.load_profile(profile_path)`는 임의 `Path`를 받는 내부 함수이며, 이를 Web API에 그대로 노출하면 사용자가 보낸 경로로 서버 파일을 읽는 통로가 될 수 있다. Web 경로는 이 함수를 직접 호출하지 않고 `profile_id`만 받는다.

```text
profile_id (Streamlit selectbox 값)
-> etl.profile_loader._ETL_PROFILE_REGISTRY[profile_id]
-> get_profile_path(profile_id)
-> config/etl/<registry가 아는 파일명>.json
```

`get_profile_path()`는 registry에 없는 `profile_id`를 `ETLProfileNotFoundError`로 거부하고, registry에 있는 경우에도 `(ETL_PROFILE_DIR / info["filename"]).resolve()`의 부모 디렉터리가 `ETL_PROFILE_DIR.resolve()`와 같은지 다시 확인한 뒤에만 경로를 반환한다. 현재 registry는 다음 두 항목만 포함한다.

| `profile_id` | 파일 | `display_name` |
|---|---|---|
| `sample_fashion_vendor_v1` | `config/etl/sample_fashion_vendor_v1.json` | 패션 공급사 샘플 |
| `sample_marketplace_vendor_v1` | `config/etl/sample_marketplace_vendor_v1.json` | 마켓플레이스 공급사 샘플 |

`profile_id`와 파일명의 `_v1`은 서버 allowlist에서 쓰는 **안정적인 API 식별자**이며 실제 버전 값이 아니다. 기존 클라이언트 호환을 위해 이 문자열은 그대로 유지한다. 실제 ETL dedup·audit에 쓰이는 버전은 프로필 JSON의 `profile_version`이고 `etl_load_runs.profile_version`에도 그 값이 기록되며, 현재 두 sample profile의 `profile_version`은 `"2"`다. 두 값이 충돌해 보이지 않도록 `display_name`에는 버전을 넣지 않는다.

`profile_id`에 `../../etc/passwd`, 절대경로, `..\..\` 같은 값을 보내면 registry 조회에서 바로 `ETLProfileNotFoundError`가 되며 `resolve()`도 실행되지 않으므로 서버 filesystem을 읽지 못한다. `tests/etl/test_web_service.py::test_run_web_etl_rejects_unknown_profile_without_touching_the_database`가 이 경로를 직접 확인하며, DB에 아무 것도 쓰지 않는 것(`session.new`/`session.dirty` 비어 있음)도 함께 검증한다.

### Profile 목록 API

```http
GET /api/v1/etl-profiles
```

Streamlit이 허용된 프로필 목록을 서버에서 가져오는 용도다. `etl.profile_loader.list_etl_profiles()`가 registry를 순회해 `id`·`display_name`만 반환하며, 내부 filesystem 경로(`filename`)는 API 응답에 포함하지 않는다.

### CSV Upload 보안

웹 ETL 업로드는 새 검증 코드를 추가하지 않고 기존 검증을 재사용한다.

- 파일 크기: `config/settings.py`의 `MAX_UPLOAD_SIZE_BYTES = 5 * 1024 * 1024`(5MB)를 `core.upload_validator.validate_csv_file_size()`로 그대로 확인한다.
- 파일명: `validate_csv_filename()`이 `.csv` 확장자와 빈 파일명을 확인한다. 원본 파일명은 `_leaf_filename()`이 디렉터리 구분자를 제거해 실제 filesystem 경로 구성에는 쓰지 않고, `TemporaryDirectory` 안의 파일 이름 한 조각으로만 사용한다.
- 내용 검증: `run_pipeline()`이 호출하는 기존 CSV 파서가 인코딩, 헤더, 필수 컬럼, 행 수, 행 형식을 그대로 검사한다.
- Content-Type이나 확장자 문자열만으로 CSV 여부를 판단하지 않고, 실제 파일 내용을 pandas로 읽어 검증한다.

### 임시 파일 처리

기존 `run_pipeline()`은 `Path` 기반 계약이므로, Web upload bytes를 위해 별도 변환 코드를 만들지 않고 `tempfile.TemporaryDirectory()`를 adapter로 사용한다.

```text
upload bytes
-> TemporaryDirectory 안의 임시 입력 파일
-> 기존 run_pipeline() (Path 기반)
-> output/rejects/summary 파일 읽기
-> with 블록 종료
-> 임시 디렉터리와 파일 삭제
```

성공, `ETLPipelineError`(잘못된 프로필 매핑/변환 실패), `ETLLoadError`(요약·CSV 불일치) 등 어느 경로로 함수가 끝나도 `TemporaryDirectory`의 `__exit__`가 임시 파일을 정리한다. `tests/etl/test_web_service.py`의 `test_run_web_etl_rejects_empty_upload_without_creating_a_run`, `test_run_web_etl_rejects_malformed_supplier_csv_without_creating_a_run`, `test_run_web_etl_cleans_up_temp_files_after_pipeline_failure`가 실행 전후 `catalogguard_web_etl_*` 임시 디렉터리 목록을 비교해 실패 경로에서도 정리되는지 확인한다. 원본 업로드 파일명은 임시 파일 이름 한 조각에만 쓰이고 실제 filesystem 경로 구성에는 사용하지 않는다.

### normal / reject / summary 정책 유지

Web ETL은 새 reject 의미를 만들지 않고 기존 Pipeline의 normal/reject/summary 정책을 그대로 사용한다.

- 부분 reject: normal 행만 staging에 적재되고 reject 건수는 summary·`etl_rejected_rows`에 유지된다.
- 전체 reject: 표준 CSV의 normal 행이 0건이면 `load_standard_csv()`가 `ETLLoadError`를 발생시켜 staging batch 자체가 생성되지 않는다. 이는 Web ETL이 새로 만든 제약이 아니라 CLI(`etl.load_cli`)가 이미 갖고 있던 `load_standard_csv()` 계약을 그대로 물려받은 것이다.

### PostgreSQL staging 재사용

Web ETL을 위한 새 DB 테이블이나 Alembic migration은 없다. 기존 `etl_load_runs`, `catalog_products_staging`, `etl_rejected_rows`를 그대로 사용하며, `load_standard_csv()`의 기존 트랜잭션 경계를 그대로 재사용한다. 상품·reject 저장 중 오류가 발생하면 배치를 포함해 전체 rollback하므로 부분 staging은 남지 않는다.

### 중복 Web ETL 실행

중복 판단 키는 CLI와 동일하게 `(input_file_sha256, profile_name, profile_version)`이다. 같은 조합으로 다시 요청하면 새 `etl_load_runs` 행을 만들지 않고 기존 배치를 `created=false`로 반환한다. 이 DB 수준 중복 방어와 Streamlit UI의 중복 클릭 방지(버튼 클릭으로만 요청, `in_flight` 상태로 중복 클릭 무시)는 서로 다른 계층의 방어이며, 최종 기준은 항상 DB unique index다. `tests/etl/test_web_service.py::test_run_web_etl_duplicate_input_returns_existing_run_without_creating_new_row`는 서로 다른 두 세션(두 개의 독립된 HTTP 요청을 흉내)에서 같은 입력으로 `run_web_etl()`을 두 번 호출해 두 번째 호출이 `created=False`와 첫 번째와 같은 `etl_load_run_id`를 반환하는지, DB에 배치가 한 건만 남는지 확인한다.

### Streamlit Web ETL UI

`ui/etl_load_history.py`의 `_render_etl_web_run()`이 웹 ETL 실행 화면을 그린다.

```text
_fetch_etl_profiles()로 GET /api/v1/etl-profiles 조회
-> "ETL 실행 프로필" selectbox
-> "공급사 CSV 파일" file_uploader
-> "ETL 실행" 버튼 (파일 미선택 시 disabled)
-> 버튼 클릭 시에만 _submit_etl_web_run() 호출
-> POST /api/v1/etl-loads
-> 정상 응답: total_rows/loaded_rows/rejected_rows와 etl_load_run_id 표시
-> ETL 적재 이력 캐시(etl_load_list_response 등)만 무효화
-> st.rerun()
```

파일 선택이나 프로필 변경만으로는 API를 호출하지 않는다. `_on_etl_web_run_profile_change()`는 프로필이 바뀌면 이전 `etl_web_run_result`/`etl_web_run_error`를 지워 stale 결과가 새 프로필의 결과처럼 보이지 않게 한다. `POST` 호출은 `_render_etl_web_run()`의 `if st.button(...)` 블록 안에서만 실행되므로, 이후 같은 화면이 다시 rerun되어도(다른 위젯 조작, 페이지 이동 등) 버튼을 다시 클릭하지 않는 한 같은 요청이 반복되지 않는다. 성공 시에는 `etl_load_list_response`·`etl_load_initialized`·`etl_load_offset`만 초기화해 ETL 적재 이력이 새 배치를 다시 조회하게 하며, `catalog_promotion_*` 상태는 건드리지 않는다. 즉 웹 ETL 실행 성공이 promotion을 자동으로 실행하지 않는다. `tests/test_etl_load_history_ui.py`의 `test_etl_web_run_profile_dropdown_lists_allowlisted_profiles`, `test_etl_web_run_submit_button_disabled_without_uploaded_file`, `test_etl_web_run_profile_change_does_not_call_run_etl_load`, `test_etl_web_run_profile_change_clears_stale_result_and_error`, `test_submit_etl_web_run_success_invalidates_history_cache_but_keeps_promotion_cache`가 이 동작을 각각 검증한다.

### Promotion과의 연결

웹 ETL 성공은 promotion을 자동으로 트리거하지 않는다. 사용자가 ETL 적재 이력에서 새로 생성된 batch를 직접 선택해야 기존 promotion preview·승인 흐름(위 "Catalog promotion preview와 승인 반영" 절)을 시작할 수 있다. 웹 ETL이 만든 배치와 CLI가 만든 배치는 `etl_load_runs` 스키마상 구분되지 않으므로, promotion 이후 단계에서는 배치가 어느 경로로 생성됐는지에 따른 분기가 없다.

## 안전성과 호환성

입력은 CSV 확장자, 크기, 인코딩, NUL 바이트, 헤더, 중복 컬럼, 행 수와 행 형식을 확인한다. 입력 파일과 출력 파일이 같거나 출력 파일끼리 겹치면 거부한다. 각 출력은 임시 파일 작성 후 원자적으로 교체한다.

표준 CSV는 `product_group_id`부터 `seller`까지 기존 컬럼 순서를 지키며 `price` 다음에 선택 컬럼 `sale_price`를 출력하고 pandas index를 쓰지 않는다. `tests/etl/test_pipeline.py`는 생성된 파일을 실제 `validate_and_read_uploaded_csv()`와 `inspect_dataframe()`에 전달해 `discount_price` 변환과 할인가 관계 검수의 호환성을 확인한다.

## PostgreSQL staging 적재

파일 변환이 끝나면 `catalogguard_ready.csv`와 `etl_summary.json`을 별도 Load 단계에 전달할 수 있다.

```text
공급사 CSV + JSON 프로필
-> etl.cli
-> 표준 CSV + reject CSV + summary JSON
-> etl.load_cli
-> summary 필드·SHA-256·품질 요약·표준 CSV 검증
-> 중복 배치 조회
-> etl_load_runs + catalog_products_staging 저장
-> FastAPI 배치 목록·상세 조회
```

두 CLI의 책임은 분리되어 있다.

| CLI | 책임 |
|---|---|
| `python -m etl.cli` | 공급사 CSV를 표준 CSV, reject CSV, summary JSON으로 변환 |
| `python -m etl.load_cli` | 표준 CSV와 summary JSON을 검증한 뒤 PostgreSQL staging에 적재 |

### 적재 검증과 중복 판단

`etl.db_loader.load_standard_csv()`는 기존 `validate_and_read_uploaded_csv()`를 재사용해 표준 CSV를 읽는다. 이어서 summary JSON에 다음 필드가 있는지 확인한다.

- `profile_name`
- `profile_version`
- `input_filename`
- `input_file_sha256`
- `output_file_sha256`
- `total_rows`
- `loaded_rows`
- `rejected_rows`
- `error_counts`
- `rejects_file_sha256` (신규 summary에서 필수)

profile 이름·버전과 파일명을 정규화하고, SHA-256 형식과 세 행 수의 음수가 아닌 정수 여부를 확인한다. `total_rows = loaded_rows + rejected_rows`를 강제하며, `error_counts`의 key·값과 reject 행 수의 관계를 검증한다. 신규 summary에 `rejects_file_sha256`가 있으면 `--rejects`가 반드시 필요하며, 실제 reject CSV의 hash·행 수·헤더·JSON 오류 배열·동적 원본 컬럼을 모두 검증한다. 한 행에 여러 오류 코드가 있을 수 있으므로 오류 건수 합계는 reject 행 수 이상이면 허용한다. 실제 표준 CSV bytes의 SHA-256이 summary의 `output_file_sha256`과 같은지, 실제 CSV 행 수가 `loaded_rows`와 같은지도 확인한다. 검증에 실패하면 DB를 변경하지 않는다. 과거 summary에 reject hash가 없으면 `--rejects` 없이 기존 방식으로 적재할 수 있고 자동 backfill은 수행하지 않는다.

같은 원본을 같은 프로필 버전으로 다시 적재했는지는 다음 세 값으로 판단한다.

```text
(input_file_sha256, profile_name, profile_version)
```

이미 같은 조합의 `etl_load_runs`가 있으면 상품 행을 추가하지 않고 기존 배치 ID와 `created=False`를 반환한다. 프로필 버전이 다르면 별도 배치로 저장한다.

### Staging 테이블 구조

`etl_load_runs`는 한 번의 ETL 적재를 나타내며 원본 파일명, 프로필, 입력·출력·reject CSV 해시, 적재 행 수와 생성 시각을 저장한다. 신규 배치는 `total_rows`, `rejected_rows`, `error_counts`를 각각 INTEGER·INTEGER·PostgreSQL JSONB로 저장하고 `reject_details_stored`와 `rejects_file_sha256`로 reject 상세 저장 여부를 표시한다. 품질 요약 기능 도입 전 배치는 과거 값을 추정하지 않고 nullable 품질 필드를 유지하며, reject 상세도 자동 backfill하지 않는다. `catalog_products_staging`은 배치에 속한 정상 표준 CSV 행을, `etl_rejected_rows`는 검증된 오류 객체와 개인정보가 마스킹된 동적 원본 컬럼 JSONB를 저장한다.

```text
etl_load_runs (1)
        |
        | etl_load_run_id, ON DELETE CASCADE
        +-----------------------> catalog_products_staging (N)
        |
        +-----------------------> etl_rejected_rows (N)
```

`etl_load_runs`에는 `(input_file_sha256, profile_name, profile_version)` unique index가 있고, 상품 테이블의 `etl_load_run_id`에는 조회용 index와 외래 키가 있다. `stock`, `price`, `sale_price`는 음수가 될 수 없으며 빈 `sale_price`는 DB `NULL`로 저장한다. 부모 배치를 삭제하면 연결된 상품 행도 cascade로 삭제된다.

### 트랜잭션과 CLI

신규 배치와 모든 상품 행·reject 행은 하나의 SQLAlchemy 트랜잭션 안에서 저장한다. 상품 또는 reject 행 저장 중 오류가 발생하면 배치와 두 자식 테이블의 데이터를 함께 rollback하며, upsert나 기존 운영 상품 덮어쓰기는 수행하지 않는다. reject CSV 자체는 파일 검증 후 원본 값을 저장하지 않고 마스킹된 JSONB만 저장한다.

```powershell
python -m etl.load_cli `
  --input .\output\catalogguard_ready.csv `
  --rejects .\output\rejected_rows.csv `
  --summary .\output\etl_summary.json
```

신규 적재 예시는 다음과 같다. 배치 ID는 DB의 현재 sequence 상태에 따라 달라진다.

```text
DB 적재 완료
적재 배치 ID: 1
신규 적재: yes
전체 행: 2
정상 상품 행: 2
거부 행: 0
```

같은 파일을 다시 실행하면 다음과 같이 기존 배치를 재사용한다.

```text
DB 적재 완료
적재 배치 ID: 1
신규 적재: no
전체 행: 2
정상 상품 행: 2
거부 행: 0
```

## 배치 출처(source lineage) 기록

`etl_load_runs`는 "이 배치를 **최초로** 만든 입력 경로"를 두 컬럼에 기록한다.

| 컬럼 | 값 | 설명 |
|---|---|---|
| `initial_source_type` | `unknown` / `upload` / `s3` / `http_feed` / `cli` | NOT NULL. DB CheckConstraint `ck_etl_load_runs_initial_source_type`로 값을 고정한다. |
| `initial_source_ref` | 비밀이 없는 최소 locator | NULL 허용. |

source별 정책은 다음과 같다.

| 입력 경로 | `initial_source_type` | `initial_source_ref` |
|---|---|---|
| 웹 업로드 `POST /api/v1/etl-loads` | `upload` | 업로드 파일의 leaf 이름. 사용자 PC의 디렉터리 경로는 저장하지 않는다. |
| S3 `POST /api/v1/etl-loads/s3` | `s3` | 허용 prefix를 제거한 상대 object key. bucket 이름은 저장하지 않는다. |
| HTTP feed `POST /api/v1/etl-loads/http` | `http_feed` | 고정 식별자 `configured_http_feed`. |
| CLI `etl.load_cli` | `cli` | `NULL`. `--input`은 원본 공급사 파일이 아니라 표준 CSV라, 저장하면 출처를 오해하게 만든다. |
| migration 이전 기존 배치 | `unknown` | `NULL` |

### 왜 "initial"인가

중복 배치 판정(dedup) 기준은 지금도 `(input_file_sha256, profile_name, profile_version)`이며 이번 변경으로 바뀌지 않았다.
따라서 같은 bytes를 같은 프로필로 다시 넣으면 **입력 경로가 달라도** 새 배치를 만들지 않고 기존 배치를 그대로 돌려준다.

```text
1일차  사용자가 A.csv 업로드
      -> etl_load_runs #42 생성 (created=true)
      -> initial_source_type = "upload"

2일차  HTTP feed가 완전히 동일한 bytes를 제공
      -> dedup으로 기존 #42 반환 (created=false)
      -> initial_source_type은 "upload" 그대로
```

즉 이 값은 "마지막으로 들어온 경로"가 아니라 "이 배치를 처음 만든 경로"다.
API 응답도 이번 요청의 경로가 아니라 DB에 저장된 최초 경로를 돌려주므로,
`created=false`인 응답에서 `initial_source_type`이 이번에 호출한 경로와 다를 수 있다.

### 저장하지 않는 것

- **원본 CSV bytes**: 이번 범위가 아니다. 지금도 SHA-256 해시만 남고 원본은 보존하지 않는다.
- **HTTP feed URL 원문**: `CATALOGGUARD_ETL_HTTP_FEED_URL`에는 token이나 signed query가 들어갈 수 있어 host·path·query 어느 것도 저장하지 않는다. 기존 로그 정책과 같은 판단이다.
- **S3 bucket 이름과 허용 prefix**: 서버 설정이지 배치별 출처 정보가 아니다.
- **재유입 이력**: dedup으로 재사용된 배치에 대해 "두 번째로 어느 경로로 또 들어왔는지"를 **DB에는** 기록하지 않는다. 이를 DB에 남기려면 배치와 수집 사건을 분리하는 별도 구조가 필요한데, 실제 요구가 관측되기 전에는 만들지 않는다. 다만 재유입 **사건 자체**는 아래 structured log로 남는다.

조회는 `GET /api/v1/etl-loads` 목록과 `GET /api/v1/etl-loads/{id}` 상세 응답에서 두 필드로 확인한다.
출처 기준 검색·필터는 제공하지 않는다.

### duplicate 재유입 관측 (`etl_duplicate_ingestion`)

`initial_source_type`은 최초 경로만 남기므로, "이번 요청이 어느 경로로 들어왔는가"는 DB만 봐서는 알 수 없다.
그래서 Web/API ETL이 기존 배치를 재사용할 때(`created=false`) structured log를 **요청당 정확히 1건** 남긴다.

```json
{
  "event": "etl_duplicate_ingestion",
  "etl_load_run_id": 42,
  "initial_source_type": "upload",
  "request_source_type": "http_feed",
  "same_source": "false",
  "request_id": "..."
}
```

| 필드 | 의미 |
|---|---|
| `etl_load_run_id` | 재사용된 기존 배치 ID |
| `initial_source_type` | DB에 저장된 **최초** 경로 |
| `request_source_type` | **이번 요청**이 들어온 경로 (`upload` / `s3` / `http_feed`) |
| `same_source` | 위 두 값의 일치 여부. `log_event()`가 scalar만 받으므로 bool이 아닌 `"true"` / `"false"` 문자열 |
| `request_id` | 같은 요청의 `http_request_completed` 로그와 잇는 correlation key |

동작 규칙은 다음과 같다.

- 신규 적재(`created=true`)에서는 남기지 않는다.
- `etl.db_loader`의 두 duplicate 경로(SELECT로 바로 찾은 경우, unique index 경쟁에서 져 `IntegrityError` 후 재조회한 경우)가 모두 `created=false`로 route까지 오므로, route에서 한 번만 남겨도 둘 다 포함된다.
- DB·API 응답·metric은 바뀌지 않는다. duplicate 총량은 기존 `catalogguard_web_etl_runs{outcome="duplicate"}`가 계속 담당하고, 이 로그는 "어느 경로 조합이었는가"만 보완한다.

로그에 넣지 않는 값: `initial_source_ref`, `source_filename`, 입력·출력 SHA-256, HTTP feed URL·token, S3 bucket·object key, `actor_username`.
locator가 필요하면 `etl_load_run_id`로 `GET /api/v1/etl-loads/{id}`를 조회하면 되므로 로그에 중복해 남길 이유가 없다.
특히 duplicate 응답의 `actor_username`은 이번 요청자가 아니라 **최초 적재자**라, 로그에 넣으면 재전송한 사람으로 오해된다.

한계:

- **CLI(`etl.load_cli`)는 범위 밖**이다. CLI는 `configure_logging()`을 거치지 않는 별도 실행 경로라 duplicate가 나도 이 로그가 남지 않는다.
- 로그 보존 기간을 넘어선 장기 감사 이력은 보장하지 않는다. 그런 요구가 실제로 생기면 그때 수집 사건 테이블을 다시 검토한다.

## 적재 배치 실행·조회 API

ETL 실행은 CLI 또는 FastAPI의 `POST /api/v1/etl-loads`(웹 ETL, 위 "웹 ETL 실행" 절 참고)로 할 수 있으며, 배치·상품 조회는 아래 `GET` API로 읽기 전용으로 제공한다.

### 웹 ETL 실행

```http
POST /api/v1/etl-loads
```

`multipart/form-data` 요청이며 파일 필드명은 `file`, 프로필 필드명은 `profile_id`다. `profile_id`는 `GET /api/v1/etl-profiles`가 반환하는 값만 허용한다.

| 오류 | 상태 코드 | `code` |
|---|---|---|
| 지원하지 않는 `profile_id` | `400` | `unsupported_profile` |
| 빈 파일, 크기 초과, ETL 변환 실패 | `400` | `invalid_upload` |
| staging 저장 실패 | `500` | `etl_load_failed` |

정상 응답은 `etl_load_run_id`, `created`, `profile_name`, `profile_version`, `source_filename`, `total_rows`, `loaded_rows`, `rejected_rows`, `error_counts`를 포함한다(`api/schemas.py`의 `ETLWebRunResponse`). `tests/test_api_etl_web_run.py`가 성공, 프로필 미지원, 잘못된 업로드, 적재 실패 각각의 HTTP 상태·오류 code·응답 계약을 검증한다.

### ETL 프로필 목록

```http
GET /api/v1/etl-profiles
```

`etl.profile_loader.list_etl_profiles()`가 반환하는 allowlist를 `{id, display_name}` 목록으로 반환한다. 서버 파일 경로는 노출하지 않는다.

### 적재 배치 목록

```http
GET /api/v1/etl-loads
```

| Query | 기본값 | 조건과 의미 |
|---|---:|---|
| `limit` | `20` | 한 페이지의 배치 수, `1` 이상 `100` 이하 |
| `offset` | `0` | 앞에서 건너뛸 배치 수, `0` 이상 |
| `filename` | 없음 | 별도 길이 제한 없는 원본 파일명 부분 검색 |
| `profile_name` | 없음 | 별도 길이 제한 없는 프로필 이름 부분 검색 |

`filename`과 `profile_name`은 앞뒤 공백을 제거하며, 공백만 남는 값은 필터로 사용하지 않는다. 검색은 대소문자를 구분하지 않는 부분 일치이고 두 필터를 함께 보내면 AND 조건으로 적용한다. `%`, `_`, `\`는 SQL LIKE의 wildcard나 escape 문법이 아니라 실제 문자로 검색하도록 escape한다.

목록은 `created_at DESC`, `id DESC` 순으로 최신 배치를 먼저 반환한다. 페이지의 `items`와 전체 건수 `total`은 같은 필터 함수를 사용하므로 검색 조건이 서로 달라지지 않는다. 목록 응답에는 배치 ID, 원본 파일명, 프로필 이름·버전, 전체·정상·거부 행 수와 생성 시각을 포함하며 SHA-256·오류 코드·상품 목록은 제외한다.

### 적재 배치 상세

```http
GET /api/v1/etl-loads/{etl_load_run_id}
```

| Query | 기본값 | 조건과 의미 |
|---|---:|---|
| `product_limit` | `50` | 한 페이지의 상품 수, `1` 이상 `100` 이하 |
| `product_offset` | `0` | 앞에서 건너뛸 상품 수, `0` 이상 |

```http
GET /api/v1/etl-loads/{etl_load_run_id}/rejections?limit=20&offset=0
```

reject 상세 응답은 저장 여부, 전체 reject 행 수, 페이지 단위의 원본 행 번호·구조화된 오류 배열·마스킹된 동적 원본 컬럼을 반환한다. reject 상세가 저장되지 않은 과거 배치는 `available=false`와 빈 목록을 반환하며, 배치가 없으면 HTTP `404`를 반환한다.

상세 응답에는 배치 기본 정보, 전체·정상·거부 행 수, `error_counts`, reject 상세 저장 여부, 원본·출력 파일 SHA-256과 해당 배치의 staging 상품 목록이 포함된다. 기존 배치는 품질 필드를 `null`로 반환한다. 상품은 staging 상품 `id ASC`로 정렬하며 SQL `LIMIT`·`OFFSET`에서 페이지를 나눈다. 모든 상품 조회와 count에는 요청한 `etl_load_run_id` 조건을 적용해 다른 배치의 상품이 섞이지 않게 한다. 배치가 없으면 HTTP `404`를 반환한다.

Path의 `etl_load_run_id`는 `1` 이상의 정수만 허용한다. `0`, 음수와 숫자가 아닌 값은 요청 검증 단계에서 HTTP `422`가 된다. nullable 컬럼인 `sale_price`, `description`, `seller`는 값이 없을 때 JSON `null`로 유지한다.

### 구현 구조

| 파일 | 역할 |
|---|---|
| `api/routes/etl_loads.py` | 웹 ETL 실행·프로필 목록 endpoint, HTTP 요청과 Query·Path 범위 검증, 404 처리, 응답 모델 변환 |
| `api/schemas.py` | 웹 ETL 실행·배치 목록·상세·reject 상세와 staging 상품의 Pydantic 응답 구조 |
| `etl/web_service.py` | `run_web_etl()`: 업로드 bytes를 `TemporaryDirectory`로 옮겨 기존 `run_pipeline()`·`load_standard_csv()`를 실행하는 얇은 웹 ETL 진입점 |
| `etl/profile_loader.py` | JSON 프로필 검증과 웹 ETL이 사용하는 `profile_id` allowlist(`get_profile_path()`, `list_etl_profiles()`) |
| `db/etl_query_service.py` | SQLAlchemy 기반 읽기 전용 필터·정렬·count·페이지 조회와 reject 상세 조회 |
| `tests/etl/test_web_service.py` | `run_web_etl()`의 정상 적재, 부분/전체 reject, 중복 재사용, allowlist 위반, 업로드 검증 실패, 임시 파일 정리 |
| `tests/test_api_etl_web_run.py` | `POST /api/v1/etl-loads`의 HTTP 상태, 오류 code, 응답 계약 |
| `tests/test_api_etl_loads.py` | HTTP 상태, 파라미터 전달, 응답 필드와 nullable 값 계약 |
| `tests/test_etl_query_service.py` | 실제 PostgreSQL의 검색·정렬·페이지네이션·NULL·배치 격리 |

라우터는 ORM 객체를 API 응답으로 직접 내보내지 않고 query service의 dataclass 결과를 Pydantic 모델로 변환한다. 따라서 DB 모델 변경이 HTTP 응답 계약을 암묵적으로 바꾸지 않는다.

## Streamlit ETL 적재 이력 화면

Streamlit에는 공급사 CSV를 업로드해 ETL을 직접 실행하는 `ETL 실행` 영역과, 저장된 ETL 배치와 staging 상품을 확인하고 선택한 batch를 운영 상품에 반영하는 `ETL 적재 이력` 탭을 제공한다. ETL 실행, 배치·상품·reject 조회, promotion preview와 실제 반영 모두 `CatalogGuardApiClient`가 FastAPI API를 호출하는 방식이며, Streamlit이 DB에 직접 쓰지는 않는다.

| 화면 기능 | 동작 |
|---|---|
| ETL 실행 | 공급사 CSV 업로드와 "ETL 실행 프로필" 선택, 버튼 클릭으로 `POST /api/v1/etl-loads` 실행, 정상/거부 행 수와 배치 ID 표시 |
| 배치 목록 | 최신 적재부터 10건씩 표시하고 전체 행·정상 적재·변환 거부 행과 전체 건수를 표시 |
| 검색 | 파일명과 프로필명 검색을 함께 적용하는 AND 조건 |
| 배치 페이지 | 이전·다음 버튼으로 목록 offset 이동 |
| 배치 상세 | 배치 ID, 파일명, 프로필, 버전, 전체 입력·정상 적재·변환 거부·정상 처리율, 적재 시각과 input/output SHA-256 전체 표시 |
| 오류 통계 | 오류 코드별 발생 건수를 발생 건수 내림차순·코드 오름차순으로 표시하고 reject 0건은 안내 |
| reject 상세 | reject 행 페이지네이션, 오류 코드·필드·메시지와 마스킹된 원본 값 표시; 과거 미저장 배치는 안내 |
| 상품 목록 | 선택한 배치의 staging 상품을 20건씩 표시 |
| promotion | 선택한 batch의 preview 실행, 반영 가능 여부·차단 사유·변경 전후·insert/update/unchanged 표시 |
| 승인 반영 | 승인 checkbox 선택 전 반영 버튼 비활성화; 승인 후 `expected_preview_hash`와 함께 FastAPI promotion 요청 |
| nullable | `sale_price`, `description`, `seller`의 `null`을 빈 값으로 표시 |
| 빈 결과·404 | 빈 목록 안내와 존재하지 않는 배치의 오류 안내 표시 |
| 요청 추적 | 유효한 `X-Request-ID`를 오류 화면에 표시 |

```text
ETL 실행 영역
-> GET /api/v1/etl-profiles
-> "ETL 실행 프로필" 선택, CSV 업로드
-> ETL 실행 버튼 클릭
-> POST /api/v1/etl-loads
-> ETL 적재 이력 캐시 무효화

ETL 적재 이력 탭
-> GET /api/v1/etl-loads (limit=10)
-> 파일명·프로필명 검색(AND)
-> 배치 이전·다음
-> 배치 상세 선택
-> GET /api/v1/etl-loads/{etl_load_run_id} (product_limit=20)
-> SHA-256·배치 상품·nullable 필드 표시
-> GET /api/v1/etl-loads/{etl_load_run_id}/rejections (limit=20)
-> reject 오류 배열·마스킹된 원본·페이지 표시
-> 상품 이전·다음
-> 선택한 batch의 promotion preview
-> insert/update/unchanged·상품별 변경 전후·차단 사유 확인
-> 승인 checkbox 선택
-> POST /api/v1/etl-loads/{etl_load_run_id}/promotions
-> 운영 상품 반영 결과와 promotion run 확인
```

Streamlit rerun에 대비해 목록·상세·reject 응답과 선택 상태를 ETL 전용 `session_state`에 보관한다. 검색 조건이나 batch가 바뀌면 이전 상세·상품·reject 상태와 promotion preview·승인 상태를 초기화해 stale 데이터가 남거나 다른 batch에 반영되지 않게 한다. preview 요청 중에는 중복 요청을 막고, preview hash가 없거나 승인하지 않은 상태에서는 반영 버튼을 비활성화한다. 성공 후에는 preview·승인 상태를 제거하고 결과만 보존하며, `preview_stale`가 발생하면 이전 preview를 제거해 새 preview를 요구한다. API Client는 preview·promotion 응답의 필수 key, count, action, before/after shape, SHA-256을 검증하고 HTTP 오류를 안전한 사용자 메시지로 변환한다. 순수 helper 테스트와 Streamlit AppTest로 목록·검색·페이지 이동·상세·품질 지표·오류 코드·SHA-256·reject 상세·nullable·404·request ID·promotion 상태 초기화를 검증한다.

## Catalog promotion preview와 승인 반영

ETL staging은 운영 상품을 바로 덮어쓰는 테이블이 아니므로, 사용자가 반영 대상을 확인하고 명시적으로 승인하는 두 단계 workflow를 둔다. ETL batch를 자동으로 고르지 않고 Streamlit에서 사용자가 직접 선택해야 하며, preview 단계에서는 DB의 운영 상품을 변경하지 않는다.

### Preview API

```http
POST /api/v1/etl-loads/{etl_load_run_id}/promotion-preview
```

preview service는 선택한 batch의 staging 상품과 같은 공급사·외부 상품 ID를 가진 운영 상품을 비교한다. 각 상품을 `insert`, `update`, `unchanged`로 분류하고, update에는 변경 필드별 `before`·`after` 값을, insert에는 `before_data: null`과 전체 `after_data`를 반환한다. 응답에는 다음 정보가 포함된다.

- `insert_count`, `update_count`, `unchanged_count`
- `items`의 공급사, 외부 상품 ID, action, 변경 필드와 전후 데이터
- `promotion_eligible`와 구조화된 `blocked_reasons`
- `preview_hash`, `preview_schema_version`, `inspection_version`
- ETL 검수에서 계산한 `error_count`, `warning_count`

품질 summary가 없는 과거 batch, reject 행이 있는 batch, 빈 staging batch, 같은 공급사 상품 ID가 중복된 batch, 상품 검수 오류가 있는 batch는 `promotion_eligible=false`가 된다. 차단 사유가 있으면 상품별 반영 목록은 제공하지 않고, preview hash는 데이터 상태를 설명하는 값으로만 반환할 수 있다.

`preview_hash`는 canonical JSON으로 정렬한 batch ID, 공급사, inspection version, staging 상품과 현재 운영 상품의 값을 SHA-256으로 계산한 것이다. 암호화나 인증 토큰이 아니라 preview 시점과 실제 반영 시점의 데이터가 같은지 비교하는 stale 감지용 값이다.

### 승인과 실제 promotion

```http
POST /api/v1/etl-loads/{etl_load_run_id}/promotions
```

```json
{
  "confirmation": true,
  "expected_preview_hash": "64자리 소문자 SHA-256 hex"
}
```

서버는 `confirmation=true`와 형식이 맞는 hash를 먼저 검증한다. 그 뒤 하나의 transaction 안에서 ETL batch와 staging·현재 운영 상품을 잠그고 preview를 다시 계산한다.

1. 이미 같은 batch의 `succeeded` run이 있으면 기존 성공 결과를 반환하고 새 반영·audit을 만들지 않는다.
2. 품질·reject·검수·중복 identity 조건이 맞지 않으면 `promotion_blocked` run을 기록하고 `409`를 반환한다.
3. 재계산한 hash와 `expected_preview_hash`가 다르면 `preview_stale` run을 기록하고 `409`를 반환한다.
4. hash가 일치하면 `catalog_products`에 insert/update하고 `catalog_promotion_runs`를 `applying`에서 `succeeded`로 완료한다.
5. insert/update마다 `catalog_product_changes`에 before/after와 변경 필드를 append-only audit으로 기록한다.
6. 반영 중 예외가 발생하면 transaction을 rollback하고 안전한 `promotion_failed` 오류와 failed run을 남긴다. 내부 SQL·DB 연결 정보는 사용자에게 노출하지 않는다.

같은 ETL batch의 성공 run은 PostgreSQL partial unique index로 한 건만 허용한다. batch row와 운영 상품 row를 잠그고, 상품 identity를 공급사와 외부 상품 ID의 조합으로 관리해 서로 다른 공급사의 같은 ID가 충돌하지 않게 한다. 동시 요청 테스트는 한 요청만 성공하고 다른 요청은 stale 또는 안전한 failed 결과가 되며, `applying` 상태가 남지 않고 운영 상품과 audit이 한 번만 생성되는지 확인한다.

## 실제 Chromium 브라우저 E2E

계층별 테스트만으로는 Streamlit rerun, 실제 접근성 이름, 동적 표·expander 렌더링과 브라우저의 raw 개인정보 노출을 확인할 수 없으므로 별도 Playwright E2E를 둔다. `scripts/run_etl_browser_e2e.py`가 테스트 PostgreSQL에 migration을 적용하고 전용 합성 fixture를 ETL CLI·Load CLI로 처리한 뒤 FastAPI와 Streamlit을 시작한다. readiness가 확인되면 `tests/e2e/test_etl_browser_e2e.py`가 Chromium에서 reject 조회와 promotion 성공 흐름을 실행한다.

```text
ETL fixture 3행
-> 표준 CSV·reject CSV·summary JSON
-> PostgreSQL 배치·상품·reject 적재
-> FastAPI /health·/ready
-> Streamlit /_stcore/health
-> ETL 적재 이력 탭·검색·상세 조회
-> 품질 3행/2행/1행/66.7%
-> staging 상품 2개
-> reject 오류 배열과 마스킹 원본
-> promotion fixture batch 직접 선택
-> preview와 상품별 변경 전후 확인
-> 승인 checkbox 선택 전 반영 버튼 disabled 확인
-> 실제 promotion 실행
-> succeeded run·운영 상품·audit·applying 0건을 PostgreSQL에서 확인
```

브라우저 테스트는 `test@example.com`, `010-1234-5678`, `123-456-789012`, `900101-1234567`이 body text와 HTML에 존재하지 않는지 확인하고, 마스킹된 값·오류 코드·필드·메시지·console error 0·page error 0을 확인한다. 실패 시 `artifacts/browser-e2e/failure.png`, `page.html`, FastAPI·Streamlit·Playwright 로그를 보존하며 runner가 시작한 프로세스와 임시 디렉터리는 성공·실패 모두 정리한다.

로컬 실행에는 `requirements-e2e.txt` 설치와 Chromium 설치가 필요하다. GitHub Actions에서는 일반 테스트와 분리된 `browser-e2e` job이 PostgreSQL 18 service, Playwright Chromium과 실패 artifact 업로드를 담당한다.

### 전체 상품 로딩과 N+1 방지

배치 상세를 조회할 때 SQLAlchemy relationship의 상품 전체를 자동으로 읽지 않는다. 배치 정보와 현재 상품 페이지를 별도 SELECT로 조회하고, 전체 상품 수는 별도 count 쿼리로 계산한다. 상품 페이지네이션은 전체 행을 Python 메모리에 올린 뒤 자르는 방식이 아니라 DB 쿼리의 `LIMIT`·`OFFSET`에서 처리한다.

N+1 문제는 배치 한 번을 조회한 뒤 상품마다 DB에 다시 질문하여 DB 요청 횟수가 지나치게 늘어나는 문제다. 현재 상세 조회는 상품마다 추가 SELECT를 실행하지 않으며, 조회 함수 안에서 `commit`이나 `rollback`도 실행하지 않는다. 트랜잭션 수명은 세션을 제공한 상위 계층이 관리한다.

### 특수문자 검색 검증

실제 PostgreSQL 18.4 테스트에서 SQL LIKE 특수문자를 다음과 같이 일반 문자로 처리하는지 확인했다.

- `%` 검색은 여러 글자 wildcard가 아니라 실제 `%`가 포함된 파일만 반환한다.
- `_` 검색은 한 글자 wildcard가 아니라 실제 `_`가 포함된 파일만 반환한다.
- `\` 검색은 escape 처리 중 사라지거나 패턴을 바꾸지 않고 실제 `\`가 포함된 파일만 반환한다.

각 테스트는 해당 문자를 실제로 포함한 fixture와 포함하지 않은 fixture를 함께 사용해, wildcard로 처리하는 잘못된 구현이 통과하지 않도록 배치 ID 목록과 `total`을 확인한다.

### Migration 검증

다음 순서로 staging migration의 upgrade, downgrade, 재upgrade를 확인했다.

```powershell
python -m alembic upgrade head
python -m alembic downgrade 20260728_0005
python -m alembic upgrade head
```

`20260727_0004`에 이어 `20260728_0005` upgrade는 `etl_load_runs`에 reject 상세 저장 여부·reject CSV SHA-256과 all-or-none CHECK constraint를 추가하고, 오류 배열·마스킹된 원본 JSONB를 저장하는 `etl_rejected_rows`와 unique/index/FK를 만든다. downgrade는 새 컬럼·constraint·테이블·index만 제거하며 기존 배치·상품·inspection 데이터는 삭제하지 않는다.

현재 Alembic head는 `20260728_0006`이다. 이 revision은 ETL staging을 변경하지 않고, 별도의 운영 상품·promotion persistence 테이블을 추가한다. 격리된 PostgreSQL 18 테스트 클러스터에서 빈 DB upgrade, `20260728_0006` → `20260728_0005` downgrade, 재-upgrade와 단일 head를 확인했으며, 이후 promotion service·API·UI가 이 테이블을 사용하는 흐름을 검증했다.

현재 기준 저장소의 GitHub Actions run `30736845060`은 성공했다. 문서에는 실행별 전체 pytest 수를 고정하지 않고, promotion preview·service·API·client·UI·concurrency 테스트와 Chromium promotion E2E가 검증하는 동작 범위를 기록한다. E2E는 브라우저 메시지뿐 아니라 PostgreSQL의 최종 운영 상품·run·audit 상태도 확인한다.

## Web ETL 검증에서 발견한 CI 결함과 수정

Web ETL 기능 commit(`ef08109`)이 병합된 뒤 실행된 GitHub Actions run `30911933934`에서 `test`·`browser-e2e` job이 모두 blocking defect로 실패했다. 두 결함 모두 Web ETL이 처음 만든 새 import·UI 경로 때문에 발생했으며, fix commit(`cb5ed81`)에서 최소 범위로 수정했다.

### AWS runtime packaging 결함

로컬 전체 테스트(`1189 passed`)와 `docker build`는 모두 성공했지만, CI의 `Verify AWS image imports` 단계는 다음 오류로 실패했다.

```text
File "/app/api/routes/etl_loads.py", line 55, in <module>
    from etl.db_loader import ETLLoadError
ModuleNotFoundError: No module named 'etl'
```

원인은 `Dockerfile.aws`가 `alembic`·`api`·`config`·`core`·`db`·`services`·`workers` package만 image에 `COPY`하고 `etl/`은 포함하지 않았기 때문이다. Web ETL 이전에는 ETL History 조회가 `db.etl_query_service`만 사용했고 `api` 패키지가 `etl.*`를 직접 import하지 않았으므로 이 누락이 드러나지 않았다. Web ETL이 `api.routes.etl_loads -> etl.db_loader/etl.pipeline/etl.profile_loader/etl.web_service` import chain을 처음 만들면서 로컬 개발 환경(`etl/`이 항상 있는 소스 트리)에서는 재현되지 않고 AWS runtime image에서만 재현되는 결함이 되었다.

수정은 `Dockerfile.aws`에 다음 한 줄을 기존 COPY 순서(알파벳 순)에 맞춰 추가하는 것으로 끝났다.

```dockerfile
COPY --chown=catalogguard:catalogguard etl ./etl
```

로컬에서 `docker build --file Dockerfile.aws --tag catalogguard-lite-aws:localfix .` 후 다음을 확인했다.

```text
docker run --rm --entrypoint id catalogguard-lite-aws:localfix -u        # 10001
docker run --rm --entrypoint python catalogguard-lite-aws:localfix -c '
import api; import services; import workers
import etl; import etl.web_service
from api.main import app
'                                                                          # 성공
```

disposable PostgreSQL 18 컨테이너를 대상으로 `alembic upgrade head` -> 기본 CMD(Uvicorn) 시작 -> `/health` HTTP `200`까지 로컬에서 재현해 확인했다.

### Streamlit accessible label 결함

신규 `ETL 실행` selectbox와 기존 ETL 적재 이력 검색 필터(`st.text_input`)가 처음에는 같은 label 문자열 `"공급사 프로필"`을 사용했다. 그 결과 기존 Chromium Browser E2E의 `page.get_by_label("공급사 프로필")`가 두 요소에 동시에 매칭되어 strict-mode violation으로 실패했다.

```text
strict mode violation: get_by_label("공급사 프로필") resolved to 2 elements:
  1) ... aria-label="Selected 패션 공급사 샘플 v1. 공급사 프로필" (combobox)
  2) ... aria-label="공급사 프로필" (textbox)
```

첫 수정은 selectbox label을 `"실행할 공급사 프로필"`로 바꾸는 것이었지만, Streamlit이 combobox의 accessible name을 `"Selected {선택값}. {label}"` 형태로 만들고 Playwright `get_by_label()`은 기본적으로 부분 문자열(substring) 매칭이므로 `"실행할 공급사 프로필"`도 여전히 `"공급사 프로필"`을 부분 문자열로 포함해 같은 위반이 재현되었다. 로컬에서 `scripts/run_etl_browser_e2e.py`를 재실행해 이 재현을 직접 확인한 뒤, label을 `"공급사 프로필"` 문자열 자체를 포함하지 않는 `"ETL 실행 프로필"`로 다시 바꿔 accessible name 충돌 자체를 없앴다. 테스트 코드의 selector(`get_by_label("공급사 프로필")`, `.first()`, `nth()` 등)는 변경하지 않았다.

수정 후 검색 필터의 accessible label은 `"공급사 프로필"`(text_input) 하나만 남고, ETL 실행 selectbox는 `"ETL 실행 프로필"`이라는 별도 label을 갖는다. `tests/e2e/test_etl_browser_e2e.py`의 기존 시나리오(`test_catalog_promotion_success_flow_in_real_browser`, `test_etl_reject_details_are_visible_and_masked_in_real_browser`)는 selector 수정 없이 다시 통과했다.

### 재검증 결과

fix commit(`cb5ed81`) push 후 GitHub Actions run `30969273954`에서 `test`·`browser-e2e` job이 모두 성공했다. `test` job의 `Run tests` 단계는 이번에는 실제로 실행되어 `1189 passed, 4 deselected in 18.24s`를 기록했으며(`0 skipped`, `0 failed`), `Verify AWS image imports`·`Verify AWS container health`·`Run async inspection E2E smoke test`·`Smoke test Streamlit startup` 단계도 모두 성공했다. `browser-e2e` job은 이전의 strict-mode violation 없이 `Chromium E2E 성공` 로그로 종료했다.

## 제한사항

- 합성 패션 공급사 프로필 2종을 지원한다.
- 실제 외부 공급사 운영 데이터 연동은 지원하지 않는다.
- 자동 공급사 감지는 지원하지 않으며, 공급사별 프로필은 수동 선택한다.
- 웹 수집과 외부 API 연동은 지원하지 않는다.
- 웹 ETL(`POST /api/v1/etl-loads`)은 업로드부터 staging 적재까지 하나의 동기 HTTP 요청으로 처리하며, Celery 같은 비동기 실행은 지원하지 않는다.
- 웹 ETL은 한 번에 CSV 파일 1개만 받으며, 여러 파일 동시 업로드나 ZIP 업로드는 지원하지 않는다.
- 웹 ETL은 CSV만 지원하며 XLSX 등 다른 형식은 지원하지 않는다.
- 웹 ETL의 `profile_id`는 서버 allowlist(`etl.profile_loader._ETL_PROFILE_REGISTRY`)로 고정되어 있으며, 사용자가 새 프로필을 업로드하거나 등록하는 Profile CRUD는 지원하지 않는다.
- 웹 ETL CSV 업로드 화면 자체를 다루는 전용 Chromium Browser E2E는 아직 없다. 기존 Browser E2E는 ETL 적재 이력 검색과 promotion 화면만 검증하며, 웹 ETL 핵심 실행 로직은 `tests/etl/test_web_service.py`, `tests/test_api_etl_web_run.py`, `tests/test_catalogguard_api_client.py`, `tests/test_etl_load_history_ui.py`의 API·client·PostgreSQL 통합·Streamlit AppTest로 검증한다.
- staging 상품 수정·삭제와 상품 변경 이력 조회 API는 지원하지 않는다.
- promotion은 외부 공급사 운영 데이터나 production catalog가 아닌 합성 fixture·테스트 PostgreSQL 환경에서만 검증했다. reject 행은 별도 `etl_rejected_rows`에 오류 배열과 마스킹된 동적 원본 컬럼으로 저장한다.
- 배치 출처는 최초 입력 경로 하나만 기록한다. dedup으로 재사용된 배치에 대해 이후 어떤 경로로 다시 들어왔는지는 기록하지 않으며, 수집 사건 단위 이력(ingestion event)은 지원하지 않는다.
- 원본 공급사 CSV bytes는 보존하지 않는다. `input_file_sha256`으로 동일성 검증만 가능하고 원본 복원이나 과거 배치 재처리는 지원하지 않는다.
- migration 이전 기존 배치의 출처는 실제 정보가 없어 `unknown`으로 남으며, 소급 복원할 수 없다.
- 증분 ETL과 streaming은 지원하지 않는다.
- 운영(production) DB 적재는 검증하지 않았다. PostgreSQL staging 적재는 임시 테스트 PostgreSQL 환경에서 검증했고, S3 source 경로에 한해 2026-08-12에 AWS RDS staging에서 합성 fixture 1건으로 추가 검증했다.
- S3 ingestion은 호출자가 `object_key` 하나를 지정하는 pull 방식이다. S3 event 알림·Lambda·SQS 기반 자동 수집, prefix 일괄 처리, 증분 수집은 지원하지 않는다.
- S3 source를 호출하는 Streamlit 화면은 없으며 현재는 API 직접 호출로만 사용한다.
- S3 source의 bucket과 허용 prefix는 서버 환경변수로 고정되어 있어 한 배포가 동시에 여러 bucket을 대상으로 삼을 수 없다.
- 실제 AWS staging S3 E2E는 합성 fixture 1건 기준 수동 검증이며 GitHub Actions에서 자동 재실행되지 않는다.
- 실제 브라우저 E2E는 Chromium 한 종류와 합성 fixture만 검증하며, 운영 환경·모바일 브라우저·외부 공급사는 검증하지 않는다.
- `sale_price`는 단일 할인 가격만 지원하며 할인율, 기간, 쿠폰·회원 가격, 최저가 추천은 제공하지 않는다.
