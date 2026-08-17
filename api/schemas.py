# 역할: CSV 검수 API가 반환하는 JSON 응답 구조를 Pydantic 모델로 정의합니다.
from datetime import datetime
from typing import Literal

from pydantic import BaseModel, ConfigDict, Field


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
    inspection_run_id: int
    # True면 이번 요청에서 새로 저장했고, False면 같은 파일/버전의 기존 이력을 반환했다는 뜻입니다.
    created: bool = True
    actor_username: str | None = None
    summary: InspectionSummary
    results: list[InspectionResultItem]


class InspectionDetailResponse(InspectionResponse):
    # 저장된 검수 실행을 조회할 때는 파일명과 저장 시각도 함께 반환합니다.
    source_filename: str
    created_at: datetime


class InspectionListItemResponse(BaseModel):
    inspection_run_id: int
    source_filename: str
    created_at: datetime
    total_products: int
    total_issues: int
    error_count: int
    warning_count: int
    actor_username: str | None = None


class InspectionListResponse(BaseModel):
    items: list[InspectionListItemResponse]
    total: int
    limit: int
    offset: int


class ETLLoadListItemResponse(BaseModel):
    etl_load_run_id: int
    source_filename: str
    profile_name: str
    profile_version: str
    total_rows: int | None
    loaded_rows: int
    rejected_rows: int | None
    created_at: datetime
    # 이 배치를 실행한 로그인 사용자입니다. migration 이전이나 CLI로 적재된 배치는 None입니다.
    actor_username: str | None
    # 이 배치를 최초로 만든 입력 경로입니다. dedup으로 재사용된 배치는 최초 값을 유지하므로,
    # 같은 배치가 나중에 다른 경로로 다시 들어왔더라도 이 값은 바뀌지 않습니다.
    initial_source_type: str
    initial_source_ref: str | None


class ETLLoadListResponse(BaseModel):
    items: list[ETLLoadListItemResponse]
    total: int
    limit: int
    offset: int


class ETLLoadQualitySummaryResponse(BaseModel):
    batch_count: int
    quality_available_batch_count: int
    quality_unavailable_batch_count: int
    total_rows: int
    loaded_rows: int
    rejected_rows: int
    rejection_rate: float


class ETLLoadQualityTrendItemResponse(BaseModel):
    etl_load_run_id: int
    created_at: datetime
    total_rows: int
    loaded_rows: int
    rejected_rows: int
    rejection_rate: float


class ETLLoadQualityTrendResponse(BaseModel):
    items: list[ETLLoadQualityTrendItemResponse]


class ETLStagingProductResponse(BaseModel):
    staging_product_id: int
    product_group_id: str
    product_id: str
    product_name: str
    category: str
    color: str
    size: str
    stock: int
    price: int
    sale_price: int | None
    image_path: str
    description: str | None
    seller: str | None
    created_at: datetime


class ETLStagingProductListResponse(BaseModel):
    items: list[ETLStagingProductResponse]
    total: int
    limit: int
    offset: int


class ETLLoadDetailResponse(BaseModel):
    etl_load_run_id: int
    source_filename: str
    profile_name: str
    profile_version: str
    input_file_sha256: str
    output_file_sha256: str
    total_rows: int | None
    loaded_rows: int
    rejected_rows: int | None
    error_counts: dict[str, int] | None
    reject_details_stored: bool
    created_at: datetime
    actor_username: str | None
    initial_source_type: str
    initial_source_ref: str | None
    products: ETLStagingProductListResponse


class ETLRejectErrorResponse(BaseModel):
    code: str
    field: str
    message: str


class ETLRejectedRowResponse(BaseModel):
    rejected_row_id: int
    source_row_number: int
    errors: list[ETLRejectErrorResponse]
    masked_source_data: dict[str, str]
    created_at: datetime


class ETLRejectedRowListResponse(BaseModel):
    available: bool
    items: list[ETLRejectedRowResponse]
    total: int
    limit: int
    offset: int


