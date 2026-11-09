#include <assert.h>
#include <string.h>

#include "node_metric_type.h"

int main(void) {
    char buffer[32];
    assert(strcmp(node_metric_type_for_channel("light", METRIC_TYPE_CUSTOM,
                                               buffer, sizeof(buffer)), "LIGHT_INTENSITY") == 0);
    assert(strcmp(node_metric_type_for_channel("light_level", METRIC_TYPE_CUSTOM,
                                               buffer, sizeof(buffer)), "LIGHT_INTENSITY") == 0);
    assert(strcmp(node_metric_type_for_channel("lux_main", METRIC_TYPE_LIGHT_INTENSITY,
                                               buffer, sizeof(buffer)), "LIGHT_INTENSITY") == 0);
    assert(strcmp(node_metric_type_for_channel("ec_tds_ppm", METRIC_TYPE_CUSTOM,
                                               buffer, sizeof(buffer)), "TDS") == 0);
    assert(strcmp(node_metric_type_for_channel("ph_sensor", METRIC_TYPE_PH,
                                               buffer, sizeof(buffer)), "PH") == 0);
    assert(strcmp(node_metric_type_for_channel("solution_temp_c", METRIC_TYPE_CUSTOM,
                                               buffer, sizeof(buffer)), "TEMPERATURE") == 0);
    assert(strcmp(node_metric_type_for_channel("ina209", METRIC_TYPE_CURRENT,
                                               buffer, sizeof(buffer)), "PUMP_CURRENT") == 0);
    assert(strcmp(node_metric_type_for_channel("custom", METRIC_TYPE_CUSTOM,
                                               buffer, sizeof(buffer)), "CUSTOM") == 0);
    assert(strcmp(node_metric_type_for_channel(NULL, METRIC_TYPE_CUSTOM,
                                               buffer, sizeof(buffer)), "OTHER") == 0);
    assert(strcmp(node_metric_type_for_channel("custom", METRIC_TYPE_CUSTOM,
                                               NULL, 0), "OTHER") == 0);
    assert(strcmp(node_metric_type_for_channel("custom", METRIC_TYPE_CUSTOM,
                                               buffer, 0), "OTHER") == 0);
    return 0;
}
