# 역할: Streamlit 앱이 업로드 전 초기 화면에서 예외 없이 렌더링되는지 테스트합니다.
from clients import catalogguard_api
from core import inspection_service
from streamlit.testing.v1 import AppTest


GROUP_CATEGORY_TEST_CSV = """product_group_id,product_id,product_name,category,color,size,stock,price,image_path
G001,P001,기본 반팔 티셔츠 블랙,TOP,BLACK,M,10,19900,image1.jpg
G001,P002,기본 반팔 티셔츠 화이트,TOP,WHITE,M,10,19900,image2.jpg
G001,P003,기본 반팔 티셔츠 네이비,SHOES,NAVY,M,10,19900,image3.jpg
G002,P004,데님 팬츠 블랙,BOTTOM,BLACK,28,10,39900,image4.jpg
G002,P005,데님 팬츠 블루,bottom,BLUE,30,10,39900,image5.jpg
G003,P006,가죽 가방,BAG,BLACK,FREE,5,79000,image6.jpg
""".encode("utf-8")
VALID_REQUEST_ID = "a29ae9a1c62f4152bb96f6513c323d96"
JOB_ID = "12345678-1234-5678-1234-567812345678"
SECOND_JOB_ID = "87654321-4321-8765-4321-876543218765"


GROUP_CATEGORY_RESULTS = [
    {
        "status": "오류",
        "product_group_id": "G001",
        "product_id": product_id,
        "error_field": "상품 그룹 카테고리 불일치",
        "reason": (
            "상품 그룹 'G001'에 서로 다른 카테고리 'TOP', 'SHOES'가 "
            "함께 등록되어 있습니다."
        ),
        "recommendation": (
            "같은 상품 그룹의 상품이 동일한 카테고리를 사용하도록 "
            "product_group_id 또는 category 값을 확인하세요."
        ),
        "risk_level": "중간",
    }
    for product_id in ("P001", "P002", "P003")
]
GROUP_CATEGORY_RESULTS.extend(
    [
        {
            "status": "오류",
            "product_group_id": product_group_id,
            "product_id": product_id,
            "error_field": "카테고리 오류",
            "reason": reason,
            "recommendation": "허용된 카테고리 값으로 수정하세요.",
            "risk_level": "중간",
        }
        for product_group_id, product_id, reason in (
            ("G001", "P003", "카테고리 'SHOES'는 허용된 카테고리가 아닙니다."),
            ("G002", "P005", "카테고리 'bottom'는 허용된 카테고리가 아닙니다."),
            ("G003", "P006", "카테고리 'BAG'는 허용된 카테고리가 아닙니다."),
        )
    ]
)
GROUP_CATEGORY_RESULTS.append(
    {
        "status": "주의",
        "product_group_id": "G001",
        "product_id": "P003",
        "error_field": "상품명·카테고리 불일치",
        "reason": (
            "상품명에서 '티셔츠'가 확인되어 상의 상품으로 추정되지만 "
            "현재 카테고리는 '신발'입니다."
        ),
        "recommendation": (
            "상품명과 카테고리를 확인하고 올바른 카테고리로 수정하십시오."
        ),
        "risk_level": "중간",
    }
)


def make_create_response(*, created):
    return {
        "inspection_run_id": 10,
        "created": created,
        "summary": {
            "total_products": 6,
            "total_issues": 7,
            "error_count": 6,
            "warning_count": 1,
        },
        "results": GROUP_CATEGORY_RESULTS,
    }


def make_detail_response():
    return {
        **make_create_response(created=True),
        "source_filename": "group_category_consistency_test.csv",
        "created_at": "2026-07-20T12:00:00+09:00",
    }


def make_job_status_response(
    status,
    *,
    created=True,
    inspection_run_id=10,
):
    response = {
        "job_id": JOB_ID,
        "status": status,
        "created": None,
        "inspection_run_id": None,
        "summary": None,
        "error_code": None,
        "message": None,
    }
    if status == "succeeded":
        response.update(
            created=created,
            inspection_run_id=inspection_run_id,
            summary=make_create_response(created=created)["summary"],
        )
    if status == "failed":
        response.update(
            error_code="inspection_failed",
            message="Traceback: redis://secret-internal:6379/0",
        )
    return response


