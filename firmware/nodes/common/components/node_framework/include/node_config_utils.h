#ifndef NODE_CONFIG_UTILS_H
#define NODE_CONFIG_UTILS_H

#ifdef __cplusplus
extern "C" {
#endif

#include <stddef.h>
#include <stdbool.h>

struct cJSON;

typedef bool (*node_config_channels_match_fn)(const struct cJSON *channels);
typedef struct cJSON *(*node_config_build_channels_fn)(void);

/**
 * @brief Построить патченный конфиг с заменой channels.
 *
 * @param json Входной JSON
 * @param len Длина JSON
 * @param force_replace Принудительно заменить channels
 * @param match_fn Коллбек проверки текущих channels (может быть NULL)
 * @param build_fn Коллбек сборки channels (обязателен)
 * @param changed Выходной флаг изменения
 * @return Новый JSON (malloc), либо NULL если не требуется/ошибка
 */
char *node_config_utils_build_patched_config(const char *json,
                                             size_t len,
                                             bool force_replace,
                                             node_config_channels_match_fn match_fn,
                                             node_config_build_channels_fn build_fn,
                                             bool *changed);

#ifdef __cplusplus
}
#endif

#endif // NODE_CONFIG_UTILS_H
