/**
 * @file oled_ui.h
 * @brief Драйвер OLED дисплея для локального UI узлов ESP32
 * 
 * Компонент реализует локальный UI на OLED дисплее 128x64 (SSD1306/SSD1309):
 * - Драйвер для SSD1306/SSD1309 через I²C
 * - Система экранов (screens) с переключением
 * - Отображение статуса ноды (Wi-Fi, MQTT, значения сенсоров, ошибки)
 * - Интеграция с NodeConfig
 * - Отдельная FreeRTOS задача для обновления дисплея
 * 
 * Согласно:
 * - doc_ai/02_HARDWARE_FIRMWARE/NODE_OLED_UI_SPEC.md
 * - doc_ai/02_HARDWARE_FIRMWARE/ESP32_C_CODING_STANDARDS.md
 */

#ifndef OLED_UI_H
#define OLED_UI_H

#include "esp_err.h"
#include <stdint.h>
#include <stdbool.h>

#ifdef __cplusplus
extern "C" {
#endif

/**
 * @brief Тип узла для отображения
 */
typedef enum {
    OLED_UI_NODE_TYPE_PH,
    OLED_UI_NODE_TYPE_EC,
    OLED_UI_NODE_TYPE_CLIMATE,
    OLED_UI_NODE_TYPE_PUMP,
    OLED_UI_NODE_TYPE_LIGHTING,
    OLED_UI_NODE_TYPE_UNKNOWN
} oled_ui_node_type_t;

/**
 * @brief Состояние UI
 */
typedef enum {
    OLED_UI_STATE_BOOT,
    OLED_UI_STATE_WIFI_SETUP,
    OLED_UI_STATE_NORMAL,
    OLED_UI_STATE_ALERT,
    OLED_UI_STATE_CALIBRATION,
    OLED_UI_STATE_SERVICE
} oled_ui_state_t;

/**
 * @brief Статус соединений
 */
typedef struct {
    bool wifi_connected;
    bool mqtt_connected;
    int8_t wifi_rssi;
} oled_ui_connection_status_t;

/**
 * @brief Модель данных для UI
 */
typedef struct {
    // Статус соединений
    oled_ui_connection_status_t connections;
    
    // Значения сенсоров (зависит от типа узла)
    float ph_value;           // Для pH узла
    float ec_value;           // Для EC узла
    float temperature_air;    // Для climate узла
    float temperature_water;  // Для pH/EC узлов
    float humidity;           // Для climate узла
    float co2;                // Для climate узла (опционально)
    
    // Статус узла
    bool alert;
    bool paused;
    char alert_message[32];   // Краткое сообщение об ошибке
    
    // Информация о зоне/рецепте
    char zone_name[32];
    char recipe_name[32];
    
    // Каналы (для отображения на экране каналов)
    struct {
        char name[16];
        float value;
        bool active;
    } channels[8];
    size_t channel_count;
} oled_ui_model_t;

/**
 * @brief Конфигурация OLED UI
 */
typedef struct {
    uint8_t i2c_address;      // I²C адрес дисплея (обычно 0x3C или 0x3D)
    uint32_t update_interval_ms; // Интервал обновления дисплея в мс
    bool enable_task;         // Создавать отдельную задачу для обновления
} oled_ui_config_t;

/**
 * @brief Инициализация OLED UI
 * 
 * @param node_type Тип узла
 * @param node_uid UID узла (для отображения)
 * @param config Конфигурация (может быть NULL для значений по умолчанию)
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t oled_ui_init(oled_ui_node_type_t node_type, const char *node_uid, 
                      const oled_ui_config_t *config);

/**
 * @brief Деинициализация OLED UI
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t oled_ui_deinit(void);

/**
 * @brief Установка состояния UI
 * 
 * @param state Новое состояние
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t oled_ui_set_state(oled_ui_state_t state);

/**
 * @brief Получение текущего состояния UI
 * 
 * @return oled_ui_state_t Текущее состояние
 */
oled_ui_state_t oled_ui_get_state(void);

/**
 * @brief Обновление модели данных UI
 * 
 * @param model Указатель на модель данных
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t oled_ui_update_model(const oled_ui_model_t *model);

/**
 * @brief Принудительное обновление дисплея
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t oled_ui_refresh(void);

/**
 * @brief Уведомление о MQTT активности (отправка сообщения)
 * 
 * Вызывается при отправке MQTT сообщения для мигания индикатора
 */
void oled_ui_notify_mqtt_tx(void);

/**
 * @brief Уведомление о MQTT активности (прием сообщения)
 * 
 * Вызывается при приеме MQTT сообщения для мигания индикатора
 */
void oled_ui_notify_mqtt_rx(void);

/**
 * @brief Переключение на следующий экран (для режима NORMAL)
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t oled_ui_next_screen(void);

/**
 * @brief Переключение на предыдущий экран (для режима NORMAL)
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t oled_ui_prev_screen(void);

/**
 * @brief Обработка события энкодера (вращение)
 * 
 * @param direction Направление: 1 = вперед, -1 = назад
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t oled_ui_handle_encoder(int direction);

/**
 * @brief Обработка события кнопки (нажатие)
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t oled_ui_handle_button(void);

/**
 * @brief Запуск задачи обновления дисплея
 * 
 * Создает отдельную FreeRTOS задачу для периодического обновления дисплея
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t oled_ui_start_task(void);

/**
 * @brief Остановка задачи обновления дисплея
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t oled_ui_stop_task(void);

/**
 * @brief Проверка инициализации OLED UI
 * 
 * @return true если OLED UI инициализирован
 */
bool oled_ui_is_initialized(void);

/**
 * @brief Отображение шага инициализации на экране BOOT
 * 
 * Показывает шаг инициализации с анимацией точек (каждые 500ms)
 * Формат: "pH NODE INIT"
 *         "Step {step_num}/8"
 *         "{step_text}"
 *         "{dots}" (анимация: "", ".", "..", "...")
 * 
 * @param step_num Номер шага (1-8)
 * @param step_text Текст шага (например, "I2C init", "pH Sensor init")
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t oled_ui_show_init_step(int step_num, const char *step_text);

/**
 * @brief Остановка анимации шагов инициализации
 * 
 * Останавливает анимацию точек и переходит к нормальному режиму
 * 
 * @return esp_err_t ESP_OK при успехе
 */
esp_err_t oled_ui_stop_init_steps(void);

#ifdef __cplusplus
}
#endif

#endif // OLED_UI_H

