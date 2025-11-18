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

static const char *HTML_PAGE = "<!DOCTYPE html><html><head><meta charset='UTF-8'><meta name='viewport' content='width=device-width, initial-scale=1'>" \
    "<title>Hydro Setup</title><style>body{font-family:Arial;margin:0;background:#0f172a;color:#e2e8f0;}" \
    ".container{max-width:420px;margin:4rem auto;background:#1f2937;padding:2rem;border-radius:16px;box-shadow:0 22px 45px rgba(15,23,42,0.45);}h1{text-align:center;}" \
    "label{display:block;margin-top:1rem;font-size:0.9rem;color:#94a3b8;text-transform:uppercase;}" \
    "input{width:100%;padding:0.75rem;margin-top:0.5rem;border-radius:10px;border:1px solid #334155;background:#0f172a;color:#f8fafc;}" \
    "button{margin-top:1.5rem;width:100%;padding:0.9rem;border:none;border-radius:12px;background:#38bdf8;color:#0f172a;font-weight:600;font-size:1rem;cursor:pointer;}" \
    "button:disabled{background:#1e40af;color:#94a3b8;cursor:not-allowed;}" \
    ".status{margin-top:1.5rem;line-height:1.6;} .status-success{color:#22c55e;} .status-error{color:#ef4444;}</style></head><body>" \
    "<div class='container'><h1>🌱 Hydro Setup</h1><p>Введите данные вашего WiFi, чтобы PH нода подключилась к сети.</p>" \
    "<form id='wifiForm'><label>WiFi SSID<input name='ssid' placeholder='MyHomeWiFi' required></label>" \
    "<label>WiFi Пароль<input name='password' type='password' placeholder='Пароль' required></label>" \
    "<button type='submit' id='submitBtn'>Подключить</button><div class='status' id='statusMsg'></div></form></div>" \
    "<script>(function(){const form=document.getElementById('wifiForm');const statusEl=document.getElementById('statusMsg');const btn=document.getElementById('submitBtn');" \
    "form.addEventListener('submit',function(e){e.preventDefault();btn.disabled=true;statusEl.textContent='Отправка...';" \
    "const payload=JSON.stringify({ssid:form.ssid.value,password:form.password.value});" \
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
    if (!cJSON_IsString(ssid) || !cJSON_IsString(password)) {
        cJSON_Delete(root);
        httpd_resp_send_err(req, HTTPD_400_BAD_REQUEST, "Missing ssid/password");
        return ESP_FAIL;
    }

    setup_portal_credentials_t creds = {0};
    strncpy(creds.ssid, ssid->valuestring, sizeof(creds.ssid) - 1);
    strncpy(creds.password, password->valuestring, sizeof(creds.password) - 1);
    ESP_LOGI(TAG, "Данные WiFi: SSID='%s', пароль (%d символов)", creds.ssid, (int)strlen(creds.password));
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
static void save_credentials_to_config_storage(const setup_portal_credentials_t *credentials) {
    if (!credentials) {
        return;
    }
    
    ESP_LOGI(TAG, "Saving WiFi credentials to config_storage: SSID='%s'", credentials->ssid);
    
    // Prepare WiFi config
    config_storage_wifi_t wifi_cfg = {0};
    strncpy(wifi_cfg.ssid, credentials->ssid, sizeof(wifi_cfg.ssid) - 1);
    strncpy(wifi_cfg.password, credentials->password, sizeof(wifi_cfg.password) - 1);
    wifi_cfg.auto_reconnect = true;
    wifi_cfg.timeout_sec = 30;
    
    // Load current config, update WiFi and save
    char json_buf[CONFIG_STORAGE_MAX_JSON_SIZE];
    if (config_storage_get_json(json_buf, sizeof(json_buf)) == ESP_OK) {
        // Update existing config
        cJSON *config = cJSON_Parse(json_buf);
        if (config) {
            cJSON *wifi_obj = cJSON_GetObjectItem(config, "wifi");
            if (!wifi_obj) {
                wifi_obj = cJSON_CreateObject();
                cJSON_AddItemToObject(config, "wifi", wifi_obj);
            }
            cJSON_DeleteItemFromObject(wifi_obj, "ssid");
            cJSON_DeleteItemFromObject(wifi_obj, "pass");
            cJSON_AddStringToObject(wifi_obj, "ssid", wifi_cfg.ssid);
            cJSON_AddStringToObject(wifi_obj, "pass", wifi_cfg.password);
            
            char *json_str = cJSON_PrintUnformatted(config);
            if (json_str) {
                esp_err_t err = config_storage_save(json_str, strlen(json_str));
                if (err != ESP_OK) {
                    ESP_LOGE(TAG, "Failed to save WiFi config: %s", esp_err_to_name(err));
                } else {
                    ESP_LOGI(TAG, "WiFi config saved successfully");
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
        cJSON_AddStringToObject(config, "node_id", "node-temp"); // Temporary ID, will be replaced
        cJSON_AddNumberToObject(config, "version", 1);
        cJSON_AddStringToObject(config, "type", "unknown");
        cJSON_AddStringToObject(config, "gh_uid", "gh-temp"); // Temporary, will be replaced via MQTT
        cJSON_AddStringToObject(config, "zone_uid", "zn-temp"); // Temporary, will be replaced via MQTT
        
        // Empty channels array (required field)
        cJSON *channels = cJSON_CreateArray();
        cJSON_AddItemToObject(config, "channels", channels);
        
        // WiFi configuration
        cJSON *wifi_obj = cJSON_CreateObject();
        cJSON_AddStringToObject(wifi_obj, "ssid", wifi_cfg.ssid);
        cJSON_AddStringToObject(wifi_obj, "pass", wifi_cfg.password);
        cJSON_AddItemToObject(config, "wifi", wifi_obj);
        
        // Minimal MQTT config (required field)
        cJSON *mqtt_obj = cJSON_CreateObject();
        cJSON_AddStringToObject(mqtt_obj, "host", "192.168.1.1"); // Temporary, will be replaced
        cJSON_AddNumberToObject(mqtt_obj, "port", 1883);
        cJSON_AddItemToObject(config, "mqtt", mqtt_obj);
        
        char *json_str = cJSON_PrintUnformatted(config);
        if (json_str) {
            esp_err_t err = config_storage_save(json_str, strlen(json_str));
            if (err != ESP_OK) {
                ESP_LOGE(TAG, "Failed to save WiFi config: %s", esp_err_to_name(err));
            } else {
                ESP_LOGI(TAG, "WiFi config saved successfully");
            }
            free(json_str);
        }
        cJSON_Delete(config);
    }
}

// Callback wrapper for full setup mode
static void credentials_callback_wrapper(const setup_portal_credentials_t *creds, void *ctx) {
    (void)ctx; // Unused
    if (creds && s_full_setup_sem) {
        save_credentials_to_config_storage(creds);
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
    bool oled_initialized = false;
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
                oled_initialized = true;
                ESP_LOGI(TAG, "Setting OLED state to WIFI_SETUP...");
                err = oled_ui_set_state(OLED_UI_STATE_WIFI_SETUP);
                if (err != ESP_OK) {
                    ESP_LOGW(TAG, "Failed to set OLED state: %s", esp_err_to_name(err));
                }
                
                // Update OLED model with AP SSID
                oled_ui_model_t model = {0};
                strncpy(model.zone_name, ap_ssid, sizeof(model.zone_name) - 1);
                model.connections.wifi_connected = false;
                model.connections.mqtt_connected = false;
                oled_ui_update_model(&model);
                oled_ui_refresh();
                
                ESP_LOGI(TAG, "OLED initialized successfully for setup mode");
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
        .user_ctx = NULL,
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
    ESP_LOGI(TAG, "  WiFi Pass:    %s", ap_password);
    ESP_LOGI(TAG, "  PIN:          %s", setup_pin);
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

