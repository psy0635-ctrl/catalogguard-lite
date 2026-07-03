# 역할: CSV 검수 API가 반환하는 JSON 응답 구조를 Pydantic 모델로 정의합니다.
from pydantic import BaseModel


# API가 밖으로 내보낼 JSON 응답 모양을 Pydantic 모델로 고정합니다.
class InspectionSummary(BaseModel):
    # CSV 전체 검수 결과를 숫자로 요약한 영역입니다.
    total_products: int
    total_issues: int
    error_count: int
    warning_count: int


class InspectionResultItem(BaseModel):
    # 화면용 결과 DataFrame의 한 행을 API 필드명으로 바꾼 형태입니다.
    status: str
    product_group_id: str
    product_id: str
    error_field: str
    reason: str
    recommendation: str
    risk_level: str


class InspectionResponse(BaseModel):
    # 최종 응답은 요약(summary)과 문제 목록(results)으로 구성됩니다.
    summary: InspectionSummary
    results: list[InspectionResultItem]
