# 역할: FastAPI CSV 검수 엔드포인트의 성공, 오류, 개인정보 마스킹 응답을 테스트합니다.
import hashlib
from datetime import datetime, timezone
from types import SimpleNamespace

import pytest
from fastapi.testclient import TestClient

from api.main import app
from api.routes import inspections as inspections_route
from config.settings import (
    DEV_DATA_PATH,
    INSPECTION_VERSION,
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
    detail_calls = []
    detail_created_at = datetime(2026, 7, 4, 3, 30, tzinfo=timezone.utc)
    detail_results = [
        SimpleNamespace(
            status="오류",
            product_group_id="G002",
            product_id="P003",
            error_field="상품 ID 중복",
            reason="동일한 상품 ID가 여러 상품에 사용되었습니다.",
            recommendation="각 상품에 고유한 상품 ID를 입력하십시오.",
            risk_level="높음",
        ),
        SimpleNamespace(
            status="주의",
            product_group_id="G003",
            product_id="P004",
            error_field="품절 상품",
            reason="재고가 0개인 품절 상품입니다.",
            recommendation="판매 상태와 재입고 여부를 확인하세요.",
            risk_level="낮음",
        ),
    ]
    list_calls = []
    save_state = SimpleNamespace(mode="created")
    list_state = SimpleNamespace(mode="default")
    list_created_at = datetime(2026, 7, 4, 4, 30, tzinfo=timezone.utc)
    default_list = SimpleNamespace(
        items=[
            SimpleNamespace(
                inspection_run_id=12,
                source_filename="template.csv",
                created_at=list_created_at,
                total_products=1,
                total_issues=0,
                error_count=0,
                warning_count=0,
            ),
            SimpleNamespace(
                inspection_run_id=11,
                source_filename="products_dev.csv",
                created_at=list_created_at,
                total_products=5,
                total_issues=2,
                error_count=1,
                warning_count=1,
            ),
        ],
        total=2,
        limit=20,
        offset=0,
    )
    paged_list = SimpleNamespace(
        items=[
            SimpleNamespace(
                inspection_run_id=3,
                source_filename="old_products.csv",
                created_at=list_created_at,
                total_products=8,
                total_issues=4,
                error_count=3,
                warning_count=1,
            )
        ],
        total=37,
        limit=10,
        offset=20,
    )
    fake_details = {
        11: SimpleNamespace(
            inspection_run_id=11,
            source_filename="products_dev.csv",
            created_at=detail_created_at,
            total_products=5,
            total_issues=2,
            error_count=1,
            warning_count=1,
            results=detail_results,
        ),
        12: SimpleNamespace(
            inspection_run_id=12,
            source_filename="template.csv",
            created_at=detail_created_at,
            total_products=1,
            total_issues=0,
            error_count=0,
            warning_count=0,
            results=[],
        ),
    }

    def override_session():
        yield fake_session

    def fake_save_inspection_report(
        session,
        *,
        source_filename,
        report,
        file_sha256=None,
        inspection_version=None,
    ):
        calls.append(
            {
                "session": session,
                "source_filename": source_filename,
                "report": report,
                "file_sha256": file_sha256,
                "inspection_version": inspection_version,
            }
        )
        if save_state.mode == "duplicate":
            return SimpleNamespace(inspection_run_id=11, created=False)
        return SimpleNamespace(inspection_run_id=123, created=True)

    def fake_get_inspection_detail(session, *, inspection_run_id):
        detail_calls.append(
            {
                "session": session,
                "inspection_run_id": inspection_run_id,
            }
        )
        return fake_details.get(inspection_run_id)

    def fake_list_inspections(
        session,
        *,
        limit,
        offset,
        filename=None,
        created_at_start=None,
        created_at_end_exclusive=None,
    ):
        list_call = {
            "session": session,
            "limit": limit,
            "offset": offset,
        }
        if filename is not None:
            list_call["filename"] = filename
        if created_at_start is not None:
            list_call["created_at_start"] = created_at_start
        if created_at_end_exclusive is not None:
            list_call["created_at_end_exclusive"] = created_at_end_exclusive
        list_calls.append(list_call)
        if list_state.mode == "empty":
            return SimpleNamespace(items=[], total=0, limit=limit, offset=offset)
        if limit == 10 and offset == 20:
            return paged_list
        return default_list

    app.dependency_overrides[get_session] = override_session
    monkeypatch.setattr(
        inspections_route,
        "save_inspection_report",
        fake_save_inspection_report,
        raising=False,
    )
    monkeypatch.setattr(
        inspections_route,
        "get_inspection_detail",
        fake_get_inspection_detail,
        raising=False,
    )
    monkeypatch.setattr(
        inspections_route,
        "list_inspections",
        fake_list_inspections,
        raising=False,
    )

    yield SimpleNamespace(
        session=fake_session,
        calls=calls,
        detail_calls=detail_calls,
        list_calls=list_calls,
        list_state=list_state,
        save_state=save_state,
    )

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


def test_list_inspections_api_returns_default_page(fake_inspection_persistence):
    response = client.get(ENDPOINT)

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 2
    assert data["limit"] == 20
    assert data["offset"] == 0
    assert [item["inspection_run_id"] for item in data["items"]] == [12, 11]
    assert data["items"][0] == {
        "inspection_run_id": 12,
        "source_filename": "template.csv",
        "created_at": data["items"][0]["created_at"],
        "total_products": 1,
        "total_issues": 0,
        "error_count": 0,
        "warning_count": 0,
    }
    assert data["items"][0]["created_at"].startswith("2026-07-04T04:30:00")
    assert fake_inspection_persistence.list_calls == [
        {
            "session": fake_inspection_persistence.session,
            "limit": 20,
            "offset": 0,
        }
    ]


def test_list_inspections_api_passes_limit_and_offset(fake_inspection_persistence):
    response = client.get(f"{ENDPOINT}?limit=10&offset=20")

    assert response.status_code == 200
    data = response.json()
    assert data["total"] == 37
    assert data["limit"] == 10
    assert data["offset"] == 20
    assert len(data["items"]) == 1
    assert data["items"][0]["inspection_run_id"] == 3
    assert fake_inspection_persistence.list_calls == [
        {
            "session": fake_inspection_persistence.session,
            "limit": 10,
            "offset": 20,
        }
    ]


def test_list_inspections_api_passes_trimmed_filename(
    fake_inspection_persistence,
):
    response = client.get(
        ENDPOINT,
        params={"limit": 10, "offset": 0, "filename": "  products  "},
    )

    assert response.status_code == 200
    assert fake_inspection_persistence.list_calls == [
        {
            "session": fake_inspection_persistence.session,
            "limit": 10,
            "offset": 0,
            "filename": "products",
        }
    ]


def test_list_inspections_api_treats_blank_filename_as_no_filter(
    fake_inspection_persistence,
):
    response = client.get(ENDPOINT, params={"filename": "   "})

    assert response.status_code == 200
    assert fake_inspection_persistence.list_calls == [
        {
            "session": fake_inspection_persistence.session,
            "limit": 20,
            "offset": 0,
        }
    ]


def test_list_inspections_api_passes_start_and_end_dates_as_utc_bounds(
    fake_inspection_persistence,
):
    response = client.get(
        ENDPOINT,
        params={
            "start_date": "2026-07-01",
            "end_date": "2026-07-05",
        },
    )

    assert response.status_code == 200
    assert fake_inspection_persistence.list_calls == [
        {
            "session": fake_inspection_persistence.session,
            "limit": 20,
            "offset": 0,
            "created_at_start": datetime(2026, 6, 30, 15, 0, tzinfo=timezone.utc),
            "created_at_end_exclusive": datetime(
                2026,
                7,
                5,
                15,
                0,
                tzinfo=timezone.utc,
            ),
        }
    ]


def test_list_inspections_api_passes_start_date_only(
    fake_inspection_persistence,
):
    response = client.get(ENDPOINT, params={"start_date": "2026-07-01"})

    assert response.status_code == 200
    assert fake_inspection_persistence.list_calls == [
        {
            "session": fake_inspection_persistence.session,
            "limit": 20,
            "offset": 0,
            "created_at_start": datetime(2026, 6, 30, 15, 0, tzinfo=timezone.utc),
        }
    ]


def test_list_inspections_api_passes_end_date_only(
    fake_inspection_persistence,
):
    response = client.get(ENDPOINT, params={"end_date": "2026-07-05"})

    assert response.status_code == 200
    assert fake_inspection_persistence.list_calls == [
        {
            "session": fake_inspection_persistence.session,
            "limit": 20,
            "offset": 0,
            "created_at_end_exclusive": datetime(
                2026,
                7,
                5,
                15,
                0,
                tzinfo=timezone.utc,
            ),
        }
    ]


def test_list_inspections_api_passes_filename_and_date_filters_together(
    fake_inspection_persistence,
):
    response = client.get(
        ENDPOINT,
        params={
            "filename": "  products  ",
            "start_date": "2026-07-01",
            "end_date": "2026-07-05",
            "limit": 10,
            "offset": 20,
        },
    )

    assert response.status_code == 200
    assert fake_inspection_persistence.list_calls == [
        {
            "session": fake_inspection_persistence.session,
            "limit": 10,
            "offset": 20,
            "filename": "products",
            "created_at_start": datetime(2026, 6, 30, 15, 0, tzinfo=timezone.utc),
            "created_at_end_exclusive": datetime(
                2026,
                7,
                5,
                15,
                0,
                tzinfo=timezone.utc,
            ),
        }
    ]


def test_list_inspections_api_accepts_same_start_and_end_date(
    fake_inspection_persistence,
):
    response = client.get(
        ENDPOINT,
        params={"start_date": "2026-07-05", "end_date": "2026-07-05"},
    )

    assert response.status_code == 200
    assert fake_inspection_persistence.list_calls == [
        {
            "session": fake_inspection_persistence.session,
            "limit": 20,
            "offset": 0,
            "created_at_start": datetime(2026, 7, 4, 15, 0, tzinfo=timezone.utc),
            "created_at_end_exclusive": datetime(
                2026,
                7,
                5,
                15,
                0,
                tzinfo=timezone.utc,
            ),
        }
    ]


def test_list_inspections_api_rejects_start_date_after_end_date_without_service_call(
    fake_inspection_persistence,
):
    response = client.get(
        ENDPOINT,
        params={"start_date": "2026-07-06", "end_date": "2026-07-05"},
    )

    assert response.status_code == 422
    assert response.json()["detail"] == "시작일은 종료일보다 늦을 수 없습니다."
    assert fake_inspection_persistence.list_calls == []


@pytest.mark.parametrize("query", ["start_date=2026-99-99", "end_date=bad-date"])
def test_list_inspections_api_rejects_invalid_date_format_without_service_call(
    fake_inspection_persistence,
    query,
):
    response = client.get(f"{ENDPOINT}?{query}")

    assert response.status_code == 422
    assert fake_inspection_persistence.list_calls == []


def test_list_inspections_api_accepts_100_character_filename(
    fake_inspection_persistence,
):
    filename = "a" * 100

    response = client.get(ENDPOINT, params={"filename": filename})

    assert response.status_code == 200
    assert fake_inspection_persistence.list_calls == [
        {
            "session": fake_inspection_persistence.session,
            "limit": 20,
            "offset": 0,
            "filename": filename,
        }
    ]


def test_list_inspections_api_rejects_too_long_filename_without_service_call(
    fake_inspection_persistence,
):
    response = client.get(ENDPOINT, params={"filename": "a" * 101})

    assert response.status_code == 422
    assert fake_inspection_persistence.list_calls == []


def test_list_inspections_api_returns_empty_list(fake_inspection_persistence):
    fake_inspection_persistence.list_state.mode = "empty"

    response = client.get(ENDPOINT)

    assert response.status_code == 200
    assert response.json() == {
        "items": [],
        "total": 0,
        "limit": 20,
        "offset": 0,
    }


@pytest.mark.parametrize("query", ["limit=0", "limit=101", "offset=-1"])
def test_list_inspections_api_rejects_invalid_query_without_service_call(
    fake_inspection_persistence,
    query,
):
    response = client.get(f"{ENDPOINT}?{query}")

    assert response.status_code == 422
    assert fake_inspection_persistence.list_calls == []


def test_get_inspection_api_returns_saved_inspection_detail(
    fake_inspection_persistence,
):
    response = client.get(f"{ENDPOINT}/11")

    assert response.status_code == 200
    data = response.json()
    assert data["inspection_run_id"] == 11
    assert data["source_filename"] == "products_dev.csv"
    assert data["created_at"].startswith("2026-07-04T03:30:00")
    assert data["summary"] == {
        "total_products": 5,
        "total_issues": 2,
        "error_count": 1,
        "warning_count": 1,
    }
    assert len(data["results"]) == 2
    assert set(data["results"][0]) == {
        "status",
        "product_group_id",
        "product_id",
        "error_field",
        "reason",
        "recommendation",
        "risk_level",
    }
    assert data["results"][0] == {
        "status": "오류",
        "product_group_id": "G002",
        "product_id": "P003",
        "error_field": "상품 ID 중복",
        "reason": "동일한 상품 ID가 여러 상품에 사용되었습니다.",
        "recommendation": "각 상품에 고유한 상품 ID를 입력하십시오.",
        "risk_level": "높음",
    }
    assert len(fake_inspection_persistence.detail_calls) == 1
    detail_call = fake_inspection_persistence.detail_calls[0]
    assert detail_call["session"] is fake_inspection_persistence.session
    assert detail_call["inspection_run_id"] == 11


def test_get_inspection_api_returns_404_when_inspection_is_missing(
    fake_inspection_persistence,
):
    response = client.get(f"{ENDPOINT}/999999")

    assert response.status_code == 404
    assert response.json() == {"detail": "검수 실행 결과를 찾을 수 없습니다."}
    assert len(fake_inspection_persistence.detail_calls) == 1
    assert fake_inspection_persistence.detail_calls[0]["inspection_run_id"] == 999999


def test_get_inspection_api_rejects_invalid_id_without_service_call(
    fake_inspection_persistence,
):
    response = client.get(f"{ENDPOINT}/abc")

    assert response.status_code == 422
    assert fake_inspection_persistence.detail_calls == []


def test_get_inspection_api_returns_empty_results(
    fake_inspection_persistence,
):
    response = client.get(f"{ENDPOINT}/12")

    assert response.status_code == 200
    data = response.json()
    assert data["inspection_run_id"] == 12
    assert data["summary"] == {
        "total_products": 1,
        "total_issues": 0,
        "error_count": 0,
        "warning_count": 0,
    }
    assert data["results"] == []


def test_inspection_api_accepts_template_csv_with_no_issues():
    response = post_csv(
        build_product_template_csv(),
        filename=get_product_template_filename(),
    )

    assert response.status_code == 200
    assert response.json() == {
        "inspection_run_id": 123,
        "created": True,
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
    assert data["created"] is True
    assert len(fake_inspection_persistence.calls) == 1

    call = fake_inspection_persistence.calls[0]
    assert call["session"] is fake_inspection_persistence.session
    assert call["source_filename"] == "products_dev.csv"
    assert call["file_sha256"] == hashlib.sha256(DEV_DATA_PATH.read_bytes()).hexdigest()
    assert call["inspection_version"] == INSPECTION_VERSION
    assert isinstance(call["report"], InspectionReport)
    assert call["report"].summary.total_products == data["summary"]["total_products"]
    assert call["report"].summary.total_issues == data["summary"]["total_issues"]
    assert len(call["report"].result_dataframe) == data["summary"]["total_issues"]


def test_inspection_api_returns_existing_detail_when_duplicate(
    fake_inspection_persistence,
):
    fake_inspection_persistence.save_state.mode = "duplicate"

    response = post_csv(DEV_DATA_PATH.read_bytes(), filename="renamed.csv")

    assert response.status_code == 200
    data = response.json()
    assert data["inspection_run_id"] == 11
    assert data["created"] is False
    assert data["summary"] == {
        "total_products": 5,
        "total_issues": 2,
        "error_count": 1,
        "warning_count": 1,
    }
    assert [item["error_field"] for item in data["results"]] == [
        "상품 ID 중복",
        "품절 상품",
    ]
    assert fake_inspection_persistence.detail_calls == [
        {
            "session": fake_inspection_persistence.session,
            "inspection_run_id": 11,
        }
    ]


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
