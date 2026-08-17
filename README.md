<!-- 역할: CatalogGuard Lite 프로젝트의 기능, 실행 방법, 구조를 설명하는 메인 문서입니다. -->

# CatalogGuard Lite

상품 카탈로그 CSV를 업로드해 누락, 형식 오류, 중복, 가격 이상치, 카테고리 불일치, 금지어와 개인정보 의심 정보를 검사하고, 검수 결과를 저장·검색·조회·다운로드하는 Python·FastAPI + PostgreSQL 기반 MVP입니다. Streamlit은 CSV 업로드 검증·검수 결과 화면, 공급사 CSV와 허용된 ETL 프로필을 선택해 웹에서 바로 ETL을 실행하는 화면, ETL 적재 이력과 선택한 batch의 운영 상품 반영 흐름을 담당합니다. JSON 프로필 기반 공급사 CSV ETL과 PostgreSQL staging 적재는 기존 CLI로도 계속 실행할 수 있으며, Streamlit에서 시작한 웹 ETL도 FastAPI를 거쳐 같은 ETL Pipeline과 staging 적재 함수를 재사용합니다. FastAPI는 웹 ETL 실행·ETL 조회·promotion preview·승인된 promotion API를 제공합니다. promotion은 미리보기, 변경 전후 확인, 사용자 승인, preview hash 재검증을 거쳐 운영 상품을 insert/update하고 run과 append-only audit을 저장합니다.

공개 Streamlit 앱은 아래 주소에서 확인할 수 있습니다.

https://catalogguard-lite-p6jtwmdhwqcapphpghfzduo.streamlit.app/

> 공개 Streamlit 앱과 로컬 전체 시스템의 기능 범위는 다를 수 있습니다. 검수 이력과 ETL 적재 이력의 검색·상세 조회는 로컬 또는 별도 배포 환경에서 FastAPI 서버와 PostgreSQL이 함께 실행되어야 사용할 수 있습니다.

프로젝트의 설계·검증 과정은 [포트폴리오 상세 문서](docs/portfolio_project.md), 공급사 변환·HTTP feed Airflow orchestration 흐름은 [ETL MVP 문서](docs/etl_mvp.md), PostgreSQL 쿼리 검증은 [SQL 성능 분석 문서](docs/sql_performance_analysis.md), 합성 fixture 기준의 발표 진행은 [Release / Portfolio Demo Runbook](docs/demo_runbook.md)에서 확인할 수 있습니다.

## 2. 프로젝트 목적

CatalogGuard Lite는 상품 운영자가 CSV로 관리하는 상품 목록을 업로드한 뒤, 등록 전에 발견해야 할 데이터 품질 문제를 빠르게 확인하도록 만든 경량 검수 도구입니다.

주요 목표는 다음과 같습니다.

- 필수 상품 정보가 빠진 행을 찾습니다.
- 잘못된 카테고리, 재고, 가격 값을 찾습니다.
- 같은 상품 ID, 비슷한 상품명, 완전히 같은 상품 내용을 찾습니다.
- 같은 상품 그룹에서 서로 다른 상품 ID가 공유하는 색상·사이즈 조합을 찾습니다.
- 같은 상품 그룹에서 서로 다른 카테고리가 함께 사용된 경우를 찾습니다.
- 상품명과 카테고리가 서로 어울리지 않는 경우를 찾습니다.
- 패션 상품의 알려진 색상·사이즈 별칭을 권장 표준값과 비교합니다.
- 금지어, 이메일, 전화번호, 주민등록번호 형식, 계좌번호 의심 정보를 찾습니다.
- 검수 결과를 화면, CSV 다운로드, PostgreSQL 이력으로 확인할 수 있게 합니다.
- 공급사별 JSON 매핑 프로필로 원본 CSV를 CatalogGuard 표준 CSV로 변환하고 오류 행을 별도 reject CSV로 분리합니다.
- 표준 CSV와 summary JSON을 CLI 또는 Streamlit 업로드 기반 웹 ETL로 PostgreSQL staging에 배치 적재하고, 같은 원본·프로필 버전의 중복 적재를 막습니다.
- Streamlit에서 공급사 CSV를 업로드하고 서버가 허용하는 ETL 프로필을 선택해 FastAPI를 통해 같은 ETL Pipeline과 staging 적재 함수로 웹에서 바로 ETL을 실행합니다.
- ETL 적재 배치 목록과 배치별 staging 상품을 FastAPI로 조회합니다.
- 운영 상품 persistence 모델, promotion 실행 이력, append-only 상품 변경 이력을 PostgreSQL 제약조건과 함께 관리합니다.

## 3. 주요 기능

- CSV 입력 템플릿 다운로드
- CSV 업로드와 상위 100행 미리보기
- 파일 확장자, 파일 크기, 인코딩, 헤더, 행 수 검증
- 개인정보 의심 값 마스킹
- 필수값 누락 탐지
- 잘못된 데이터 형식 탐지
- 상품 ID, 상품명, 상품 내용 중복 탐지
- 상품 그룹 내 색상·사이즈 옵션 조합 중복 탐지
- 상품 그룹 내 카테고리 일관성 검수
- 상품 그룹 내 사이즈 체계 일관성 검수
- 가격 오류와 카테고리별 가격 이상치 탐지
- 상품명과 카테고리 불일치 탐지
- 알려진 색상 별칭을 권장 표준 색상으로 안내
- 알려진 사이즈 별칭을 권장 표준 사이즈로 안내
- 금지어와 위험 표현 탐지
- 이메일, 전화번호, 주민등록번호, 계좌번호 의심 정보 탐지
- 상태, 오류 항목, 상품 ID 기준 검수 결과 필터
- 필터 적용 전 전체 결과 기준 오류 항목별·위험 수준별 발생 건수와 문제가 많은 상품 TOP 5 통계
- CSV 검수 화면과 검수 이력 상세 화면의 공통 통계 UI
- 문제 0건, 통계 생성 실패, 검수 요약과 상세 건수 불일치 시 안전한 안내
- 현재 필터 결과 CSV 다운로드
- 검수 결과 PostgreSQL 저장
- 검수 이력 목록 조회와 페이지 이동
- 파일명 부분 검색
- 검수 이력 상세 조회
- 상세 결과 CSV 다운로드
- 같은 Streamlit 세션 안에서 동일 CSV 중복 저장 방지
- PostgreSQL DB 수준 동일 CSV 중복 저장 방지
- ETL staging 배치와 정상 상품 행의 PostgreSQL 저장
- ETL summary의 output SHA-256·행 수·품질 요약 검증과 배치 단위 rollback
- `total_rows`, `loaded_rows`, `rejected_rows`, `error_counts`의 PostgreSQL JSONB 저장과 기존 배치 NULL 호환
- reject CSV의 SHA-256·행 수·구조화된 오류 배열 검증과 `etl_rejected_rows` JSONB 저장
- reject 원본 값의 개인정보·계좌번호 마스킹과 API·Streamlit reject 상세 조회
- DB에서 staging 부모 배치를 삭제할 때의 상품 행 cascade와 음수 stock·price·sale_price 방지 제약
- ETL 적재 배치 목록의 파일명·프로필명 검색과 페이지네이션
- ETL 적재 목록·상세의 전체 행·정상 적재·변환 거부 수와 상세 오류 코드 통계
- ETL 적재 상세의 input/output SHA-256 및 배치별 staging 상품 페이지네이션
- ETL 적재 목록·상세에서 배치를 최초로 만든 입력 경로(업로드/S3/HTTP feed/CLI) 확인. 중복으로 재사용된 배치는 최초 경로를 유지하며, HTTP feed URL 원문이나 S3 bucket 이름은 저장하지 않습니다.
- Streamlit `ETL 적재 이력` 탭에서 목록·검색·배치 상세·품질 지표·오류 코드·SHA-256·staging 상품·reject 상세 조회
- Playwright Chromium 실제 브라우저에서 ETL 검색·상세·상품·reject 마스킹과 raw 민감정보 미노출 검증
- ETL 목록의 빈 결과 안내, 404와 검증된 `X-Request-ID` 표시
- 배치 변경 시 이전 상세·상품 상태 초기화와 실패 상세 요청의 중복 API 호출 방지
- 기본값인 `즉시 검수`와 Redis·Celery를 사용하는 `백그라운드 검수` 선택
- 백그라운드 작업의 `queued`, `running`, `succeeded`, `failed` 상태와 수동 새로고침
- 비동기 결과도 기존 검수 요약·통계·필터·다운로드 화면으로 표시
- Streamlit은 업로드 검증과 미리보기만 담당하고, 전체 검수의 단일 기준은 FastAPI 서버로 유지
- `POST /api/v1/inspections` 한 번으로 검수 실행과 이력 저장을 처리하고, `GET` 상세 응답을 화면에 재사용
- 서버 응답의 실행 ID·요약·상세 결과를 검증한 뒤에만 Streamlit 세션 상태에 저장
- FastAPI 오류 응답의 요청 ID를 API Client 예외까지 전달
- Streamlit API 오류 화면에 검증된 요청 ID 표시
- 요청 ID를 이용한 Railway 구조화 로그 추적
- `etl.cli`를 통한 공급사 CSV 표준화, reject CSV·요약 JSON 생성
- `etl.load_cli`를 통한 표준 CSV·summary JSON의 PostgreSQL staging 적재
- Streamlit `ETL 실행` 영역에서 공급사 CSV 업로드와 서버 allowlist 기반 ETL 프로필 선택
- `GET /api/v1/etl-profiles/{profile_id}`와 Streamlit `ETL 실행` 영역의 조회 전용 프로필 상세로 선택한 프로필의 `profile_name`·`profile_version`·컬럼 매핑·필수 원본 컬럼·기본값 확인(프로필 수정·등록은 지원하지 않음)
- `POST /api/v1/etl-loads`로 업로드 CSV와 profile_id를 받아 기존 `run_pipeline()`·`load_standard_csv()`를 그대로 실행하고 PostgreSQL staging까지 적재
- 동일한 원본 파일 해시·프로필 이름·버전의 웹 ETL 요청은 새 배치를 만들지 않고 기존 배치를 `created=false`로 재사용
- 웹 ETL 성공 후 ETL 적재 이력 캐시만 자동 무효화하고, 운영 상품 반영은 사용자가 이력에서 batch를 선택해 별도로 진행
- `POST /api/v1/etl-loads/s3`로 서버에 설정된 private S3 bucket의 허용 prefix 객체만 읽어 같은 `run_web_etl()` 흐름으로 staging까지 적재(업로드 대신 S3를 입력원으로 사용하는 source adapter이며 별도 ETL pipeline이 아님)
- S3 source는 bucket·prefix를 서버 환경변수로 고정하고 요청은 `object_key`만 받으며, prefix 밖 key 차단·HeadObject 기반 크기 제한·bounded read를 적용
- `POST /api/v1/etl-loads/http`로 서버에 설정된 신뢰 공급사 HTTP feed의 CSV를 읽어 같은 `run_web_etl()` 흐름으로 staging까지 적재(세 번째 ETL pipeline이 아니라 세 번째 source adapter)
- HTTP feed source는 URL을 서버 환경변수로 고정하고 요청은 `profile_id`만 받으며, 외부 host는 `https`만 허용·redirect 비허용·bounded timeout·bounded read를 적용해 SSRF와 과대 응답을 차단
- 실제 AWS staging(ap-northeast-2)에서 private S3 → EC2 Instance Role 최소권한(`s3:GetObject` + 정확한 prefix) → FastAPI → 기존 ETL pipeline → RDS PostgreSQL 적재까지 E2E 검증
- ETL batch를 명시적으로 선택하는 catalog promotion preview
- insert/update/unchanged 건수와 상품별 변경 전·후 값 표시
- 반영 가능 여부·차단 사유·사용자 승인 checkbox·SHA-256 preview hash 재검증
- 승인된 promotion transaction, 운영 상품 insert/update, promotion run 상태와 append-only audit 저장
- stale preview·중복 promotion·Streamlit rerun 상태 초기화와 안전한 오류 mapping
- PostgreSQL·FastAPI·Streamlit·Chromium Playwright 전체 promotion E2E와 PostgreSQL 최종 상태 검증
- Promotion 실행 이력과 상품별 변경 audit 조회
- Promotion Rollback preview로 대상 상품과 현재 Catalog 상태의 conflict 확인
- Preview hash 재검증과 서버 confirmation을 거치는 transaction 기반 Rollback
- INSERT promotion 상품 삭제, UPDATE promotion 상품 이전 상태 복원과 원본 promotion audit 보존
- Rollback 실행 이력 목록·상세 조회와 상품별 Rollback Change Audit(delete/restore, 원본 Audit ID, 변경 필드별 전·후 값) 조회
- Streamlit에서 Rollback 실행 이력·상세·상품 Rollback 변경 Audit 확인과 reload 없는 이력 갱신
- 실제 Chromium E2E에서 Rollback Change Audit 화면 표시와 PostgreSQL audit·최종 Catalog 상태까지 검증
- Streamlit 로그인과 JWT Access Token 발급, viewer(조회)·operator(운영 데이터 변경) 역할 분리
- FastAPI의 모든 보호된 endpoint에서 현재 사용자와 역할을 서버가 최종 검증(Streamlit 버튼 비활성화는 편의 기능일 뿐 실제 보안 경계는 아님)
- Sync·Async Inspection과 Web ETL·Promotion·Rollback이 새 실행 이력 row를 만들면 인증된 JWT `current_user`를 actor로 기록(Actor Audit MVP). 동일 CSV·검수 버전의 기존 `inspection_run`을 재사용할 때는 최초 actor를 유지
- Prometheus 기반 HTTP·Web ETL Observability MVP: HTTP 요청 수·응답 시간·상태 계열과 Web ETL 신규/중복/실패·처리 행 수를 low-cardinality metric으로 `GET /metrics`에 노출(기본 비활성)
- Kubernetes Deployment Readiness MVP: 기존 `Dockerfile.aws` image를 그대로 사용해 kind 기반 GitHub Actions에서 PostgreSQL → Alembic Migration Job → FastAPI Deployment → Service → `/health`·`/ready`까지 실제 배포·검증
- Terraform AWS Staging IaC Validation MVP: 콘솔에서 수동 구성했던 AWS staging(EC2·RDS·Security Group·SSM)을 `terraform/` 코드로 옮기고, mock provider 기반 보안 정책 테스트와 GitHub Actions `terraform-validate` job으로 자동 검증(실제 `terraform apply`는 수행하지 않음)

## 4. 사용자 기능 흐름

```text
CSV 검수 탭
-> CSV 입력 템플릿 다운로드
-> 상품 CSV 작성
-> CSV 파일 업로드
-> 파일명, 크기, 인코딩, 헤더, 행 수 검증
-> 개인정보가 마스킹된 미리보기 확인
-> 즉시 검수(기본값) 또는 백그라운드 검수 선택
-> 백그라운드 검수는 상태 새로고침으로 진행 상태 확인
-> 검수 요약 확인
-> 필터 적용 전 전체 검수 결과 통계 확인
-> 오류/주의 상세 결과 확인
-> 상태, 오류 항목, 상품 ID로 필터
-> 현재 필터 결과 CSV 다운로드
-> 검수 실행 및 이력 저장 버튼 클릭
-> FastAPI가 검수·저장하고 상세 결과 반환
-> 반환된 결과를 화면에 표시
```

```text
검수 이력 탭
-> FastAPI 서버 연결
-> 저장된 검수 이력 목록 조회
-> 파일명 검색
-> 이전/다음 페이지 이동
-> 검수 실행 선택
-> 상세 결과 조회
-> 전체 검수 결과 통계 확인
-> 상세 결과 CSV 다운로드
-> 목록으로 돌아가기
```

검수 결과 저장이나 검수 이력 조회 중 API 오류가 발생하면 Streamlit의 안전한 오류 안내에서 요청 ID를 확인하고, 운영자는 Railway 로그에서 같은 `request_id`를 검색해 해당 요청을 추적할 수 있습니다. 서버 응답이 없는 timeout이나 연결 실패에는 요청 ID를 표시하지 않습니다.

```text
API 오류 발생
-> Streamlit 오류 안내 확인
-> 요청 ID 확인
-> Railway 로그에서 같은 request_id 검색
```

같은 CSV를 이미 저장한 경우에는 PostgreSQL에 저장된 파일 해시와 검수 규칙 버전을 기준으로 기존 실행 ID를 안내합니다. 같은 Streamlit 세션 안에서는 `saved_file_hash`, `saved_inspection_run_id` 상태값으로 저장 API 재호출을 줄이고, 브라우저나 Streamlit 서버를 재시작한 뒤에는 DB의 중복 제약조건으로 새 이력이 중복 생성되지 않도록 막습니다.

공급사 CSV의 변환·적재·조회·운영 반영 흐름은 다음과 같습니다. ETL 변환과 staging 적재는 CLI 또는 Streamlit 기반 웹 ETL로 실행할 수 있으며, 두 경로 모두 같은 `run_pipeline()`·`load_standard_csv()`를 재사용합니다. FastAPI는 웹 ETL 실행, 저장된 배치 조회와 별도의 promotion API를 제공합니다.

```text
공급사 원본 CSV
-> JSON 프로필 선택 (CLI) 또는 Streamlit에서 허용된 ETL 프로필 선택 (웹)
-> 표준 컬럼 변환
-> 정상 행과 reject 행 분리
-> 표준 CSV·reject CSV·summary JSON 생성
-> 파일 해시와 행 수 검증
-> PostgreSQL staging 적재
-> 오류 배열·마스킹된 reject 원본 저장
-> 중복 적재 방지
-> ETL 적재 배치 목록·상세 API 조회
-> CatalogGuard 검수
-> 검수 결과 PostgreSQL 저장
-> FastAPI 조회
-> Streamlit 결과·통계·다운로드
-> 사용자가 ETL batch 직접 선택
-> promotion preview 실행
-> insert/update/unchanged 및 상품별 변경 전·후 확인
-> 승인 checkbox 선택
-> expected_preview_hash와 함께 promotion 요청
-> 운영 상품 insert/update 및 promotion run(actor 포함)·audit 저장
-> Promotion 실행 이력 조회
-> 필요 시 Rollback Preview 확인
-> conflict 없으면 confirmation 후 Rollback 실행(actor 포함 rollback run 저장)
-> Rollback 실행 이력 갱신
-> Rollback 실행 선택 후 상세 조회
-> 상품별 Rollback 변경 Audit 확인
```

웹 ETL 실행 흐름은 다음과 같습니다.

```text
Streamlit ETL 실행 영역
-> GET /api/v1/etl-profiles로 허용된 프로필 목록 조회
-> "ETL 실행 프로필" 선택
-> 공급사 CSV 업로드
-> ETL 실행 버튼 클릭 (파일 선택·프로필 변경만으로는 API 호출 안 함)
-> POST /api/v1/etl-loads
-> 기존 run_pipeline()·load_standard_csv() 실행
-> current_user 기준 actor_user_id·actor_username 저장
-> 정상/거부 행 수와 배치 ID 표시
-> ETL 적재 이력 캐시 무효화
-> ETL 적재 이력에서 새 배치 확인
```

웹 ETL 성공이 운영 상품 반영을 자동으로 시작하지는 않습니다. 사용자가 ETL 적재 이력에서 새로 생성된 batch를 직접 선택한 뒤 기존 promotion preview·승인 흐름을 그대로 사용합니다. 배치 조회 API가 CatalogGuard 검수나 promotion을 자동으로 실행하는 것도 아닙니다. 생성된 표준 CSV의 검수, staging 적재 이력 조회, 선택한 batch의 promotion preview와 실제 반영은 각각의 API·CLI 호출로 구분합니다. Streamlit은 DB에 직접 쓰지 않고 `CatalogGuardApiClient`를 통해 FastAPI를 호출합니다.

succeeded promotion run은 되돌릴 수 있습니다. Rollback preview는 해당 promotion이 만든 after 상태와 현재 Catalog 상태를 비교해 그 사이에 다른 변경이 있었는지 확인하고, 값이 달라졌으면 conflict로 표시해 실행을 막습니다. 문제가 없으면 사용자 confirmation과 preview hash 재검증을 거쳐 하나의 transaction으로 INSERT promotion 상품은 삭제하고 UPDATE promotion 상품은 이전 상태로 복원합니다. 원본 promotion audit은 상품이 삭제된 뒤에도 삭제하지 않고 별도 rollback audit과 함께 보존합니다. 되돌린 뒤에는 Rollback 실행 이력에서 실행을 선택해 상세와 상품별 Rollback 변경 Audit(어떤 상품이 어떤 원본 audit을 되돌렸고, delete인지 restore인지, 어떤 필드가 어떤 값으로 바뀌었는지)을 확인할 수 있습니다.

## 5. 전체 시스템 구조

CSV를 검수하는 기본 흐름은 FastAPI 서버와 공통 검수 서비스가 담당합니다. Streamlit은 파일 형식 검증, 개인정보 마스킹 미리보기, 요청·응답 표시를 담당하며 전체 규칙을 다시 실행하지 않습니다.

```text
CSV 업로드
-> Streamlit app.py: 업로드 사전 검증·마스킹 미리보기
-> 검수 실행 및 이력 저장 버튼
-> CatalogGuardApiClient
-> FastAPI POST /api/v1/inspections
-> core.upload_validator
-> core.inspection_service
-> core.rules
   -> core.fashion_attribute_validator
   -> core.group_category_consistency_detector
   -> core.group_size_consistency_detector
-> PostgreSQL 저장
-> FastAPI GET /api/v1/inspections/{inspection_run_id}
-> Streamlit이 상세 응답을 DataFrame으로 변환·표시
-> 현재 필터 결과 CSV 다운로드
```

서버 검수 응답은 `apply_inspection_save_response()`에서 실행 ID, `created`, 요약 수치, 상세 결과의 필수 필드를 검증한 뒤에만 세션 상태에 반영합니다. 따라서 부분적이거나 잘못된 응답을 성공 결과로 캐시하지 않습니다.

```text
Streamlit 사전 검증·미리보기
-> FastAPI POST /api/v1/inspections
-> FastAPI가 SHA-256·중복 조회·검수·저장
-> FastAPI GET 상세 응답
-> 기존 history detail 변환기 재사용
-> 결과·통계·필터·다운로드
```

검수 결과를 저장할 때는 Streamlit이 FastAPI에 원본 업로드 파일을 한 번 보내고, FastAPI가 CSV bytes의 SHA-256 해시를 직접 계산합니다. 서버는 `file_sha256`과 `inspection_version`으로 기존 이력을 먼저 조회하고, 같은 파일과 같은 검수 버전이 이미 있으면 새 실행을 만들지 않고 기존 ID를 반환합니다.

```text
CSV 업로드
-> 검수 실행 및 이력 저장 버튼
-> CatalogGuardApiClient
-> FastAPI POST /api/v1/inspections
-> CSV bytes의 SHA-256 계산
-> file_sha256 + inspection_version으로 기존 이력 조회
-> 기존 이력이 있으면 기존 ID 반환
-> 기존 이력이 없으면 검수·저장 후 상세 응답 반환
-> FastAPI GET /api/v1/inspections/{inspection_run_id}
-> Streamlit 결과 표시
-> PostgreSQL partial unique index가 동시 요청 중복 차단
```

세션 중복 방지는 같은 Streamlit 세션에서 같은 파일을 다시 제출할 때 POST·GET 재호출을 줄이는 장치입니다. DB 중복 방지는 PostgreSQL 저장 데이터를 기준으로 판단하므로 브라우저나 Streamlit을 재시작해도 동작하고, 동시에 들어오는 동일 저장 요청도 unique index로 최종 차단합니다.

CSV 검수 규칙은 서버에서만 실행됩니다. 아래의 공통 서비스와 규칙 모듈은 FastAPI 요청 경로에서 호출됩니다.
```text
FastAPI POST /api/v1/inspections
-> core.upload_validator
-> core.inspection_service
-> core.rules
   -> core.fashion_attribute_validator
   -> core.group_category_consistency_detector
   -> core.group_size_consistency_detector
-> core.presentation
-> API 응답의 요약·상세 결과
```

통계 집계는 화면 코드와 분리한 뒤 CSV 검수 화면과 검수 이력 상세 화면에서 같은 방식으로 사용합니다.

```text
필터 적용 전 전체 검수 결과 DataFrame
-> core.presentation.build_inspection_statistics(results_df)
-> 오류 항목별 / 위험 수준별 / 상품별 집계
-> app.render_inspection_statistics(results_df, expected_total_issues)
-> CSV 검수 화면과 검수 이력 상세 화면에 공통 표시
```

`build_inspection_statistics()`는 입력 DataFrame을 변경하지 않고 상품별 전체 집계까지 반환하며, TOP 5 제한은 UI helper인 `render_inspection_statistics()`에서만 적용합니다. 통계에는 필터 전 `result_df`를 사용하고 상세 표와 CSV 다운로드에는 `filtered_result_df`를 사용하므로, 필터를 변경해도 전체 통계는 유지되고 상세 결과만 바뀝니다. 문제 0건, 집계 실패, 저장된 요약과 상세 문제 수 불일치 시에는 통계 표시를 중단하고 내부 예외 원문을 노출하지 않습니다. 이 기능은 기존 DB, API, Alembic migration을 변경하지 않고 추가했습니다.

저장된 이력을 조회할 때는 FastAPI와 PostgreSQL이 필요합니다.

```text
검수 이력 탭
-> Streamlit app.py
-> CatalogGuardApiClient
-> FastAPI GET /api/v1/inspections
-> db.persistence_service
-> db.repositories
-> PostgreSQL
```

FastAPI 오류 응답의 요청 ID는 다음 경로로 Streamlit까지 전달됩니다.

```text
Railway FastAPI
-> X-Request-ID 응답 헤더
-> CatalogGuardApiClient
-> CatalogGuardApiError.request_id
-> Streamlit 오류 화면
```

API Client는 헤더 값의 앞뒤 공백을 제거한 뒤 정확히 32자리인 소문자 16진수만 요청 ID로 인정합니다. 잘못된 형식은 표시하지 않으며, 서버 응답이 없는 timeout과 연결 실패에는 요청 ID가 없습니다. 클라이언트가 임의 요청 ID를 생성하지도 않습니다.

ETL 적재 이력은 검수 이력과 별도 조회 계층을 사용합니다. 같은 `/api/v1/etl-loads` 경로의 `POST`는 조회가 아니라 웹 ETL 실행이며, `api.routes.etl_loads`가 `etl.web_service.run_web_etl()`을 호출해 새 배치를 만든 뒤 아래 조회 계층에서 그대로 조회할 수 있습니다.

```text
FastAPI POST /api/v1/etl-loads
-> etl.web_service.run_web_etl()
-> etl.pipeline.run_pipeline()
-> etl.db_loader.load_standard_csv()
-> PostgreSQL staging

FastAPI GET /api/v1/etl-loads
-> db.etl_query_service
-> etl_load_runs 목록·count
-> PostgreSQL

FastAPI GET /api/v1/etl-loads/{etl_load_run_id}
-> db.etl_query_service
-> 배치 정보와 해당 배치의 staging 상품 페이지
-> PostgreSQL
```

Streamlit의 `ETL 적재 이력` 탭에서 배치 목록·상세·상품 조회 부분은 이 읽기 전용 API를 사용한다. 목록은 화면에서 10건씩 표시하고 파일명·프로필명 검색을 함께 적용할 수 있으며, 선택한 배치의 상세 화면에서는 input/output SHA-256 전체 값과 staging 상품을 20건씩 표시한다. `sale_price`, `description`, `seller`가 `null`인 상품도 빈 값으로 안전하게 표시한다. 운영 상품 반영은 별도의 promotion POST API를 호출한다.

```text
ETL 적재 이력 탭
-> GET /api/v1/etl-loads (limit=10)
-> 파일명·프로필명 검색(AND)
-> 배치 이전·다음 페이지
-> 배치 상세 선택
-> GET /api/v1/etl-loads/{etl_load_run_id} (product_limit=20)
-> SHA-256·nullable 필드·staging 상품 표시
-> 상품 이전·다음 페이지
```

화면은 `CatalogGuardApiClient`를 통해서만 API를 호출하며 DB에 직접 연결하지 않는다. 웹 ETL 실행도 `POST /api/v1/etl-loads`를 통한 API 호출이며, Streamlit이 파일을 직접 PostgreSQL에 적재하지는 않는다. Streamlit rerun 사이에는 정상 응답과 선택 상태를 session state로 유지하고, 검색·배치·상품 페이지가 바뀌면 관련 상태를 초기화한다. 상세 API가 실패한 뒤 같은 화면 rerun에서 동일 요청을 반복하지 않으며, 존재하지 않는 배치는 404와 request ID를 함께 안내한다.

검수 이력 탭의 전체 요약 CSV 다운로드는 같은 목록 API를 재사용합니다. 화면에 보이는 현재 페이지 10건만 쓰지 않고, 사용자가 `CSV 다운로드 준비` 버튼을 누르면 검색 버튼으로 확정된 파일명·날짜·상태 조건을 유지한 채 `limit=100`, `offset=0`부터 반복 조회해 전체 결과를 모은 뒤 CSV로 변환합니다.

```text
현재 검색 조건
-> CSV 다운로드 준비 버튼 클릭
-> FastAPI GET /api/v1/inspections를 100건씩 반복 조회
-> 전체 검수 이력 요약 결합
-> UTF-8-SIG CSV 변환
-> Streamlit 다운로드 버튼
```

```text
검수 상세 결과
-> Streamlit app.py
-> CatalogGuardApiClient
-> FastAPI GET /api/v1/inspections/{inspection_run_id}
-> db.persistence_service
-> db.repositories
-> PostgreSQL
-> 상세 결과 CSV 다운로드
```

서버 검수 입력과 Streamlit 미리보기 입력은 분리합니다. Streamlit은 업로드 검증 뒤 미리보기 복사본을 만들고, 원본 bytes는 FastAPI 서버로 한 번 전달합니다.

```text
업로드 원본 bytes
-> FastAPI의 Product 변환
-> 서버의 실제 검수 규칙에 사용

마스킹된 DataFrame 복사본
-> Streamlit 미리보기에만 사용
```

패션 색상·사이즈 검수는 `core.rules`가 현재 입력값을 `core.fashion_attribute_validator`의 별칭 사전과 비교해 주의 항목을 만듭니다. 중복 옵션 검수는 같은 비교 함수를 재사용해 `product_group_id`, 색상 비교 키, 사이즈 비교 키가 같은 상품을 찾습니다. 권장 표준값과 비교 키는 검수에만 사용하며 원본 DataFrame, 마스킹 미리보기의 색상·사이즈, `Product.color`, `Product.size`는 변경하지 않습니다.

