# CatalogGuard Lite v0.2.0 Fact Consistency Matrix

## Release identity

| Fact | Verified value | Evidence scope |
|---|---|---|
| Official release | v0.2.0 | GitHub Release, published 2026-09-10 |
| Release target commit | `29abc4aff8825074f7cd3feab6d370bd9b3f0e4e` | annotated tag `v0.2.0` peel target |
| Tag object | `a7e1fdc0e560991a7bae7ae0e3acdb0137a87a2c` | annotated tag object |
| Release URL | https://github.com/psy0635-ctrl/catalogguard-lite/releases/tag/v0.2.0 | GitHub Release |
| Related PRs | #85 reinspection, #86 read-only Copilot, #88 Copilot evaluation hardening | merged pull requests |
| Inspection version | `14` | `config/settings.py` |
| Alembic head | `20260908_0019` | repository migration head |
| Agents SDK | `openai-agents==0.22.1` | requirements |
| Default agent model | `gpt-5.6-terra` | `CATALOGGUARD_AGENT_MODEL` default |
| Full repository validation | 2394 passed, 382 skipped, 13 deselected | v0.2.0 release validation |
| Required CI jobs | test, browser-e2e, kubernetes-smoke, terraform-validate, airflow-smoke | fresh-main release validation |

## Product and agent facts

| Topic | Accurate statement | Do not claim |
|---|---|---|
| Inspection authority | Deterministic Rule Engine remains the source of truth for errors, categories, prices, and rules. | AI decides inspection results. |
| Reinspection | A user manually changes the original product CSV, then runs the existing inspection path again and may open the existing Comparison workflow. | Worksheet upload, automatic source recovery, or automatic correction. |
| Comparison | Stored issue rows are compared as a multiset; `base_only` and `target_only` are neutral facts. | Full product diff or automatic quality-improvement judgment. |
| Copilot tools | Exactly four read-only Function Tools: current summary, source-row issues, correction overview, baseline comparison. | Write, SQL, generic HTTP/web, shell/code execution, MCP, Promotion, or Rollback capability. |
| Evidence | Responses use `answer`, `evidence`, `limitations`; persisted run/source row/rule/comparison references are validated. Empty or unmatched evidence is rejected. | Ungrounded model prose is accepted. |
| Safety | New category/rule/price judgment requests are rejected before model execution; tool data is data, not instructions. | Perfect prompt-injection prevention or general AI accuracy. |
| API key | `OPENAI_API_KEY` is optional. Without it only Copilot returns unavailable; normal application flows remain available. | API key is shown, embedded, or required for all functions. |
| Model validation | Twenty deterministic safety and behavior scenarios passed. Live model smoke was not run because no API key was configured. | Live-model success or accuracy score. |

## Scope language for employment materials

| Area | Safe wording |
|---|---|
| Kubernetes | Manifests and kind smoke validation; not production cluster operation. |
| Terraform | AWS staging IaC definition and mock-provider validation; not actual Terraform apply. |
| ETL | CSV, HTTP, and S3 inputs; profile-based standardization; staging, persistent rejection, masked safe rejection CSV, and source-row lineage. |
| Promotion | Preview, explicit confirmation, hash revalidation, transaction, audit, and conflict-safe rollback. |
| AI | A read-only explanation aid over persisted results, not an auto-fix, auto-inspection, RAG, MCP, LangGraph, or vector database system. |
