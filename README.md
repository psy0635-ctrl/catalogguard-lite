# CatalogGuard Lite

상품 카탈로그 CSV를 업로드하면 필수 값 누락, 잘못된 카테고리, 재고/가격 오류, 중복 상품, 개인정보 포함 여부를 검사하는 Streamlit 기반 검수 도구입니다.

- 배포 URL: https://catalogguard-lite-p6jtwmdhwqcapphpghfzduo.streamlit.app/
- 실행 방식: Streamlit 웹 앱
- 주요 기술: Python 3.11, Streamlit, pandas, pytest
- 현재 테스트 기준: 327개 자동 테스트 통과, 경고 1건

## 프로젝트 소개

CatalogGuard Lite는 상품 운영자가 CSV로 관리하는 상품 목록을 업로드한 뒤, 검수 결과를 화면과 CSV 다운로드 파일로 확인할 수 있도록 만든 경량 품질 검사 도구입니다.

이 프로젝트는 실제 상품 데이터를 저장하거나 외부 서버로 전송하지 않습니다. 업로드된 CSV는 앱 실행 중 메모리에서 검수되며, 개인정보로 보이는 값은 미리보기와 검수 결과 표시 단계에서 마스킹됩니다.

## 핵심 기능

- CSV 업로드 전 파일 검증
- CSV 입력 템플릿 다운로드
- 업로드 상품 데이터 미리보기
- 미리보기 개인정보 마스킹
- 상품 필수 값 누락 검사
- 허용 카테고리 검사
- 재고 오류 및 품절 상품 검사
- 가격 오류 및 카테고리별 가격 이상치 검사
- 상품 ID, 상품명, 완전 중복 상품 탐지
- 상품명과 카테고리 불일치 탐지
- 금지어 및 개인정보 형태 탐지
- 검수 결과 필터링
- 현재 필터 결과 CSV 다운로드

## 서비스 흐름

```text
CSV 업로드
-> 파일명, 크기, 인코딩, 헤더, 행 개수 검증
-> 원본 DataFrame 생성
-> 마스킹된 미리보기 복사본 생성
-> 원본 DataFrame을 Product 객체로 변환
-> 검수 규칙 실행
-> 검수 결과 화면 표시
-> 필터링된 결과 CSV 다운로드
```

중요한 분리 원칙은 다음과 같습니다.

```text
원본 DataFrame
-> Product 객체 변환
-> 실제 상품 검수에 사용

마스킹된 DataFrame 복사본
-> 화면 미리보기에만 사용
```

## 실행 화면

### 1. CSV 템플릿 및 파일 업로드

필수·선택 컬럼을 확인하고 CSV 입력 템플릿을 내려받을 수 있습니다. 작성한 상품 CSV 파일은 업로드 영역에서 검수를 시작할 수 있습니다.

![CatalogGuard Lite CSV 템플릿 및 파일 업로드 화면](docs/images/01_initial_upload.png)

### 2. 개인정보 마스킹 미리보기

업로드한 데이터는 검수 전에 미리보기로 확인할 수 있습니다. 이메일, 전화번호, 주민등록번호 형태는 일부 문자를 가려서 표시합니다.

![CatalogGuard Lite 개인정보 마스킹 미리보기 화면](docs/images/02_masked_preview_summary.png)

> 위 화면은 개인정보 마스킹 기능을 확인하기 위해 가짜 이메일, 전화번호 및 주민등록번호 형태가 포함된 테스트 CSV를 사용한 예시입니다.

### 3. 검수 결과 필터 및 CSV 다운로드

발견된 문제의 상태, 오류 항목과 상품 ID를 기준으로 결과를 필터링할 수 있습니다. 각 문제의 오류 이유, 수정 권장사항과 위험 수준을 확인하고 현재 필터 결과를 CSV로 내려받을 수 있습니다.

![CatalogGuard Lite 검수 결과 필터 및 CSV 다운로드 화면](docs/images/03_results_filter_download.png)

> 위 화면은 `data/dev/products_dev.csv`를 사용한 검수 예시이며, 상품 5개에서 오류 6건이 탐지된 결과입니다.

## 배포 앱

현재 배포된 앱은 아래 주소에서 확인할 수 있습니다.

https://catalogguard-lite-p6jtwmdhwqcapphpghfzduo.streamlit.app/

Streamlit Community Cloud 기준 설정은 다음과 같습니다.

| 항목 | 값 |
|---|---|
| Repository | `psy0635-ctrl/catalogguard-lite` |
| Branch | `main` |
| Main file path | `app.py` |
| Python | `3.11` 권장 |
| Secrets | 사용하지 않음 |

