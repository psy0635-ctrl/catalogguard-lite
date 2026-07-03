from pydantic import BaseModel


class InspectionSummary(BaseModel):
    total_products: int
    total_issues: int
    error_count: int
    warning_count: int


class InspectionResultItem(BaseModel):
    status: str
    product_group_id: str
    product_id: str
    error_field: str
    reason: str
    recommendation: str
    risk_level: str


class InspectionResponse(BaseModel):
    summary: InspectionSummary
    results: list[InspectionResultItem]
