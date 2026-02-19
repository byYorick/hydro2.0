#!/usr/bin/env bash
# AE2 S12 gate runner:
# 1) collect SLO baseline CSV (remote by default, local optional)
# 2) calculate release decision artifact

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

DOCKER_COMPOSE_FILE="$PROJECT_ROOT/backend/docker-compose.dev.yml"
DOC_DIR="$PROJECT_ROOT/doc_ai/10_AI_DEV_GUIDES"
BASELINE_CSV="${AE2_S12_BASELINE_CSV:-$DOC_DIR/AE2_S12_STAGING_SLO_BASELINE.csv}"
DECISION_TXT="${AE2_S12_DECISION_TXT:-$DOC_DIR/AE2_S12_STAGING_RELEASE_DECISION.txt}"
BUNDLE_CHECK_SCRIPT="$PROJECT_ROOT/tools/testing/check_ae2_s12_release_bundle.sh"
SUMMARY_SCRIPT="$PROJECT_ROOT/tools/testing/build_ae2_s12_gate_summary.py"
SUMMARY_MD="${AE2_S12_SUMMARY_MD:-$DOC_DIR/AE2_S12_STAGING_GATE_SUMMARY.md}"
METADATA_SCRIPT="$PROJECT_ROOT/tools/testing/build_ae2_s12_gate_metadata.py"
METADATA_JSON="${AE2_S12_METADATA_JSON:-$DOC_DIR/AE2_S12_STAGING_GATE_METADATA.json}"
FINALIZE_SCRIPT="$PROJECT_ROOT/tools/testing/finalize_ae2_s12_docs.py"

MODE="${AE2_SLO_PROBE_MODE:-remote}"
REQUESTS="${AE2_SLO_PROBE_REQUESTS:-240}"
CONCURRENCY="${AE2_SLO_PROBE_CONCURRENCY:-40}"
BOOTSTRAP_WAIT_SEC="${AE2_SLO_PROBE_BOOTSTRAP_WAIT_SEC:-60}"
BASE_URL="${AE2_SLO_PROBE_BASE_URL:-}"
AUTHORIZATION="${AE2_SLO_PROBE_AUTHORIZATION:-}"
HTTP_TIMEOUT_SEC="${AE2_SLO_PROBE_HTTP_TIMEOUT_SEC:-}"
VERIFY_TLS="${AE2_SLO_PROBE_VERIFY_TLS:-}"
TRACE_ID_PREFIX="${AE2_SLO_PROBE_TRACE_ID_PREFIX:-}"
RUN_BUNDLE_CHECK="${AE2_S12_RUN_BUNDLE_CHECK:-true}"
EXPECT_DECISION="${AE2_S12_EXPECT_DECISION:-ALLOW_FULL_ROLLOUT}"
WRITE_SUMMARY="${AE2_S12_WRITE_SUMMARY:-true}"
WRITE_METADATA="${AE2_S12_WRITE_METADATA:-true}"
AUTO_FINALIZE_DOCS="${AE2_S12_AUTO_FINALIZE_DOCS:-false}"

to_abs_path() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf "%s" "$path"
  else
    printf "%s/%s" "$PROJECT_ROOT" "$path"
  fi
}

BASELINE_CSV="$(to_abs_path "$BASELINE_CSV")"
DECISION_TXT="$(to_abs_path "$DECISION_TXT")"
SUMMARY_MD="$(to_abs_path "$SUMMARY_MD")"
METADATA_JSON="$(to_abs_path "$METADATA_JSON")"

if [[ "$MODE" != "remote" && "$MODE" != "local" ]]; then
  echo "[ERROR] AE2_SLO_PROBE_MODE must be 'remote' or 'local'" >&2
  exit 2
fi

if [[ "$MODE" == "remote" && -z "$BASE_URL" ]]; then
  echo "[ERROR] AE2_SLO_PROBE_BASE_URL is required (example: http://staging-ae:8000)" >&2
  exit 2
fi

mkdir -p "$DOC_DIR"
mkdir -p "$(dirname "$BASELINE_CSV")"
mkdir -p "$(dirname "$DECISION_TXT")"
mkdir -p "$(dirname "$SUMMARY_MD")"
mkdir -p "$(dirname "$METADATA_JSON")"

