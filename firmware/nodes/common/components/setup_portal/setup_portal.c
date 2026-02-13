#include "setup_portal.h"
#include "config_storage.h"
#include "oled_ui.h"
#include "i2c_bus.h"
#include "esp_log.h"
#include "esp_wifi.h"
#include "esp_netif.h"
#include "esp_event.h"
#include "esp_mac.h"
#include "esp_system.h"
#include "nvs_flash.h"
#include "esp_http_server.h"
#include "node_utils.h"
#include "freertos/FreeRTOS.h"
#include "freertos/task.h"
#include "freertos/semphr.h"
#include "cJSON.h"
#include <string.h>
#include <stdlib.h>
#include <stdio.h>

static const char *TAG = "setup_portal";

static httpd_handle_t s_http_server = NULL;
static setup_portal_config_t s_config = {0};
static bool s_running = false;
static bool s_netif_initialized = false;
static esp_netif_t *s_ap_netif = NULL;
static SemaphoreHandle_t s_full_setup_sem = NULL;

static const char *map_node_type_from_prefix(const char *prefix) {
    if (!prefix) {
        return "unknown";
    }
    if (strcmp(prefix, "PH") == 0) {
        return "ph";
    }
    if (strcmp(prefix, "EC") == 0) {
        return "ec";
    }
    if (strcmp(prefix, "CLIMATE") == 0) {
        return "climate";
    }
    if (strcmp(prefix, "PUMP") == 0) {
        return "pump";
    }
    if (strcmp(prefix, "RELAY") == 0) {
        return "relay";
    }
    if (strcmp(prefix, "LIGHT") == 0) {
        return "light";
    }
    return "unknown";
}

static const char *HTML_PAGE = "<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1'>" \
    "<title>Hydro Setup</title><style>body{font-family:Arial;margin:0;background:#0f172a;color:#e2e8f0;}" \
    ".container{max-width:420px;margin:4rem auto;background:#1f2937;padding:2rem;border-radius:16px;box-shadow:0 22px 45px rgba(15,23,42,0.45);}h1{text-align:center;}" \
    "label{display:block;margin-top:1rem;font-size:0.9rem;color:#94a3b8;text-transform:uppercase;}" \
    "input{width:100%;padding:0.75rem;margin-top:0.5rem;border-radius:10px;border:1px solid #334155;background:#0f172a;color:#f8fafc;}" \
    "input:invalid{border-color:#ef4444;}" \
    "button{margin-top:1.5rem;width:100%;padding:0.9rem;border:none;border-radius:12px;background:#38bdf8;color:#0f172a;font-weight:600;font-size:1rem;cursor:pointer;}" \
    "button:disabled{background:#1e40af;color:#94a3b8;cursor:not-allowed;}" \
    ".status{margin-top:1.5rem;line-height:1.6;} .status-success{color:#22c55e;} .status-error{color:#ef4444;}</style></head><body>" \
    "<div class='container'><h1>🌱 Hydro Setup</h1><p>Введите данные вашего WiFi и MQTT, чтобы нода подключилась к сети.</p>" \
    "<form id='wifiForm'><label>WiFi SSID<input name='ssid' placeholder='MyHomeWiFi' required></label>" \
    "<label>WiFi Пароль<input name='password' type='password' placeholder='Пароль' required></label>" \
    "<label>MQTT Хост<input name='mqtt_host' type='text' placeholder='192.168.1.4' pattern='^([0-9]{1,3}\\.){3}[0-9]{1,3}$' required></label>" \
    "<label>MQTT Порт<input name='mqtt_port' type='number' placeholder='1883' min='1' max='65535' required></label>" \
    "<button type='submit' id='submitBtn'>Подключить</button><div class='status' id='statusMsg'></div></form></div>" \
    "<script>(function(){const form=document.getElementById('wifiForm');const statusEl=document.getElementById('statusMsg');const btn=document.getElementById('submitBtn');" \
    "function validateIP(ip){const parts=ip.split('.');if(parts.length!==4)return false;for(let i=0;i<4;i++){const num=parseInt(parts[i],10);if(isNaN(num)||num<0||num>255)return false;}return true;}" \
    "form.addEventListener('submit',function(e){e.preventDefault();const mqttHost=form.mqtt_host.value.trim();const mqttPort=parseInt(form.mqtt_port.value,10);" \
    "if(!validateIP(mqttHost)){statusEl.innerHTML='<span class=\\'status-error\\'>Неверный формат IP-адреса. Используйте формат xxx.xxx.xxx.xxx</span>';return;}" \
    "if(isNaN(mqttPort)||mqttPort<1||mqttPort>65535){statusEl.innerHTML='<span class=\\'status-error\\'>Порт должен быть числом от 1 до 65535</span>';return;}" \
    "btn.disabled=true;statusEl.textContent='Отправка...';" \
    "const payload=JSON.stringify({ssid:form.ssid.value,password:form.password.value,mqtt_host:mqttHost,mqtt_port:mqttPort});" \
    "fetch('/wifi/connect',{method:'POST',headers:{'Content-Type':'application/json'},body:payload}).then(function(resp){" \
    "if(resp.ok){statusEl.innerHTML='<span class=\\'status-success\\'>✓ Данные получены. Устройство перезапустится автоматически.</span>';return null;}" \
    "return resp.json().then(function(body){throw new Error(body.message||resp.statusText||'Ошибка');});}).catch(function(err){" \
    "statusEl.innerHTML='<span class=\\'status-error\\'>'+err.message+'</span>';btn.disabled=false;});});})();</script></body></html>";

