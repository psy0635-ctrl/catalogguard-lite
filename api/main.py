from fastapi import FastAPI

from api.routes.inspections import router as inspections_router


app = FastAPI(
    title="CatalogGuard Lite API",
    version="0.1.0",
)

app.include_router(inspections_router)


@app.get("/health")
def health_check() -> dict[str, str]:
    return {
        "status": "ok",
        "service": "catalogguard-lite-api",
    }
