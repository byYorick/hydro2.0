/**
 * @file config_storage.h
 * @brief Хранение и загрузка NodeConfig из NVS
 * 
 * Компонент для работы с NodeConfig:
 * - Загрузка конфигурации из NVS при старте
 * - Сохранение обновленного конфига в NVS
 * - API для доступа к параметрам конфигурации
 * 
 * Согласно:
 * - firmware/NODE_CONFIG_SPEC.md
 * - doc_ai/02_HARDWARE_FIRMWARE/NODE_ARCH_FULL.md
 */

#ifndef CONFIG_STORAGE_H
#define CONFIG_STORAGE_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

// Максимальные размеры для строк
#define CONFIG_STORAGE_MAX_STRING_LEN 128
#define CONFIG_STORAGE_MAX_JSON_SIZE  4096

/**
 * @brief Структура для параметров MQTT из NodeConfig
 */
typedef struct {
    char host[CONFIG_STORAGE_MAX_STRING_LEN];
    uint16_t port;
    uint16_t keepalive;
    char username[CONFIG_STORAGE_MAX_STRING_LEN];
    char password[CONFIG_STORAGE_MAX_STRING_LEN];
    bool use_tls;
} config_storage_mqtt_t;

/**
 * @brief Структура для параметров Wi-Fi из NodeConfig
 */
typedef struct {
    char ssid[CONFIG_STORAGE_MAX_STRING_LEN];
    char password[CONFIG_STORAGE_MAX_STRING_LEN];
    bool auto_reconnect;
    uint16_t timeout_sec;
} config_storage_wifi_t;

/**
 * @brief Сохранение последней валидной температуры для компенсации EC
 *
 * @param temperature Температура раствора в градусах Цельсия
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t config_storage_set_last_temperature(float temperature);

/**
 * @brief Получение сохраненной температуры для компенсации EC
 *
 * @param temperature Указатель для сохранения значения
 * @return esp_err_t ESP_OK если значение найдено
 */
esp_err_t config_storage_get_last_temperature(float *temperature);

/**
 * @brief Инициализация config_storage
 *
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t config_storage_init(void);

/**
 * @brief Загрузка NodeConfig из NVS
 * 
 * @return esp_err_t 
 *   - ESP_OK: конфиг загружен успешно
 *   - ESP_ERR_NOT_FOUND: конфиг не найден в NVS
 *   - ESP_ERR_INVALID_SIZE: конфиг слишком большой
 *   - ESP_FAIL: ошибка парсинга JSON
 */
esp_err_t config_storage_load(void);

/**
 * @brief Сохранение NodeConfig в NVS
 * 
 * @param json_config JSON строка с конфигурацией
 * @param json_len Длина JSON строки
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t config_storage_save(const char *json_config, size_t json_len);

/**
 * @brief Проверка наличия конфигурации в NVS
 * 
 * @return true если конфиг существует
 */
bool config_storage_exists(void);

/**
 * @brief Получение JSON конфигурации
 * 
 * @param buffer Буфер для JSON строки
 * @param buffer_size Размер буфера
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t config_storage_get_json(char *buffer, size_t buffer_size);

/**
 * @brief Получение node_id из конфигурации
 * 
 * @param node_id Буфер для node_id
 * @param node_id_size Размер буфера
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t config_storage_get_node_id(char *node_id, size_t node_id_size);

/**
 * @brief Получение type из конфигурации
 * 
 * @param type Буфер для type
 * @param type_size Размер буфера
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t config_storage_get_type(char *type, size_t type_size);

/**
 * @brief Получение version из конфигурации
 * 
 * @param version Указатель для сохранения version
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t config_storage_get_version(int *version);

/**
 * @brief Получение gh_uid из конфигурации
 * 
 * @param gh_uid Буфер для gh_uid
 * @param gh_uid_size Размер буфера
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t config_storage_get_gh_uid(char *gh_uid, size_t gh_uid_size);

/**
 * @brief Получение zone_uid из конфигурации
 * 
 * @param zone_uid Буфер для zone_uid
 * @param zone_uid_size Размер буфера
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t config_storage_get_zone_uid(char *zone_uid, size_t zone_uid_size);

/**
 * @brief Получение параметров MQTT из конфигурации
 * 
 * @param mqtt Указатель на структуру для заполнения
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t config_storage_get_mqtt(config_storage_mqtt_t *mqtt);

/**
 * @brief Получение параметров Wi-Fi из конфигурации
 * 
 * @param wifi Указатель на структуру для заполнения
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t config_storage_get_wifi(config_storage_wifi_t *wifi);

/**
 * @brief Валидация конфигурации
 * 
 * Проверяет наличие обязательных полей и корректность типов
 * 
 * @param json_config JSON строка с конфигурацией
 * @param json_len Длина JSON строки
 * @param error_msg Буфер для сообщения об ошибке (может быть NULL)
 * @param error_msg_size Размер буфера
 * @return esp_err_t ESP_OK если конфиг валиден
 */
esp_err_t config_storage_validate(const char *json_config, size_t json_len, 
                                  char *error_msg, size_t error_msg_size);

/**
 * @brief Сброс gh_uid/zone_uid в конфигурации к указанным значениям.
 *
 * Wi-Fi и MQTT параметры сохраняются.
 *
 * @param gh_uid Новый gh_uid
 * @param zone_uid Новый zone_uid
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t config_storage_reset_namespace(const char *gh_uid, const char *zone_uid);

/**
 * @brief Полный сброс конфигурации в NVS (включая сетевые параметры).
 *
 * Удаляются все ключи в namespace node_config.
 *
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t config_storage_factory_reset(void);

/**
 * @brief Деинициализация config_storage
 */
void config_storage_deinit(void);

#ifdef __cplusplus
}
#endif

#endif // CONFIG_STORAGE_H









