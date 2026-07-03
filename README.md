# CatalogGuard Lite

상품 카탈로그 CSV 데이터의 품질을 검증하고 검수 결과를 CSV로 내려받을 수 있는 경량 도구입니다.

CSV 파일을 읽어서 상품 데이터에 빠진 값, 잘못된 카테고리, 이상한 재고, 이상한 가격, 중복 상품 ID가 있는지 확인합니다.

## 검증 규칙

- **duplicate_product_id**: 같은 `product_id`가 여러 상품에 사용된 경우
- **duplicate_product_name**: 정리한 `product_name`이 같은 상품명 중복 후보가 있는 경우. 같은 상품 그룹에서 색상이나 사이즈가 명확하게 다른 옵션 상품은 제외합니다.
- **duplicate_product_content**: `product_name`, `category`, `color`, `size`, `price`가 모두 같은 상품이 중복 등록된 경우
- **missing_required_field**: `product_group_id`, `product_id`, `product_name`, `category`, `color`, `size`, `image_path` 중 값이 비어 있는 경우
- **invalid_category**: `category`가 허용 목록(`TOP`, `BOTTOM`, `OUTER`)에 없는 경우
- **invalid_stock** / **out_of_stock**: `stock`이 숫자가 아니거나 음수(error), 0(warning)인 경우
- **invalid_price** / **invalid_non_positive_price**: `price`가 숫자가 아니거나 0 이하인 경우
- **category_price_anomaly**: 같은 카테고리의 유효 가격이 5개 이상일 때 중앙값 기준으로 지나치게 높거나 낮은 가격을 warning으로 표시
- **product_category_mismatch**: 상품명에서 추정되는 카테고리와 현재 `category`가 명확하게 다른 경우
- **prohibited_term**: `product_name`, `description`, `seller`에서 설정된 금지어가 발견된 경우
- **email_address** / **phone_number** / **resident_registration_number**: 상품 텍스트에 이메일 주소, 전화번호, 주민등록번호 형식이 포함된 경우
- **suspected_bank_account**: 계좌, 입금, 송금, 은행, 예금주 같은 문맥어와 10~14자리 숫자 형식이 함께 있을 때 계좌번호 의심 항목을 warning으로 표시

헤더만 있고 상품 행이 없는 CSV는 처리하지 않습니다.
잘못된 재고와 가격 문자열은 앱을 중단시키지 않고 형식 오류로 처리합니다.
상품 ID가 비어 있으면 중복 검사가 아니라 필수 값 누락으로 처리합니다.
0원, 음수, 숫자 오류 가격은 가격 이상치가 아니라 가격 오류 규칙에서 처리합니다.
가격 이상치 분석은 현재 상품 행 단위로 수행되며, 같은 상품 그룹의 여러 옵션이 가격 분포에 여러 번 포함될 수 있습니다.
상품명·카테고리 불일치는 명확한 키워드가 하나의 카테고리만 가리킬 때만 warning으로 표시합니다.
완전 중복 상품 검사는 공백과 영문 대소문자를 정리한 뒤 비교하며, 상품 ID, 상품 그룹 ID, 재고, 이미지 경로는 비교 기준에서 제외합니다.
상품명 중복 검사는 다른 상품 그룹의 동일 상품명이나 같은 상품 그룹의 동일 옵션 조합을 중복 후보로 표시합니다.
누락 값, 잘못된 카테고리, 0원·음수·숫자 오류 가격은 완전 중복 비교에서 제외합니다.
금지어 목록은 MVP 예시이며 실제 서비스 운영 정책에 맞게 조정해야 합니다.
개인정보와 계좌번호 의심 탐지는 정규식 기반이므로 오탐과 미탐 가능성이 있습니다.
테스트 데이터에는 실제 개인정보를 사용하지 말고 가짜 값을 사용해야 합니다.

## 검수 결과 표시

- 오류 이유는 사용자가 읽기 쉬운 한글 문장으로 표시됩니다.
- 결과 CSV 다운로드 파일에도 한글 오류 이유가 포함됩니다.
- 이메일 주소, 전화번호, 주민등록번호 형식, 계좌번호 의심 값은 화면과 CSV에서 마스킹되어 표시됩니다.
- 전체 상태는 오류, 주의, 정상으로 구분되어 표시됩니다.
- 검수 상태와 오류 항목으로 결과를 필터링할 수 있습니다.
- 상품 ID 일부 문자를 검색할 수 있습니다.
- CSV 다운로드는 현재 필터 결과만 포함합니다.
- CSV 다운로드 파일은 Windows Excel에서 한글이 깨지지 않도록 UTF-8 BOM 인코딩으로 생성됩니다.
- CSV 다운로드용 데이터는 표시용 결과 DataFrame의 복사본을 사용하며, 원본 검수 결과를 직접 변경하지 않습니다.
- 수식으로 해석될 수 있는 문자열은 CSV에서 안전하게 처리됩니다.