## CSV 입력 형식

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

선택 컬럼은 2개입니다.

| 컬럼 | 설명 |
|---|---|
| `description` | 상품 설명 |
| `seller` | 판매자 정보 |

허용 카테고리는 `TOP`, `BOTTOM`, `OUTER`입니다.

## CSV 업로드 검증

업로드된 파일은 검수 규칙 실행 전에 먼저 검증됩니다.

- `.csv` 확장자만 허용
- 최대 파일 크기 5MB
- 최대 데이터 행 수 10,000행
- UTF-8 BOM, UTF-8, CP949 인코딩 지원
- NUL 바이트 포함 파일 차단
- 빈 파일과 헤더만 있는 파일 차단
- 빈 컬럼명 차단
- 중복 컬럼명 차단
- 필수 컬럼 누락 차단
- CSV 행의 열 개수 불일치 차단

## 검수 규칙

현재 `core/rules.py`의 `RULES`에는 10개 규칙 함수가 등록되어 있습니다.

| 규칙 | 주요 내용 | 심각도 |
|---|---|---|
| `check_duplicate_product_id` | 같은 상품 ID가 여러 행에 사용되었는지 검사 | 오류 |
| `check_duplicate_product_name` | 정규화된 상품명이 중복 후보인지 검사 | 주의 |
| `check_duplicate_product_content` | 상품명, 카테고리, 색상, 사이즈, 가격이 모두 같은 상품 검사 | 오류 |
| `check_missing_required_fields` | 필수 값 누락 검사 | 오류 |
| `check_invalid_category` | 허용되지 않은 카테고리 검사 | 오류 |
| `check_stock` | 재고 누락, 숫자 오류, 음수, 0개 검사 | 오류 또는 주의 |
| `check_price` | 가격 누락, 숫자 오류, 0 이하 가격 검사 | 오류 |
| `check_price_outliers` | 카테고리 중앙값 기준 가격 이상치 검사 | 주의 |
| `check_product_category_mismatch` | 상품명 키워드와 카테고리 불일치 검사 | 주의 |
| `check_prohibited_and_personal_information` | 금지어, 이메일, 전화번호, 주민등록번호 형태, 계좌번호 의심 검사 | 오류 또는 주의 |

가격 이상치는 같은 카테고리의 유효 가격이 5개 이상일 때 계산합니다. 카테고리 중앙값의 0.25배보다 낮거나 4배보다 높은 가격을 주의 항목으로 표시합니다.

상품명 중복 검사는 같은 상품 그룹 안에서 색상 또는 사이즈가 명확히 다른 정상 옵션 상품을 중복 후보에서 제외합니다.

## 개인정보 처리

개인정보 관련 정규식과 미리보기 마스킹 함수는 `core/privacy.py`에 모여 있습니다.

미리보기에서 마스킹하는 항목은 다음과 같습니다.

| 항목 | 예시 |
|---|---|
| 전화번호 | `010-****-5678` |
| 이메일 | `sa****@test.com` |
| 주민등록번호 형태 | `900101-*******` |

마스킹은 셀 전체뿐 아니라 문장 안에 포함된 값에도 적용됩니다.

```text
문의 전화는 010-1234-5678입니다.
-> 문의 전화는 010-****-5678입니다.
```

숫자형 컬럼으로 쓰이는 `product_group_id`, `product_id`, `stock`, `price`는 미리보기 마스킹 대상에서 제외합니다. 또한 문자열이 아닌 값은 그대로 반환해 가격, 재고, 결측값 처리와 충돌하지 않도록 했습니다.

계좌번호 의심 값은 숫자만으로 판단하지 않고 `계좌`, `입금`, `송금`, `은행`, `예금주` 같은 문맥어가 함께 있을 때 검수 결과에 표시합니다.

## 검수 결과 화면

검수 결과는 다음 컬럼으로 표시됩니다.

```text
검수 상태, 오류 항목, 상품 그룹 ID, 상품 ID, 오류 이유, 수정 권장사항, 위험 수준
```

화면에서는 다음 기능을 사용할 수 있습니다.

- 전체 상태, 전체 상품 수, 전체 문제 수, 오류 수, 주의 수 요약
- 검수 상태 필터
- 오류 항목 필터
- 상품 ID 검색
- 현재 필터 결과 CSV 다운로드

