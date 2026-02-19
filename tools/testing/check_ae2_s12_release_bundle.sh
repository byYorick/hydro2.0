#!/usr/bin/env bash
# AE2 S12 release bundle checker:
# validates that baseline CSV and decision TXT exist and are consistent.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
PROJECT_ROOT="$(cd "$SCRIPT_DIR/../.." && pwd)"

DOCKER_COMPOSE_FILE="$PROJECT_ROOT/backend/docker-compose.dev.yml"
DOC_DIR="$PROJECT_ROOT/doc_ai/10_AI_DEV_GUIDES"
BASELINE_CSV="${AE2_S12_BASELINE_CSV:-$DOC_DIR/AE2_S12_STAGING_SLO_BASELINE.csv}"
DECISION_TXT="${AE2_S12_DECISION_TXT:-$DOC_DIR/AE2_S12_STAGING_RELEASE_DECISION.txt}"
EXPECT_DECISION_RAW="${AE2_S12_EXPECT_DECISION:-ALLOW_FULL_ROLLOUT}"
METADATA_JSON_DEFAULT="$DOC_DIR/AE2_S12_STAGING_GATE_METADATA.json"
REQUIRE_REMOTE_METADATA="${AE2_S12_REQUIRE_REMOTE_METADATA:-false}"
require_remote_normalized="$(printf "%s" "$REQUIRE_REMOTE_METADATA" | tr '[:upper:]' '[:lower:]')"
EXPECT_DECISION="$(printf "%s" "$EXPECT_DECISION_RAW" | tr '[:lower:]' '[:upper:]' | xargs)"
if [[ "$EXPECT_DECISION" == DECISION=* ]]; then
  EXPECT_DECISION="${EXPECT_DECISION#DECISION=}"
fi
if [[ -z "$EXPECT_DECISION" ]]; then
  EXPECT_DECISION="ALLOW_FULL_ROLLOUT"
fi
expect_decision_normalized="$EXPECT_DECISION"

if [[ "$require_remote_normalized" == "1" || "$require_remote_normalized" == "true" || "$require_remote_normalized" == "yes" ]]; then
  if [[ "$expect_decision_normalized" == "ANY" ]]; then
    echo "[ERROR] AE2_S12_REQUIRE_REMOTE_METADATA=true requires strict expected decision (AE2_S12_EXPECT_DECISION must not be ANY)." >&2
    exit 1
  fi
fi

if [[ "${AE2_S12_METADATA_JSON+x}" == "x" ]]; then
  METADATA_JSON="${AE2_S12_METADATA_JSON}"
else
  METADATA_JSON="$METADATA_JSON_DEFAULT"
fi

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
if [[ -n "$METADATA_JSON" ]]; then
  METADATA_JSON="$(to_abs_path "$METADATA_JSON")"
fi

if [[ ! -s "$BASELINE_CSV" ]]; then
  echo "[ERROR] Baseline CSV not found or empty: $BASELINE_CSV" >&2
  exit 2
fi
if [[ ! -s "$DECISION_TXT" ]]; then
  echo "[ERROR] Decision TXT not found or empty: $DECISION_TXT" >&2
  exit 2
fi

recorded_decision="$(head -n 1 "$DECISION_TXT" | tr -d '\r' | xargs)"
if [[ ! "$recorded_decision" =~ ^decision= ]]; then
  echo "[ERROR] Decision TXT first line must start with 'decision=': $DECISION_TXT" >&2
  exit 2
fi

computed_output="$(cat "$BASELINE_CSV" | docker compose -f "$DOCKER_COMPOSE_FILE" run --rm --no-deps -T \
  automation-engine python tests/s12_slo_release_decision.py --stdin)"
computed_decision="$(printf "%s\n" "$computed_output" | head -n 1 | tr -d '\r' | xargs)"

echo "[INFO] Recorded decision: $recorded_decision"
echo "[INFO] Computed decision: $computed_decision"

if [[ "$recorded_decision" != "$computed_decision" ]]; then
  echo "[ERROR] Decision mismatch between TXT and CSV-derived output." >&2
  echo "[ERROR] Full computed output:" >&2
  printf "%s\n" "$computed_output" >&2
  exit 1
fi

