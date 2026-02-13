/**
 * @file test_node_ui.h
 * @brief Локальный UI для test_node: ILI9341 + LVGL + энкодер
 */

#ifndef TEST_NODE_UI_H
#define TEST_NODE_UI_H

#include "esp_err.h"
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

typedef enum {
    TEST_NODE_UI_SETTINGS_ACTION_RESET_ZONES = 0,
    TEST_NODE_UI_SETTINGS_ACTION_FACTORY_RESET = 1,
} test_node_ui_settings_action_t;

typedef void (*test_node_ui_settings_action_cb_t)(test_node_ui_settings_action_t action, void *user_ctx);

/**
 * @brief Инициализация локального UI.
 *
 * @return ESP_OK при успехе
 */
esp_err_t test_node_ui_init(void);

/**
 * @brief Показать шаг инициализации на экране.
 *
 * Функция потокобезопасна. При выключенном UI вызов игнорируется.
 *
 * @param step Текст шага
 */
void test_node_ui_show_step(const char *step);

/**
 * @brief Добавить короткий лог в терминальное окно.
 *
 * @param node_uid UID ноды (или NULL для системного лога)
 * @param message Короткое сообщение
 */
void test_node_ui_log_event(const char *node_uid, const char *message);

/**
 * @brief Обновить статус Wi-Fi.
 *
 * @param connected true если подключено
 * @param status_text Короткий текст статуса (опционально)
 */
void test_node_ui_set_wifi_status(bool connected, const char *status_text);

/**
 * @brief Обновить статус MQTT.
 *
 * @param connected true если подключено
 * @param status_text Короткий текст статуса (опционально)
 */
void test_node_ui_set_mqtt_status(bool connected, const char *status_text);

/**
 * @brief Зарегистрировать виртуальную ноду для отображения.
 *
 * @param node_uid UID ноды
 * @param zone_uid Текущая зона
 */
void test_node_ui_register_node(const char *node_uid, const char *zone_uid);

/**
 * @brief Обновить зону ноды в UI.
 *
 * @param node_uid UID ноды
 * @param zone_uid UID зоны
 */
void test_node_ui_set_node_zone(const char *node_uid, const char *zone_uid);

/**
 * @brief Отметить heartbeat ноды (мигающий индикатор).
 *
 * @param node_uid UID ноды
 */
void test_node_ui_mark_node_heartbeat(const char *node_uid);

/**
 * @brief Отметить LWT/offline ноды (мигающий индикатор).
 *
 * @param node_uid UID ноды
 */
void test_node_ui_mark_node_lwt(const char *node_uid);

/**
 * @brief Обновить ONLINE/OFFLINE статус ноды.
 *
 * @param node_uid UID ноды
 * @param status Строка статуса
 */
void test_node_ui_set_node_status(const char *node_uid, const char *status);

/**
 * @brief Установить общий режим UI (BOOT/RUN/SETUP и т.д.).
 *
 * @param mode Короткая строка режима
 */
void test_node_ui_set_mode(const char *mode);

/**
 * @brief Обновить данные setup-портала для отображения на экране.
 *
 * @param ssid SSID setup AP
 * @param password_text Текст пароля (или маска)
 * @param pin PIN код
 */
void test_node_ui_set_setup_info(const char *ssid, const char *password_text, const char *pin);

/**
 * @brief Регистрация callback действий меню настроек.
 *
 * @param cb Callback (может быть NULL для отключения)
 * @param user_ctx Пользовательский контекст
 */
void test_node_ui_register_settings_action_cb(test_node_ui_settings_action_cb_t cb, void *user_ctx);

#ifdef __cplusplus
}
#endif

#endif // TEST_NODE_UI_H
