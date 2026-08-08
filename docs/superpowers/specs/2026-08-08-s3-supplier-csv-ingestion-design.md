# AWS S3 Supplier CSV Ingestion Connector MVP

## Goal

Add a secure, synchronous AWS S3 input path to CatalogGuard Lite's existing
supplier CSV Web ETL flow. The connector downloads one configured S3 object
and passes its bytes to the existing `run_web_etl()` service; it does not
create a second ETL pipeline or change the database schema.

## API

Add `POST /api/v1/etl-loads/s3`.

The JSON request body is:

```json
{
  "profile_id": "sample_fashion_vendor_v1",
  "object_key": "incoming/vendor-a/products.csv"
}
```

The endpoint requires the existing `operator` role and returns the existing
`ETLWebRunResponse`. It passes `current_user.id` and `current_user.username`
to `run_web_etl()` exactly as the multipart Web ETL endpoint does.

## Architecture and data flow

Create `etl/s3_source.py` as a narrow S3 source adapter. It owns only S3
configuration, object-key validation, metadata lookup, safe bounded download,
stream closure, and translation of S3 failures into application exceptions.
Its boto3 client is injectable so tests use a fake client and never contact
AWS. When no client is injected, it creates `boto3.client("s3")` lazily at
read time, never at module import time.

```text
HTTP request
  -> route validation and operator authentication
  -> S3 source adapter
       -> configured bucket/prefix and key validation
       -> HeadObject and ContentLength validation
       -> GetObject and optional ContentLength consistency validation
  -> existing run_web_etl()
  -> existing run_pipeline()
  -> existing load_standard_csv()
  -> existing ETLLoadRun / staging tables
```

The route does not call boto3 directly. After a successful download, it calls
`run_web_etl()` with the downloaded bytes and the leaf CSV filename from the
S3 key. Existing CSV validation, temporary-file bridging, pipeline execution,
SHA-256 duplicate handling, transactional load behavior, audit fields, and
`ETLWebRunResponse` construction remain the source of truth.

## Settings and validation

`CATALOGGUARD_ETL_S3_BUCKET` is required and is read only from the server
environment. The request never accepts a bucket or AWS credentials.

`CATALOGGUARD_ETL_S3_PREFIX` is optional. An unset or blank value permits all
object keys in the configured bucket. When configured, the value is normalized
as an object-key directory prefix with a trailing `/`; therefore
`incoming/vendor/` permits `incoming/vendor/products.csv` but not
`incoming/vendor2/products.csv`.

The adapter rejects an empty key and reuses `validate_csv_filename()` for the
leaf name. It treats an S3 key as an S3 key, never as a local filesystem path.
The leaf name is used as `source_filename` so `ETLLoadRun` stores only the CSV
filename.

Before `GetObject`, the adapter calls `HeadObject` and checks ContentLength
against the existing CSV size limit from `core.upload_validator`/
`config.settings`; no S3-specific limit is duplicated. It rejects empty or
oversized objects before downloading. After `GetObject`, it validates the
response ContentLength before reading, then calls
`Body.read(MAX_UPLOAD_SIZE_BYTES + 1)` and always closes the body in a
`finally` block. The bounded read and the existing shared size validation
reject a changed/oversized object without consuming an unbounded body.
`run_web_etl()` still performs its existing byte-size validation after the
download. VersionId, ETag, and concurrent object-change controls are explicitly
out of scope.

## Errors, logging, and metrics

The route maps adapter failures to safe responses:

| Condition | HTTP | Code |
| --- | --- | --- |
| Bucket not configured | 503 | `s3_not_configured` |
| Object absent | 404 | `s3_object_not_found` |
| Prefix violation | 400 | `s3_key_not_allowed` |
| Empty key or non-CSV leaf | 400 | Existing upload-validation behavior |
| Empty or oversized object | 400 | Existing upload-validation behavior |
| Access denied, AWS communication, malformed S3 response | 502 | `s3_read_failed` |

S3 failures happen before `run_web_etl()` and are logged in a structured,
safe form. They are not recorded in the existing Web ETL metrics, and no new
S3 metric is added in this MVP. AWS credentials, bucket internals, stack
traces, and raw SDK errors are never returned to clients.

`ETLProfileNotFoundError`, CSV validation, pipeline errors, and DB load errors
after download retain the existing Web ETL response mapping and metrics.

## Dependencies and tests

Add `boto3` only to the dependency manifest used by the API runtime
(`requirements-api.txt`), after confirming it is absent. No `moto` dependency
is added.

Tests are written first and use fake S3 clients. They cover successful
operator ingestion, anonymous and viewer rejection, unset-prefix acceptance,
configured-prefix acceptance/rejection, `.csv` validation, HeadObject size
rejection before GetObject, response ContentLength and bounded-body size
rejection, body closure after successful and failed reads, absent objects,
safe AWS read errors, unsupported profiles, existing duplicate behavior, and
actor audit persistence. Existing ETL and Web API tests remain part of
regression coverage. The final checks run the focused S3 tests, related
ETL/Web tests, and `python -m pytest tests -q`.

## Explicit non-goals

No user-selected buckets, credential input or hardcoding, public-bucket
assumptions, DB migration, separate S3 pipeline, async jobs, event-driven S3
ingestion, Terraform changes, or UI changes are part of this MVP.