probe_env_args=(
  -e AE2_SLO_PROBE_MODE="$MODE"
  -e AE2_SLO_PROBE_AUTHORIZATION="$AUTHORIZATION"
  -e AE2_SLO_PROBE_OUTPUT_MODE=csv
  -e AE2_SLO_PROBE_REQUESTS="$REQUESTS"
  -e AE2_SLO_PROBE_CONCURRENCY="$CONCURRENCY"
  -e AE2_SLO_PROBE_BOOTSTRAP_WAIT_SEC="$BOOTSTRAP_WAIT_SEC"
)
if [[ "$MODE" == "remote" ]]; then
  probe_env_args+=(-e AE2_SLO_PROBE_BASE_URL="$BASE_URL")
fi

if [[ -n "$HTTP_TIMEOUT_SEC" ]]; then
  probe_env_args+=(-e AE2_SLO_PROBE_HTTP_TIMEOUT_SEC="$HTTP_TIMEOUT_SEC")
fi
if [[ -n "$VERIFY_TLS" ]]; then
  probe_env_args+=(-e AE2_SLO_PROBE_VERIFY_TLS="$VERIFY_TLS")
fi
if [[ -n "$TRACE_ID_PREFIX" ]]; then
  probe_env_args+=(-e AE2_SLO_PROBE_TRACE_ID_PREFIX="$TRACE_ID_PREFIX")
fi

echo "[INFO] AE2 S12 gate runner mode: $MODE"
echo "[INFO] AE2 S12 gate: collecting baseline..."
docker compose -f "$DOCKER_COMPOSE_FILE" run --rm --no-deps \
  "${probe_env_args[@]}" \
  automation-engine python tests/s12_cutover_slo_probe.py \
  > "$BASELINE_CSV"

echo "[INFO] AE2 S12 gate: calculating release decision..."
cat "$BASELINE_CSV" | docker compose -f "$DOCKER_COMPOSE_FILE" run --rm --no-deps -T \
  automation-engine python tests/s12_slo_release_decision.py --stdin \
  > "$DECISION_TXT"

echo "[INFO] Baseline artifact: $BASELINE_CSV"
echo "[INFO] Decision artifact: $DECISION_TXT"
echo "[INFO] Decision summary:"
head -n 1 "$DECISION_TXT"

run_bundle_check_normalized="$(printf "%s" "$RUN_BUNDLE_CHECK" | tr '[:upper:]' '[:lower:]')"
expect_decision_normalized="$(printf "%s" "$EXPECT_DECISION" | tr '[:lower:]' '[:upper:]' | xargs)"
if [[ "$expect_decision_normalized" == DECISION=* ]]; then
  expect_decision_normalized="${expect_decision_normalized#DECISION=}"
fi
if [[ -z "$expect_decision_normalized" ]]; then
  expect_decision_normalized="ALLOW_FULL_ROLLOUT"
fi
write_summary_normalized="$(printf "%s" "$WRITE_SUMMARY" | tr '[:upper:]' '[:lower:]')"
auto_finalize_normalized="$(printf "%s" "$AUTO_FINALIZE_DOCS" | tr '[:upper:]' '[:lower:]')"
if [[ "$write_summary_normalized" == "1" || "$write_summary_normalized" == "true" || "$write_summary_normalized" == "yes" ]]; then
  if [[ ! -f "$SUMMARY_SCRIPT" ]]; then
    echo "[ERROR] Summary script is missing: $SUMMARY_SCRIPT" >&2
    exit 2
  fi
  echo "[INFO] AE2 S12 gate: writing summary markdown..."
  python3 "$SUMMARY_SCRIPT" \
    --baseline-csv "$BASELINE_CSV" \
    --decision-txt "$DECISION_TXT" \
    --output-md "$SUMMARY_MD" \
    --mode "$MODE"
  echo "[INFO] Summary artifact: $SUMMARY_MD"
else
  echo "[INFO] Summary generation: SKIPPED (AE2_S12_WRITE_SUMMARY=$WRITE_SUMMARY)"
fi

write_metadata_normalized="$(printf "%s" "$WRITE_METADATA" | tr '[:upper:]' '[:lower:]')"
if [[ "$write_metadata_normalized" == "1" || "$write_metadata_normalized" == "true" || "$write_metadata_normalized" == "yes" ]]; then
  if [[ ! -f "$METADATA_SCRIPT" ]]; then
    echo "[ERROR] Metadata script is missing: $METADATA_SCRIPT" >&2
    exit 2
  fi
  echo "[INFO] AE2 S12 gate: writing metadata json..."
  python3 "$METADATA_SCRIPT" \
    --mode "$MODE" \
    --baseline-csv "$BASELINE_CSV" \
    --decision-txt "$DECISION_TXT" \
    --summary-md "$SUMMARY_MD" \
    --output-json "$METADATA_JSON" \
    --base-url "$BASE_URL" \
    --requests "$REQUESTS" \
    --concurrency "$CONCURRENCY" \
    --bootstrap-wait-sec "$BOOTSTRAP_WAIT_SEC" \
    --run-bundle-check "$RUN_BUNDLE_CHECK" \
    --expect-decision "$expect_decision_normalized"
  echo "[INFO] Metadata artifact: $METADATA_JSON"
