#include <assert.h>
#include <stdio.h>
#include "node_safe_mode_policy.h"
#include "node_command_id.h"
static void test_command_id_correlation(void)
{
    node_command_id_t wire;
    node_command_id_t pending;
    node_command_id_t terminal;
    memset(wire, 'x', NODE_COMMAND_ID_MAX_LEN);
    wire[NODE_COMMAND_ID_MAX_LEN] = '\0';
    assert(node_command_id_copy(pending, wire));
    assert(node_command_id_copy(terminal, pending));
    assert(strcmp(wire, terminal) == 0);
    assert(strlen(terminal) == 128);
    char oversized[NODE_COMMAND_ID_MAX_LEN + 2u];
    memset(oversized, 'y', sizeof(oversized) - 1u);
    oversized[sizeof(oversized) - 1u] = '\0';
    assert(!node_command_id_copy(pending, oversized));
    assert(pending[0] == '\0');
}

int main(void) {
    test_command_id_correlation();
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
