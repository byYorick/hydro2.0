#ifndef SETUP_PORTAL_H
#define SETUP_PORTAL_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef struct {
    char ssid[33];
    char password[65];
} setup_portal_credentials_t;

typedef void (*setup_portal_credentials_cb_t)(const setup_portal_credentials_t *credentials, void *user_ctx);

typedef struct {
    const char *ap_ssid;
    const char *ap_password;
    setup_portal_credentials_cb_t on_credentials;
    void *user_ctx;
} setup_portal_config_t;

/**
 * @brief Конфигурация для полного цикла настройки
 */
typedef struct {
    const char *node_type_prefix;  // Префикс для SSID (например, "PH", "EC")
    const char *ap_password;        // Пароль для AP (может быть NULL для открытой сети)
    bool enable_oled;               // Инициализировать OLED для отображения setup информации
    void *oled_user_ctx;            // Контекст для OLED (например, функция проверки инициализации)
} setup_portal_full_config_t;

/**
 * @brief Запуск базового setup portal (AP + HTTP сервер)
 * 
 * @param config Конфигурация portal
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t setup_portal_start(const setup_portal_config_t *config);

/**
 * @brief Остановка setup portal
 */
void setup_portal_stop(void);

/**
 * @brief Проверка, запущен ли setup portal
 * 
 * @return true если portal запущен
 */
bool setup_portal_is_running(void);

/**
 * @brief Генерация PIN кода на основе MAC адреса
 * 
 * @param pin_out Буфер для PIN кода (минимум 7 байт)
 * @param pin_size Размер буфера
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t setup_portal_generate_pin(char *pin_out, size_t pin_size);

/**
 * @brief Полный цикл настройки узла
 * 
 * Эта функция:
 * 1. Генерирует PIN на основе MAC адреса
 * 2. Создает AP с SSID вида "{PREFIX}_SETUP_{PIN}"
 * 3. Инициализирует OLED (если включено) и отображает setup информацию
 * 4. Запускает HTTP сервер для получения WiFi credentials
 * 5. Сохраняет credentials в config_storage
 * 6. Перезагружает устройство после успешной настройки
 * 
 * Функция блокирует выполнение до получения credentials или ошибки.
 * 
 * @param config Конфигурация полного цикла настройки
 * @return esp_err_t ESP_OK при успехе, ESP_FAIL при ошибке
 */
esp_err_t setup_portal_run_full_setup(const setup_portal_full_config_t *config);

#ifdef __cplusplus
}
#endif

#endif // SETUP_PORTAL_H

