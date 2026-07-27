from fastapi import APIRouter, Depends, HTTPException, Path, Query, status
from sqlalchemy.orm import Session

from api.schemas import (
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
