import logging

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    Path,
    Query,
    Request,
    Response,
    UploadFile,
    status,
)
from sqlalchemy.orm import Session

from api.dependencies import require_operator, require_viewer
from api.schemas import (
    CatalogPromotionAuditListResponse,
    CatalogPromotionAuditResponse,
    CatalogPromotionBlockedReasonResponse,
    CatalogPromotionChangedFieldResponse,
    CatalogPromotionPreviewItemResponse,
    CatalogPromotionPreviewResponse,
    CatalogPromotionProductDataResponse,
    CatalogPromotionRequest,
    CatalogPromotionResponse,
    CatalogPromotionRunDetailResponse,
    CatalogPromotionRunListItemResponse,
    CatalogPromotionRunListResponse,
    CatalogPromotionRunStatus,
    CatalogReconciliationChangedFieldResponse,
    CatalogReconciliationItemResponse,
    CatalogReconciliationResponse,
    CatalogPromotionRollbackBlockedReasonResponse,
    CatalogPromotionRollbackChangeListResponse,
    CatalogPromotionRollbackChangeResponse,
    CatalogPromotionRollbackPreviewItemResponse,
    CatalogPromotionRollbackPreviewResponse,
    CatalogPromotionRollbackRequest,
    CatalogPromotionRollbackResponse,
    CatalogPromotionRollbackRunDetailResponse,
    CatalogPromotionRollbackRunListItemResponse,
    CatalogPromotionRollbackRunListResponse,
    CatalogPromotionRollbackRunStatus,
    ETLHTTPFeedLoadRequest,
    ETLLoadDetailResponse,
    ETLLoadListItemResponse,
    ETLLoadListResponse,
    ETLLoadQualitySummaryResponse,
    ETLLoadQualityTrendItemResponse,
    ETLLoadQualityTrendResponse,
    ETLProfileActivationResponse,
    ETLProfileActivationUpdateRequest,
    ETLProfileDetailResponse,
    ETLProfileListResponse,
    ETLProfileResponse,
    ETLQualityObservabilityErrorCodeResponse,
    ETLQualityObservabilityProfileListResponse,
    ETLQualityObservabilityProfileResponse,
    ETLQualityObservabilityResponse,
    ETLRejectErrorResponse,
    ETLRejectedRowListResponse,
    ETLRejectedRowResponse,
    ETLS3LoadRequest,
    ETLStagingProductListResponse,
    ETLStagingProductResponse,
    ETLWebRunResponse,
    UnknownSizeTokenItemResponse,
    UnknownSizeTokenReportResponse,
)
from config.metrics import record_web_etl_run, record_web_etl_rows
from config.logging import LOGGER_NAME, log_event
from core.upload_validator import CsvUploadValidationError
from db.etl_quality_observability_service import (
    DEFAULT_BATCH_LIMIT as OBSERVABILITY_DEFAULT_LIMIT,
    ETLQualityObservability,
    MAX_BATCH_LIMIT as OBSERVABILITY_MAX_LIMIT,
    MIN_BATCH_LIMIT as OBSERVABILITY_MIN_LIMIT,
    get_etl_quality_observability,
    list_etl_quality_observability_profiles,
)
from db.etl_query_service import (
    ETLLoadDetail,
    ETLLoadList,
    ETLLoadQualitySummary,
    ETLLoadQualityTrend,
    ETLLoadQualityTrendItem,
    get_etl_load_detail,
    get_etl_load_quality_summary,
    get_etl_load_quality_trend,
    list_etl_rejections,
    list_etl_loads,
    normalize_etl_filter,
)
from etl.db_loader import ETLLoadError
from etl.http_source import (
    HTTPFeedNotConfiguredError,
    HTTPFeedReadError,
    read_http_feed_csv,
)
from etl.pipeline import ETLPipelineError
from etl.profile_loader import (
    ETLProfileInactiveError,
    ETLProfileNotFoundError,
    get_etl_profile_detail,
    is_etl_profile_inactive,
    list_etl_profiles,
    registered_profile_versions,
)
from config.settings import ETL_HTTP_FEED_SOURCE_REF
from etl.s3_source import (
    S3KeyNotAllowedError,
    S3NotConfiguredError,
    S3ObjectNotFoundError,
    S3ReadError,
    read_s3_csv_object,
    sanitized_object_ref,
)
from db.etl_profile_activation_service import (
    ETLProfileVersionNotFoundError,
    get_etl_profile_activation,
    set_etl_profile_activation,
)
from etl.web_service import ETLWebRunOutcome, run_web_etl
from db.catalog_reconciliation_service import (
    CatalogReconciliationDuplicateIdentityError,
    CatalogReconciliationReport,
    DEFAULT_ITEM_LIMIT as RECONCILIATION_DEFAULT_LIMIT,
    MAX_ITEM_LIMIT as RECONCILIATION_MAX_LIMIT,
    build_catalog_reconciliation_report,
)
from db.catalog_promotion_preview_service import (
    CatalogPromotionPreview,
    ETLLoadRunNotFoundError,
    PromotionPreviewItem,
    preview_catalog_promotion,
)
from db.catalog_promotion_service import (
    CatalogPromotionConfirmationRequiredError,
    CatalogPromotionExecutionFailedError,
    CatalogPromotionExecutionResult,
    CatalogPromotionInvalidPreviewHashError,
    execute_catalog_promotion,
)
from db.catalog_promotion_rollback_service import (
    CatalogPromotionRollbackAlreadyExecutedError,
    CatalogPromotionRollbackConfirmationRequiredError,
    CatalogPromotionRollbackExecutionFailedError,
    CatalogPromotionRollbackInvalidPreviewHashError,
    CatalogPromotionRollbackNotFoundError,
    CatalogPromotionRollbackPreview,
    CatalogPromotionRollbackExecutionResult,
    execute_catalog_promotion_rollback,
    preview_catalog_promotion_rollback,
)
from db.catalog_promotion_query_service import (
    CatalogPromotionAuditList,
    CatalogPromotionRunDetail,
    CatalogPromotionRunList,
    get_catalog_promotion_detail,
    list_catalog_promotion_audits,
    list_catalog_promotions,
    list_unknown_size_tokens,
)
from db.catalog_promotion_rollback_query_service import (
    CatalogPromotionRollbackChangeList,
    CatalogPromotionRollbackRunDetail,
    CatalogPromotionRollbackRunList,
    get_catalog_promotion_rollback_detail,
    list_catalog_promotion_rollback_changes,
    list_catalog_promotion_rollbacks,
)
from db.session import get_session


router = APIRouter()
_LOGGER = logging.getLogger(LOGGER_NAME)
CATALOG_PROMOTION_NOT_FOUND_MESSAGE = "Promotion run not found."
CATALOG_PROMOTION_ROLLBACK_NOT_FOUND_MESSAGE = "Rollback run not found."
ETL_LOAD_NOT_FOUND_MESSAGE = "ETL 적재 배치를 찾을 수 없습니다."
SERVER_SIDE_INACTIVE_PROFILE_MESSAGE = "Supplier profile is inactive."