class ETLWebRunResponse(BaseModel):
    etl_load_run_id: int
    created: bool
    profile_name: str
    profile_version: str
    source_filename: str
    total_rows: int | None
    loaded_rows: int
    rejected_rows: int | None
    error_counts: dict[str, int] | None
    actor_username: str | None
    initial_source_type: str
    initial_source_ref: str | None


class ETLS3LoadRequest(BaseModel):
    model_config = ConfigDict(extra="forbid")

    profile_id: str
    object_key: str


class ETLHTTPFeedLoadRequest(BaseModel):
    # feed URL은 서버 설정으로만 정합니다. extra="forbid"가 클라이언트의 url 지정을 막습니다.
    model_config = ConfigDict(extra="forbid")

    profile_id: str


class ETLProfileResponse(BaseModel):
    id: str
    display_name: str


class ETLProfileListResponse(BaseModel):
    items: list[ETLProfileResponse]


CatalogPromotionValue = str | int | None


class CatalogPromotionChangedFieldResponse(BaseModel):
    before: CatalogPromotionValue
    after: CatalogPromotionValue


class CatalogPromotionProductDataResponse(BaseModel):
    external_product_id: str
    product_group_id: str
    product_name: str
    category: str
    color: str
    size: str
    stock: int
    price: int
    sale_price: int | None
    image_path: str
    description: str | None
    seller: str | None


class CatalogPromotionBlockedReasonResponse(BaseModel):
    code: str
    message: str
    supplier_key: str | None = None
    external_product_id: str | None = None
    staging_product_ids: list[int] = Field(default_factory=list)


class CatalogPromotionPreviewItemResponse(BaseModel):
    supplier_key: str
    external_product_id: str
    action: Literal["insert", "update", "unchanged"]
    changed_fields: dict[str, CatalogPromotionChangedFieldResponse]
    before_data: CatalogPromotionProductDataResponse | None
    after_data: CatalogPromotionProductDataResponse


class CatalogPromotionPreviewResponse(BaseModel):
    etl_load_run_id: int
    supplier_key: str
    inspection_version: str
    preview_schema_version: int
    preview_hash: str | None
    promotion_eligible: bool
    blocked_reasons: list[CatalogPromotionBlockedReasonResponse]
    insert_count: int
    update_count: int
    unchanged_count: int
    error_count: int
    warning_count: int
    items: list[CatalogPromotionPreviewItemResponse]


class CatalogPromotionRequest(BaseModel):
    confirmation: bool
    expected_preview_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class CatalogPromotionResponse(BaseModel):
    promotion_run_id: int
    etl_load_run_id: int
    status: Literal["succeeded"]
    created: bool
    preview_hash: str
    preview_schema_version: int
    inspection_version: str
    inserted_count: int
    updated_count: int
    unchanged_count: int
    blocked_count: int
    error_count: int
    warning_count: int
    started_at: datetime
    completed_at: datetime
    actor_username: str | None


CatalogPromotionRunStatus = Literal["applying", "succeeded", "failed", "blocked"]


class CatalogPromotionRunListItemResponse(BaseModel):
    promotion_run_id: int
    etl_load_run_id: int
    source_filename: str
    profile_name: str
    status: CatalogPromotionRunStatus
    inserted_count: int
    updated_count: int
    unchanged_count: int
    blocked_count: int
    error_count: int
    warning_count: int
    failure_code: str | None
    safe_failure_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    actor_username: str | None


class CatalogPromotionRunListResponse(BaseModel):
    items: list[CatalogPromotionRunListItemResponse]
    total: int
    limit: int
    offset: int


class CatalogPromotionRunDetailResponse(CatalogPromotionRunListItemResponse):
    preview_hash: str | None
    preview_schema_version: str | None
    inspection_version: str | None


class CatalogPromotionAuditResponse(BaseModel):
    audit_id: int
    promotion_run_id: int
    catalog_product_id: int
    action: Literal["insert", "update"]
    changed_fields: dict[str, object]
    before_data: dict[str, object] | None
    after_data: dict[str, object]
    created_at: datetime


class CatalogPromotionAuditListResponse(BaseModel):
    items: list[CatalogPromotionAuditResponse]
    total: int
    limit: int
    offset: int


class UnknownSizeTokenItemResponse(BaseModel):
    token: str
    count: int


