# AWS S3 Supplier CSV Ingestion Connector MVP Implementation Plan

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** Add an operator-only S3 CSV source that safely feeds the existing Web ETL path.

**Architecture:** `etl/s3_source.py` validates configured S3 access and returns bounded downloaded bytes plus the leaf filename. The new route maps adapter errors, then sends those two values and the authenticated actor to the unmodified `run_web_etl()` pipeline bridge.

**Tech Stack:** Python 3.11, FastAPI, SQLAlchemy, pytest, boto3 1.43.54, existing Prometheus helpers.

## Global Constraints

- Use only the server configuration `CATALOGGUARD_ETL_S3_BUCKET` (required) and `CATALOGGUARD_ETL_S3_PREFIX` (optional); do not accept bucket or credentials in HTTP input.
- Normalize a configured prefix to a trailing `/`; an unset/blank prefix permits every key in the configured bucket.
- Reuse `validate_csv_filename()` and one shared byte-count size validator; never duplicate the 5 MiB limit.
- Call HeadObject and validate ContentLength before GetObject; validate GetObject ContentLength too; read at most `MAX_UPLOAD_SIZE_BYTES + 1` bytes and always close the body.
- Lazily create the boto3 client only at an S3 read, support fake-client injection, and rely on boto3's default credential provider chain.
- Do not create a second ETL pipeline, a database migration, UI/infra changes, new metrics, a moto dependency, or AWS calls in tests.
- S3 pre-ETL failures get structured safe logs but are not written to existing Web ETL metrics. Once download succeeds, preserve the existing created/duplicate/failed and row metrics behavior.
- Preserve existing SHA-256 idempotency and actor audit by calling `run_web_etl()` with `current_user.id` and `current_user.username`.
- Do not run `git add`, `git commit`, or `git push`.

---

## File structure

- Create `etl/s3_source.py`: S3 configuration, key/prefix validation, metadata-first bounded download, exception translation, safe logging.
- Modify `core/upload_validator.py`: expose byte-count validation so both upload bytes and S3 ContentLength use one limit.
- Modify `config/settings.py`: define environment-variable names and getters without resolving them at import time.
- Modify `api/schemas.py`: add the two-field JSON request model.
- Modify `api/routes/etl_loads.py`: wire the protected S3 endpoint to the adapter then existing Web ETL service.
- Modify `requirements-api.txt`: add the verified boto3 runtime package only.
- Create `tests/etl/test_s3_source.py`: fake-client unit tests for adapter behavior and resource cleanup.
- Create `tests/test_api_etl_s3_load.py`: route, RBAC, error mapping, and Postgres integration tests.
- Modify `tests/test_upload_validator.py`: direct behavior tests for the shared byte-count validator.

### Task 1: Shared size validation and S3 adapter

**Files:**
- Create: `etl/s3_source.py`
- Modify: `core/upload_validator.py`
- Modify: `config/settings.py`
- Modify: `requirements-api.txt`
- Modify: `tests/test_upload_validator.py`
- Test: `tests/etl/test_s3_source.py`

**Interfaces:**
- Consumes: `MAX_UPLOAD_SIZE_BYTES`, `CsvUploadValidationError`, and `validate_csv_filename()`.
- Produces: `S3SourceObject(source_filename: str, content: bytes)`, `read_s3_csv_object(object_key: str, *, client: S3Client | None = None) -> S3SourceObject`, `S3NotConfiguredError`, `S3ObjectNotFoundError`, `S3KeyNotAllowedError`, and `S3ReadError`.

- [ ] **Step 1: Write the failing shared-size tests**

```python
def test_validate_csv_size_bytes_count_rejects_empty_size():
    with pytest.raises(CsvUploadValidationError):
        validate_csv_size_bytes_count(0)


def test_validate_csv_size_bytes_count_rejects_size_above_existing_limit():
    with pytest.raises(CsvUploadValidationError):
        validate_csv_size_bytes_count(MAX_UPLOAD_SIZE_BYTES + 1)
```

