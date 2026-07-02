# CatalogGuard Lite

상품 카탈로그 CSV 데이터의 품질을 검증하는 경량 도구입니다.

CSV 파일을 읽어서 상품 데이터에 빠진 값, 잘못된 카테고리, 이상한 재고, 이상한 가격, 중복 상품 ID가 있는지 확인합니다.

## 검증 규칙

- **duplicate_product_id**: `product_id`가 서로 다른 `product_group_id`에서 재사용되는 경우
- **missing_required_field**: `product_group_id`, `product_id`, `product_name`, `category`, `color`, `size`, `image_path` 중 값이 비어 있는 경우
- **invalid_category**: `category`가 허용 목록(`TOP`, `BOTTOM`, `OUTER`)에 없는 경우
- **invalid_stock** / **out_of_stock**: `stock`이 숫자가 아니거나 음수(error), 0(warning)인 경우
- **invalid_price** / **zero_price**: `price`가 숫자가 아니거나 음수(error), 0(warning)인 경우
- **price_outlier**: 같은 카테고리의 유효 가격이 5개 이상일 때 IQR 방식으로 지나치게 높거나 낮은 가격을 warning으로 표시

헤더만 있고 상품 행이 없는 CSV는 처리하지 않습니다.
잘못된 재고와 가격 문자열은 앱을 중단시키지 않고 형식 오류로 처리합니다.
상품 ID 또는 상품 그룹 ID가 비어 있으면 중복 검사가 아니라 필수 값 누락으로 처리합니다.
0원, 음수, 숫자 오류 가격은 가격 이상치가 아니라 기존 가격 형식 규칙에서 처리합니다.
가격 이상치 분석은 현재 상품 행 단위로 수행되며, 같은 상품 그룹의 여러 옵션이 가격 분포에 여러 번 포함될 수 있습니다.

## 검수 결과 표시

- 오류 이유는 사용자가 읽기 쉬운 한글 문장으로 표시됩니다.
- 결과 CSV 다운로드 파일에도 한글 오류 이유가 포함됩니다.
- 전체 상태는 오류, 주의, 정상으로 구분되어 표시됩니다.
- 검수 상태와 오류 항목으로 결과를 필터링할 수 있습니다.
- 상품 ID 일부 문자를 검색할 수 있습니다.
- CSV 다운로드는 현재 필터 결과만 포함합니다.

## 프로젝트 구조

```
app.py                 # Streamlit CSV 업로드 및 결과 화면
config/settings.py   # 경로, 필수 컬럼, 허용값 등 설정
core/models.py        # Product, ValidationIssue 데이터 모델
core/loader.py         # CSV -> Product 리스트 로딩
core/rules.py           # 검증 규칙 및 run_all_rules()
core/presentation.py    # 검수 결과 표시, 필터, 한글 메시지 변환
tests/test_loader.py    # CSV 로딩 테스트
tests/test_rules.py     # 검증 규칙 테스트
tests/test_presentation.py # 표시 및 필터 테스트
data/dev/                # 개발용 샘플 데이터
```

## CSV 필수 컬럼

```text
product_group_id, product_id, product_name, category, color, size, stock, price, image_path
```

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
- CSV 업로드 버튼
- 상품 데이터 미리보기
- 검수 요약
- 검수 결과 표
- 검수 상태, 오류 항목, 상품 ID 검색 필터
- 현재 필터 결과 다운로드 버튼

### 샘플 CSV 결과

`data/dev/products_dev.csv`를 업로드했을 때 예상 결과는 다음과 같습니다.

```text
전체 상품 수: 5
전체 문제 수: 5
오류 수: 4
주의 수: 1
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

현재 테스트는 총 73개입니다.

- `tests/test_loader.py`: 17개
- `tests/test_rules.py`: 25개
- `tests/test_presentation.py`: 31개

마지막 확인 결과:

```text
73 passed
```
