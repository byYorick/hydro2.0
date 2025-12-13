# Руководство по управлению WS2811/WS2812 на ESP32

## Обзор

WS2811 и WS2812 - это адресные RGB светодиодные ленты, которые используют протокол OneWire для управления. Каждый светодиод имеет свой адрес и может управляться независимо.

## Технические характеристики

- **Протокол**: OneWire (специальный протокол с таймингами)
- **Напряжение питания**: 5V (WS2812) или 12V (WS2811)
- **Ток потребления**: ~60mA на светодиод при максимальной яркости
- **Частота данных**: ~800kHz
- **Количество светодиодов**: до 1024 на одну линию (ограничение ESP32)

## Методы управления на ESP32

### 1. RMT (Remote Control) - Рекомендуемый метод

RMT - это встроенный периферийный модуль ESP32, специально разработанный для работы с протоколами типа OneWire.

**Преимущества:**
- Низкая нагрузка на CPU
- Точные тайминги
- Поддержка DMA
- Не требует дополнительных библиотек

**Недостатки:**
- Ограниченное количество каналов (8 на ESP32)
- Требует настройки таймингов

### 2. SPI DMA

Использование SPI с DMA для эмуляции протокола WS2811.

**Преимущества:**
- Высокая скорость передачи
- Много каналов (зависит от доступных SPI интерфейсов)

**Недостатки:**
- Более сложная настройка
- Требует больше памяти

## Реализация драйвера WS2811

### Структура компонента

```
firmware/nodes/common/components/ws2811_driver/
├── ws2811_driver.c
├── ws2811_driver.h
└── README.md
```

### Основные функции

```c
// Инициализация драйвера
esp_err_t ws2811_driver_init(uint8_t gpio_pin, uint16_t led_count);

// Установка цвета одного светодиода
esp_err_t ws2811_driver_set_pixel(uint16_t index, uint8_t r, uint8_t g, uint8_t b);

// Установка цвета всех светодиодов
esp_err_t ws2811_driver_set_all(uint8_t r, uint8_t g, uint8_t b);

// Обновление ленты (отправка данных)
esp_err_t ws2811_driver_update(void);

// Очистка (выключение всех светодиодов)
esp_err_t ws2811_driver_clear(void);

// Установка яркости (0-255)
esp_err_t ws2811_driver_set_brightness(uint8_t brightness);
```

### Пример использования

```c
#include "ws2811_driver.h"

void app_main(void) {
    // Инициализация: GPIO 18, 60 светодиодов
    esp_err_t err = ws2811_driver_init(18, 60);
    if (err != ESP_OK) {
        ESP_LOGE("APP", "Failed to initialize WS2811 driver");
        return;
    }
    
    // Установка красного цвета для первого светодиода
    ws2811_driver_set_pixel(0, 255, 0, 0);
    
    // Установка зеленого цвета для второго светодиода
    ws2811_driver_set_pixel(1, 0, 255, 0);
    
    // Установка синего цвета для третьего светодиода
    ws2811_driver_set_pixel(2, 0, 0, 255);
    
    // Отправка данных на ленту
    ws2811_driver_update();
    
    // Очистка через 5 секунд
    vTaskDelay(pdMS_TO_TICKS(5000));
    ws2811_driver_clear();
    ws2811_driver_update();
}
```

## Интеграция с Node Framework

### Добавление в NodeConfig

```json
{
  "node_id": "nd-light-1",
  "channels": [
    {
      "name": "led_strip_1",
      "type": "ws2811",
      "gpio": 18,
      "led_count": 60,
      "brightness": 128
    }
  ]
}
```

### Обработка команд через MQTT