상품 그룹 카테고리 일관성 검수는 `core.group_category_consistency_detector`가 기존 `core.category_mismatch_detector.normalize_category()`를 재사용합니다. 이 비교는 원본 category를 고치지 않으며, 표시 계층에는 JSON 구조화 메시지로 값을 전달합니다. JSON이 손상되거나 예상 구조가 아니어도 내부 prefix, 영문 메시지나 JSON 원문 대신 안전한 한글 기본 문구를 표시합니다.

상품 그룹 사이즈 체계 일관성 검수는 `core.group_size_consistency_detector`가 기존 `core.fashion_attribute_validator.find_standard_size()`와 `SIZE_ALIASES`를 재사용하는 `find_size_system()`으로 각 사이즈를 문자형(ALPHA)·숫자형(NUMERIC)으로만 분류합니다. 판정할 수 없는 값은 비교에서 제외하며, 이 규칙도 원본 사이즈 값을 고치지 않습니다.

Streamlit에 로그인하면 이후 모든 화면과 API 호출이 JWT Access Token을 거칩니다. FastAPI는 매 요청마다 role/is_active를 PostgreSQL에서 다시 확인한 뒤에만 검수·ETL·Promotion·Rollback 로직에 진입시킵니다. Authentication(로그인한 사용자가 누구인지 확인)과 RBAC(그 사용자가 무엇을 할 수 있는지 확인)은 실행 전 통제이고, 새 Inspection·Web ETL·Promotion·Rollback 실행 이력 row가 만들어지면 그 요청의 `current_user`를 actor로 남기는 Actor Audit(누가 실행했는지 기록)이 이어집니다.

```text
Streamlit
-> 로그인(아이디·비밀번호)
-> POST /api/v1/auth/login
-> JWT Access Token 발급
-> CatalogGuardApiClient가 Authorization: Bearer 헤더로 이후 모든 요청에 자동 첨부
-> FastAPI get_current_user(): 토큰 검증 + PostgreSQL users 재조회(role, is_active)
-> require_viewer / require_operator: 역할 검사
-> Inspection / ETL / Promotion / Rollback endpoint 진입
-> 새 Inspection / Web ETL / Promotion / Rollback 실행 이력에 current_user 기준 actor_user_id·actor_username 저장
-> PostgreSQL
```

비동기 검수는 이 인증 단계를 그대로 거친 뒤 별도 경로로 처리합니다.

```text
FastAPI (인증·RBAC 통과 후 작업 등록)
-> current_user.id·current_user.username scalar를 Redis job state에 저장
-> Celery Worker가 scalar actor와 검수 결과를 공통 persistence 계층에 전달
-> PostgreSQL inspection_runs 저장
```

로그인하지 않았거나 토큰이 유효하지 않으면 401을, 로그인은 됐지만 역할이 부족하면 403을 반환합니다. 자세한 endpoint별 권한 표는 18장을 참고하세요.

## 6. 실행 화면

### CSV 템플릿 및 파일 업로드

필수·선택 컬럼을 확인하고 CSV 입력 템플릿을 내려받을 수 있습니다. 작성한 상품 CSV 파일은 업로드 영역에서 검수를 시작할 수 있습니다.

![CatalogGuard Lite CSV 템플릿 및 파일 업로드 화면](docs/images/01_initial_upload.png)

### 개인정보 마스킹 미리보기

업로드한 데이터는 검수 전에 미리보기로 확인할 수 있습니다. 이메일, 전화번호, 주민등록번호 형태는 일부 문자를 가려서 표시합니다.

![CatalogGuard Lite 개인정보 마스킹 미리보기 화면](docs/images/02_masked_preview_summary.png)

> 위 화면은 개인정보 마스킹 기능을 확인하기 위해 가짜 이메일, 전화번호 및 주민등록번호 형태가 포함된 테스트 CSV를 사용한 예시입니다.

### 검수 결과 필터 및 CSV 다운로드

발견된 문제의 상태, 오류 항목과 상품 ID를 기준으로 결과를 필터링할 수 있습니다. 각 문제의 오류 이유, 수정 권장사항과 위험 수준을 확인하고 현재 필터 결과를 CSV로 내려받을 수 있습니다.

![CatalogGuard Lite 검수 결과 필터 및 CSV 다운로드 화면](docs/images/03_results_filter_download.png)

> 위 화면은 `data/dev/products_dev.csv`를 사용한 검수 예시이며, 상품 5개에서 오류 6건이 탐지된 결과입니다.

### 검수 이력 목록과 검색

저장된 검수 실행을 파일명, 날짜 범위와 검수 상태로 검색하고 페이지 단위로 확인할 수 있습니다. 목록에는 실행 사용자를 표시하며, migration 이전 legacy row처럼 actor가 `NULL`이면 `알 수 없음`으로 표시합니다. 현재 검색 조건에 맞는 전체 검수 이력 요약도 실행 사용자를 포함한 CSV로 준비해 내려받을 수 있습니다.

![CatalogGuard Lite 검수 이력 목록과 검색 화면](docs/images/04_history_list.png)

### 검수 이력 상세 결과

선택한 검수 실행의 파일명, 실행 사용자, 검수 시간과 요약 수치를 확인할 수 있습니다. 각 문제의 오류 이유, 수정 권장사항과 위험 수준을 조회하고 상세 결과를 CSV로 내려받을 수 있습니다. legacy `NULL` actor는 `알 수 없음`으로 표시합니다.

![CatalogGuard Lite 검수 이력 상세 결과 화면](docs/images/05_history_detail.png)

### 검수 결과 통계

전체 검수 문제 6건을 오류 항목별, 위험 수준별, 상품별 통계로 한 화면에서 확인할 수 있습니다. 아래 예시는 오류 항목 필터에서 `가격 오류`를 선택해 상세 결과가 3건만 표시된 상태이며, 통계는 필터 적용 전 전체 결과를 기준으로 하므로 6건을 유지합니다.

![검수 결과 통계 화면](docs/images/06_inspection_statistics.png)

### 패션 색상·사이즈 표준화 검수 확인

로컬 업로드 검수 흐름에서 3행 패션 테스트 CSV를 확인한 결과, 비표준 색상 1건과 비표준 사이즈 1건을 찾아 오류 0건, 주의 2건으로 표시했습니다. `MELANGE GRAY`와 숫자 사이즈 `95`는 보수적인 MVP 판정 범위에서 제외되어 새 경고를 만들지 않았습니다. 기존 `data/dev/products_dev.csv`에서도 새 색상·사이즈 규칙으로 인한 불필요한 경고가 발생하지 않음을 확인했습니다.

완전 중복과 옵션 중복 우선순위를 확인하는 6행 CSV를 Streamlit 업로드 흐름에서 재검증한 결과는 전체 문제 7건, 오류 3건, 주의 4건입니다. 완전 중복은 P006에 1건, 실제 옵션만 중복인 P001/P002에는 2건이 표시되었으며, 완전 중복 관계인 P005/P006에는 옵션 중복이 다시 표시되지 않았습니다. 오류·오류 항목·상품 ID 필터와 필터 결과 CSV 다운로드가 정상 동작했고 원본 색상·사이즈·재고·이미지 경로도 유지되었습니다.

### 상품 그룹 카테고리 일관성 검수 확인

`data/dev/group_category_consistency_test.csv`와 실제 `app.py` Streamlit AppTest 경로로 6개 상품을 업로드해 확인했습니다. 전체 문제는 7건으로 오류 6건, 주의 1건이었고, G001의 `TOP`·`SHOES` 불일치가 비교에 참여한 P001, P002, P003 모두에 표시되었습니다. G002의 `BOTTOM`·`bottom`은 같은 비교값이므로 새 불일치가 없었고, G003은 상품 한 건이라 새 불일치가 없었습니다. 오류 필터는 6건, 카테고리 불일치 규칙 필터는 3건, P003 검색은 1건을 표시했으며 결과 CSV 다운로드 URL도 생성되었습니다. 미리보기의 소문자 `bottom` 원본 표기도 유지되었습니다. 검증 후 임시 CSV는 삭제했습니다.

## 7. 기술 스택

| 영역 | 기술 |
|---|---|
| 화면 | Streamlit `1.58.0` |
| API | FastAPI `0.139.0`, Uvicorn `0.49.0`, Pydantic |
| 데이터 처리 | Python `3.11`, pandas `3.0.3` |
| API 클라이언트 | requests `2.34.2` |
| 데이터베이스 | PostgreSQL, SQLAlchemy `2.0.51`, psycopg `3.3.4` |
| 마이그레이션 | Alembic `1.18.5` |
| 인증 | PyJWT `2.10.1`(JWT, HS256), bcrypt `4.2.1`(password hash) |
| 관측성 | prometheus-client `0.25.0`(HTTP·Web ETL metric instrumentation, `GET /metrics`) |
| 비동기 처리 | Redis `7.4`, Celery `5.6.3` |
| Kubernetes(CI 검증) | kind `v0.32.0`, kubectl `v1.36.2`, kind node `kindest/node:v1.36.1`(SHA-256 digest 고정) |
| IaC(CI 검증) | Terraform `1.15.8`, AWS Provider `6.55.0`(`.terraform.lock.hcl` 고정), mock provider 기반 `terraform test` |
| 로컬 실행 | Docker Compose |
| 테스트 | pytest |
| CI | GitHub Actions |
| CI 테스트 서비스 | PostgreSQL `18`·Redis `7.4` 서비스 컨테이너 |

`requirements.txt`에는 Streamlit 앱 실행에 필요한 기본 패키지가 있고, `requirements-api.txt`에는 FastAPI와 PostgreSQL 저장 계층에 필요한 패키지가 있습니다. FastAPI도 pandas 기반 검수 로직을 사용하므로 로컬 전체 시스템을 실행할 때는 두 파일을 모두 설치하는 것이 안전합니다. 실제 브라우저 E2E는 `requirements-e2e.txt`로 별도 설치하며, Playwright와 호환되는 pytest 8 환경을 사용합니다.

```powershell
python -m pip install -r requirements-e2e.txt
python -m playwright install chromium
```

GitHub Actions는 일반 `test` job에서 PostgreSQL·Redis 서비스, Alembic 마이그레이션, E2E를 제외한 전체 pytest와 비동기 검수 smoke를 실행하고, `Dockerfile.aws` image build·import·UID `10001`·PostgreSQL migration·기본 CMD Uvicorn·`/health` HTTP `200`도 확인합니다. `Dockerfile.aws`는 `api`·`config`·`core`·`db`·`etl`·`services`·`workers` package를 모두 image에 포함하며, import 검증은 `api.main` import 시 연결되는 `api.routes.etl_loads` -> `etl.*` import chain까지 실제로 확인합니다. 별도 `browser-e2e` job에서는 PostgreSQL 서비스와 Chromium을 사용해 ETL CLI·Loader·FastAPI·Streamlit·실제 브라우저 흐름을 검증합니다. AWS runtime smoke는 실제 AWS 배포가 아니며, 배포는 수행하지 않습니다. 세 번째 `kubernetes-smoke` job은 같은 `Dockerfile.aws` image를 kind 실제 Kubernetes cluster에 배포해 `/health`·`/ready`까지 확인합니다(자세한 내용은 16장 "Kubernetes Deployment Readiness" 참고). 네 번째 `terraform-validate` job은 실제 AWS 자격 증명 없이 `terraform/`의 fmt·init·validate와 mock provider 기반 `terraform test`만 실행하며, `terraform apply`는 수행하지 않습니다(자세한 내용은 16장 "Terraform AWS Staging IaC Validation" 참고).

다섯 번째 `airflow-smoke` job은 분리된 Airflow 3.3.0 / Python 3.11 image와 PostgreSQL 17 metadata DB, 별도 CatalogGuard test DB, DAG processor, deterministic HTTP feed를 기동한다. 이어 Airflow migration·기존 Alembic migration·DAG import/structure·실제 staging load·idempotency·lineage를 검증한다.

## 8. 프로젝트 폴더 구조

```text
catalogguard-lite/
  .github/
    workflows/
      test.yml
  README.md
  app.py
  clients/
    __init__.py
    catalogguard_api.py
  api/
    __init__.py
    main.py
    schemas.py
    dependencies.py
    routes/
      __init__.py
      auth.py
      etl_loads.py
      inspections.py
      inspection_jobs.py
  config/
    database.py
    metrics.py
    settings.py
    etl/
      sample_fashion_vendor_v1.json
      sample_marketplace_vendor_v1.json
  core/
    __init__.py
    category_mismatch_detector.py
    duplicate_detector.py
    fashion_attribute_validator.py
    group_category_consistency_detector.py
    group_size_consistency_detector.py
    inspection_service.py
    loader.py
    models.py
    presentation.py
    price_anomaly_detector.py
    privacy.py
    product_template.py
    result_exporter.py
    rules.py
    security.py
    upload_validator.py
  db/
    __init__.py
    auth_service.py
    base.py
    etl_query_service.py
    models.py
    persistence_service.py
    repositories.py
    session.py
  services/
    inspection_job_service.py
    job_files.py
    redis_job_store.py
  workers/
    celery_app.py
    inspection_tasks.py
  etl/
    cli.py
    models.py
    pipeline.py
    profile_loader.py
    transformer.py
    web_service.py
  compose.local.yaml
  alembic/
    env.py
    script.py.mako
    versions/
      20260703_0001_create_inspection_tables.py
      20260705_0002_add_inspection_file_identity.py
      20260725_0003_create_etl_staging_tables.py
      20260727_0004_add_etl_quality_summary.py
      20260728_0005_add_etl_rejected_rows.py
      20260728_0006_create_catalog_promotion_tables.py
      20260803_0007_create_catalog_promotion_rollback_tables.py
      20260803_0008_allow_catalog_product_audit_detach.py
      20260805_0009_create_users_table.py
      20260806_0010_add_actor_audit_columns.py
      20260808_0011_add_promotion_audit_order_index.py
      20260810_0012_add_inspection_actor_audit.py
      20260813_0013_add_etl_initial_source_lineage.py
  data/
    dev/
      category_mismatch_test.csv
      price_anomaly_test.csv
      privacy_masking_test.csv
      products_dev.csv
  docs/
    images/
      01_initial_upload.png
      02_masked_preview_summary.png
      03_results_filter_download.png
      04_history_list.png
      05_history_detail.png
      06_inspection_statistics.png
    portfolio_project.md
    etl_mvp.md
    sql_performance_analysis.md
  tests/
    test_api_etl_loads.py
    test_api_health.py
    test_api_logging.py
    test_api_inspections.py
    test_app_history_download_helpers.py
    test_app_history_helpers.py
    test_app_inspection_save_helpers.py
    test_app_smoke.py
    test_catalogguard_api_client.py
    test_category_mismatch_detector.py
    test_database_connection.py
    test_database_models.py
    test_duplicate_detector.py
    test_etl_query_service.py
    test_fashion_attribute_validator.py
    test_group_category_consistency_detector.py
    test_group_size_consistency_detector.py
    test_inspection_persistence.py
    test_inspection_service.py
    test_loader.py
    test_metrics.py
    test_presentation.py
    test_price_anomaly_detector.py
    test_privacy.py
    test_product_template.py
    test_result_exporter.py
    test_rules.py
    test_upload_validator.py
    etl/
      test_cli.py
      test_pipeline.py
      test_profile_loader.py
      test_transformer.py
  k8s/
    catalogguard-api.yaml
    dev-postgres.yaml
    migration-job.yaml
  terraform/
    .terraform.lock.hcl
    main.tf
    outputs.tf
    variables.tf
    versions.tf
    tests/
      staging.tftest.hcl
  .env.example
  alembic.ini
  requirements.txt
  requirements-api.txt
```

## 9. 주요 파일 역할

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit 화면, CSV 검수·이력 탭, 공통 통계 UI, 검수 저장, 목록·상세·CSV 다운로드, API 오류 안내와 요청 ID 표시 |
| `clients/catalogguard_api.py` | FastAPI 검수·ETL·promotion API 호출, 응답 schema·SHA-256 검증, HTTP·404·JSON 오류 mapping |
| `api/main.py` | FastAPI 앱 생성, 라우터 등록, `/health`와 `/ready`, 요청 ID 및 요청 단위 로그 처리 |
| `api/routes/etl_loads.py` | 웹 ETL 실행(`POST /api/v1/etl-loads`)과 ETL 프로필 목록 조회, ETL 조회와 promotion preview·실행 endpoint, Query·Path 검증, 오류 응답과 응답 변환 |
| `api/routes/inspections.py` | 검수 생성, JWT `current_user` actor 전달, 서버 SHA-256 계산, 중복 이력 응답, actor를 포함한 검수 이력 목록·상세 조회 API |
| `api/schemas.py` | `actor_username`을 포함한 검수·ETL 조회·promotion API 응답 Pydantic 모델과 `LoginRequest`/`LoginResponse`/`CurrentUserResponse` |
| `api/dependencies.py` | `get_current_user()`(JWT 검증 + PostgreSQL 재조회), `require_viewer`/`require_operator` RBAC dependency |
| `api/routes/auth.py` | `POST /api/v1/auth/login`(Access Token 발급), `GET /api/v1/auth/me` |
| `config/logging.py` | 중복 handler 없이 한 줄 JSON 운영 로그를 기록하는 표준 라이브러리 유틸리티 |
| `config/settings.py` | CSV 컬럼, 허용 카테고리, 카테고리별 필수 패션 속성 정책, 업로드 제한, 금지어, API 클라이언트 환경변수, `INSPECTION_VERSION` |
| `config/database.py` | `DATABASE_URL`, `TEST_DATABASE_URL` 환경변수 읽기와 검증 |
| `config/metrics.py` | `CATALOGGUARD_METRICS_ENABLED` 파싱, 전용 Prometheus `CollectorRegistry`와 metric 4개 정의, HTTP·Web ETL metric 기록 helper |
| `core/inspection_service.py` | FastAPI 요청에서 실행되는 공통 CSV 검수 서비스 |
| `core/upload_validator.py` | 업로드 CSV 파일명, 크기, 인코딩, 헤더, 행 수 검증 |
| `core/rules.py` | 전체 검수 규칙 실행 |
| `core/duplicate_detector.py` | 상품 ID·상품명과 상품 그룹 내 색상·사이즈 옵션 조합 중복 탐지 |
| `core/group_category_consistency_detector.py` | 상품 그룹별 카테고리 정규화 비교, 입력 순서 유지와 안전한 JSON 메시지 생성·검증 |
| `core/group_size_consistency_detector.py` | 상품 그룹별 사이즈 체계(ALPHA·NUMERIC) 비교와 혼재 그룹의 주의 항목 생성 |
| `core/fashion_attribute_validator.py` | 패션 색상·사이즈 별칭을 권장 표준값으로 찾고 원본을 바꾸지 않는 비교 키를 만드는 순수 함수 |
| `core/presentation.py` | 내부 검수 문제를 화면용 한글 결과표로 변환하고 전체 검수 결과 통계를 집계 |
| `core/result_exporter.py` | 검수 결과 CSV 다운로드 데이터와 파일명 생성 |
| `core/product_template.py` | CSV 입력 템플릿 생성 |
| `core/privacy.py` | 개인정보 정규식과 마스킹 처리 |
| `core/security.py` | bcrypt 비밀번호 hash·검증, JWT Access Token 발급·검증 |
| `db/models.py` | actor FK·snapshot을 포함한 `inspection_runs`, `inspection_results`, ETL staging 배치·상품, `users` SQLAlchemy 모델 |
| `db/auth_service.py` | `users` 조회, 로그인 인증(`authenticate_user`), 계정 생성(`create_user`, bootstrap CLI 전용) |
| `db/etl_query_service.py` | 필터·정렬·count·SQL 페이지네이션을 적용하는 읽기 전용 ETL 배치·상품 조회 Service |
| `db/repositories.py` | actor를 포함한 검수 실행과 상세 결과 저장·조회, 파일 identity 조회 Repository |
| `db/persistence_service.py` | 검수 결과와 최초 actor 저장 트랜잭션, 중복 조회·최초 actor 보존, 경쟁 상태 처리, 목록·상세 조회 Service |
| `db/session.py` | SQLAlchemy 엔진, 세션 팩토리, DB 연결 확인, FastAPI 세션 의존성 |
| `ui/auth.py` | Streamlit 로그인·로그아웃 UI, `session_state` 기반 Access Token 저장, 인증된 API Client 생성 |
| `ui/etl_load_history.py` | ETL 목록·검색·페이지네이션·상세·promotion 승인 UI. viewer는 실행 버튼이 비활성화되지만 실제 차단은 FastAPI가 수행 |
| `services/redis_job_store.py` | Redis에 비동기 검수 작업 상태, optional actor scalar와 TTL 저장. actor 필드가 없는 legacy payload도 `None`으로 복원 |
| `services/inspection_job_service.py`, `services/job_files.py` | actor scalar를 포함한 작업 제출, 서버 생성 job 파일 저장·검증·정리 |
| `workers/celery_app.py`, `workers/inspection_tasks.py` | Celery Worker 실행과 Redis actor scalar를 사용한 비동기 CSV 검수·결과 저장 |
| `etl/profile_loader.py`, `etl/transformer.py`, `etl/pipeline.py` | JSON 프로필 검증, 공급사 행 변환, reject 분리와 원자적 출력 저장. `profile_loader.py`는 웹 ETL이 사용하는 `profile_id` allowlist(`get_profile_path()`)도 함께 제공 |
| `etl/cli.py` | 공급사 CSV ETL CLI 진입점 |
| `etl/db_loader.py` | 표준 CSV·summary JSON 검증, 중복 배치 조회와 staging 트랜잭션 적재. CLI(`load_cli.py`)와 웹 ETL(`web_service.py`)이 함께 재사용 |
| `etl/load_cli.py` | ETL 결과를 PostgreSQL staging에 적재하는 별도 CLI 진입점 |
| `etl/web_service.py` | 업로드 bytes를 `TemporaryDirectory`에 저장해 기존 `run_pipeline()`·`load_standard_csv()`를 실행하는 웹 ETL 진입점(`run_web_etl()`) |
| `scripts/run_etl_browser_e2e.py` | 테스트 DB migration, ETL CLI·Loader, FastAPI·Streamlit readiness, Playwright 실행과 cleanup을 담당하는 E2E runner |
| `scripts/create_user.py` | 로그인 계정을 생성하는 bootstrap CLI(회원가입 API 없음). `--username`, `--role`, 비밀번호는 인자·환경변수·interactive prompt 중 하나로 지정 |
| `tests/e2e/test_etl_browser_e2e.py` | 실제 Chromium의 ETL 탭·promotion 승인·반영·reject 마스킹·raw 미노출과 PostgreSQL 최종 상태 검증 |
| `tests/fixtures/e2e/etl_browser_vendor.csv` | 정상 2행·복수 오류 reject 1행과 합성 민감정보를 담은 브라우저 E2E fixture |
| `config/etl/sample_fashion_vendor_v1.json` | 샘플 공급사 컬럼과 CatalogGuard 표준 컬럼 매핑 프로필 |
| `config/etl/sample_marketplace_vendor_v1.json` | 별도 상품 그룹 ID와 SKU를 사용하는 두 번째 합성 공급사 매핑 프로필 |
| `compose.local.yaml` | PostgreSQL·Redis·FastAPI·Celery Worker 로컬 실행 구성 |
| `alembic/versions/20260703_0001_create_inspection_tables.py` | 검수 이력 저장 테이블 생성 마이그레이션 |
| `alembic/versions/20260705_0002_add_inspection_file_identity.py` | 파일 해시와 검수 버전 컬럼, CHECK constraint, partial unique index 추가 마이그레이션 |
| `alembic/versions/20260725_0003_create_etl_staging_tables.py` | ETL 배치·상품 staging 테이블, unique index, FK와 CHECK constraint 추가 마이그레이션 |
| `alembic/versions/20260805_0009_create_users_table.py` | `users` 테이블(`username` unique, `role` CHECK, `is_active`) 생성 마이그레이션 |
| `alembic/versions/20260806_0010_add_actor_audit_columns.py` | `etl_load_runs`·`catalog_promotion_runs`·`catalog_promotion_rollbacks`에 `actor_user_id`(FK `ON DELETE SET NULL`)·`actor_username` nullable 컬럼 추가 마이그레이션 |
| `alembic/versions/20260808_0011_add_promotion_audit_order_index.py` | promotion audit 페이지네이션을 위한 `(promotion_run_id, created_at DESC, id DESC)` 정렬 index 추가 마이그레이션 |
| `alembic/versions/20260810_0012_add_inspection_actor_audit.py` | `inspection_runs`에 `actor_user_id`(FK `ON DELETE SET NULL`)·`actor_username` nullable 컬럼을 추가하는 Inspection Actor Audit 마이그레이션 |
| `alembic/versions/20260813_0013_add_etl_initial_source_lineage.py` | `etl_load_runs`에 최초 입력 경로를 기록하는 `initial_source_type`·`initial_source_ref`를 추가하는 ETL lineage 마이그레이션 |
| `.github/workflows/test.yml` | 일반 테스트와 분리된 `browser-e2e`·`kubernetes-smoke` job을 포함해 PostgreSQL·Chromium 실제 브라우저 흐름과 kind 실제 Kubernetes 배포까지 실행하는 GitHub Actions workflow |
| `k8s/dev-postgres.yaml`, `k8s/migration-job.yaml`, `k8s/catalogguard-api.yaml` | kind CI 전용 PostgreSQL, Alembic Migration Job, FastAPI Deployment/Service manifest |
| `.env.example` | 로컬 PostgreSQL 연결 환경변수 예시 |
| `requirements.txt` | Streamlit 앱 기본 실행 패키지 |
| `requirements-api.txt` | FastAPI, PostgreSQL, Alembic 관련 패키지 |
| `requirements-e2e.txt` | Playwright Chromium과 pytest-playwright 선택적 E2E 패키지 |

## 10. CSV 입력 컬럼

필수 컬럼은 9개입니다.

| 컬럼 | 설명 |
|---|---|
| `product_group_id` | 옵션 상품을 묶는 상품 그룹 ID |
| `product_id` | 개별 상품 ID |
| `product_name` | 상품명 |
| `category` | 상품 카테고리 |
| `color` | 색상 |
| `size` | 사이즈 |
| `stock` | 재고 수량 |
| `price` | 판매 가격 |
| `image_path` | 상품 이미지 경로 |

선택 컬럼은 3개입니다.

| 컬럼 | 설명 |
|---|---|
| `sale_price` | 할인가. 비어 있으면 할인하지 않는 상품으로 처리하며, 입력된 경우 `price`보다 클 수 없습니다. |
| `description` | 상품 설명 |
| `seller` | 판매자 정보 |

허용 카테고리는 다음 5개입니다.

```text
TOP
BOTTOM
OUTER
SHOES
BAG
```

CSV의 공식 category 입력값은 위 대문자 값(canonical)뿐입니다. `top`, `상의`, `shoes`, `신발`, `bag`, `가방` 같은 표기는 상품명·카테고리 비교, 상품 그룹 카테고리 비교, 카테고리별 가격 이상치 비교 과정에서 같은 의미로 인식하지만 정식 입력값은 아니므로, 그대로 입력하면 기존과 같이 `카테고리 오류`가 발생합니다. 입력 데이터의 표기를 하나로 유지하기 위한 정책입니다.

카테고리 검수는 다음 두 역할을 분리해서 처리합니다. 별칭과 한국어 표기를 의미 비교에 사용한다고 해서 공식 입력값으로 허용하는 것은 아닙니다.

```text
1. Validation
   공식 입력값인가?
   -> VALID_CATEGORIES 직접 비교 (canonical 대문자 5개만 허용)

2. Semantic normalization
   비교할 때 같은 의미인가?
   -> 카테고리 별칭 정규화 (TOP / top / 상의 를 같은 의미로 비교)
```

`카테고리 오류`와 `완전 중복 상품`은 1번 기준만 사용하므로 `shoes`, `신발`, `bag`, `가방`은 여전히 공식 입력값이 아닙니다. `상품명·카테고리 불일치`, `상품 그룹 카테고리 불일치`, `가격 이상치`는 2번 기준을 사용합니다.

### 카테고리별 필수 패션 속성 정책

필수 값 검사는 카테고리에 따라 `size` 필요 여부를 다르게 판단합니다. 정책은 `config/settings.py`의 `FASHION_CATEGORY_ATTRIBUTE_RULES` 한 곳에만 정의합니다.

| 카테고리 | `size` |
|---|---|
| `TOP` | 필수 |
| `BOTTOM` | 필수 |
| `OUTER` | 필수 |
| `SHOES` | 필수 |
| `BAG` | 선택 |

`BAG`은 의류 사이즈 체계가 없는 단일 사이즈 상품이 많아 `size`를 선택 값으로 처리하며, 비워 두어도 `필수 값 누락` 오류가 발생하지 않습니다. `FREE`를 입력해도 됩니다. 나머지 카테고리는 기존과 같이 `size`를 비우면 `필수 값 누락` 오류가 발생합니다.

이 정책은 `size`에만 적용합니다. `BAG`에서도 `product_name`, `color`, `image_path` 같은 나머지 필수 값 정책은 그대로 유지됩니다.

이 정책은 CSV 업로드 검수뿐 아니라 공급사 ETL 경로에도 같은 기준으로 적용됩니다. `etl/transformer.py`는 `required_source_columns`의 빈 값을, `etl/db_loader.py`는 표준 CSV의 빈 필수 값을 판단할 때 모두 `is_field_required_for_category()`를 호출합니다. 따라서 `BAG` + 빈 `size`는 검수에서 정상이고 ETL 변환·staging 적재도 통과합니다. ETL이 같은 정책을 다시 구현하지 않으며 기준은 `FASHION_CATEGORY_ATTRIBUTE_RULES` 한 곳뿐입니다. 자세한 내용은 `docs/etl_mvp.md`에 있습니다.

카테고리 값이 비어 있거나 허용 목록에 없으면 어떤 패션 카테고리인지 추정하지 않고 기존 `REQUIRED_FIELDS` 정책을 그대로 적용하므로 `size`는 계속 필수입니다. canonical 대문자 표기와 정확히 일치할 때만 정책을 적용하므로, `bag`처럼 별칭으로 입력하면 기존과 같이 `카테고리 오류`가 발생하고 `size`도 필수로 남습니다.

CSV 템플릿 다운로드 파일명은 `catalogguard_product_template.csv`입니다.

### 패션 색상·사이즈 표준화 기준

색상 검수는 다음 권장 표준값을 지원합니다.

```text
BLACK, WHITE, GRAY, NAVY, BEIGE, BROWN, RED, BLUE,
GREEN, YELLOW, PINK, PURPLE, ORANGE, KHAKI, IVORY, CREAM
```