The break these catch is bypassing the existing upload limit for S3 metadata.

- [ ] **Step 2: Run the shared-size tests to verify red**

Run: `python -m pytest tests/test_upload_validator.py -q`

Expected: import failure for `validate_csv_size_bytes_count`.

- [ ] **Step 3: Implement the common byte-count validator**

```python
def validate_csv_size_bytes_count(size_bytes: int) -> None:
    if size_bytes == 0:
        raise CsvUploadValidationError("업로드한 파일이 비어 있습니다.")
    if size_bytes > MAX_UPLOAD_SIZE_BYTES:
        raise CsvUploadValidationError("파일 크기가 너무 큽니다.")


def validate_csv_file_size(file_bytes: bytes) -> None:
    validate_csv_size_bytes_count(len(file_bytes))
```

Keep the existing user-facing validation messages and behavior for byte uploads.

- [ ] **Step 4: Run the shared-size tests to verify green**

Run: `python -m pytest tests/test_upload_validator.py -q`

Expected: PASS.

- [ ] **Step 5: Write failing S3 adapter tests using a complete fake client/body**

```python
def test_unset_prefix_allows_a_csv_anywhere_in_the_configured_bucket(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    monkeypatch.delenv("CATALOGGUARD_ETL_S3_PREFIX", raising=False)
    result = read_s3_csv_object(
        "other/vendor/products.csv",
        client=FakeS3Client(
            head_response={"ContentLength": 13},
            object_response={"ContentLength": 13, "Body": FakeBody(b"supplier,csv\n")},
        ),
    )
    assert result.source_filename == "products.csv"
    assert result.content == b"supplier,csv\n"


def test_prefix_blocks_similar_but_outside_directory_before_s3_calls(monkeypatch):
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_BUCKET", "catalogguard-source")
    monkeypatch.setenv("CATALOGGUARD_ETL_S3_PREFIX", "incoming/vendor")
    client = FakeS3Client(head_response={}, object_response={})
    with pytest.raises(S3KeyNotAllowedError):
        read_s3_csv_object("incoming/vendor2/products.csv", client=client)
    assert client.calls == []
```

Add independent tests for blank key, non-CSV leaf, missing bucket, configured-prefix acceptance, missing object, AccessDenied/client failure, malformed metadata/response, zero and oversized HeadObject size before GetObject, oversized GetObject ContentLength before `Body.read`, bounded-byte oversize rejection, and body closure after both successful and raising reads. The fakes record calls and closure only where ordering and cleanup are observable behavior.

- [ ] **Step 6: Run adapter tests to verify red**

Run: `python -m pytest tests/etl/test_s3_source.py -q`

Expected: collection failure because `etl.s3_source` does not exist.

- [ ] **Step 7: Implement settings and the minimal adapter**

```python
CATALOGGUARD_ETL_S3_BUCKET_ENV_VAR = "CATALOGGUARD_ETL_S3_BUCKET"
CATALOGGUARD_ETL_S3_PREFIX_ENV_VAR = "CATALOGGUARD_ETL_S3_PREFIX"

def get_catalogguard_etl_s3_bucket() -> str | None:
    value = os.environ.get(CATALOGGUARD_ETL_S3_BUCKET_ENV_VAR, "").strip()
    return value or None

def get_catalogguard_etl_s3_prefix() -> str | None:
    value = os.environ.get(CATALOGGUARD_ETL_S3_PREFIX_ENV_VAR, "").strip().strip("/")
    return f"{value}/" if value else None

def read_s3_csv_object(object_key: str, *, client=None) -> S3SourceObject:
    bucket = _require_configured_bucket()
    source_filename = _validate_object_key(object_key)
    _validate_configured_prefix(object_key)
    client = boto3.client("s3") if client is None else client
    validate_csv_size_bytes_count(_content_length(client.head_object(Bucket=bucket, Key=object_key)))
    response = client.get_object(Bucket=bucket, Key=object_key)
    validate_csv_size_bytes_count(_content_length(response))
    body = _response_body(response)
    try:
        content = body.read(MAX_UPLOAD_SIZE_BYTES + 1)
    finally:
        body.close()
    validate_csv_size_bytes_count(len(content))
    return S3SourceObject(source_filename=source_filename, content=content)
```

