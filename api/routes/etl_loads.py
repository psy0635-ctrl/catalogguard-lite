from fastapi import APIRouter, Depends, HTTPException, Path, Query, Response, status
from sqlalchemy.orm import Session

from api.schemas import (
    CatalogPromotionBlockedReasonResponse,
    CatalogPromotionChangedFieldResponse,
    CatalogPromotionPreviewItemResponse,
    CatalogPromotionPreviewResponse,
    CatalogPromotionProductDataResponse,
    ETLLoadDetailResponse,
    ETLLoadListItemResponse,
    ETLLoadListResponse,
    ETLRejectErrorResponse,
    ETLRejectedRowListResponse,
    ETLRejectedRowResponse,
    ETLStagingProductListResponse,
    ETLStagingProductResponse,
)
from db.etl_query_service import (
    ETLLoadDetail,
    ETLLoadList,
    get_etl_load_detail,
    list_etl_rejections,
    list_etl_loads,
    normalize_etl_filter,
)
from db.catalog_promotion_preview_service import (
    CatalogPromotionPreview,
    ETLLoadRunNotFoundError,
    PromotionPreviewItem,
    preview_catalog_promotion,
)
from db.session import get_session


router = APIRouter()
ETL_LOAD_NOT_FOUND_MESSAGE = "ETL 적재 배치를 찾을 수 없습니다."


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
            )
            for item in result.items
        ],
        total=result.total,
        limit=result.limit,
        offset=result.offset,
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


@router.get("/api/v1/etl-loads", response_model=ETLLoadListResponse)
def list_etl_load_runs(
    limit: int = Query(default=20, ge=1, le=100),
    offset: int = Query(default=0, ge=0),
    filename: str | None = Query(default=None),
    profile_name: str | None = Query(default=None),
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
    "/api/v1/etl-loads/{etl_load_run_id}",
    response_model=ETLLoadDetailResponse,
)
def get_etl_load_run(
    etl_load_run_id: int = Path(..., ge=1),
    product_limit: int = Query(default=50, ge=1, le=100),
    product_offset: int = Query(default=0, ge=0),
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


@router.post(
    "/api/v1/etl-loads/{etl_load_run_id}/promotion-preview",
    response_model=CatalogPromotionPreviewResponse,
    status_code=status.HTTP_200_OK,
)
def create_catalog_promotion_preview(
    response: Response,
    etl_load_run_id: int = Path(..., ge=1),
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