결과 CSV는 Windows Excel에서 한글이 깨지지 않도록 UTF-8 BOM으로 생성합니다. CSV 수식 삽입을 막기 위해 `=`, `+`, `-`, `@`로 시작하는 문자열은 다운로드용 복사본에서 안전하게 처리합니다.

## 샘플 데이터 기준 결과

`data/dev/products_dev.csv`를 현재 코드로 검수하면 다음 결과가 나옵니다.

```text
전체 상품 수: 5
전체 문제 수: 6
오류 수: 6
주의 수: 0
```

## 프로젝트 구조

```text
app.py
config/
  settings.py
core/
  category_mismatch_detector.py
  duplicate_detector.py
  loader.py
  models.py
  presentation.py
  price_anomaly_detector.py
  privacy.py
  product_template.py
  result_exporter.py
  rules.py
  upload_validator.py
data/
  dev/
    category_mismatch_test.csv
    price_anomaly_test.csv
    products_dev.csv
tests/
  test_app_smoke.py
  test_category_mismatch_detector.py
  test_duplicate_detector.py
  test_loader.py
  test_presentation.py
  test_price_anomaly_detector.py
  test_privacy.py
  test_product_template.py
  test_result_exporter.py
  test_rules.py
  test_upload_validator.py
```

## 주요 파일 역할

| 파일 | 역할 |
|---|---|
| `app.py` | Streamlit 화면, CSV 업로드, 미리보기, 검수 요약, 결과 필터, 다운로드 연결 |
| `config/settings.py` | 컬럼, 카테고리, 업로드 제한, 금지어, 스캔 대상 필드 설정 |
| `core/upload_validator.py` | 업로드 CSV 사전 검증 |
| `core/loader.py` | DataFrame 또는 CSV 파일을 Product 객체 목록으로 변환 |
| `core/rules.py` | 전체 검수 규칙 실행 |
| `core/privacy.py` | 개인정보 정규식, 마스킹, 미리보기 복사본 생성 |
| `core/presentation.py` | 검수 결과를 화면용 DataFrame과 한글 메시지로 변환 |
| `core/result_exporter.py` | 검수 결과 CSV 다운로드 데이터 생성 |
| `core/product_template.py` | CSV 입력 템플릿 생성 |
| `core/duplicate_detector.py` | 상품 ID와 상품명 중복 탐지 |
| `core/price_anomaly_detector.py` | 카테고리별 가격 이상치 탐지 |
| `core/category_mismatch_detector.py` | 상품명 키워드 기반 카테고리 불일치 탐지 |

## 설치 및 실행

Windows PowerShell 또는 VS Code 터미널에서 실행합니다.

```powershell
cd <프로젝트_폴더>
python -m venv .venv
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements.txt
python -m streamlit run app.py
```

브라우저가 자동으로 열리지 않으면 터미널에 표시되는 Streamlit 주소를 열면 됩니다.

## FastAPI 개발 서버

API 서버 실행과 테스트에는 별도 의존성 파일을 사용합니다.

```powershell
cd <프로젝트_폴더>
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-api.txt
python -m uvicorn api.main:app --reload
```

브라우저에서 아래 주소를 확인합니다.

- Health check: http://127.0.0.1:8000/health
- API docs: http://127.0.0.1:8000/docs

API 테스트만 실행하려면 다음 명령을 사용합니다.

```powershell
python -m pytest tests/test_api_health.py -q
```

서버는 실행 중인 터미널에서 `Ctrl+C`로 종료합니다.

## 테스트 실행

테스트 실행에는 pytest와 API 테스트 의존성이 필요합니다. 현재 확인한 테스트 도구 버전은 `pytest==9.1.1`입니다.

```powershell
cd <프로젝트_폴더>
.\.venv\Scripts\Activate.ps1
python -m pip install -r requirements-api.txt
python -m pip install pytest==9.1.1
python -m pytest -q
```

현재 확인 결과는 다음과 같습니다.

```text
전체 테스트: 327개 통과
경고: 1건
```

## 개발 메모

- 원본 DataFrame은 검수 로직에 그대로 사용합니다.
- 미리보기 마스킹은 복사본 DataFrame에만 적용합니다.
- 결과 CSV 생성도 표시용 결과 DataFrame의 복사본을 사용합니다.
- 개인정보 탐지는 정규식 기반이므로 실제 운영에서는 정책과 샘플 데이터를 기준으로 지속 조정이 필요합니다.
- 금지어 목록은 MVP 예시이며 운영 정책에 맞게 바꾸는 것을 전제로 합니다.
- 현재 프로젝트는 인증, 데이터베이스 저장, 외부 API 연동을 포함하지 않습니다.
