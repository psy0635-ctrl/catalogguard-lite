# CatalogGuard Lite — 캡처·3분 시연·재부팅 복구

## 현재 확인된 화면

- PostgreSQL: 127.0.0.1:55432, Alembic `20260915_0020`
- FastAPI: http://127.0.0.1:8001, `/health`·`/ready`·`/docs` HTTP 200
- Streamlit: http://127.0.0.1:8501, 로그인 성공
- ETL 배치 1: 전체 3 / 정상 2 / reject 1
- 검수 run 1: 상품 5 / issue 6
- 수정본 run 2: 상품 5 / issue 5
- 비교 방향: 기준 run 1 → 비교 run 2, 공통 5 / 기준에만 1 / 비교에만 0
- Trend: 버전 15, 서울 날짜 2026-09-24, 실행 2 / 상품 10 / issue 11

## 수동 캡처 순서

1. GitHub 저장소 README 첫 화면: 프로젝트 이름과 목적 문단.
2. Streamlit 로그인 → **ETL 적재 이력** → **ETL 실행**: 패션 공급사 샘플과 CSV/XLSX 파일 선택.
3. 같은 탭 아래 **ETL 적재 이력** → 배치 **1** 선택 → **상세 조회**: 전체 3, 정상 2, 변환 거부 1.
4. 같은 상세의 **거부 행 상세** → **원본 행 3 - 마스킹 원본** 펼치기: 오류 코드·이유·마스킹 값.
5. **CSV 검수** → `data/dev/products_dev.csv` 선택: CSV 업로드와 상품 데이터 미리보기.
6. **검수 실행 및 이력 저장**: 요약 5/6과 결과 표의 오류 이유·수정 권장사항. 같은 파일이면 기존 run 1을 불러오는 것이 정상입니다.
7. **검수 이력** → **검수 실행 비교**: 기준 **1 products_dev.csv**, 비교 **2 catalogguard_demo_products_corrected.csv**를 명시적으로 선택하고 **비교**. 공통 5 / 기준에만 1 / 비교에만 0.
8. 같은 탭의 **검수 품질 추세**: 현재 버전 15와 서울 날짜 집계.
9. 기존 GitHub Actions run `35808803669`: 5개 job 성공. Golden 실제 출력은 `golden-regression.txt`.

이 폴더의 `screenshots`에 9개 실측 이미지를 저장했습니다. `screenshots/drafts`는 구도를 고르며 보존한 초안입니다.

## 3분 대본

- **0:00–0:20 문제:** 공급사마다 다른 상품 데이터를 등록하면 가격 오류, 누락, 중복을 뒤늦게 발견할 수 있습니다.
- **0:20–0:50 ETL:** 배치 1의 전체 3·정상 2·reject 1. 공급사 데이터를 공통 형식으로 바꾸고 오류 행은 분리합니다.
- **0:50–1:30 Inspection:** run 1의 상품 5·issue 6. 오류 항목, 이유, 수정 권장사항을 보여줍니다.
- **1:30–2:05 오류·작업표:** 원본 행 관계와 Correction Worksheet를 설명합니다. 작업표 자체를 재업로드하지 않습니다.
- **2:05–2:35 Comparison:** 원본 run 1 → 수정본 run 2, 5/1/0. base_only를 자동으로 개선이라고 단정하지 않습니다.
- **2:35–2:50 Trend:** 현재 버전 15의 서울 날짜 집계를 보여줍니다.
- **2:50–3:00 Golden·CI:** Golden `2 passed`와 기존 Actions 5개 성공을 보여줍니다.

DB 시작, migration, 사용자 생성, dependency 설치, 전체 테스트, ETL·Inspection 신규 실행은 3분 시연 전에 마칩니다.

## 재부팅 후 복구

아래 임시 DB 경로가 유지된 경우에만 같은 배치·실행 ID를 복구할 수 있습니다. Windows가 임시 폴더를 삭제했다면 같은 데이터를 보장할 수 없으므로 기존 ID를 전제로 시연하지 마세요. 모든 명령은 **새 PowerShell**에서 시작하며, 저장소 작업 디렉터리는 `C:\study\catalogguard-lite`입니다. 비밀 값이 있는 변수를 화면에 출력하지 마세요.

### 1. PostgreSQL — PowerShell 1