사이즈 검수는 다음 권장 표준값을 지원합니다.

```text
XXS, XS, S, M, L, XL, XXL, XXXL, FREE
```

알려진 별칭은 다음과 같이 안내합니다.

```text
블랙, black, Black -> BLACK
grey, 회색 -> GRAY
medium, m -> M
2XL, xx-large -> XXL
프리사이즈, one size -> FREE
```

판정 방식은 다음과 같습니다.

- 입력값의 앞뒤 공백을 제거하고 영문 대소문자를 무시해 별칭 사전을 조회합니다.
- 별칭 사전의 키와 정확히 일치하는 값만 판정하며 부분 문자열이나 유사도 검사는 사용하지 않습니다.
- 찾은 표준값과 현재 입력값이 완전히 다르면 `주의`(`warning`)로 표시하며 위험 수준은 `낮음`입니다.
- 원본 CSV, 원본 DataFrame과 `Product`의 색상·사이즈를 자동으로 수정하지 않습니다.
- 결과표의 오류 이유에 현재 값과 권장 표준값을 함께 표시합니다.

색상·사이즈 비표준 표기 검수에서는 오탐을 줄이기 위해 `MELANGE GRAY`, `OATMEAL`, `DUSTY PINK` 같은 사용자 정의·복합 색상과 `95`, `100`, `28`, `30` 같은 숫자 사이즈를 표준화 대상으로 판단하지 않습니다. 별칭 사전에 없는 값 자체만으로는 비표준 오류나 주의를 만들지 않습니다. 이는 정상값을 잘못 경고하는 일을 줄이기 위한 보수적인 MVP 방식이며, 아래 중복 옵션 검수에서는 정리된 비교 키로 사용할 수 있습니다.

#### 별칭 사전에 없는 사이즈를 판단하는 기준

`사이즈 표기 비표준`은 **표준값을 이미 알고 있는 값의 표기 차이를 교정하는 규칙**입니다. `free_size`는 별칭 사전에서 `FREE`를 찾을 수 있으므로 "표준값 `FREE`으로 통일하세요"라고 안내할 수 있습니다. 반면 `FREEE`, `OS`, `CUSTOM`, `95호`처럼 사전에 없는 값은 어떤 표준값으로 안내해야 할지 알 수 없으므로, 그 값이라는 사실만으로는 오류나 주의를 만들지 않습니다.

`find_standard_size()`가 `None`을 돌려준다는 것은 **그 값이 정상이라고 확정했다는 뜻이 아니라, canonical 표준값을 판단할 근거가 없다는 뜻**입니다. 이 상태를 문서에서는 미판정이라고 부릅니다. 정상이라고 확정한 것도, 오류라고 판단한 것도 아닌 상태입니다.

숫자 사이즈는 특히 주의해야 합니다. `95`, `270`은 `find_standard_size()`의 별칭 대상은 아니지만 아래 사이즈 체계 일관성 검수에서 `NUMERIC` 체계로 정상 사용할 수 있는 값입니다. 따라서 `find_standard_size()`가 `None`이라는 이유로 잘못된 사이즈라고 해석하지 않습니다.

문자열 유사도(fuzzy matching)로 오타를 추정하지 않는 이유도 여기에 있습니다. 사이즈 값은 `XS`·`XXS`·`XXXS`처럼 **실제로 서로 다른 값끼리도 한 글자 차이**여서, 유사도만으로는 오타와 사전에 없는 실제 사이즈를 구분할 수 없습니다. 예를 들어 `OS`는 `S`와 한 글자 차이지만 두 값의 의미는 서로 다릅니다. 잘못된 교정을 권하지 않기 위해 현재 MVP에서는 유사도 기반 추천을 사용하지 않습니다.

#### 사이즈 vocabulary를 확장하는 기준

현재 표준 사이즈 vocabulary는 `XXS`, `XS`, `S`, `M`, `L`, `XL`, `XXL`, `XXXL`, `FREE`이며, 문자형(ALPHA) 범위는 `XXS`부터 `XXXL`까지입니다. `FREE`는 별도 semantic canonical이라 ALPHA·NUMERIC 체계로 분류하지 않습니다. 사전에 근거가 확인된 표기만 지원하는 Policy C를 적용해, `2XL`→`XXL`, `3XL`→`XXXL`, `ONE SIZE`·`ONE-SIZE`·`ONE_SIZE`·`ONESIZE`→`FREE`, `F`→`FREE`는 기존 지원을 유지합니다.

반면 `XXXS`, `XXXXL`, `4XL`, `5XL`, `2XS`, `3XS`, `OS`, `ONE`, `FS`는 현재 저장소 근거만으로 기존 canonical과 같은 의미라고 확정하지 않습니다. 예를 들어 `4XL`을 `XXXL`로 바꾸면 실제로 더 큰 별도 사이즈일 수 있는 값을 잃을 수 있습니다. 다른 사이즈를 잘못 합치는 것보다 unknown(미판정)으로 남겨 두는 편이 안전하므로, 이 값들은 실제 공급사 데이터 또는 승인된 size taxonomy 근거가 생길 때까지 새 alias·canonical로 등록하지 않습니다. 이는 unknown 자체를 오류로 만들지 않는 위 Policy E와 같은 보수적 원칙입니다.

#### 미판정 사이즈 토큰 빈도 보고서

운영자는 ETL 적재 이력 화면의 `미판정 사이즈 토큰` 표에서 현재 운영 카탈로그(`catalog_products`)에 남아 있는 미판정 원본 토큰과 건수를 확인할 수 있습니다. API는 `GET /api/v1/catalog/unknown-size-tokens`이며 viewer 이상 권한에서 호출할 수 있고, 기본 상위 20개(최대 100개)를 `{"items": [{"token": "4XL", "count": 8}]}` 형식으로 반환합니다.

보고서는 raw `size` 값별 DB `GROUP BY` 결과를 사용합니다. 앞뒤·연속 공백과 대소문자만 정리해 같은 미판정 토큰을 합산하되, 사전 밖 값의 하이픈·슬래시·공백 차이(`4XL`, `4-XL`, `4/XL`, `4 XL`)는 근거 없이 합치지 않습니다. 이미 지원하는 별칭, `find_size_system()`이 NUMERIC으로 판정하는 숫자 사이즈, 빈 값은 제외합니다. 이 보고서는 오류 판정이나 자동 alias 추가가 아니라 Policy C 검토를 위한 관측 도구이며, 운영 카탈로그의 현재 스냅샷만 보므로 미승격 staging·inspection 전용 데이터와 과거 추이는 포함하지 않습니다.

### 상품 그룹 내 중복 색상·사이즈 옵션 기준

다음 조건을 모두 만족하면 `상품 옵션 조합 중복` 오류로 표시합니다.

- `product_group_id`가 같습니다.
- 색상 비교 키와 사이즈 비교 키가 모두 같습니다.
- 중복 묶음에 서로 다른 `product_id`가 두 개 이상 있습니다.
- 색상이 비어 있지 않습니다.
- 사이즈가 비어 있지 않거나, 그 카테고리에서 `size`가 선택 값입니다.

알려진 별칭은 표준값으로 비교합니다. 예를 들어 `블랙`, `black`, `BLACK`은 모두 `BLACK`이고 `medium`, `M`은 모두 `M`입니다. 별칭 사전에 없는 사용자 정의 값도 앞뒤 공백과 영문 대소문자를 정리한 비교 키를 사용하므로 `MELANGE GRAY`와 `melange gray`, `95`와 ` 95 `를 같은 값으로 비교할 수 있습니다. 사용자 정의 값이라는 이유만으로 색상·사이즈 비표준 경고를 추가하지는 않습니다.

의미 비교에서는 값 안쪽의 연속 공백도 의미 차이로 보지 않습니다. `free size`, `free  size`, `free\tsize`는 모두 별칭 `free size`와 같은 값으로 읽어 표준값 `FREE`로 비교하며, `extra large`·`extra small`·`one size`처럼 공백이 들어간 다른 별칭도 같습니다. 공급사 데이터에 공백이 두 번 들어갔다는 이유만으로 옵션 중복 검사와 `사이즈 표기 비표준` 주의에서 빠지지 않게 하기 위한 것입니다. 별칭 사전에 없는 사용자 정의 값도 같은 기준으로 공백만 정리하므로 `MELANGE GRAY`와 `melange  gray`는 같은 색상으로 비교합니다. 값이 공백뿐이면 기존과 같이 빈 값으로 보므로 `""`와 `FREE`는 계속 서로 다른 값입니다. 이 정리는 비교 키에만 적용하고 원본 `Product.size`·`Product.color` 값은 바꾸지 않습니다.

#### 별칭 조회의 구분자 정책

공급사마다 같은 옵션을 `free size`, `free-size`, `free_size`, `freesize`처럼 다른 구분자로 입력합니다. 그래서 **별칭 사전을 조회할 때만** 공백과 하이픈(`-`), 언더스코어(`_`)를 무시한 조회 키를 사용합니다. 위 네 표기는 모두 조회 키 `freesize`가 되어 이미 등록된 별칭 `free size`·`freesize`와 연결되므로 표준값 `FREE`로 비교합니다. `extra large`·`extra-large`·`extra_large`도 같은 방식으로 `XL`이 되고, `x-large`·`xx-large`처럼 하이픈이 포함된 기존 별칭도 그대로 유지됩니다.

`/`와 `.`는 무시하지 않습니다. `BLACK/WHITE`(복합 색상), `S/M`(선택), `10.5`(숫자 사이즈)처럼 값 자체의 의미일 수 있기 때문입니다. 따라서 `free/size`와 `FREE.SIZE`는 자동으로 `FREE`가 되지 않습니다.

이 정책은 **사전 안에서는 관대하게, 사전 밖에서는 보수적으로** 비교한다는 원칙을 따릅니다. 구분자를 무시한 결과가 사전에 등록된 별칭과 정확히 일치할 때만 표준값으로 인정하므로, `S-M`·`36-38`·`95-100`처럼 구분자에 의미가 있는 값이나 `OS`·`ONE`·`one size fits all`처럼 사전에 없는 표현은 그대로 사용자 정의 값으로 남습니다. 구분자만 남는 값(`-`, `_`)도 조회 키가 비어 어떤 별칭과도 연결되지 않습니다.

사전 밖 사용자 정의 값의 비교 키에는 이 구분자 정책을 적용하지 않습니다. 그래서 `MELANGE-GRAY`와 `MELANGE GRAY`는 계속 서로 다른 색상으로 비교합니다. 사전은 무엇을 같은 의미로 볼지 범위를 정해 주지만, 임의의 문자열에는 그런 근거가 없기 때문입니다. 별칭 사전(`SIZE_ALIASES`·`COLOR_ALIASES`)에 새 항목을 추가하는 변경도 아니며, 구분자를 무시했을 때 서로 다른 표준값이 같은 조회 키로 합쳐지면 조회 표를 만들 때 오류로 막습니다.

다른 상품 그룹의 같은 옵션은 중복이 아닙니다. 색상이 비어 있거나 `size`가 필수인 카테고리에서 사이즈가 비어 있으면 중복 옵션 규칙에서 제외하고 기존 필수 값 누락 규칙이 처리합니다. 같은 `product_id`만 반복된 경우도 새 규칙에서 제외하고 기존 상품 ID 중복 규칙이 처리합니다. 중복에 포함된 서로 다른 상품 ID의 모든 행에 결과를 연결하며 입력 순서를 유지합니다.

`완전 중복 상품`은 `상품 옵션 조합 중복`보다 우선합니다. 기존 완전 중복 기준인 정규화된 상품명·카테고리·색상·사이즈·가격이 같은 상품 관계는 완전 중복으로만 표시하고, 같은 관계를 옵션 중복으로 다시 표시하지 않습니다. 완전 중복 판정에는 재고와 이미지 경로를 사용하지 않습니다. 색상·사이즈 비교 키만 같고 가격 등 다른 완전 중복 기준이 다르면 옵션 중복은 그대로 표시합니다. 세 상품 이상이 같은 옵션을 공유할 때도 그룹 전체를 제거하지 않고 상품 관계별로 판정하므로, 일부 상품만 완전 중복이어도 나머지 상품과의 실제 옵션 중복은 유지됩니다.

완전 중복 판정은 category가 허용 목록 안에 있을 때만 수행합니다. 따라서 `SHOES`와 `BAG`를 공식 허용 카테고리로 확장하면서, 이전에는 검사에서 빠져 있던 신발·가방 상품도 완전 중복 검사 대상이 되었습니다. 새 중복 탐지 방식을 추가한 것이 아니라 기존 완전 중복 규칙이 적용되는 범위가 넓어진 것입니다.

빈 `size`는 그 카테고리에서 `size`가 선택 값일 때만 정상 비교값으로 사용합니다. 판단 기준은 검수·ETL과 같은 `is_field_required_for_category()`이며 완전 중복 규칙이 정책을 다시 구현하지 않습니다. 따라서 `BAG` 상품은 `size`를 비워 두어도 나머지 완전 중복 기준(상품명·카테고리·색상·가격)이 같으면 완전 중복으로 표시합니다. `size`가 필수인 `TOP`·`BOTTOM`·`OUTER`·`SHOES`에서 `size`가 비면 기존과 같이 완전 중복 비교 대상에서 제외하고 `필수 값 누락` 오류가 처리합니다. 빈 `size`와 `FREE`는 서로 다른 값이므로 둘을 같은 상품으로 보지 않으며, 빈 `size`를 `FREE`로 채우거나 원본 값을 바꾸지 않습니다. `BAG`에서도 색상, 상품명, 가격 등 나머지 비교 조건과 기존 제외 조건은 그대로 유지합니다.

같은 기준을 `상품 옵션 조합 중복`에도 적용합니다. `size`가 선택 값인 canonical 카테고리에서는 빈 `size`도 하나의 정상 옵션 상태이므로, 같은 상품 그룹 안에서 같은 색상과 빈 `size` 조합이 서로 다른 `product_id`에 반복되면 `상품 옵션 조합 중복` 오류로 표시합니다. 예를 들어 `BAG` 상품 두 개가 같은 그룹에서 색상 `BLACK`과 빈 `size`를 함께 사용하면, 상품명이나 가격이 달라 완전 중복이 아니더라도 옵션 조합 중복입니다. `size`가 필수인 `TOP`·`BOTTOM`·`OUTER`·`SHOES`와 허용 목록에 없는 카테고리에서 `size`가 비면 기존과 같이 옵션 중복 비교에서 제외하고 `필수 값 누락` 오류가 처리합니다. 옵션 중복에서도 빈 `size`와 `FREE`는 서로 다른 값이며, 판단 기준은 완전 중복과 같은 `is_field_required_for_category()` 하나뿐입니다. 완전 중복이 옵션 중복보다 우선한다는 기존 순서도 그대로여서, 완전 중복 관계인 빈 `size` 상품에는 옵션 중복을 다시 표시하지 않습니다.

빈 `size`의 내부 비교값은 빈 문자열 그대로 유지하고, 화면과 결과 CSV에는 `사이즈 없음`으로 표시합니다. 표시 문구만 바꾸는 것이며 저장값이나 비교값을 `없음` 같은 문자열로 바꾸지 않습니다.

### 완전 중복과 옵션 중복의 사이즈·색상 비교 기준 차이

앞의 카테고리 검수와 같은 `Validation` / `Semantic normalization` 2단 구분을 사이즈·색상에도 적용합니다. 두 규칙이 서로 다른 질문에 답하므로 비교 기준도 다릅니다.

```text
완전 중복 상품 (duplicate_product_content)
   질문: 같은 상품 행을 두 번 등록했는가?
   비교: 공백과 영문 대소문자만 정리한 값 (별칭 미적용)

상품 옵션 조합 중복 (duplicate_variant_combination)
   질문: 같은 그룹에서 사용자가 보기에 같은 옵션이 두 번 있는가?
   비교: SIZE_ALIASES · COLOR_ALIASES 표준값 (별칭 적용)
```

따라서 `FREE`와 `free size`는 완전 중복으로는 서로 다른 상품이고, 옵션 중복으로는 같은 옵션입니다. `free-size`, `free_size`처럼 구분자만 다른 표기도 마찬가지로 완전 중복에서는 다른 상품입니다. 완전 중복은 별칭 조회를 사용하지 않으므로 구분자 정책의 영향을 받지 않습니다. 표기가 다르다는 사실 자체는 `사이즈 표기 비표준` 주의가 원본 값과 권장 표준값을 함께 알려 주므로, 표기를 통일한 뒤 다시 검수하면 완전 중복 여부도 새 기준으로 판정됩니다. 완전 중복에 별칭을 적용하지 않는 이유는 이 규칙의 위험 수준이 `높음`이고 권장 조치가 상품 삭제·통합이어서, 표기가 사실상 같은 경우로 판정 범위를 좁게 유지하기 위한 것입니다. 대소문자와 앞뒤 공백만 다른 `FREE`와 ` free `는 완전 중복에서도 같은 값입니다.

검수 과정은 비교 키만 별도로 만들고 원본 CSV, 원본 DataFrame, 미리보기와 `Product.color`·`Product.size`를 자동 수정하지 않습니다.

### 카테고리 허용 여부와 상품명 의미 검수의 구분

`카테고리 오류`는 category가 허용 목록 안에 있는지만 보고, `상품명·카테고리 불일치`는 상품명에서 추정한 의미와 입력 category가 맞는지를 봅니다. 두 검수는 서로 독립적입니다.

```text
남성 러닝 운동화 + SHOES
-> 허용 카테고리이고 상품명 의미도 일치
-> 카테고리 오류 없음, 상품명·카테고리 불일치 없음

오버핏 반팔 티셔츠 + SHOES
-> SHOES 자체는 허용 카테고리
-> 카테고리 오류 없음
-> 상품명 의미가 맞지 않아 상품명·카테고리 불일치 주의

레더 토트백 + BAG + size=FREE
-> 정상 입력

가죽 벨트 + ACCESSORY
-> 허용 목록에 없어 카테고리 오류
```

`SHOES`와 `BAG`를 공식 허용 카테고리로 추가하기 전에는, 상품명 의미가 정확히 맞는 신발·가방 상품도 허용 목록에 없다는 이유로 `카테고리 오류`가 발생했습니다. 이번 확장은 이 불일치를 없애기 위한 것이며, 상품명 의미 검수 로직 자체는 바뀌지 않았습니다.

### 상품 그룹 내 카테고리 일관성 기준

같은 `product_group_id` 안에서 비어 있지 않은 category 정규화 결과가 두 개 이상이면 `상품 그룹 카테고리 불일치` 오류로 표시합니다. 비교할 때 앞뒤 공백과 영문 대소문자를 무시하고 기존 카테고리 별칭을 재사용하므로 `TOP`, `top`, `상의`는 같은 값으로 판단합니다. 사용자에게는 정규화 키가 아니라 각 비교값이 최초로 등장했을 때의 원본 대표 표기를 최초 입력 순서대로 보여 줍니다.

빈 category는 비교에서 제외하고 기존 `필수 값 누락` 오류가 처리합니다. 허용 목록에 없는 category도 그룹 안에서 모두 같은 비교값이면 새 일관성 오류를 만들지 않지만, 서로 다른 값과 섞이면 기존 `카테고리 오류`와 새 그룹 일관성 오류가 함께 표시될 수 있습니다. 기존 상품명·카테고리 불일치 규칙도 의미가 다르므로 필요한 경우 함께 표시됩니다.

어느 category가 정답인지 다수결이나 상품명 추론으로 결정하지 않습니다. 불일치 그룹에서 비어 있지 않은 비교에 참여한 모든 상품에 결과를 연결하고 전체 입력 순서를 유지합니다. 따라서 그룹 한 곳의 카테고리 문제 하나가 참여 상품 수만큼 결과 행으로 생성될 수 있습니다. 이 방식은 특정 상품만 자동으로 잘못됐다고 단정하지 않고 그룹 전체를 함께 점검하게 하기 위한 정책입니다.

비교용 정규화는 원본 category를 자동 수정하지 않습니다. 입력 DataFrame과 `report.source_dataframe`은 업로드 원본을 보존하고, 탐지기에 직접 전달한 `Product`도 변경하지 않습니다. 단, `report.products`는 기존 loader 계약에 따라 문자열 앞뒤 공백이 제거된 상태입니다. 구조화 JSON에는 그룹, 최초 대표 category와 상품 ID를 저장하므로 작은따옴표, 큰따옴표, 쉼표, 한글과 공백이 있어도 문자열 정규식 파싱 없이 안전하게 표시할 수 있습니다.

### 카테고리별 가격 이상치 비교 기준

카테고리별 가격 중앙값을 기준으로 지나치게 낮거나 높은 가격을 `가격 이상치` 주의로 표시합니다. 이때 상품을 같은 카테고리로 묶는 비교 기준은 `core.category_mismatch_detector.normalize_category()`를 그대로 재사용합니다. 따라서 `TOP`/`top`/`상의`, `SHOES`/`shoes`/`신발`, `BAG`/`bag`/`가방`은 의미상 같은 카테고리 그룹으로 함께 비교합니다.

이전에는 이 규칙만 앞뒤 공백과 영문 대소문자만 정리해서 비교했기 때문에 `TOP`과 `top`은 같은 그룹이지만 `상의`는 별도 그룹이 되었습니다. 그 결과 한 카테고리의 표기가 섞이면 각 그룹의 상품 수가 최소 비교 기준 아래로 내려가, 표기가 정상인 canonical 상품의 가격 이상치까지 검출되지 않을 수 있었습니다. 비교 기준을 통일해 이 누락을 없앴습니다.

```text
SHOES 10000 / SHOES 10000 / SHOES 10000 / SHOES 100000
+ 신발 10000 / 신발 10000 / 신발 10000

이전: shoes 4개, 신발 3개로 분리 -> 둘 다 5개 미만 -> 가격 이상치 없음
이후: 같은 의미 카테고리 7개 -> 중앙값 10000 -> SHOES 100000 가격 이상치 검출
```

이 통일은 의미 비교에만 적용합니다. `카테고리 오류`는 그대로 canonical 값만 허용하므로 위 예시의 `신발` 행에는 `카테고리 오류`가 함께 표시됩니다. 사용자에게 보여 주는 메시지에는 정규화 키가 아니라 입력한 원본 category 표기를 그대로 사용하며, 최소 비교 상품 수와 이상치 배수 기준은 바뀌지 않았습니다.

### 상품 그룹 내 사이즈 체계 일관성 기준

같은 `product_group_id` 안에서 문자형 사이즈와 숫자형 사이즈가 함께 사용되면 `상품 그룹 사이즈 체계 불일치` 주의로 표시합니다.

```text
G001: S / M / L      -> 정상
G002: 95 / 100 / 105 -> 정상
G003: M / L / 100    -> 사이즈 체계 혼재 주의
```

사이즈 체계는 다음 두 가지만 분류합니다.

| 체계 | 판정 기준 | 예 |
|---|---|---|
| ALPHA | 기존 `find_standard_size()`가 `XXS`, `XS`, `S`, `M`, `L`, `XL`, `XXL`, `XXXL` 중 하나로 정규화할 수 있는 값 | `M`, `m`, `medium`, `2XL`, `xx-large` |
| NUMERIC | 공백을 제거한 뒤 ASCII 숫자로만 이루어진 값 | `95`, `100`, `105`, `270`, `30` |

다음 값은 이번 체계 혼재 판정에서 제외합니다.

- `FREE`, `free`, `F`, `one size`, `프리`, `프리사이즈` 같은 FREE 계열
- `OS`, `1호`, `여성용`, `custom size`, `M-L`, `95-100` 같은 사용자 정의·범위 표기
- 빈 값. 빈 사이즈는 카테고리별 필수 패션 속성 정책에 따라 기존 `필수 값 누락` 오류가 처리하며, `size`가 선택 값인 `BAG`은 오류 없이 이 비교에서만 제외합니다.

판정 방식은 다음과 같습니다.

- ALPHA와 NUMERIC이 동시에 있는 그룹에서만 주의 항목을 만듭니다. 한 체계만 쓰는 그룹은 정상입니다.
- 실제로 ALPHA 또는 NUMERIC으로 분류된 상품에만 결과를 연결합니다. 같은 그룹의 FREE·사용자 정의·빈 사이즈 상품에는 이 주의를 붙이지 않습니다.
- `product_group_id`가 비어 있는 상품은 하나의 그룹으로 묶지 않습니다. 이 경우도 기존 `필수 값 누락` 오류가 처리합니다.
- 다른 상품 그룹의 사이즈는 서로 비교하지 않습니다.
- 확정 오류가 아니라 `주의`(`warning`)입니다. 브랜드나 운영 정책상 서로 다른 사이즈 체계를 함께 쓸 가능성을 배제할 수 없기 때문입니다.
- 원본 CSV, 원본 DataFrame과 `Product.size`를 자동으로 수정하지 않습니다.

이 규칙은 category와 무관하게 동작합니다. `SHOES` 그룹의 `250 / 260 / 270`은 숫자형 한 체계만 쓰므로 정상이고, 같은 `SHOES` 그룹에 `M`과 `270`이 함께 있으면 문자형·숫자형 혼재로 주의가 표시됩니다.

이 규칙은 숫자 사이즈에서 카테고리를 추정하지 않습니다. `95`를 상의, `270`을 신발, `30`을 하의로 단정하지 않으며 KR·US·UK·EU 사이즈 변환, 성별·브랜드별 사이즈 차트, 카테고리별 허용 사이즈 범위도 사용하지 않습니다. 명확히 판정 가능한 ALPHA와 NUMERIC의 혼재만 탐지하고 FREE와 사용자 정의 값은 비교에서 제외해, 정상 데이터를 잘못 경고할 가능성을 줄였습니다.

기존 규칙과는 다음과 같이 역할이 나뉘며 서로를 대체하지 않습니다.

| 규칙 | 보는 대상 |
|---|---|
| `사이즈 표기 비표준` | `medium`을 `M`으로 통일하는 사이즈 표기 표준화 |
| `상품 그룹 사이즈 체계 불일치` | 같은 그룹에서 `M`과 `100`처럼 서로 다른 사이즈 체계가 섞였는지 |
| `상품 옵션 조합 중복` | 같은 그룹에서 색상과 사이즈 조합이 중복되는지 |
| `상품 그룹 카테고리 불일치` | 같은 그룹에서 category가 서로 다른지 |

## 11. CSV 업로드 검증 기준

업로드된 파일은 검수 규칙 실행 전에 먼저 검증됩니다.

- 파일명이 없거나 `.csv` 확장자가 아니면 차단합니다.
- 빈 파일은 차단합니다.
- 최대 파일 크기는 `5MB`입니다.
- NUL 바이트가 포함된 파일은 일반 CSV 텍스트 파일이 아닌 것으로 보고 차단합니다.
- 지원 인코딩은 `utf-8-sig`, `utf-8`, `cp949`입니다.
- 내용이 공백뿐인 파일은 차단합니다.
- 헤더가 없거나 CSV 따옴표 형식이 깨진 파일은 차단합니다.
- 빈 컬럼명이 있으면 차단합니다.
- 대소문자만 다른 중복 컬럼명도 중복으로 보고 차단합니다.
- 필수 컬럼이 빠지면 차단합니다.
- 데이터 행의 열 개수가 헤더와 다르면 차단합니다.
- 데이터 행이 없는 헤더 전용 CSV는 차단합니다.
- 최대 데이터 행 수는 `10,000`행입니다.

## 12. 설치 방법

Windows PowerShell 또는 VS Code 터미널에서 저장소 루트로 이동한 뒤 가상환경을 만듭니다.

```powershell
cd C:\study\catalogguard-lite
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip
```

Streamlit CSV 검수 화면만 실행하려면 기본 패키지를 설치합니다.

```powershell
python -m pip install -r requirements.txt
```

FastAPI, PostgreSQL 저장, 검수 이력 기능까지 로컬에서 함께 실행하려면 API 패키지도 설치합니다.

```powershell
python -m pip install -r requirements-api.txt
```

테스트 실행에 `pytest`가 없다면 별도로 설치합니다.

```powershell
python -m pip install pytest==9.1.1
```

## 13. PostgreSQL 개발 DB와 테스트 DB 준비 방법

PostgreSQL이 설치되어 있고 `psql` 명령을 PowerShell에서 사용할 수 있어야 합니다. 아래 예시는 PostgreSQL 18 기준으로 사용할 수 있는 개발 DB와 테스트 DB 이름입니다.

| 용도 | 데이터베이스 | 사용자 |
|---|---|---|
| 개발 | `catalogguard_lite` | `catalogguard_user` |
| 테스트 | `catalogguard_lite_test` | `catalogguard_test_user` |

관리자 권한으로 PostgreSQL에 접속한 뒤 사용자와 데이터베이스를 만듭니다.

```powershell
psql -U postgres
```

`psql` 안에서 아래 SQL을 실행합니다. `CHANGE_ME`는 실제 로컬 비밀번호로 바꾸세요.

```sql
CREATE USER catalogguard_user WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE catalogguard_lite OWNER catalogguard_user;
CREATE USER catalogguard_test_user WITH PASSWORD 'CHANGE_ME';
CREATE DATABASE catalogguard_lite_test OWNER catalogguard_test_user;
```

생성이 끝나면 `\q`로 `psql`을 종료합니다.

```sql
\q
```

이미 사용자나 데이터베이스가 있다면 환경에 맞게 비밀번호 변경, 권한 부여, 기존 DB 재사용 중 하나를 선택하면 됩니다.

## 14. 환경변수 설정

`.env.example`에는 PostgreSQL 연결 문자열 예시가 있습니다.

```text
DATABASE_URL=postgresql+psycopg://catalogguard_user:CHANGE_ME@localhost:5432/catalogguard_lite
TEST_DATABASE_URL=postgresql+psycopg://catalogguard_test_user:CHANGE_ME@localhost:5432/catalogguard_lite_test
```

현재 코드에는 `.env` 파일을 자동으로 읽는 `python-dotenv` 설정이 없습니다. 로컬 실행 시에는 PowerShell 환경변수로 직접 설정하세요.

```powershell
$env:DATABASE_URL="postgresql+psycopg://catalogguard_user:CHANGE_ME@localhost:5432/catalogguard_lite"
$env:TEST_DATABASE_URL="postgresql+psycopg://catalogguard_test_user:CHANGE_ME@localhost:5432/catalogguard_lite_test"
```

Streamlit에서 검수 이력 저장·목록·상세 조회 기능을 사용하려면 FastAPI 주소도 설정합니다.

```powershell
$env:CATALOGGUARD_API_BASE_URL="http://127.0.0.1:8001"
$env:CATALOGGUARD_API_TIMEOUT_SECONDS="5.0"
```