def make_job_submission_response(job_id=JOB_ID):
    return {
        "job_id": job_id,
        "status": "queued",
        "status_url": f"/api/v1/inspection-jobs/{job_id}",
    }


class FakeInspectionApiClient:
    def __init__(
        self,
        *,
        created=True,
        create_error=None,
        async_statuses=None,
        submit_error=None,
        submit_responses=None,
        status_error=None,
        detail_error=None,
        detail_responses=None,
    ):
        self.created = created
        self.create_error = create_error
        self.async_statuses = list(async_statuses or [])
        self.submit_error = submit_error
        self.submit_responses = list(submit_responses or [])
        self.status_error = status_error
        self.detail_error = detail_error
        self.detail_responses = list(detail_responses or [])
        self.create_calls = []
        self.detail_calls = []
        self.submit_calls = []
        self.status_calls = []

    def create_inspection(self, **kwargs):
        self.create_calls.append(kwargs)
        if self.create_error is not None:
            raise self.create_error
        return make_create_response(created=self.created)

    def get_inspection_detail(self, inspection_run_id):
        self.detail_calls.append(inspection_run_id)
        if self.detail_responses:
            response = self.detail_responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        if self.detail_error is not None:
            raise self.detail_error
        return make_detail_response()

    def submit_inspection_job(self, **kwargs):
        self.submit_calls.append(kwargs)
        if self.submit_responses:
            response = self.submit_responses.pop(0)
            if isinstance(response, Exception):
                raise response
            return response
        if self.submit_error is not None:
            raise self.submit_error
        return make_job_submission_response()

    def get_inspection_job(self, job_id):
        self.status_calls.append(job_id)
        if self.status_error is not None:
            raise self.status_error
        if self.async_statuses:
            return self.async_statuses.pop(0)
        return make_job_status_response("queued")

    def list_inspections(self, **params):
        return {"items": [], "total": 0, "limit": params["limit"], "offset": 0}


def find_widget(widgets, label):
    return next(widget for widget in widgets if widget.label == label)


def find_result_dataframe(app):
    expected_columns = {
        "검수 상태",
        "오류 항목",
        "상품 그룹 ID",
        "상품 ID",
        "오류 이유",
        "수정 권장사항",
        "위험 수준",
    }
    return next(
        dataframe.value
        for dataframe in app.dataframe
        if set(dataframe.value.columns) == expected_columns
    )


def test_app_initial_render_without_upload(monkeypatch):
    monkeypatch.delenv("CATALOGGUARD_API_BASE_URL", raising=False)
    app = AppTest.from_file("app.py")

    app.run(timeout=10)

    assert len(app.exception) == 0
    assert [title.value for title in app.title] == ["CatalogGuard Lite"]
    assert "CSV 입력 템플릿" in [subheader.value for subheader in app.subheader]
    assert "검수 이력" in [subheader.value for subheader in app.subheader]
    assert [uploader.label for uploader in app.file_uploader] == ["CSV 파일 업로드"]
    assert find_widget(app.radio, "검수 방식").value == "즉시 검수"
    assert "검사할 CSV 파일을 업로드해 주세요." in [
        info.value for info in app.info
    ]
    assert "검수 이력 API 주소가 설정되지 않았습니다." in [
        warning.value for warning in app.warning
    ]
    assert app.session_state["history_view_mode"] == "list"
    assert app.session_state["selected_inspection_run_id"] is None
    assert app.session_state["history_offset"] == 0
    assert app.session_state["history_filename_input"] == ""
    assert app.session_state["history_filename_query"] == ""
    assert app.session_state["history_status_input"] == "전체"
    assert app.session_state["history_status_query"] is None


