# CatalogGuard Lite

상품 카탈로그 CSV 데이터의 품질을 검증하는 경량 도구입니다.

## 검증 규칙

- **duplicate_product_id**: `product_id`가 서로 다른 `product_group_id`에서 재사용되는 경우
- **missing_required_field**: `product_name`, `category`, `color`, `size`, `image_path` 중 값이 비어 있는 경우
- **invalid_category**: `category`가 허용 목록(`TOP`, `BOTTOM`, `OUTER`)에 없는 경우
- **invalid_stock** / **out_of_stock**: `stock`이 숫자가 아니거나 음수(error), 0(warning)인 경우

## 프로젝트 구조

```
config/settings.py   # 경로, 필수 컬럼, 허용값 등 설정
core/models.py        # Product, ValidationIssue 데이터 모델
core/loader.py         # CSV -> Product 리스트 로딩
core/rules.py           # 검증 규칙 및 run_all_rules()
tests/test_rules.py     # pytest 기반 규칙 테스트
data/dev/                # 개발용 샘플 데이터
```

## 실행

```bash
pip install -r requirements.txt
pytest
```

```python
from core.loader import load_products
from core.rules import run_all_rules
from config.settings import DEV_DATA_PATH

products = load_products(DEV_DATA_PATH)
issues = run_all_rules(products)
```