@router.get(
    "/api/v1/catalog/unknown-size-tokens",
    response_model=UnknownSizeTokenReportResponse,
)
def get_unknown_size_token_report(
    limit: int = Query(default=20, ge=1, le=100),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> UnknownSizeTokenReportResponse:
    items = list_unknown_size_tokens(session, limit=limit)
    return UnknownSizeTokenReportResponse(
        items=[
            UnknownSizeTokenItemResponse(token=item.token, count=item.count)
            for item in items
        ]
    )


def _build_list_response(result: ETLLoadList) -> ETLLoadListResponse:
    return ETLLoadListResponse(
        items=[
            ETLLoadListItemResponse(
                etl_load_run_id=item.etl_load_run_id,
                source_filename=item.source_filename,
                profile_name=item.profile_name,
                profile_version=item.profile_version,
                total_rows=item.total_rows,
                loaded_rows=item.loaded_rows,
                rejected_rows=item.rejected_rows,
                created_at=item.created_at,
                actor_username=item.actor_username,
                initial_source_type=item.initial_source_type,
                initial_source_ref=item.initial_source_ref,
            )
            for item in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


def _build_quality_summary_response(
    result: ETLLoadQualitySummary,
) -> ETLLoadQualitySummaryResponse:
    return ETLLoadQualitySummaryResponse(
        batch_count=result.batch_count,
        quality_available_batch_count=result.quality_available_batch_count,
        quality_unavailable_batch_count=result.quality_unavailable_batch_count,
        total_rows=result.total_rows,
        loaded_rows=result.loaded_rows,
        rejected_rows=result.rejected_rows,
        rejection_rate=result.rejection_rate,
    )


def _build_quality_trend_response(
    result: ETLLoadQualityTrend,
) -> ETLLoadQualityTrendResponse:
    return ETLLoadQualityTrendResponse(
        items=[
            ETLLoadQualityTrendItemResponse(
                etl_load_run_id=item.etl_load_run_id,
                created_at=item.created_at,
                total_rows=item.total_rows,
                loaded_rows=item.loaded_rows,
                rejected_rows=item.rejected_rows,
                rejection_rate=item.rejection_rate,
            )
            for item in result.items
        ]
    )


def _build_quality_item_response(
    item: ETLLoadQualityTrendItem | None,
) -> ETLLoadQualityTrendItemResponse | None:
    if item is None:
        return None
    return ETLLoadQualityTrendItemResponse(
        etl_load_run_id=item.etl_load_run_id,
        created_at=item.created_at,
        total_rows=item.total_rows,
        loaded_rows=item.loaded_rows,
        rejected_rows=item.rejected_rows,
        rejection_rate=item.rejection_rate,
    )


def _build_quality_observability_response(
    result: ETLQualityObservability,
) -> ETLQualityObservabilityResponse:
    return ETLQualityObservabilityResponse(
        profile_name=result.profile_name,
        limit=result.limit,
        batch_count=result.batch_count,
        latest_batch=_build_quality_item_response(result.latest_batch),
        previous_batch=_build_quality_item_response(result.previous_batch),
        rejection_rate_delta=result.rejection_rate_delta,
        direction=result.direction,
        error_codes=[
            ETLQualityObservabilityErrorCodeResponse(
                error_code=item.error_code,
                total_count=item.total_count,
                affected_batch_count=item.affected_batch_count,
            )
            for item in result.error_codes
        ],
        recent_batches=[
            _build_quality_item_response(item) for item in result.recent_batches
        ],
    )


def _build_web_run_response(result: ETLWebRunOutcome) -> ETLWebRunResponse:
    return ETLWebRunResponse(
        etl_load_run_id=result.etl_load_run_id,
        created=result.created,
        profile_name=result.profile_name,
        profile_version=result.profile_version,
        source_filename=result.source_filename,
        total_rows=result.total_rows,
        loaded_rows=result.loaded_rows,
        rejected_rows=result.rejected_rows,
        error_counts=result.error_counts,
        actor_username=result.actor_username,
        initial_source_type=result.initial_source_type,
        initial_source_ref=result.initial_source_ref,
    )


def _build_detail_response(result: ETLLoadDetail) -> ETLLoadDetailResponse:
    return ETLLoadDetailResponse(
        etl_load_run_id=result.etl_load_run_id,
        source_filename=result.source_filename,
        profile_name=result.profile_name,
        profile_version=result.profile_version,
        input_file_sha256=result.input_file_sha256,
        output_file_sha256=result.output_file_sha256,
        total_rows=result.total_rows,
        loaded_rows=result.loaded_rows,
        rejected_rows=result.rejected_rows,
        error_counts=result.error_counts,
        reject_details_stored=result.reject_details_stored,
        created_at=result.created_at,
        actor_username=result.actor_username,
        initial_source_type=result.initial_source_type,
        initial_source_ref=result.initial_source_ref,
        products=ETLStagingProductListResponse(
            items=[
                ETLStagingProductResponse(
                    staging_product_id=product.staging_product_id,
                    product_group_id=product.product_group_id,
                    product_id=product.product_id,
                    product_name=product.product_name,
                    category=product.category,
                    color=product.color,
                    size=product.size,
                    stock=product.stock,
                    price=product.price,
                    sale_price=product.sale_price,
                    image_path=product.image_path,
                    description=product.description,
                    seller=product.seller,
                    created_at=product.created_at,
                )
                for product in result.products.items
            ],
            total=result.products.total,
            limit=result.products.limit,
            offset=result.products.offset,
        ),
    )


def _build_promotion_product_data_response(
    data: dict[str, str | int | None],
) -> CatalogPromotionProductDataResponse:
    return CatalogPromotionProductDataResponse(
        external_product_id=data["external_product_id"],
        product_group_id=data["product_group_id"],
        product_name=data["product_name"],
        category=data["category"],
        color=data["color"],
        size=data["size"],
        stock=data["stock"],
        price=data["price"],
        sale_price=data["sale_price"],
        image_path=data["image_path"],
        description=data["description"],
        seller=data["seller"],
    )


def _build_promotion_item_response(
    item: PromotionPreviewItem,
) -> CatalogPromotionPreviewItemResponse:
    return CatalogPromotionPreviewItemResponse(
        supplier_key=item.supplier_key,
        external_product_id=item.external_product_id,
        action=item.action,
        changed_fields={
            field_name: CatalogPromotionChangedFieldResponse(
                before=change["before"],
                after=change["after"],
            )
            for field_name, change in item.changed_fields.items()
        },
        before_data=(
            None
            if item.before_data is None
            else _build_promotion_product_data_response(item.before_data)
        ),
        after_data=_build_promotion_product_data_response(item.after_data),
    )


def _build_promotion_preview_response(
    result: CatalogPromotionPreview,
) -> CatalogPromotionPreviewResponse:
    return CatalogPromotionPreviewResponse(
        etl_load_run_id=result.etl_load_run_id,
        supplier_key=result.supplier_key,
        inspection_version=result.inspection_version,
        preview_schema_version=result.preview_schema_version,
        preview_hash=result.preview_hash,
        promotion_eligible=result.promotion_eligible,
        blocked_reasons=[
            CatalogPromotionBlockedReasonResponse(
                code=reason.code,
                message=reason.message,
                supplier_key=reason.supplier_key,
                external_product_id=reason.external_product_id,
                staging_product_ids=list(reason.staging_product_ids),
            )
            for reason in result.blocked_reasons
        ],
        insert_count=result.insert_count,
        update_count=result.update_count,
        unchanged_count=result.unchanged_count,
        error_count=result.error_count,
        warning_count=result.warning_count,
        items=[_build_promotion_item_response(item) for item in result.items],
    )


def _build_promotion_response(
    result: CatalogPromotionExecutionResult,
) -> CatalogPromotionResponse:
    return CatalogPromotionResponse(
        promotion_run_id=result.promotion_run_id,
        etl_load_run_id=result.etl_load_run_id,
        status="succeeded",
        created=result.created,
        preview_hash=result.preview_hash,
        preview_schema_version=result.preview_schema_version,
        inspection_version=result.inspection_version,
        inserted_count=result.inserted_count,
        updated_count=result.updated_count,
        unchanged_count=result.unchanged_count,
        blocked_count=result.blocked_count,
        error_count=result.error_count,
        warning_count=result.warning_count,
        started_at=result.started_at,
        completed_at=result.completed_at,
        actor_username=result.actor_username,
    )


def _build_promotion_run_item_response(
    item,
) -> CatalogPromotionRunListItemResponse:
    return CatalogPromotionRunListItemResponse(
        promotion_run_id=item.promotion_run_id,
        etl_load_run_id=item.etl_load_run_id,
        source_filename=item.source_filename,
        profile_name=item.profile_name,
        status=item.status,
        inserted_count=item.inserted_count,
        updated_count=item.updated_count,
        unchanged_count=item.unchanged_count,
        blocked_count=item.blocked_count,
        error_count=item.error_count,
        warning_count=item.warning_count,
        failure_code=item.failure_code,
        safe_failure_message=item.safe_failure_message,
        started_at=item.started_at,
        completed_at=item.completed_at,
        created_at=item.created_at,
        actor_username=item.actor_username,
    )


def _build_promotion_run_list_response(
    result: CatalogPromotionRunList,
) -> CatalogPromotionRunListResponse:
    return CatalogPromotionRunListResponse(
        items=[_build_promotion_run_item_response(item) for item in result.items],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


def _build_promotion_run_detail_response(
    result: CatalogPromotionRunDetail,
) -> CatalogPromotionRunDetailResponse:
    item = _build_promotion_run_item_response(result)
    return CatalogPromotionRunDetailResponse(
        **item.model_dump(),
        preview_hash=result.preview_hash,
        preview_schema_version=result.preview_schema_version,
        inspection_version=result.inspection_version,
    )


def _build_rollback_run_item_response(
    item,
) -> CatalogPromotionRollbackRunListItemResponse:
    return CatalogPromotionRollbackRunListItemResponse(
        rollback_run_id=item.rollback_run_id,
        target_promotion_run_id=item.target_promotion_run_id,
        status=item.status,
        restored_count=item.restored_count,
        deleted_count=item.deleted_count,
        conflict_count=item.conflict_count,
        failure_code=item.failure_code,
        safe_failure_message=item.safe_failure_message,
        started_at=item.started_at,
        completed_at=item.completed_at,
        created_at=item.created_at,
        actor_username=item.actor_username,
    )


def _build_rollback_run_list_response(
    result: CatalogPromotionRollbackRunList,
) -> CatalogPromotionRollbackRunListResponse:
    return CatalogPromotionRollbackRunListResponse(
        items=[_build_rollback_run_item_response(item) for item in result.items],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


def _build_rollback_run_detail_response(
    result: CatalogPromotionRollbackRunDetail,
) -> CatalogPromotionRollbackRunDetailResponse:
    item = _build_rollback_run_item_response(result)
    return CatalogPromotionRollbackRunDetailResponse(
        **item.model_dump(),
        preview_hash=result.preview_hash,
        preview_schema_version=result.preview_schema_version,
    )


def _build_rollback_change_list_response(
    result: CatalogPromotionRollbackChangeList,
) -> CatalogPromotionRollbackChangeListResponse:
    return CatalogPromotionRollbackChangeListResponse(
        items=[
            CatalogPromotionRollbackChangeResponse(
                rollback_change_id=item.rollback_change_id,
                rollback_run_id=item.rollback_run_id,
                original_audit_id=item.original_audit_id,
                catalog_product_id=item.catalog_product_id,
                action=item.action,
                changed_fields=item.changed_fields,
                before_data=item.before_data,
                after_data=item.after_data,
                created_at=item.created_at,
            )
            for item in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


def _build_promotion_audit_list_response(
    result: CatalogPromotionAuditList,
) -> CatalogPromotionAuditListResponse:
    return CatalogPromotionAuditListResponse(
        items=[
            CatalogPromotionAuditResponse(
                audit_id=item.audit_id,
                promotion_run_id=item.promotion_run_id,
                catalog_product_id=item.catalog_product_id,
                action=item.action,
                changed_fields=item.changed_fields,
                before_data=item.before_data,
                after_data=item.after_data,
                created_at=item.created_at,
            )
            for item in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


@router.get(
    "/api/v1/catalog-promotions",
    response_model=CatalogPromotionRunListResponse,
)
def list_catalog_promotion_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    promotion_status: CatalogPromotionRunStatus | None = Query(
        default=None,
        alias="status",
    ),
    etl_load_run_id: int | None = Query(default=None, ge=1),
    filename: str | None = Query(default=None),
    profile_name: str | None = Query(default=None),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> CatalogPromotionRunListResponse:
    result = list_catalog_promotions(
        session,
        limit=limit,
        offset=offset,
        status=promotion_status,
        etl_load_run_id=etl_load_run_id,
        filename=normalize_etl_filter(filename),
        profile_name=normalize_etl_filter(profile_name),
    )
    return _build_promotion_run_list_response(result)


@router.get(
    "/api/v1/catalog-promotions/{promotion_run_id}",
    response_model=CatalogPromotionRunDetailResponse,
)
def get_catalog_promotion_run(
    promotion_run_id: int = Path(..., ge=1),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> CatalogPromotionRunDetailResponse:
    result = get_catalog_promotion_detail(
        session,
        promotion_run_id=promotion_run_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=CATALOG_PROMOTION_NOT_FOUND_MESSAGE,
        )
    return _build_promotion_run_detail_response(result)


@router.get(
    "/api/v1/catalog-promotions/{promotion_run_id}/audits",
    response_model=CatalogPromotionAuditListResponse,
)
def list_catalog_promotion_run_audits(
    promotion_run_id: int = Path(..., ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> CatalogPromotionAuditListResponse:
    result = list_catalog_promotion_audits(
        session,
        promotion_run_id=promotion_run_id,
        limit=limit,
        offset=offset,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=CATALOG_PROMOTION_NOT_FOUND_MESSAGE,
        )
    return _build_promotion_audit_list_response(result)


@router.get(
    "/api/v1/catalog-promotion-rollbacks",
    response_model=CatalogPromotionRollbackRunListResponse,
)
def list_catalog_promotion_rollback_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    rollback_status: CatalogPromotionRollbackRunStatus | None = Query(
        default=None,
        alias="status",
    ),
    target_promotion_run_id: int | None = Query(default=None, ge=1),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> CatalogPromotionRollbackRunListResponse:
    result = list_catalog_promotion_rollbacks(
        session,
        limit=limit,
        offset=offset,
        status=rollback_status,
        target_promotion_run_id=target_promotion_run_id,
    )
    return _build_rollback_run_list_response(result)


@router.get(
    "/api/v1/catalog-promotion-rollbacks/{rollback_run_id}/changes",
    response_model=CatalogPromotionRollbackChangeListResponse,
)
def list_catalog_promotion_rollback_run_changes(
    rollback_run_id: int = Path(..., ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> CatalogPromotionRollbackChangeListResponse:
    result = list_catalog_promotion_rollback_changes(
        session,
        rollback_run_id=rollback_run_id,
        limit=limit,
        offset=offset,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=CATALOG_PROMOTION_ROLLBACK_NOT_FOUND_MESSAGE,
        )
    return _build_rollback_change_list_response(result)


@router.get(
    "/api/v1/catalog-promotion-rollbacks/{rollback_run_id}",
    response_model=CatalogPromotionRollbackRunDetailResponse,
)
def get_catalog_promotion_rollback_run(
    rollback_run_id: int = Path(..., ge=1),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> CatalogPromotionRollbackRunDetailResponse:
    result = get_catalog_promotion_rollback_detail(
        session,
        rollback_run_id=rollback_run_id,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=CATALOG_PROMOTION_ROLLBACK_NOT_FOUND_MESSAGE,
        )
    return _build_rollback_run_detail_response(result)


@router.get("/api/v1/etl-loads", response_model=ETLLoadListResponse)
def list_etl_load_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    filename: str | None = Query(default=None),
    profile_name: str | None = Query(default=None),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> ETLLoadListResponse:
    result = list_etl_loads(
        session,
        limit=limit,
        offset=offset,
        filename=normalize_etl_filter(filename),
        profile_name=normalize_etl_filter(profile_name),
    )
    return _build_list_response(result)


@router.get(
    "/api/v1/etl-loads/quality-summary",
    response_model=ETLLoadQualitySummaryResponse,
)
def get_etl_load_quality_summary_route(
    profile_name: str | None = Query(default=None),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> ETLLoadQualitySummaryResponse:
    result = get_etl_load_quality_summary(
        session,
        profile_name=normalize_etl_filter(profile_name),
    )
    return _build_quality_summary_response(result)


@router.get(
    "/api/v1/etl-loads/quality-trend",
    response_model=ETLLoadQualityTrendResponse,
)
def get_etl_load_quality_trend_route(
    profile_name: str | None = Query(default=None),
    limit: int = Query(default=10, ge=1, le=50),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> ETLLoadQualityTrendResponse:
    result = get_etl_load_quality_trend(
        session,
        profile_name=normalize_etl_filter(profile_name),
        limit=limit,
    )
    return _build_quality_trend_response(result)


@router.get(
    "/api/v1/etl-loads/quality-observability",
    response_model=ETLQualityObservabilityResponse,
)
def get_etl_quality_observability_route(
    # 다른 공급사끼리 비교하면 "품질이 나빠졌다"가 아니라 "공급사가 다르다"를 보게 되므로,
    # profile_name은 선택 필터가 아니라 필수 입력입니다.
    profile_name: str = Query(..., min_length=1),
    limit: int = Query(
        default=OBSERVABILITY_DEFAULT_LIMIT,
        ge=OBSERVABILITY_MIN_LIMIT,
        le=OBSERVABILITY_MAX_LIMIT,
    ),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> ETLQualityObservabilityResponse:
    normalized_profile_name = normalize_etl_filter(profile_name)
    if normalized_profile_name is None:
        # min_length는 공백만 있는 값을 통과시키므로, 공백 입력도 여기서 같은 422로 막습니다.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "profile_name_required",
                "message": "profile_name은 비어 있을 수 없습니다.",
            },
        )
    result = get_etl_quality_observability(
        session,
        profile_name=normalized_profile_name,
        limit=limit,
    )
    return _build_quality_observability_response(result)


@router.get(
    "/api/v1/etl-loads/quality-observability/profiles",
    response_model=ETLQualityObservabilityProfileListResponse,
)
def list_etl_quality_observability_profiles_route(
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> ETLQualityObservabilityProfileListResponse:
    """Suppliers that have at least one quality-available ETL batch to compare."""
    result = list_etl_quality_observability_profiles(session)
    return ETLQualityObservabilityProfileListResponse(
        items=[
            ETLQualityObservabilityProfileResponse(profile_name=item.profile_name)
            for item in result.items
        ]
    )


@router.get("/api/v1/etl-profiles", response_model=ETLProfileListResponse)
def list_etl_profile_options(
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> ETLProfileListResponse:
    # session을 넘겨 runtime override까지 반영합니다. 배포 기본값만 보면 운영자가
    # 방금 내린 프로필이 selector에 남아, 고를 수는 있는데 실행만 409로 막힙니다.
    return ETLProfileListResponse(
        items=[
            ETLProfileResponse(**profile)
            for profile in list_etl_profiles(session=session)
        ]
    )


@router.get(
    "/api/v1/etl-profiles/{profile_id}",
    response_model=ETLProfileDetailResponse,
)
def get_etl_profile_detail_route(
    profile_id: str,
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> ETLProfileDetailResponse:
    try:
        detail = get_etl_profile_detail(profile_id, session=session)
    except ETLProfileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="ETL profile not found.",
        ) from error
    except ETLProfileInactiveError as error:
        # 이 endpoint는 active 버전의 detail을 보여 줍니다. 비활성 프로필에 대해
        # 마지막 active 버전을 그대로 보여 주면 "지금 이 버전으로 실행된다"는 거짓을
        # 말하게 되므로, 404(없음)와 구분되는 409로 상태 충돌을 알립니다.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "inactive_profile",
                "message": "ETL profile is inactive.",
            },
        ) from error

    return ETLProfileDetailResponse(
        id=detail["id"],
        display_name=detail["display_name"],
        profile_name=detail["profile_name"],
        profile_version=detail["profile_version"],
        source_columns={
            source: list(targets)
            for source, targets in detail["source_columns"].items()
        },
        required_source_columns=list(detail["required_source_columns"]),
        defaults=detail["defaults"],
    )


def _log_duplicate_ingestion(
    http_request: Request,
    outcome: ETLWebRunOutcome,
    *,
    request_source_type: str,
) -> None:
    """Record one structured event when a request reuses an existing batch.

    ETLLoadRun stores only the source that first created a batch, so the path this
    request actually arrived on is otherwise lost the moment dedup returns. Both
    duplicate paths in etl.db_loader (the plain SELECT hit and the IntegrityError
    retry after losing the unique-identity race) return created=False here, so
    logging once in the route covers them both without touching the loader.

    Deliberately excluded: initial_source_ref, source_filename, hashes and
    actor_username. The first two can leak supplier paths, and actor_username on a
    duplicate is the original loader rather than the caller who re-sent the file.
    Everything needed later is reachable from etl_load_run_id.
    """
    if outcome.created:
        return
    log_event(
        _LOGGER,
        logging.INFO,
        event="etl_duplicate_ingestion",
        etl_load_run_id=outcome.etl_load_run_id,
        initial_source_type=outcome.initial_source_type,
        request_source_type=request_source_type,
        # log_event only accepts scalars, so this stays a readable string, not a bool.
        same_source=(
            "true" if outcome.initial_source_type == request_source_type else "false"
        ),
        # 미들웨어가 만든 요청 ID를 그대로 씁니다. 여기서 새로 만들면
        # http_request_completed 로그와 이어지지 않습니다.
        request_id=getattr(http_request.state, "request_id", None),
    )


ETL_PROFILE_NOT_FOUND_MESSAGE = "ETL profile not found."


def _build_profile_activation_response(view) -> ETLProfileActivationResponse:
    return ETLProfileActivationResponse(
        profile_id=view.profile_id,
        display_name=view.display_name,
        deployment_active_version=view.deployment_active_version,
        runtime_override_exists=view.runtime_override_exists,
        runtime_active_version=view.runtime_active_version,
        effective_active_version=view.effective_active_version,
        is_active=view.is_active,
        available_versions=list(view.available_versions),
        actor_username=view.actor_username,
        updated_at=view.updated_at,
    )


@router.get(
    "/api/v1/etl-profiles/{profile_id}/activation",
    response_model=ETLProfileActivationResponse,
)
def get_etl_profile_activation_route(
    profile_id: str,
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> ETLProfileActivationResponse:
    """Show the deployment default, the runtime override, and what actually applies.

    비활성 프로필도 200으로 조회됩니다. 이 endpoint의 목적이 바로 "지금 활성인가"를
    묻는 것이므로, 비활성이라고 409를 내면 운영자가 상태를 확인할 방법이 없어집니다.
    같은 이유로 목록 필터(list_etl_profiles)와 달리 여기서는 숨기지 않습니다.
    """
    try:
        view = get_etl_profile_activation(session, profile_id=profile_id)
    except ETLProfileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ETL_PROFILE_NOT_FOUND_MESSAGE,
        ) from error
    return _build_profile_activation_response(view)


@router.put(
    "/api/v1/etl-profiles/{profile_id}/activation",
    response_model=ETLProfileActivationResponse,
)
def set_etl_profile_activation_route(
    request: ETLProfileActivationUpdateRequest,
    profile_id: str,
    current_user=Depends(require_operator),
    session: Session = Depends(get_session),
) -> ETLProfileActivationResponse:
    """Set the runtime active version, or deactivate with a null version.

    PUT을 쓰는 이유는 이 요청이 새 자원을 만드는 것이 아니라 하나뿐인 상태를 통째로
    바꾸기 때문입니다. 같은 body를 두 번 보내면 결과가 같습니다.

    이 endpoint는 Profile Update API가 아닙니다. source_columns/required_source_columns/
    defaults는 여기서 바꿀 수 없고, 바꾸는 것은 "이미 보존된 어떤 버전을 신규 실행에
    쓸 것인가" 하나뿐입니다(Policy A).

    actor는 인증된 current_user에서만 가져옵니다. 요청 body에는 사용자 이름을 넣을
    자리가 없습니다.
    """
    try:
        view = set_etl_profile_activation(
            session,
            profile_id=profile_id,
            active_version=request.active_version,
            actor_user_id=current_user.id,
            actor_username=current_user.username,
        )
    except ETLProfileNotFoundError as error:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ETL_PROFILE_NOT_FOUND_MESSAGE,
        ) from error
    except ETLProfileVersionNotFoundError as error:
        # 프로필은 있는데 그 버전이 보존 목록에 없는 경우입니다. 404(프로필 없음)와
        # 구분되도록 422로 답하고, 고를 수 있는 버전을 함께 알려 줍니다. archive 경로나
        # registry 내부 값은 노출하지 않습니다.
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "unknown_profile_version",
                "message": "요청한 ETL 프로필 버전이 없습니다.",
                "available_versions": registered_profile_versions(profile_id),
            },
        ) from error
    return _build_profile_activation_response(view)


@router.post("/api/v1/etl-loads", response_model=ETLWebRunResponse)
async def create_etl_load_run(
    http_request: Request,
    file: UploadFile = File(...),
    profile_id: str = Form(...),
    current_user=Depends(require_operator),
    session: Session = Depends(get_session),
) -> ETLWebRunResponse:
    # run_web_etl()에 넘기는 값과 로그에 남기는 값이 갈라지지 않도록 한 곳에서 정합니다.
    request_source_type = "upload"
    file_bytes = await file.read()
    try:
        outcome = run_web_etl(
            session,
            profile_id=profile_id,
            source_filename=file.filename or "",
            input_bytes=file_bytes,
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            initial_source_type=request_source_type,
            # 업로드는 파일명이 곧 locator입니다. 디렉터리 경로는 넘기지 않습니다.
            initial_source_ref=_upload_source_ref(file.filename),
        )
    except ETLProfileNotFoundError:
        record_web_etl_run("failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "unsupported_profile",
                "message": "지원하지 않는 공급사 프로필입니다.",
            },
        ) from None
    except ETLProfileInactiveError:
        # 없는 프로필(400 unsupported_profile)과 섞지 않습니다. 프로필은 존재하고
        # archive도 그대로 있지만 지금 실행할 버전이 없는 상태이므로 409입니다.
        record_web_etl_run("failed")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "inactive_profile",
                "message": "비활성화된 공급사 프로필입니다.",
            },
        ) from None
    except (CsvUploadValidationError, ETLPipelineError) as error:
        record_web_etl_run("failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_upload", "message": str(error)},
        ) from None
    except ETLLoadError:
        record_web_etl_run("failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "etl_load_failed",
                "message": "ETL 처리 중 오류가 발생했습니다.",
            },
        ) from None

    # outcome은 run_web_etl()/load_standard_csv()가 이미 commit까지 마친 뒤의 결과이므로,
    # 이 시점에 기록하는 metric은 실제 DB 반영 여부와 항상 일치합니다.
    record_web_etl_run("created" if outcome.created else "duplicate")
    if outcome.created:
        record_web_etl_rows(loaded_rows=outcome.loaded_rows, rejected_rows=outcome.rejected_rows)
    _log_duplicate_ingestion(
        http_request,
        outcome,
        request_source_type=request_source_type,
    )

    return _build_web_run_response(outcome)


def _upload_source_ref(filename: str | None) -> str | None:
    # 사용자 PC의 경로 원문은 저장하지 않고 leaf 파일명만 남깁니다.
    leaf = str(filename or "").replace("\\", "/").split("/")[-1].strip()
    return leaf or None


def _reject_inactive_profile_before_source_fetch(
    session: Session,
    profile_id: str,
) -> None:
    """Block a deactivated profile before any external source I/O happens.

    S3/HTTP feed는 source adapter를 먼저 실행하는 구조입니다. 이 검사가 없으면 서버가
    이미 비활성인 것을 알면서도 외부를 읽고, source가 먼저 실패할 경우 409
    inactive_profile 대신 404/502/503 같은 source 오류를 돌려주게 됩니다. Phase 5A
    정책은 비활성 프로필의 신규 실행을 막는 것이므로 읽기 전에 끊습니다.

    여기서 막는 것은 "allowlist에 있으면서 비활성"인 경우뿐입니다. 없는 profile_id는
    그대로 통과시켜 기존 source-error precedence와 400 unsupported_profile 계약을
    유지합니다. 잘못된 active pointer도 통과시켜 기존대로 실행 시점에 실패합니다.

    비활성 판단은 배포 기본값이 아니라 runtime override까지 반영한 effective 상태입니다.
    그래서 route의 session을 받습니다. 이것이 없으면 runtime에서 내린 프로필의 S3/HTTP
    실행이 외부를 먼저 읽고 나서야 막힙니다.
    """
    if not is_etl_profile_inactive(profile_id, session=session):
        return

    # 실행을 시도하다 막힌 것이므로 업로드 경로와 같은 실패 metric을 남깁니다.
    # 이 시점에 끊었으니 _run_server_side_source_etl()은 호출되지 않고, 따라서
    # failed는 정확히 한 번만 기록됩니다.
    record_web_etl_run("failed")
    raise HTTPException(
        status_code=status.HTTP_409_CONFLICT,
        detail={
            "code": "inactive_profile",
            "message": SERVER_SIDE_INACTIVE_PROFILE_MESSAGE,
        },
    )


def _run_server_side_source_etl(
    session: Session,
    *,
    http_request: Request,
    profile_id: str,
    source_filename: str,
    input_bytes: bytes,
    current_user,
    initial_source_type: str,
    initial_source_ref: str | None,
) -> ETLWebRunResponse:
    """Run the existing Web ETL service for a server-side fetched source.

    S3 and HTTP feed sources only differ in how the CSV bytes arrive, so they share
    the same downstream orchestration, error mapping, and Web ETL metrics.
    """
    try:
        outcome = run_web_etl(
            session,
            profile_id=profile_id,
            source_filename=source_filename,
            input_bytes=input_bytes,
            actor_user_id=current_user.id,
            actor_username=current_user.username,
            initial_source_type=initial_source_type,
            initial_source_ref=initial_source_ref,
        )
    except ETLProfileNotFoundError:
        record_web_etl_run("failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "unsupported_profile",
                "message": "Unsupported supplier profile.",
            },
        ) from None
    except ETLProfileInactiveError:
        # 정상 흐름에서는 _reject_inactive_profile_before_source_fetch()가 이미 걸러
        # 여기까지 오지 않습니다. 프로필이 그 사이에 바뀌는 경우까지 같은 응답을
        # 주도록 남겨 둔 두 번째 방어선입니다.
        record_web_etl_run("failed")
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "inactive_profile",
                "message": SERVER_SIDE_INACTIVE_PROFILE_MESSAGE,
            },
        ) from None
    except (CsvUploadValidationError, ETLPipelineError) as error:
        record_web_etl_run("failed")
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"code": "invalid_upload", "message": str(error)},
        ) from None
    except ETLLoadError:
        record_web_etl_run("failed")
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail={
                "code": "etl_load_failed",
                "message": "An error occurred while processing ETL.",
            },
        ) from None

    record_web_etl_run("created" if outcome.created else "duplicate")
    if outcome.created:
        record_web_etl_rows(
            loaded_rows=outcome.loaded_rows,
            rejected_rows=outcome.rejected_rows,
        )
    # 이번 요청 source는 run_web_etl()에 넘긴 값과 같은 변수라 서로 어긋날 수 없습니다.
    _log_duplicate_ingestion(
        http_request,
        outcome,
        request_source_type=initial_source_type,
    )
    return _build_web_run_response(outcome)


def _raise_s3_source_error(
    *,
    status_code: int,
    code: str,
    message: str,
) -> None:
    """Log a safe, structured S3 source failure without SDK or object details."""
    log_event(
        _LOGGER,
        logging.WARNING,
        event="s3_etl_source_failed",
        error_code=code,
    )
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


@router.post("/api/v1/etl-loads/s3", response_model=ETLWebRunResponse)
def create_s3_etl_load_run(
    request: ETLS3LoadRequest,
    http_request: Request,
    current_user=Depends(require_operator),
    session: Session = Depends(get_session),
) -> ETLWebRunResponse:
    """Download a configured S3 CSV and pass it to the existing Web ETL service."""
    _reject_inactive_profile_before_source_fetch(session, request.profile_id)

    try:
        source = read_s3_csv_object(request.object_key)
    except S3NotConfiguredError:
        _raise_s3_source_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="s3_not_configured",
            message="S3 source is not configured.",
        )
    except S3ObjectNotFoundError:
        _raise_s3_source_error(
            status_code=status.HTTP_404_NOT_FOUND,
            code="s3_object_not_found",
            message="S3 object was not found.",
        )
    except S3KeyNotAllowedError:
        _raise_s3_source_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="s3_key_not_allowed",
            message="S3 object key is not allowed.",
        )
    except S3ReadError:
        _raise_s3_source_error(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="s3_read_failed",
            message="S3 source could not be read.",
        )
    except CsvUploadValidationError as error:
        # This happened before run_web_etl(), so it must not affect Web ETL metrics.
        _raise_s3_source_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_upload",
            message=str(error),
        )

    return _run_server_side_source_etl(
        session,
        http_request=http_request,
        profile_id=request.profile_id,
        source_filename=source.source_filename,
        input_bytes=source.content,
        current_user=current_user,
        initial_source_type="s3",
        # bucket은 저장하지 않고, 허용 prefix를 제거한 상대 key만 남깁니다.
        initial_source_ref=sanitized_object_ref(request.object_key),
    )