def test_app_upload_filters_and_downloads_group_category_results(monkeypatch):
    api_client = FakeInspectionApiClient(created=True)
    local_inspection_calls = []
    real_inspect_dataframe = inspection_service.inspect_dataframe

    def spy_inspect_dataframe(dataframe):
        local_inspection_calls.append(dataframe)
        return real_inspect_dataframe(dataframe)

    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    monkeypatch.setattr(
        inspection_service,
        "inspect_dataframe",
        spy_inspect_dataframe,
    )
    app = AppTest.from_file("app.py").run(timeout=10)

    app.file_uploader[0].upload(
        "group_category_consistency_test.csv",
        GROUP_CATEGORY_TEST_CSV,
        "text/csv",
    ).run(timeout=10)

    assert len(app.exception) == 0
    assert local_inspection_calls == []
    assert api_client.create_calls == []
    assert api_client.submit_calls == []
    assert api_client.detail_calls == []
    assert find_widget(app.button, "검수 실행 및 이력 저장") is not None

    find_widget(app.button, "검수 실행 및 이력 저장").click().run(timeout=10)

    assert len(app.exception) == 0
    assert local_inspection_calls == []
    assert len(api_client.create_calls) == 1
    assert api_client.submit_calls == []
    assert api_client.create_calls[0]["file_content"] == GROUP_CATEGORY_TEST_CSV
    assert api_client.detail_calls == [10]
    assert app.session_state["saved_inspection_run_id"] == 10
    assert app.session_state["current_inspection_created"] is True
    assert app.session_state["current_inspection_detail_response"] == (
        make_detail_response()
    )
    assert "검수 결과를 새 이력으로 저장했습니다. 실행 ID: 10" in [
        success.value for success in app.success
    ]
    metrics = {metric.label: metric.value for metric in app.metric}
    assert metrics == {
        "전체 상태": "오류",
        "전체 상품 수": "6",
        "전체 문제 수": "7",
        "오류 수": "6",
        "주의 수": "1",
    }

    preview = app.dataframe[0].value
    assert preview["product_id"].tolist() == [
        "P001",
        "P002",
        "P003",
        "P004",
        "P005",
        "P006",
    ]
    assert preview["category"].tolist() == [
        "TOP",
        "TOP",
        "SHOES",
        "BOTTOM",
        "bottom",
        "BAG",
    ]

    results = find_result_dataframe(app)
    category_results = results[
        results["오류 항목"] == "상품 그룹 카테고리 불일치"
    ]
    assert category_results["상품 ID"].tolist() == ["P001", "P002", "P003"]
    assert set(category_results["검수 상태"]) == {"오류"}
    assert set(category_results["위험 수준"]) == {"중간"}
    assert all(
        "'TOP', 'SHOES'" in reason
        for reason in category_results["오류 이유"]
    )
    assert all(
        "product_group_id 또는 category" in recommendation
        for recommendation in category_results["수정 권장사항"]
    )
    assert not any(
        "inconsistent_group_category" in reason
        for reason in results["오류 이유"]
    )
    assert "상품 그룹 카테고리 불일치" in app.selectbox[1].options
    assert not {
        "색상 표기 비표준",
        "사이즈 표기 비표준",
        "상품 옵션 조합 중복",
    } & set(results["오류 항목"])

    find_widget(app.selectbox, "검수 상태").select("오류").run(timeout=10)

    assert len(app.exception) == 0
    assert "현재 조건에 맞는 검수 결과: 6건" in [
        caption.value for caption in app.caption
    ]
    assert set(find_result_dataframe(app)["검수 상태"]) == {"오류"}

    find_widget(app.selectbox, "오류 항목").select(
        "상품 그룹 카테고리 불일치"
    ).run(timeout=10)

    assert len(app.exception) == 0
    assert "현재 조건에 맞는 검수 결과: 3건" in [
        caption.value for caption in app.caption
    ]
    assert find_result_dataframe(app)["상품 ID"].tolist() == [
        "P001",
        "P002",
        "P003",
    ]

    find_widget(app.text_input, "상품 ID 검색").input("P003").run(timeout=10)

    assert len(app.exception) == 0
    assert "현재 조건에 맞는 검수 결과: 1건" in [
        caption.value for caption in app.caption
    ]
    assert find_result_dataframe(app)["상품 ID"].tolist() == ["P003"]
    result_downloads = [
        download
        for download in app.get("download_button")
        if download.proto.label == "현재 필터 결과 CSV 다운로드"
    ]
    assert len(result_downloads) == 1
    assert result_downloads[0].proto.url.endswith(".csv")
    assert len(api_client.create_calls) == 1
    assert api_client.detail_calls == [10]


