# Canonical JSON Schemas

Authoritative schemas for automation configuration namespaces. These files are the single source of truth shared by:

- **Laravel** validator (`AutomationConfigRegistry` → `JsonSchemaValidator`, Phase 2)
- **AE3 Python** loader (Pydantic models generated from these schemas, Phase 2)
- **Frontend** validation (copy at `backend/laravel/resources/js/schemas/`, Phase 6)
- **AUTHORITY.md** parameter tables (generated via `make generate-authority`, Phase 7)

## Schemas (v1)

| File | Namespace | Status |
|---|---|---|
| `zone_correction.v1.json` | `zone.correction` | Full coverage (48 params + phase overrides) |
| `recipe_phase.v1.json` | recipe phase runtime payload | Full coverage (phase_targets, irrigation, diagnostics_execution) |
| `zone_pid.v1.json` | `zone.pid.ph`, `zone.pid.ec` | Full coverage; cross-field constraints in loader |
| `zone_process_calibration.v1.json` | `zone.process_calibration.*` | Full coverage; "at least one gain > 0" in loader |
| `zone_logic_profile.v1.json` | `zone.logic_profile` | Structural v1; subsystem schemas to be added |
| `system_automation_defaults.v1.json` | `system.automation_defaults` | Placeholder; full schema in later phase |

## Conventions

- **Dialect**: JSON Schema Draft 2020-12 (`$schema` declared in each file)
- **`$id`**: `https://hydro2.local/schemas/<name>/v<N>.json` — local URN, not resolved over network
- **Versioning**: file name encodes major version (`foo.v1.json`); `schema_version` property is `const: N` for runtime sanity
- **Strictness**: `additionalProperties: false` is the default; exceptions are documented per schema
- **Cross-field constraints**: not expressible in standard JSON Schema, enforced in language-side loaders (Pydantic validators, PHP validators)
- **Bounds**: all numeric fields carry `minimum`/`maximum` (or `exclusiveMinimum`); strings use `maxLength`

## Validation

```bash
make schemas-validate
```

Runs each schema through JSON Schema Draft 2020-12 meta-schema to confirm it is itself valid JSON Schema.

## Related specs

- [doc_ai/04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md](../doc_ai/04_BACKEND_CORE/AUTOMATION_CONFIG_AUTHORITY.md) — config authority: namespaces, documents, bundles, live-edit
- [doc_ai/04_BACKEND_CORE/ae3lite.md](../doc_ai/04_BACKEND_CORE/ae3lite.md) — AE3 runtime canonical spec