def _raise_http_feed_source_error(
    *,
    status_code: int,
    code: str,
    message: str,
) -> None:
    """Log a safe, structured HTTP feed failure without the URL or response body."""
    log_event(
        _LOGGER,
        logging.WARNING,
        event="http_etl_source_failed",
        error_code=code,
    )
    raise HTTPException(
        status_code=status_code,
        detail={"code": code, "message": message},
    )


@router.post("/api/v1/etl-loads/http", response_model=ETLWebRunResponse)
def create_http_feed_etl_load_run(
    request: ETLHTTPFeedLoadRequest,
    http_request: Request,
    current_user=Depends(require_operator),
    session: Session = Depends(get_session),
) -> ETLWebRunResponse:
    """Download the configured trusted HTTP feed CSV and reuse the Web ETL service.

    The feed URL comes from server configuration only. Clients choose the supplier
    profile, never the host, so this endpoint cannot be turned into an SSRF probe.
    """
    _reject_inactive_profile_before_source_fetch(session, request.profile_id)

    try:
        source = read_http_feed_csv()
    except HTTPFeedNotConfiguredError:
        _raise_http_feed_source_error(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            code="http_feed_not_configured",
            message="HTTP feed source is not configured.",
        )
    except HTTPFeedReadError:
        _raise_http_feed_source_error(
            status_code=status.HTTP_502_BAD_GATEWAY,
            code="http_feed_read_failed",
            message="HTTP feed source could not be read.",
        )
    except CsvUploadValidationError as error:
        # This happened before run_web_etl(), so it must not affect Web ETL metrics.
        _raise_http_feed_source_error(
            status_code=status.HTTP_400_BAD_REQUEST,
            code="invalid_upload",
            message=str(error),
        )

    return _run_server_side_source_etl(
        session,
        http_request=http_request,
        profile_id=request.profile_id,
        source_filename=source.source_filename,
        input_bytes=source.content,
        current_user=current_user,
        initial_source_type="http_feed",
        # feed URL/query/token은 저장하지 않습니다. 비밀 없는 고정 식별자만 남깁니다.
        initial_source_ref=ETL_HTTP_FEED_SOURCE_REF,
    )