def test_app_background_job_posts_once_refreshes_with_get_and_reuses_result_ui(
    monkeypatch,
):
    api_client = FakeInspectionApiClient(
        async_statuses=[
            make_job_status_response("running"),
            make_job_status_response("succeeded"),
        ]
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)
    find_widget(app.radio, "검수 방식").set_value("백그라운드 검수").run(
        timeout=10
    )
    app.file_uploader[0].upload(
        "group_category_consistency_test.csv",
        GROUP_CATEGORY_TEST_CSV,
        "text/csv",
    ).run(timeout=10)

    find_widget(app.button, "백그라운드 검수 시작").click().run(timeout=10)

    assert len(api_client.submit_calls) == 1
    assert api_client.create_calls == []
    assert api_client.status_calls == []
    assert app.session_state["async_job_id"] == JOB_ID
    assert app.session_state["async_job_status"] == "queued"
    assert "검수 작업이 대기 중입니다." in [info.value for info in app.info]

    app.run(timeout=10)
    assert len(api_client.submit_calls) == 1
    assert api_client.status_calls == []

    find_widget(app.button, "상태 새로고침").click().run(timeout=10)
    assert len(api_client.submit_calls) == 1
    assert api_client.status_calls == [JOB_ID]
    assert app.session_state["async_job_status"] == "running"
    assert "상품 데이터를 검수하고 있습니다." in [info.value for info in app.info]

    find_widget(app.button, "상태 새로고침").click().run(timeout=10)
    assert len(api_client.submit_calls) == 1
    assert api_client.status_calls == [JOB_ID, JOB_ID]
    assert api_client.detail_calls == [10]
    assert app.session_state["async_job_status"] == "succeeded"
    assert app.session_state["saved_inspection_run_id"] == 10
    assert "검수가 완료되었습니다." in [success.value for success in app.success]
    assert {metric.label: metric.value for metric in app.metric} == {
        "전체 상태": "오류",
        "전체 상품 수": "6",
        "전체 문제 수": "7",
        "오류 수": "6",
        "주의 수": "1",
    }

    app.run(timeout=10)
    assert len(api_client.submit_calls) == 1
    assert api_client.status_calls == [JOB_ID, JOB_ID]
    assert api_client.detail_calls == [10]


def test_app_background_duplicate_result_preserves_created_false(monkeypatch):
    api_client = FakeInspectionApiClient(
        created=False,
        async_statuses=[make_job_status_response("succeeded", created=False)],
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)
    find_widget(app.radio, "검수 방식").set_value("백그라운드 검수").run(
        timeout=10
    )
    app.file_uploader[0].upload(
        "products.csv", GROUP_CATEGORY_TEST_CSV, "text/csv"
    ).run(timeout=10)
    find_widget(app.button, "백그라운드 검수 시작").click().run(timeout=10)
    find_widget(app.button, "상태 새로고침").click().run(timeout=10)

    assert app.session_state["current_inspection_created"] is False
    assert "이미 검수한 동일 파일이므로 기존 검수 결과를 불러왔습니다. 실행 ID: 10" in [
        info.value for info in app.info
    ]
    assert len(api_client.submit_calls) == 1