```c
// В node_framework_integration.c
static esp_err_t handle_led_strip_command(cJSON *command) {
    cJSON *channel = cJSON_GetObjectItem(command, "channel");
    cJSON *action = cJSON_GetObjectItem(command, "action");
    cJSON *params = cJSON_GetObjectItem(command, "params");
    
    if (!channel || !action) {
        return ESP_ERR_INVALID_ARG;
    }
    
    const char *channel_name = cJSON_GetStringValue(channel);
    const char *action_str = cJSON_GetStringValue(action);
    
    if (strcmp(action_str, "set_color") == 0) {
        cJSON *r = cJSON_GetObjectItem(params, "r");
        cJSON *g = cJSON_GetObjectItem(params, "g");
        cJSON *b = cJSON_GetObjectItem(params, "b");
        cJSON *index = cJSON_GetObjectItem(params, "index");
        
        if (index) {
            // Установка цвета одного светодиода
            ws2811_driver_set_pixel(
                cJSON_GetNumberValue(index),
                cJSON_GetNumberValue(r),
                cJSON_GetNumberValue(g),
                cJSON_GetNumberValue(b)
            );
        } else {
            // Установка цвета всех светодиодов
            ws2811_driver_set_all(
                cJSON_GetNumberValue(r),
                cJSON_GetNumberValue(g),
                cJSON_GetNumberValue(b)
            );
        }
        ws2811_driver_update();
    } else if (strcmp(action_str, "clear") == 0) {
        ws2811_driver_clear();
        ws2811_driver_update();
    }
    
    return ESP_OK;
}
```

### Пример MQTT команды

```json
{
  "message_type": "node_command",
  "node_id": "nd-light-1",
  "command": {
    "channel": "led_strip_1",
    "action": "set_color",
    "params": {
      "r": 255,
      "g": 0,
      "b": 0,
      "index": 0
    }
  }
}
```

## Тайминги протокола WS2811

Для правильной работы необходимо соблюдать точные тайминги:

- **Bit 0 (низкий уровень)**:
  - Высокий уровень: 0.3µs ± 0.15µs
  - Низкий уровень: 0.9µs ± 0.15µs

- **Bit 1 (высокий уровень)**:
  - Высокий уровень: 0.6µs ± 0.15µs
  - Низкий уровень: 0.6µs ± 0.15µs

- **Reset (сброс)**:
  - Низкий уровень: минимум 50µs

## Электрические требования

### Питание

- **WS2812**: 5V, до 60mA на светодиод
- **WS2811**: 12V, до 60mA на светодиод
- Для 60 светодиодов при максимальной яркости: ~3.6A при 5V

**Важно**: Используйте внешний источник питания для лент длиннее 10-15 светодиодов!

### Подключение

```
ESP32 GPIO (3.3V) → WS2811 Data In
5V/12V Power Supply → WS2811 VCC
GND → WS2811 GND (общий с ESP32)
```

**Рекомендация**: Используйте логический преобразователь уровня (level shifter) для надежной работы, особенно при длинных проводах.

## Оптимизация производительности

### Буферизация

Для плавных анимаций используйте двойную буферизацию:

```c
typedef struct {
    uint8_t r[LED_COUNT];
    uint8_t g[LED_COUNT];
    uint8_t b[LED_COUNT];
} led_buffer_t;

static led_buffer_t s_buffer[2];
static uint8_t s_active_buffer = 0;

void prepare_animation_frame(void) {
    uint8_t inactive = 1 - s_active_buffer;
    // Подготовка кадра в неактивном буфере
    // ...
    s_active_buffer = inactive;
    // Обновление ленты из активного буфера
}
```

### FreeRTOS задача для анимаций

```c
void led_animation_task(void *pvParameters) {
    while (1) {
        // Обновление анимации
        update_animation();
        
        // Отправка на ленту
        ws2811_driver_update();
        
        // Задержка для FPS (например, 30 FPS = 33ms)
        vTaskDelay(pdMS_TO_TICKS(33));
    }
}
```

## Отладка

### Проблемы с таймингами

Если светодиоды показывают неправильные цвета:
1. Проверьте частоту CPU (должна быть 240MHz)
2. Убедитесь, что нет прерываний во время передачи
3. Проверьте длину проводов (не более 1-2 метров без буфера)

### Проблемы с питанием

Если светодиоды мигают или гаснут:
1. Проверьте достаточность тока источника питания
2. Добавьте конденсатор 1000µF на вход питания ленты
3. Используйте отдельный источник питания для ленты

## Дополнительные ресурсы

- [ESP-IDF RMT Driver Documentation](https://docs.espressif.com/projects/esp-idf/en/latest/esp32/api-reference/peripherals/rmt.html)
- [WS2812 Datasheet](https://cdn-shop.adafruit.com/datasheets/WS2812.pdf)
- [FastLED Library](https://github.com/FastLED/FastLED) - альтернативная библиотека для Arduino

