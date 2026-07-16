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


def test_inspect_dataframe_reports_duplicate_variants_and_preserves_original_values():
    dataframe = pd.DataFrame(
        [
            {
                "product_group_id": "G001",
                "product_id": "P001",
                "product_name": "기본 반팔 티셔츠 A",
                "category": "TOP",
                "color": "블랙",
                "size": "medium",
                "stock": "10",
                "price": "19900",
                "image_path": "image1.jpg",
            },
            {
                "product_group_id": "G001",
                "product_id": "P002",
                "product_name": "기본 반팔 티셔츠 B",
                "category": "TOP",
                "color": "BLACK",
                "size": "M",
                "stock": "10",
                "price": "19900",
                "image_path": "image2.jpg",
            },
        ]
    )
    original_dataframe = dataframe.copy(deep=True)

    report = inspect_dataframe(dataframe)

    assert report.summary.total_products == 2
    assert report.summary.error_count == 2
    assert report.summary.warning_count == 2
    assert report.summary.total_issues == 4
    duplicate_issues = [
        issue
        for issue in report.issues
        if issue.rule == "duplicate_variant_combination"
    ]
    assert [issue.product_id for issue in duplicate_issues] == ["P001", "P002"]
    pd.testing.assert_frame_equal(dataframe, original_dataframe)
    pd.testing.assert_frame_equal(report.source_dataframe, original_dataframe)
    assert [(product.color, product.size) for product in report.products] == [
        ("블랙", "medium"),
        ("BLACK", "M"),
    ]


def test_inspect_dataframe_does_not_double_report_complete_duplicate_as_variant():
    dataframe = pd.DataFrame(
        [
            {
                "product_group_id": "G003",
                "product_id": "P005",
                "product_name": "Melange T-shirt",
                "category": "TOP",
                "color": "MELANGE GRAY",
                "size": "95",
                "stock": "10",
                "price": "21900",
                "image_path": "p005.jpg",
            },
            {
                "product_group_id": "G003",
                "product_id": "P006",
                "product_name": "Melange T-shirt",
                "category": "TOP",
                "color": "melange gray",
                "size": "95",
                "stock": "7",
                "price": "21900",
                "image_path": "p006.jpg",
            },
        ]
    )

    report = inspect_dataframe(dataframe)

    assert [
        issue.product_id
        for issue in report.issues
        if issue.rule == "duplicate_product_content"
    ] == ["P006"]
    assert not any(
        issue.rule == "duplicate_variant_combination" for issue in report.issues
    )
    assert report.summary.error_count == 1


def test_inspect_dataframe_translates_duplicate_variant_values_losslessly():
    dataframe = pd.DataFrame(
        [
            {
                "product_group_id": "G'001",
                "product_id": "P, 001",
                "product_name": "상품 A",
                "category": "TOP",
                "color": "women's blue",
                "size": "95",
                "stock": "10",
                "price": "19900",
                "image_path": "image1.jpg",
            },
            {
                "product_group_id": "G'001",
                "product_id": "P'002",
                "product_name": "상품 B",
                "category": "TOP",
                "color": "WOMEN'S BLUE",
                "size": " 95 ",
                "stock": "10",
                "price": "20900",
                "image_path": "image2.jpg",
            },
        ]
    )

    report = inspect_dataframe(dataframe)

    expected_reason = (
        "상품 그룹 'G'001'에서 색상 'women's blue', 사이즈 '95' 조합이 "
        "상품 ID 'P, 001', 'P'002'에 중복되어 있습니다."
    )
    assert report.result_dataframe["상품 ID"].tolist() == ["P, 001", "P'002"]
    assert report.result_dataframe["오류 이유"].tolist() == [
        expected_reason,
        expected_reason,
    ]
    assert not any(
        "product_group_id" in reason
        for reason in report.result_dataframe["오류 이유"]
    )
