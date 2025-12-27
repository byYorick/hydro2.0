# DB_FIX_PLAN

Purpose: repair database migrations/schema to match canonical model and make migrations safe, repeatable, and verifiable.
Reference: doc_ai/DB_CANON_V2.md (target schema and invariants).

## 0) Scope and assumptions
- DB: PostgreSQL with optional TimescaleDB extensions.
- Target: align schema + migrations to the canonical grow-cycle-centric model.
- Non-goals: full data backfill for legacy tables unless required by prod data.

## 1) Baseline and diff
- Inventory all migrations that create/alter core tables and list their final column sets.
- Compare against DB_CANON_V2 and list deltas (missing tables/columns, wrong types, legacy leftovers).
- Decide the canonical schema for conflicts (example: zones<->nodes 1:1 rule vs zone_id nullable).
- Output: a delta checklist to drive fixes.

## 2) Migration hygiene and compile fixes
- Fix migration compile errors (missing imports, invalid Schema::hasIndex usage).
- Remove or guard non-portable/unsafe statements (raw SQL without driver checks).
- Ensure up/down paths are symmetric and do not drop columns before rename.
- Output: migrations run clean on empty DB.

## 3) Telemetry model alignment
- Confirm new telemetry model uses sensors (telemetry_samples + telemetry_last with sensor_id).
- Update telemetry_agg_* and related indexes to use sensor_id (or document why legacy model remains).
- Recreate telemetry_raw view after telemetry_samples replacement.
- Align partitioning/retention scripts with the new schema.
- Output: telemetry tables + view + retention work consistently.

## 4) Commands and zone_events partitioning
- Replace fixed CREATE TABLE ... commands_partitioned with dynamic column list from information_schema.
- Ensure INSERT uses explicit column lists to avoid data loss.
- Re-apply constraints and indexes after swap.
- Output: partitioning migration safe across schema changes.

## 5) Grow cycles and recipe revisions
- Add safe backfill plan for recipe_revision_id and current phase/step pointers.
- Reconcile legacy zone_recipe_instances drop with active data constraints.
- Add invariants (one active cycle per zone) as partial unique indexes.
- Output: grow_cycle data integrity matches canonical invariants.

## 6) Consistency checks and tests
- Run db_sanity.sql and database index tests.
- Add missing test coverage for new constraints and partitioning expectations.
- Output: repeatable verification script for CI/staging.

## 7) Rollout plan
- Dry run on a clean DB.
- Run on staging snapshot, validate invariants, compare row counts.
- Production rollout with maintenance window and rollback path (DDL + data checks).

## Deliverables
- Fixed migrations.
- Updated telemetry partitioning/retention scripts.
- Verified schema against DB_CANON_V2.
- DB diagrams (PNG) in doc_ai/diagrams.