def test_app_background_failed_job_hides_internal_error_and_keeps_sync_available(
    monkeypatch,
):
    api_client = FakeInspectionApiClient(
        async_statuses=[make_job_status_response("failed")]
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)
    find_widget(app.radio, "검수 방식").set_value("백그라운드 검수").run(
        timeout=10
    )
    app.file_uploader[0].upload(
        "products.csv", GROUP_CATEGORY_TEST_CSV, "text/csv"
    ).run(timeout=10)
    find_widget(app.button, "백그라운드 검수 시작").click().run(timeout=10)
    find_widget(app.button, "상태 새로고침").click().run(timeout=10)

    displayed_errors = [error.value for error in app.error]
    assert "검수 처리 중 오류가 발생했습니다." in displayed_errors
    assert all("Traceback" not in message for message in displayed_errors)
    assert all("redis://" not in message for message in displayed_errors)

    find_widget(app.radio, "검수 방식").set_value("즉시 검수").run(timeout=10)
    assert find_widget(app.button, "검수 실행 및 이력 저장") is not None
    assert "async_job_id" not in app.session_state


def test_app_background_failed_job_can_be_resubmitted_only_by_user_click(monkeypatch):
    api_client = FakeInspectionApiClient(
        async_statuses=[make_job_status_response("failed")],
        submit_responses=[
            make_job_submission_response(JOB_ID),
            make_job_submission_response(SECOND_JOB_ID),
        ],
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)
    find_widget(app.radio, "검수 방식").set_value("백그라운드 검수").run(
        timeout=10
    )
    app.file_uploader[0].upload(
        "products.csv", GROUP_CATEGORY_TEST_CSV, "text/csv"
    ).run(timeout=10)
    find_widget(app.button, "백그라운드 검수 시작").click().run(timeout=10)
    find_widget(app.button, "상태 새로고침").click().run(timeout=10)

    app.run(timeout=10)
    assert len(api_client.submit_calls) == 1
    assert app.session_state["async_job_id"] == JOB_ID

    find_widget(app.button, "백그라운드 검수 다시 시도").click().run(timeout=10)

    assert len(api_client.submit_calls) == 2
    assert app.session_state["async_job_id"] == SECOND_JOB_ID
    assert app.session_state["async_job_status"] == "queued"

    app.run(timeout=10)
    assert len(api_client.submit_calls) == 2


def test_app_new_upload_clears_background_job_state(monkeypatch):
    api_client = FakeInspectionApiClient()
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)
    find_widget(app.radio, "검수 방식").set_value("백그라운드 검수").run(
        timeout=10
    )
    app.file_uploader[0].upload(
        "first.csv", GROUP_CATEGORY_TEST_CSV, "text/csv"
    ).run(timeout=10)
    find_widget(app.button, "백그라운드 검수 시작").click().run(timeout=10)
    assert app.session_state["async_job_id"] == JOB_ID

    second_csv = GROUP_CATEGORY_TEST_CSV.replace(b"P006", b"P007")
    app.file_uploader[0].upload("first.csv", second_csv, "text/csv").run(
        timeout=10
    )

    assert "async_job_id" not in app.session_state
    assert "async_job_status" not in app.session_state
    assert len(api_client.submit_calls) == 1
    assert find_widget(app.button, "백그라운드 검수 시작") is not None


def test_app_background_submission_error_is_safe_and_does_not_store_job(monkeypatch):
    api_client = FakeInspectionApiClient(
        submit_error=catalogguard_api.CatalogGuardApiConnectionError(
            "redis://secret-internal:6379/0"
        )
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)
    find_widget(app.radio, "검수 방식").set_value("백그라운드 검수").run(
        timeout=10
    )
    app.file_uploader[0].upload(
        "products.csv", GROUP_CATEGORY_TEST_CSV, "text/csv"
    ).run(timeout=10)
    find_widget(app.button, "백그라운드 검수 시작").click().run(timeout=10)

    displayed = [error.value for error in app.error]
    assert "백그라운드 검수 서비스를 사용할 수 없습니다." in displayed
    assert all("redis://" not in message for message in displayed)
    assert "async_job_id" not in app.session_state
    assert len(api_client.submit_calls) == 1


