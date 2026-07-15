# 역할: 검수 전체 흐름이 패션 표준화 경고를 만들고 원본 데이터를 보존하는지 테스트합니다.
import pandas as pd

from core.inspection_service import inspect_dataframe


def test_inspect_dataframe_reports_fashion_warnings_without_changing_source_data():
    dataframe = pd.DataFrame(
        [
            {
                "product_group_id": "G001",
                "product_id": "P001",
                "product_name": "기본 반팔 티셔츠",
                "category": "TOP",
                "color": "블랙",
                "size": "medium",
                "stock": "10",
                "price": "19900",
                "image_path": "image.jpg",
                "description": "",
                "seller": "",
            }
        ]
    )
    original_dataframe = dataframe.copy(deep=True)

    report = inspect_dataframe(dataframe)

    assert report.summary.total_products == 1
    assert report.summary.error_count == 0
    assert report.summary.warning_count == 2
    assert report.summary.total_issues == 2
    assert [issue.rule for issue in report.issues] == [
        "non_standard_color",
        "non_standard_size",
    ]
    pd.testing.assert_frame_equal(dataframe, original_dataframe)
    pd.testing.assert_frame_equal(report.source_dataframe, original_dataframe)
    assert report.masked_preview_dataframe.loc[0, "color"] == "블랙"
    assert report.masked_preview_dataframe.loc[0, "size"] == "medium"
    assert report.products[0].color == "블랙"
    assert report.products[0].size == "medium"
