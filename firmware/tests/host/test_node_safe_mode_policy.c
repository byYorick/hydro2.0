#include <assert.h>
#include <stdio.h>
#include "node_safe_mode_policy.h"
int main(void) {
    assert(node_safe_mode_command_allowed("enter_safe_mode", false, false));
    assert(node_safe_mode_command_allowed("exit_safe_mode", false, false));
    assert(node_safe_mode_command_allowed("state", false, false));
    assert(node_safe_mode_command_allowed("set_relay", true, false));
    assert(node_safe_mode_command_allowed("set_pwm", false, true));
    assert(!node_safe_mode_command_allowed("set_relay", false, false));
    assert(!node_safe_mode_command_allowed("set_pwm", false, false));
    assert(!node_safe_mode_command_allowed("dose", true, true));
    assert(!node_safe_mode_command_allowed("restart", false, false));
    assert(!node_safe_mode_command_allowed("set_position", true, true));
    puts("test_node_safe_mode_policy: ok");
}