static esp_err_t ensure_netif_initialized(void) {
    if (s_netif_initialized) {
        return ESP_OK;
    }

    esp_err_t err = esp_netif_init();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        return err;
    }

    err = esp_event_loop_create_default();
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        return err;
    }

    s_ap_netif = esp_netif_create_default_wifi_ap();
    if (s_ap_netif == NULL) {
        ESP_LOGE(TAG, "Failed to create default WiFi AP interface");
        return ESP_FAIL;
    }

    s_netif_initialized = true;
    return ESP_OK;
}

static esp_err_t start_softap(const char *ssid, const char *password) {
    wifi_init_config_t cfg = WIFI_INIT_CONFIG_DEFAULT();
    ESP_ERROR_CHECK(esp_wifi_init(&cfg));
    ESP_ERROR_CHECK(esp_wifi_set_mode(WIFI_MODE_AP));

    wifi_config_t wifi_config = {0};
    strncpy((char *)wifi_config.ap.ssid, ssid, sizeof(wifi_config.ap.ssid) - 1);
    wifi_config.ap.ssid_len = strlen(ssid);
    strncpy((char *)wifi_config.ap.password, password, sizeof(wifi_config.ap.password) - 1);
    wifi_config.ap.channel = 6;
    wifi_config.ap.max_connection = 4;
    wifi_config.ap.beacon_interval = 100;
    wifi_config.ap.authmode = (strlen(password) > 0) ? WIFI_AUTH_WPA_WPA2_PSK : WIFI_AUTH_OPEN;
    wifi_config.ap.ssid_hidden = 0;

    ESP_ERROR_CHECK(esp_wifi_set_config(WIFI_IF_AP, &wifi_config));
    ESP_ERROR_CHECK(esp_wifi_start());

    ESP_LOGI(TAG, "SoftAP запущен: SSID='%s'", ssid);
    return ESP_OK;
}

static esp_err_t stop_softap(void) {
    if (!s_netif_initialized) {
        return ESP_OK;
    }
    esp_wifi_stop();
    esp_wifi_deinit();
    if (s_ap_netif) {
        esp_netif_destroy(s_ap_netif);
        s_ap_netif = NULL;
    }
    s_netif_initialized = false;
    return ESP_OK;
}

/**
 * @brief Валидация IP-адреса в формате xxx.xxx.xxx.xxx
 * 
 * @param ip_str Строка с IP-адресом
 * @return true если IP-адрес валиден, false иначе
 */