class UnknownSizeTokenReportResponse(BaseModel):
    items: list[UnknownSizeTokenItemResponse]


InspectionJobStatus = Literal["queued", "running", "succeeded", "failed"]


class InspectionJobSubmissionResponse(BaseModel):
    job_id: str
    status: Literal["queued"]
    status_url: str


class InspectionJobStatusResponse(BaseModel):
    job_id: str
    status: InspectionJobStatus
    created: bool | None = None
    inspection_run_id: int | None = None
    summary: InspectionSummary | None = None
    error_code: str | None = None
    message: str | None = None
    created_at: datetime
    updated_at: datetime


CatalogPromotionRollbackRunStatus = Literal[
    "applying",
    "succeeded",
    "failed",
    "blocked",
]


class CatalogPromotionRollbackRunListItemResponse(BaseModel):
    rollback_run_id: int
    target_promotion_run_id: int
    status: CatalogPromotionRollbackRunStatus
    restored_count: int
    deleted_count: int
    conflict_count: int
    failure_code: str | None
    safe_failure_message: str | None
    started_at: datetime | None
    completed_at: datetime | None
    created_at: datetime
    actor_username: str | None


class CatalogPromotionRollbackRunListResponse(BaseModel):
    items: list[CatalogPromotionRollbackRunListItemResponse]
    total: int
    limit: int
    offset: int


class CatalogPromotionRollbackRunDetailResponse(
    CatalogPromotionRollbackRunListItemResponse
):
    preview_hash: str | None
    preview_schema_version: str | None


CatalogPromotionRollbackChangeAction = Literal["delete", "restore"]


class CatalogPromotionRollbackChangeResponse(BaseModel):
    rollback_change_id: int
    rollback_run_id: int
    original_audit_id: int
    catalog_product_id: int
    action: CatalogPromotionRollbackChangeAction
    changed_fields: dict[str, object]
    before_data: dict[str, object]
    after_data: dict[str, object] | None
    created_at: datetime


class CatalogPromotionRollbackChangeListResponse(BaseModel):
    items: list[CatalogPromotionRollbackChangeResponse]
    total: int
    limit: int
    offset: int


class CatalogPromotionRollbackBlockedReasonResponse(BaseModel):
    code: str
    message: str
    catalog_product_id: int | None = None
    external_product_id: str | None = None


class CatalogPromotionRollbackPreviewItemResponse(BaseModel):
    audit_id: int
    catalog_product_id: int
    external_product_id: str
    rollback_action: Literal["delete", "restore"]
    current_data: CatalogPromotionProductDataResponse | None
    restore_data: CatalogPromotionProductDataResponse | None
    conflict: bool
    conflict_reason: str | None


class CatalogPromotionRollbackPreviewResponse(BaseModel):
    target_promotion_run_id: int
    preview_schema_version: int
    preview_hash: str | None
    rollback_eligible: bool
    blocked_reasons: list[CatalogPromotionRollbackBlockedReasonResponse]
    restore_count: int
    delete_count: int
    conflict_count: int
    items: list[CatalogPromotionRollbackPreviewItemResponse]


class CatalogPromotionRollbackRequest(BaseModel):
    confirmation: bool
    expected_preview_hash: str = Field(
        min_length=64,
        max_length=64,
        pattern=r"^[0-9a-f]{64}$",
    )


class CatalogPromotionRollbackResponse(BaseModel):
    rollback_run_id: int
    target_promotion_run_id: int
    status: Literal["succeeded"]
    created: bool
    preview_hash: str
    preview_schema_version: int
    restored_count: int
    deleted_count: int
    conflict_count: int
    started_at: datetime
    completed_at: datetime
    actor_username: str | None


class LoginRequest(BaseModel):
    username: str = Field(min_length=1, max_length=50)
    password: str = Field(min_length=1, max_length=128)


class LoginResponse(BaseModel):
    access_token: str
    token_type: Literal["bearer"]
    expires_in: int


class CurrentUserResponse(BaseModel):
    # password_hash는 절대 포함하지 않습니다.
    username: str
    role: Literal["viewer", "operator"]