@router.get(
    "/api/v1/etl-loads/{etl_load_run_id}",
    response_model=ETLLoadDetailResponse,
)
def get_etl_load_run(
    etl_load_run_id: int = Path(..., ge=1),
    product_limit: int = Query(default=50, ge=1, le=100),
    product_offset: int = Query(default=0, ge=0),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> ETLLoadDetailResponse:
    result = get_etl_load_detail(
        session,
        etl_load_run_id=etl_load_run_id,
        product_limit=product_limit,
        product_offset=product_offset,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ETL_LOAD_NOT_FOUND_MESSAGE,
        )
    return _build_detail_response(result)


@router.get(
    "/api/v1/etl-loads/{etl_load_run_id}/rejections",
    response_model=ETLRejectedRowListResponse,
)
def list_etl_rejected_rows(
    etl_load_run_id: int = Path(..., ge=1),
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> ETLRejectedRowListResponse:
    result = list_etl_rejections(
        session,
        etl_load_run_id=etl_load_run_id,
        limit=limit,
        offset=offset,
    )
    if result is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ETL_LOAD_NOT_FOUND_MESSAGE,
        )
    return ETLRejectedRowListResponse(
        available=result.available,
        items=[
            ETLRejectedRowResponse(
                rejected_row_id=item.rejected_row_id,
                source_row_number=item.source_row_number,
                errors=[
                    ETLRejectErrorResponse(
                        code=error.code,
                        field=error.field,
                        message=error.message,
                    )
                    for error in item.errors
                ],
                masked_source_data=item.masked_source_data,
                created_at=item.created_at,
            )
            for item in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


def _build_catalog_reconciliation_response(
    result: CatalogReconciliationReport,
) -> CatalogReconciliationResponse:
    return CatalogReconciliationResponse(
        etl_load_run_id=result.etl_load_run_id,
        supplier_key=result.supplier_key,
        total_rows=result.total_rows,
        loaded_rows=result.loaded_rows,
        rejected_rows=result.rejected_rows,
        new_count=result.new_count,
        changed_count=result.changed_count,
        unchanged_count=result.unchanged_count,
        not_observed_in_batch_count=result.not_observed_in_batch_count,
        field_change_counts=dict(result.field_change_counts),
        items=[
            CatalogReconciliationItemResponse(
                external_product_id=item.external_product_id,
                status=item.status,
                changed_fields={
                    field_name: CatalogReconciliationChangedFieldResponse(
                        before=change["before"],
                        after=change["after"],
                    )
                    for field_name, change in item.changed_fields.items()
                },
            )
            for item in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
    )


@router.get(
    "/api/v1/etl-loads/{etl_load_run_id}/catalog-reconciliation",
    response_model=CatalogReconciliationResponse,
)
def get_catalog_reconciliation_report(
    etl_load_run_id: int = Path(..., ge=1),
    limit: int = Query(default=RECONCILIATION_DEFAULT_LIMIT, ge=1, le=RECONCILIATION_MAX_LIMIT),
    offset: int = Query(default=0, ge=0),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> CatalogReconciliationResponse:
    """Report how one staging batch differs from the live catalog. Read-only."""
    try:
        result = build_catalog_reconciliation_report(
            session,
            etl_load_run_id=etl_load_run_id,
            limit=limit,
            offset=offset,
        )
    except ETLLoadRunNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ETL_LOAD_NOT_FOUND_MESSAGE,
        ) from None
    except CatalogReconciliationDuplicateIdentityError:
        # Promotion Preview와 같은 안전 철학입니다. 어느 행이 진짜인지 알 수 없으므로
        # 임의로 고르지 않고 거부합니다. 내부 경로나 SQL은 노출하지 않습니다.
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail={
                "code": "duplicate_product_identity",
                "message": "같은 공급사 상품 식별자가 배치 안에 중복되어 있습니다.",
            },
        ) from None

    return _build_catalog_reconciliation_response(result)


@router.post(
    "/api/v1/etl-loads/{etl_load_run_id}/promotion-preview",
    response_model=CatalogPromotionPreviewResponse,
    status_code=status.HTTP_200_OK,
)
def create_catalog_promotion_preview(
    response: Response,
    etl_load_run_id: int = Path(..., ge=1),
    _current_user=Depends(require_viewer),
    session: Session = Depends(get_session),
) -> CatalogPromotionPreviewResponse:
    try:
        result = preview_catalog_promotion(
            session,
            etl_load_run_id=etl_load_run_id,
        )
    except ETLLoadRunNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=ETL_LOAD_NOT_FOUND_MESSAGE,
        ) from None

    response.headers["Cache-Control"] = "no-store"
    return _build_promotion_preview_response(result)


@router.post(
    "/api/v1/etl-loads/{etl_load_run_id}/promotions",
    response_model=CatalogPromotionResponse,
    status_code=status.HTTP_200_OK,
)
def create_catalog_promotion(
    request: CatalogPromotionRequest,
    response: Response,
    etl_load_run_id: int = Path(..., ge=1),
    current_user=Depends(require_operator),
    session: Session = Depends(get_session),
) -> CatalogPromotionResponse:
    try:
        result = execute_catalog_promotion(
            session,
            etl_load_run_id=etl_load_run_id,
            confirmation=request.confirmation,
            expected_preview_hash=request.expected_preview_hash,
            actor_user_id=current_user.id,
            actor_username=current_user.username,
        )
    except CatalogPromotionConfirmationRequiredError:
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={
                "code": "confirmation_required",
                "message": (
                    "운영 상품 반영을 위해 명시적인 승인이 필요합니다."
                ),
            },
        ) from None
    except CatalogPromotionInvalidPreviewHashError:
        raise HTTPException(
            status_code=status.HTTP_422_UNPROCESSABLE_ENTITY,
            detail={
                "code": "invalid_preview_hash",
                "message": "expected_preview_hash 형식이 올바르지 않습니다.",
            },
        ) from None
    except ETLLoadRunNotFoundError:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail={
                "code": "etl_load_not_found",
                "message": ETL_LOAD_NOT_FOUND_MESSAGE,
            },
        ) from None
    except CatalogPromotionExecutionFailedError as error:
        detail = {
            "code": "promotion_failed",
            "message": "운영 상품 반영 중 오류가 발생했습니다.",
        }
        if error.promotion_run_id is not None:
            detail["promotion_run_id"] = error.promotion_run_id
        raise HTTPException(
            status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
            detail=detail,
        ) from None

    if result.status == "blocked":
        detail = {
            "code": result.failure_code,
            "message": result.safe_failure_message,
            "promotion_run_id": result.promotion_run_id,
        }
        if result.failure_code == "promotion_blocked":
            detail["blocked_reasons"] = [
                CatalogPromotionBlockedReasonResponse(
                    code=reason.code,
                    message=reason.message,
                    supplier_key=reason.supplier_key,
                    external_product_id=reason.external_product_id,
                    staging_product_ids=list(reason.staging_product_ids),
                ).model_dump()
                for reason in result.blocked_reasons
            ]
        raise HTTPException(
            status_code=status.HTTP_409_CONFLICT,
            detail=detail,
        )

    response.headers["Cache-Control"] = "no-store"
    return _build_promotion_response(result)


