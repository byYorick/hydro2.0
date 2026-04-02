#!/bin/bash
# Точечный launcher для smart-irrigation E2E pipeline на реальной test_node.

set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REAL_HW_LAUNCHER="$SCRIPT_DIR/run_automation_engine_real_hardware.sh"

export HYDRO_SEED_PROFILE="${HYDRO_SEED_PROFILE:-smart-irrigation}"
export SCENARIO_SET="${SCENARIO_SET:-smart_irrigation}"

echo "🧪 Smart irrigation E2E launcher"
echo "  - HYDRO_SEED_PROFILE=${HYDRO_SEED_PROFILE}"
echo "  - SCENARIO_SET=${SCENARIO_SET}"
echo "  - real-hardware harness: ${REAL_HW_LAUNCHER}"

exec "$REAL_HW_LAUNCHER" "$@"
