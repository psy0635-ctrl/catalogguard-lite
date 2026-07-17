# 역할: Streamlit 앱이 업로드 전 초기 화면에서 예외 없이 렌더링되는지 테스트합니다.
from streamlit.testing.v1 import AppTest


GROUP_CATEGORY_TEST_CSV = """product_group_id,product_id,product_name,category,color,size,stock,price,image_path
G001,P001,기본 반팔 티셔츠 블랙,TOP,BLACK,M,10,19900,image1.jpg
G001,P002,기본 반팔 티셔츠 화이트,TOP,WHITE,M,10,19900,image2.jpg
G001,P003,기본 반팔 티셔츠 네이비,SHOES,NAVY,M,10,19900,image3.jpg
G002,P004,데님 팬츠 블랙,BOTTOM,BLACK,28,10,39900,image4.jpg
G002,P005,데님 팬츠 블루,bottom,BLUE,30,10,39900,image5.jpg
G003,P006,가죽 가방,BAG,BLACK,FREE,5,79000,image6.jpg
""".encode("utf-8")


def test_app_initial_render_without_upload(monkeypatch):
    monkeypatch.delenv("CATALOGGUARD_API_BASE_URL", raising=False)
    app = AppTest.from_file("app.py")

    app.run(timeout=10)

    assert len(app.exception) == 0
    assert [title.value for title in app.title] == ["CatalogGuard Lite"]
    assert "CSV 입력 템플릿" in [subheader.value for subheader in app.subheader]
    assert "검수 이력" in [subheader.value for subheader in app.subheader]
    assert [uploader.label for uploader in app.file_uploader] == ["CSV 파일 업로드"]
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
    monkeypatch.delenv("CATALOGGUARD_API_BASE_URL", raising=False)
    app = AppTest.from_file("app.py").run(timeout=10)

    app.file_uploader[0].upload(
        "group_category_consistency_test.csv",
        GROUP_CATEGORY_TEST_CSV,
        "text/csv",
    ).run(timeout=10)

    assert len(app.exception) == 0
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

    results = app.dataframe[-1].value
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

    app.selectbox[0].select("오류").run(timeout=10)

    assert len(app.exception) == 0
    assert "현재 조건에 맞는 검수 결과: 6건" in [
        caption.value for caption in app.caption
    ]
    assert set(app.dataframe[-1].value["검수 상태"]) == {"오류"}

    app.selectbox[1].select("상품 그룹 카테고리 불일치").run(timeout=10)

    assert len(app.exception) == 0
    assert "현재 조건에 맞는 검수 결과: 3건" in [
        caption.value for caption in app.caption
    ]
    assert app.dataframe[-1].value["상품 ID"].tolist() == [
        "P001",
        "P002",
        "P003",
    ]

    app.text_input[0].input("P003").run(timeout=10)

    assert len(app.exception) == 0
    assert "현재 조건에 맞는 검수 결과: 1건" in [
        caption.value for caption in app.caption
    ]
    assert app.dataframe[-1].value["상품 ID"].tolist() == ["P003"]
    result_downloads = [
        download
        for download in app.get("download_button")
        if download.proto.label == "현재 필터 결과 CSV 다운로드"
    ]
    assert len(result_downloads) == 1
    assert result_downloads[0].proto.url.endswith(".csv")
