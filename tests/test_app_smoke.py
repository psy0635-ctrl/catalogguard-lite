# 역할: Streamlit 앱이 업로드 전 초기 화면에서 예외 없이 렌더링되는지 테스트합니다.
from streamlit.testing.v1 import AppTest


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
