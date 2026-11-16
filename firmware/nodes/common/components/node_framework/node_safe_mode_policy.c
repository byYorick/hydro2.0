#include "node_safe_mode_policy.h"
#include <string.h>
bool node_safe_mode_command_allowed(const char *cmd, bool relay_off, bool pwm_off)
{
    if (cmd == NULL) return false;
    if (strcmp(cmd, "enter_safe_mode") == 0 || strcmp(cmd, "exit_safe_mode") == 0 || strcmp(cmd, "state") == 0) return true;
    if ((strcmp(cmd, "set_relay") == 0 || strcmp(cmd, "set_state") == 0) && relay_off) return true;
    return strcmp(cmd, "set_pwm") == 0 && pwm_off;
}