```powershell
cd C:\study\catalogguard-lite
$q = Join-Path $env:TEMP 'catalogguard-demo-pg-20260924'
if (-not (Test-Path -LiteralPath (Join-Path $q 'data')) -or
    -not (Test-Path -LiteralPath (Join-Path $q 'pg-password.txt'))) {
    throw '이전 임시 데모 DB가 없습니다.'
}
$pg = 'C:\Program Files\PostgreSQL\18\bin\pg_ctl.exe'
& $pg -D (Join-Path $q 'data') status
if ($LASTEXITCODE -ne 0) {
    & $pg -D (Join-Path $q 'data') -l (Join-Path $q 'postgres.log') -o '-h 127.0.0.1 -p 55432' start
}
```

정상: `server is running` 또는 `server started`, 포트 55432 수신.

### 2. FastAPI — PowerShell 2

```powershell
cd C:\study\catalogguard-lite
$q = Join-Path $env:TEMP 'catalogguard-demo-pg-20260924'
$dbpw = (Get-Content -LiteralPath (Join-Path $q 'pg-password.txt') -Raw).Trim()
$env:DATABASE_URL = 'postgresql+psycopg://catalogguard_demo:' +
    [uri]::EscapeDataString($dbpw) +
    '@127.0.0.1:55432/catalogguard_demo'
$line = Get-Content -LiteralPath '.env.local' |
    Where-Object { $_ -match '^CATALOGGUARD_JWT_SECRET=' } |
    Select-Object -First 1
if (-not $line) { throw '로컬 JWT 설정이 없습니다.' }
$env:CATALOGGUARD_JWT_SECRET = ($line -split '=', 2)[1].Trim('"', "'")
& .\.venv\Scripts\python.exe -B -m alembic current
& .\.venv\Scripts\python.exe -B -m uvicorn api.main:app --host 127.0.0.1 --port 8001
```

정상: Alembic `20260915_0020 (head)`. 다른 PowerShell에서 `Invoke-WebRequest http://127.0.0.1:8001/ready -UseBasicParsing`의 상태 코드 200. `/health`, `/docs`도 200.

### 3. Streamlit — PowerShell 3

```powershell
cd C:\study\catalogguard-lite
$env:CATALOGGUARD_API_BASE_URL = 'http://127.0.0.1:8001'
& .\.venv\Scripts\python.exe -B -m streamlit run app.py --server.address 127.0.0.1 --server.port 8501 --server.headless true
```

정상: `http://127.0.0.1:8501` 접근, 로그인 화면 표시.

### 4. 로그인

기존 `operator1` 비밀번호를 알고 있으면 그대로 사용하세요. 캡처용 `portfolio_capture` 계정의 임의 비밀번호는 **같은 Windows 사용자**에서만 복호화되는 DPAPI 파일 `capture-operator-password.dpapi`에 저장했습니다. 터미널에 표시하지 않고 잠시 클립보드로 복사해 입력하려면:

```powershell
$p = 'C:\Users\user\Desktop\catalogguard-portfolio\demo-notes\capture-operator-password.dpapi'
$secure = Get-Content -LiteralPath $p | ConvertTo-SecureString
$credential = [pscredential]::new('portfolio_capture', $secure)
Set-Clipboard -Value $credential.GetNetworkCredential().Password
```

브라우저에 붙여넣은 직후 `Set-Clipboard -Value ''`로 클립보드를 비우세요. DPAPI 파일을 다른 PC에 복사해도 복호화되지 않습니다.

## 질문 대응

| 질문 | 보여줄 화면 | 답변 핵심 |
|---|---|---|
| ETL과 Inspection의 차이 | 배치 1 + 검수 run 1 | ETL은 공급사 데이터 변환·적재, Inspection은 상품 품질 규칙 검사입니다. |
| 오류를 어떻게 검증했나 | Golden 출력 + Actions | Golden fixture의 예상 issue와 결과를 비교하고 CI에서 분리된 검증을 실행합니다. 정확도 100%라는 뜻은 아닙니다. |
| 같은 파일을 다시 올리면 | ETL 배치 + 검수 화면 | ETL은 입력 identity 기준 기존 batch 재사용, Inspection은 파일 SHA-256과 검수 버전 기준 중복 저장 방지입니다. |
| 수정됐는지 어떻게 확인하나 | run 1 → run 2 비교 | 같은 상품 구성에서 음수 가격 한 건을 수정했고 base_only 1을 확인했습니다. 일반적으로 base_only만으로 개선을 단정할 수는 없습니다. |

## 캡처 보안

- 실제 DB 연결 문자열, 비밀번호, JWT, API key, Redis credential, 개인 이메일·전화번호는 표시하지 않습니다.
- 합성 fixture와 로컬 계정만 사용합니다.
- 브라우저의 민감한 query parameter와 터미널 secret을 화면에서 제외합니다.
- `09_golden_ci.png`는 기존 Actions 성공 화면이며 Golden CLI 출력은 별도 텍스트 파일입니다.