def _build_rollback_product_data_response(data):
    if data is None:
        return None
    return _build_promotion_product_data_response(data)


def _build_rollback_preview_response(result: CatalogPromotionRollbackPreview):
    return CatalogPromotionRollbackPreviewResponse(
        target_promotion_run_id=result.target_promotion_run_id,
        preview_schema_version=result.preview_schema_version,
        preview_hash=result.preview_hash,
        rollback_eligible=result.rollback_eligible,
        blocked_reasons=[CatalogPromotionRollbackBlockedReasonResponse(code=r.code, message=r.message, catalog_product_id=r.catalog_product_id, external_product_id=r.external_product_id) for r in result.blocked_reasons],
        restore_count=result.restore_count,
        delete_count=result.delete_count,
        conflict_count=result.conflict_count,
        items=[CatalogPromotionRollbackPreviewItemResponse(audit_id=i.audit_id, catalog_product_id=i.catalog_product_id, external_product_id=i.external_product_id, rollback_action=i.rollback_action, current_data=_build_rollback_product_data_response(i.current_data), restore_data=_build_rollback_product_data_response(i.restore_data), conflict=i.conflict, conflict_reason=i.conflict_reason) for i in result.items],
    )


def _build_rollback_response(result: CatalogPromotionRollbackExecutionResult):
    return CatalogPromotionRollbackResponse(
        rollback_run_id=result.rollback_run_id,
        target_promotion_run_id=result.target_promotion_run_id,
        status="succeeded",
        created=result.created,
        preview_hash=result.preview_hash,
        preview_schema_version=result.preview_schema_version,
        restored_count=result.restored_count,
        deleted_count=result.deleted_count,
        conflict_count=result.conflict_count,
        started_at=result.started_at,
        completed_at=result.completed_at,
        actor_username=result.actor_username,
    )


