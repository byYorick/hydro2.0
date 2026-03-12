#ifndef STORAGE_IRRIGATION_NODE_CONFIG_UTILS_H
#define STORAGE_IRRIGATION_NODE_CONFIG_UTILS_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdbool.h>
#include "esp_err.h"

char *storage_irrigation_node_build_patched_config(const char *json, size_t len, bool force_replace, bool *changed);
esp_err_t storage_irrigation_node_patch_stored_config(bool force_replace, bool *changed);

#ifdef __cplusplus
}
#endif

#endif // STORAGE_IRRIGATION_NODE_CONFIG_UTILS_H