Translate botocore `ClientError` code `NoSuchKey`/`404` to
`S3ObjectNotFoundError`; translate other SDK, network, malformed-response, and
body-read failures to `S3ReadError`. Do not log raw exception text, bucket,
credentials, request identifiers, or full object key. Create `boto3.client("s3")`
inside `read_s3_csv_object()` only when `client is None`.

- [ ] **Step 8: Add the runtime dependency and run adapter tests to verify green**

Add exactly `boto3==1.43.54` to `requirements-api.txt`; this release is the
current PyPI release and supports the project Python runtime. Run:

`python -m pytest tests/test_upload_validator.py tests/etl/test_s3_source.py -q`

Expected: PASS with no AWS network calls.

### Task 2: S3 API endpoint, error mapping, and ETL integration

**Files:**
- Modify: `api/schemas.py`
- Modify: `api/routes/etl_loads.py`
- Test: `tests/test_api_etl_s3_load.py`

**Interfaces:**
- Consumes: `ETLS3LoadRequest`, `read_s3_csv_object()`, S3 adapter exceptions, `require_operator`, and `run_web_etl()`.
- Produces: `POST /api/v1/etl-loads/s3` returning `ETLWebRunResponse`.

- [ ] **Step 1: Write failing endpoint contract and authorization tests**

```python
def test_s3_endpoint_passes_downloaded_leaf_and_authenticated_actor_to_web_etl(monkeypatch):
    monkeypatch.setattr(etl_loads_route, "read_s3_csv_object", lambda key: S3SourceObject("products.csv", b"supplier,csv\n"))
    monkeypatch.setattr(etl_loads_route, "run_web_etl", fake_outcome_service)
    response = client.post(ENDPOINT, json={"profile_id": "sample_fashion_vendor_v1", "object_key": "incoming/vendor/products.csv"})
    assert response.status_code == 200
    assert response.json()["source_filename"] == "products.csv"


def test_anonymous_s3_endpoint_returns_401_without_reading_s3(monkeypatch):
    monkeypatch.setattr(etl_loads_route, "read_s3_csv_object", lambda key: pytest.fail("S3 must not be read"))
    assert client.post(ENDPOINT, json={"profile_id": "sample_fashion_vendor_v1", "object_key": "products.csv"}).status_code == 401

def test_viewer_s3_endpoint_returns_403_without_reading_s3(monkeypatch):
    override_current_user(role="viewer")
    monkeypatch.setattr(etl_loads_route, "read_s3_csv_object", lambda key: pytest.fail("S3 must not be read"))
    assert client.post(ENDPOINT, json={"profile_id": "sample_fashion_vendor_v1", "object_key": "products.csv"}).status_code == 403
```

The primary break these tests catch is bypassing operator authorization or bypassing the existing Web ETL service/response contract.

- [ ] **Step 2: Run endpoint tests to verify red**

Run: `python -m pytest tests/test_api_etl_s3_load.py -q`

Expected: collection failure because the S3 endpoint and request schema are absent.

- [ ] **Step 3: Add the request model and the thin route**

```python
class ETLS3LoadRequest(BaseModel):
    profile_id: str
    object_key: str


@router.post("/api/v1/etl-loads/s3", response_model=ETLWebRunResponse)
def create_s3_etl_load_run(request: ETLS3LoadRequest, current_user=Depends(require_operator), session=Depends(get_session)):
    source = read_s3_csv_object(request.object_key)
    outcome = run_web_etl(session, profile_id=request.profile_id,
                          source_filename=source.source_filename,
                          input_bytes=source.content,
                          actor_user_id=current_user.id,
                          actor_username=current_user.username)
    return _build_web_run_response(outcome)
```

