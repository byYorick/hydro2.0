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
gcc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined \
  -I firmware/nodes/common/components/node_utils \
  firmware/tests/host/test_command_wire_values.c -lm -o "$out/command-wire"
"$out/command-wire"
gcc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined \
  -I firmware/nodes/common/components/node_framework/include \
  firmware/tests/host/test_telemetry_metric_type.c \
  firmware/nodes/common/components/node_framework/node_metric_type.c \
  -o "$out/telemetry-metric"
"$out/telemetry-metric"
gcc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined \
  -I firmware/nodes/common/components/climate_control/include \
  firmware/tests/host/test_climate_control_logic.c \
  firmware/nodes/common/components/climate_control/climate_control_logic.c \
  -lm -o "$out/climate"
"$out/climate"
gcc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined \
  -I firmware/nodes/common/components/sensors/ds18b20/include \
  firmware/tests/host/test_ds18b20_parse.c \
  firmware/nodes/common/components/sensors/ds18b20/ds18b20_parse.c \
  -lm -o "$out/ds18b20"
"$out/ds18b20"
gcc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined \
  -I firmware/nodes/common/components/config_storage/include \
  -I firmware/nodes/storage_irrigation_node/main \
  firmware/tests/host/test_storage_irr_link_loss.c \
  firmware/nodes/common/components/config_storage/link_loss_timeout.c \
  firmware/nodes/storage_irrigation_node/main/storage_irrigation_link_loss_logic.c \
  -o "$out/storage-irr-link-loss"
"$out/storage-irr-link-loss"
gcc -std=c11 -Wall -Wextra -Werror -fsanitize=undefined \
  -I firmware/nodes/common/components/dose_limit/include \
  firmware/tests/host/test_dose_limit.c \
  firmware/nodes/common/components/dose_limit/dose_limit.c \
  -lm -o "$out/dose-limit"
"$out/dose-limit"
