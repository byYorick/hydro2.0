#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../.."
out=$(mktemp -d)
trap 'rm -rf "$out"' EXIT
gcc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined \
  -I firmware/nodes/common/components/actuator_failsafe/include \
  firmware/tests/host/test_actuator_failsafe_logic.c \
  firmware/nodes/common/components/actuator_failsafe/actuator_failsafe_logic.c \
  -o "$out/actuator"
gcc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined \
  -I firmware/nodes/storage_irrigation_node/main \
  firmware/tests/host/test_estop_lock_policy.c -o "$out/estop"
"$out/actuator"
"$out/estop"