`CATALOGGUARD_API_TIMEOUT_SECONDS`는 생략하거나 잘못된 값이 들어가면 기본값 `5.0`초를 사용합니다. `CATALOGGUARD_API_BASE_URL`이 없으면 Streamlit의 CSV 검수 자체는 가능하지만, 검수 이력 저장과 조회는 사용할 수 없습니다.

로그인·JWT 검증에는 `CATALOGGUARD_JWT_SECRET`이 필요합니다. 이 값이 없으면 로그인, 토큰 검증이 필요한 요청은 실패하지만 `/health`, `/ready`, CLI ETL(`etl.cli`, `etl.load_cli`), Alembic migration은 이 값을 요구하지 않습니다.

```powershell
$env:CATALOGGUARD_JWT_SECRET="로컬에서만 사용할 임의의 긴 문자열"
```

| 환경변수 | 기본값 | 설명 |
|---|---|---|
| `CATALOGGUARD_JWT_SECRET` | 없음(필수) | JWT Access Token 서명 secret. 서버 설정으로 고정되며 요청에서 선택할 수 없음(알고리즘은 `HS256` 고정) |
| `CATALOGGUARD_JWT_ACCESS_TOKEN_TTL_SECONDS` | `3600` | Access Token 만료 시간(초). 만료되면 Refresh Token 없이 다시 로그인해야 함 |
| `CATALOGGUARD_METRICS_ENABLED` | `false` | `GET /metrics` 활성화 여부. `true`/`1`/`yes`(대소문자 무관)일 때만 활성화되며, 그 외 값이나 미설정 시 `/metrics`는 `404`이고 metric instrumentation도 no-op(내부 counter도 증가하지 않음) |
| `CATALOGGUARD_ETL_S3_BUCKET` | 없음 | `POST /api/v1/etl-loads/s3`가 읽을 S3 bucket. 요청으로 bucket을 지정할 수 없으며, 미설정 시 이 endpoint는 `503`(`s3_not_configured`) |
| `CATALOGGUARD_ETL_S3_PREFIX` | 없음 | 허용할 object key prefix(예: `incoming/catalogguard/`). 앞뒤 `/`는 정규화하며, 설정 시 이 prefix로 시작하지 않는 `object_key`는 S3 호출 전에 `400`(`s3_key_not_allowed`)으로 차단. 미설정이면 prefix 제한 없이 해당 bucket 전체가 대상이 되므로 설정을 권장 |
| `CATALOGGUARD_ETL_HTTP_FEED_URL` | 없음 | `POST /api/v1/etl-loads/http`가 읽을 신뢰 공급사 CSV feed URL(예: `https://supplier.example.invalid/catalog.csv`). 요청으로 URL을 지정할 수 없으며, 미설정 시 이 endpoint는 `503`(`http_feed_not_configured`). 외부 host는 `https`만 허용하고 평문 `http`는 loopback host에서만 허용 |
| `CATALOGGUARD_ETL_HTTP_FEED_FILENAME` | `supplier_feed.csv` | HTTP feed로 받은 CSV를 기존 ETL에 넘길 때 사용할 `source_filename`. 응답 헤더에서 추출하지 않고 서버 설정으로만 정하며, `.csv`가 아니면 `400`(`invalid_upload`) |

실제 `CATALOGGUARD_JWT_SECRET` 값은 저장소에 커밋하지 않으며, 이 문서에도 실제 값을 적지 않습니다.

## 15. Alembic 마이그레이션

마이그레이션은 `DATABASE_URL`이 설정된 PowerShell에서 저장소 루트 기준으로 실행합니다.

```powershell
cd C:\study\catalogguard-lite
.\.venv\Scripts\Activate.ps1
python -m alembic current
python -m alembic upgrade head
python -m alembic history
```

현재 Alembic head는 `20260813_0013`입니다.

`20260703_0001_create_inspection_tables.py`는 다음 테이블을 만듭니다.

- `inspection_runs`
- `inspection_results`

`20260705_0002_add_inspection_file_identity.py`는 동일 CSV 중복 저장을 DB 수준에서 막기 위해 `inspection_runs`에 파일 identity 정보를 추가합니다.

`20260725_0003_create_etl_staging_tables.py`는 ETL 결과를 배치 단위로 적재하기 위한 다음 테이블을 추가합니다.

- `etl_load_runs`: 원본 파일명, 프로필 이름·버전, 입력·출력 SHA-256과 적재 행 수를 저장
- `catalog_products_staging`: 정상 표준 CSV 상품 행을 저장하고 `etl_load_runs`와 외래 키로 연결

`20260727_0004_add_etl_quality_summary.py`와 `20260728_0005_add_etl_rejected_rows.py`는 ETL 품질 요약과 `etl_rejected_rows`를 추가합니다. reject 행에는 `{code, field, message}` 오류 JSONB 배열과 개인정보가 마스킹된 동적 원본 컬럼 JSONB만 저장합니다.

`etl_load_runs`에는 `(input_file_sha256, profile_name, profile_version)` unique index가 있습니다. staging 상품 테이블의 `etl_load_run_id`에는 조회용 index와 `ON DELETE CASCADE` 외래 키가 있고, `stock`, `price`, `sale_price`의 음수 방지 CHECK constraint가 있습니다.

`20260728_0006_create_catalog_promotion_tables.py`는 다음 persistence 테이블을 추가합니다.

- `catalog_products`: `(supplier_key, external_product_id)` 복합 unique identity와 마지막 ETL 출처 FK를 갖는 운영 상품 모델
- `catalog_promotion_runs`: 실행 상태·count·preview 메타데이터를 저장하며, 같은 ETL batch의 `succeeded` 실행을 partial unique index로 한 건만 허용
- `catalog_product_changes`: `insert`·`update`만 기록하는 append-only JSONB audit log

새 테이블의 출처·감사 FK는 모두 `ON DELETE RESTRICT`다. `catalog_product_changes.before_data`는 `JSONB(none_as_null=True)`를 사용해 insert 이력의 Python `None`을 SQL `NULL`로 저장한다. `catalog_promotion_preview_service.py`와 `catalog_promotion_service.py`가 이 테이블을 사용해 preview, 승인된 transaction upsert, promotion run과 append-only audit을 처리한다.

`20260803_0007_create_catalog_promotion_rollback_tables.py`는 promotion rollback을 위한 다음 테이블을 추가합니다.

- `catalog_promotion_rollbacks`: rollback 실행 단위 상태(`applying`/`succeeded`/`failed`/`blocked`)와 count·preview 메타데이터를 저장하며, 같은 `target_promotion_run_id`의 `succeeded` 실행을 partial unique index로 한 건만 허용
- `catalog_promotion_rollback_changes`: rollback이 상품별로 삭제(`delete`)했는지 이전 상태로 복원(`restore`)했는지 기록하는 append-only JSONB audit log이며, 원본 `catalog_product_changes` 행을 FK로 연결

`20260803_0008_allow_catalog_product_audit_detach.py`는 `catalog_product_changes.catalog_product_id`와 `catalog_promotion_rollback_changes.catalog_product_id`의 `ON DELETE RESTRICT` 외래 키를 제거합니다. INSERT promotion을 rollback하면 운영 상품이 실제로 삭제될 수 있는데, 이 외래 키가 남아 있으면 감사 이력이 상품을 계속 참조하고 있어 삭제 자체가 막힙니다. 외래 키를 제거해 상품이 삭제되어도 두 audit 테이블의 행은 그대로 남도록 했습니다.

`20260805_0009_create_users_table.py`는 Authentication + RBAC를 위한 `users` 테이블을 추가합니다.

- `id`, `username`(`VARCHAR(50)`, unique index), `password_hash`(`VARCHAR(255)`, bcrypt hash만 저장), `role`(`VARCHAR(20)`, `CHECK (role IN ('viewer', 'operator'))`), `is_active`(기본 `true`), `created_at`
- 기존 `inspection_runs`, `etl_load_runs`, `catalog_products`, `catalog_promotion_runs` 등 다른 테이블은 이 마이그레이션에서 변경하지 않았습니다. 누가 실행했는지를 기존 실행 이력에 기록하는 actor 컬럼·FK는 추가하지 않았으며, 이는 "누가 실행할 수 있는지"를 통제하는 이번 Authentication 범위와는 다른 별도 기능입니다.

`20260806_0010_add_actor_audit_columns.py`는 `etl_load_runs`, `catalog_promotion_runs`, `catalog_promotion_rollbacks` 3개 테이블에 다음 컬럼을 nullable로 추가합니다.

- `actor_user_id`(`BigInteger`, `users.id` FK, `ON DELETE SET NULL`)
- `actor_username`(`VARCHAR(50)`, `users.username`과 같은 길이)

기존 row는 이 migration 실행 전에 만들어졌으므로 실행한 사용자를 알 수 없어 두 컬럼 모두 `NULL`로 유지하며, 임의 사용자로 backfill하지 않습니다. 새로 생성되는 row는 `api/routes/etl_loads.py`가 `require_operator`로 인증된 JWT `current_user.id`·`current_user.username`에서 값을 가져와 채웁니다. `actor_username`은 `users.username`이 나중에 바뀌어도 실행 당시 이름을 보존하는 snapshot이고, `actor_user_id`는 `users` 테이블과의 현재 FK 연결을 위한 값입니다. `actor_user_id`가 가리키는 사용자가 삭제되면 `ON DELETE SET NULL`로 `actor_user_id`만 `NULL`이 되고 `actor_username` snapshot과 실행 이력 행 자체는 그대로 남습니다. downgrade는 FK 제약을 먼저 제거한 뒤 `actor_username`, `actor_user_id` 컬럼을 순서대로 제거합니다. 이 최초 Actor Audit migration은 Web ETL·Promotion·Rollback을 대상으로 했고, Inspection은 아래 `20260810_0012`에서 같은 규칙으로 확장했습니다.

`20260808_0011_add_promotion_audit_order_index.py`는 promotion audit 페이지네이션 쿼리가 사용하는 `(promotion_run_id, created_at DESC, id DESC)` 정렬 index를 추가합니다.

`20260810_0012_add_inspection_actor_audit.py`(`down_revision=20260808_0011`)는 `inspection_runs`에 다음 컬럼을 nullable로 추가합니다.

- `actor_user_id`(`BIGINT`, `users.id` FK, `ON DELETE SET NULL`)
- `actor_username`(`VARCHAR(50)`, 실행 당시 username snapshot)

기존 검수 이력은 두 actor 컬럼을 `NULL`로 유지하며 임의 backfill하지 않습니다. 새 Sync·Async 검수 row를 만들 때만 인증된 JWT `current_user`의 scalar `id`·`username`을 저장합니다. 사용자가 삭제되면 `actor_user_id`만 `NULL`이 되고 `actor_username`과 검수 이력은 남습니다. 동일한 `file_sha256`·`inspection_version`의 기존 row를 재사용하면 actor를 UPDATE하지 않아 최초 row 생성 사용자를 보존합니다.

격리된 로컬 PostgreSQL 18 테스트 클러스터에서 당시 `upgrade head`, `downgrade 20260808_0011`, 재-upgrade를 실행했습니다. downgrade 시 `inspection_runs`의 actor 컬럼 2개와 해당 FK만 제거되고 다른 테이블·컬럼은 유지됐으며, 재-upgrade 뒤 당시 head인 `20260810_0012`와 `ON DELETE SET NULL` FK가 복원되는 것을 SQLAlchemy inspector로 확인했습니다.

`20260813_0013_add_etl_initial_source_lineage.py`(`down_revision=20260810_0012`)는 `etl_load_runs`에 최초 입력 경로 lineage를 위한 다음 컬럼을 추가합니다.

- `initial_source_type`(`VARCHAR(20)`, `NOT NULL`): 기존 row backfill에만 `unknown` server default를 사용한 뒤 제거하고, `unknown`·`upload`·`s3`·`http_feed`·`cli`만 허용하는 `ck_etl_load_runs_initial_source_type` CHECK constraint를 추가
- `initial_source_ref`(`VARCHAR(255)`, nullable)

downgrade는 CHECK constraint를 먼저 제거한 뒤 `initial_source_ref`, `initial_source_type` 순으로 제거합니다.

upgrade 동작은 다음 순서입니다.

1. `file_sha256` nullable 컬럼 추가
2. `inspection_version`을 임시 nullable 상태로 추가
3. 기존 행의 `inspection_version IS NULL` 값을 문자열 `"1"`로 backfill
4. `inspection_version`을 `NOT NULL`로 변경
5. `file_sha256` 길이와 `inspection_version` 빈 문자열 방지 CHECK constraint 추가
6. `(file_sha256, inspection_version)` partial unique index 추가

중요한 점은 기존 이력의 `file_sha256`을 NULL로 유지한다는 것입니다. DB에는 과거 원본 CSV bytes가 저장되어 있지 않으므로 과거 파일 해시를 추측해서 채우지 않습니다. 또한 `inspection_version`에는 DB `server_default`를 두지 않고, 애플리케이션이 현재 검수 규칙 버전을 명시적으로 저장합니다.

테이블이 만들어졌는지 확인하려면 아래 명령을 실행합니다.

```powershell
psql "$env:DATABASE_URL" -c "\dt"
psql "$env:DATABASE_URL" -c "\d inspection_runs"
psql "$env:DATABASE_URL" -c "\d inspection_results"
psql "$env:DATABASE_URL" -c "\d etl_load_runs"
psql "$env:DATABASE_URL" -c "\d catalog_products_staging"
psql "$env:DATABASE_URL" -c "\d catalog_products"
psql "$env:DATABASE_URL" -c "\d catalog_promotion_runs"
psql "$env:DATABASE_URL" -c "\d catalog_product_changes"
psql "$env:DATABASE_URL" -c "\d catalog_promotion_rollbacks"
psql "$env:DATABASE_URL" -c "\d catalog_promotion_rollback_changes"
psql "$env:DATABASE_URL" -c "\d users"
```

테스트용 PostgreSQL 18 임시 클러스터에서 빈 DB의 `upgrade head`, `downgrade 20260728_0005`, 재-upgrade와 단일 head를 확인했다. `0006` downgrade는 새 운영 상품 persistence 테이블만 제거하며 기존 inspection·ETL staging 테이블은 유지한다.

같은 방식으로 로컬 disposable PostgreSQL 18에서 빈 DB의 `upgrade head`, `downgrade 20260803_0007`, `downgrade 20260728_0006`, 재-upgrade와 단일 head도 확인했다. `20260805_0009`도 같은 방식으로 `downgrade 20260803_0008` 뒤 재-upgrade와 단일 head(`20260805_0009`)를 disposable PostgreSQL 18에서 확인했다.

`tests/test_inspection_actor_migration.py`와 `tests/test_catalog_promotion_migration.py`는 `alembic.script.ScriptDirectory`로 현재 단일 head가 `20260813_0013`인지 확인합니다. CI의 `Apply database migrations` step은 고정 revision이 아니라 `upgrade head`를 실행하므로 현재 migration chain 전체를 적용합니다.

## 16. FastAPI 실행 방법

FastAPI는 검수 이력 저장, 목록 조회, 상세 조회를 담당합니다. 실행 전에 `DATABASE_URL`, `CATALOGGUARD_JWT_SECRET`이 설정되어 있고 Alembic 마이그레이션이 적용되어 있어야 합니다.

```powershell
cd C:\study\catalogguard-lite
.\.venv\Scripts\Activate.ps1
python -m uvicorn api.main:app --host 127.0.0.1 --port 8001 --reload
```

브라우저에서 아래 주소를 확인합니다.

- Health check: http://127.0.0.1:8001/health
- Readiness check: http://127.0.0.1:8001/ready
- API docs: http://127.0.0.1:8001/docs

`/health`와 `/ready`는 로그인 없이 접근할 수 있지만, 검수·ETL·promotion·rollback API는 로그인이 필요합니다. 회원가입 API는 없으므로 먼저 `scripts/create_user.py`로 계정을 만듭니다.

```powershell
$env:CATALOGGUARD_SEED_USER_PASSWORD="로컬에서만 사용할 임의의 비밀번호"
python scripts/create_user.py --username operator1 --role operator
```

`--password`를 생략하면 `CATALOGGUARD_SEED_USER_PASSWORD` 환경변수를 사용하고, 그것도 없으면 대화형으로 비밀번호를 입력받습니다. 로그인 후 발급받은 Access Token을 `Authorization: Bearer` 헤더에 넣어 요청합니다.

```powershell
$login = Invoke-RestMethod -Method Post -Uri "http://127.0.0.1:8001/api/v1/auth/login" `
  -ContentType "application/json" `
  -Body (@{ username = "operator1"; password = "위에서 설정한 비밀번호" } | ConvertTo-Json)

curl.exe -X POST "http://127.0.0.1:8001/api/v1/inspections" `
  -H "accept: application/json" `
  -H "Authorization: Bearer $($login.access_token)" `
  -F "file=@data/dev/products_dev.csv;type=text/csv"
```

서버는 실행 중인 PowerShell에서 `Ctrl+C`로 종료합니다.

### FastAPI + PostgreSQL + Redis + Celery Docker Compose 로컬 실행

이 절은 `compose.local.yaml`로 FastAPI, PostgreSQL, Redis, Celery Worker를 실행합니다. Streamlit은 호스트에서 실행하며 컨테이너화하지 않습니다. API와 Worker 이미지는 기존 `Dockerfile.local`을 재사용하고, 컨테이너 내부 API 포트 `8000`은 Windows 호스트의 기본 `8001`에 연결합니다. PostgreSQL은 CI와 같은 메이저 버전 18을 사용하며, Windows PostgreSQL의 기본 포트 `5432`와 겹치지 않도록 호스트의 `5433`에 연결합니다.

#### 로컬 환경변수 파일 준비

저장소 루트에서 예시 파일을 복사하고 `.env.local`의 `CHANGE_ME`만 URL-safe 임의 문자열로 바꿉니다. 실제 비밀번호나 전체 DB 연결 문자열은 문서, 명령 출력 또는 Git에 기록하지 않습니다. `.env.local`과 일반 `.env`는 `.gitignore` 및 `.dockerignore`에서 제외됩니다.

```powershell
cd C:\study\catalogguard-lite
Copy-Item .env.local.example .env.local
notepad .env.local
```

호스트 포트가 이미 사용 중이면 `.env.local`의 `POSTGRES_HOST_PORT` 또는 `API_HOST_PORT`만 다른 빈 포트로 바꿉니다. 컨테이너끼리는 호스트 포트와 관계없이 API가 `db` 서비스의 PostgreSQL `5432` 포트에 연결합니다.

#### 빌드와 실행

```powershell
docker compose --env-file .env.local -f compose.local.yaml build
docker compose --env-file .env.local -f compose.local.yaml up -d
```

`db`와 `redis` healthcheck가 통과한 뒤 `api`가 시작되고, API가 healthy 상태가 되면 `worker`가 시작됩니다. API 시작 명령은 먼저 `python -m alembic upgrade head`를 적용하고, 성공한 경우에만 Uvicorn을 `--no-access-log`로 실행합니다. 임의의 `sleep`은 사용하지 않습니다.

서비스 상태와 필요한 로그만 확인합니다. 정상 기동이면 `db`, `redis`, `api`가 healthy이고 Worker 로그에 `ready`가 표시됩니다.

```powershell
docker compose --env-file .env.local -f compose.local.yaml ps
docker compose --env-file .env.local -f compose.local.yaml logs --tail 100 db redis api worker
```

마이그레이션의 현재 revision과 head가 같은지 확인합니다.

```powershell
docker compose --env-file .env.local -f compose.local.yaml exec api `
  python -m alembic current
docker compose --env-file .env.local -f compose.local.yaml exec api `
  python -m alembic heads
```

#### Health와 readiness 확인

`/health`는 API 프로세스를, `/ready`는 PostgreSQL 연결까지 확인합니다. 두 응답이 HTTP `200`이고 `/ready` 본문의 `database`가 `ok`인지, 두 응답에 `X-Request-ID`가 있는지 확인합니다.

```powershell
$healthResponse = Invoke-WebRequest `
  -Uri "http://127.0.0.1:8001/health" `
  -UseBasicParsing
$readyResponse = Invoke-WebRequest `
  -Uri "http://127.0.0.1:8001/ready" `
  -UseBasicParsing

