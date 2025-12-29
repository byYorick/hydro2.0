/**
 * @file node_utils.h
 * @brief Утилиты для работы с нодами
 * 
 * Общие helper функции для всех нод
 */

#ifndef NODE_UTILS_H
#define NODE_UTILS_H

#include "esp_err.h"
#include "config_storage.h"
#include "wifi_manager.h"
#include "mqtt_manager.h"
#include <stddef.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Безопасное копирование строки с гарантией null-termination
 * 
 * @param dest Буфер назначения
 * @param src Исходная строка
 * @param dest_size Размер буфера назначения
 * @return ESP_OK при успехе
 */
esp_err_t node_utils_strncpy_safe(char *dest, const char *src, size_t dest_size);

/**
 * @brief Получить hardware_id (MAC-основанный идентификатор ноды)
 *
 * Формат: esp32-<mac6bytes lowercase hex>
 *
 * @param hardware_id Буфер для записи hardware_id
 * @param size Размер буфера (рекомендуется >= 32)
 * @return ESP_OK при успехе
 */
esp_err_t node_utils_get_hardware_id(char *hardware_id, size_t size);

/**
 * @brief Инициализация WiFi конфигурации из config_storage
 * 
 * @param wifi_config Указатель на структуру для заполнения
 * @param wifi_ssid Буфер для SSID (должен быть CONFIG_STORAGE_MAX_STRING_LEN)
 * @param wifi_password Буфер для пароля (должен быть CONFIG_STORAGE_MAX_STRING_LEN)
 * @return ESP_OK при успехе, ESP_ERR_NOT_FOUND если конфиг не найден
 */
esp_err_t node_utils_init_wifi_config(
    wifi_manager_config_t *wifi_config,
    char *wifi_ssid,
    char *wifi_password
);

/**
 * @brief Инициализация MQTT конфигурации из config_storage
 * 
 * @param mqtt_config Указатель на структуру для заполнения
 * @param node_info Указатель на структуру node_info для заполнения
 * @param mqtt_host Буфер для хоста (должен быть CONFIG_STORAGE_MAX_STRING_LEN)
 * @param mqtt_username Буфер для username (должен быть CONFIG_STORAGE_MAX_STRING_LEN)
 * @param mqtt_password Буфер для password (должен быть CONFIG_STORAGE_MAX_STRING_LEN)
 * @param node_id Буфер для node_id (должен быть минимум 64 байта)
 * @param gh_uid Буфер для gh_uid (должен быть CONFIG_STORAGE_MAX_STRING_LEN)
 * @param zone_uid Буфер для zone_uid (должен быть CONFIG_STORAGE_MAX_STRING_LEN)
 * @param default_gh_uid Дефолтное значение gh_uid
 * @param default_zone_uid Дефолтное значение zone_uid
 * @param default_node_id Дефолтное значение node_id
 * @return ESP_OK при успехе
 */
esp_err_t node_utils_init_mqtt_config(
    mqtt_manager_config_t *mqtt_config,
    mqtt_node_info_t *node_info,
    char *mqtt_host,
    char *mqtt_username,
    char *mqtt_password,
    char *node_id,
    char *gh_uid,
    char *zone_uid,
    const char *default_gh_uid,
    const char *default_zone_uid,
    const char *default_node_id
);

/**
 * @brief Получение текущего timestamp в секундах
 * 
 * Возвращает Unix timestamp с учетом смещения времени, установленного через set_time.
 * Если время не синхронизировано, возвращает аптайм (uptime).
 * 
 * @return Unix timestamp в секундах, или аптайм если время не синхронизировано
 */
int64_t node_utils_get_timestamp_seconds(void);

/**
 * @brief Получение текущего Unix timestamp в секундах с учетом смещения
 * 
 * Использует смещение времени (time_offset_us), установленное через set_time,
 * для преобразования esp_timer_get_time() в Unix timestamp.
 * 
 * @return Unix timestamp в секундах, или аптайм если время не синхронизировано
 */
int64_t node_utils_now_epoch(void);

/**
 * @brief Установка времени через смещение
 * 
 * Вычисляет и сохраняет смещение времени для преобразования esp_timer_get_time()
 * в Unix timestamp.
 * 
 * @param unix_ts_sec Unix timestamp в секундах (UTC)
 * @return ESP_OK при успехе
 */
esp_err_t node_utils_set_time(int64_t unix_ts_sec);

/**
 * @brief Получение Unix timestamp (UTC время)
 * 
 * Возвращает реальное Unix время, если SNTP синхронизирован.
 * Если SNTP не синхронизирован, возвращает 0.
 * 
 * @return Unix timestamp в секундах, или 0 если время не синхронизировано
 */
int64_t node_utils_get_unix_timestamp(void);

/**
 * @brief Проверка синхронизации времени
 * 
 * @return true если время синхронизировано через set_time
 */
bool node_utils_is_time_synced(void);

/**
 * @brief Базовая инициализация NVS, esp_netif, event loop и Wi‑Fi STA
 * 
 * Идёмпотентная: повторные вызовы не считаются ошибкой. Используется
 * всеми нодами для одинакового пути старта перед node_framework.
 * 
 * @return ESP_OK при успехе или ESP_ERR_xxx при фатальной ошибке
 */
esp_err_t node_utils_bootstrap_network_stack(void);

/**
 * @brief Публикация node_hello сообщения для регистрации узла
 * 
 * @param node_type Тип ноды ("ph", "ec", "pump", "climate")
 * @param capabilities Массив capabilities (например, ["ph", "temperature"])
 * @param capabilities_count Количество capabilities
 * @return ESP_OK при успехе
 */
esp_err_t node_utils_publish_node_hello(
    const char *node_type,
    const char *capabilities[],
    size_t capabilities_count
);

/**
 * @brief Публикация NodeConfig отчета на сервер
 *
 * Отправляет полный NodeConfig, сохраненный в NVS, в топик
 * hydro/{gh}/{zone}/{node}/config_report.
 *
 * @return ESP_OK при успехе
 */
esp_err_t node_utils_publish_config_report(void);

/**
 * @brief Запрос времени у сервера через MQTT
 * 
 * Публикует запрос времени в топик hydro/time/request
 * Сервер должен ответить командой set_time
 * 
 * @return ESP_OK при успехе
 */
esp_err_t node_utils_request_time(void);

#ifdef __cplusplus
}
#endif

#endif // NODE_UTILS_H
