#pragma once
#include <stdbool.h>
/** Read-only, repeated stop and explicit OFF remain usable while latched. */
bool node_safe_mode_command_allowed(const char *cmd, bool relay_off, bool pwm_off);
