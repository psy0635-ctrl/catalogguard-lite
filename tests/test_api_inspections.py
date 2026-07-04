# 역할: FastAPI CSV 검수 엔드포인트의 성공, 오류, 개인정보 마스킹 응답을 테스트합니다.
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import inspections as inspections_route
from config.settings import (
    DEV_DATA_PATH,
    MAX_CSV_ROWS,
    MAX_UPLOAD_SIZE_BYTES,
    REQUIRED_COLUMNS,
)
from core.inspection_service import InspectionReport
from core.product_template import build_product_template_csv, get_product_template_filename
from db.session import get_session


client = TestClient(app)
ENDPOINT = "/api/v1/inspections"

BASE_ROW = {
    "product_group_id": "G001",
    "product_id": "P001",
    "product_name": "기본 티셔츠",
    "category": "TOP",
    "color": "BLACK",
    "size": "M",
    "stock": "10",
    "price": "19900",
    "image_path": "image.jpg",
    "description": "안전한 상품 설명",
    "seller": "공식 판매자",
}

ALL_COLUMNS = [*REQUIRED_COLUMNS, "description", "seller"]


@pytest.fixture(autouse=True)
def fake_inspection_persistence(monkeypatch):
    fake_session = object()
    calls = []

    def override_session():
        yield fake_session

    def fake_save_inspection_report(session, *, source_filename, report):
        calls.append(
            {
                "session": session,
                "source_filename": source_filename,
                "report": report,
            }
        )
        return 123

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(
        inspections_route,
        "save_inspection_report",
        fake_save_inspection_report,
        raising=False,
    )

    yield SimpleNamespace(session=fake_session, calls=calls)

    app.dependency_overrides.clear()


def make_csv_text(
    rows: list[dict[str, str]] | None = None,
    *,
    columns: list[str] | None = None,
    row_count: int | None = None,
) -> str:
    csv_columns = columns or ALL_COLUMNS
    source_rows = rows or [BASE_ROW]
    if row_count is not None:
        source_rows = [BASE_ROW] * row_count

    lines = [",".join(csv_columns)]
    for row in source_rows:
        lines.append(",".join(row.get(column.strip(), "") for column in csv_columns))
    return "\n".join(lines) + "\n"


def post_csv(
    file_bytes: bytes,
    *,
    filename: str = "products.csv",
    content_type: str = "text/csv",
):
    return client.post(
        ENDPOINT,
        files={"file": (filename, file_bytes, content_type)},
    )