if [[ "$EXPECT_DECISION" != "ANY" ]]; then
  expected_line="decision=$EXPECT_DECISION"
  if [[ "$recorded_decision" != "$expected_line" ]]; then
    echo "[ERROR] Decision does not match expected value." >&2
    echo "[ERROR] Expected: $expected_line" >&2
    echo "[ERROR] Actual:   $recorded_decision" >&2
    exit 1
  fi
  echo "[INFO] Expected decision check: PASS ($expected_line)"
else
  echo "[INFO] Expected decision check: SKIPPED (AE2_S12_EXPECT_DECISION=ANY)"
fi

if [[ "$require_remote_normalized" == "1" || "$require_remote_normalized" == "true" || "$require_remote_normalized" == "yes" ]]; then
  if [[ -z "$METADATA_JSON" || ! -s "$METADATA_JSON" ]]; then
    echo "[ERROR] Remote metadata is required but metadata json is missing: ${METADATA_JSON:-<empty>}" >&2
    exit 1
  fi
fi

if [[ -n "$METADATA_JSON" && -s "$METADATA_JSON" ]]; then
  metadata_dump="$(python3 - "$METADATA_JSON" <<'PY'
import json, sys
from pathlib import Path
path = Path(sys.argv[1])
payload = json.loads(path.read_text(encoding="utf-8"))
mode = str(payload.get("mode", "")).strip().lower()
base_url = str(payload.get("base_url", "")).strip()
decision = str((payload.get("decision") or {}).get("recorded", "")).strip()
artifacts = payload.get("artifacts") or {}
baseline = str(artifacts.get("baseline_csv", "")).strip()
decision_txt = str(artifacts.get("decision_txt", "")).strip()
print(mode)
print(base_url)
print(decision)
print(baseline)
print(decision_txt)
PY
)"
  metadata_mode="$(printf "%s\n" "$metadata_dump" | sed -n '1p')"
  metadata_base_url="$(printf "%s\n" "$metadata_dump" | sed -n '2p')"
  metadata_decision="$(printf "%s\n" "$metadata_dump" | sed -n '3p')"
  metadata_baseline="$(printf "%s\n" "$metadata_dump" | sed -n '4p')"
  metadata_decision_txt="$(printf "%s\n" "$metadata_dump" | sed -n '5p')"

  if [[ -n "$metadata_decision" && "$metadata_decision" != "$recorded_decision" ]]; then
    echo "[ERROR] Metadata recorded decision mismatch." >&2
    echo "[ERROR] metadata decision: $metadata_decision" >&2
    echo "[ERROR] artifact decision: $recorded_decision" >&2
    exit 1
  fi

  if [[ -n "$metadata_baseline" ]]; then
    metadata_baseline_abs="$(to_abs_path "$metadata_baseline")"
    if [[ "$metadata_baseline_abs" != "$BASELINE_CSV" ]]; then
      echo "[ERROR] Metadata baseline path mismatch." >&2
      echo "[ERROR] metadata baseline: $metadata_baseline_abs" >&2
      echo "[ERROR] checker baseline:  $BASELINE_CSV" >&2
      exit 1
    fi
  fi

  if [[ -n "$metadata_decision_txt" ]]; then
    metadata_decision_txt_abs="$(to_abs_path "$metadata_decision_txt")"
    if [[ "$metadata_decision_txt_abs" != "$DECISION_TXT" ]]; then
      echo "[ERROR] Metadata decision path mismatch." >&2
      echo "[ERROR] metadata decision: $metadata_decision_txt_abs" >&2
      echo "[ERROR] checker decision:  $DECISION_TXT" >&2
      exit 1
    fi
  fi

  if [[ "$require_remote_normalized" == "1" || "$require_remote_normalized" == "true" || "$require_remote_normalized" == "yes" ]]; then
    if [[ "$metadata_mode" != "remote" ]]; then
      echo "[ERROR] Remote metadata required, but metadata mode is '$metadata_mode'." >&2
      exit 1
    fi
    if [[ -z "$metadata_base_url" ]]; then
      echo "[ERROR] Remote metadata required, but metadata base_url is empty." >&2
      exit 1
    fi
  fi

  echo "[INFO] Metadata check: PASS ($METADATA_JSON)"
else
  echo "[INFO] Metadata check: SKIPPED (metadata json missing)"
fi

echo "[INFO] AE2 S12 release bundle consistency: PASS"
exit 0
