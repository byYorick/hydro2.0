#ifndef NODE_COMMAND_ID_H
#define NODE_COMMAND_ID_H

#include <stdbool.h>
#include <string.h>

/* Protocol 2.0: up to 128 bytes plus the terminating NUL. */
#define NODE_COMMAND_ID_MAX_LEN 128u
typedef char node_command_id_t[NODE_COMMAND_ID_MAX_LEN + 1u];

static inline bool node_command_id_copy(node_command_id_t target, const char *source)
{
    if (source == NULL || strlen(source) > NODE_COMMAND_ID_MAX_LEN) {
        target[0] = '\0';
        return false;
    }
    memcpy(target, source, strlen(source) + 1u);
    return true;
}

#endif
