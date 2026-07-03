from streamlit.testing.v1 import AppTest


def test_app_initial_render_without_upload():
    app = AppTest.from_file("app.py")

    app.run(timeout=10)

    assert len(app.exception) == 0
    assert [title.value for title in app.title] == ["CatalogGuard Lite"]
    assert "CSV 입력 템플릿" in [subheader.value for subheader in app.subheader]
    assert [uploader.label for uploader in app.file_uploader] == ["CSV 파일 업로드"]
    assert "검사할 CSV 파일을 업로드해 주세요." in [
        info.value for info in app.info
    ]