def test_inspection_api_accepts_template_csv_with_no_issues():
    response = post_csv(
        build_product_template_csv(),
        filename=get_product_template_filename(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "inspection_run_id": 123,
        "summary": {
            "total_products": 1,
            "total_issues": 0,
            "error_count": 0,
            "warning_count": 0,
        },
        "results": [],
    }


def test_inspection_api_persists_report_and_returns_inspection_run_id(
    fake_inspection_persistence,
):
    response = post_csv(DEV_DATA_PATH.read_bytes(), filename="products_dev.csv")

    assert response.status_code == 200
    data = response.json()
    assert data["inspection_run_id"] == 123
    assert isinstance(data["inspection_run_id"], int)
    assert len(fake_inspection_persistence.calls) == 1

    call = fake_inspection_persistence.calls[0]
    assert call["session"] is fake_inspection_persistence.session
    assert call["source_filename"] == "products_dev.csv"
    assert isinstance(call["report"], InspectionReport)
    assert call["report"].summary.total_products == data["summary"]["total_products"]
    assert call["report"].summary.total_issues == data["summary"]["total_issues"]
    assert len(call["report"].result_dataframe) == data["summary"]["total_issues"]


def test_inspection_api_returns_expected_products_dev_summary():
    response = post_csv(DEV_DATA_PATH.read_bytes())

    assert response.status_code == 200
    data = response.json()
    assert data["summary"] == {
        "total_products": 5,
        "total_issues": 6,
        "error_count": 6,
        "warning_count": 0,
    }
    assert len(data["results"]) == 6


def test_inspection_api_returns_existing_presentation_fields_as_snake_case():
    response = post_csv(DEV_DATA_PATH.read_bytes())

    assert response.status_code == 200
    result = response.json()["results"][0]
    assert set(result) == {
        "status",
        "product_group_id",
        "product_id",
        "error_field",
        "reason",
        "recommendation",
        "risk_level",
    }
    assert result["status"] == "오류"
    assert result["error_field"] == "상품 ID 중복"
    assert result["risk_level"] == "높음"


def test_inspection_api_result_contains_representative_price_error():
    response = post_csv(DEV_DATA_PATH.read_bytes())

    assert response.status_code == 200
    reasons = [item["reason"] for item in response.json()["results"]]
    assert "상품 가격이 0 이하입니다. 현재 가격: -5,000원." in reasons
    assert "상품 가격이 0 이하입니다. 현재 가격: 0원." in reasons


def test_inspection_api_missing_file_field_returns_422():
    response = client.post(ENDPOINT)

    assert response.status_code == 422


def test_inspection_api_rejects_non_csv_extension():
    response = post_csv(make_csv_text().encode("utf-8"), filename="products.txt")

    assert response.status_code == 400
    assert response.json()["detail"] == "CSV 파일만 업로드할 수 있습니다."


def test_inspection_api_rejects_empty_file():
    response = post_csv(b"")

    assert response.status_code == 400
    assert response.json()["detail"] == "업로드한 파일이 비어 있습니다."


def test_inspection_api_does_not_persist_when_csv_validation_fails(
    fake_inspection_persistence,
):
    response = post_csv(b"")

    assert response.status_code == 400
    assert fake_inspection_persistence.calls == []


def test_inspection_api_rejects_bad_csv_quotes():
    csv_text = (
        ",".join(REQUIRED_COLUMNS)
        + '\nG001,P001,"닫히지 않은 상품명,TOP,BLACK,M,5,19000,a.jpg\n'
    )

    response = post_csv(csv_text.encode("utf-8"))

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "CSV 형식이 올바르지 않습니다. 따옴표와 열 개수를 확인해 주세요."
    )


def test_inspection_api_rejects_missing_required_column():
    columns = [column for column in REQUIRED_COLUMNS if column != "price"]
    response = post_csv(make_csv_text(columns=columns).encode("utf-8"))

    assert response.status_code == 400
    assert response.json()["detail"] == "필수 컬럼이 없습니다: price"


def test_inspection_api_rejects_header_only_csv():
    response = post_csv((",".join(REQUIRED_COLUMNS) + "\n").encode("utf-8"))

    assert response.status_code == 400
    assert response.json()["detail"] == "CSV에 상품 데이터가 없습니다."


def test_inspection_api_rejects_nul_bytes():
    response = post_csv(b"product_id,product_name\x00,category\nP001,test,TOP\n")

    assert response.status_code == 400
    assert response.json()["detail"] == "일반적인 CSV 텍스트 파일이 아닙니다."


def test_inspection_api_rejects_duplicate_columns():
    columns = [
        "product_group_id",
        "product_id",
        "product_name",
        "product_id",
        "category",
        "color",
        "size",
        "stock",
        "price",
        "image_path",
    ]

    response = post_csv(make_csv_text(columns=columns).encode("utf-8"))

    assert response.status_code == 400
    assert response.json()["detail"] == "중복된 컬럼명이 있습니다: product_id"


def test_inspection_api_rejects_over_maximum_row_count():
    csv_text = make_csv_text(row_count=MAX_CSV_ROWS + 1)

    response = post_csv(csv_text.encode("utf-8"))

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "상품 데이터가 너무 많습니다. 최대 10,000행까지 지원합니다."
    )


def test_inspection_api_rejects_over_maximum_file_size():
    response = post_csv(b"x" * (MAX_UPLOAD_SIZE_BYTES + 1))

    assert response.status_code == 400
    assert response.json()["detail"] == (
        "파일 크기가 너무 큽니다. 최대 5MB까지 업로드할 수 있습니다."
    )