def test_app_background_status_error_keeps_job_without_reposting(monkeypatch):
    api_client = FakeInspectionApiClient(
        status_error=catalogguard_api.CatalogGuardApiResponseError(
            "Traceback: secret"
        )
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)
    find_widget(app.radio, "검수 방식").set_value("백그라운드 검수").run(
        timeout=10
    )
    app.file_uploader[0].upload(
        "products.csv", GROUP_CATEGORY_TEST_CSV, "text/csv"
    ).run(timeout=10)
    find_widget(app.button, "백그라운드 검수 시작").click().run(timeout=10)
    find_widget(app.button, "상태 새로고침").click().run(timeout=10)

    displayed = [error.value for error in app.error]
    assert "작업 상태를 확인할 수 없습니다." in displayed
    assert all("Traceback" not in message for message in displayed)
    assert app.session_state["async_job_id"] == JOB_ID
    assert len(api_client.submit_calls) == 1
    assert api_client.status_calls == [JOB_ID]


def test_app_background_missing_run_id_is_reported_without_detail_request(monkeypatch):
    api_client = FakeInspectionApiClient(
        async_statuses=[
            make_job_status_response("succeeded", inspection_run_id=None)
        ]
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)
    find_widget(app.radio, "검수 방식").set_value("백그라운드 검수").run(
        timeout=10
    )
    app.file_uploader[0].upload(
        "products.csv", GROUP_CATEGORY_TEST_CSV, "text/csv"
    ).run(timeout=10)
    find_widget(app.button, "백그라운드 검수 시작").click().run(timeout=10)
    find_widget(app.button, "상태 새로고침").click().run(timeout=10)

    assert "완료된 검수 결과를 불러올 수 없습니다." in [
        error.value for error in app.error
    ]
    assert api_client.detail_calls == []
    assert "saved_inspection_run_id" not in app.session_state


def test_app_background_detail_retry_only_repeats_detail_get(monkeypatch):
    api_client = FakeInspectionApiClient(
        async_statuses=[
            make_job_status_response("succeeded"),
            make_job_status_response("succeeded"),
        ],
        detail_responses=[
            catalogguard_api.CatalogGuardApiResponseError(
                "postgresql://secret-internal/catalog"
            ),
            make_detail_response(),
        ],
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)
    find_widget(app.radio, "검수 방식").set_value("백그라운드 검수").run(
        timeout=10
    )
    app.file_uploader[0].upload(
        "products.csv", GROUP_CATEGORY_TEST_CSV, "text/csv"
    ).run(timeout=10)
    find_widget(app.button, "백그라운드 검수 시작").click().run(timeout=10)
    find_widget(app.button, "상태 새로고침").click().run(timeout=10)

    displayed = [error.value for error in app.error]
    assert "완료된 검수 결과를 불러올 수 없습니다." in displayed
    assert all("postgresql://" not in message for message in displayed)
    assert api_client.detail_calls == [10]
    assert api_client.status_calls == [JOB_ID]
    assert app.session_state["async_job_id"] == JOB_ID
    assert app.session_state["async_job_response"]["inspection_run_id"] == 10
    assert find_widget(app.button, "결과 다시 불러오기") is not None

    find_widget(app.button, "결과 다시 불러오기").click().run(timeout=10)

    assert len(api_client.submit_calls) == 1
    assert api_client.status_calls == [JOB_ID]
    assert api_client.detail_calls == [10, 10]
    assert app.session_state["saved_inspection_run_id"] == 10
    assert "async_job_error" not in app.session_state


def test_app_background_detail_not_found_preserves_completed_job(monkeypatch):
    api_client = FakeInspectionApiClient(
        async_statuses=[make_job_status_response("succeeded")],
        detail_responses=[
            catalogguard_api.InspectionNotFoundError("missing detail")
        ],
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)
    find_widget(app.radio, "검수 방식").set_value("백그라운드 검수").run(
        timeout=10
    )
    app.file_uploader[0].upload(
        "products.csv", GROUP_CATEGORY_TEST_CSV, "text/csv"
    ).run(timeout=10)
    find_widget(app.button, "백그라운드 검수 시작").click().run(timeout=10)
    find_widget(app.button, "상태 새로고침").click().run(timeout=10)

    assert app.session_state["async_job_id"] == JOB_ID
    assert app.session_state["async_job_status"] == "succeeded"
    assert app.session_state["async_job_response"]["inspection_run_id"] == 10
    assert find_widget(app.button, "결과 다시 불러오기") is not None


