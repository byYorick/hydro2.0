#include "node_metric_type.h"
#include <string.h>

// Маппинг канала к metric_type согласно каноническому формату (UPPERCASE)
const char *node_metric_type_for_channel(const char *channel, metric_type_t type,
                                          char *out_buf, size_t out_size) {
    if (channel == NULL) {
        return "OTHER";
    }

    /* TDS (ppm) с ec_node — отдельный MQTT channel id; не смешивать с EC (mS/cm) на ec_sensor. */
    if (strcmp(channel, "ec_tds_ppm") == 0) {
        return "TDS";
    }

    // Прямой маппинг каналов → metric_type (канонический формат)
    if (strcmp(channel, "ph_sensor") == 0 || strcmp(channel, "ph") == 0) {
        if (type == METRIC_TYPE_PH) {
            return "PH";
        }
        /* Вторичные метрики на том же железном канале — не подменяют PH. */
    }
    if (strcmp(channel, "ec_sensor") == 0 || strcmp(channel, "ec") == 0) {
        if (type == METRIC_TYPE_EC) {
            return "EC";
        }
        /* Например METRIC_TYPE_CUSTOM на ec_sensor — не тегировать как EC. */
    }
    if (strcmp(channel, "air_temp_c") == 0 || strcmp(channel, "temperature") == 0) {
        return "TEMPERATURE";
    }
    if (strcmp(channel, "air_rh") == 0 || strcmp(channel, "humidity") == 0) {
        return "HUMIDITY";
    }
    if (strcmp(channel, "co2_ppm") == 0 || strcmp(channel, "co2") == 0) {
        return "CO2";
    }
    if (strcmp(channel, "ina209") == 0 || strcmp(channel, "pump_bus_current") == 0) {
        return "PUMP_CURRENT";
    }
    if (strcmp(channel, "flow_present") == 0) {
        return "FLOW_RATE";
    }
    /* Температура раствора: один metric_type для канонического и альтернативных id сегмента топика
       (см. digital-twin/sim_world и NODE_CHANNELS_REFERENCE — firmware channel solution_temp_c). */
    if (strcmp(channel, "solution_temp_c") == 0 || strcmp(channel, "solution_temp") == 0 ||
        strcmp(channel, "temp_water") == 0 || strcmp(channel, "water_temp_c") == 0) {
        return "TEMPERATURE";
    }

    if (strcmp(channel, "light") == 0 || strcmp(channel, "light_level") == 0) {
        return "LIGHT_INTENSITY";
    }

    // Fallback: используем metric_type enum с преобразованием в UPPERCASE
    switch (type) {
        case METRIC_TYPE_PH: return "PH";
        case METRIC_TYPE_EC: return "EC";
        case METRIC_TYPE_TEMPERATURE: return "TEMPERATURE";
        case METRIC_TYPE_HUMIDITY: return "HUMIDITY";
        case METRIC_TYPE_CURRENT: return "PUMP_CURRENT";
        case METRIC_TYPE_PUMP_STATE: return "PUMP_STATE";
        case METRIC_TYPE_LIGHT_INTENSITY: return "LIGHT_INTENSITY";
        default: {
            // Если ничего не подошло, используем имя канала в UPPERCASE
            if (!out_buf || out_size == 0) {
                return "OTHER";
            }
            strncpy(out_buf, channel, out_size - 1);
            out_buf[out_size - 1] = '\0';
            // Преобразуем в uppercase
            for (char *p = out_buf; *p; p++) {
                if (*p >= 'a' && *p <= 'z') {
                    *p = *p - 'a' + 'A';
                }
            }
            return out_buf;
        }
    }
}