static bool validate_ip_address(const char *ip_str) {
    if (!ip_str || strlen(ip_str) == 0) {
        return false;
    }
    
    int octets[4];
    int count = sscanf(ip_str, "%d.%d.%d.%d", &octets[0], &octets[1], &octets[2], &octets[3]);
    
    if (count != 4) {
        return false;
    }
    
    // Проверка каждого октета на диапазон 0-255
    for (int i = 0; i < 4; i++) {
        if (octets[i] < 0 || octets[i] > 255) {
            return false;
        }
    }
    
    // Проверка, что строка не содержит лишних символов после последнего октета
    char test_str[128];
    snprintf(test_str, sizeof(test_str), "%d.%d.%d.%d", octets[0], octets[1], octets[2], octets[3]);
    if (strcmp(ip_str, test_str) != 0) {
        return false;
    }
    
    return true;
}

static esp_err_t wifi_get_handler(httpd_req_t *req) {
    httpd_resp_set_type(req, "text/html");
    httpd_resp_set_hdr(req, "Cache-Control", "no-store");
    httpd_resp_send(req, HTML_PAGE, HTTPD_RESP_USE_STRLEN);
    return ESP_OK;
}

static esp_err_t wifi_post_handler(httpd_req_t *req) {
    int total = req->content_len;
    if (total <= 0 || total > 512) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid payload");
        return ESP_FAIL;
    }

    ESP_LOGI(TAG, "Получен POST /wifi/connect (len=%d)", total);

    char *buf = calloc(1, total + 1);
    if (!buf) {
        httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "No memory");
        return ESP_FAIL;
    }

    int received = 0;
    while (received < total) {
        int r = httpd_req_recv(req, buf + received, total - received);
        if (r <= 0) {
            free(buf);
            httpd_resp_send_err(req, HTTPD_500_INTERNAL_SERVER_ERROR, "Receive failed");
            return ESP_FAIL;
        }
        received += r;
    }

    cJSON *root = cJSON_Parse(buf);
    free(buf);
    if (!root) {
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid JSON");
        return ESP_FAIL;
    }

    const cJSON *ssid = cJSON_GetObjectItem(root, "ssid");
    const cJSON *password = cJSON_GetObjectItem(root, "password");
    const cJSON *mqtt_host = cJSON_GetObjectItem(root, "mqtt_host");
    const cJSON *mqtt_port = cJSON_GetObjectItem(root, "mqtt_port");
    
    // Валидация обязательных полей
    if (!cJSON_IsString(ssid) || !cJSON_IsString(password) || 
        !cJSON_IsString(mqtt_host) || !cJSON_IsNumber(mqtt_port)) {
        cJSON_Delete(root);
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing required fields: ssid, password, mqtt_host, mqtt_port");
        return ESP_FAIL;
    }
    
    // Валидация IP-адреса
    if (!validate_ip_address(mqtt_host->valuestring)) {
        cJSON_Delete(root);
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid MQTT host format. Expected xxx.xxx.xxx.xxx");
        return ESP_FAIL;
    }
    
    // Валидация порта
    int port_value = (int)cJSON_GetNumberValue(mqtt_port);
    if (port_value < 1 || port_value > 65535) {
        cJSON_Delete(root);
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Invalid MQTT port. Must be between 1 and 65535");
        return ESP_FAIL;
    }
    
    // Проверка максимальной длины хоста
    if (strlen(mqtt_host->valuestring) >= CONFIG_STORAGE_MAX_STRING_LEN) {
        cJSON_Delete(root);
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "MQTT host too long");
        return ESP_FAIL;
    }

    setup_portal_credentials_t creds = {0};
    strncpy(creds.ssid, ssid->valuestring, sizeof(creds.ssid) - 1);
    creds.ssid[sizeof(creds.ssid) - 1] = '\0';  // Гарантируем null-termination
    strncpy(creds.password, password->valuestring, sizeof(creds.password) - 1);
    creds.password[sizeof(creds.password) - 1] = '\0';  // Гарантируем null-termination
    strncpy(creds.mqtt_host, mqtt_host->valuestring, sizeof(creds.mqtt_host) - 1);
    creds.mqtt_host[sizeof(creds.mqtt_host) - 1] = '\0';  // Гарантируем null-termination
    creds.mqtt_port = (uint16_t)port_value;
    
    ESP_LOGI(TAG, "Данные WiFi: SSID='%s', пароль (%d символов)", creds.ssid, (int)strlen(creds.password));
    ESP_LOGI(TAG, "Данные MQTT: хост='%s', порт=%d", creds.mqtt_host, creds.mqtt_port);
    cJSON_Delete(root);

    if (s_config.on_credentials) {
        s_config.on_credentials(&creds, s_config.user_ctx);
    }

    httpd_resp_set_type(req, "application/json");
    httpd_resp_sendstr(req, "{\"success\":true}");
    return ESP_OK;
}

