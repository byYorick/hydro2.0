/**
 * @file wifi_manager.c
 * @brief Реализация Wi-Fi менеджера
 * 
 * Базовая реализация подключения к Wi-Fi сети
 * Согласно WIFI_CONNECTIVITY_ENGINE.md
 */

#include "wifi_manager.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_event.h"
#include "freertos/FreeRTOS.h"
#include "freertos/event_groups.h"
#include <string.h>

static const char *TAG = "wifi_manager";

// Event group для Wi-Fi событий
#define WIFI_CONNECTED_BIT BIT0
#define WIFI_FAIL_BIT      BIT1

static EventGroupHandle_t s_wifi_event_group = NULL;
static wifi_connection_cb_t s_connection_cb = NULL;
static void *s_connection_user_ctx = NULL;
static bool s_is_connected = false;

/**
 * @brief Обработчик событий Wi-Fi
 */
static void wifi_event_handler(void* arg, esp_event_base_t event_base,
                              int32_t event_id, void* event_data) {
    if (event_base == WIFI_EVENT) {
        switch (event_id) {
            case WIFI_EVENT_STA_START:
                ESP_LOGI(TAG, "Wi-Fi station started");
                esp_wifi_connect();
                break;
                
            case WIFI_EVENT_STA_CONNECTED: {
                wifi_event_sta_connected_t* event = (wifi_event_sta_connected_t*) event_data;
                ESP_LOGI(TAG, "Connected to AP SSID:%s", event->ssid);
                break;
            }
            
            case WIFI_EVENT_STA_DISCONNECTED: {
                wifi_event_sta_disconnected_t* event = (wifi_event_sta_disconnected_t*) event_data;
                ESP_LOGW(TAG, "Disconnected from AP. Reason: %d", event->reason);
                s_is_connected = false;
                
                // Вызов callback отключения
                if (s_connection_cb) {
                    s_connection_cb(false, s_connection_user_ctx);
                }
                
                // Попытка переподключения
                esp_wifi_connect();
                xEventGroupClearBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
                break;
            }
            
            default:
                break;
        }
    } else if (event_base == IP_EVENT) {
        switch (event_id) {
            case IP_EVENT_STA_GOT_IP: {
                ip_event_got_ip_t* event = (ip_event_got_ip_t*) event_data;
                ESP_LOGI(TAG, "Got IP:" IPSTR, IP2STR(&event->ip_info.ip));
                s_is_connected = true;
                xEventGroupSetBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
                
                // Вызов callback подключения
                if (s_connection_cb) {
                    s_connection_cb(true, s_connection_user_ctx);
                }
                break;
            }
            
            case IP_EVENT_STA_LOST_IP:
                ESP_LOGW(TAG, "Lost IP address");
                s_is_connected = false;
                xEventGroupClearBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
                
                // Вызов callback отключения
                if (s_connection_cb) {
                    s_connection_cb(false, s_connection_user_ctx);
                }
                break;
                
            default:
                break;
        }
    }
}

esp_err_t wifi_manager_init(void) {
    if (s_wifi_event_group != NULL) {
        ESP_LOGW(TAG, "Wi-Fi manager already initialized");
        return ESP_OK;
    }
    
    s_wifi_event_group = xEventGroupCreate();
    if (s_wifi_event_group == NULL) {
        ESP_LOGE(TAG, "Failed to create event group");
        return ESP_ERR_NO_MEM;
    }
    
    // Регистрация обработчиков событий
    ESP_ERROR_CHECK(esp_event_handler_instance_register(WIFI_EVENT,
                                                        ESP_EVENT_ANY_ID,
                                                        &wifi_event_handler,
                                                        NULL,
                                                        NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
                                                        IP_EVENT_STA_GOT_IP,
                                                        &wifi_event_handler,
                                                        NULL,
                                                        NULL));
    ESP_ERROR_CHECK(esp_event_handler_instance_register(IP_EVENT,
                                                        IP_EVENT_STA_LOST_IP,
                                                        &wifi_event_handler,
                                                        NULL,
                                                        NULL));
    
    ESP_LOGI(TAG, "Wi-Fi manager initialized");
    return ESP_OK;
}

esp_err_t wifi_manager_connect(const wifi_manager_config_t *config) {
    if (config == NULL || config->ssid == NULL) {
        ESP_LOGE(TAG, "Invalid Wi-Fi config");
        return ESP_ERR_INVALID_ARG;
    }
    
    if (s_wifi_event_group == NULL) {
        ESP_LOGE(TAG, "Wi-Fi manager not initialized");
        return ESP_ERR_INVALID_STATE;
    }
    
    wifi_config_t wifi_config = {0};
    strncpy((char*)wifi_config.sta.ssid, config->ssid, sizeof(wifi_config.sta.ssid) - 1);
    if (config->password) {
        strncpy((char*)wifi_config.sta.password, config->password, sizeof(wifi_config.sta.password) - 1);
    }
    wifi_config.sta.threshold.authmode = WIFI_AUTH_WPA2_PSK;
    wifi_config.sta.pmf_cfg.capable = true;
    wifi_config.sta.pmf_cfg.required = false;
    
    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_STA, &wifi_config));
    
    ESP_LOGI(TAG, "Connecting to Wi-Fi SSID: %s", config->ssid);
    esp_wifi_connect();
    
    // Ожидание подключения (таймаут 30 секунд)
    EventBits_t bits = xEventGroupWaitBits(s_wifi_event_group,
                                          WIFI_CONNECTED_BIT | WIFI_FAIL_BIT,
                                          pdFALSE,
                                          pdFALSE,
                                          pdMS_TO_TICKS(30000));
    
    if (bits & WIFI_CONNECTED_BIT) {
        ESP_LOGI(TAG, "Connected to Wi-Fi successfully");
        return ESP_OK;
    } else if (bits & WIFI_FAIL_BIT) {
        ESP_LOGE(TAG, "Failed to connect to Wi-Fi");
        return ESP_FAIL;
    } else {
        ESP_LOGE(TAG, "Wi-Fi connection timeout");
        return ESP_ERR_TIMEOUT;
    }
}

esp_err_t wifi_manager_disconnect(void) {
    if (s_wifi_event_group == NULL) {
        return ESP_ERR_INVALID_STATE;
    }
    
    esp_wifi_disconnect();
    s_is_connected = false;
    xEventGroupClearBits(s_wifi_event_group, WIFI_CONNECTED_BIT);
    
    ESP_LOGI(TAG, "Disconnected from Wi-Fi");
    return ESP_OK;
}

bool wifi_manager_is_connected(void) {
    return s_is_connected;
}

esp_err_t wifi_manager_get_rssi(int8_t *rssi) {
    if (rssi == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    
    if (!s_is_connected) {
        *rssi = -100;
        return ESP_ERR_INVALID_STATE;
    }
    
    wifi_ap_record_t ap_info;
    esp_err_t err = esp_wifi_sta_get_ap_info(&ap_info);
    if (err == ESP_OK) {
        *rssi = ap_info.rssi;
    } else {
        *rssi = -100;
    }
    
    return err;
}

void wifi_manager_register_connection_cb(wifi_connection_cb_t cb, void *user_ctx) {
    s_connection_cb = cb;
    s_connection_user_ctx = user_ctx;
}

void wifi_manager_deinit(void) {
    if (s_wifi_event_group != NULL) {
        vEventGroupDelete(s_wifi_event_group);
        s_wifi_event_group = NULL;
    }
    s_connection_cb = NULL;
    s_connection_user_ctx = NULL;
    s_is_connected = false;
}