def test_app_inspection_mode_round_trip_does_not_call_any_inspection_api(monkeypatch):
    api_client = FakeInspectionApiClient()
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)
    app.file_uploader[0].upload(
        "products.csv", GROUP_CATEGORY_TEST_CSV, "text/csv"
    ).run(timeout=10)

    find_widget(app.radio, "검수 방식").set_value("백그라운드 검수").run(
        timeout=10
    )
    find_widget(app.radio, "검수 방식").set_value("즉시 검수").run(timeout=10)
    find_widget(app.radio, "검수 방식").set_value("백그라운드 검수").run(
        timeout=10
    )

    assert api_client.create_calls == []
    assert api_client.submit_calls == []
    assert api_client.status_calls == []
    assert api_client.detail_calls == []
    assert "async_job_id" not in app.session_state
    assert find_widget(app.button, "백그라운드 검수 시작") is not None


def test_app_duplicate_upload_loads_existing_server_result(monkeypatch):
    api_client = FakeInspectionApiClient(created=False)
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)

    app.file_uploader[0].upload(
        "group_category_consistency_test.csv",
        GROUP_CATEGORY_TEST_CSV,
        "text/csv",
    ).run(timeout=10)
    find_widget(app.button, "검수 실행 및 이력 저장").click().run(timeout=10)

    assert len(api_client.create_calls) == 1
    assert api_client.detail_calls == [10]
    assert app.session_state["current_inspection_created"] is False
    assert (
        "이미 검수한 동일 파일이므로 기존 검수 결과를 불러왔습니다. "
        "실행 ID: 10"
    ) in [info.value for info in app.info]
    assert len(find_result_dataframe(app)) == 7


def test_app_new_upload_clears_previous_server_result(monkeypatch):
    api_client = FakeInspectionApiClient(created=True)
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)
    app.file_uploader[0].upload(
        "first.csv",
        GROUP_CATEGORY_TEST_CSV,
        "text/csv",
    ).run(timeout=10)
    find_widget(app.button, "검수 실행 및 이력 저장").click().run(timeout=10)
    assert app.session_state["saved_inspection_run_id"] == 10

    second_csv = GROUP_CATEGORY_TEST_CSV.replace(b"P006", b"P007")
    app.file_uploader[0].upload(
        "second.csv",
        second_csv,
        "text/csv",
    ).run(timeout=10)

    assert "saved_inspection_run_id" not in app.session_state
    assert "current_inspection_detail_response" not in app.session_state
    assert all(metric.label != "전체 문제 수" for metric in app.metric)


def test_app_api_error_does_not_show_stale_success_result(monkeypatch):
    api_client = FakeInspectionApiClient(
        create_error=catalogguard_api.CatalogGuardApiResponseError(
            "bad request",
            request_id=VALID_REQUEST_ID,
        )
    )
    monkeypatch.setattr(
        catalogguard_api,
        "create_catalogguard_api_client",
        lambda: api_client,
    )
    app = AppTest.from_file("app.py").run(timeout=10)
    app.file_uploader[0].upload(
        "invalid.csv",
        GROUP_CATEGORY_TEST_CSV,
        "text/csv",
    ).run(timeout=10)
    find_widget(app.button, "검수 실행 및 이력 저장").click().run(timeout=10)

    assert len(app.exception) == 0
    assert len(api_client.create_calls) == 1
    assert api_client.detail_calls == []
    assert "검수를 완료하지 못했습니다." in [error.value for error in app.error]
    assert any(VALID_REQUEST_ID in caption.value for caption in app.caption)
    assert "saved_inspection_run_id" not in app.session_state
    assert "current_inspection_detail_response" not in app.session_state
    assert all(metric.label != "전체 문제 수" for metric in app.metric)
