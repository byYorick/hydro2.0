#ifndef NODE_METRIC_TYPE_H
#define NODE_METRIC_TYPE_H

#include <stddef.h>

/**
 * @brief Типы метрик телеметрии
 */
typedef enum {
    METRIC_TYPE_PH,
    METRIC_TYPE_EC,
    METRIC_TYPE_TEMPERATURE,
    METRIC_TYPE_HUMIDITY,
    METRIC_TYPE_CURRENT,
    METRIC_TYPE_PUMP_STATE,
    METRIC_TYPE_CUSTOM,  // Для пользовательских типов
    METRIC_TYPE_LIGHT_INTENSITY
} metric_type_t;


#ifdef __cplusplus
extern "C" {
#endif
const char *node_metric_type_for_channel(const char *channel, metric_type_t type,
                                         char *out_buf, size_t out_size);
#ifdef __cplusplus
}
#endif
#endif