$healthResponse.StatusCode
$healthResponse.Content
$healthResponse.Headers["X-Request-ID"]
$readyResponse.StatusCode
$readyResponse.Content
$readyResponse.Headers["X-Request-ID"]
```

API 문서는 http://127.0.0.1:8001/docs 에서 확인할 수 있습니다. CSV 저장·목록·상세 조회 API는 위의 기존 FastAPI 사용법과 동일합니다.

#### 중지, 삭제, 데이터 보존

다음 명령은 컨테이너와 네트워크만 제거합니다. `postgres_data`, `redis_data`, `inspection_jobs` named volume은 남으므로 같은 Compose 프로젝트를 다시 실행하면 검수 이력과 로컬 비동기 작업 데이터가 유지됩니다.

```powershell
docker compose --env-file .env.local -f compose.local.yaml down
```

컨테이너만 잠시 멈추고 나중에 그대로 재개하려면 `stop`과 `start`를 사용합니다.

```powershell
docker compose --env-file .env.local -f compose.local.yaml stop
docker compose --env-file .env.local -f compose.local.yaml start
```

아래 명령의 `-v`는 PostgreSQL, Redis, 작업 파일 named volume과 모든 로컬 검수·작업 데이터를 삭제합니다. 복구할 수 없는 로컬 전체 초기화가 목적일 때만 실행합니다.

```powershell
> 주의: 로컬 PostgreSQL·Redis·비동기 작업 데이터를 영구 삭제합니다.
docker compose --env-file .env.local -f compose.local.yaml down -v
```

데이터를 보존하려면 `down -v`와 named volume 수동 삭제를 피하고, 동일한 저장소 경로와 `compose.local.yaml`을 사용합니다. 볼륨 존재 여부는 `docker volume ls --filter "name=catalogguard-lite-local"`로 확인할 수 있습니다.

#### 오류 확인 항목

- Docker Desktop이 실행 중이고 `docker version`에서 Server 정보가 보이는지 확인합니다.
- `docker compose ... ps`에서 `db`, `redis`, `api` healthcheck와 `worker` 상태를 확인합니다.
- `docker compose ... logs --tail 100 db redis api worker`에서 PostgreSQL·Redis 초기화, Alembic, Uvicorn, Celery 시작 오류를 확인합니다.
- Windows에서 `5433` 또는 `8001`이 사용 중이면 `.env.local`의 호스트 포트를 바꿉니다.
- `.env.local`의 필수 값이 비어 있지 않은지 확인하되, 비밀번호나 DB 연결 문자열을 터미널에 출력하지 않습니다.
- migration 오류가 있으면 `alembic current`와 `alembic heads`를 비교합니다.

`compose.local.yaml`, `.env.local.example`, `Dockerfile.local`은 로컬 개발 전용입니다. 루트 `Dockerfile`을 추가하지 않고 Railway 설정도 수정하지 않으므로 기존 Railpack 빌드, Pre-deploy Command, Start Command, 운영 `DATABASE_URL`과 Railway 배포 방식에는 영향을 주지 않습니다.

### AWS EC2·RDS staging 수동 배포 및 검증

2026-07-19 AWS 서울 리전에서 Amazon Linux 2023 EC2의 Docker 기반 FastAPI와
PostgreSQL RDS를 사용한 staging 수동 배포를 검증했습니다.
TLS 기반 RDS 연결과 Alembic migration을 적용하고 `/health`와 `/ready`의 HTTP 200 응답을 확인했으며,
CSV 저장·목록·상세 조회와 동일 CSV 중복 저장 방지를 검증했습니다.
별도 Streamlit AWS 검증 앱에서도 화면 저장과 검수 이력 조회를 확인했습니다.
상세 배포 절차와 재시작·중지 방법은 [AWS staging 배포 런북](docs/aws-staging-deployment.md)을 참고합니다.
기존 Railway production과 production Streamlit 설정은 변경하지 않았습니다.

### AWS staging S3 Supplier CSV ingestion 실제 E2E 검증

2026-08-12 서울 리전(`ap-northeast-2`) staging에서 S3 source adapter를 실제 AWS 자원에 연결해 검증했습니다. 이전까지 이 기능은 fake S3 client 기반 단위·API 테스트만 있었고, 이번에 실제 S3 객체·EC2 Instance Role·RDS까지 연결한 것이 차이입니다.

```text
private S3 (Block Public Access 4개 모두 활성, SSE-S3, bucket policy 없음)
-> EC2 Instance Role(CatalogGuardEC2SSMRole) 최소권한
-> FastAPI POST /api/v1/etl-loads/s3
-> 기존 read_s3_csv_object() -> run_web_etl() -> run_pipeline() -> load_standard_csv()
-> RDS PostgreSQL staging(ETLLoadRun / staging row / Actor Audit)
```

IAM은 EC2 Role의 inline policy 하나로 `s3:GetObject`만, 그것도 `arn:aws:s3:::<staging-bucket>/incoming/catalogguard/*` 한 prefix로 제한했습니다. `s3:PutObject`·`s3:DeleteObject`·`s3:ListBucket`·`s3:*`·`Resource: "*"`는 부여하지 않았고, 컨테이너에 AWS access key를 주입하지 않아 실제 principal이 `assumed-role/CatalogGuardEC2SSMRole/<instance-id>`로 확인되었습니다. EC2 Security Group의 inbound 규칙은 0개이고 FastAPI는 `127.0.0.1:8000`에만 bind하며, RDS는 publicly accessible `false`·저장 암호화 활성 상태에서 EC2 Security Group만 5432로 접근합니다. 호출은 SSM Session Manager 경유 localhost로 수행했고 SSH나 public inbound를 열지 않았습니다.

합성 fixture `tests/fixtures/etl/sample_vendor_valid.csv`(236 bytes) 1건만 사용했으며 실제 고객·공급사 데이터는 사용하지 않았습니다. 실제 결과는 다음과 같습니다.

| 검증 | 실제 결과 |
|---|---|
| 첫 요청 | HTTP `200`, `created=true`, `etl_load_run_id=1`, total 1 / loaded 1 / rejected 0 |
| ETL 변환 | 입력 `"12,000"` -> staging `price=12000`(기존 pipeline 그대로) |
| 동일 객체 재요청 | HTTP `200`, `created=false`, 같은 `etl_load_run_id`, DB `etl_load_runs` 1건 유지 |
| Actor Audit | `actor_user_id`·`actor_username`이 `users` row와 일치, dedup 요청에서도 최초 actor 유지 |
| anonymous / viewer | `401 authentication_required` / `403 insufficient_role` |
| 허용 prefix 밖 key | `400 s3_key_not_allowed` (S3 호출 전 차단) |
| 허용 prefix 내 없는 key | `502 s3_read_failed` |
| cold start | EC2 stop 후 재시작 시 최신 container 자동 기동, `/health`·`/ready` 모두 `200` |

"허용 prefix 내 없는 key" 항목은 설명이 필요합니다. `s3:ListBucket`을 주지 않으면 실제 S3는 없는 key에 `404`가 아니라 `403 AccessDenied`를 반환하므로, 애플리케이션은 이를 `s3_object_not_found`가 아니라 `s3_read_failed`로 안전하게 매핑합니다. `404`를 만들기 위해 `ListBucket`을 추가하지 않았고, 최소권한을 유지한 결과로 기록합니다.

이번 검증에서 S3 bucket과 IAM policy는 AWS Console·CLI로 구성했습니다. Terraform으로 만들거나 `import`하지 않았으므로 Terraform이 관리하는 자원이 아닙니다. 애플리케이션 코드는 수정하지 않았고, 변경한 것은 AWS staging runtime 설정(환경변수·RDS CA bundle 배치·최신 image 재배포)뿐입니다.

### Railway FastAPI 배포 설정

production 환경에는 `catalogguard-lite` FastAPI 서비스와 `Postgres` PostgreSQL 서비스가 배포되어 있습니다. API 의존성은 `requirements-api.txt`에 분리되어 있으므로 Railway 대시보드에서 Build Command는 비워 두고, 다음 설정을 사용합니다.

```text
Root Directory: /
Build Command: (비워 둠)
RAILPACK_INSTALL_CMD: python -m venv /app/.venv && /app/.venv/bin/python -m pip install -r requirements-api.txt
Pre-deploy Command: cd /app && /app/.venv/bin/alembic upgrade head
Start Command: cd /app && /app/.venv/bin/uvicorn api.main:app --host 0.0.0.0 --port $PORT --no-access-log
Healthcheck Path: /health
DATABASE_URL: Postgres 서비스의 DATABASE_URL을 Reference Variable로 연결
```

실제 `DATABASE_URL` 값이나 비밀번호는 저장소에 기록하지 않습니다. Start Command에는 운영 배포용으로 `--reload`, `127.0.0.1`, 고정 포트 `8000`을 넣지 않습니다. `--no-access-log`는 query string을 포함할 수 있는 Uvicorn 기본 요청 접근 로그만 비활성화하며, FastAPI 서버 시작 로그와 애플리케이션이 직접 기록하는 요청별 구조화 로그는 계속 유지합니다. `/health`는 FastAPI 프로세스 상태만 빠르게 확인하며 PostgreSQL 연결까지 확인하지 않습니다.

Railway Healthcheck Path는 계속 `/health`로 유지합니다. `/ready`는 FastAPI와 PostgreSQL 연결 상태를 함께 확인하며, 코드 배포 후 `/ready` 응답을 별도로 확인해야 합니다.

Railway가 제공하는 driverless `postgresql://` 형식의 `DATABASE_URL`은 애플리케이션에서 `postgresql+psycopg://`로 정규화해 SQLAlchemy가 설치된 `psycopg` 드라이버를 사용하게 합니다.

공개 API 주소와 확인 경로는 다음과 같습니다.

- API Base URL: https://catalogguard-lite-production.up.railway.app
- Health: https://catalogguard-lite-production.up.railway.app/health
- Readiness (코드 배포 후 확인): https://catalogguard-lite-production.up.railway.app/ready
- Swagger Docs: https://catalogguard-lite-production.up.railway.app/docs

Streamlit Community Cloud의 Secrets에는 다음 값을 설정합니다.

```toml
CATALOGGUARD_API_BASE_URL = "https://catalogguard-lite-production.up.railway.app"
CATALOGGUARD_API_TIMEOUT_SECONDS = "10"
```

현재 배포에서 확인한 범위는 `/health`, `/docs`, Streamlit Community Cloud 연결, CSV 검수, PostgreSQL 검수 이력 저장, 목록·상세 조회, 상세·전체 CSV 다운로드와 동일 파일 중복 저장입니다. promotion의 실제 배포 여부와 공개 앱 기능 범위는 별도 검증하지 않았습니다.

#### 첫 배포 오류 해결

- 첫 빌드에서는 Railway가 `requirements.txt`를 설치해 FastAPI, SQLAlchemy, Alembic, psycopg 등 API·DB 패키지가 누락되었습니다.
- `RAILPACK_INSTALL_CMD`로 `requirements-api.txt`를 설치하도록 바꿨지만, 설치 명령을 덮어쓰면서 `/app/.venv`가 생성되지 않았습니다. 현재 명령은 `python -m venv /app/.venv`로 가상환경을 먼저 생성합니다.
- Pre-deploy에서 `alembic command not found`가 발생해 `/app/.venv/bin/alembic` 절대 경로를 사용하도록 수정했습니다.
- Start Command의 `uvicorn`도 같은 이유로 `/app/.venv/bin/uvicorn` 절대 경로를 사용합니다.

### Kubernetes Deployment Readiness(kind 기반 CI 검증)

새 Kubernetes 전용 Dockerfile을 만들지 않고 기존 `Dockerfile.aws` image를 그대로 사용합니다. `k8s/` 아래 manifest 3개가 이 image를 kind(Docker 안에서 실제 Kubernetes node를 실행하는 CI/로컬 도구) cluster에 배포합니다.

```text
Dockerfile.aws image
-> kind Kubernetes cluster
-> catalogguard namespace
-> CI 런타임 Secret(catalogguard-secrets)
-> PostgreSQL Deployment + Service (CI disposable, PVC 없음)
-> Alembic Migration Job (command override로 1회 실행)
-> FastAPI Deployment (command override로 uvicorn만 실행) + Service
-> livenessProbe /health, readinessProbe /ready
```

`Dockerfile.aws`의 기본 CMD는 `alembic upgrade head && uvicorn ...` 순서로 migration과 API 실행을 함께 담당합니다. Kubernetes에서는 API Pod가 여러 개일 수 있어 이 CMD를 그대로 쓰면 각 Pod가 migration을 중복 실행할 수 있으므로, `k8s/migration-job.yaml`이 `command` override로 migration만 실행하는 별도 `Job`을 담당하고 `k8s/catalogguard-api.yaml`은 `command` override로 uvicorn만 실행합니다. `Dockerfile.aws` 자체는 수정하지 않았습니다.

| Manifest | 역할 |
|---|---|
| `k8s/dev-postgres.yaml` | CI/kind smoke 전용 disposable `Deployment`+`Service`(`postgres:18`, PVC 없음, `pg_isready` probe) |
| `k8s/migration-job.yaml` | 기존 image로 `python -m alembic upgrade head`만 실행하는 `Job`(`backoffLimit: 2`) |
| `k8s/catalogguard-api.yaml` | 기존 image로 uvicorn만 실행하는 `Deployment`(`replicas: 1`)+`Service`(ClusterIP `:8000`) |

liveness와 readiness는 기존 endpoint 의미를 그대로 따릅니다.

```text
livenessProbe  -> GET /health  (프로세스 생존만 확인, DB 미확인 — DB 장애로 정상 container가 계속 재시작되는 것을 방지)
readinessProbe -> GET /ready   (PostgreSQL 연결까지 확인 — DB에 연결될 때만 Service가 트래픽을 보냄)
```

두 endpoint의 Python 로직은 이번 작업에서 변경하지 않았습니다. API·Migration Pod 모두 기존 Dockerfile의 UID와 동일한 `runAsUser: 10001`(non-root), `allowPrivilegeEscalation: false`로 실행됩니다. `catalogguard-secrets`는 manifest에 하드코딩된 값 없이 `secretKeyRef`(name+key)만 참조하며, 실제 값은 GitHub Actions 실행마다 `kubectl create secret generic`으로 새로 생성합니다(YAML 자체는 commit하지 않음).

`.github/workflows/test.yml`의 `kubernetes-smoke` job은 kind와 kubectl을 고정 버전으로 설치한 뒤(`releases/latest`·`stable.txt` 같은 동적 조회 없이 `KIND_VERSION`/`KUBECTL_VERSION`/`KIND_NODE_IMAGE`를 job `env:`에 고정), 실제 cluster에서 위 흐름 전체를 검증합니다.

```text
kind/kubectl 설치(고정 버전)
-> Dockerfile.aws image build
-> kind cluster 생성(node image SHA-256 digest 고정)
-> kind load docker-image
-> namespace/Secret 생성
-> PostgreSQL rollout 대기
-> Migration Job condition=complete 대기
-> FastAPI rollout 대기
-> Service port-forward로 GET /health, GET /ready 확인
-> 실패 시 kubectl get/describe/logs 진단(Secret 값은 출력하지 않음)
-> kind cluster 삭제
```

이번 범위는 FastAPI + PostgreSQL의 Kubernetes 배포 가능성 검증까지입니다. Redis/Celery Async Inspection과 Streamlit은 Kubernetes에 배포하지 않았고, Ingress·TLS·HPA·Helm·실제 EKS/GKE/AKS도 이번 범위에 없습니다. 아래 Terraform은 AWS EC2·RDS staging 구성을 코드화한 것이며 Kubernetes cluster나 EKS를 만들지 않습니다. 현재 한계는 25장을 참고하세요.

### Terraform AWS Staging IaC Validation(mock provider 기반 CI 검증)

위 "AWS EC2·RDS staging 수동 배포 및 검증"에서 콘솔로 직접 만든 staging 구성을 `terraform/` 아래 코드로 옮긴 IaC Validation MVP입니다. 이 저장소에서는 `terraform apply`·`destroy`·`import`를 실행하지 않으며, 검증은 fmt·validate와 mock provider 기반 `terraform test`까지입니다. 따라서 이 코드로 만들어진 실제 AWS 리소스는 없고, 2026-07-19에 수동으로 만든 기존 staging 리소스도 Terraform state에 들어 있지 않습니다.

```text
수동 AWS staging 구성(문서 기록)
-> terraform/ 코드화(data·resource·variable)
-> mock provider 기반 보안 정책 test
-> GitHub Actions terraform-validate job 자동 검증
```

| 파일 | 역할 |
|---|---|
| `terraform/versions.tf` | `required_version = "~> 1.15.0"`, AWS provider `~> 6.55.0` 고정(backend 미구성) |
| `terraform/variables.tf` | region·이름 접두어·인스턴스 타입·RDS 설정 변수. `rds_master_password`는 `default` 없이 `sensitive = true` |
| `terraform/main.tf` | Default VPC·subnet·AMI 조회와 Security Group·IAM·EC2·RDS 리소스 정의 |
| `terraform/outputs.tf` | EC2 instance ID, 두 Security Group ID, RDS 식별자만 출력(endpoint·비밀번호 미출력) |
| `terraform/.terraform.lock.hcl` | 실제 선택된 provider 버전 `6.55.0` 고정(commit 대상) |
| `terraform/tests/staging.tftest.hcl` | mock provider 기반 보안 정책 test |

조회(data)와 생성(resource) 대상은 다음과 같습니다. custom VPC나 private subnet을 새로 만들지 않고 기존 Default VPC·subnet을 그대로 조회해 사용합니다.

```text
data  : aws_vpc.default, aws_subnets.default,
        aws_ami.amazon_linux_2023, aws_iam_policy_document.ec2_assume_role
resource: aws_security_group.ec2, aws_security_group.rds,
          aws_iam_role.ec2_ssm, aws_iam_role_policy_attachment.ec2_ssm_core,
          aws_iam_instance_profile.ec2_ssm, aws_instance.api,
          aws_db_subnet_group.staging, aws_db_instance.staging
```

보안 설정은 수동 구성에서 확인한 기준을 그대로 코드로 옮겼습니다.

- EC2 Security Group에는 `ingress` 블록 자체를 두지 않습니다. SSH `22`를 포함해 인터넷에 공개하는 inbound 규칙이 없으며, 접근은 SSM Session Manager로만 합니다.
- RDS Security Group은 PostgreSQL `5432` 하나만 허용하고, source도 CIDR이 아니라 EC2 Security Group 참조입니다(`cidr_blocks = []`).
- `aws_db_instance.staging`의 `publicly_accessible`은 변수로 노출하지 않고 `false`로 고정했습니다.
- `storage_encrypted = true`로 RDS 저장 데이터를 암호화합니다.
- `rds_master_password`는 기본값이 없고 `sensitive = true`이므로, 실제 사용 시 `TF_VAR_rds_master_password` 같은 외부 경로로 주입해야 하며 저장소에 값을 커밋하지 않습니다.
- EC2에는 SSM용 IAM Role(`AmazonSSMManagedInstanceCore` 관리형 정책 1개만 연결)과 Instance Profile을 붙이고 `key_name`을 지정하지 않아 SSH key pair를 만들지 않습니다.
- `metadata_options { http_tokens = "required" }`(IMDSv2)와 루트 볼륨 `encrypted = true`는 2026-07-19 수동 구성에는 없던 값이며, 이번 코드화 시 추가한 표준 보안 기본값입니다. apply하지 않았으므로 실제 인스턴스에는 아직 반영되지 않았습니다.

`terraform/tests/staging.tftest.hcl`은 `mock_provider "aws" {}`와 `override_data` 4개를 사용해 실제 AWS 자격 증명·리소스 없이 계산된 값만 검증합니다. `run` 블록은 2개이며 assertion은 모두 12개입니다.

| run 블록 | assertion | 검증 내용 |
|---|---:|---|
| `plan_staging_infrastructure` | 9 | EC2 inbound 규칙 0개, RDS ingress 정확히 1개, 그 규칙이 `5432`·CIDR 0개·Security Group 1개인지, RDS `publicly_accessible=false`·Single-AZ·`storage_encrypted=true`·`skip_final_snapshot=false`, EC2의 SSM instance profile 사용과 `AmazonSSMManagedInstanceCore` 정책 연결 |
| `no_open_internet_ingress` | 3 | `publicly_accessible`이 계속 `false`로 고정되어 있는지, EC2·RDS Security Group 어느 쪽에도 `0.0.0.0/0` inbound가 없는지 |

두 번째 run 블록은 이후 누군가 `0.0.0.0/0` inbound 규칙을 추가하면 CI가 실패하도록 하는 보안 회귀 방지 test입니다. `key_name` 미설정은 mock provider가 미설정 속성에도 임의 값을 채우기 때문에 test로 검증하지 않고 코드 리뷰로 확인합니다.

`.github/workflows/test.yml`의 `terraform-validate` job은 `terraform` 디렉터리에서 다음 순서로 실행되며, AWS 자격 증명을 사용하지 않습니다.

```text
hashicorp/setup-terraform (TERRAFORM_VERSION 1.15.8 고정, terraform_wrapper: false)
-> terraform fmt -check -recursive
-> terraform init -backend=false -input=false -lockfile=readonly
-> terraform validate
-> terraform test (mock provider)
```

`init`은 `-backend=false`로 실행하므로 remote state를 만들지 않고, `-lockfile=readonly`로 `.terraform.lock.hcl`에 고정된 provider 버전을 CI가 임의로 갱신하지 못하게 합니다. `.gitignore`에는 `.terraform/`, `*.tfstate*`, `*.tfplan`, `terraform.tfvars`, `override.tf` 계열을 추가했고, provider 버전을 고정하는 `.terraform.lock.hcl`만 commit합니다.

commit `38385f0`의 GitHub Actions run `31160915277`에서 확인한 결과는 다음과 같습니다.

```text
Installed hashicorp/aws v6.55.0 (signed by HashiCorp)
terraform validate -> Success! The configuration is valid.
run "plan_staging_infrastructure"... pass
run "no_open_internet_ingress"... pass
terraform test -> Success! 2 passed, 0 failed.
```

같은 run에서 `test`·`browser-e2e`·`kubernetes-smoke` job도 모두 성공했습니다. 이번 범위는 코드화와 정적·mock 검증까지이며, 실제 AWS 리소스 생성·기존 리소스 import·S3 remote state·state locking은 포함하지 않습니다. 현재 한계는 25장을 참고하세요.

## 17. Streamlit 실행 방법

Streamlit 화면만 실행하려면 아래 명령을 사용합니다.

```powershell
cd C:\study\catalogguard-lite
.\.venv\Scripts\Activate.ps1
python -m streamlit run app.py
```

검수 이력까지 사용하려면 다른 PowerShell 창에서 FastAPI 서버를 먼저 실행하고, Streamlit을 실행하는 PowerShell에도 API 주소를 설정합니다.

```powershell
$env:CATALOGGUARD_API_BASE_URL="http://127.0.0.1:8001"
python -m streamlit run app.py
```

브라우저가 자동으로 열리지 않으면 터미널에 표시되는 Streamlit 주소를 열면 됩니다.

화면을 열면 좌측 사이드바에 로그인 폼이 표시됩니다. 로그인 전에는 "좌측 사이드바에서 로그인한 뒤 이용해 주세요" 안내만 보이며 어떤 탭도 사용할 수 없습니다. 위 16장에서 만든 계정으로 아이디·비밀번호를 입력해 로그인하면 사이드바에 `아이디 (운영자/조회자)로 로그인했습니다`가 표시되고, 로그아웃 버튼으로 세션을 종료할 수 있습니다. viewer로 로그인하면 조회 화면은 그대로 사용할 수 있지만 ETL 실행·Promotion·Rollback 버튼은 비활성화됩니다(실제 차단은 FastAPI가 수행하며 이 비활성화는 편의 기능입니다).

## 18. API 목록

### `GET /health`

FastAPI 서버 상태를 확인합니다. PostgreSQL 연결을 확인하는 엔드포인트는 아닙니다. Docker `HEALTHCHECK`와 Kubernetes `livenessProbe`(16장 "Kubernetes Deployment Readiness" 참고)가 이 endpoint를 사용해 "프로세스 자체가 살아 있는지"만 확인합니다.

응답 예시는 다음과 같습니다.

```json
{
  "status": "ok",
  "service": "catalogguard-lite-api"
}
```

### `GET /ready`

FastAPI 프로세스와 PostgreSQL 연결 상태를 함께 확인합니다. 기존 SQLAlchemy 엔진으로 `SELECT 1`을 실행하며, 성공하면 HTTP `200`과 `database: "ok"`를 반환하고 연결 또는 쿼리가 실패하면 내부 오류 내용을 노출하지 않고 HTTP `503`과 `database: "unavailable"`을 반환합니다.

공개 확인 주소는 https://catalogguard-lite-production.up.railway.app/ready 입니다. 운영 배포에서 `/health`와 `/ready`가 HTTP `200`을 반환하고 `/ready`의 `database`가 `"ok"`인지 확인합니다. Railway Healthcheck Path는 `/health`로 유지합니다. `/health`, `/ready`는 `POST /api/v1/auth/login`과 함께 로그인 없이 접근할 수 있는 유일한 endpoint입니다. Kubernetes에서는 이 endpoint를 `readinessProbe`로 사용해, PostgreSQL에 연결할 수 있을 때만 Service가 해당 Pod로 트래픽을 보내도록 합니다.

### `GET /metrics`

`CATALOGGUARD_METRICS_ENABLED=true`(또는 `1`/`yes`)일 때만 Prometheus text 형식으로 현재 custom metric을 반환합니다. 그 외에는(미설정 포함) 로그인 여부와 관계없이 항상 HTTP `404`입니다. 인증은 요구하지 않지만 기본값이 비활성이므로 별도로 켜지 않으면 외부에 노출되지 않습니다. metric 정의와 label 설계는 아래 "Prometheus Metrics"를 참고하세요.

### `POST /api/v1/auth/login`

아이디·비밀번호로 로그인하고 JWT Access Token을 발급받습니다. 회원가입 API는 없으며 계정은 `scripts/create_user.py`로만 만듭니다(13장 참고).

```json
{
  "username": "operator1",
  "password": "..."
}
```

성공 응답에는 `access_token`, `token_type`(`"bearer"`), `expires_in`(초)이 있습니다. 아이디가 없거나, 비밀번호가 틀리거나, 계정이 비활성 상태여도 모두 같은 HTTP `401`과 `{"code": "invalid_credentials", ...}`만 반환해 계정 존재 여부나 활성 상태를 외부에 노출하지 않습니다.

### `GET /api/v1/auth/me`

현재 로그인한 사용자의 `username`, `role`을 반환합니다(`password_hash`는 절대 포함하지 않습니다). 로그인이 필요합니다.

### 인증(Authentication)과 권한(RBAC)

로그인 후에는 모든 요청에 `Authorization: Bearer <access_token>` 헤더가 필요합니다. Streamlit의 `CatalogGuardApiClient`는 로그인 성공 시 이 헤더를 세션에 한 번 설정해 이후 모든 요청에 자동으로 붙입니다.

- **401 Unauthorized**: 로그인되지 않았거나(토큰 없음), JWT가 없거나 형식이 잘못됐거나 만료됐거나, 토큰은 유효하지만 계정이 비활성(`is_active=false`)인 경우
- **403 Forbidden**: 로그인은 성공했지만 현재 역할(`role`)로는 허용되지 않는 작업인 경우

예를 들어 viewer 계정으로 로그인한 뒤 Promotion 실행 API를 호출하면, 로그인 자체는 성공했으므로 401이 아니라 403(`insufficient_role`)이 반환됩니다.

`get_current_user()`는 토큰의 `role`을 그대로 신뢰하지 않고 매 요청마다 PostgreSQL의 `users` 테이블에서 현재 `role`·`is_active`를 다시 확인합니다. 따라서 이미 발급된 토큰이 있어도 관리자가 계정을 비활성화하면 다음 요청부터 즉시 차단됩니다.

역할은 `viewer`(조회)와 `operator`(운영 데이터 변경) 2개만 있습니다. 현재 admin 전용 기능이 없어 admin 역할은 만들지 않았습니다.

| Endpoint | 인증 | 필요 역할 |
|---|---|---|
| `GET /health`, `GET /ready`, `POST /api/v1/auth/login` | 불필요 | - |
| `GET /api/v1/auth/me` | 필요 | viewer 이상 |
| `GET /api/v1/inspections`, `GET /api/v1/inspections/{id}` | 필요 | viewer 이상 |
| `POST /api/v1/inspections` | 필요 | operator |
| `GET /api/v1/inspection-jobs/{job_id}` | 필요 | viewer 이상 |
| `POST /api/v1/inspection-jobs` | 필요 | operator |
| `GET /api/v1/etl-profiles`, `GET /api/v1/etl-loads`, `GET /api/v1/etl-loads/{id}` | 필요 | viewer 이상 |
| `POST /api/v1/etl-loads`, `POST /api/v1/etl-loads/s3` | 필요 | operator |
| `POST /api/v1/etl-loads/{id}/promotion-preview` | 필요 | viewer 이상 |
| `POST /api/v1/etl-loads/{id}/promotions` | 필요 | operator |
| `GET /api/v1/catalog-promotions`, `GET /api/v1/catalog-promotions/{id}`, `GET /api/v1/catalog-promotions/{id}/audits` | 필요 | viewer 이상 |
| `POST /api/v1/catalog-promotions/{id}/rollback-preview` | 필요 | viewer 이상 |
| `POST /api/v1/catalog-promotions/{id}/rollback` | 필요 | operator |
| `GET /api/v1/catalog-promotion-rollbacks`, `GET /api/v1/catalog-promotion-rollbacks/{id}`, `GET /api/v1/catalog-promotion-rollbacks/{id}/changes` | 필요 | viewer 이상 |

Promotion Preview·Rollback Preview는 DB를 변경하지 않고 "무엇이 바뀔지"만 보여주므로 viewer도 조회할 수 있게 했고, 실제 반영(Promotion 실행)·되돌리기(Rollback 실행)만 operator로 제한했습니다. UI에서 viewer의 실행 버튼을 비활성화하는 것은 편의 기능일 뿐이며, 실제 권한 검사는 항상 FastAPI가 수행합니다.

### Actor Audit

Authentication(로그인한 사용자가 누구인지 확인)과 RBAC(그 사용자가 무엇을 할 수 있는지 확인)은 실행 전 통제입니다. Actor Audit은 여기에 실행 이력 row를 최초로 만든 사용자를 기록합니다. Sync·Async Inspection, Web ETL, Promotion, Rollback이 새 실행 이력을 만들 때 요청을 처리한 `current_user.id`·`current_user.username`을 `actor_user_id`·`actor_username`으로 저장합니다.

```text
JWT
-> require_operator
-> current_user
-> current_user.id, current_user.username
-> actor_user_id, actor_username
-> 실행 이력 DB 저장
```

`actor_username`은 request body나 multipart form 어디에서도 클라이언트가 지정하는 값이 아니며 항상 인증된 `current_user`에서만 가져옵니다. `POST /api/v1/inspections`에 위조한 `actor_user_id`·`actor_username` form 값을 함께 보내도 저장된 actor는 토큰의 실제 사용자입니다. `actor_user_id`는 `users.id`와 현재 사용자를 연결하는 FK라 사용자가 삭제되면 `NULL`이 되고, `actor_username`은 실행 당시 이름을 보존하는 snapshot이라 그대로 남습니다.

Inspection actor는 `inspection_runs` row를 최초로 만든 사용자를 뜻합니다. 동일한 `file_sha256`·`inspection_version` 요청은 기존 row를 재사용하므로, 이후 다른 operator가 같은 CSV를 요청해도 actor를 UPDATE하지 않습니다. 이 MVP는 중복 요청을 포함한 모든 요청자를 별도 event로 저장하는 범용 감사 시스템이 아닙니다.

Sync Inspection은 route가 `current_user` scalar를 공통 `save_inspection_report()`에 직접 전달합니다. Async Inspection은 SQLAlchemy `User` 객체나 JWT를 Redis/Celery로 넘기지 않고 `actor_user_id`·`actor_username` scalar만 `InspectionJobState`에 저장한 뒤 Worker가 같은 persistence 계층에 전달합니다. 기존 actor 필드가 없는 Redis payload는 두 값 모두 `None`으로 복원합니다.

API는 내부 FK인 `actor_user_id`를 노출하지 않습니다. `actor_username`만 새 Sync Inspection 응답과 검수 목록·상세 응답에서 확인할 수 있으며, async job status 응답에는 추가하지 않았습니다. Async 완료 뒤 `inspection_run_id`로 상세를 조회하면 actor를 확인할 수 있습니다. Streamlit 검수 이력 목록·전체 요약 CSV·상세는 실행 사용자를 표시하고, legacy `NULL` actor는 `알 수 없음`으로 표시합니다.

Web ETL은 `ETLLoadRun`이 실제로 생성될 때만 actor를 저장합니다. 파일 검증이나 `run_pipeline()` 단계에서 실패해 `etl_load_runs` row가 없으면 actor도 없습니다. Promotion·Rollback은 기존 실행 이력 구조상 `succeeded`뿐 아니라 `blocked`(`preview_stale` 포함)·`failed` 상태도 row로 남기며 이 상태들에도 actor를 함께 저장합니다. 컬럼·FK 구조는 15장, 저장 범위는 24장을 참고하세요.

현재 Access Token만 구현되어 있으며 Refresh Token은 없습니다. 토큰이 만료되면 다시 로그인해야 합니다.

### 요청 ID와 운영 구조화 로그

FastAPI는 클라이언트의 `X-Request-ID`를 재사용하지 않고 요청마다 새 ID를 생성해 모든 응답의 `X-Request-ID` 헤더에 넣습니다. 요청 ID는 인증 정보나 보안 토큰이 아니라 문제 추적용 식별값입니다.

Streamlit의 `CatalogGuardApiClient`는 응답 헤더의 앞뒤 공백을 제거한 뒤 `^[0-9a-f]{32}$`에 일치하는 정확히 32자리 소문자 16진수만 허용합니다. 검증된 요청 ID는 HTTP 오류와 GET·POST JSON 응답 해석 실패에서 `CatalogGuardApiError.request_id`에 보존되며, 상세 조회 HTTP `404`의 `InspectionNotFoundError`에도 유지됩니다. timeout과 연결 실패는 서버 응답이 없으므로 요청 ID가 없고, 클라이언트가 임의 값을 생성하지 않습니다.

Streamlit은 다음 오류 흐름에서 검증된 요청 ID가 있을 때만 기존 사용자 안내 뒤에 한 번 표시합니다.

- 검수 결과 저장
- 검수 이력 목록 조회
- 검수 상세 결과 조회
- 전체 검수 이력 CSV 준비
- 상세 조회 HTTP `404`

가상의 요청 ID를 사용한 표시 예시는 다음과 같습니다.

```text
검수 이력을 불러오는 중 오류가 발생했습니다.

요청 ID: a29ae9a1c62f4152bb96f6513c323d96
```

화면에는 원본 예외 메시지, 응답 본문, stack trace, DB URL, 비밀번호와 내부 호스트를 표시하지 않습니다. 운영 문제를 추적할 때는 사용자에게 안내된 요청 ID를 Railway 로그의 같은 `request_id`와 대조합니다.

- 라우트가 응답을 반환하면 상태 코드와 관계없이 `http_request_completed`를 한 번 기록합니다.
- 처리되지 않은 일반 예외는 `http_request_failed`로 기록하며, 안전한 기존 HTTP `500` 응답에도 `X-Request-ID`를 포함합니다.
- `/ready`의 DB 확인 실패는 `database_readiness_failed`와 처리된 HTTP `503` 완료 이벤트로 구분해 기록합니다.
- 로그에는 요청 본문과 CSV 내용, query parameter, 요청 헤더, DB URL, 비밀번호, 호스트, 원본 예외 메시지와 stack trace를 기록하지 않습니다.
- Uvicorn 기본 access log는 URL의 query string을 포함할 수 있으므로 Railway Start Command의 `--no-access-log`로 비활성화합니다. 이 옵션은 Uvicorn의 기본 요청 접근 로그만 끄며 FastAPI 서버 시작 로그와 애플리케이션 구조화 로그에는 영향을 주지 않습니다.
- 민감정보, 토큰, 비밀번호는 로그 설정과 관계없이 URL query string에 넣지 않습니다.

Railway Healthcheck Path는 계속 `/health`로 유지합니다. 운영 검증에서 `/health`와 `/ready`의 HTTP `200`, `/ready`의 `database: "ok"`, 정상적인 `X-Request-ID` 생성과 구조화 로그 유지를 확인했습니다. Uvicorn access log를 비활성화한 뒤 검사 query string이 Deploy Logs에 남지 않고 구조화 로그의 `path`가 `/health`로만 기록되는 것도 확인했습니다.

### Prometheus Metrics

구조화 로그와 `/health`·`/ready`는 이미 있었고, 여기에 요청 수·응답 시간·상태 계열처럼 운영 상태를 숫자로 집계하는 metrics 계층을 추가했습니다. 세 가지는 서로 다른 개념이며 Prometheus가 기존 로그나 헬스체크를 대체하지 않습니다.

```text
Logging = 개별 요청·사건의 상세 기록
Health/Ready = 서비스가 살아 있고 요청을 처리할 준비가 됐는지 확인
Metrics = 요청 수·응답 시간·ETL 실행 수 같은 운영 상태의 숫자 집계
```

```text
HTTP Request
-> Request ID 생성
-> FastAPI 처리
-> 기존 구조화 로그 + Prometheus metric 기록(같은 duration 측정값 재사용)
-> request count / duration histogram / status class
```

새 timing middleware를 추가하지 않고, 기존 `log_http_request` middleware가 이미 계산하던 duration을 그대로 재사용해 로그와 metric 양쪽에 씁니다. 현재 정의된 custom metric은 4개입니다.

| metric | type | labels | 설명 |
|---|---|---|---|
| `catalogguard_http_requests_total` | Counter | `method`, `route`, `status_class` | 완료되거나 unhandled exception으로 끝난 모든 HTTP 요청(`/health`·`/ready`·`/metrics` 제외) |
| `catalogguard_http_request_duration_seconds` | Histogram | `method`, `route` | 위와 같은 범위의 요청 처리 시간(초) |
| `catalogguard_web_etl_runs_total` | Counter | `outcome`(`created`/`duplicate`/`failed`) | `POST /api/v1/etl-loads` 요청 결과 |
| `catalogguard_web_etl_rows_total` | Counter | `result`(`loaded`/`rejected`) | 새로 생성된 배치의 처리 행 수 |

`route` label은 실제 요청 경로가 아니라 FastAPI route template을 사용합니다. 예를 들어 `/api/v1/catalog-promotions/1`과 `/api/v1/catalog-promotions/999`는 각각 별도 label이 아니라 둘 다 `/api/v1/catalog-promotions/{promotion_run_id}`로 집계됩니다. 매칭되는 route가 없는 404(예: 존재하지 않는 임의 경로)는 고정 label `unmatched`를 사용합니다. 동적 ID를 label로 그대로 쓰면 값마다 새로운 Prometheus time series가 생겨 메모리와 조회 비용이 계속 늘어나는 high-cardinality 문제가 생기므로, 이 프로젝트는 route template과 소수의 고정값(`status_class`, `outcome`, `result`)만 label로 사용합니다. `username`, `actor_username`, `request_id`, JWT, 실제 run ID, 파일명, 상품 ID 같은 값은 label에도 metric 출력에도 넣지 않습니다.

`/health`, `/ready`, `/metrics` 자체에 대한 요청은 HTTP metric 집계에서 제외합니다. health probe나 Prometheus scrape 요청이 계속 반복되면서 일반 사용자 트래픽 통계를 왜곡하는 것을 막기 위해서입니다. 로그(`http_request_completed` 등)는 이 세 경로에도 그대로 남습니다.

unhandled exception이 발생해도 기존 안전한 HTTP `500` 응답, `X-Request-ID`, `http_request_failed` 구조화 로그는 그대로 유지되며, 여기에 `status_class="5xx"` metric 기록만 추가됩니다. Metrics 때문에 기존 오류 처리 계약을 바꾸지 않았습니다.

Web ETL은 `POST /api/v1/etl-loads`의 결과가 확정된 뒤(즉 `run_web_etl()`이 성공하거나 특정 예외로 실패를 반환한 뒤) route에서 metric을 기록합니다.

```text
신규 실행(created=True)
-> runs_total{outcome="created"} +1
-> rows_total{result="loaded"} += loaded_rows, rows_total{result="rejected"} += rejected_rows

동일 배치 재사용(created=False)
-> runs_total{outcome="duplicate"} +1
-> rows_total은 증가하지 않음(기존 배치의 행 수를 다시 더하면 같은 ETL 결과가 중복 집계됨)

실패(파일 검증/ETL pipeline/load 오류)
-> runs_total{outcome="failed"} +1
-> rows_total 증가 없음
```

Web ETL이 실패하면 `ETLLoadRun` row 자체가 생성되지 않아 Actor Audit 기록도 없지만(18장 "Actor Audit" 참고), `catalogguard_web_etl_runs_total{outcome="failed"}`는 API 실행 시도 자체를 세므로 증가할 수 있습니다. DB 실행 이력(영구), Actor Audit(DB 이력의 실행자 기록), Prometheus metric(현재 프로세스의 운영 집계, 재시작 시 초기화)은 서로 다른 개념입니다.

현재 구현은 애플리케이션이 Prometheus가 읽어갈 수 있는 형식으로 metric을 노출하는 instrumentation MVP이며, Prometheus 서버가 주기적으로 scrape하는 운영 환경이나 Grafana 대시보드는 이번 범위에 포함하지 않습니다. 전용 `CollectorRegistry`를 프로세스 하나 안에서만 사용하므로, 여러 Uvicorn worker를 띄우는 환경에서는 worker별로 값이 나뉘며 이번 MVP는 이를 통합하지 않습니다.

### `POST /api/v1/inspections`

CSV 파일을 업로드해 검수하고, 검수 실행과 상세 결과를 PostgreSQL에 저장합니다.

- 요청 형식: `multipart/form-data`
- 파일 필드명: `file`
- 정상 응답: `inspection_run_id`, `created`, `actor_username`, `summary`, `results`
- 잘못된 CSV: HTTP `400`
- 파일 필드 누락: HTTP `422`

새로 저장된 경우 응답 예시는 다음과 같습니다.

```json
{
  "inspection_run_id": 123,
  "created": true,
  "actor_username": "operator01",
  "summary": {
    "total_products": 5,
    "total_issues": 6,
    "error_count": 6,
    "warning_count": 0
  },
  "results": [
    {
      "status": "오류",
      "product_group_id": "G002",
      "product_id": "P003",
      "error_field": "가격 오류",
      "reason": "상품 가격이 0 이하입니다. 현재 가격: -5,000원.",
      "recommendation": "0보다 큰 정상 판매 가격을 입력하십시오.",
      "risk_level": "높음"
    }
  ]
}
```

같은 CSV bytes와 같은 검수 규칙 버전이 이미 저장되어 있으면 새 `inspection_run`과 `inspection_results`를 만들지 않고 기존 실행 ID를 반환합니다.

```json
{
  "inspection_run_id": 123,
  "created": false,
  "actor_username": "operator01",
  "summary": {
    "total_products": 5,
    "total_issues": 6,
    "error_count": 6,
    "warning_count": 0
  },
  "results": []
}
```

`created=false`일 때는 새로 계산한 결과와 기존 ID를 섞지 않고, 기존 DB에 저장된 요약·상세 결과와 최초 `actor_username`을 반환합니다. 중복 요청을 보낸 현재 사용자로 actor를 덮어쓰지 않습니다. API Client는 구버전 서버 호환을 위해 `created`가 없는 응답은 `true`로 처리하지만, `created`가 존재할 때는 실제 boolean 값만 허용합니다.

### `GET /api/v1/inspections`

저장된 검수 이력 목록을 조회합니다.

| Query | 기본값 | 조건 |
|---|---:|---|
| `limit` | `20` | `1` 이상 `100` 이하 |
| `offset` | `0` | `0` 이상 |
| `filename` | 없음 | 선택값, 최대 `100`자 |
| `start_date` | 없음 | 선택값, `YYYY-MM-DD` |
| `end_date` | 없음 | 선택값, `YYYY-MM-DD` |
| `status` | 없음 | 선택값, `error`, `warning`, `normal` |

응답 예시는 다음과 같습니다.

```json
{
  "items": [
    {
      "inspection_run_id": 11,
      "source_filename": "products_dev.csv",
      "actor_username": "operator01",
      "created_at": "2026-07-04T13:42:39.495949+09:00",
      "total_products": 5,
      "total_issues": 6,
      "error_count": 6,
      "warning_count": 0
    }
  ],
  "total": 1,
  "limit": 20,
  "offset": 0
}
```

### `GET /api/v1/inspections/{inspection_run_id}`

저장된 검수 실행 1건의 상세 결과를 조회합니다.

- `inspection_run_id`가 없으면 HTTP `404`
- 숫자가 아닌 ID는 HTTP `422`
- 응답에는 파일명, `actor_username`, 저장 시각, 요약, 상세 결과 목록이 포함됩니다. migration 이전 legacy row의 actor는 JSON `null`입니다.

### `GET /api/v1/etl-profiles`

Streamlit이 웹 ETL 실행 화면에서 사용할 수 있는 ETL 프로필 목록을 서버 allowlist 기준으로 반환합니다. 서버 파일 경로는 노출하지 않고 `id`, `display_name`만 반환합니다.

```json
{
  "items": [
    {"id": "sample_fashion_vendor_v1", "display_name": "패션 공급사 샘플"},
    {"id": "sample_marketplace_vendor_v1", "display_name": "마켓플레이스 공급사 샘플"}
  ]
}
```

### `POST /api/v1/etl-loads`

공급사 CSV와 `profile_id`를 받아 웹에서 바로 ETL을 실행하고 PostgreSQL staging에 적재합니다. `profile_id`는 위 목록 API가 반환하는 값 중 하나만 허용하며, 임의 파일 경로는 받지 않습니다.

- 요청 형식: `multipart/form-data`
- 파일 필드명: `file`, 프로필 필드명: `profile_id`
- 정상 응답: `etl_load_run_id`, `created`, `profile_name`, `profile_version`, `source_filename`, `total_rows`, `loaded_rows`, `rejected_rows`, `error_counts`, `actor_username`(요청한 JWT `current_user`의 username)
- 지원하지 않는 `profile_id`: HTTP `400` (`unsupported_profile`)
- 빈 파일, 크기 초과, ETL 변환 실패 등 잘못된 업로드: HTTP `400` (`invalid_upload`)

동일한 `input_file_sha256`·`profile_name`·`profile_version` 조합으로 다시 요청하면 새 배치를 만들지 않고 기존 배치를 `created: false`로 반환합니다. 내부적으로는 CLI의 `etl.cli`·`etl.load_cli`가 호출하는 `run_pipeline()`·`load_standard_csv()`를 그대로 실행합니다.

### `POST /api/v1/etl-loads/s3`

파일 업로드 대신 서버에 설정된 S3 bucket에서 공급사 CSV를 읽어 같은 웹 ETL 흐름을 실행합니다. 요청 본문은 `profile_id`와 `object_key`만 받습니다.

```json
{
  "profile_id": "sample_fashion_vendor_v1",
  "object_key": "incoming/catalogguard/e2e/sample_vendor_valid.csv"
}
```

bucket과 허용 prefix는 요청이 아니라 서버 환경변수 `CATALOGGUARD_ETL_S3_BUCKET`·`CATALOGGUARD_ETL_S3_PREFIX`로만 정합니다. 호출자는 bucket을 고를 수 없고, prefix 밖 `object_key`는 S3를 호출하기 전에 차단합니다. 객체는 HeadObject로 크기를 먼저 확인한 뒤 업로드와 동일한 상한까지만 읽습니다. 내려받은 bytes는 업로드 경로와 같은 `run_web_etl()`에 전달하므로 `run_pipeline()`·`load_standard_csv()`와 중복 방지·Actor Audit 동작이 모두 같습니다.

응답 형식은 `POST /api/v1/etl-loads`와 동일하며, 오류는 다음과 같이 매핑합니다.

| 상황 | HTTP | code |
|---|---:|---|
| 허용 prefix 밖 `object_key` | `400` | `s3_key_not_allowed` |
| 파일명·크기 등 업로드 검증 실패 | `400` | `invalid_upload` |
| S3가 객체 없음을 알린 경우 | `404` | `s3_object_not_found` |
| S3 읽기 실패(권한 거부 포함) | `502` | `s3_read_failed` |
| 서버에 bucket 미설정 | `503` | `s3_not_configured` |

AWS 자격증명은 요청이나 환경변수로 받지 않고 boto3 기본 credential chain을 사용하므로, EC2에서는 Instance Role이 그대로 적용됩니다.

### `GET /api/v1/etl-loads`

PostgreSQL staging에 저장된 ETL 적재 배치 목록을 조회합니다. 목록 응답에는 응답 크기가 큰 SHA-256과 상품 목록을 포함하지 않습니다.

| Query | 기본값 | 조건과 의미 |
|---|---:|---|
| `limit` | `20` | `1` 이상 `100` 이하 |
| `offset` | `0` | 앞에서 건너뛸 배치 수, `0` 이상 |
| `filename` | 없음 | 별도 길이 제한 없는 원본 파일명의 대소문자 구분 없는 부분 검색 |
| `profile_name` | 없음 | 별도 길이 제한 없는 프로필 이름의 대소문자 구분 없는 부분 검색 |

검색어의 앞뒤 공백은 제거하고 공백뿐인 값은 필터에서 제외합니다. `filename`과 `profile_name`을 함께 보내면 두 조건을 모두 만족하는 배치만 반환합니다. `%`, `_`, `\`는 SQL wildcard가 아니라 실제 문자로 검색하며, 목록과 `total`에는 같은 필터를 적용합니다. 정렬은 최신 적재가 먼저 오도록 `created_at DESC`, 같은 시각에는 `id DESC`입니다.

### `GET /api/v1/etl-loads/{etl_load_run_id}`

적재 배치의 메타데이터와 해당 배치에 속한 staging 상품을 조회합니다. 목록에는 전체 행·정상 적재 행·변환 거부 행을 포함하고, 상세에는 여기에 오류 코드별 발생 건수와 원본·출력 파일 SHA-256을 추가합니다. 품질 요약 기능 도입 전 배치는 품질 필드를 `null`로 반환합니다.

| Query | 기본값 | 조건과 의미 |
|---|---:|---|
| `product_limit` | `50` | `1` 이상 `100` 이하 |
| `product_offset` | `0` | 앞에서 건너뛸 상품 수, `0` 이상 |

상품은 staging 상품 `id` 오름차순이며, DB 쿼리의 `LIMIT`·`OFFSET`으로 페이지를 나눕니다. 다른 배치의 상품은 포함하지 않고, 존재하지 않는 `etl_load_run_id`는 HTTP `404`를 반환합니다. 상세 구현과 검색 규칙은 [ETL MVP 문서](docs/etl_mvp.md)를 참고하세요.

`etl_load_run_id`는 `1` 이상의 정수만 허용하며 `0`, 음수와 숫자가 아닌 값은 HTTP `422`를 반환합니다.

### `POST /api/v1/etl-loads/{etl_load_run_id}/promotion-preview`

선택한 ETL batch와 현재 운영 상품을 비교하는 미리보기입니다. DB의 운영 상품을 변경하지 않고 `insert`, `update`, `unchanged` 건수, 상품별 `before_data`·`after_data`, 변경 필드, `promotion_eligible`, `blocked_reasons`, `preview_hash`를 반환합니다. 품질 summary 누락, reject 행 존재, 빈 staging batch, 중복 상품 식별자, 검수 오류가 있으면 반영을 차단합니다.

### `POST /api/v1/etl-loads/{etl_load_run_id}/promotions`

미리보기 확인 후 운영 상품을 반영합니다. 요청에는 `confirmation: true`와 미리보기 응답의 64자리 소문자 SHA-256 `expected_preview_hash`가 필요합니다.

```json
{
  "confirmation": true,
  "expected_preview_hash": "preview 응답의 SHA-256 hash"
}
```

서버는 transaction 안에서 batch·staging·현재 운영 상품을 잠그고 preview를 다시 계산합니다. hash가 달라지면 `preview_stale`, 반영 조건이 맞지 않으면 `promotion_blocked`로 `409`를 반환하며 운영 상품을 변경하지 않습니다. 성공 시 운영 상품 insert/update와 `catalog_promotion_runs`의 `succeeded` 기록(요청한 JWT `current_user` 기준 `actor_user_id`·`actor_username` 포함), `catalog_product_changes` append-only audit을 함께 저장합니다. 같은 ETL batch의 성공 반영은 partial unique index와 잠금으로 한 번만 허용하고, 경쟁 요청의 실패는 내부 SQL 오류를 노출하지 않는 안전한 메시지로 변환합니다. promotion이 실패해도(예: 예외) `failed` run에 같은 방식으로 actor를 기록해 누가 시도했는지는 남습니다.

### `POST /api/v1/catalog-promotions/{promotion_run_id}/rollback-preview`

succeeded promotion run 하나를 되돌릴 수 있는지 확인하는 미리보기입니다. DB를 변경하지 않고 `rollback_eligible`, `blocked_reasons`, `restore_count`, `delete_count`, `conflict_count`, `preview_hash`와 상품별 `rollback_action`(`delete`/`restore`)·`current_data`·`restore_data`·`conflict` 목록을 반환합니다. 존재하지 않는 `promotion_run_id`는 HTTP `404`입니다.

### `POST /api/v1/catalog-promotions/{promotion_run_id}/rollback`

미리보기 확인 후 실제로 되돌립니다. 요청에는 `confirmation: true`와 미리보기 응답의 64자리 소문자 SHA-256 `expected_preview_hash`가 필요합니다.

```json
{
  "confirmation": true,
  "expected_preview_hash": "rollback preview 응답의 SHA-256 hash"
}
```

서버는 transaction 안에서 대상 promotion run과 관련 상품을 다시 잠그고 rollback preview를 다시 계산합니다. hash가 달라지면 `preview_stale`, 그 사이에 상품이 다시 바뀌었거나 반영 조건이 맞지 않으면 `rollback_conflict`/`rollback_not_eligible`로 `409`를 반환하며 운영 상품을 변경하지 않습니다. 이미 같은 promotion run이 성공적으로 rollback된 경우에도 `409`(`already_rolled_back`)로 차단합니다. 성공 시 INSERT promotion 상품은 삭제하고 UPDATE promotion 상품은 이전 상태로 복원하며, `catalog_promotion_rollbacks`의 `succeeded` 기록(요청한 JWT `current_user` 기준 `actor_user_id`·`actor_username` 포함)과 `catalog_promotion_rollback_changes` append-only audit을 함께 저장합니다. 원본 `catalog_product_changes` audit은 상품이 삭제되어도 삭제하지 않습니다.

### `GET /api/v1/catalog-promotion-rollbacks`

저장된 rollback 실행 이력을 최신순으로 조회합니다. 상태 filter와 `limit`/`offset` pagination을 지원하며, 항목마다 `rollback_run_id`, `target_promotion_run_id`, `status`, `restored_count`, `deleted_count`, `conflict_count`, `failure_code`, `safe_failure_message`, 실행 시각과 `actor_username`을 반환합니다.

### `GET /api/v1/catalog-promotion-rollbacks/{rollback_run_id}`

단일 rollback 실행 상세입니다. 목록 항목과 같은 필드에 `preview_hash`, `preview_schema_version`을 더해 반환하며, 존재하지 않는 ID는 HTTP `404`입니다.

### `GET /api/v1/catalog-promotion-rollbacks/{rollback_run_id}/changes`

해당 rollback 실행이 상품별로 만든 change audit입니다. run 단위 count가 "몇 건을 되돌렸는지"만 알려주는 데 비해, 이 API는 어떤 상품이 어떤 원본 promotion audit을 되돌린 것인지, `delete`인지 `restore`인지, 어떤 필드가 어떤 값에서 어떤 값으로 바뀌었는지까지 보여줍니다. 항목은 `rollback_change_id`, `rollback_run_id`, `original_audit_id`, `catalog_product_id`, `action`, `changed_fields`, `before_data`, `after_data`, `created_at`이며 `created_at DESC, id DESC`로 정렬하고 `limit`(기본 `20`, 최대 `100`)·`offset`으로 나눕니다.

존재하지 않는 `rollback_run_id`는 HTTP `404`이지만, rollback 실행이 존재하고 change가 0건이면 `404`가 아니라 `200`과 빈 `items`를 반환합니다. 상품을 전혀 바꾸지 않은 `blocked`·`failed` 실행은 change가 0건인 것이 정상이기 때문입니다.

## 19. 검수 이력 검색과 전체 요약 CSV 다운로드

검수 이력 목록 API와 Streamlit 검수 이력 탭은 파일명, 날짜, 검수 상태 검색을 지원합니다.

- `filename` 검색어는 앞뒤 공백을 제거합니다.
- 공백뿐인 검색어는 검색 조건 없이 전체 목록을 조회합니다.
- 최대 길이는 `100`자입니다.
- 대소문자를 구분하지 않는 부분 검색입니다.
- 파일명 앞, 중간, 뒤 어디에 검색어가 있어도 찾습니다.
- `%`, `_`, `\` 문자는 SQL wildcard가 아니라 일반 문자로 검색되도록 이스케이프합니다.
- 정렬은 `created_at DESC`, `id DESC`입니다.
- `total`과 `items`에는 같은 검색 조건이 적용됩니다.
- `start_date`와 `end_date`는 한국 시간 기준 날짜 범위로 검색합니다.
- `status`는 `error`, `warning`, `normal` 중 하나이며, 오류는 `error_count > 0`, 주의는 `error_count == 0 and warning_count > 0`, 정상은 `error_count == 0 and warning_count == 0` 기준입니다.
- Streamlit에서 검색 버튼을 누르면 `offset`이 `0`으로 초기화됩니다.
- 상세 화면에서 목록으로 돌아오면 검색 조건과 현재 페이지 offset은 유지됩니다.
- 전체 요약 CSV 다운로드는 현재 페이지 offset을 바꾸지 않고, 검색 버튼으로 실제 적용된 조건만 사용합니다.
- 전체 요약 CSV는 `CSV 다운로드 준비` 버튼을 누를 때만 전체 조회를 실행하고, 준비된 결과를 세션에 저장한 뒤 다운로드 버튼을 표시합니다.
- API 최대 `limit=100`에 맞춰 100건씩 반복 조회하므로 검색 결과가 100건을 초과해도 전체 이력이 CSV에 포함됩니다.
- 검색 결과가 0건이면 전체 요약 CSV 다운로드 버튼을 표시하지 않고 다운로드할 이력이 없다는 안내를 보여줍니다.

예시는 다음과 같습니다.

```powershell
curl.exe "http://127.0.0.1:8001/api/v1/inspections?limit=10&offset=0&filename=products"
```

## 20. 동일 CSV 중복 저장 방지

동일 CSV 중복 저장 방지는 파일명보다 CSV bytes를 기준으로 판단합니다. FastAPI 서버가 업로드된 CSV bytes로 SHA-256 해시를 직접 계산하므로 클라이언트가 보낸 해시를 신뢰하지 않습니다.

`inspection_runs`에 저장되는 identity 컬럼은 다음과 같습니다.

| 컬럼 | 타입 | 설명 |
|---|---|---|
| `file_sha256` | `String(64)`, nullable | CSV bytes의 SHA-256 hex 문자열입니다. migration 이전 기존 이력은 NULL입니다. |
| `inspection_version` | `String(20)`, nullable 아님 | 검수 규칙 버전입니다. 현재 `INSPECTION_VERSION` 값은 `"10"`입니다. DB `server_default`는 없습니다. |

중복 판단 기준은 같은 `file_sha256`과 같은 `inspection_version`입니다.

- 파일명이 달라도 CSV bytes와 검수 버전이 같으면 같은 파일로 봅니다.
- 파일명이 같아도 CSV bytes가 다르면 새로운 이력으로 저장합니다.
- 같은 CSV라도 검수 규칙 버전이 달라지면 다시 검수하고 새 이력으로 저장할 수 있습니다.

상품 그룹 내 중복 색상·사이즈 옵션 규칙을 추가할 때 검수 버전을 `"3"`으로 올렸고, 상품 그룹 카테고리 일관성 규칙을 추가하면서 `"4"`로 올렸습니다. 선택적 `sale_price`와 정상가·할인가 관계 규칙을 추가하면서 `"5"`로 올렸습니다. 상품 그룹 사이즈 체계 일관성 규칙을 추가하면서 `"6"`으로 올렸습니다. `SHOES`와 `BAG`를 공식 허용 카테고리로 확장하면서 `"7"`로 올렸습니다. 카테고리별 가격 이상치 비교가 기존 카테고리 별칭 정규화를 재사용하도록 통일하면서 `"8"`로 올렸습니다. 같은 CSV라도 카테고리 표기가 섞여 있으면 가격 그룹이 합쳐져 `가격 이상치` 결과가 달라질 수 있으므로, 기존 검수 결과를 그대로 재사용하지 않기 위한 것입니다. 카테고리별 필수 패션 속성 정책을 추가해 `BAG`의 `size`를 선택 값으로 바꾸면서 `"9"`로 올렸습니다. 버전 8까지 `필수 값 누락` 오류가 발생하던 빈 `size`의 `BAG` 상품이 버전 9에서는 정상 처리되므로, 같은 CSV를 다시 올렸을 때 버전 8 결과를 재사용해 새 정책이 적용되지 않는 일을 막기 위한 것입니다. `size`가 선택 값인 카테고리의 빈 `size`도 완전 중복 비교에 포함하면서 `"10"`으로 올렸습니다. 버전 9까지 완전 중복 검사에서 빠지던 빈 `size`의 `BAG` 상품이 버전 10에서는 `완전 중복 상품` 오류로 표시되므로, 같은 CSV가 버전 9 결과를 재사용해 새 검사 범위가 적용되지 않는 일을 막기 위한 것입니다. `BAG`처럼 `size`가 선택 값인 canonical 카테고리의 빈 `size`를 `상품 옵션 조합 중복` 비교에도 포함하면서 `"11"`로 올렸습니다. 버전 10까지 아무 오류도 만들지 않던 "같은 그룹·같은 색상·빈 `size`이면서 완전 중복은 아닌" 상품이 버전 11에서는 `상품 옵션 조합 중복` 오류로 표시되므로, 같은 CSV가 버전 10 결과를 재사용하지 않도록 한 것입니다. 사이즈·색상 별칭 비교에서 값 안쪽의 연속 공백을 정리하도록 보강하면서 `"12"`로 올렸습니다. 버전 11까지 `free  size`처럼 별칭에 공백이 더 들어간 값은 표준값을 찾지 못해 `상품 옵션 조합 중복`과 `사이즈 표기 비표준` 검사에서 모두 빠졌지만 버전 12에서는 `free size`와 같은 값으로 비교되므로, 같은 CSV가 버전 11 결과를 재사용하지 않도록 한 것입니다. 이번에 별칭 조회에서 공백뿐 아니라 하이픈(`-`)과 언더스코어(`_`) 차이도 무시하도록 확장하면서 현재 `INSPECTION_VERSION`을 `"13"`으로 올렸습니다. 버전 12까지 `free-size`·`free_size`·`extra_large`처럼 등록된 별칭의 구분자만 다른 값은 표준값을 찾지 못해 아무 오류도 만들지 않았지만 버전 13에서는 기존 별칭과 같은 값으로 비교되므로, 같은 CSV가 버전 12 결과를 재사용하지 않도록 한 것입니다. 별칭 사전 자체는 바뀌지 않았고 `/`와 `.`는 계속 구분자로 취급하지 않습니다. 같은 CSV라도 새 검수 기준으로 다시 검사할 수 있도록 inspection identity에 사용하는 규칙 버전을 올린 것이며, 동일 CSV라도 버전 6, 버전 7, 버전 8은 별도 검수 결과로 저장할 수 있습니다. 버전 6에서 `카테고리 오류`가 발생하던 canonical `SHOES`·`BAG` 상품이 버전 7에서는 정상 카테고리로 처리되고, 같은 이유로 완전 중복 검사 대상에도 포함되므로 같은 CSV의 결과가 달라질 수 있습니다. 파일 해시와 검수 버전을 함께 사용하는 기존 중복 저장 방지 기준은 그대로 유지됩니다. DB 스키마 변경은 없어 이 기능을 위한 Alembic migration은 추가하지 않았으며, 과거 이력과 기존 migration의 `"1"` backfill 값은 그대로 유지합니다.

PostgreSQL에는 다음 partial unique index가 있습니다.

```text
ux_inspection_runs_file_sha256_inspection_version
columns: file_sha256, inspection_version
where: file_sha256 IS NOT NULL
```

이 index의 의미는 다음과 같습니다.

- 기존 `file_sha256=NULL` 행은 여러 개 존재할 수 있습니다.
- migration 이후 저장되는 같은 파일과 같은 검수 버전은 한 건만 허용합니다.
- 동시에 같은 파일 저장 요청이 들어와도 DB에서 최종 차단합니다.
- 같은 파일이라도 `inspection_version`이 다르면 새 저장이 가능합니다.

추가 CHECK constraint도 있습니다.

- `file_sha256`이 NULL이 아니면 길이가 정확히 64여야 합니다.
- `inspection_version`은 빈 문자열이나 공백만 있는 문자열일 수 없습니다.

기존 migration 이전 이력은 `inspection_version="1"`로 채워지지만 `file_sha256`은 NULL입니다. 과거 원본 CSV bytes가 DB에 없으므로 해시 재생성이 불가능하고, 신규 CSV 저장 시 과거 이력과 자동으로 중복 비교되지는 않습니다. 따라서 migration 이후 같은 CSV를 처음 저장할 때는 새로운 실행 ID가 한 번 생성될 수 있습니다. 그 다음부터는 Streamlit이나 브라우저를 재시작해도 기존 실행 ID가 반환됩니다.

개발 DB에서 수동 확인한 예로, `products_dev.csv`를 최초 저장했을 때 실행 ID `6`이 생성되었고 Streamlit 재시작 후 같은 CSV를 다시 저장하자 새 실행 ID를 만들지 않고 기존 실행 ID `6`을 반환했습니다. 이 숫자는 해당 개발 DB에서의 예시일 뿐 고정된 시스템 값은 아닙니다.

## 21. 검수 결과와 CSV 다운로드 형식

검수 결과 화면과 다운로드 CSV는 다음 컬럼을 사용합니다.

```text
검수 상태, 오류 항목, 상품 그룹 ID, 상품 ID, 오류 이유, 수정 권장사항, 위험 수준
```

Streamlit CSV 검수 탭에서는 다음 필터를 적용할 수 있습니다.

- 검수 상태: `전체`, `오류`, `주의`
- 오류 항목: 전체 또는 발견된 오류 항목
- 상품 ID 검색: 대소문자 구분 없는 부분 검색

CSV 다운로드 동작은 다음과 같습니다.

- 현재 필터 결과만 CSV로 다운로드합니다.
- 다운로드 CSV는 Windows Excel에서 한글이 깨지지 않도록 UTF-8 BOM으로 생성합니다.
- DataFrame index는 CSV에 포함하지 않습니다.
- `=`, `+`, `-`, `@`로 시작하는 문자열은 CSV 수식 삽입을 막기 위해 앞에 작은따옴표를 붙입니다.
- 업로드 파일이 `products_dev.csv`이면 기본 결과 파일명은 `products_dev_validation_results.csv`입니다.
- 파일명에 Windows 예약 문자가 있으면 `_`로 바꿉니다.
- 검수 이력 상세 CSV 파일명은 `inspection_<실행ID>_<원본파일명>_results.csv` 형식입니다.
- 상세 결과가 없는 검수 실행은 상세 CSV 다운로드 버튼을 표시하지 않습니다.

검수 이력 전체 요약 CSV 다운로드는 현재 검색 조건에 맞는 모든 이력의 요약을 내려받습니다.

- 파일명 예시는 `inspection_history_20260707_153000.csv`입니다.
- CSV 인코딩은 Windows Excel 호환을 위해 UTF-8-SIG입니다.
- CSV 컬럼은 `실행 ID`, `파일명`, `검수 시간`, `전체 상품`, `전체 문제`, `오류`, `주의`, `검수 상태`입니다.
- `검수 상태`는 숫자가 아니라 `오류`, `주의`, `정상` 한글 값으로 표시합니다.
- 전체 조회 중 API 연결 실패, timeout, 서버 오류, 잘못된 응답 형식이 발생하면 일부 데이터만 담은 CSV는 제공하지 않습니다.

## 22. 샘플 데이터 검수 결과

`data/dev/products_dev.csv`를 현재 코드로 검수하면 다음 결과가 나옵니다.

```text
전체 상품 수: 5
전체 문제 수: 6
오류 수: 6
주의 수: 0
```

API로 확인하려면 FastAPI 서버를 실행한 뒤 아래 명령을 사용합니다.

```powershell
curl.exe -X POST "http://127.0.0.1:8001/api/v1/inspections" `
  -H "accept: application/json" `
  -F "file=@data/dev/products_dev.csv;type=text/csv"
```

### 패션 색상·사이즈 검수 예시

다음 상품은 알려진 별칭인 `블랙`과 `medium`을 사용합니다.

```csv
product_group_id,product_id,product_name,category,color,size,stock,price,image_path
G001,P001,오버핏 반팔 티셔츠,TOP,블랙,medium,10,19900,image.jpg
```

색상 검수 결과는 다음과 같습니다.

```text
검수 상태: 주의
오류 항목: 색상 표기 비표준
오류 이유: 색상 '블랙'은 표준값 'BLACK'으로 통일하는 것이 좋습니다.
수정 권장사항: 오류 이유에 표시된 표준 색상값으로 수정하세요.
위험 수준: 낮음
```

사이즈 검수 결과는 다음과 같습니다.

```text
검수 상태: 주의
오류 항목: 사이즈 표기 비표준
오류 이유: 사이즈 'medium'은 표준값 'M'으로 통일하는 것이 좋습니다.
수정 권장사항: 오류 이유에 표시된 표준 사이즈값으로 수정하세요.
위험 수준: 낮음
```

### 상품 그룹 내 중복 옵션 검수 예시

다음 두 행은 원본 표기는 다르지만 비교 키가 모두 `BLACK / M`입니다.

```csv
product_group_id,product_id,product_name,category,color,size,stock,price,image_path
G001,P001,기본 반팔 티셔츠 A,TOP,BLACK,M,10,19900,image1.jpg
G001,P002,기본 반팔 티셔츠 B,TOP,black,medium,10,19900,image2.jpg
```

두 상품 모두 다음 오류 결과에 연결됩니다.

```text
검수 상태: 오류
오류 항목: 상품 옵션 조합 중복
오류 이유: 상품 그룹 'G001'에서 색상 'BLACK', 사이즈 'M' 조합이 상품 ID 'P001', 'P002'에 중복되어 있습니다.
수정 권장사항: 같은 상품 그룹 안에서 색상과 사이즈 조합이 한 번만 사용되도록 중복 상품을 통합하거나 옵션 값을 수정하세요.
위험 수준: 중간
```

검수 후에도 P002의 원본 `color=black`, `size=medium` 값은 그대로 유지됩니다.

### 상품 그룹 내 사이즈 체계 일관성 검수 예시

다음 상품 그룹은 문자형 사이즈와 숫자형 사이즈를 함께 사용합니다.

```csv
product_group_id,product_id,product_name,category,color,size,stock,price,image_path
G001,P001,베이직 셔츠,TOP,BLACK,medium,10,29900,image1.jpg
G001,P002,베이직 셔츠,TOP,NAVY,L,10,29900,image2.jpg
G001,P003,베이직 셔츠,TOP,WHITE,100,10,29900,image3.jpg
```

세 상품 모두 다음 주의 결과에 연결됩니다.

```text
검수 상태: 주의
오류 항목: 상품 그룹 사이즈 체계 불일치
오류 이유: 상품 그룹 'G001'에서 문자형 사이즈와 숫자형 사이즈가 함께 사용되고 있습니다.
수정 권장사항: 같은 상품의 사이즈 옵션이 동일한 사이즈 체계를 사용하는지 확인하세요.
위험 수준: 중간
```

P001의 `medium`은 기존 사이즈 표기 표준화 규칙에도 해당하므로 `사이즈 표기 비표준` 주의가 함께 한 번 표시됩니다. 두 규칙은 보는 대상이 다르며 서로를 대체하지 않습니다.

같은 그룹에 `FREE`나 `custom size` 상품이 있어도 그 상품에는 사이즈 체계 주의를 붙이지 않습니다.

## 23. 테스트 실행 방법

DB가 필요 없는 단위 테스트와 API 테스트는 일반 환경에서 실행할 수 있습니다.

```powershell
cd C:\study\catalogguard-lite
.\.venv\Scripts\Activate.ps1
python -m pytest tests/test_api_health.py -q
python -m pytest tests/test_api_logging.py -q
python -m pytest tests/test_api_inspections.py -q
python -m pytest tests/test_catalogguard_api_client.py -q
python -m pytest tests/test_app_history_helpers.py -q
python -m pytest tests/test_app_history_download_helpers.py -q
python -m pytest tests/test_app_inspection_save_helpers.py -q
python -m pytest tests/test_security.py tests/test_auth_service.py tests/test_create_user_cli.py -q
python -m pytest tests/test_api_auth.py tests/test_ui_auth.py -q
```

요청 ID 전달 관련 테스트는 다음 명령으로 한 번에 실행합니다.

```powershell
python -m pytest tests/test_catalogguard_api_client.py tests/test_app_history_helpers.py tests/test_app_smoke.py -q
```

PostgreSQL 통합 테스트를 포함하려면 `TEST_DATABASE_URL`을 설정하고 테스트 DB에 마이그레이션을 적용합니다.

```powershell
$env:TEST_DATABASE_URL="postgresql+psycopg://catalogguard_test_user:CHANGE_ME@localhost:5432/catalogguard_lite_test"
$env:DATABASE_URL=$env:TEST_DATABASE_URL
python -m alembic upgrade head
python -m pytest tests/test_inspection_persistence.py -q
python -m pytest tests/test_api_rbac.py tests/test_api_inspections_transaction_regression.py -q
python -m pytest tests/test_actor_audit.py -q
python -m pytest tests/test_inspection_actor_migration.py -q
```

전체 테스트는 다음 명령으로 실행합니다.

```powershell
python -m pytest -q
```

### Authentication/RBAC와 sync inspection transaction 테스트

`tests/test_security.py`는 bcrypt 비밀번호 hash·검증과 JWT 발급·검증(만료, 잘못된 서명, 형식 오류)을 확인합니다. `tests/test_auth_service.py`, `tests/test_create_user_cli.py`는 `users` 조회·로그인 인증·계정 생성 CLI를 실제 PostgreSQL로 검증합니다. `tests/test_api_auth.py`는 로그인·현재 사용자 API 계약을, `tests/test_api_rbac.py`는 실제 PostgreSQL 사용자·JWT로 401(인증 실패)과 403(권한 부족) 경계를 endpoint 단위로 검증합니다. `tests/test_ui_auth.py`는 Streamlit 로그인·로그아웃·역할별 버튼 제한을 AppTest로 검증합니다.

`tests/test_api_inspections_transaction_regression.py`는 `find_existing_inspection_run`·`save_inspection_report`를 monkeypatch하지 않고 실제 PostgreSQL Session으로 `POST /api/v1/inspections`를 검증하는 regression test입니다. 신규 CSV 저장 후 새 Session으로 재조회해 commit과 JWT actor를 확인하고, 동일 CSV를 다른 operator가 재요청해도 기존 run과 최초 actor를 재사용하는지, 위조한 multipart actor 값을 무시하는지, 사용자 삭제 후 `actor_user_id=NULL`·`actor_username` snapshot 보존이 동작하는지 확인합니다. 저장 도중 강제 실패가 발생하면 `inspection_runs`·`inspection_results`가 모두 rollback되는지와 anonymous(401)·viewer(403)·operator(성공)의 권한 경계도 함께 확인합니다.

`tests/test_actor_audit.py`는 Web ETL·Promotion·Rollback 각각에서 `actor_user_id`·`actor_username`이 인증된 JWT `current_user`로부터 기록되는지 실제 PostgreSQL로 검증하는 10개 시나리오입니다. JWT actor 기록(신규 Session으로 재조회해 commit 확인), viewer 요청 차단(403)과 run 미생성(세 endpoint 모두), Web ETL의 anonymous 요청 차단(401)과 run 미생성, request body에 `actor_username`을 함께 보내도 무시되고 토큰의 사용자로만 기록되는지(actor 위조 방지), Promotion 저장 중 강제 실패 시에도 `failed` run에 actor가 정확히 기록되고 운영 상품은 생성되지 않는지(false success 방지), migration 이전 legacy row(actor 컬럼 `NULL`)를 안전하게 조회할 수 있는지를 확인합니다.

### Inspection Actor Audit 검증

격리된 로컬 PostgreSQL 18.4 클러스터에서 `20260810_0012` upgrade·schema/FK inspection·`20260808_0011` downgrade·재-upgrade를 확인했습니다. Sync actor, actor 위조 방지, dedup 최초 actor 보존, 사용자 삭제 후 FK `NULL`과 username snapshot 보존을 실제 PostgreSQL row로 검증했습니다. Async 경로는 Redis state·legacy payload·InspectionJobService·Celery Worker·Async API를 검증하고, 로컬 Redis 7.4·Celery·FastAPI E2E에서 동일 CSV 두 번 실행 후 `inspection_runs` 1건과 최초 actor가 남는 것을 확인했습니다.

Rollback Change Audit 기능 완료 commit `abcea748e299009b4889b0daa98ad4c9c97e770b`을 대상으로 한 GitHub Actions run `31487868946`에서는 `test`·`browser-e2e`·`terraform-validate`·`kubernetes-smoke` 4개 job이 모두 성공했습니다. 이 run의 `test` job 결과는 다음과 같습니다. 운영 DB나 AWS/RDS가 아니라 일회성 PostgreSQL·Redis 서비스 컨테이너에서 실행한 결과입니다.

```text
1451 passed
0 failed
0 skipped
4 deselected
warnings 0
```

Chromium Browser E2E는 이 수치에 포함되지 않습니다. `pytest.ini`의 `-m "not e2e"`로 제외되어 별도 `browser-e2e` job에서 실행합니다.

이 문서 단계에서는 Python source·migration·test를 변경하지 않았으므로 전체 suite를 다시 실행하지 않았고, 위 수치는 해당 run에서 확인한 결과를 그대로 기록했습니다.

### Prometheus Metrics 테스트

`tests/test_metrics.py`는 32개 시나리오로 구성됩니다. `CATALOGGUARD_METRICS_ENABLED` true/false 계열 값 parsing, `/metrics` 비활성 시 404와 instrumentation no-op(counter가 실제로 증가하지 않음), 활성 시 Prometheus text 형식 응답, HTTP 요청 counter·duration histogram 증가, `/api/v1/catalog-promotions/{id}`류 동적 ID 요청이 route template 하나로만 집계되고 원본 경로가 별도 label로 남지 않는지, 매칭되지 않는 임의 경로가 고정 `unmatched` label로만 집계되는지, `/health`·`/ready`·`/metrics` 요청이 HTTP metric에서 제외되는지, unhandled exception이 기존 안전한 500 응답·요청 ID·로그를 그대로 유지하면서 `5xx` metric도 증가시키는지, `/metrics` 응답 본문에 사용자명·요청 ID·동적 ID가 노출되지 않는지를 확인합니다. Web ETL 쪽은 신규 실행(created)·동일 배치 재사용(duplicate, rows 재집계 없음)·4가지 실패 예외 각각(failed, rows 증가 없음)을 확인하고, 마지막 시나리오는 실제 PostgreSQL로 로그인 후 같은 CSV를 두 번 요청해 신규 1회·중복 1회·행 수가 정확히 한 번만 집계되는지 검증합니다. counter 값은 테스트 실행 순서에 의존하지 않도록 매 테스트에서 요청 전후 값의 차이(delta)로만 비교합니다.

### PostgreSQL persistence 포함 검증 결과

promotion과 rollback 기능은 운영 DB나 Railway DB에 연결하지 않고 저장소의 테스트 PostgreSQL 환경에서 검증했습니다. 문서에는 실행별 전체 테스트 수를 추측해 기록하지 않으며, 아래 수치는 Terraform 기능 검증 commit(`38385f0`)의 GitHub Actions run `31160915277`에서 실제로 확인된 결과입니다. pytest 수치 자체는 Kubernetes·Terraform 작업이 Python 코드를 변경하지 않아 직전 Observability 검증 commit과 동일합니다.

```text
promotion preview·service·API·client·UI·concurrency 테스트 파일과 Playwright Chromium promotion E2E를 포함한 검증 범위를 확인
rollback preview·service·API 계약과 PostgreSQL 통합 테스트 파일을 포함한 검증 범위를 확인
Alembic history/heads: `20260806_0010` 단일 head 확인
promotion PostgreSQL transaction·partial unique index·audit·stale/중복 경쟁 조건 확인
rollback PostgreSQL INSERT 삭제·UPDATE 복원·conflict 차단·중복 rollback 차단·transaction 원자성·원본 audit 보존 확인
Chromium promotion E2E: preview·승인 전 버튼 비활성화·실제 반영·성공/중복 메시지·PostgreSQL 최종 상태 확인. 로그인 후 operator 권한으로 실행
Authentication/RBAC: 401/403 경계, viewer/operator 권한 분리, sync inspection PostgreSQL transaction regression을 실제 PostgreSQL로 확인
Actor Audit: Web ETL·Promotion·Rollback의 JWT actor 기록, viewer 403(세 endpoint)과 Web ETL anonymous 401의 run 미생성, actor 위조 방지, Promotion 실패 시 failed run actor 기록, legacy row(actor NULL) 안전 조회를 tests/test_actor_audit.py 10개 시나리오로 실제 PostgreSQL 확인
Prometheus Metrics: HTTP metric·Web ETL metric·cardinality 방지·민감정보 미노출·실제 PostgreSQL 신규/중복 ETL 집계를 tests/test_metrics.py 32개 시나리오로 확인(이번 run에서 로컬 skip 없이 전체 실행)
Kubernetes smoke: kind 실제 cluster에서 PostgreSQL rollout·Alembic Migration Job condition=complete·FastAPI rollout·Service를 통한 GET /health·GET /ready HTTP 200을 kubernetes-smoke job으로 확인(pytest 범위 밖, 별도 job)
Terraform validate: terraform fmt·init·validate와 mock provider terraform test `2 passed, 0 failed`를 terraform-validate job으로 확인(pytest 범위 밖, 별도 job. apply 미수행)
Run tests: `1309 passed`, `0 skipped`, `4 deselected`, `0 failed`
```

promotion preview의 응답 schema와 hash 형식, blocked reason, insert/update/unchanged 계산, confirmation 요구, stale preview, 안전한 오류 mapping, Streamlit 상태 초기화와 중복 제출 방지를 테스트했습니다. promotion E2E는 브라우저 성공 메시지에 의존하지 않고 `catalog_products`, `catalog_promotion_runs`, `catalog_product_changes`의 PostgreSQL 최종 상태와 `applying` 잔존 여부까지 확인합니다. rollback은 서비스·API 계층의 PostgreSQL 통합 테스트에 더해, 조회 계층(query service·API·client)과 Streamlit History/Detail/Change Audit AppTest, 실제 Chromium Browser E2E까지 검증합니다.

### 실제 브라우저 ETL E2E

실제 Chromium 브라우저 E2E는 ETL reject fixture와 promotion fixture를 각각 `etl.cli`·`etl.load_cli`로 처리하고 테스트 PostgreSQL에 적재한 뒤, runner가 FastAPI와 Streamlit을 직접 시작합니다. Authentication 도입 후에는 두 시나리오 모두 시작 시 `browser_e2e_operator` 계정을 `scripts/create_user.py`로 생성하고, Streamlit 로그인 폼에서 실제 로그인한 뒤 기존 흐름을 이어갑니다. promotion 시나리오는 `ETL 적재 이력` 탭에서 파일명·프로필명으로 batch를 검색하고, 실제 combobox 선택, preview, 변경 전·후 표, 승인 checkbox, 반영 버튼 상태, promotion 성공 또는 중복 메시지를 확인합니다. 이후 테스트 코드가 PostgreSQL의 succeeded run 1건, 운영 상품 insert/update, audit 존재, applying run 0건을 직접 확인합니다. 같은 시나리오는 이어서 Promotion 실행 이력·상품 변경 Audit, Rollback Preview·승인·실행, reload 없이 갱신되는 Rollback 실행 이력, Rollback 실행 상세, 그리고 `상품 Rollback 변경 Audit` 화면까지 진행합니다. Change Audit 영역에서는 표 컬럼(`원본 Audit ID`·`외부 상품 ID`·`변경 유형`·`변경 필드`·`변경 전`·`변경 후`), `상품 삭제` 표시, delete의 `삭제됨` 표시, 실제 변경 필드와 fixture 상품 표시, 전체 change 건수 caption과 pagination 버튼 비활성화를 확인하고, PostgreSQL에서는 rollback change 2건이 모두 `delete`인지, `original_audit_id` 집합이 원본 `catalog_product_changes.id` 집합과 일치하는지, 되돌린 뒤 운영 상품이 0건인지를 함께 확인합니다. reject 시나리오는 별도로 마스킹과 raw 민감정보 미노출, console/page error 0건을 확인합니다. 이 E2E는 로그인·ETL 검색·promotion·rollback 화면을 다루며, 웹 ETL CSV 업로드 화면 자체를 실제 브라우저에서 검증하는 전용 시나리오는 아직 없습니다. 웹 ETL selectbox를 추가할 때 이 검색 필드와 accessible label(`공급사 프로필`)이 겹쳐 기존 E2E의 `get_by_label()`이 strict-mode violation으로 실패한 적이 있으며, selectbox label을 `ETL 실행 프로필`로 분리해 해결했습니다. 로그인 폼의 `아이디`·`비밀번호` label도 기존 UI label과 겹치지 않도록 새로 붙였습니다.

일반 테스트의 `pytest==9.1.1`과 browser plugin의 `pytest<9` 제약을 섞지 않도록 E2E는 전용 가상환경에 설치하는 방식을 권장합니다.

```powershell
python -m venv .venv-e2e
.\.venv-e2e\Scripts\Activate.ps1
python -m pip install --upgrade pip
python -m pip install -r requirements-e2e.txt
python -m playwright install chromium
```

```powershell
$env:DATABASE_URL = "postgresql+psycopg://postgres:postgres@127.0.0.1:5432/catalogguard_lite_test"
python .\scripts\run_etl_browser_e2e.py
```

runner는 로컬 loopback 테스트 DB만 허용하고, 실패 시 `artifacts/browser-e2e/`에 screenshot·HTML·FastAPI/Streamlit/Playwright 로그를 남긴 뒤 시작한 프로세스만 종료합니다. GitHub Actions의 `browser-e2e` job은 별도 PostgreSQL service와 Chromium을 사용하며 실패 artifact를 업로드합니다.

`requirements-e2e.txt`는 `pytest-playwright==0.7.0`의 `pytest>=6.2.4,<9.0.0` 호환 범위에 맞춰 browser E2E용 `pytest==8.4.1`을 사용합니다. 일반 unit·integration suite와 GitHub Actions `test` job의 `pytest==9.1.1`과는 서로 다른 의존성 환경이며, 두 pin을 임의로 하나로 통합하지 않습니다.

### 동기 검수 성능 측정

`scripts/benchmark_inspection.py`는 합성 CSV를 사용해 동기 검수 1회와 같은 입력을 연속 2회 검수하는 경우의 중앙 실행 시간과 Python 추적 메모리를 비교합니다. 기본 설정은 행 수 `100, 1,000, 5,000, 10,000`, 워밍업 1회, 반복 3회이며, 결과는 `tests/test_benchmark_inspection.py`로 검증합니다.

측정 환경은 Python 3.11.9, Windows 10.0.26200, Intel Core i7-14700F 기반의 개발 PC입니다.

개발 PC에서 측정한 대표 결과는 다음과 같습니다.

| 행 수 | 입력 크기 | 문제 수 | 1회 중앙값 | 연속 2회 중앙값 | Python peak |
|---:|---:|---:|---:|---:|---:|
| 100 | 0.016 MiB | 15 | 0.009544초 | 0.018815초 | 0.177 MiB |
| 1,000 | 0.156 MiB | 149 | 0.074266초 | 0.150817초 | 1.603 MiB |
| 5,000 | 0.781 MiB | 757 | 0.371740초 | 0.867245초 | 6.485 MiB |
| 10,000 | 1.563 MiB | 1,507 | 0.875495초 | 1.645721초 | 12.939 MiB |

측정상 시간과 Python 추적 메모리는 행 수에 따라 대체로 선형으로 증가했고, 같은 검수를 두 번 수행하면 1회 대비 약 1.88~2.33배가 걸렸습니다. 10,000행 1회 검수는 개발 PC에서 약 0.88초였습니다. 이 결과는 동기 검수 중복 제거를 우선한 근거이며, AWS나 대규모 트래픽 성능을 보증하는 수치는 아닙니다. `tracemalloc`은 Python이 추적한 메모리만 포함하므로 Pandas/C 확장과 OS 전체 프로세스 메모리는 포함하지 않을 수 있습니다.

재현 명령:

```powershell
python scripts/benchmark_inspection.py --rows 100 1000 5000 10000 --repeat 3 --warmup 1 --output artifacts/inspection_benchmark.json
```

측정 환경은 로컬 개발 PC이며 DB·네트워크 시간, 실제 동시 접속과 운영 트래픽은 포함하지 않습니다. 이 측정은 Streamlit과 FastAPI의 이중 검수를 제거하는 근거로 사용했습니다. 현재 비동기 경로는 Redis/Celery로 요청 수명과 검수 작업을 분리하지만, 대규모 트래픽 성능을 입증하는 자료로 해석하지 않습니다.

### GitHub Actions 자동 테스트

`.github/workflows/test.yml`의 `Test` workflow는 `main` 브랜치 push와 `main` 브랜치를 대상으로 한 pull request에서 실행됩니다. 일반 `test` job은 Python 3.11, PostgreSQL 18·Redis 7.4, Alembic, E2E 제외 pytest, 실제 Celery Worker·FastAPI·비동기 CSV 검수 E2E와 Streamlit startup smoke를 실행합니다. 또한 `Dockerfile.aws` image build, `api`·`services`·`workers`와 Celery task import, 실행 UID `10001`, PostgreSQL migration, 기본 CMD의 Uvicorn 시작과 `/health` HTTP `200`을 검증합니다. 이 AWS 검증은 GitHub Actions Ubuntu의 Docker packaging/runtime smoke이며 실제 AWS 배포는 수행하지 않습니다. 별도 `browser-e2e` job은 PostgreSQL 18 service와 Playwright Chromium을 준비하고 `scripts/run_etl_browser_e2e.py`로 ETL CLI·Loader·FastAPI·Streamlit·실제 브라우저 흐름을 검증하며, 실패 시에만 browser artifact를 업로드합니다. 세 번째 `kubernetes-smoke` job은 고정 버전 kind/kubectl로 실제 Kubernetes cluster를 만들고, 같은 `Dockerfile.aws` image를 `k8s/` manifest로 배포해 PostgreSQL rollout·Alembic Migration Job·FastAPI rollout·`/health`·`/ready`까지 검증합니다(자세한 흐름은 16장 참고). 이 job도 실패 시에만 `kubectl get/describe/logs` 기반 진단 정보를 출력하며 Secret 값은 출력하지 않습니다. 네 번째 `terraform-validate` job은 고정 버전 Terraform `1.15.8`로 `terraform/`의 `fmt -check -recursive`·`init -backend=false`·`validate`·mock provider `test`를 실행합니다. 실제 AWS 자격 증명을 사용하지 않고 `terraform apply`·`destroy`·`import`도 수행하지 않으므로 AWS 리소스와 비용이 발생하지 않습니다(자세한 흐름은 16장 참고).

`test`와 `browser-e2e` job 모두 `CATALOGGUARD_JWT_SECRET`을 `ci-test-only-jwt-secret-do-not-use-in-production` 같은 CI 전용 값으로 설정하며 운영 secret과 공유하지 않습니다. `test` job은 비동기 E2E 실행 전 `scripts/create_user.py`로 synthetic operator 계정을 만들고, `browser-e2e` job은 Chromium 실행 전 `browser_e2e_operator` 계정을 만들어 로그인 후 기존 흐름을 검증합니다.

```text
main push 또는 main 대상 pull request
-> GitHub Actions Test workflow
-> PostgreSQL 18·Redis 7.4 서비스 컨테이너
-> Python 3.11과 의존성 설치
-> Alembic upgrade head
-> Dockerfile.aws image build
-> AWS image import smoke와 실행 UID 10001 확인
-> PostgreSQL migration과 Dockerfile.aws 기본 CMD(Uvicorn) 시작
-> AWS runtime container의 /health HTTP 200 확인
-> E2E 제외 전체 pytest 1회 실행
-> Celery Worker와 FastAPI 프로세스 시작
-> /health·/ready 확인
-> 비동기 CSV 제출, 상태 polling, 결과·중복 재사용·임시 파일 정리 E2E 확인
-> 실패 시 FastAPI·Celery 로그 출력 및 프로세스 정리
-> Streamlit 서버 시작
-> /_stcore/health 응답 확인
-> Streamlit 프로세스 종료
```

서비스 컨테이너는 workflow가 실행되는 동안만 사용하는 일회성 PostgreSQL·Redis CI 테스트 구성입니다. Railway나 운영 PostgreSQL·Redis에 연결하지 않으며, E2E를 제외한 단위 테스트와 실제 PostgreSQL 연결·저장 통합 테스트를 함께 실행합니다.

비동기 E2E 테스트는 기본 `pytest`에서 `e2e` marker로 제외하고, workflow에서만 다음 명령으로 명시 실행합니다. 이 검사는 테스트용 PostgreSQL·Redis, FastAPI, Celery Worker가 모두 준비된 환경을 요구하며 운영 Redis·Celery 배포 검증과는 구분됩니다. Authentication 도입 후에는 FastAPI가 준비된 뒤 synthetic operator 계정으로 로그인해 발급받은 JWT Access Token으로 `POST /api/v1/inspection-jobs`를 호출합니다.

```bash
python -m pytest -m e2e tests/e2e/test_async_inspection_ci.py -q
```

Streamlit 시작 스모크 테스트는 `python -m streamlit run app.py`로 실제 서버를 `127.0.0.1:8501`에서 실행하고, 최대 30초 동안 `/_stcore/health`를 반복 확인합니다. 각 요청에는 1초의 연결 제한과 2초의 전체 제한을 적용합니다. HTTP `200`을 받은 뒤에도 2초 동안 프로세스가 살아 있는지 확인하므로, Streamlit 실행 명령이 성공하고 서버 Health endpoint가 응답하는 시작 단계를 검사합니다.

성공과 실패 경로 모두 `trap cleanup EXIT`로 프로세스를 정리합니다. 먼저 SIGTERM을 보낸 뒤 최대 5초 동안 기다리고, 종료되지 않으면 SIGKILL을 보낸 다음 `wait`로 프로세스를 회수합니다. 실패 시에는 마지막 `curl` 종료 코드, HTTP 상태, 응답 본문, 오류와 Streamlit 시작 로그를 출력해 원인을 확인할 수 있게 합니다.

이 Step에서는 `CATALOGGUARD_API_BASE_URL`, `CATALOGGUARD_API_TIMEOUT_SECONDS`, `DATABASE_URL`, `TEST_DATABASE_URL`을 빈 값으로 덮어씁니다. 따라서 Railway 운영 API나 운영 PostgreSQL에 연결하거나 운영 데이터와 검수 이력을 읽고 저장하지 않고, Streamlit 서버 자체가 시작되는지만 확인합니다. 환경변수의 실제 값과 Secret은 workflow 로그나 문서에 기록하지 않습니다.

`tests/test_app_smoke.py`의 AppTest는 `app.py`의 초기 화면이 예외 없이 렌더링되고 API 주소가 없을 때 안전한 안내가 표시되는지 확인합니다. 또한 6행 카테고리 일관성 CSV를 실제 업로드해 요약 수치, 원본 미리보기, 참여 상품별 한글 결과, 상태·규칙·상품 ID 필터와 결과 CSV 다운로드 생성을 확인합니다. GitHub Actions의 시작 스모크 테스트는 실제 Streamlit 서버 프로세스, 포트와 Health 응답을 확인하므로 두 검사는 서로 다른 범위를 보완합니다.

AppTest는 실제 `app.py` 실행 경로의 CSV 업로드와 검수·필터 위젯을 검증하지만 실제 브라우저의 파일 선택 창이나 픽셀 렌더링까지 자동화하지는 않습니다. GitHub Actions 스모크 테스트도 Railway API 실제 통신, 운영 Secrets 설정, Streamlit Community Cloud 전용 장애나 모든 Segmentation fault를 검증하지 않습니다.

Terraform 기능 검증 commit(`38385f0`)의 GitHub Actions run `31160915277`은 `test`·`browser-e2e`·`kubernetes-smoke`·`terraform-validate` job 모두 성공했습니다. Actions 실행별 전체 테스트 수는 이 문서에 추측해 고정하지 않으며, 위 "PostgreSQL persistence 포함 검증 결과"에 적은 수치는 이 run에서 실제로 확인한 값입니다. AWS Docker runtime smoke(image build·import·UID `10001`·migration·Uvicorn 시작·`/health` HTTP `200`)에서 `prometheus-client`가 `requirements-api.txt`를 통해 `Dockerfile.aws` image에도 정상 설치·import됨을 확인했습니다. `kubernetes-smoke` job 로그에서 `kind v0.32.0`, `kubectl` client `v1.36.2`, node `kindest/node:v1.36.1`(SHA-256 digest 고정)로 실제 cluster가 만들어졌고, `deployment "postgres" successfully rolled out`, `job.batch/catalogguard-migrate condition met`, `deployment "catalogguard-api" successfully rolled out`, `GET /health -> {"status":"ok","service":"catalogguard-lite-api"}`, `GET /ready -> {"status":"ready","service":"catalogguard-lite-api","database":"ok"}`를 확인했습니다. `terraform-validate` job 로그에서는 `Installed hashicorp/aws v6.55.0`, `Success! The configuration is valid.`와 mock provider `terraform test`의 `Success! 2 passed, 0 failed.`를 확인했습니다. promotion E2E와 Streamlit startup smoke의 실제 검증 범위는 위 테스트·workflow 설명을 따릅니다. Actions의 일회성 서비스 컨테이너·kind cluster는 운영 DB·Redis와 분리되며, kind cluster는 job 종료 시 삭제됩니다.

## 24. 데이터 저장 범위와 보안

PostgreSQL에는 검수 실행 요약·상세 결과, ETL staging 배치·정상 상품 행, 운영 상품 persistence·promotion 감사 이력을 저장합니다. ETL staging은 운영 상품 테이블이 아니라 적재 결과를 확인하기 위한 별도 영역입니다.

저장하는 값은 다음과 같습니다.

- 업로드 파일의 파일명
- SHA-256 파일 해시
- 검수 규칙 버전
- 전체 상품 수
- 전체 문제 수
- 오류 수
- 주의 수
- 검수 실행자의 `actor_user_id`와 실행 당시 `actor_username` snapshot
- 검수 실행 생성 시각
- 상세 결과의 상품 그룹 ID
- 상세 결과의 상품 ID
- 검수 상태
- 오류 항목
- 오류 이유
- 수정 권장사항
- 위험 수준

ETL staging에는 다음 값을 저장합니다.

- `etl_load_runs`의 원본 파일명, 프로필 이름·버전, 입력·출력 SHA-256, 적재 행 수·품질 요약, 생성 시각
- `catalog_products_staging`의 표준 CSV 정상 행과 `etl_load_run_id`
- 빈 `sale_price`는 `NULL`로 저장하며 `stock`, `price`, `sale_price` 음수는 DB CHECK constraint로 거부

ETL 적재는 summary의 필수 필드, 실제 표준 CSV·reject CSV SHA-256, 실제 행 수와 reject CSV의 구조를 확인한 뒤 배치·정상 상품·reject 행을 하나의 트랜잭션으로 저장합니다. `(input_file_sha256, profile_name, profile_version)` unique index로 중복을 판단하며, 실패 시 전체 rollback합니다. reject 원본 값은 마스킹된 문자열만 `etl_rejected_rows`에 저장하고 raw CSV와 개인정보 원문은 저장하지 않습니다.

운영 상품 persistence에는 `catalog_products`의 공급사·외부 상품 ID, 표준 상품 필드와 마지막 ETL 출처, `catalog_promotion_runs`의 상태·count·preview 메타데이터, `catalog_product_changes`의 action·변경 JSONB·전후 값, `catalog_promotion_rollbacks`의 rollback 실행 상태·count·preview 메타데이터, `catalog_promotion_rollback_changes`의 상품별 delete/restore 변경 JSONB를 저장합니다. 승인된 promotion transaction이 운영 상품과 run·audit을 함께 저장하며, 감사 이력은 append-only 제약과 FK RESTRICT로 보호합니다. 다만 `catalog_product_changes`와 `catalog_promotion_rollback_changes`의 `catalog_product_id`에는 FK를 두지 않아, INSERT promotion을 rollback해 상품이 실제로 삭제되어도 두 감사 이력은 삭제되지 않고 남습니다. `GET /api/v1/catalog-promotions`, `GET /api/v1/catalog-promotions/{promotion_run_id}`, `GET /api/v1/catalog-promotions/{promotion_run_id}/audits`로 promotion 실행 이력과 상품별 변경 audit을 조회할 수 있고, `GET /api/v1/catalog-promotion-rollbacks`, `GET /api/v1/catalog-promotion-rollbacks/{rollback_run_id}`, `GET /api/v1/catalog-promotion-rollbacks/{rollback_run_id}/changes`로 rollback 실행 이력과 상품별 delete/restore change audit을 조회할 수 있습니다.

저장하지 않는 값은 다음과 같습니다.

- 원본 CSV 파일 bytes
- 원본 CSV 전체 내용
- 상품 설명 원문 전체
- 판매자 정보 원문 전체
- 이메일 원문
- 전화번호 원문
- 주민등록번호 형태 원문
- 이미지 파일

개인정보 의심 값은 검수 결과 메시지에 마스킹된 형태로 들어갑니다. 예를 들어 `demo.user@example.com`, `010-1234-5678`, `900101-1234567` 같은 값은 API 응답과 DB 저장 결과에서 각각 `de*******@example.com`, `010-****-5678`, `900101-*******`처럼 표시됩니다.

SHA-256 해시는 파일 동일성 확인용입니다. 해시만으로 원본 CSV를 복원할 수 없으며, 원본 CSV bytes나 전체 원문은 DB에 저장하지 않습니다.

파일명 저장 시 경로가 들어와도 파일명만 남깁니다. 파일명이 비어 있으면 `uploaded.csv`를 사용하고, 최대 `255`자로 제한합니다.

API 클라이언트는 연결 실패, timeout, 서버 오류를 사용자용 메시지로 바꾸며 내부 URL이나 서버 응답 본문을 그대로 노출하지 않도록 테스트되어 있습니다.

`users` 테이블에는 `username`, `password_hash`(bcrypt hash), `role`, `is_active`, `created_at`만 저장합니다. 비밀번호 원문은 저장하지 않으며, bcrypt hash는 복호화가 아니라 매 로그인마다 재계산해 비교하는 단방향 함수입니다. JWT Access Token의 payload도 `sub`(username), `role`, `iat`, `exp`만 포함하고 `password_hash` 등 민감정보는 넣지 않습니다.

Authentication은 "누가 실행할 수 있는지"를 통제하는 기능입니다. `inspection_runs`, `etl_load_runs`, `catalog_promotion_runs`, `catalog_promotion_rollbacks` 실행 이력 테이블에는 "누가 실행했는지"를 기록하는 `actor_user_id`(`users.id` FK, `ON DELETE SET NULL`)·`actor_username`(snapshot) 컬럼이 있습니다. 이 값은 요청을 처리한 JWT `current_user`에서만 채워지며, request body나 form으로 클라이언트가 다른 사용자 이름을 지정할 수 없습니다. migration 이전 기존 row는 두 값 모두 `NULL`로 유지합니다.

## 25. 현재 한계

- MVP 단계의 규칙 기반 검사이므로 실제 운영 정책에 맞춘 금지어와 개인정보 탐지 조정이 필요합니다.
- 개인정보 탐지는 정규식 기반이므로 오탐과 미탐 가능성이 있습니다.
- 허용 카테고리는 현재 `TOP`, `BOTTOM`, `OUTER`, `SHOES`, `BAG` 5개이며, `ACCESSORY` 같은 그 밖의 값은 아직 지원하지 않습니다.
- 카테고리는 계층 없는 평면 목록이며 상위·하위 카테고리 관계를 다루지 않습니다.
- 공식 입력은 대문자 canonical 값만 허용합니다. `shoes`, `신발`, `bag`, `가방` 같은 표기를 정식 입력값으로 받아들이지는 않습니다.
- 카테고리별 필수 패션 속성 정책은 `size`에만 적용됩니다. `BAG`은 `size`가 선택 값이라 빈 사이즈도 허용하고 `TOP`·`BOTTOM`·`OUTER`·`SHOES`는 필수 값으로 검사하지만, 색상이나 이미지 경로처럼 다른 필드를 카테고리별로 다르게 적용하는 기능은 없습니다. 가방의 "별도 사이즈 없음"은 빈 `size`와 `FREE` 어느 쪽으로도 입력할 수 있으며, 두 값은 서로 다른 값이므로 한쪽으로 통일하도록 강제하지 않습니다.
- 카테고리와 사이즈를 직접 연결해 판정하지 않습니다. `270`을 신발 사이즈로 자동 인정하거나 카테고리별 사이즈 범위를 검증하지 않습니다.
- 공급사 ETL 변환 단계에서는 category 값을 사전 검증하거나 거부하지 않습니다. 카테고리 문제는 검수 단계에서 확인합니다.
- 패션 색상·사이즈 검수는 별칭 사전의 정확 일치만 지원하며 오타 유사도는 검사하지 않습니다. 따라서 `FREEE`, `MEDUM`처럼 오타로 보이는 값도 사전에 없으면 미판정으로 남고 경고가 나오지 않습니다. 사전에 없는 실제 사이즈를 잘못 교정하지 않기 위해 감수한 선택입니다.
- 사용자 정의·복합 색상과 숫자 사이즈는 비표준 표기 경고 대상으로 판단하지 않습니다.
- 중복 옵션 조합을 자동 병합하거나 중복 상품을 자동 삭제하지 않습니다.
- 누락된 색상·사이즈 옵션 조합을 추론하지 않습니다.
- 중복 옵션별 재고를 합산하지 않습니다.
- 상품명과 상품 그룹의 일치 여부를 판단하지 않습니다.
- 사이즈 체계 일관성 검수는 ALPHA와 NUMERIC만 구분합니다. FREE 계열과 `1호`, `M-L` 같은 사용자 정의·범위 표기는 체계 판정에서 제외하므로, 이런 값이 섞인 혼재는 탐지하지 않습니다.
- 숫자 사이즈로 카테고리를 추정하지 않으며 카테고리별 허용 사이즈 범위는 구현되어 있지 않습니다.
- KR·US·UK·EU 사이즈 변환과 성별·브랜드별 사이즈 차트는 구현되어 있지 않습니다.
- 사이즈 체계가 혼재해도 어느 쪽이 정답인지 자동으로 선택하거나 사이즈 값을 자동 수정하지 않습니다.
- 사이즈 체계 일관성 검수는 CSV 검수(Inspection) 규칙이며, 공급사 ETL의 변환 reject 조건에는 적용되지 않습니다.
- 그룹에서 정답 category를 자동 선택하거나 category 값을 자동 수정하지 않습니다.
- 상품명에서 그룹의 category를 자동 추론하지 않습니다.
- category 계층 관계를 비교하거나 상품 그룹을 자동 분리하지 않습니다.
- 카테고리별 가격 이상치는 같은 카테고리의 유효 가격이 5개 이상일 때만 계산됩니다.
- migration 이전 기존 이력은 `file_sha256=NULL`이라 과거 이력까지 소급해 중복 판단할 수 없습니다.
- `INSPECTION_VERSION`은 검수 규칙이 변경될 때 개발자가 직접 올려야 합니다.
- 공개 Streamlit 앱에서는 FastAPI와 PostgreSQL 연동 상태에 따라 검수 이력 기능을 사용할 수 없을 수 있습니다.
- Refresh Token은 없으며 Access Token이 만료되면 다시 로그인해야 합니다.
- 회원가입 API, 비밀번호 찾기/재설정 기능은 없습니다. 계정은 `scripts/create_user.py` bootstrap CLI로만 만듭니다.
- OAuth, MFA, SSO 연동은 없습니다.
- 로그인 시도 rate limit이나 brute-force 방어는 구현되어 있지 않습니다.
- 역할은 `viewer`·`operator` 2개만 있으며, 세밀한 permission 단위 ACL이나 관리자 전용 화면은 없습니다.
- Inspection Actor Audit은 `inspection_runs` row를 최초 생성한 사용자만 기록합니다. 동일 CSV·검수 버전의 dedup 요청자를 별도 event로 모두 저장하지는 않습니다.
- Async job status 응답에는 actor를 노출하지 않습니다. 완료 후 `inspection_run_id`로 검수 상세를 조회하면 `actor_username`을 확인할 수 있습니다.
- `TEST_DATABASE_URL`과 `DATABASE_URL`이 모두 없는 환경에서 anonymous Sync Inspection 요청은 auth보다 DB dependency가 먼저 평가되어 401 대신 500이 될 수 있습니다. 테스트 DB가 정상 설정된 환경에서는 401을 반환하며, 이 기존 dependency-order 결함은 Inspection Actor Audit의 blocker가 아닙니다.
- Rollback 실행의 `actor_username`은 실행 직후 POST 응답과 `GET /api/v1/catalog-promotion-rollbacks` 이력 조회에서 확인할 수 있습니다. 실행자 기준으로 검색·필터하는 기능은 없습니다.
- Prometheus metric은 애플리케이션이 값을 노출하는 instrumentation 단계이며, 이를 주기적으로 수집하는 Prometheus 서버나 Grafana 대시보드는 아직 구축하지 않았습니다.
- metric은 process-global 메모리 상태이므로 프로세스가 재시작되면 초기화됩니다. DB 실행 이력(영구)·Actor Audit(DB 이력의 실행자 기록)과는 별개 개념입니다.
- metric registry가 프로세스 하나 안에서만 유지되므로, 여러 Uvicorn worker를 띄우는 환경에서는 worker별로 값이 나뉘며 이번 MVP는 이를 통합하지 않습니다.
- Async Inspection/Celery, Redis queue depth, Promotion·Rollback 실행, Actor Audit, DB connection pool 관련 domain metric은 아직 없습니다.
- Kubernetes 배포는 kind 기반 CI/local smoke 검증까지이며, 실제 EKS/GKE/AKS 등 production 클러스터에는 배포하지 않았습니다.
- Kubernetes에는 FastAPI·PostgreSQL만 배포했습니다. Redis/Celery Async Inspection과 Streamlit은 Kubernetes에 배포하지 않았습니다.
- Kubernetes Service는 ClusterIP만 사용하며 Ingress·TLS·외부 노출은 없습니다. `replicas: 1` 고정이며 HorizontalPodAutoscaler·PodDisruptionBudget도 없습니다.
- Kubernetes의 dev PostgreSQL은 PersistentVolume이 없는 CI 전용 disposable 구성이며, kind cluster를 삭제하면 데이터도 함께 사라집니다. NetworkPolicy와 세분화된 ServiceAccount도 없습니다.
- Kubernetes manifest의 resource requests/limits는 CI/개발용 초기값이며 실측 production sizing이 아닙니다.
- Terraform은 코드화와 fmt·validate·mock provider test까지이며, 실제 `terraform apply`·`destroy`를 실행하지 않았습니다. 따라서 이 코드로 만들어진 AWS 리소스는 없습니다.
- 2026-07-19에 콘솔로 만든 기존 EC2·RDS는 Terraform으로 import하지 않았으므로 Terraform state와 실제 AWS 상태가 연결되어 있지 않습니다.
- Terraform backend를 구성하지 않았습니다. S3 remote state와 state locking(DynamoDB 등)은 없으며, `init`도 `-backend=false`로만 실행합니다.
- Terraform은 기존 Default VPC·subnet을 조회해 사용하며, custom VPC와 private subnet 기반 네트워크를 새로 구성하지 않습니다.
- Terraform으로 Kubernetes/EKS 리소스를 만들지 않으며, production(Railway) 환경도 Terraform으로 관리하지 않습니다.
- `terraform test`는 mock provider 기반이므로 계산된 설정값만 검증합니다. 실제 AWS API 응답, 계정 quota, IAM 권한 부족 같은 문제는 이 test로 확인할 수 없습니다.
- mock provider는 코드에서 설정하지 않은 속성에도 임의 값을 채우므로, EC2에 `key_name`을 지정하지 않았다는 사실은 test가 아니라 코드 리뷰로 확인합니다.
- Terraform 코드의 IMDSv2 강제와 루트 볼륨 암호화는 수동 구성에 없던 값이며, apply하지 않았으므로 실제 인스턴스에는 반영되어 있지 않습니다.
- 저장된 검수 이력 삭제 기능은 구현되어 있지 않습니다.
- 전체 요약 CSV는 목록 API를 반복 조회하므로 다운로드 중 DB 내용이 바뀌는 상황의 완전한 스냅샷 보장은 별도 트랜잭션/내보내기 API가 필요합니다.
- 실제 외부 공급사 운영 데이터와 연동하지 않았습니다.
- 웹 ETL은 업로드부터 staging 적재까지 하나의 동기 HTTP 요청으로 처리하며, 비동기(Celery) 처리는 아직 없습니다.
- 웹 ETL은 한 번에 CSV 파일 1개만 업로드할 수 있으며, 여러 파일 동시 업로드는 지원하지 않습니다.
- 웹 ETL은 CSV만 지원하며 Excel/XLSX 업로드는 지원하지 않습니다.
- 웹 ETL의 ETL 프로필은 서버 allowlist(`config/etl/*.json`)로 고정되어 있으며, 사용자가 새 프로필을 업로드하거나 만드는 기능은 없습니다. 프로필 상세는 조회만 가능합니다.
- 이미 ETL 실행에 사용한 `profile_version`의 매핑을 그대로 두고 수정하는 것을 막는 장치는 아직 없습니다. `etl_load_runs`는 `profile_name`·`profile_version`만 기록하고 프로필 JSON snapshot이나 매핑 hash는 저장하지 않으므로, 어떤 버전을 썼는지는 알 수 있지만 그 버전의 당시 내용이 보존된다고 DB가 보장하지는 않습니다. 버전 증가 기준과 향후 방향은 [ETL Profile Version Lifecycle Policy](docs/etl_profile_lifecycle.md)에 정리했습니다.
- Web ETL CSV 업로드 자체를 대상으로 하는 전용 Chromium Browser E2E는 아직 없습니다. 웹 ETL 핵심 로직은 API·Client·PostgreSQL 통합 테스트와 Streamlit AppTest로 검증합니다.
- S3 ingestion은 호출자가 `object_key` 하나를 지정하는 pull 방식입니다. S3 event 알림·Lambda·SQS 기반 자동 수집과 prefix 일괄 처리는 지원하지 않습니다.
- S3 source를 실제로 호출하는 Streamlit 화면은 없습니다. 현재는 API 직접 호출로만 사용합니다.
- EC2 Role에 `s3:ListBucket`을 부여하지 않았으므로, 허용 prefix 안에 없는 key는 `404 s3_object_not_found`가 아니라 `502 s3_read_failed`로 응답합니다. 최소권한을 유지하기 위한 의도된 선택입니다.
- AWS staging의 S3 bucket과 EC2 Role의 S3 read policy는 Console·CLI로 구성했으며 Terraform으로 관리하지 않습니다.
- AWS staging S3 E2E는 합성 fixture 1건 기준 수동 검증이며, GitHub Actions에서 자동으로 재실행되지 않습니다.
- Streamlit ETL 적재 이력 화면은 배치·staging 상품 조회는 읽기 전용으로 유지하면서, 선택한 batch에 대해 promotion preview와 승인된 운영 상품 반영을 FastAPI API로 요청합니다. staging 상품 직접 수정·삭제는 지원하지 않습니다.
- staging 상품을 수정·삭제하는 API는 구현되어 있지 않습니다.
- promotion은 품질 summary·reject·검수 오류·중복 identity가 없는 선택 batch만 대상으로 하며, 실제 외부 공급사 운영 데이터와 production catalog 반영은 검증하지 않았습니다.
- 일부 rollback 실행 오류 코드(`already_rolled_back` 등)는 API client에서 전용 예외가 아닌 일반 오류로 처리됩니다. 전용 예외는 `preview_stale`과 조회 계열 `404`뿐입니다.
- Rollback Change Audit 조회는 `limit`/`offset` pagination만 제공하며, action·상품·기간 filter나 검색·export는 지원하지 않습니다.
- Rollback Browser E2E fixture는 INSERT promotion 2건을 되돌리는 delete-only 시나리오입니다. `restore` change의 화면 표시는 Streamlit AppTest와 service·API 테스트로만 확인했습니다.
- 여러 promotion을 한 번에 되돌리는 일괄 rollback은 지원하지 않습니다.
- 임의 시점으로 되돌리는 point-in-time recovery는 지원하지 않으며, rollback은 하나의 succeeded promotion run 단위로만 동작합니다.
- reject 행은 `etl_rejected_rows`에 구조화된 오류와 마스킹된 원본으로 저장하며, 자동 공급사 감지는 지원하지 않습니다.
- 증분 ETL과 streaming을 지원하지 않습니다.
- 운영 DB 적재는 검증하지 않았고, PostgreSQL 적재는 임시 테스트 환경에서만 검증했습니다.
- `.env` 자동 로딩은 구현되어 있지 않으므로 로컬에서는 PowerShell 환경변수를 직접 설정해야 합니다.

## 26. 향후 개선 방향

- 운영 정책에 맞는 금지어, 개인정보, 카테고리 규칙 확장
- 검수 규칙 변경 시 `inspection_version` 관리 정책 수립
- 과거 이력 backfill 정책 검토
- 검수 이력 삭제와 보관 정책
- dedup 요청자를 포함한 요청 단위 감사 event가 필요할 경우 별도 audit event 모델 검토
- Rollback 실행 이력만 목록으로 조회하는 전용 GET API
- Prometheus 서버 구축과 scrape 설정, Grafana 대시보드
- 여러 Uvicorn worker 환경을 위한 metric 통합(현재는 프로세스 단일 registry)
- Async Inspection/Celery, Redis queue depth, Promotion·Rollback, Actor Audit, DB connection pool domain metric 추가
- Redis/Celery, Streamlit의 Kubernetes 배포
- Kubernetes Ingress/TLS, HorizontalPodAutoscaler, PodDisruptionBudget, NetworkPolicy
- 실제 EKS/GKE/AKS 등 production Kubernetes 배포와 managed PostgreSQL(RDS 등) 연동
- Terraform S3 remote state와 state locking 구성
- 기존 수동 생성 AWS staging 리소스의 Terraform import와 실제 `apply` 기반 재현
- custom VPC·private subnet 기반 네트워크 구성의 Terraform 코드화
- Refresh Token, 회원가입, password reset, OAuth/MFA/SSO, 로그인 rate limit
- 중복 저장 이벤트 로그 또는 감사 기록 검토
- 기간별 검수 추세와 파일 간 비교 통계 추가
- 대용량 CSV 처리 성능 개선
- 카테고리와 가격 이상치 기준을 설정 파일이나 관리 화면에서 조정
- 상품 그룹 내 상품명 일관성 검수
- 카테고리별 사이즈 형식 검수
- 브랜드 표준화
- `gender` 선택 컬럼과 표준화
- 웹 ETL 처리 시간이 길어질 경우의 비동기(Celery) 실행
- 웹 ETL 다중 파일 업로드와 XLSX 등 추가 입력 형식 지원
- 공개된 `profile_version`의 매핑이 조용히 수정되는 것을 막는 immutable version guardrail(Profile CRUD보다 먼저 적용)
- 사용자 정의 ETL 프로필 등록·관리(Profile CRUD)
- Web ETL CSV 업로드 전용 Browser E2E
- 실제 운영 공급사·production catalog 연동과 배포 환경 promotion 검증
- 증분 ETL과 대용량 streaming 처리
- Async worker(`workers/inspection_tasks.py`)의 세션 트랜잭션 경계 정리(현재는 `session.rollback()`으로 사전 조회를 분리하며, sync 경로와 다른 방식)

## 27. 개발 시 주의사항

- 원본 CSV 파일과 원문 개인정보를 DB에 저장하지 않는 현재 원칙을 유지합니다.
- 검수 결과 컬럼을 바꾸면 `core/presentation.py`, `api/routes/inspections.py`, `db/persistence_service.py`, `app.py`의 상세 CSV 변환 로직과 관련 테스트를 함께 확인합니다.
- DB 모델을 바꾸면 SQLAlchemy 모델과 Alembic 마이그레이션을 함께 수정합니다.
- 검수 규칙을 바꿔 같은 CSV도 다시 검수해야 하는 경우 `config/settings.py`의 `INSPECTION_VERSION`을 함께 올립니다.
- `inspection_version`에는 DB `server_default`를 두지 않고 애플리케이션에서 명시적으로 저장합니다.
- `DATABASE_URL`, `TEST_DATABASE_URL`, `CATALOGGUARD_JWT_SECRET` 같은 비밀번호·secret 포함 환경변수는 저장소에 커밋하지 않습니다.
- 같은 요청 안에서 다른 목적의 SQLAlchemy Session이 필요하면(예: 쓰기 트랜잭션을 시작하기 전의 빠른 조회) `Depends(get_session)`을 재사용해 같은 Session을 공유하지 말고, `Depends(get_session, use_cache=False)`로 독립된 Session을 받습니다. 같은 Session에서 SELECT가 먼저 실행되면 SQLAlchemy가 트랜잭션을 암묵적으로 시작(autobegin)시켜, 이후 Service가 여는 `with session.begin()`과 충돌합니다(`api/routes/inspections.py`의 `precheck_session` 참고).
- `requirements.txt`와 `requirements-api.txt`의 역할이 나뉘어 있으므로 로컬 전체 시스템에서는 두 파일을 모두 설치합니다.
- 파일명 검색을 수정할 때는 `%`, `_`, `\`가 일반 문자처럼 검색되는지 확인합니다.
- Streamlit 세션 중복 방지와 DB 수준 중복 방지는 역할이 다르므로 둘 다 유지합니다.
- 문서에 새 기능을 추가하기 전에는 실제 코드와 테스트가 먼저 구현되어 있는지 확인합니다.
## SQL 쿼리·인덱스 성능 분석

PostgreSQL 18의 격리 테스트 DB에서 검수 실행 10,000건과 상세 결과 100,000건을 생성하고 동일 CSV, 이력 목록·count, 상세 조회를 `EXPLAIN ANALYZE BUFFERS`로 측정했습니다. 기존 인덱스가 핵심 조회에 사용되었고 새 후보 인덱스의 실질 이득이 확인되지 않아 migration과 Repository 쿼리는 변경하지 않았습니다.

재현 가능한 opt-in 성능 테스트와 실행 계획, 후보 인덱스를 기각한 근거는 [SQL 성능 분석 문서](docs/sql_performance_analysis.md)에 정리했습니다. 기본 pytest에서는 성능 테스트를 제외하며, 전용 test/perf DB에서만 다음과 같이 실행합니다.

```powershell
$env:RUN_SQL_PERFORMANCE="1"
python -m pytest -m performance tests/performance/test_inspection_query_performance.py -s -q
```

## 공급사 CSV ETL MVP

## Airflow Foundation과 configured HTTP feed staging

`airflow/`는 CatalogGuard 애플리케이션과 분리된 Airflow 3.3.0 / Python 3.11
runtime이다. 자체 image·의존성·PostgreSQL 17 metadata DB·API server·scheduler·DAG
processor를 가지며, CatalogGuard application requirements나 application DB를 공유하지
않는다. `LocalExecutor`를 사용한다.

Airflow는 ETL 변환 로직을 새로 구현하지 않는다. 운영자가 manual trigger한
`catalogguard_http_feed_to_staging`의 단일 task
`ingest_configured_http_feed_to_staging`가 기존 서비스를 순서대로 호출한다.

```text
운영자
-> Airflow manual trigger
-> catalogguard_http_feed_to_staging
-> ingest_configured_http_feed_to_staging
-> read_http_feed_csv()
-> run_web_etl()
-> run_pipeline()
-> load_standard_csv()
-> ETLLoadRun / CatalogProductStaging / ETLRejectedRow
```

Orchestration은 실행 순서·상태·재시도를 관리하는 역할이다. 따라서 이 DAG는 CSV
artifact를 XCom이나 shared filesystem에 저장하지 않고, XCom/task result로는
`etl_load_run_id`와 `created`만 돌려준다. `catalogguard_airflow_smoke` DAG는 ETL을
실행하지 않는 import/structure 검증용 DAG다.

Airflow metadata DB는 DAG run·task run·retry·scheduler 상태를 저장하고,
CatalogGuard DB는 ETL load run·staging·reject row·catalog data를 저장한다. 두 DB는
별도 PostgreSQL instance이며, Airflow scheduler만 CatalogGuard DB 연결과 feed 환경설정을
받는다.

Before starting it, copy the example environment file and replace the Airflow
placeholder secrets. Generate the Fernet key with the Airflow image, for example:

```powershell
docker run --rm --entrypoint python apache/airflow:3.3.0-python3.11 -c "from cryptography.fernet import Fernet; print(Fernet.generate_key().decode())"
```

Start the foundation and then inspect its smoke DAG:

```powershell
docker compose --env-file .env -f airflow/compose.yaml up --build -d
docker compose --env-file .env -f airflow/compose.yaml exec airflow-scheduler airflow dags list-import-errors
docker compose --env-file .env -f airflow/compose.yaml exec airflow-scheduler airflow tasks list catalogguard_airflow_smoke
```

configured HTTP feed staging DAG는 manual trigger만 지원하며, allowlist의
`profile_id`만 전달한다. feed URL·filename은 DAG parameter가 아니라 scheduler/task
환경설정이다. `DATABASE_URL`은 scheduler container에서 도달 가능한 별도 CatalogGuard DB를
가리켜야 하며, host-side DB에는 `localhost`를 사용하지 않는다. Airflow metadata DB는
`airflow-db` service에 남는다.

```powershell
docker compose --env-file .env -f airflow/compose.yaml exec airflow-scheduler airflow dags trigger catalogguard_http_feed_to_staging --conf '{"profile_id":"sample_fashion_vendor_v1"}'
```

task는 timeout·일시적 network/DNS/connection 문제, HTTP 429·5xx, 그리고
`connection_invalidated`·SQLSTATE `40001`·`40P01`인 DB 오류만 retry한다. redirect,
429 이외 HTTP 4xx, missing/unsafe feed 설정, invalid CSV/profile/pipeline/load 검증 오류와
그 밖의 DB 오류는 retry하지 않는다.

Idempotency(같은 작업을 다시 실행해도 중복 결과를 만들지 않는 성질)의 identity는
`(input_file_sha256, profile_name, profile_version)`이다. 같은 bytes를 다시 처리하면
기존 `ETLLoadRun`을 재사용해 `created=false`를 반환하므로 staging/reject row도 중복되지
않는다. 단, retry가 URL을 다시 읽는 구조이므로 remote feed 내용이 바뀌면 SHA-256도 달라져
새 batch가 될 수 있다.

HTTP lineage는 `initial_source_type=http_feed`,
`initial_source_ref=configured_http_feed`로 남기고 actor는 시스템 실행이므로 둘 다 `NULL`이다.
실제 URL·query·token은 lineage·XCom·안전한 예외에 저장하지 않는다. raw URL parameter와 raw
profile path를 받지 않고, profile allowlist·redirect 차단·unsafe URL 차단·환경설정 기반 feed를
사용한다. 실제 `.env` 값과 secret은 commit하지 않는다.

Airflow는 공급사 ETL 실행 흐름과 retry를 관리한다. 반면 Celery는 API가 요청한 사용자 검수의
비동기 inspection 처리에만 사용하며, 이 DAG는 Celery·Promotion을 호출하지 않는다.

The Airflow UI/API is exposed on `http://localhost:8088` by default. Stop only
the Airflow foundation with the following command; it does not touch the
CatalogGuard local Compose project or its volumes:

```powershell
docker compose --env-file .env -f airflow/compose.yaml down
```

GitHub Actions의 다섯 job(`test`, `browser-e2e`, `kubernetes-smoke`,
`terraform-validate`, `airflow-smoke`)이 main에서 검증된다. 특히 `airflow-smoke`는
격리 Airflow image build, 두 PostgreSQL DB 초기화, Airflow/Alembic migration, deterministic
HTTP feed, DAG processor·import·structure, 실제 staging load, idempotency와 lineage를 확인한다.
세부 설계·용어·현재 한계는 [ETL MVP 문서의 Airflow orchestration 절](docs/etl_mvp.md#airflow-manual-http-feed-orchestration)을 참고한다.

`etl.cli`는 JSON 프로필을 사용해 서로 다른 컬럼 구조의 합성 공급사 CSV 2종을 CatalogGuard 표준 CSV로 변환합니다. 상품 그룹 ID와 SKU가 분리된 구조도 지원하는 것을 확인했으며, 정상가보다 큰 할인가 같은 상품 품질 문제는 정상 행으로 남겨 기존 검수기가 처리하도록 합니다. 자세한 프로필 비교, CLI 예시와 제한사항은 [ETL MVP 문서](docs/etl_mvp.md)를 참고하세요.

```powershell
python -m etl.cli `
  --input .\tests\fixtures\etl\sample_vendor_mixed.csv `
  --profile .\config\etl\sample_fashion_vendor_v1.json `
  --output .\output\catalogguard_ready.csv `
  --rejects .\output\rejected_rows.csv `
  --summary .\output\etl_summary.json
```

생성된 표준 CSV와 summary JSON은 별도 CLI로 PostgreSQL staging에 적재합니다. 실제 표준 CSV의 SHA-256과 summary의 `output_file_sha256`, 실제 행 수와 `loaded_rows`를 비교하고, 동일한 입력 해시·프로필 이름·버전의 배치는 재사용합니다.

```powershell
python -m etl.load_cli `
  --input .\output\catalogguard_ready.csv `
  --rejects .\output\rejected_rows.csv `
  --summary .\output\etl_summary.json
```

```text
DB 적재 완료
적재 배치 ID: 1
신규 적재: yes
전체 행: 2
정상 상품 행: 2
거부 행: 0
```

적재 후에는 `GET /api/v1/etl-loads`로 배치 목록을, `GET /api/v1/etl-loads/{etl_load_run_id}`로 파일 해시와 해당 배치의 staging 상품을, `GET /api/v1/etl-loads/{etl_load_run_id}/rejections`로 구조화된 오류와 마스킹된 원본을 페이지 단위로 조회할 수 있습니다. 프로필 구조, 변환·오류 기준, 조회 규칙과 제한사항은 [ETL MVP 문서](docs/etl_mvp.md)를 참고하세요.

위 두 CLI 명령과 같은 변환·적재 로직을 Streamlit에서도 실행할 수 있습니다. `ETL 실행` 영역에서 공급사 CSV를 업로드하고 `ETL 실행 프로필`을 선택한 뒤 버튼을 클릭하면 `POST /api/v1/etl-loads`가 같은 `run_pipeline()`·`load_standard_csv()`를 호출해 staging까지 적재합니다. 웹 ETL의 profile allowlist, 업로드 검증, 중복 재사용과 임시 파일 정리 같은 구현 세부사항은 [ETL MVP 문서](docs/etl_mvp.md)를 참고하세요.