def test_inspection_api_accepts_utf8_csv():
    response = post_csv(make_csv_text().encode("utf-8"))

    assert response.status_code == 200
    assert response.json()["summary"]["total_products"] == 1


def test_inspection_api_accepts_utf8_bom_csv():
    response = post_csv(b"\xef\xbb\xbf" + make_csv_text().encode("utf-8"))

    assert response.status_code == 200
    assert response.json()["summary"]["total_products"] == 1


def test_inspection_api_accepts_cp949_csv():
    response = post_csv(make_csv_text().encode("cp949"))

    assert response.status_code == 200
    assert response.json()["summary"]["total_products"] == 1


def test_inspection_api_does_not_return_raw_personal_information():
    csv_text = make_csv_text(
        [
            {
                **BASE_ROW,
                "description": (
                    "문의 demo.user@example.com 010-1234-5678 "
                    "000000-1234567"
                ),
            }
        ]
    )

    response = post_csv(csv_text.encode("utf-8"))

    assert response.status_code == 200
    response_text = response.content.decode("utf-8")
    assert "demo.user@example.com" not in response_text
    assert "010-1234-5678" not in response_text
    assert "000000-1234567" not in response_text
    assert "de*******@example.com" in response_text
    assert "010-****-5678" in response_text
    assert "000000-*******" in response_text
    assert response.json()["summary"] == {
        "total_products": 1,
        "total_issues": 3,
        "error_count": 3,
        "warning_count": 0,
    }


def test_inspection_api_keeps_duplicate_product_id_detection():
    csv_text = make_csv_text(
        [
            BASE_ROW,
            {
                **BASE_ROW,
                "product_group_id": "G002",
                "product_id": "P001",
                "product_name": "다른 상품",
            },
        ]
    )

    response = post_csv(csv_text.encode("utf-8"))

    assert response.status_code == 200
    duplicate_results = [
        item
        for item in response.json()["results"]
        if item["error_field"] == "상품 ID 중복"
    ]
    assert len(duplicate_results) == 2


def test_inspection_api_keeps_normal_option_duplicate_name_exclusion():
    csv_text = make_csv_text(
        [
            BASE_ROW,
            {
                **BASE_ROW,
                "product_id": "P002",
                "color": "NAVY",
                "size": "L",
            },
        ]
    )

    response = post_csv(csv_text.encode("utf-8"))

    assert response.status_code == 200
    assert response.json()["summary"]["total_issues"] == 0
    assert response.json()["results"] == []


def test_inspection_api_keeps_price_anomaly_detection():
    rows = [
        {**BASE_ROW, "product_id": "P001", "price": "10000"},
        {**BASE_ROW, "product_id": "P002", "price": "10000"},
        {**BASE_ROW, "product_id": "P003", "price": "10000"},
        {**BASE_ROW, "product_id": "P004", "price": "10000"},
        {**BASE_ROW, "product_id": "P005", "price": "100000"},
    ]

    response = post_csv(make_csv_text(rows).encode("utf-8"))

    assert response.status_code == 200
    assert any(
        item["error_field"] == "가격 이상치" for item in response.json()["results"]
    )


def test_inspection_api_keeps_category_mismatch_detection():
    csv_text = make_csv_text([{**BASE_ROW, "product_name": "가죽 부츠", "category": "TOP"}])

    response = post_csv(csv_text.encode("utf-8"))

    assert response.status_code == 200
    assert response.json()["results"][0]["error_field"] == "상품명·카테고리 불일치"


def test_inspection_api_keeps_prohibited_term_detection():
    csv_text = make_csv_text([{**BASE_ROW, "product_name": "카톡 문의 상품"}])

    response = post_csv(csv_text.encode("utf-8"))

    assert response.status_code == 200
    assert response.json()["results"][0]["error_field"] == "금지어 포함"
