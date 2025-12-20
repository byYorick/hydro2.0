/**
 * @file light_node_config_utils.h
 * @brief Вспомогательные функции для патча NodeConfig light_node.
 */

#ifndef LIGHT_NODE_CONFIG_UTILS_H
#define LIGHT_NODE_CONFIG_UTILS_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdbool.h>

char *light_node_build_patched_config(const char *json, size_t len, bool force_replace, bool *changed);

#ifdef __cplusplus
}
#endif

#endif // LIGHT_NODE_CONFIG_UTILS_H