else
  echo "[INFO] Metadata generation: SKIPPED (AE2_S12_WRITE_METADATA=$WRITE_METADATA)"
fi

if [[ "$run_bundle_check_normalized" == "1" || "$run_bundle_check_normalized" == "true" || "$run_bundle_check_normalized" == "yes" ]]; then
  if [[ ! -x "$BUNDLE_CHECK_SCRIPT" ]]; then
    echo "[ERROR] Bundle check script is missing or not executable: $BUNDLE_CHECK_SCRIPT" >&2
    exit 2
  fi
  require_remote_metadata_for_check="false"
  if [[ "$auto_finalize_normalized" == "1" || "$auto_finalize_normalized" == "true" || "$auto_finalize_normalized" == "yes" ]]; then
    if [[ "$MODE" == "remote" ]]; then
      require_remote_metadata_for_check="true"
      echo "[INFO] AE2 S12 gate: strict remote metadata check enabled (auto-finalize requested)"
    fi
  fi
  metadata_for_check="$METADATA_JSON"
  if [[ "$write_metadata_normalized" != "1" && "$write_metadata_normalized" != "true" && "$write_metadata_normalized" != "yes" ]]; then
    metadata_for_check=""
  fi
  echo "[INFO] AE2 S12 gate: running bundle consistency check..."
  AE2_S12_BASELINE_CSV="$BASELINE_CSV" \
  AE2_S12_DECISION_TXT="$DECISION_TXT" \
  AE2_S12_EXPECT_DECISION="$expect_decision_normalized" \
  AE2_S12_METADATA_JSON="$metadata_for_check" \
  AE2_S12_REQUIRE_REMOTE_METADATA="$require_remote_metadata_for_check" \
  "$BUNDLE_CHECK_SCRIPT"
else
  echo "[INFO] Bundle consistency check: SKIPPED (AE2_S12_RUN_BUNDLE_CHECK=$RUN_BUNDLE_CHECK)"
fi

if [[ "$auto_finalize_normalized" == "1" || "$auto_finalize_normalized" == "true" || "$auto_finalize_normalized" == "yes" ]]; then
  if [[ "$MODE" != "remote" ]]; then
    echo "[INFO] Auto-finalize docs: SKIPPED (requires AE2_SLO_PROBE_MODE=remote)"
  elif [[ "$run_bundle_check_normalized" != "1" && "$run_bundle_check_normalized" != "true" && "$run_bundle_check_normalized" != "yes" ]]; then
    echo "[INFO] Auto-finalize docs: SKIPPED (requires AE2_S12_RUN_BUNDLE_CHECK=true)"
  elif [[ "$write_metadata_normalized" != "1" && "$write_metadata_normalized" != "true" && "$write_metadata_normalized" != "yes" ]]; then
    echo "[INFO] Auto-finalize docs: SKIPPED (requires AE2_S12_WRITE_METADATA=true)"
  elif [[ "$expect_decision_normalized" == "ANY" ]]; then
    echo "[INFO] Auto-finalize docs: SKIPPED (requires strict AE2_S12_EXPECT_DECISION, ANY is not allowed)"
  elif [[ "$expect_decision_normalized" != "ALLOW_FULL_ROLLOUT" ]]; then
    echo "[INFO] Auto-finalize docs: SKIPPED (requires AE2_S12_EXPECT_DECISION=ALLOW_FULL_ROLLOUT)"
  else
    if [[ ! -f "$FINALIZE_SCRIPT" ]]; then
      echo "[ERROR] Finalize script is missing: $FINALIZE_SCRIPT" >&2
      exit 2
    fi
    echo "[INFO] AE2 S12 gate: running docs finalization..."
    AE2_S12_BASELINE_CSV="$BASELINE_CSV" \
    AE2_S12_DECISION_TXT="$DECISION_TXT" \
    AE2_S12_METADATA_JSON="$metadata_for_check" \
    AE2_S12_EXPECT_DECISION="$expect_decision_normalized" \
    python3 "$FINALIZE_SCRIPT" --apply
  fi
else
  echo "[INFO] Auto-finalize docs: SKIPPED (AE2_S12_AUTO_FINALIZE_DOCS=$AUTO_FINALIZE_DOCS)"
fi