static httpd_handle_t start_http_server(void) {
    httpd_config_t config = HTTPD_DEFAULT_CONFIG();
    config.server_port = 80;
    config.stack_size = 8192;

    if (httpd_start(&s_http_server, &config) != ESP_OK) {
        ESP_LOGE(TAG, "Не удалось запустить HTTP сервер");
        return NULL;
    }

    httpd_uri_t root_get = {
        .uri = "/",
        .method = HTTP_GET,
        .handler = wifi_get_handler,
        .user_ctx = NULL,
    };
    httpd_uri_t wifi_post = {
        .uri = "/wifi/connect",
        .method = HTTP_POST,
        .handler = wifi_post_handler,
        .user_ctx = NULL,
    };

    httpd_register_uri_handler(s_http_server, &root_get);
    httpd_register_uri_handler(s_http_server, &wifi_post);

    ESP_LOGI(TAG, "HTTP Setup портал запущен");
    return s_http_server;
}

esp_err_t setup_portal_start(const setup_portal_config_t *config) {
    if (config == NULL || config->ap_ssid == NULL || config->on_credentials == NULL) {
        return ESP_ERR_INVALID_ARG;
    }
    if (s_running) {
        return ESP_ERR_INVALID_STATE;
    }

    ESP_ERROR_CHECK(nvs_flash_init());
    ESP_ERROR_CHECK(ensure_netif_initialized());

    memset(&s_config, 0, sizeof(s_config));
    s_config.on_credentials = config->on_credentials;
    s_config.user_ctx = config->user_ctx;
    s_config.ap_ssid = config->ap_ssid;
    s_config.ap_password = config->ap_password;

    ESP_ERROR_CHECK(start_softap(config->ap_ssid, config->ap_password ? config->ap_password : ""));
    if (!start_http_server()) {
        stop_softap();
        return ESP_FAIL;
    }

    s_running = true;
    return ESP_OK;
}

void setup_portal_stop(void) {
    if (!s_running) {
        return;
    }

    if (s_http_server) {
        httpd_stop(s_http_server);
        s_http_server = NULL;
    }

    stop_softap();
    s_running = false;
    ESP_LOGI(TAG, "Setup портал остановлен");
}

bool setup_portal_is_running(void) {
    return s_running;
}

esp_err_t setup_portal_generate_pin(char *pin_out, size_t pin_size) {
    if (!pin_out || pin_size < 7) {
        return ESP_ERR_INVALID_ARG;
    }
    
    uint8_t mac[6] = {0};
    esp_err_t err = esp_efuse_mac_get_default(mac);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to get MAC address: %s", esp_err_to_name(err));
        return err;
    }
    
    // Generate 6-digit PIN based on MAC address
    uint32_t pin_value = (mac[3] << 16) | (mac[4] << 8) | mac[5];
    pin_value = pin_value % 1000000; // Limit to 6 digits
    
    snprintf(pin_out, pin_size, "%06lu", (unsigned long)pin_value);
    return ESP_OK;
}

// Forward declaration
static void credentials_callback_wrapper(const setup_portal_credentials_t *creds, void *ctx);