Map adapter exceptions to the specified 503/404/400/502 safe detail codes and
log their safe event/code. For successful downloads, mirror the existing
route's `record_web_etl_run()` and `record_web_etl_rows()` behavior around
`run_web_etl()` errors and outcomes; do not call those functions for adapter
failures.

- [ ] **Step 4: Add failing route error and metric-boundary tests**

```python
@pytest.mark.parametrize(
    ("error", "expected_status", "expected_code"),
    [(S3NotConfiguredError(), 503, "s3_not_configured"),
     (S3ObjectNotFoundError(), 404, "s3_object_not_found"),
     (S3KeyNotAllowedError(), 400, "s3_key_not_allowed"),
     (S3ReadError(), 502, "s3_read_failed")],
)
def test_s3_adapter_failures_are_safe_and_do_not_record_web_etl_metrics(
    monkeypatch, error, expected_status, expected_code
):
    monkeypatch.setattr(etl_loads_route, "read_s3_csv_object", lambda key: (_ for _ in ()).throw(error))
    monkeypatch.setattr(etl_loads_route, "record_web_etl_run", lambda outcome: pytest.fail("metric must not be recorded"))
    response = client.post(ENDPOINT, json={"profile_id": "sample_fashion_vendor_v1", "object_key": "products.csv"})
    assert response.status_code == expected_status
    assert response.json()["detail"]["code"] == expected_code
```

Also test unsupported profile maps to `unsupported_profile`, uploaded CSV and
pipeline validation retains `invalid_upload`, DB load errors retain
`etl_load_failed`, and the returned safe response does not expose injected raw
SDK error text.

- [ ] **Step 5: Run endpoint tests to verify red then green**

Run: `python -m pytest tests/test_api_etl_s3_load.py -q`

Expected before mapping: the new error-mapping tests fail; after minimal route
mapping/logging/metric implementation: PASS.

- [ ] **Step 6: Add Postgres integration tests with a fake S3 adapter**

```python
def test_s3_endpoint_persists_staging_and_actor_and_reuses_duplicate_identity(postgres_api, monkeypatch):
    monkeypatch.setattr(etl_loads_route, "read_s3_csv_object", fake_supplier_csv_source)
    first = authenticated_client.post(ENDPOINT, json=REQUEST)
    second = authenticated_client.post(ENDPOINT, json=REQUEST)
    assert first.json()["created"] is True
    assert second.json()["created"] is False
    assert stored_run.actor_username == username
```

Use real `run_web_etl()` and a real test PostgreSQL session when configured;
skip through the established fixture when no test database exists. Assert the
staging row count, leaf source filename, actor fields, and one persistent
`ETLLoadRun` rather than mock call counts.

- [ ] **Step 7: Run the focused S3 and regression suites**

Run:

`python -m pytest tests/etl/test_s3_source.py tests/test_api_etl_s3_load.py tests/etl/test_web_service.py tests/test_api_etl_web_run.py tests/test_actor_audit.py -q`

Expected: zero failures; PostgreSQL-only cases may skip only when its test URL
is unset.

### Task 3: Final verification and review

**Files:**
- Review only: all changed files

- [ ] **Step 1: Run the full suite**

Run: `python -m pytest tests -q`

Expected: `failed = 0`; separately report actual passed, skipped, and
deselected counts.

- [ ] **Step 2: Run static Git checks**

Run:

`git diff --check`

`git status --short`

`git diff --stat`

Expected: no whitespace errors, no staged files, and only the planned source,
test, dependency, and documentation changes.

- [ ] **Step 3: Inspect the final diff against global constraints**

Verify no credentials or `.env` edits, no client-selected bucket, no route
boto3 call, no duplicate size constant, no migration/UI/Terraform changes, no
unbounded body read, and no unclosed body stream. Report actual test results
and leave the work uncommitted.
