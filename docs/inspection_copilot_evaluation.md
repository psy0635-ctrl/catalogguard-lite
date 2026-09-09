# Inspection Copilot Evaluation

## Scope

This is an 18-scenario deterministic regression suite for the existing
read-only Inspection Copilot.  It does not evaluate general model quality and
does not call the OpenAI API in CI.  `ScriptedModel` exercises the Agents SDK
tool loop while synthetic CatalogGuard results provide the only fixture data.

The suite covers these safety and behavior categories:

| Category | Scenarios | What is asserted |
| --- | ---: | --- |
| Groundedness and missing data | 5 | Saved counts, source-row identity, absent rows, and evidence references cannot be invented. |
| Read-only safety | 6 | Auto-fix, promotion, rollback, SQL, Python execution, and a write-oriented injection request return without running a model. |
| Prompt-injection boundary | 2 | User and tool-data instruction strings do not add capability beyond the fixed tool registry. |
| PII and data minimization | 1 | Tool projections mask email and resident-registration-number patterns and exclude raw CSV-only fields. |
| Comparison neutrality | 2 | The existing comparison counts are relayed without improvement/worsening claims; missing and version-mismatched comparisons remain unavailable. |
| Bounded execution | 2 | Correction projections are capped at ten rows and repeated tool calls stop at `MAX_AGENT_TURNS`. |

The focused suite also covers the authenticated endpoint's question-length
validation, optional API-key behavior, safe timeout/invalid-response mapping,
and the Streamlit rendering contract.

## Safety boundary

The Copilot receives exactly four local function tools:

1. `get_current_inspection_summary`
2. `get_source_row_issues`
3. `get_correction_overview`
4. `get_baseline_comparison`

It has no write, SQL, generic HTTP, web-search, shell, code-execution, MCP,
promotion, or rollback tool.  Tool projections retain only the persisted
inspection fields needed to explain a result; projected free-text identifiers,
reasons, and recommendations are privacy-masked before they reach the model.
Structured evidence is checked against the selected persisted run(s) before it
is returned to the client.

Prompt-injection resistance here is capability-based, not a claim that a model
can perfectly ignore every malicious string: catalog data is treated as data,
and there is no write capability for it to obtain.

## Live smoke

Live smoke is optional and must use synthetic data only.  It was not run for
this evaluation when `OPENAI_API_KEY` was absent.  No key is requested, logged,
or committed.  A passing deterministic suite therefore demonstrates the
defined orchestration and boundary contracts, not model accuracy.

## Non-goals

This evaluation does not add tools, endpoints, database tables, migrations,
conversation/audit persistence, model selection UI, rate limiting, or changes
to CatalogGuard inspection rules.  `INSPECTION_VERSION` remains `14`.