@router.post("/api/v1/catalog-promotions/{promotion_run_id}/rollback-preview", response_model=CatalogPromotionRollbackPreviewResponse, status_code=status.HTTP_200_OK)
def create_catalog_promotion_rollback_preview(promotion_run_id: int = Path(..., ge=1), response: Response = None, _current_user=Depends(require_viewer), session: Session = Depends(get_session)):
    try:
        result = preview_catalog_promotion_rollback(session, promotion_run_id=promotion_run_id)
    except CatalogPromotionRollbackNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "promotion_not_found", "message": CATALOG_PROMOTION_NOT_FOUND_MESSAGE}) from None
    if response is not None:
        response.headers["Cache-Control"] = "no-store"
    return _build_rollback_preview_response(result)


@router.post("/api/v1/catalog-promotions/{promotion_run_id}/rollback", response_model=CatalogPromotionRollbackResponse, status_code=status.HTTP_200_OK)
def create_catalog_promotion_rollback(request: CatalogPromotionRollbackRequest, response: Response, promotion_run_id: int = Path(..., ge=1), current_user=Depends(require_operator), session: Session = Depends(get_session)):
    try:
        result = execute_catalog_promotion_rollback(
            session,
            promotion_run_id=promotion_run_id,
            confirmation=request.confirmation,
            expected_preview_hash=request.expected_preview_hash,
            actor_user_id=current_user.id,
            actor_username=current_user.username,
        )
    except CatalogPromotionRollbackConfirmationRequiredError:
        raise HTTPException(status_code=status.HTTP_400_BAD_REQUEST, detail={"code": "confirmation_required", "message": "Explicit confirmation is required to execute rollback."}) from None
    except CatalogPromotionRollbackInvalidPreviewHashError:
        raise HTTPException(status_code=status.HTTP_422_UNPROCESSABLE_ENTITY, detail={"code": "invalid_preview_hash", "message": "expected_preview_hash has an invalid format."}) from None
    except CatalogPromotionRollbackNotFoundError:
        raise HTTPException(status_code=status.HTTP_404_NOT_FOUND, detail={"code": "promotion_not_found", "message": CATALOG_PROMOTION_NOT_FOUND_MESSAGE}) from None
    except CatalogPromotionRollbackAlreadyExecutedError as error:
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": "already_rolled_back", "message": "This promotion run has already been rolled back.", "rollback_run_id": error.rollback_run_id}) from None
    except CatalogPromotionRollbackExecutionFailedError as error:
        detail = {"code": "rollback_failed", "message": "Rollback could not be completed."}
        if error.rollback_run_id is not None:
            detail["rollback_run_id"] = error.rollback_run_id
        raise HTTPException(status_code=status.HTTP_500_INTERNAL_SERVER_ERROR, detail=detail) from None
    if result.status == "blocked":
        raise HTTPException(status_code=status.HTTP_409_CONFLICT, detail={"code": result.failure_code, "message": result.safe_failure_message, "rollback_run_id": result.rollback_run_id, "blocked_reasons": [{"code": r.code, "message": r.message, "catalog_product_id": r.catalog_product_id, "external_product_id": r.external_product_id} for r in result.blocked_reasons]})
    response.headers["Cache-Control"] = "no-store"
    return _build_rollback_response(result)