// Internal callback for saving credentials to config_storage
static void save_credentials_to_config_storage(const setup_portal_credentials_t *credentials, const char *node_type_prefix) {
    if (!credentials) {
        return;
    }
    
    ESP_LOGI(TAG, "Saving WiFi and MQTT credentials to config_storage: SSID='%s', MQTT host='%s', port=%d", 
             credentials->ssid, credentials->mqtt_host, credentials->mqtt_port);
    
    // КРИТИЧНО: Проверяем, что SSID не пустой
    // ssid - это массив, поэтому проверяем только длину
    if (strlen(credentials->ssid) == 0) {
        ESP_LOGE(TAG, "Cannot save config: SSID is empty");
        return;
    }
    
    // Prepare WiFi config
    config_storage_wifi_t wifi_cfg = {0};
    strncpy(wifi_cfg.ssid, credentials->ssid, sizeof(wifi_cfg.ssid) - 1);
    wifi_cfg.ssid[sizeof(wifi_cfg.ssid) - 1] = '\0';  // Гарантируем null-termination
    strncpy(wifi_cfg.password, credentials->password, sizeof(wifi_cfg.password) - 1);
    wifi_cfg.password[sizeof(wifi_cfg.password) - 1] = '\0';  // Гарантируем null-termination
    wifi_cfg.auto_reconnect = true;
    wifi_cfg.timeout_sec = 30;
    
    // Дополнительная проверка после копирования
    if (strlen(wifi_cfg.ssid) == 0) {
        ESP_LOGE(TAG, "Cannot save config: SSID is empty after copy");
        return;
    }
    
    // hardware_id для первичной идентификации
    char hardware_id[32] = {0};
    bool has_hw_id = (node_utils_get_hardware_id(hardware_id, sizeof(hardware_id)) == ESP_OK);

    // Load current config, update WiFi and MQTT, then save
    // КРИТИЧНО: Используем статический буфер вместо стека для предотвращения переполнения
    static char json_buf[CONFIG_STORAGE_MAX_JSON_SIZE];
    const char *node_type = map_node_type_from_prefix(node_type_prefix);

    if (config_storage_get_json(json_buf, sizeof(json_buf)) == ESP_OK) {
        // Update existing config
        cJSON *config = cJSON_Parse(json_buf);
        if (config) {
            // Обновляем node_id, если он пустой или временный
            if (has_hw_id) {
                cJSON *node_id_item = cJSON_GetObjectItem(config, "node_id");
                if (!cJSON_IsString(node_id_item) || node_id_item->valuestring == NULL ||
                    strlen(node_id_item->valuestring) == 0 ||
                    strcmp(node_id_item->valuestring, "node-temp") == 0) {
                    cJSON_DeleteItemFromObject(config, "node_id");
                    cJSON_AddStringToObject(config, "node_id", hardware_id);
                    ESP_LOGI(TAG, "Updated node_id to hardware_id: %s", hardware_id);
                }
            }

            // Обновляем type, если отсутствует или unknown
            cJSON *type_item = cJSON_GetObjectItem(config, "type");
            if (!cJSON_IsString(type_item) || !type_item->valuestring || strlen(type_item->valuestring) == 0 ||
                strcmp(type_item->valuestring, "unknown") == 0) {
                cJSON_DeleteItemFromObject(config, "type");
                cJSON_AddStringToObject(config, "type", node_type);
                ESP_LOGI(TAG, "Updated node type in config: %s", node_type);
            }

            // Update WiFi configuration
            cJSON *wifi_obj = cJSON_GetObjectItem(config, "wifi");
            if (!wifi_obj) {
                wifi_obj = cJSON_CreateObject();
                cJSON_AddItemToObject(config, "wifi", wifi_obj);
            }
            cJSON_DeleteItemFromObject(wifi_obj, "ssid");
            cJSON_DeleteItemFromObject(wifi_obj, "pass");
            
            // КРИТИЧНО: Проверяем SSID перед добавлением
            if (strlen(wifi_cfg.ssid) == 0) {
                ESP_LOGE(TAG, "CRITICAL: SSID is empty before updating WiFi config");
                cJSON_Delete(config);
                return;
            }
            
            cJSON_AddStringToObject(wifi_obj, "ssid", wifi_cfg.ssid);
            cJSON_AddStringToObject(wifi_obj, "pass", wifi_cfg.password);
            
            ESP_LOGI(TAG, "WiFi config updated: SSID='%s' (len=%zu)", wifi_cfg.ssid, strlen(wifi_cfg.ssid));
            
            // Update MQTT configuration
            cJSON *mqtt_obj = cJSON_GetObjectItem(config, "mqtt");
            if (!mqtt_obj) {
                mqtt_obj = cJSON_CreateObject();
                cJSON_AddItemToObject(config, "mqtt", mqtt_obj);
            }
            cJSON_DeleteItemFromObject(mqtt_obj, "host");
            cJSON_DeleteItemFromObject(mqtt_obj, "port");
            cJSON_AddStringToObject(mqtt_obj, "host", credentials->mqtt_host);
            cJSON_AddNumberToObject(mqtt_obj, "port", credentials->mqtt_port);
            
            // КРИТИЧНО: Проверяем SSID в JSON перед сохранением
            cJSON *wifi_verify = cJSON_GetObjectItem(config, "wifi");
            if (wifi_verify) {
                cJSON *ssid_verify = cJSON_GetObjectItem(wifi_verify, "ssid");
                if (!ssid_verify || !cJSON_IsString(ssid_verify) || 
                    !ssid_verify->valuestring || strlen(ssid_verify->valuestring) == 0) {
                    ESP_LOGE(TAG, "CRITICAL: SSID is empty in JSON config before saving (update existing) - aborting");
                    cJSON_Delete(config);
                    return;
                }
                ESP_LOGI(TAG, "Verified SSID in JSON config before saving (update): '%s' (len=%zu)", 
                        ssid_verify->valuestring, strlen(ssid_verify->valuestring));
            }
            
            char *json_str = cJSON_PrintUnformatted(config);
            if (json_str) {
                esp_err_t err = config_storage_save(json_str, strlen(json_str));
                if (err != ESP_OK) {
                    ESP_LOGE(TAG, "Failed to save config: %s", esp_err_to_name(err));
                } else {
                    ESP_LOGI(TAG, "WiFi and MQTT config saved successfully");
                    // КРИТИЧНО: После сохранения загружаем конфигурацию обратно для проверки
                    // Это гарантирует, что конфигурация валидна и будет доступна после перезагрузки
                    esp_err_t load_err = config_storage_load();
                    if (load_err != ESP_OK) {
                        ESP_LOGE(TAG, "Failed to reload config after save: %s", esp_err_to_name(load_err));
                    } else {
                        ESP_LOGI(TAG, "Config reloaded and validated successfully");
                    }
                }
                free(json_str);
            }
            cJSON_Delete(config);
        }
    } else {
        // If no config exists, create minimal valid config
        // Validation requires: node_id, version, type, gh_uid, zone_uid, channels, wifi, mqtt
        cJSON *config = cJSON_CreateObject();
        
        // Required fields for validation
        if (has_hw_id) {
            cJSON_AddStringToObject(config, "node_id", hardware_id);
        } else {
            cJSON_AddStringToObject(config, "node_id", "node-temp"); // fallback
        }
        cJSON_AddNumberToObject(config, "version", 1);
        cJSON_AddStringToObject(config, "type", node_type);
        cJSON_AddStringToObject(config, "gh_uid", "gh-temp"); // Temporary, will be replaced via MQTT
        cJSON_AddStringToObject(config, "zone_uid", "zn-temp"); // Temporary, will be replaced via MQTT
        
        // Empty channels array (required field)
        cJSON *channels = cJSON_CreateArray();
        cJSON_AddItemToObject(config, "channels", channels);
        
        // WiFi configuration
        cJSON *wifi_obj = cJSON_CreateObject();
            // КРИТИЧНО: Проверяем SSID перед добавлением в JSON
            if (strlen(wifi_cfg.ssid) == 0) {
                ESP_LOGE(TAG, "CRITICAL: SSID is empty before adding to JSON config");
                cJSON_Delete(config);
                return;
            }
            cJSON_AddStringToObject(wifi_obj, "ssid", wifi_cfg.ssid);
            cJSON_AddStringToObject(wifi_obj, "pass", wifi_cfg.password);
            cJSON_AddItemToObject(config, "wifi", wifi_obj);
            
            ESP_LOGI(TAG, "WiFi config prepared: SSID='%s' (len=%zu)", wifi_cfg.ssid, strlen(wifi_cfg.ssid));
        
        // MQTT configuration (using provided values)
        cJSON *mqtt_obj = cJSON_CreateObject();
        cJSON_AddStringToObject(mqtt_obj, "host", credentials->mqtt_host);
        cJSON_AddNumberToObject(mqtt_obj, "port", credentials->mqtt_port);
        cJSON_AddItemToObject(config, "mqtt", mqtt_obj);
        
        // КРИТИЧНО: Проверяем SSID в JSON перед сохранением
        cJSON *wifi_check = cJSON_GetObjectItem(config, "wifi");
        if (wifi_check) {
            cJSON *ssid_check = cJSON_GetObjectItem(wifi_check, "ssid");
            if (!ssid_check || !cJSON_IsString(ssid_check) || 
                !ssid_check->valuestring || strlen(ssid_check->valuestring) == 0) {
                ESP_LOGE(TAG, "CRITICAL: SSID is empty in JSON config before saving - aborting");
                cJSON_Delete(config);
                return;
            }
            ESP_LOGI(TAG, "Verified SSID in JSON config before saving: '%s' (len=%zu)", 
                    ssid_check->valuestring, strlen(ssid_check->valuestring));
        }
        
        char *json_str = cJSON_PrintUnformatted(config);
        if (json_str) {
            esp_err_t err = config_storage_save(json_str, strlen(json_str));
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to save config: %s", esp_err_to_name(err));
            } else {
                ESP_LOGI(TAG, "WiFi and MQTT config saved successfully");
                // КРИТИЧНО: После сохранения загружаем конфигурацию обратно для проверки
                // Это гарантирует, что конфигурация валидна и будет доступна после перезагрузки
                esp_err_t load_err = config_storage_load();
                if (load_err != ESP_OK) {
                    ESP_LOGE(TAG, "Failed to reload config after save: %s", esp_err_to_name(load_err));
                } else {
                    ESP_LOGI(TAG, "Config reloaded and validated successfully");
                }
            }
            free(json_str);
        }
        cJSON_Delete(config);
    }
}