## CSV 업로드 제한

- CSV 파일만 업로드할 수 있습니다. 확장자는 대소문자를 구분하지 않습니다.
- 최대 파일 크기는 5MB입니다.
- 최대 데이터 행 수는 10,000행입니다.
- 지원 인코딩은 UTF-8 BOM, UTF-8, CP949입니다.
- NUL 바이트가 포함된 일반 텍스트가 아닌 파일은 거부합니다.
- 빈 파일, 헤더만 있는 파일, 잘못된 CSV 형식은 검수를 시작하기 전에 차단합니다.
- 빈 컬럼명과 중복 컬럼명을 검사합니다.
- 필수 컬럼 누락을 검사하며, `description`, `seller` 선택 컬럼 누락은 허용합니다.
- 정상 검증된 DataFrame 하나를 미리보기와 상품 검수에 함께 사용합니다.

## CSV 입력 템플릿

앱 화면의 `CSV 입력 템플릿 다운로드` 버튼을 사용하면 현재 지원하는 컬럼이 포함된 CSV 파일을 내려받을 수 있습니다.

템플릿에는 작성 방법을 보여 주기 위한 가짜 예시 상품 1개가 포함되어 있습니다.
실제 사용 전 예시 행을 삭제하거나 실제 상품 정보로 교체해 주세요.

필수 컬럼은 `product_group_id`, `product_id`, `product_name`, `category`, `color`, `size`, `stock`, `price`, `image_path`입니다.
선택 컬럼은 `description`, `seller`입니다.

## 프로젝트 구조

```
app.py                 # Streamlit CSV 업로드 및 결과 화면
config/settings.py   # 경로, 필수 컬럼, 허용값 등 설정
core/models.py        # Product, ValidationIssue 데이터 모델
core/loader.py         # CSV -> Product 리스트 로딩
core/upload_validator.py # CSV 업로드 파일 사전 검증
core/product_template.py # CSV 입력 템플릿 생성
core/rules.py           # 검증 규칙 및 run_all_rules()
core/presentation.py    # 검수 결과 표시, 필터, 한글 메시지 변환
core/result_exporter.py # 검수 결과 CSV 다운로드 데이터 생성
tests/test_loader.py    # CSV 로딩 테스트
tests/test_upload_validator.py # CSV 업로드 검증 테스트
tests/test_product_template.py # CSV 입력 템플릿 테스트
tests/test_rules.py     # 검증 규칙 테스트
tests/test_presentation.py # 표시 및 필터 테스트
tests/test_result_exporter.py # 검수 결과 CSV 다운로드 테스트
data/dev/                # 개발용 샘플 데이터
```

## CSV 필수 컬럼

```text
product_group_id, product_id, product_name, category, color, size, stock, price, image_path
```

## CSV 선택 컬럼

```text
description, seller
```

`description`과 `seller`는 상품 설명과 판매자 정보 검수에 사용됩니다.
두 컬럼이 없는 기존 CSV도 그대로 로딩되며, 값이 비어 있으면 빈 문자열로 처리합니다.

## 실행

Windows PowerShell 또는 VS Code 터미널에서 프로젝트 루트로 이동한 뒤 실행합니다.

### 설치 명령어

```powershell
python -m pip install -r requirements.txt
```

### 테스트 실행

```powershell
python -m pytest -q
```

### Streamlit 실행

```powershell
python -m streamlit run app.py
```

### 정상 실행 결과

브라우저가 열리고 다음 화면이 보여야 합니다.

- CatalogGuard Lite 제목
- CSV 입력 템플릿 다운로드 버튼
- CSV 업로드 버튼
- 상품 데이터 미리보기
- 검수 요약
- 검수 결과 표
- 검수 상태, 오류 항목, 상품 ID 검색 필터
- 현재 필터 결과 CSV 다운로드 버튼

### 샘플 CSV 결과

`data/dev/products_dev.csv`를 업로드했을 때 예상 결과는 다음과 같습니다.

```text
전체 상품 수: 5
전체 문제 수: 6
오류 수: 6
주의 수: 0
```

## Python 예시

```python
from core.loader import load_products
from core.rules import run_all_rules
from config.settings import DEV_DATA_PATH

products = load_products(DEV_DATA_PATH)
issues = run_all_rules(products)
```

## 테스트

현재 테스트는 pytest로 실행합니다.

- `tests/test_loader.py`: CSV 로딩 테스트
- `tests/test_upload_validator.py`: CSV 업로드 검증 테스트
- `tests/test_product_template.py`: CSV 입력 템플릿 테스트
- `tests/test_rules.py`: 검증 규칙 테스트
- `tests/test_presentation.py`: 표시 및 필터 테스트
- `tests/test_result_exporter.py`: 검수 결과 CSV 다운로드 테스트

실행 예시:

```text
pytest
```