// Callback wrapper for full setup mode
static void credentials_callback_wrapper(const setup_portal_credentials_t *creds, void *ctx) {
    const char *node_type_prefix = (const char *)ctx;
    if (creds && s_full_setup_sem) {
        save_credentials_to_config_storage(creds, node_type_prefix);
        xSemaphoreGive(s_full_setup_sem);
    }
}

esp_err_t setup_portal_run_full_setup(const setup_portal_full_config_t *config) {
    if (!config || !config->node_type_prefix) {
        return ESP_ERR_INVALID_ARG;
    }
    
    ESP_LOGW(TAG, "========================================");
    ESP_LOGW(TAG, "=== NODE SETUP MODE ACTIVATED ===");
    ESP_LOGW(TAG, "========================================");
    
    // Generate PIN
    char setup_pin[7] = {0};
    esp_err_t err = setup_portal_generate_pin(setup_pin, sizeof(setup_pin));
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to generate PIN: %s", esp_err_to_name(err));
        return err;
    }
    
    // Create AP SSID
    char ap_ssid[32] = {0};
    snprintf(ap_ssid, sizeof(ap_ssid), "%s_SETUP_%s", config->node_type_prefix, setup_pin);
    const char *ap_password = config->ap_password ? config->ap_password : "hydro2025";
    
    // Initialize OLED if enabled
    if (config->enable_oled) {
        ESP_LOGI(TAG, "=== Setup Mode OLED Initialization ===");
        if (!i2c_bus_is_initialized()) {
            ESP_LOGW(TAG, "I2C bus not initialized, cannot initialize OLED in setup mode");
        } else {
            ESP_LOGI(TAG, "I2C bus is initialized, initializing OLED for setup mode...");
            oled_ui_config_t oled_config = {
                .i2c_address = 0x3C,
                .update_interval_ms = 1500,  // Увеличено с 500 до 1500 мс для плавного обновления
                .enable_task = true
            };
            ESP_LOGI(TAG, "OLED config: addr=0x%02X, interval=%dms", 
                     oled_config.i2c_address, oled_config.update_interval_ms);
            
            // Determine node type for OLED
            oled_ui_node_type_t node_type = OLED_UI_NODE_TYPE_UNKNOWN;
            if (strcmp(config->node_type_prefix, "PH") == 0) {
                node_type = OLED_UI_NODE_TYPE_PH;
            } else if (strcmp(config->node_type_prefix, "EC") == 0) {
                node_type = OLED_UI_NODE_TYPE_EC;
            } else if (strcmp(config->node_type_prefix, "CLIMATE") == 0) {
                node_type = OLED_UI_NODE_TYPE_CLIMATE;
            } else if (strcmp(config->node_type_prefix, "PUMP") == 0) {
                node_type = OLED_UI_NODE_TYPE_PUMP;
            }
            
            err = oled_ui_init(node_type, ap_ssid, &oled_config);
            if (err == ESP_OK) {
                ESP_LOGI(TAG, "OLED initialized successfully for setup mode");
                ESP_LOGI(TAG, "Setting OLED state to WIFI_SETUP...");
                err = oled_ui_set_state(OLED_UI_STATE_WIFI_SETUP);
                if (err != ESP_OK) {
                    ESP_LOGW(TAG, "Failed to set OLED state: %s", esp_err_to_name(err));
                }
                
                // Update OLED model with AP SSID
                oled_ui_model_t model = {0};
                strncpy(model.zone_name, ap_ssid, sizeof(model.zone_name) - 1);
                model.zone_name[sizeof(model.zone_name) - 1] = '\0';  // Гарантируем null-termination
                model.connections.wifi_connected = false;
                model.connections.mqtt_connected = false;
                
                ESP_LOGI(TAG, "Updating OLED model with AP SSID: %s", model.zone_name);
                oled_ui_update_model(&model);
                
                // Принудительное обновление экрана сразу
                vTaskDelay(pdMS_TO_TICKS(100));  // Небольшая задержка для завершения инициализации
                oled_ui_refresh();
                vTaskDelay(pdMS_TO_TICKS(100));  // Даем время на отрисовку
                
                ESP_LOGI(TAG, "OLED initialized successfully for setup mode (SSID: %s)", ap_ssid);
            } else {
                ESP_LOGE(TAG, "Failed to initialize OLED: %s (error code: %d)", 
                         esp_err_to_name(err), err);
            }
        }
        ESP_LOGI(TAG, "=== Setup Mode OLED Initialization Complete ===");
    }
    
    // Create semaphore for waiting credentials
    s_full_setup_sem = xSemaphoreCreateBinary();
    if (!s_full_setup_sem) {
        ESP_LOGE(TAG, "Failed to create semaphore for setup portal");
        return ESP_ERR_NO_MEM;
    }
    
    // Setup credentials callback
    bool credentials_received = false;
    
    // Start setup portal
    setup_portal_config_t portal_cfg = {
        .ap_ssid = ap_ssid,
        .ap_password = ap_password,
        .on_credentials = credentials_callback_wrapper,
        .user_ctx = (void *)config->node_type_prefix,
    };
    
    err = setup_portal_start(&portal_cfg);
    if (err != ESP_OK) {
        ESP_LOGE(TAG, "Failed to start setup portal: %s", esp_err_to_name(err));
        if (s_full_setup_sem) {
            vSemaphoreDelete(s_full_setup_sem);
            s_full_setup_sem = NULL;
        }
        return err;
    }
    
    ESP_LOGI(TAG, "========================================");
    ESP_LOGI(TAG, "Connection data:");
    ESP_LOGI(TAG, "  WiFi SSID:    %s", ap_ssid);
    // Безопасность: не логируем пароль и PIN в открытом виде
    ESP_LOGI(TAG, "  WiFi Pass:    [%d characters]", (int)strlen(ap_password));
    ESP_LOGI(TAG, "  PIN:          [%d characters]", (int)strlen(setup_pin));
    ESP_LOGI(TAG, "  Open browser: http://192.168.4.1");
    ESP_LOGI(TAG, "========================================");
    
    // Wait for WiFi credentials
    if (xSemaphoreTake(s_full_setup_sem, portMAX_DELAY) == pdTRUE) {
        credentials_received = true;
    } else {
        ESP_LOGE(TAG, "Waiting for WiFi data interrupted");
    }
    
    setup_portal_stop();
    if (s_full_setup_sem) {
        vSemaphoreDelete(s_full_setup_sem);
        s_full_setup_sem = NULL;
    }
    
    if (!credentials_received) {
        ESP_LOGE(TAG, "WiFi data not received. Please retry setup.");
        while (1) {
            vTaskDelay(pdMS_TO_TICKS(5000));
        }
    }
    
    ESP_LOGI(TAG, "WiFi data saved. Rebooting device...");
    vTaskDelay(pdMS_TO_TICKS(2000));
    esp_restart();
    
    return ESP_OK; // Never reached
}
