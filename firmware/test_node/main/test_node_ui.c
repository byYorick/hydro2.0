/**
 * @file test_node_ui.c
 * @brief Локальный UI для test_node: ILI9341 + LVGL + энкодер
 */

#include "test_node_ui.h"

#include "esp_check.h"
#include "esp_err.h"
#include "esp_heap_caps.h"
#include "esp_lcd_ili9341.h"
#include "esp_lcd_panel_io.h"
#include "esp_lcd_panel_ops.h"
#include "esp_log.h"
#include "esp_timer.h"
#include "driver/gpio.h"
#include "driver/spi_master.h"
#include "freertos/FreeRTOS.h"
#include "freertos/queue.h"
#include "freertos/task.h"
#include "lvgl.h"
#include "sdkconfig.h"

#include <ctype.h>
#include <inttypes.h>
#include <stdbool.h>
#include <stdint.h>
#include <stdlib.h>
#include <stdio.h>
#include <string.h>

static const char *TAG = "test_node_ui";

#ifndef CONFIG_TEST_NODE_LCD_SWAP_XY
#define CONFIG_TEST_NODE_LCD_SWAP_XY 0
#endif

#ifndef CONFIG_TEST_NODE_LCD_RGB_ORDER_BGR
#define CONFIG_TEST_NODE_LCD_RGB_ORDER_BGR 0
#endif

#ifndef CONFIG_TEST_NODE_LCD_MIRROR_X
#define CONFIG_TEST_NODE_LCD_MIRROR_X 0
#endif

#ifndef CONFIG_TEST_NODE_LCD_MIRROR_Y
#define CONFIG_TEST_NODE_LCD_MIRROR_Y 0
#endif

#ifndef CONFIG_TEST_NODE_LCD_INVERT_COLORS
#define CONFIG_TEST_NODE_LCD_INVERT_COLORS 0
#endif

#ifndef CONFIG_TEST_NODE_LCD_IO_QUEUE_DEPTH
#define CONFIG_TEST_NODE_LCD_IO_QUEUE_DEPTH 2
#endif

#ifdef CONFIG_TEST_NODE_LCD_SWAP_COLOR_BYTES
#define TEST_NODE_LCD_SWAP_COLOR_BYTES 1
#else
#define TEST_NODE_LCD_SWAP_COLOR_BYTES 0
#endif

#ifdef CONFIG_TEST_NODE_LCD_SINGLE_BUFFER
#define TEST_NODE_LCD_SINGLE_BUFFER 1
#else
#define TEST_NODE_LCD_SINGLE_BUFFER 0
#endif

#if CONFIG_TEST_NODE_UI_ENABLE

#define LCD_HOST SPI2_HOST
#define LCD_DMA_MIN_TRANSFER_LINES 80
#define LVGL_TICK_PERIOD_MS 2
#define LVGL_TASK_PERIOD_MS 10
#define LVGL_TASK_STACK_SIZE 16384
#define LVGL_TASK_PRIORITY 5
#define UI_EVENT_QUEUE_LEN 32
#define UI_LOG_EVENT_QUEUE_LEN 96
#define UI_MAX_HP_EVENTS_PER_CYCLE 32
#define UI_MAX_LOG_EVENTS_PER_CYCLE 16
#define UI_TEXT_MAX 80
#define UI_NODE_UID_MAX 48
#define UI_ZONE_UID_MAX 24
#define UI_SHORT_NAME_MAX 8
#define UI_NODE_TELEMETRY_MAX 20
#define UI_MAX_NODES 8
#define UI_EXPECTED_VISIBLE_NODES 6
#define UI_LOG_LINES_MAX 320
#define UI_LOG_LINE_MAX 88
#define UI_LOG_VISIBLE_LINES 14
#define UI_EXPECTED_VISIBLE_LOG_ROWS 10
#define UI_BLINK_INTERVAL_MS 200
#define UI_HB_BLINK_TICKS 6
#define UI_LWT_BLINK_TICKS 8
#define UI_SCROLL_LOG_STEP 1
#define UI_DEBUG_DUMP_PERIOD_MS 0
#define ENCODER_TRANSITIONS_PER_STEP 2
#define ENCODER_BUTTON_DEBOUNCE_MS 25
#define ENCODER_SETTINGS_HOLD_MS 3000

#define UI_COLOR_BG_MAIN        0x06141D
#define UI_COLOR_BG_SETUP       0x2A1014
#define UI_COLOR_BG_SETTINGS    0x1B0F09
#define UI_COLOR_PANEL_NODES    0x0B1E2A
#define UI_COLOR_PANEL_LOG      0x041016
#define UI_COLOR_PANEL_SETUP    0x3A1A20
#define UI_COLOR_BORDER_NODES   0x2F5E76
#define UI_COLOR_BORDER_LOG     0x2D6B83
#define UI_COLOR_BORDER_SETUP   0xB8485A
#define UI_COLOR_TEXT_PRIMARY   0xD9EEF7
#define UI_COLOR_TEXT_DIM       0xA8C6D6
#define UI_COLOR_ACCENT_INFO    0x8FD9FF
#define UI_COLOR_ACCENT_OK      0x9BE7C2
#define UI_COLOR_ACCENT_WARN    0xFFD98A
#define UI_COLOR_ACCENT_ALERT   0xFFB0A1

#if LV_COLOR_DEPTH != 16
#error "test_node_ui requires LV_COLOR_DEPTH=16"
#endif

#if defined(CONFIG_LV_FONT_MONTSERRAT_12) && CONFIG_LV_FONT_MONTSERRAT_12
#define UI_FONT_SMALL (&lv_font_montserrat_12)
#else
#define UI_FONT_SMALL LV_FONT_DEFAULT
#endif

typedef enum {
    UI_EVENT_STEP = 0,
    UI_EVENT_LOG,
    UI_EVENT_WIFI_STATUS,
    UI_EVENT_MQTT_STATUS,
    UI_EVENT_MODE,
    UI_EVENT_SETUP_INFO,
    UI_EVENT_NODE_REGISTER,
    UI_EVENT_NODE_ZONE,
    UI_EVENT_NODE_HEARTBEAT,
    UI_EVENT_NODE_LWT,
    UI_EVENT_NODE_STATUS,
} ui_event_type_t;

typedef struct {
    ui_event_type_t type;
    bool flag;
    char node_uid[UI_NODE_UID_MAX];
    char text[UI_TEXT_MAX];
    char text2[UI_TEXT_MAX];
} ui_event_msg_t;

typedef struct {
    bool in_use;
    bool online;
    uint8_t hb_blink_ticks;
    uint8_t lwt_blink_ticks;
    char node_uid[UI_NODE_UID_MAX];
    char short_name[UI_SHORT_NAME_MAX];
    char zone_uid[UI_ZONE_UID_MAX];
    char last_telemetry[UI_NODE_TELEMETRY_MAX];
} ui_node_view_t;

static esp_lcd_panel_io_handle_t s_panel_io = NULL;
static esp_lcd_panel_handle_t s_panel_handle = NULL;
static lv_display_t *s_lv_display = NULL;
static lv_indev_t *s_encoder_indev = NULL;
static lv_color_t *s_buf_a = NULL;
static lv_color_t *s_buf_b = NULL;
static QueueHandle_t s_event_queue_hp = NULL;
static QueueHandle_t s_event_queue_log = NULL;
static TaskHandle_t s_lvgl_task_handle = NULL;
static esp_timer_handle_t s_lvgl_tick_timer = NULL;

static lv_obj_t *s_wifi_label = NULL;
static lv_obj_t *s_mqtt_label = NULL;
static lv_obj_t *s_mode_label = NULL;
static lv_obj_t *s_diag_label = NULL;
static lv_obj_t *s_diag_big_label = NULL;
static lv_obj_t *s_nodes_box = NULL;
static lv_obj_t *s_nodes_label_rows[UI_MAX_NODES] = {NULL};
static lv_obj_t *s_nodes_state_rows[UI_MAX_NODES] = {NULL};
static size_t s_nodes_rows_count = UI_MAX_NODES;
static lv_obj_t *s_log_box = NULL;
static lv_obj_t *s_log_title = NULL;
static lv_obj_t *s_log_label_rows[UI_LOG_VISIBLE_LINES] = {NULL};
static size_t s_log_rows_count = UI_LOG_VISIBLE_LINES;
static lv_obj_t *s_setup_box = NULL;
static lv_obj_t *s_setup_title = NULL;
static lv_obj_t *s_setup_details = NULL;
static lv_obj_t *s_settings_menu = NULL;
static lv_obj_t *s_settings_page_main = NULL;
static lv_obj_t *s_settings_cont_back = NULL;
static lv_obj_t *s_settings_cont_reset_zones = NULL;
static lv_obj_t *s_settings_cont_factory_reset = NULL;
static lv_obj_t *s_settings_hint_label = NULL;

static char s_wifi_status[UI_TEXT_MAX] = "INIT";
static char s_mqtt_status[UI_TEXT_MAX] = "INIT";
static char s_mode_status[UI_TEXT_MAX] = "BOOT";
static char s_setup_ssid[UI_NODE_UID_MAX] = "";
static char s_setup_password[UI_TEXT_MAX] = "";
static char s_setup_pin[UI_TEXT_MAX] = "";
static char s_setup_url[UI_TEXT_MAX] = "http://192.168.4.1";
static bool s_wifi_connected = false;
static bool s_mqtt_connected = false;
static int64_t s_boot_us = 0;
static char s_wifi_line_buf[24] = "";
static char s_mqtt_line_buf[12] = "";
static char s_mode_line_buf[UI_TEXT_MAX + 12] = "";
static char s_nodes_row_text_buf[UI_MAX_NODES][UI_TEXT_MAX] = {{0}};
static char s_nodes_state_text_buf[UI_MAX_NODES][24] = {{0}};
static char s_log_row_text_buf[UI_LOG_VISIBLE_LINES][UI_LOG_LINE_MAX] = {{0}};
static char s_log_title_buf[48] = "";
static char s_setup_details_buf[(UI_TEXT_MAX * 4) + 64] = "";
static char s_diag_line_buf[48] = "";
static char s_diag_big_line_buf[64] = "";

static ui_node_view_t s_nodes[UI_MAX_NODES] = {{0}};

static char s_log_lines[UI_LOG_LINES_MAX][UI_LOG_LINE_MAX] = {{0}};
static size_t s_log_start = 0;
static size_t s_log_count = 0;
static size_t s_log_scroll_offset = 0;

static portMUX_TYPE s_encoder_mux = portMUX_INITIALIZER_UNLOCKED;
static volatile int16_t s_encoder_quarter_accum = 0;
static volatile int16_t s_encoder_step_buffer = 0;
static volatile uint8_t s_encoder_prev_state = 0;
static int s_encoder_btn_idle_level = 1;
static bool s_encoder_btn_last_sample_pressed = false;
static bool s_encoder_btn_stable_pressed = false;
static bool s_encoder_btn_prev_stable_pressed = false;
static int64_t s_encoder_btn_last_change_us = 0;
static int64_t s_encoder_btn_press_started_us = 0;
static bool s_encoder_long_press_handled = false;
static bool s_settings_menu_active = false;
static uint8_t s_settings_menu_selected = 0;
static test_node_ui_settings_action_cb_t s_settings_action_cb = NULL;
static void *s_settings_action_user_ctx = NULL;
static uint32_t s_dbg_enqueue_counters[UI_EVENT_NODE_STATUS + 1] = {0};
static uint32_t s_dbg_apply_counters[UI_EVENT_NODE_STATUS + 1] = {0};
static uint32_t s_dbg_log_enqueue_total = 0;
static uint32_t s_dbg_log_apply_total = 0;
static uint32_t s_dbg_log_drop_total = 0;
static uint32_t s_dbg_hp_drop_total = 0;

static bool ui_mode_is_setup(void) {
    return strncmp(s_mode_status, "SETUP", 5) == 0;
}

static void ui_refresh_setup_box(void);

static void ui_refresh_settings_menu(void) {
    if (!s_settings_menu || !s_settings_cont_back || !s_settings_cont_reset_zones || !s_settings_cont_factory_reset || !s_settings_hint_label) {
        return;
    }

    lv_obj_set_style_bg_opa(
        s_settings_cont_back,
        s_settings_menu_selected == 0 ? LV_OPA_30 : LV_OPA_TRANSP,
        LV_PART_MAIN
    );
    lv_obj_set_style_bg_color(
        s_settings_cont_back,
        lv_color_hex(0x4F6E82),
        LV_PART_MAIN
    );

    lv_obj_set_style_bg_opa(
        s_settings_cont_reset_zones,
        s_settings_menu_selected == 1 ? LV_OPA_30 : LV_OPA_TRANSP,
        LV_PART_MAIN
    );
    lv_obj_set_style_bg_color(
        s_settings_cont_reset_zones,
        lv_color_hex(0xCE9A3B),
        LV_PART_MAIN
    );

    lv_obj_set_style_bg_opa(
        s_settings_cont_factory_reset,
        s_settings_menu_selected == 2 ? LV_OPA_30 : LV_OPA_TRANSP,
        LV_PART_MAIN
    );
    lv_obj_set_style_bg_color(
        s_settings_cont_factory_reset,
        lv_color_hex(0xC35E5E),
        LV_PART_MAIN
    );

    lv_label_set_text(s_settings_hint_label, "Click: apply  Hold 3s: close");
    lv_obj_invalidate(s_settings_cont_back);
    lv_obj_invalidate(s_settings_cont_reset_zones);
    lv_obj_invalidate(s_settings_cont_factory_reset);
    lv_obj_invalidate(s_settings_hint_label);
}

static void ui_refresh_setup_box(void) {
    const bool setup_mode = ui_mode_is_setup();
    const bool settings_mode = s_settings_menu_active && !setup_mode;

    if (!s_setup_box || !s_setup_title || !s_setup_details || !s_nodes_box || !s_log_box || !s_settings_menu) {
        return;
    }

    if (setup_mode) {
        lv_obj_clear_flag(s_setup_box, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_nodes_box, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_log_box, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_settings_menu, LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_style_bg_color(lv_scr_act(), lv_color_hex(UI_COLOR_BG_SETUP), 0);
        lv_obj_set_style_bg_opa(lv_scr_act(), LV_OPA_COVER, 0);
        lv_obj_set_style_border_width(lv_scr_act(), 0, 0);
        lv_obj_set_style_pad_all(lv_scr_act(), 0, 0);
        lv_obj_clear_flag(lv_scr_act(), LV_OBJ_FLAG_SCROLLABLE);
        lv_obj_set_style_border_color(s_log_box, lv_color_hex(0x8A3546), 0);
        lv_label_set_text_static(s_setup_title, "SETUP PORTAL");
        snprintf(
            s_setup_details_buf,
            sizeof(s_setup_details_buf),
            "WiFi SSID: %s\nWiFi Pass: %s\nPIN: %s\nOpen: %s",
            s_setup_ssid[0] ? s_setup_ssid : "(waiting)",
            s_setup_password[0] ? s_setup_password : "(waiting)",
            s_setup_pin[0] ? s_setup_pin : "(waiting)",
            s_setup_url[0] ? s_setup_url : "http://192.168.4.1"
        );
        lv_label_set_text_static(s_setup_details, s_setup_details_buf);
        return;
    }

    lv_obj_add_flag(s_setup_box, LV_OBJ_FLAG_HIDDEN);
    lv_obj_set_style_bg_color(
        lv_scr_act(),
        settings_mode ? lv_color_hex(UI_COLOR_BG_SETTINGS) : lv_color_hex(UI_COLOR_BG_MAIN),
        0
    );
    lv_obj_set_style_bg_opa(lv_scr_act(), LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(lv_scr_act(), 0, 0);
    lv_obj_set_style_pad_all(lv_scr_act(), 0, 0);
    lv_obj_clear_flag(lv_scr_act(), LV_OBJ_FLAG_SCROLLABLE);
    if (settings_mode) {
        lv_obj_add_flag(s_nodes_box, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_log_box, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s_settings_menu, LV_OBJ_FLAG_HIDDEN);
        ui_refresh_settings_menu();
    } else {
        lv_obj_clear_flag(s_nodes_box, LV_OBJ_FLAG_HIDDEN);
        lv_obj_clear_flag(s_log_box, LV_OBJ_FLAG_HIDDEN);
        lv_obj_add_flag(s_settings_menu, LV_OBJ_FLAG_HIDDEN);
        lv_obj_set_style_border_color(s_log_box, lv_color_hex(UI_COLOR_BORDER_LOG), 0);
    }
}

static bool panel_io_color_trans_done(
    esp_lcd_panel_io_handle_t panel_io,
    esp_lcd_panel_io_event_data_t *edata,
    void *user_ctx
) {
    lv_display_t *disp = (lv_display_t *)user_ctx;
    (void)panel_io;
    (void)edata;
    if (!disp) {
        disp = s_lv_display;
    }
    if (disp) {
        lv_display_flush_ready(disp);
    }
    return false;
}

static void lvgl_tick_timer_cb(void *arg) {
    (void)arg;
    lv_tick_inc(LVGL_TICK_PERIOD_MS);
}

static void ui_make_short_name(const char *node_uid, char *out, size_t out_size) {
    const char *src = node_uid;
    size_t i = 0;

    if (!out || out_size == 0) {
        return;
    }

    if (!node_uid || node_uid[0] == '\0') {
        snprintf(out, out_size, "SYS");
        return;
    }

    if (strstr(node_uid, "-irrig-") != NULL) {
        snprintf(out, out_size, "IRR");
        return;
    }
    if (strstr(node_uid, "-ph-") != NULL) {
        snprintf(out, out_size, "PH");
        return;
    }
    if (strstr(node_uid, "-ec-") != NULL) {
        snprintf(out, out_size, "EC");
        return;
    }
    if (strstr(node_uid, "-tank-") != NULL) {
        snprintf(out, out_size, "TNK");
        return;
    }
    if (strstr(node_uid, "-climate-") != NULL) {
        snprintf(out, out_size, "CLI");
        return;
    }
    if (strstr(node_uid, "-light-") != NULL) {
        snprintf(out, out_size, "LGT");
        return;
    }

    if (strncmp(node_uid, "nd-", 3) == 0) {
        src = node_uid + 3;
    }

    while (src[i] != '\0' && i < out_size - 1) {
        char ch = src[i];
        if (ch == '-') {
            break;
        }
        out[i] = (char)toupper((unsigned char)ch);
        i++;
    }
    out[i] = '\0';

    if (out[0] == '\0') {
        snprintf(out, out_size, "NODE");
    }
}

static int ui_find_node_index(const char *node_uid) {
    size_t i;

    if (!node_uid || node_uid[0] == '\0') {
        return -1;
    }

    for (i = 0; i < UI_MAX_NODES; i++) {
        if (s_nodes[i].in_use && strcmp(s_nodes[i].node_uid, node_uid) == 0) {
            return (int)i;
        }
    }

    return -1;
}

static int ui_ensure_node_index(const char *node_uid) {
    size_t i;
    int index;

    index = ui_find_node_index(node_uid);
    if (index >= 0) {
        return index;
    }

    for (i = 0; i < UI_MAX_NODES; i++) {
        if (!s_nodes[i].in_use) {
            s_nodes[i].in_use = true;
            s_nodes[i].online = false;
            s_nodes[i].hb_blink_ticks = 0;
            s_nodes[i].lwt_blink_ticks = 0;
            snprintf(s_nodes[i].node_uid, sizeof(s_nodes[i].node_uid), "%s", node_uid ? node_uid : "unknown");
            ui_make_short_name(s_nodes[i].node_uid, s_nodes[i].short_name, sizeof(s_nodes[i].short_name));
            snprintf(s_nodes[i].zone_uid, sizeof(s_nodes[i].zone_uid), "--");
            snprintf(s_nodes[i].last_telemetry, sizeof(s_nodes[i].last_telemetry), "--");
            return (int)i;
        }
    }

    return -1;
}

static const char *ui_node_short_or_uid(const char *node_uid) {
    int idx = ui_find_node_index(node_uid);
    if (idx >= 0) {
        return s_nodes[idx].short_name;
    }
    return node_uid ? node_uid : "SYS";
}

static bool ui_status_is_online(const char *status) {
    if (!status) {
        return false;
    }
    return strcmp(status, "ONLINE") == 0 || strcmp(status, "online") == 0 || strcmp(status, "ON") == 0;
}

static void ui_refresh_diag_label(void) {
    size_t i;
    size_t nodes_in_use = 0;
    UBaseType_t hp_depth = 0;
    UBaseType_t log_depth = 0;

    if (!s_diag_label) {
        return;
    }

    for (i = 0; i < UI_MAX_NODES; i++) {
        if (s_nodes[i].in_use) {
            nodes_in_use++;
        }
    }
    if (s_event_queue_hp) {
        hp_depth = uxQueueMessagesWaiting(s_event_queue_hp);
    }
    if (s_event_queue_log) {
        log_depth = uxQueueMessagesWaiting(s_event_queue_log);
    }

    snprintf(
        s_diag_line_buf,
        sizeof(s_diag_line_buf),
        "N:%u L:%u Q:%u/%u",
        (unsigned)nodes_in_use,
        (unsigned)s_log_count,
        (unsigned)hp_depth,
        (unsigned)log_depth
    );
    lv_label_set_text_static(s_diag_label, s_diag_line_buf);
    lv_obj_invalidate(s_diag_label);

    if (s_diag_big_label) {
        snprintf(
            s_diag_big_line_buf,
            sizeof(s_diag_big_line_buf),
            "OK N:%u L:%u W:%u Q:%u",
            (unsigned)nodes_in_use,
            (unsigned)s_log_count,
            (unsigned)(s_wifi_connected ? 1 : 0),
            (unsigned)(s_mqtt_connected ? 1 : 0)
        );
        lv_label_set_text_static(s_diag_big_label, s_diag_big_line_buf);
        lv_obj_invalidate(s_diag_big_label);
    }
}

static void ui_refresh_status_labels(void) {
    bool show_mode;
    const char *wifi_text;
    const char *mqtt_text;

    if (!s_wifi_label || !s_mqtt_label || !s_mode_label) {
        return;
    }

    wifi_text = s_wifi_connected
        ? (s_wifi_status[0] != '\0' ? s_wifi_status : "?")
        : "X";
    mqtt_text = s_mqtt_connected
        ? (s_mqtt_status[0] != '\0' ? s_mqtt_status : "OK")
        : "X";

    snprintf(
        s_wifi_line_buf,
        sizeof(s_wifi_line_buf),
        "W:%.*s",
        20,
        wifi_text
    );
    snprintf(
        s_mqtt_line_buf,
        sizeof(s_mqtt_line_buf),
        "Q:%.*s",
        8,
        mqtt_text
    );
    snprintf(
        s_mode_line_buf,
        sizeof(s_mode_line_buf),
        "%s",
        ui_mode_is_setup() ? "SETUP MODE ACTIVE" : (s_mode_status[0] != '\0' ? s_mode_status : "RUN")
    );

    lv_label_set_text_static(s_wifi_label, s_wifi_line_buf);
    lv_label_set_text_static(s_mqtt_label, s_mqtt_line_buf);
    show_mode = ui_mode_is_setup() || strncmp(s_mode_status, "BOOT", 4) == 0 || strncmp(s_mode_status, "SETUP_ERR", 9) == 0;
    if (show_mode) {
        lv_obj_clear_flag(s_mode_label, LV_OBJ_FLAG_HIDDEN);
        lv_label_set_text_static(s_mode_label, s_mode_line_buf);
    } else {
        lv_obj_add_flag(s_mode_label, LV_OBJ_FLAG_HIDDEN);
    }
    lv_obj_set_style_text_color(
        s_mode_label,
        ui_mode_is_setup() ? lv_color_hex(UI_COLOR_ACCENT_ALERT) : lv_color_hex(UI_COLOR_ACCENT_WARN),
        0
    );
    lv_obj_set_style_bg_color(
        s_mode_label,
        ui_mode_is_setup() ? lv_color_hex(0x5E2525) : lv_color_hex(0x2A2A2A),
        0
    );
    ui_refresh_setup_box();
    ui_refresh_settings_menu();
    ui_refresh_diag_label();
}

static void ui_refresh_nodes_label(void) {
    size_t i;
    size_t row = 0;

    if (!s_nodes_label_rows[0]) {
        return;
    }

    for (i = 0; i < UI_MAX_NODES && row < s_nodes_rows_count; i++) {
        const char *hb_icon = " ";
        const char *lwt_icon = " ";
        const char *state_icon = NULL;
        char zone_short[11];
        const char *telemetry_short = NULL;

        if (!s_nodes[i].in_use) {
            continue;
        }

        if (s_nodes[i].hb_blink_ticks > 0 && (s_nodes[i].hb_blink_ticks % 2U) == 0U) {
            hb_icon = LV_SYMBOL_REFRESH;
        }
        if (s_nodes[i].lwt_blink_ticks > 0 && (s_nodes[i].lwt_blink_ticks % 2U) == 0U) {
            lwt_icon = LV_SYMBOL_WARNING;
        }

        state_icon = s_nodes[i].online ? LV_SYMBOL_OK : LV_SYMBOL_CLOSE;
        telemetry_short = s_nodes[i].last_telemetry[0] ? s_nodes[i].last_telemetry : "--";
        snprintf(
            zone_short,
            sizeof(zone_short),
            "%.*s",
            (int)sizeof(zone_short) - 1,
            s_nodes[i].zone_uid
        );

        snprintf(
            s_nodes_row_text_buf[row],
            sizeof(s_nodes_row_text_buf[row]),
            "%-3.3s %-10.10s z:%-7.7s",
            s_nodes[i].short_name,
            telemetry_short,
            zone_short
        );
        snprintf(
            s_nodes_state_text_buf[row],
            sizeof(s_nodes_state_text_buf[row]),
            "%s %s %s",
            hb_icon,
            lwt_icon,
            state_icon
        );
        lv_label_set_text(s_nodes_label_rows[row], s_nodes_row_text_buf[row]);
        if (s_nodes_state_rows[row]) {
            lv_label_set_text(s_nodes_state_rows[row], s_nodes_state_text_buf[row]);
            lv_obj_invalidate(s_nodes_state_rows[row]);
        }
        lv_obj_invalidate(s_nodes_label_rows[row]);
        row++;
    }

    if (row == 0) {
        snprintf(s_nodes_row_text_buf[0], sizeof(s_nodes_row_text_buf[0]), "%s", "(nodes empty)");
        lv_label_set_text(s_nodes_label_rows[0], s_nodes_row_text_buf[0]);
        lv_obj_invalidate(s_nodes_label_rows[0]);
        row = 1;
    }

    for (i = row; i < s_nodes_rows_count; i++) {
        s_nodes_row_text_buf[i][0] = '\0';
        s_nodes_state_text_buf[i][0] = '\0';
        lv_label_set_text(s_nodes_label_rows[i], s_nodes_row_text_buf[i]);
        if (s_nodes_state_rows[i]) {
            lv_label_set_text(s_nodes_state_rows[i], s_nodes_state_text_buf[i]);
            lv_obj_invalidate(s_nodes_state_rows[i]);
        }
        lv_obj_invalidate(s_nodes_label_rows[i]);
    }

    if (s_nodes_box) {
        lv_obj_invalidate(s_nodes_box);
    }
    ui_refresh_diag_label();
}

static const char *ui_get_log_line(size_t logical_index) {
    size_t ring_index = (s_log_start + logical_index) % UI_LOG_LINES_MAX;
    return s_log_lines[ring_index];
}

static void ui_refresh_log_label(void) {
    size_t visible = s_log_rows_count;
    size_t max_scroll;
    size_t start_index;
    size_t i;

    if (!s_log_label_rows[0] || !s_log_title) {
        return;
    }

    if (s_log_count == 0) {
        snprintf(s_log_row_text_buf[0], sizeof(s_log_row_text_buf[0]), "%s", "[SYS] waiting logs...");
        for (i = 1; i < s_log_rows_count; i++) {
            s_log_row_text_buf[i][0] = '\0';
        }
        snprintf(s_log_title_buf, sizeof(s_log_title_buf), "%s", "LOG cmd+zone (enc)");
        lv_label_set_text(s_log_label_rows[0], s_log_row_text_buf[0]);
        for (i = 1; i < s_log_rows_count; i++) {
            lv_label_set_text(s_log_label_rows[i], s_log_row_text_buf[i]);
        }
        lv_label_set_text(s_log_title, s_log_title_buf);
        for (i = 0; i < s_log_rows_count; i++) {
            lv_obj_invalidate(s_log_label_rows[i]);
        }
        lv_obj_invalidate(s_log_title);
        if (s_log_box) {
            lv_obj_invalidate(s_log_box);
        }
        return;
    }

    if (s_log_count < visible) {
        visible = s_log_count;
    }

    max_scroll = (s_log_count > visible) ? (s_log_count - visible) : 0;
    if (s_log_scroll_offset > max_scroll) {
        s_log_scroll_offset = max_scroll;
    }

    start_index = s_log_count - visible - s_log_scroll_offset;

    for (i = 0; i < s_log_rows_count; i++) {
        if (i < visible) {
            const char *line = ui_get_log_line(start_index + i);
            snprintf(s_log_row_text_buf[i], sizeof(s_log_row_text_buf[i]), "%s", line);
        } else {
            s_log_row_text_buf[i][0] = '\0';
        }
        lv_label_set_text(s_log_label_rows[i], s_log_row_text_buf[i]);
        lv_obj_invalidate(s_log_label_rows[i]);
    }

    snprintf(s_log_title_buf, sizeof(s_log_title_buf), "LOG cmd+zone  off:%u", (unsigned)s_log_scroll_offset);
    lv_label_set_text(s_log_title, s_log_title_buf);
    lv_obj_invalidate(s_log_title);
    if (s_log_box) {
        lv_obj_invalidate(s_log_box);
    }
    ui_refresh_diag_label();
}

static bool ui_log_should_display(const char *message) {
    if (!message || message[0] == '\0') {
        return false;
    }

    if (strncmp(message, "cmd_resp ", 9) == 0) {
        return true;
    }
    if (strncmp(message, "cmd ack ", 8) == 0) {
        return true;
    }
    if (strncmp(message, "cmd run ", 8) == 0) {
        return true;
    }
    if (strncmp(message, "cmd done ", 9) == 0) {
        return true;
    }

    // Оставляем в логе только ключевые строки привязки зон.
    if (strncmp(message, "zone -> ", 8) == 0) {
        return true;
    }
    if (strncmp(message, "config applied zone=", 20) == 0) {
        return true;
    }
    if (strncmp(message, "settings: zones reset to ", 25) == 0) {
        return true;
    }

    return false;
}

static void ui_compact_channel_name(const char *channel, char *out, size_t out_size) {
    if (!out || out_size == 0) {
        return;
    }
    if (!channel || channel[0] == '\0') {
        snprintf(out, out_size, "-");
        return;
    }

    if (strcmp(channel, "ph_sensor") == 0) {
        snprintf(out, out_size, "ph");
        return;
    }
    if (strcmp(channel, "ec_sensor") == 0) {
        snprintf(out, out_size, "ec");
        return;
    }
    if (strcmp(channel, "water_level") == 0) {
        snprintf(out, out_size, "lvl");
        return;
    }
    if (strcmp(channel, "air_temp_c") == 0) {
        snprintf(out, out_size, "tmp");
        return;
    }
    if (strcmp(channel, "air_rh") == 0) {
        snprintf(out, out_size, "rh");
        return;
    }
    if (strcmp(channel, "light_level") == 0) {
        snprintf(out, out_size, "lux");
        return;
    }
    if (strcmp(channel, "flow_present") == 0) {
        snprintf(out, out_size, "flow");
        return;
    }
    if (strcmp(channel, "pump_bus_current") == 0) {
        snprintf(out, out_size, "amp");
        return;
    }

    snprintf(out, out_size, "%.6s", channel);
}

static void ui_compact_cmd_name(const char *cmd, char *out, size_t out_size) {
    if (!out || out_size == 0) {
        return;
    }
    if (!cmd || cmd[0] == '\0') {
        snprintf(out, out_size, "-");
        return;
    }

    if (strcmp(cmd, "test_sensor") == 0 || strcmp(cmd, "probe_sensor") == 0) {
        snprintf(out, out_size, "probe");
        return;
    }
    if (strcmp(cmd, "set_relay") == 0) {
        snprintf(out, out_size, "relay");
        return;
    }
    if (strcmp(cmd, "set_pwm") == 0) {
        snprintf(out, out_size, "pwm");
        return;
    }
    if (strcmp(cmd, "run_pump") == 0) {
        snprintf(out, out_size, "pump");
        return;
    }
    if (strcmp(cmd, "dose") == 0) {
        snprintf(out, out_size, "dose");
        return;
    }
    if (strcmp(cmd, "restart") == 0 || strcmp(cmd, "reboot") == 0) {
        snprintf(out, out_size, "rst");
        return;
    }
    if (
        strcmp(cmd, "report_config") == 0 ||
        strcmp(cmd, "config_report") == 0 ||
        strcmp(cmd, "get_config") == 0 ||
        strcmp(cmd, "sync_config") == 0
    ) {
        snprintf(out, out_size, "cfg");
        return;
    }

    snprintf(out, out_size, "%.6s", cmd);
}

static void ui_trim_number_text(char *num_text) {
    size_t len;

    if (!num_text || num_text[0] == '\0') {
        return;
    }

    len = strlen(num_text);
    while (len > 0 && num_text[len - 1] == '0') {
        num_text[len - 1] = '\0';
        len--;
    }
    if (len > 0 && num_text[len - 1] == '.') {
        num_text[len - 1] = '\0';
    }
}

static bool ui_update_node_telemetry_from_log(const char *node_uid, const char *message) {
    const char *payload;
    const char *slash;
    const char *eq;
    char channel[32];
    char channel_short[12];
    char value[20];
    size_t channel_len;
    size_t value_len;
    int idx;

    if (!node_uid || node_uid[0] == '\0' || !message || strncmp(message, "tel ", 4) != 0) {
        return false;
    }

    payload = message + 4;
    slash = strchr(payload, '/');
    eq = strchr(payload, '=');
    if (!slash || !eq || eq <= slash) {
        return false;
    }

    channel_len = (size_t)(slash - payload);
    if (channel_len >= sizeof(channel)) {
        channel_len = sizeof(channel) - 1;
    }
    memcpy(channel, payload, channel_len);
    channel[channel_len] = '\0';

    value_len = strlen(eq + 1);
    if (value_len >= sizeof(value)) {
        value_len = sizeof(value) - 1;
    }
    memcpy(value, eq + 1, value_len);
    value[value_len] = '\0';

    ui_compact_channel_name(channel, channel_short, sizeof(channel_short));
    ui_trim_number_text(value);

    idx = ui_ensure_node_index(node_uid);
    if (idx < 0) {
        return false;
    }

    snprintf(
        s_nodes[idx].last_telemetry,
        sizeof(s_nodes[idx].last_telemetry),
        "%.*s=%.*s",
        7,
        channel_short,
        11,
        value[0] ? value : "?"
    );
    ui_refresh_nodes_label();
    return true;
}

static void ui_compact_log_message(const char *message, char *out, size_t out_size) {
    char work[UI_TEXT_MAX + 8];
    char ch[12];
    char cmd[12];
    char status[16];
    char value[20];
    const char *p;
    const char *slash;
    const char *eq;

    if (!out || out_size == 0) {
        return;
    }

    out[0] = '\0';
    if (!message || message[0] == '\0') {
        return;
    }

    if (strncmp(message, "tel ", 4) == 0) {
        p = message + 4;
        slash = strchr(p, '/');
        eq = strchr(p, '=');
        if (slash && eq && eq > slash) {
            size_t ch_len = (size_t)(slash - p);
            size_t val_len = strlen(eq + 1);
            if (ch_len >= sizeof(work)) {
                ch_len = sizeof(work) - 1;
            }
            if (val_len >= sizeof(value)) {
                val_len = sizeof(value) - 1;
            }
            memcpy(work, p, ch_len);
            work[ch_len] = '\0';
            memcpy(value, eq + 1, val_len);
            value[val_len] = '\0';
            ui_compact_channel_name(work, ch, sizeof(ch));
            ui_trim_number_text(value);
            snprintf(out, out_size, "T %s=%s", ch, value);
            return;
        }
    }

    if (sscanf(message, "cmd ack %31[^/]/%31s", work, value) == 2) {
        ui_compact_channel_name(work, ch, sizeof(ch));
        ui_compact_cmd_name(value, cmd, sizeof(cmd));
        snprintf(out, out_size, "C+ %s/%s", ch, cmd);
        return;
    }

    if (sscanf(message, "cmd run %31[^/]/%31s", work, value) == 2) {
        ui_compact_channel_name(work, ch, sizeof(ch));
        ui_compact_cmd_name(value, cmd, sizeof(cmd));
        snprintf(out, out_size, "C> %s/%s", ch, cmd);
        return;
    }

    if (sscanf(message, "cmd done %31[^/]/%31s -> %15s", work, value, status) == 3) {
        ui_compact_channel_name(work, ch, sizeof(ch));
        ui_compact_cmd_name(value, cmd, sizeof(cmd));
        snprintf(out, out_size, "C= %s/%s %s", ch, cmd, status);
        return;
    }

    if (sscanf(message, "cmd_resp %15s %31s", status, work) == 2) {
        ui_compact_channel_name(work, ch, sizeof(ch));
        snprintf(out, out_size, "R %s %s", status, ch);
        return;
    }

    if (strncmp(message, "zone -> ", 8) == 0) {
        snprintf(out, out_size, "Z -> %.16s", message + 8);
        return;
    }

    if (strncmp(message, "config applied zone=", 20) == 0) {
        snprintf(out, out_size, "Z cfg %.14s", message + 20);
        return;
    }

    if (strncmp(message, "settings: zones reset to ", 25) == 0) {
        snprintf(out, out_size, "Z reset %.14s", message + 25);
        return;
    }

    snprintf(out, out_size, "%.26s", message);
}

static void ui_append_log_line(const char *node_uid, const char *message) {
    char line[UI_LOG_LINE_MAX];
    char compact_msg[UI_TEXT_MAX];
    const char *prefix = "SYS";

    if (ui_update_node_telemetry_from_log(node_uid, message)) {
        return;
    }

    if (!ui_log_should_display(message)) {
        return;
    }

    if (node_uid && node_uid[0] != '\0') {
        (void)ui_ensure_node_index(node_uid);
        prefix = ui_node_short_or_uid(node_uid);
    }

    ui_compact_log_message(message, compact_msg, sizeof(compact_msg));
    if (compact_msg[0] == '\0') {
        return;
    }
    snprintf(line, sizeof(line), "[%s] %s", prefix, compact_msg);

    if (s_log_count < UI_LOG_LINES_MAX) {
        size_t idx = (s_log_start + s_log_count) % UI_LOG_LINES_MAX;
        snprintf(s_log_lines[idx], sizeof(s_log_lines[idx]), "%s", line);
        s_log_count++;
    } else {
        snprintf(s_log_lines[s_log_start], sizeof(s_log_lines[s_log_start]), "%s", line);
        s_log_start = (s_log_start + 1) % UI_LOG_LINES_MAX;
    }

    ui_refresh_log_label();
}

static void ui_scroll_logs(int32_t diff) {
    size_t visible = (s_log_count < s_log_rows_count) ? s_log_count : s_log_rows_count;
    size_t max_scroll = (s_log_count > visible) ? (s_log_count - visible) : 0;

    if (diff == 0) {
        return;
    }

    if (diff > 0) {
        size_t inc = (size_t)(diff * UI_SCROLL_LOG_STEP);
        if (inc > (max_scroll - s_log_scroll_offset)) {
            s_log_scroll_offset = max_scroll;
        } else {
            s_log_scroll_offset += inc;
        }
    } else {
        size_t dec = (size_t)((-diff) * UI_SCROLL_LOG_STEP);
        if (dec > s_log_scroll_offset) {
            s_log_scroll_offset = 0;
        } else {
            s_log_scroll_offset -= dec;
        }
    }

    ui_refresh_log_label();
}

static void ui_apply_event(const ui_event_msg_t *msg) {
    int idx;

    if (!msg) {
        return;
    }

    if ((unsigned)msg->type <= UI_EVENT_NODE_STATUS) {
        s_dbg_apply_counters[msg->type]++;
    }
    if (msg->type == UI_EVENT_LOG) {
        s_dbg_log_apply_total++;
    }

    switch (msg->type) {
        case UI_EVENT_STEP:
            ui_append_log_line(NULL, msg->text);
            break;

        case UI_EVENT_LOG:
            ui_append_log_line(msg->node_uid, msg->text);
            break;

        case UI_EVENT_WIFI_STATUS:
            s_wifi_connected = msg->flag;
            snprintf(
                s_wifi_status,
                sizeof(s_wifi_status),
                "%.*s",
                (int)sizeof(s_wifi_status) - 1,
                msg->text[0] ? msg->text : ""
            );
            ui_refresh_status_labels();
            break;

        case UI_EVENT_MQTT_STATUS:
            s_mqtt_connected = msg->flag;
            snprintf(
                s_mqtt_status,
                sizeof(s_mqtt_status),
                "%.*s",
                (int)sizeof(s_mqtt_status) - 1,
                msg->text[0] ? msg->text : ""
            );
            ui_refresh_status_labels();
            break;

        case UI_EVENT_MODE:
            snprintf(
                s_mode_status,
                sizeof(s_mode_status),
                "%.*s",
                (int)sizeof(s_mode_status) - 1,
                msg->text[0] ? msg->text : "RUN"
            );
            ui_refresh_status_labels();
            break;

        case UI_EVENT_SETUP_INFO:
            snprintf(
                s_setup_ssid,
                sizeof(s_setup_ssid),
                "%.*s",
                (int)sizeof(s_setup_ssid) - 1,
                msg->node_uid[0] ? msg->node_uid : ""
            );
            snprintf(
                s_setup_password,
                sizeof(s_setup_password),
                "%.*s",
                (int)sizeof(s_setup_password) - 1,
                msg->text[0] ? msg->text : ""
            );
            snprintf(
                s_setup_pin,
                sizeof(s_setup_pin),
                "%.*s",
                (int)sizeof(s_setup_pin) - 1,
                msg->text2[0] ? msg->text2 : ""
            );
            ui_refresh_setup_box();
            break;

        case UI_EVENT_NODE_REGISTER:
            idx = ui_ensure_node_index(msg->node_uid);
            if (idx >= 0 && msg->text[0] != '\0') {
                snprintf(
                    s_nodes[idx].zone_uid,
                    sizeof(s_nodes[idx].zone_uid),
                    "%.*s",
                    (int)sizeof(s_nodes[idx].zone_uid) - 1,
                    msg->text
                );
            }
            ui_refresh_nodes_label();
            break;

        case UI_EVENT_NODE_ZONE:
            idx = ui_ensure_node_index(msg->node_uid);
            if (idx >= 0 && msg->text[0] != '\0') {
                snprintf(
                    s_nodes[idx].zone_uid,
                    sizeof(s_nodes[idx].zone_uid),
                    "%.*s",
                    (int)sizeof(s_nodes[idx].zone_uid) - 1,
                    msg->text
                );
            }
            ui_refresh_nodes_label();
            break;

        case UI_EVENT_NODE_HEARTBEAT:
            idx = ui_ensure_node_index(msg->node_uid);
            if (idx >= 0) {
                s_nodes[idx].hb_blink_ticks = UI_HB_BLINK_TICKS;
            }
            ui_refresh_nodes_label();
            break;

        case UI_EVENT_NODE_LWT:
            idx = ui_ensure_node_index(msg->node_uid);
            if (idx >= 0) {
                s_nodes[idx].lwt_blink_ticks = UI_LWT_BLINK_TICKS;
                s_nodes[idx].online = false;
            }
            ui_refresh_nodes_label();
            break;

        case UI_EVENT_NODE_STATUS:
            idx = ui_ensure_node_index(msg->node_uid);
            if (idx >= 0) {
                s_nodes[idx].online = ui_status_is_online(msg->text);
                if (!s_nodes[idx].online) {
                    s_nodes[idx].lwt_blink_ticks = UI_LWT_BLINK_TICKS;
                }
            }
            ui_refresh_nodes_label();
            break;

        default:
            break;
    }
}

static void ui_process_queue(void) {
    ui_event_msg_t msg;
    uint32_t hp_processed = 0;
    uint32_t log_processed = 0;

    while (s_event_queue_hp && hp_processed < UI_MAX_HP_EVENTS_PER_CYCLE) {
        if (xQueueReceive(s_event_queue_hp, &msg, 0) != pdTRUE) {
            break;
        }
        ui_apply_event(&msg);
        hp_processed++;
    }

    while (s_event_queue_log && log_processed < UI_MAX_LOG_EVENTS_PER_CYCLE) {
        if (xQueueReceive(s_event_queue_log, &msg, 0) != pdTRUE) {
            break;
        }
        ui_apply_event(&msg);
        log_processed++;
    }
}

#if UI_DEBUG_DUMP_PERIOD_MS > 0
static void ui_debug_dump_state(void) {
    size_t nodes_in_use = 0;
    size_t i;
    const char *nodes_text = NULL;
    const char *log_text = NULL;
    size_t nodes_text_len = 0;
    size_t log_text_len = 0;
    UBaseType_t hp_depth = 0;
    UBaseType_t log_depth = 0;
    bool nodes_hidden = true;
    bool setup_hidden = true;
    bool log_hidden = true;

    for (i = 0; i < UI_MAX_NODES; i++) {
        if (s_nodes[i].in_use) {
            nodes_in_use++;
        }
    }

    if (s_event_queue_hp) {
        hp_depth = uxQueueMessagesWaiting(s_event_queue_hp);
    }
    if (s_event_queue_log) {
        log_depth = uxQueueMessagesWaiting(s_event_queue_log);
    }

    if (s_nodes_box) {
        nodes_hidden = lv_obj_has_flag(s_nodes_box, LV_OBJ_FLAG_HIDDEN);
    }
    if (s_setup_box) {
        setup_hidden = lv_obj_has_flag(s_setup_box, LV_OBJ_FLAG_HIDDEN);
    }
    if (s_log_box) {
        log_hidden = lv_obj_has_flag(s_log_box, LV_OBJ_FLAG_HIDDEN);
    }

    if (s_nodes_label_rows[0]) {
        for (i = 0; i < s_nodes_rows_count; i++) {
            nodes_text = lv_label_get_text(s_nodes_label_rows[i]);
            if (nodes_text) {
                nodes_text_len += strlen(nodes_text);
            }
        }
    }
    if (s_log_label_rows[0]) {
        for (i = 0; i < s_log_rows_count; i++) {
            log_text = lv_label_get_text(s_log_label_rows[i]);
            if (log_text) {
                log_text_len += strlen(log_text);
            }
        }
    }

    ESP_LOGI(
        TAG,
        "UI DBG state: mode=%s wifi=%d mqtt=%d nodes=%u log_count=%u scroll=%u hp_q=%u log_q=%u hidden[nodes=%d setup=%d log=%d] txtlen[nodes=%u log=%u]",
        s_mode_status,
        s_wifi_connected,
        s_mqtt_connected,
        (unsigned)nodes_in_use,
        (unsigned)s_log_count,
        (unsigned)s_log_scroll_offset,
        (unsigned)hp_depth,
        (unsigned)log_depth,
        nodes_hidden,
        setup_hidden,
        log_hidden,
        (unsigned)nodes_text_len,
        (unsigned)log_text_len
    );

    ESP_LOGI(
        TAG,
        "UI DBG evt enq/app: STEP %u/%u LOG %u/%u WIFI %u/%u MQTT %u/%u MODE %u/%u REG %u/%u ZONE %u/%u HB %u/%u LWT %u/%u ST %u/%u drop[log=%u hp=%u]",
        s_dbg_enqueue_counters[UI_EVENT_STEP], s_dbg_apply_counters[UI_EVENT_STEP],
        s_dbg_enqueue_counters[UI_EVENT_LOG], s_dbg_apply_counters[UI_EVENT_LOG],
        s_dbg_enqueue_counters[UI_EVENT_WIFI_STATUS], s_dbg_apply_counters[UI_EVENT_WIFI_STATUS],
        s_dbg_enqueue_counters[UI_EVENT_MQTT_STATUS], s_dbg_apply_counters[UI_EVENT_MQTT_STATUS],
        s_dbg_enqueue_counters[UI_EVENT_MODE], s_dbg_apply_counters[UI_EVENT_MODE],
        s_dbg_enqueue_counters[UI_EVENT_NODE_REGISTER], s_dbg_apply_counters[UI_EVENT_NODE_REGISTER],
        s_dbg_enqueue_counters[UI_EVENT_NODE_ZONE], s_dbg_apply_counters[UI_EVENT_NODE_ZONE],
        s_dbg_enqueue_counters[UI_EVENT_NODE_HEARTBEAT], s_dbg_apply_counters[UI_EVENT_NODE_HEARTBEAT],
        s_dbg_enqueue_counters[UI_EVENT_NODE_LWT], s_dbg_apply_counters[UI_EVENT_NODE_LWT],
        s_dbg_enqueue_counters[UI_EVENT_NODE_STATUS], s_dbg_apply_counters[UI_EVENT_NODE_STATUS],
        s_dbg_log_drop_total,
        s_dbg_hp_drop_total
    );
}
#endif

static void ui_tick_blink(void) {
    size_t i;
    bool changed = false;

    for (i = 0; i < UI_MAX_NODES; i++) {
        if (!s_nodes[i].in_use) {
            continue;
        }

        if (s_nodes[i].hb_blink_ticks > 0) {
            s_nodes[i].hb_blink_ticks--;
            changed = true;
        }
        if (s_nodes[i].lwt_blink_ticks > 0) {
            s_nodes[i].lwt_blink_ticks--;
            changed = true;
        }
    }

    if (changed) {
        ui_refresh_nodes_label();
    }
}

static void ui_enqueue_event(
    ui_event_type_t type,
    const char *node_uid,
    const char *text,
    const char *text2,
    bool flag
) {
    ui_event_msg_t msg;
    QueueHandle_t target_queue;

    target_queue = (type == UI_EVENT_LOG) ? s_event_queue_log : s_event_queue_hp;
    if (!target_queue) {
        return;
    }

    memset(&msg, 0, sizeof(msg));
    msg.type = type;
    msg.flag = flag;

    if (node_uid) {
        snprintf(msg.node_uid, sizeof(msg.node_uid), "%s", node_uid);
    }
    if (text) {
        snprintf(msg.text, sizeof(msg.text), "%s", text);
    }
    if (text2) {
        snprintf(msg.text2, sizeof(msg.text2), "%s", text2);
    }

    if ((unsigned)type <= UI_EVENT_NODE_STATUS) {
        s_dbg_enqueue_counters[type]++;
    }
    if (type == UI_EVENT_LOG) {
        s_dbg_log_enqueue_total++;
    }

    if (xQueueSend(target_queue, &msg, pdMS_TO_TICKS(10)) != pdTRUE) {
        if (type == UI_EVENT_LOG) {
            // Для логов удаляем самый старый лог и пробуем ещё раз.
            ui_event_msg_t dropped_log;
            (void)xQueueReceive(target_queue, &dropped_log, 0);
            s_dbg_log_drop_total++;
            (void)xQueueSend(target_queue, &msg, 0);
            return;
        }
        ui_event_msg_t dropped;
        (void)xQueueReceive(target_queue, &dropped, 0);
        s_dbg_hp_drop_total++;
        (void)xQueueSend(target_queue, &msg, 0);
    }
}

static void lvgl_flush_cb(lv_display_t *disp, const lv_area_t *area, uint8_t *px_map) {
    esp_lcd_panel_handle_t panel = (esp_lcd_panel_handle_t)lv_display_get_user_data(disp);
#if TEST_NODE_LCD_SWAP_COLOR_BYTES
    uint32_t px_count = (uint32_t)(area->x2 - area->x1 + 1) * (uint32_t)(area->y2 - area->y1 + 1);
    lv_draw_sw_rgb565_swap(px_map, px_count);
#endif
    esp_err_t err = esp_lcd_panel_draw_bitmap(
        panel ? panel : s_panel_handle,
        area->x1,
        area->y1,
        area->x2 + 1,
        area->y2 + 1,
        px_map
    );
    if (err != ESP_OK) {
        ESP_LOGW(TAG, "esp_lcd_panel_draw_bitmap failed: %s", esp_err_to_name(err));
        lv_display_flush_ready(disp);
    }
}

static void encoder_read_cb(lv_indev_t *indev, lv_indev_data_t *data) {
    int16_t step_diff;
    int btn_sample_level;
    bool btn_sample_pressed;
    int64_t now_us;
    (void)indev;

    portENTER_CRITICAL(&s_encoder_mux);
    step_diff = s_encoder_step_buffer;
    s_encoder_step_buffer = 0;
    portEXIT_CRITICAL(&s_encoder_mux);

    btn_sample_level = gpio_get_level(CONFIG_TEST_NODE_ENCODER_PIN_SW);
    btn_sample_pressed = btn_sample_level != s_encoder_btn_idle_level;
    now_us = esp_timer_get_time();

    if (btn_sample_pressed != s_encoder_btn_last_sample_pressed) {
        s_encoder_btn_last_sample_pressed = btn_sample_pressed;
        s_encoder_btn_last_change_us = now_us;
    } else if ((now_us - s_encoder_btn_last_change_us) >= (ENCODER_BUTTON_DEBOUNCE_MS * 1000LL)) {
        s_encoder_btn_stable_pressed = btn_sample_pressed;
    }

    if (s_encoder_btn_stable_pressed && !s_encoder_btn_prev_stable_pressed) {
        s_encoder_btn_press_started_us = now_us;
        s_encoder_long_press_handled = false;
    } else if (!s_encoder_btn_stable_pressed && s_encoder_btn_prev_stable_pressed) {
        bool short_press = !s_encoder_long_press_handled;
        s_encoder_btn_press_started_us = 0;
        s_encoder_long_press_handled = false;
        if (short_press) {
            if (s_settings_menu_active) {
                s_settings_menu_active = false;
                ui_refresh_settings_menu();
                ui_refresh_setup_box();

                if (s_settings_menu_selected == 0) {
                    ui_append_log_line(NULL, "settings: back");
                } else {
                    test_node_ui_settings_action_t action =
                        (s_settings_menu_selected == 1)
                            ? TEST_NODE_UI_SETTINGS_ACTION_RESET_ZONES
                            : TEST_NODE_UI_SETTINGS_ACTION_FACTORY_RESET;
                    ui_append_log_line(NULL, (action == TEST_NODE_UI_SETTINGS_ACTION_RESET_ZONES)
                        ? "settings: reset zones"
                        : "settings: factory reset");
                    if (s_settings_action_cb) {
                        s_settings_action_cb(action, s_settings_action_user_ctx);
                    }
                }
            } else {
                s_log_scroll_offset = 0;
                ui_refresh_log_label();
                ui_append_log_line(NULL, "scroll -> latest");
            }
        }
    }

    if (s_encoder_btn_stable_pressed && !s_encoder_long_press_handled && s_encoder_btn_press_started_us > 0) {
        int64_t pressed_ms = (now_us - s_encoder_btn_press_started_us) / 1000LL;
        if (pressed_ms >= ENCODER_SETTINGS_HOLD_MS) {
            s_encoder_long_press_handled = true;
            s_settings_menu_active = !s_settings_menu_active;
            if (s_settings_menu_active) {
                s_settings_menu_selected = 0;
                ui_append_log_line(NULL, "settings menu open");
            } else {
                ui_append_log_line(NULL, "settings menu closed");
            }
            ui_refresh_settings_menu();
            ui_refresh_setup_box();
        }
    }

        if (step_diff != 0) {
            if (s_settings_menu_active) {
                int next_index = (int)s_settings_menu_selected + (step_diff > 0 ? 1 : -1);
                if (next_index < 0) {
                    next_index = 0;
                }
                if (next_index > 2) {
                    next_index = 2;
                }
                if ((uint8_t)next_index != s_settings_menu_selected) {
                    s_settings_menu_selected = (uint8_t)next_index;
                ui_refresh_settings_menu();
            }
        } else {
            ui_scroll_logs(step_diff);
        }
    }
    s_encoder_btn_prev_stable_pressed = s_encoder_btn_stable_pressed;

    /* LVGL encoder-группа здесь не используется. Обнуляем, чтобы не было побочных эффектов. */
    data->enc_diff = 0;
    data->state = LV_INDEV_STATE_RELEASED;
    data->continue_reading = false;
}

static void IRAM_ATTR encoder_gpio_isr_handler(void *arg) {
    static const int8_t lut[16] = {0, -1, 1, 0, 1, 0, 0, -1, -1, 0, 0, 1, 0, 1, -1, 0};
    uint8_t curr_state =
        (uint8_t)(((gpio_get_level(CONFIG_TEST_NODE_ENCODER_PIN_A) ? 1 : 0) << 1) |
                  (gpio_get_level(CONFIG_TEST_NODE_ENCODER_PIN_B) ? 1 : 0));
    int8_t quarter_step;
    int16_t quarter_accum;
    (void)arg;

    portENTER_CRITICAL_ISR(&s_encoder_mux);
    quarter_step = lut[(s_encoder_prev_state << 2) | curr_state];
    s_encoder_prev_state = curr_state;
    if (quarter_step != 0) {
        quarter_accum = (int16_t)(s_encoder_quarter_accum + quarter_step);
        if (quarter_accum >= ENCODER_TRANSITIONS_PER_STEP) {
            s_encoder_step_buffer++;
            quarter_accum = 0;
        } else if (quarter_accum <= -ENCODER_TRANSITIONS_PER_STEP) {
            s_encoder_step_buffer--;
            quarter_accum = 0;
        }
        s_encoder_quarter_accum = quarter_accum;
    }
    portEXIT_CRITICAL_ISR(&s_encoder_mux);
}

static void init_encoder_gpio(void) {
    gpio_config_t enc_ab_io = {
        .pin_bit_mask =
            (1ULL << CONFIG_TEST_NODE_ENCODER_PIN_A) |
            (1ULL << CONFIG_TEST_NODE_ENCODER_PIN_B),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_ANYEDGE,
    };
    gpio_config_t enc_sw_io = {
        .pin_bit_mask = (1ULL << CONFIG_TEST_NODE_ENCODER_PIN_SW),
        .mode = GPIO_MODE_INPUT,
        .pull_up_en = GPIO_PULLUP_ENABLE,
        .pull_down_en = GPIO_PULLDOWN_DISABLE,
        .intr_type = GPIO_INTR_DISABLE,
    };
    esp_err_t err;

    ESP_ERROR_CHECK(gpio_config(&enc_ab_io));
    ESP_ERROR_CHECK(gpio_config(&enc_sw_io));

    err = gpio_install_isr_service(ESP_INTR_FLAG_IRAM);
    if (err != ESP_OK && err != ESP_ERR_INVALID_STATE) {
        ESP_ERROR_CHECK(err);
    }

    portENTER_CRITICAL(&s_encoder_mux);
    s_encoder_prev_state = (uint8_t)(((gpio_get_level(CONFIG_TEST_NODE_ENCODER_PIN_A) ? 1 : 0) << 1) |
                                     (gpio_get_level(CONFIG_TEST_NODE_ENCODER_PIN_B) ? 1 : 0));
    s_encoder_quarter_accum = 0;
    s_encoder_step_buffer = 0;
    portEXIT_CRITICAL(&s_encoder_mux);

    s_encoder_btn_idle_level = gpio_get_level(CONFIG_TEST_NODE_ENCODER_PIN_SW);
    s_encoder_btn_last_sample_pressed = false;
    s_encoder_btn_stable_pressed = false;
    s_encoder_btn_prev_stable_pressed = false;
    s_encoder_btn_last_change_us = esp_timer_get_time();

    (void)gpio_isr_handler_remove(CONFIG_TEST_NODE_ENCODER_PIN_A);
    (void)gpio_isr_handler_remove(CONFIG_TEST_NODE_ENCODER_PIN_B);

    ESP_ERROR_CHECK(gpio_isr_handler_add(
        CONFIG_TEST_NODE_ENCODER_PIN_A,
        encoder_gpio_isr_handler,
        NULL
    ));
    ESP_ERROR_CHECK(gpio_isr_handler_add(
        CONFIG_TEST_NODE_ENCODER_PIN_B,
        encoder_gpio_isr_handler,
        NULL
    ));
}

static esp_err_t init_lcd_panel(void) {
    esp_err_t err;
    size_t max_transfer_lines = (size_t)CONFIG_TEST_NODE_LCD_BUFFER_LINES;

    if (CONFIG_TEST_NODE_LCD_PIN_SCLK < 0 || CONFIG_TEST_NODE_LCD_PIN_MOSI < 0 ||
        CONFIG_TEST_NODE_LCD_PIN_DC < 0 || CONFIG_TEST_NODE_LCD_PIN_CS < 0) {
        ESP_LOGE(TAG, "Invalid LCD pins: SCLK/MOSI/DC/CS must be >= 0");
        return ESP_ERR_INVALID_ARG;
    }

    if (CONFIG_TEST_NODE_LCD_PIN_BK_LIGHT >= 0) {
        gpio_config_t bk_gpio_config = {
            .mode = GPIO_MODE_OUTPUT,
            .pin_bit_mask = (1ULL << CONFIG_TEST_NODE_LCD_PIN_BK_LIGHT),
        };
        ESP_RETURN_ON_ERROR(gpio_config(&bk_gpio_config), TAG, "backlight gpio_config failed");
        gpio_set_level(CONFIG_TEST_NODE_LCD_PIN_BK_LIGHT, !CONFIG_TEST_NODE_LCD_BK_LIGHT_ON_LEVEL);
    } else {
        ESP_LOGW(TAG, "LCD backlight pin disabled (CONFIG_TEST_NODE_LCD_PIN_BK_LIGHT = -1)");
    }

    if (max_transfer_lines < LCD_DMA_MIN_TRANSFER_LINES) {
        max_transfer_lines = LCD_DMA_MIN_TRANSFER_LINES;
    }

    spi_bus_config_t buscfg = {
        .sclk_io_num = CONFIG_TEST_NODE_LCD_PIN_SCLK,
        .mosi_io_num = CONFIG_TEST_NODE_LCD_PIN_MOSI,
        .miso_io_num = CONFIG_TEST_NODE_LCD_PIN_MISO,
        .quadwp_io_num = -1,
        .quadhd_io_num = -1,
        .max_transfer_sz = CONFIG_TEST_NODE_LCD_H_RES * max_transfer_lines * sizeof(uint16_t),
    };

    err = spi_bus_initialize(LCD_HOST, &buscfg, SPI_DMA_CH_AUTO);
    if (err != ESP_OK) {
        if (err == ESP_ERR_INVALID_STATE) {
            ESP_LOGE(TAG, "spi_bus_initialize: SPI bus already initialized (possible LCD SPI conflict)");
        }
        ESP_LOGE(TAG, "spi_bus_initialize failed: %s", esp_err_to_name(err));
        return err;
    }

    esp_lcd_panel_io_spi_config_t io_config = {
        .dc_gpio_num = CONFIG_TEST_NODE_LCD_PIN_DC,
        .cs_gpio_num = CONFIG_TEST_NODE_LCD_PIN_CS,
        .pclk_hz = CONFIG_TEST_NODE_LCD_PIXEL_CLOCK_HZ,
        .lcd_cmd_bits = 8,
        .lcd_param_bits = 8,
        .spi_mode = 0,
        .trans_queue_depth = CONFIG_TEST_NODE_LCD_IO_QUEUE_DEPTH,
    };

    ESP_RETURN_ON_ERROR(esp_lcd_new_panel_io_spi(LCD_HOST, &io_config, &s_panel_io), TAG, "new_panel_io_spi failed");

    esp_lcd_panel_dev_config_t panel_config = {
        .reset_gpio_num = CONFIG_TEST_NODE_LCD_PIN_RST,
        .rgb_ele_order = CONFIG_TEST_NODE_LCD_RGB_ORDER_BGR
            ? LCD_RGB_ELEMENT_ORDER_BGR
            : LCD_RGB_ELEMENT_ORDER_RGB,
        .bits_per_pixel = 16,
    };

    ESP_RETURN_ON_ERROR(esp_lcd_new_panel_ili9341(s_panel_io, &panel_config, &s_panel_handle), TAG, "new_panel_ili9341 failed");
    ESP_RETURN_ON_ERROR(esp_lcd_panel_reset(s_panel_handle), TAG, "panel_reset failed");
    ESP_RETURN_ON_ERROR(esp_lcd_panel_init(s_panel_handle), TAG, "panel_init failed");
    ESP_RETURN_ON_ERROR(esp_lcd_panel_swap_xy(s_panel_handle, CONFIG_TEST_NODE_LCD_SWAP_XY), TAG, "panel_swap_xy failed");
    ESP_RETURN_ON_ERROR(
        esp_lcd_panel_mirror(s_panel_handle, CONFIG_TEST_NODE_LCD_MIRROR_X, CONFIG_TEST_NODE_LCD_MIRROR_Y),
        TAG,
        "panel_mirror failed"
    );
    ESP_RETURN_ON_ERROR(esp_lcd_panel_invert_color(s_panel_handle, CONFIG_TEST_NODE_LCD_INVERT_COLORS), TAG, "panel_invert failed");
    ESP_RETURN_ON_ERROR(esp_lcd_panel_disp_on_off(s_panel_handle, true), TAG, "panel_on failed");

    if (CONFIG_TEST_NODE_LCD_PIN_BK_LIGHT >= 0) {
        gpio_set_level(CONFIG_TEST_NODE_LCD_PIN_BK_LIGHT, CONFIG_TEST_NODE_LCD_BK_LIGHT_ON_LEVEL);
    }

    ESP_LOGI(
        TAG,
        "LCD cfg: rgb=%s swap_xy=%d mirror_x=%d mirror_y=%d invert=%d swap_bytes=%d pclk=%d qdepth=%d single_buf=%d",
        CONFIG_TEST_NODE_LCD_RGB_ORDER_BGR ? "BGR" : "RGB",
        CONFIG_TEST_NODE_LCD_SWAP_XY,
        CONFIG_TEST_NODE_LCD_MIRROR_X,
        CONFIG_TEST_NODE_LCD_MIRROR_Y,
        CONFIG_TEST_NODE_LCD_INVERT_COLORS,
        TEST_NODE_LCD_SWAP_COLOR_BYTES,
        CONFIG_TEST_NODE_LCD_PIXEL_CLOCK_HZ,
        CONFIG_TEST_NODE_LCD_IO_QUEUE_DEPTH,
        TEST_NODE_LCD_SINGLE_BUFFER
    );

    return ESP_OK;
}

static void *ui_dma_alloc(size_t size_bytes) {
    void *buf = spi_bus_dma_memory_alloc(LCD_HOST, size_bytes, 0);
    if (!buf) {
        buf = heap_caps_malloc(size_bytes, MALLOC_CAP_DMA | MALLOC_CAP_INTERNAL);
    }
    if (!buf) {
        buf = heap_caps_malloc(size_bytes, MALLOC_CAP_DMA);
    }
    return buf;
}

static int32_t ui_effective_line_height(void) {
    int32_t line_h = lv_font_get_line_height(UI_FONT_SMALL);
    return (line_h < 8) ? 12 : line_h;
}

static void ui_style_label(lv_obj_t *label, lv_color_t color) {
    lv_obj_set_style_text_font(label, UI_FONT_SMALL, 0);
    lv_obj_set_style_text_color(label, color, 0);
    lv_obj_set_style_text_opa(label, LV_OPA_COVER, 0);
}

static void ui_style_panel(
    lv_obj_t *panel,
    lv_color_t bg_color,
    lv_color_t border_color,
    uint8_t border_width,
    uint8_t radius,
    uint8_t pad
) {
    lv_obj_clear_flag(panel, LV_OBJ_FLAG_SCROLLABLE);
    lv_obj_set_style_bg_color(panel, bg_color, 0);
    lv_obj_set_style_bg_opa(panel, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(panel, border_color, 0);
    lv_obj_set_style_border_width(panel, border_width, 0);
    lv_obj_set_style_radius(panel, radius, 0);
    lv_obj_set_style_pad_all(panel, pad, 0);
}

static esp_err_t init_lvgl(void) {
    esp_err_t err;
    size_t buffer_pixels = (size_t)(CONFIG_TEST_NODE_LCD_H_RES * CONFIG_TEST_NODE_LCD_BUFFER_LINES);
    size_t buffer_size_bytes = buffer_pixels * sizeof(lv_color_t);
    const esp_lcd_panel_io_callbacks_t panel_io_cbs = {
        .on_color_trans_done = panel_io_color_trans_done,
    };

    lv_init();

    if (!s_lvgl_tick_timer) {
        const esp_timer_create_args_t lvgl_tick_timer_args = {
            .callback = lvgl_tick_timer_cb,
            .name = "lvgl_tick",
        };
        err = esp_timer_create(&lvgl_tick_timer_args, &s_lvgl_tick_timer);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "esp_timer_create(lvgl_tick) failed: %s", esp_err_to_name(err));
            return err;
        }
        err = esp_timer_start_periodic(s_lvgl_tick_timer, LVGL_TICK_PERIOD_MS * 1000);
        if (err != ESP_OK) {
            ESP_LOGE(TAG, "esp_timer_start_periodic(lvgl_tick) failed: %s", esp_err_to_name(err));
            (void)esp_timer_delete(s_lvgl_tick_timer);
            s_lvgl_tick_timer = NULL;
            return err;
        }
    }

    s_buf_a = ui_dma_alloc(buffer_size_bytes);
    if (!s_buf_a) {
        ESP_LOGE(TAG, "LVGL draw buffer A alloc failed");
        return ESP_ERR_NO_MEM;
    }
    memset(s_buf_a, 0, buffer_size_bytes);

#if TEST_NODE_LCD_SINGLE_BUFFER
    s_buf_b = NULL;
#else
    s_buf_b = ui_dma_alloc(buffer_size_bytes);
#endif

    if (!TEST_NODE_LCD_SINGLE_BUFFER && !s_buf_b) {
        ESP_LOGE(TAG, "LVGL draw buffer B alloc failed");
        if (s_buf_a) {
            free(s_buf_a);
            s_buf_a = NULL;
        }
        return ESP_ERR_NO_MEM;
    }
    if (s_buf_b) {
        memset(s_buf_b, 0, buffer_size_bytes);
    }

    s_lv_display = lv_display_create(CONFIG_TEST_NODE_LCD_H_RES, CONFIG_TEST_NODE_LCD_V_RES);
    if (!s_lv_display) {
        ESP_LOGE(TAG, "lv_display_create failed");
        free(s_buf_a);
        free(s_buf_b);
        s_buf_a = NULL;
        s_buf_b = NULL;
        return ESP_FAIL;
    }
    lv_display_set_default(s_lv_display);
    lv_display_set_color_format(s_lv_display, LV_COLOR_FORMAT_RGB565);
    lv_display_set_buffers(
        s_lv_display,
        s_buf_a,
        s_buf_b,
        buffer_size_bytes,
        LV_DISPLAY_RENDER_MODE_PARTIAL
    );
    lv_display_set_user_data(s_lv_display, s_panel_handle);
    lv_display_set_flush_cb(s_lv_display, lvgl_flush_cb);
    ESP_RETURN_ON_ERROR(
        esp_lcd_panel_io_register_event_callbacks(s_panel_io, &panel_io_cbs, s_lv_display),
        TAG,
        "panel_io callbacks registration failed"
    );

    s_encoder_indev = lv_indev_create();
    if (!s_encoder_indev) {
        ESP_LOGE(TAG, "lv_indev_create failed");
        lv_display_delete(s_lv_display);
        s_lv_display = NULL;
        free(s_buf_a);
        free(s_buf_b);
        s_buf_a = NULL;
        s_buf_b = NULL;
        return ESP_FAIL;
    }
    lv_indev_set_type(s_encoder_indev, LV_INDEV_TYPE_ENCODER);
    lv_indev_set_read_cb(s_encoder_indev, encoder_read_cb);
    lv_indev_set_display(s_encoder_indev, s_lv_display);

    lv_obj_set_style_bg_color(lv_scr_act(), lv_color_hex(UI_COLOR_BG_MAIN), 0);
    lv_obj_set_style_bg_opa(lv_scr_act(), LV_OPA_COVER, 0);
    lv_obj_set_style_border_width(lv_scr_act(), 0, 0);
    lv_obj_set_style_pad_all(lv_scr_act(), 0, 0);
    lv_obj_clear_flag(lv_scr_act(), LV_OBJ_FLAG_SCROLLABLE);

    s_wifi_label = lv_label_create(lv_scr_act());
    ui_style_label(s_wifi_label, lv_color_hex(UI_COLOR_ACCENT_INFO));
    lv_obj_align(s_wifi_label, LV_ALIGN_TOP_LEFT, 6, 4);
    lv_obj_set_style_bg_opa(s_wifi_label, LV_OPA_20, 0);
    lv_obj_set_style_bg_color(s_wifi_label, lv_color_hex(0x113141), 0);
    lv_obj_set_style_pad_hor(s_wifi_label, 4, 0);
    lv_obj_set_style_pad_ver(s_wifi_label, 1, 0);

    s_mqtt_label = lv_label_create(lv_scr_act());
    ui_style_label(s_mqtt_label, lv_color_hex(UI_COLOR_ACCENT_OK));
    lv_obj_align(s_mqtt_label, LV_ALIGN_TOP_RIGHT, -6, 4);
    lv_obj_set_style_bg_opa(s_mqtt_label, LV_OPA_20, 0);
    lv_obj_set_style_bg_color(s_mqtt_label, lv_color_hex(0x123629), 0);
    lv_obj_set_style_pad_hor(s_mqtt_label, 4, 0);
    lv_obj_set_style_pad_ver(s_mqtt_label, 1, 0);

    s_mode_label = lv_label_create(lv_scr_act());
    ui_style_label(s_mode_label, lv_color_hex(UI_COLOR_ACCENT_WARN));
    lv_obj_set_style_bg_opa(s_mode_label, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(s_mode_label, lv_color_hex(0x2A2A2A), 0);
    lv_obj_set_style_pad_left(s_mode_label, 6, 0);
    lv_obj_set_style_pad_right(s_mode_label, 6, 0);
    lv_obj_set_style_pad_top(s_mode_label, 2, 0);
    lv_obj_set_style_pad_bottom(s_mode_label, 2, 0);
    lv_obj_align(s_mode_label, LV_ALIGN_TOP_MID, 0, 22);

    s_diag_label = lv_label_create(lv_scr_act());
    ui_style_label(s_diag_label, lv_color_hex(UI_COLOR_ACCENT_WARN));
    lv_obj_align(s_diag_label, LV_ALIGN_TOP_MID, 0, 4);

    s_diag_big_label = lv_label_create(lv_scr_act());
    ui_style_label(s_diag_big_label, lv_color_hex(UI_COLOR_ACCENT_WARN));
    lv_obj_set_style_bg_opa(s_diag_big_label, LV_OPA_COVER, 0);
    lv_obj_set_style_bg_color(s_diag_big_label, lv_color_hex(0x4A2B1D), 0);
    lv_obj_set_style_pad_left(s_diag_big_label, 4, 0);
    lv_obj_set_style_pad_right(s_diag_big_label, 4, 0);
    lv_obj_set_style_pad_top(s_diag_big_label, 2, 0);
    lv_obj_set_style_pad_bottom(s_diag_big_label, 2, 0);
    lv_obj_align(s_diag_big_label, LV_ALIGN_CENTER, 0, -4);

    s_nodes_box = lv_obj_create(lv_scr_act());
    lv_obj_set_size(s_nodes_box, CONFIG_TEST_NODE_LCD_H_RES - 8, 98);
    lv_obj_align(s_nodes_box, LV_ALIGN_TOP_MID, 0, 20);
    ui_style_panel(
        s_nodes_box,
        lv_color_hex(UI_COLOR_PANEL_NODES),
        lv_color_hex(UI_COLOR_BORDER_NODES),
        2,
        5,
        4
    );

    {
        int32_t line_h = ui_effective_line_height();
        int32_t line_step = line_h + 1;
        int32_t line_w = CONFIG_TEST_NODE_LCD_H_RES - 8 - (4 * 2);
        int32_t left_w = line_w - 46;
        size_t i;

        s_nodes_rows_count = UI_EXPECTED_VISIBLE_NODES;
        if (s_nodes_rows_count > UI_MAX_NODES) {
            s_nodes_rows_count = UI_MAX_NODES;
        }

        if (left_w < 60) {
            left_w = line_w;
        }

        for (i = 0; i < s_nodes_rows_count; i++) {
            s_nodes_label_rows[i] = lv_label_create(s_nodes_box);
            ui_style_label(s_nodes_label_rows[i], lv_color_hex(UI_COLOR_TEXT_PRIMARY));
            lv_obj_set_width(s_nodes_label_rows[i], left_w);
            lv_label_set_long_mode(s_nodes_label_rows[i], LV_LABEL_LONG_CLIP);
            lv_obj_align(s_nodes_label_rows[i], LV_ALIGN_TOP_LEFT, 0, (int32_t)(i * line_step));
            s_nodes_row_text_buf[i][0] = '\0';
            lv_label_set_text(s_nodes_label_rows[i], s_nodes_row_text_buf[i]);

            s_nodes_state_rows[i] = lv_label_create(s_nodes_box);
            ui_style_label(s_nodes_state_rows[i], lv_color_hex(UI_COLOR_ACCENT_INFO));
            lv_obj_align(s_nodes_state_rows[i], LV_ALIGN_TOP_RIGHT, 0, (int32_t)(i * line_step));
            s_nodes_state_text_buf[i][0] = '\0';
            lv_label_set_text(s_nodes_state_rows[i], s_nodes_state_text_buf[i]);
        }
    }

    s_setup_box = lv_obj_create(lv_scr_act());
    lv_obj_set_size(s_setup_box, CONFIG_TEST_NODE_LCD_H_RES - 8, 98);
    lv_obj_align(s_setup_box, LV_ALIGN_TOP_MID, 0, 20);
    ui_style_panel(
        s_setup_box,
        lv_color_hex(UI_COLOR_PANEL_SETUP),
        lv_color_hex(UI_COLOR_BORDER_SETUP),
        2,
        5,
        6
    );
    lv_obj_set_flex_flow(s_setup_box, LV_FLEX_FLOW_COLUMN);
    lv_obj_set_flex_align(s_setup_box, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START, LV_FLEX_ALIGN_START);
    lv_obj_set_style_pad_row(s_setup_box, 4, 0);

    s_setup_title = lv_label_create(s_setup_box);
    ui_style_label(s_setup_title, lv_color_hex(UI_COLOR_ACCENT_WARN));

    s_setup_details = lv_label_create(s_setup_box);
    ui_style_label(s_setup_details, lv_color_hex(UI_COLOR_TEXT_PRIMARY));
    lv_obj_set_width(s_setup_details, lv_obj_get_width(s_setup_box) - 2);
    lv_label_set_long_mode(s_setup_details, LV_LABEL_LONG_WRAP);
    lv_obj_set_style_text_line_space(s_setup_details, 2, 0);
    lv_obj_add_flag(s_setup_box, LV_OBJ_FLAG_HIDDEN);

    s_settings_menu = lv_menu_create(lv_scr_act());
    lv_obj_set_size(s_settings_menu, CONFIG_TEST_NODE_LCD_H_RES - 8, CONFIG_TEST_NODE_LCD_V_RES - 56);
    lv_obj_align(s_settings_menu, LV_ALIGN_CENTER, 0, 8);
    lv_obj_set_style_bg_color(s_settings_menu, lv_color_hex(0x1A130C), 0);
    lv_obj_set_style_bg_opa(s_settings_menu, LV_OPA_COVER, 0);
    lv_obj_set_style_border_color(s_settings_menu, lv_color_hex(0xE1B96D), 0);
    lv_obj_set_style_border_width(s_settings_menu, 2, 0);
    lv_obj_set_style_radius(s_settings_menu, 4, 0);
    lv_obj_add_flag(s_settings_menu, LV_OBJ_FLAG_HIDDEN);
    lv_menu_set_mode_header(s_settings_menu, LV_MENU_HEADER_TOP_FIXED);
    lv_menu_set_mode_root_back_button(s_settings_menu, LV_MENU_ROOT_BACK_BUTTON_DISABLED);
    lv_obj_set_style_text_font(s_settings_menu, UI_FONT_SMALL, LV_PART_MAIN);
    lv_obj_set_style_text_color(s_settings_menu, lv_color_hex(UI_COLOR_TEXT_PRIMARY), LV_PART_MAIN);
    lv_obj_set_style_pad_row(s_settings_menu, 2, LV_PART_MAIN);

    s_settings_page_main = lv_menu_page_create(s_settings_menu, "SETTINGS");
    {
        lv_obj_t *section = lv_menu_section_create(s_settings_page_main);
        lv_obj_t *label = NULL;

        s_settings_cont_back = lv_menu_cont_create(section);
        label = lv_label_create(s_settings_cont_back);
        lv_label_set_text(label, "0) Back");

        s_settings_cont_reset_zones = lv_menu_cont_create(section);
        label = lv_label_create(s_settings_cont_reset_zones);
        lv_label_set_text(label, "1) Reset zones to default");

        s_settings_cont_factory_reset = lv_menu_cont_create(section);
        label = lv_label_create(s_settings_cont_factory_reset);
        lv_label_set_text(label, "2) Full reset (erase all config)");

        {
            lv_obj_t *hint_cont = lv_menu_cont_create(section);
            s_settings_hint_label = lv_label_create(hint_cont);
            lv_label_set_text(s_settings_hint_label, "Click: apply  Hold 3s: close");
            lv_obj_set_style_text_color(s_settings_hint_label, lv_color_hex(UI_COLOR_TEXT_DIM), 0);
        }
    }
    lv_menu_set_page(s_settings_menu, s_settings_page_main);

    s_log_box = lv_obj_create(lv_scr_act());
    lv_obj_set_size(s_log_box, CONFIG_TEST_NODE_LCD_H_RES - 8, 188);
    lv_obj_align(s_log_box, LV_ALIGN_BOTTOM_MID, 0, -2);
    ui_style_panel(
        s_log_box,
        lv_color_hex(UI_COLOR_PANEL_LOG),
        lv_color_hex(UI_COLOR_BORDER_LOG),
        2,
        5,
        4
    );

    s_log_title = lv_label_create(s_log_box);
    ui_style_label(s_log_title, lv_color_hex(UI_COLOR_ACCENT_INFO));
    lv_obj_align(s_log_title, LV_ALIGN_TOP_LEFT, 0, 0);

    {
        int32_t line_h = ui_effective_line_height();
        int32_t line_step = line_h + 1;
        int32_t line_w = CONFIG_TEST_NODE_LCD_H_RES - 8 - (4 * 2);
        size_t i;

        s_log_rows_count = UI_EXPECTED_VISIBLE_LOG_ROWS;
        if (s_log_rows_count > UI_LOG_VISIBLE_LINES) {
            s_log_rows_count = UI_LOG_VISIBLE_LINES;
        }

        for (i = 0; i < s_log_rows_count; i++) {
            s_log_label_rows[i] = lv_label_create(s_log_box);
            ui_style_label(s_log_label_rows[i], lv_color_hex(UI_COLOR_TEXT_PRIMARY));
            lv_obj_set_width(s_log_label_rows[i], line_w);
            lv_label_set_long_mode(s_log_label_rows[i], LV_LABEL_LONG_CLIP);
            lv_obj_align(s_log_label_rows[i], LV_ALIGN_TOP_LEFT, 0, line_h + 4 + ((int32_t)i * line_step));
            s_log_row_text_buf[i][0] = '\0';
            lv_label_set_text(s_log_label_rows[i], s_log_row_text_buf[i]);
        }
    }

    ui_refresh_status_labels();
    ui_refresh_nodes_label();
    ui_refresh_log_label();
    ui_refresh_setup_box();
    ui_refresh_settings_menu();
    lv_obj_invalidate(lv_scr_act());
    lv_refr_now(s_lv_display);

    return ESP_OK;
}

static void lvgl_task(void *arg) {
    uint32_t blink_update_ms = 0;
    (void)arg;

    while (1) {
        ui_process_queue();
        lv_timer_handler();

        blink_update_ms += LVGL_TASK_PERIOD_MS;
        if (blink_update_ms >= UI_BLINK_INTERVAL_MS) {
            blink_update_ms = 0;
            ui_tick_blink();
        }

#if UI_DEBUG_DUMP_PERIOD_MS > 0
        {
            static uint32_t dbg_elapsed_ms = 0;
            dbg_elapsed_ms += LVGL_TASK_PERIOD_MS;
            if (dbg_elapsed_ms >= UI_DEBUG_DUMP_PERIOD_MS) {
                dbg_elapsed_ms = 0;
                ui_debug_dump_state();
            }
        }
#endif

        vTaskDelay(pdMS_TO_TICKS(LVGL_TASK_PERIOD_MS));
    }
}

static void ui_cleanup_init_resources(void) {
    size_t i;

    if (s_lvgl_task_handle) {
        vTaskDelete(s_lvgl_task_handle);
        s_lvgl_task_handle = NULL;
    }

    if (s_lvgl_tick_timer) {
        (void)esp_timer_stop(s_lvgl_tick_timer);
        (void)esp_timer_delete(s_lvgl_tick_timer);
        s_lvgl_tick_timer = NULL;
    }

    if (s_encoder_indev) {
        lv_indev_delete(s_encoder_indev);
        s_encoder_indev = NULL;
    }

    if (s_lv_display) {
        lv_display_delete(s_lv_display);
        s_lv_display = NULL;
    }

    if (s_buf_a) {
        free(s_buf_a);
        s_buf_a = NULL;
    }
    if (s_buf_b) {
        free(s_buf_b);
        s_buf_b = NULL;
    }

    if (s_event_queue_hp) {
        vQueueDelete(s_event_queue_hp);
        s_event_queue_hp = NULL;
    }
    if (s_event_queue_log) {
        vQueueDelete(s_event_queue_log);
        s_event_queue_log = NULL;
    }

    if (s_panel_handle) {
        (void)esp_lcd_panel_del(s_panel_handle);
        s_panel_handle = NULL;
    }
    if (s_panel_io) {
        (void)esp_lcd_panel_io_del(s_panel_io);
        s_panel_io = NULL;
    }
    (void)spi_bus_free(LCD_HOST);

    (void)gpio_isr_handler_remove(CONFIG_TEST_NODE_ENCODER_PIN_A);
    (void)gpio_isr_handler_remove(CONFIG_TEST_NODE_ENCODER_PIN_B);

    s_wifi_label = NULL;
    s_mqtt_label = NULL;
    s_mode_label = NULL;
    s_diag_label = NULL;
    s_diag_big_label = NULL;
    s_nodes_box = NULL;
    s_log_box = NULL;
    s_log_title = NULL;
    s_setup_box = NULL;
    s_setup_title = NULL;
    s_setup_details = NULL;
    s_settings_menu = NULL;
    s_settings_page_main = NULL;
    s_settings_cont_back = NULL;
    s_settings_cont_reset_zones = NULL;
    s_settings_cont_factory_reset = NULL;
    s_settings_hint_label = NULL;
    s_nodes_rows_count = UI_MAX_NODES;
    s_log_rows_count = UI_LOG_VISIBLE_LINES;
    for (i = 0; i < UI_MAX_NODES; i++) {
        s_nodes_label_rows[i] = NULL;
        s_nodes_state_rows[i] = NULL;
    }
    for (i = 0; i < UI_LOG_VISIBLE_LINES; i++) {
        s_log_label_rows[i] = NULL;
    }
}

esp_err_t test_node_ui_init(void) {
    esp_err_t err;
    int lvgl_task_core = 0;

    s_boot_us = esp_timer_get_time();

    ESP_LOGI(
        TAG,
        "UI init: ILI9341 pins [SCLK=%d MOSI=%d MISO=%d DC=%d RST=%d CS=%d BL=%d], encoder [A=%d B=%d SW=%d]",
        CONFIG_TEST_NODE_LCD_PIN_SCLK,
        CONFIG_TEST_NODE_LCD_PIN_MOSI,
        CONFIG_TEST_NODE_LCD_PIN_MISO,
        CONFIG_TEST_NODE_LCD_PIN_DC,
        CONFIG_TEST_NODE_LCD_PIN_RST,
        CONFIG_TEST_NODE_LCD_PIN_CS,
        CONFIG_TEST_NODE_LCD_PIN_BK_LIGHT,
        CONFIG_TEST_NODE_ENCODER_PIN_A,
        CONFIG_TEST_NODE_ENCODER_PIN_B,
        CONFIG_TEST_NODE_ENCODER_PIN_SW
    );

    init_encoder_gpio();

    err = init_lcd_panel();
    if (err != ESP_OK) {
        ui_cleanup_init_resources();
        return err;
    }

    s_event_queue_hp = xQueueCreate(UI_EVENT_QUEUE_LEN, sizeof(ui_event_msg_t));
    s_event_queue_log = xQueueCreate(UI_LOG_EVENT_QUEUE_LEN, sizeof(ui_event_msg_t));
    if (!s_event_queue_hp || !s_event_queue_log) {
        ESP_LOGE(TAG, "Failed to create UI event queues");
        ui_cleanup_init_resources();
        return ESP_ERR_NO_MEM;
    }
    ESP_LOGI(
        TAG,
        "UI queues allocated: msg=%uB hp=%u (~%uB) log=%u (~%uB), heap=%u",
        (unsigned)sizeof(ui_event_msg_t),
        (unsigned)UI_EVENT_QUEUE_LEN,
        (unsigned)(UI_EVENT_QUEUE_LEN * sizeof(ui_event_msg_t)),
        (unsigned)UI_LOG_EVENT_QUEUE_LEN,
        (unsigned)(UI_LOG_EVENT_QUEUE_LEN * sizeof(ui_event_msg_t)),
        (unsigned)esp_get_free_heap_size()
    );

    err = init_lvgl();
    if (err != ESP_OK) {
        ui_cleanup_init_resources();
        return err;
    }

    ui_append_log_line(NULL, "display initialized");
    ui_append_log_line(NULL, "terminal ready");

    #if CONFIG_FREERTOS_UNICORE
    BaseType_t lvgl_task_ok = xTaskCreate(
        lvgl_task,
        "lvgl_task",
        LVGL_TASK_STACK_SIZE,
        NULL,
        LVGL_TASK_PRIORITY,
        &s_lvgl_task_handle
    );
    #else
    lvgl_task_core = xPortGetCoreID();
    if (lvgl_task_core < 0 || lvgl_task_core >= portNUM_PROCESSORS) {
        lvgl_task_core = 0;
    }
    ESP_LOGI(TAG, "LVGL task pin core=%d (same as init core)", lvgl_task_core);
    BaseType_t lvgl_task_ok = xTaskCreatePinnedToCore(
        lvgl_task,
        "lvgl_task",
        LVGL_TASK_STACK_SIZE,
        NULL,
        LVGL_TASK_PRIORITY,
        &s_lvgl_task_handle,
        lvgl_task_core
    );
    if (lvgl_task_ok != pdPASS) {
        lvgl_task_ok = xTaskCreate(
            lvgl_task,
            "lvgl_task",
            LVGL_TASK_STACK_SIZE,
            NULL,
            LVGL_TASK_PRIORITY,
            &s_lvgl_task_handle
        );
    }
    #endif

    if (lvgl_task_ok != pdPASS) {
        ESP_LOGE(TAG, "xTaskCreate(lvgl_task) failed");
        ui_cleanup_init_resources();
        return ESP_ERR_NO_MEM;
    }

    ESP_LOGI(TAG, "UI ready (uptime base=%" PRId64 "us)", s_boot_us);
    return ESP_OK;
}

void test_node_ui_show_step(const char *step) {
    if (!step || step[0] == '\0') {
        return;
    }
    ESP_LOGI(TAG, "UI step: %s", step);
    ui_enqueue_event(UI_EVENT_STEP, NULL, step, NULL, false);
}

void test_node_ui_log_event(const char *node_uid, const char *message) {
    if (!message || message[0] == '\0') {
        return;
    }
    ui_enqueue_event(UI_EVENT_LOG, node_uid, message, NULL, false);
}

void test_node_ui_set_wifi_status(bool connected, const char *status_text) {
    ui_enqueue_event(UI_EVENT_WIFI_STATUS, NULL, status_text, NULL, connected);
}

void test_node_ui_set_mqtt_status(bool connected, const char *status_text) {
    ui_enqueue_event(UI_EVENT_MQTT_STATUS, NULL, status_text, NULL, connected);
}

void test_node_ui_set_mode(const char *mode) {
    ui_enqueue_event(UI_EVENT_MODE, NULL, mode, NULL, false);
}

void test_node_ui_set_setup_info(const char *ssid, const char *password_text, const char *pin) {
    ui_enqueue_event(UI_EVENT_SETUP_INFO, ssid, password_text, pin, false);
}

void test_node_ui_register_settings_action_cb(test_node_ui_settings_action_cb_t cb, void *user_ctx) {
    s_settings_action_cb = cb;
    s_settings_action_user_ctx = user_ctx;
}

void test_node_ui_register_node(const char *node_uid, const char *zone_uid) {
    if (!node_uid || node_uid[0] == '\0') {
        return;
    }
    ui_enqueue_event(UI_EVENT_NODE_REGISTER, node_uid, zone_uid, NULL, false);
}

void test_node_ui_set_node_zone(const char *node_uid, const char *zone_uid) {
    if (!node_uid || node_uid[0] == '\0') {
        return;
    }
    ui_enqueue_event(UI_EVENT_NODE_ZONE, node_uid, zone_uid, NULL, false);
}

void test_node_ui_mark_node_heartbeat(const char *node_uid) {
    if (!node_uid || node_uid[0] == '\0') {
        return;
    }
    ui_enqueue_event(UI_EVENT_NODE_HEARTBEAT, node_uid, NULL, NULL, false);
}

void test_node_ui_mark_node_lwt(const char *node_uid) {
    if (!node_uid || node_uid[0] == '\0') {
        return;
    }
    ui_enqueue_event(UI_EVENT_NODE_LWT, node_uid, NULL, NULL, false);
}

void test_node_ui_set_node_status(const char *node_uid, const char *status) {
    if (!node_uid || node_uid[0] == '\0') {
        return;
    }
    ui_enqueue_event(UI_EVENT_NODE_STATUS, node_uid, status, NULL, false);
}

#else

esp_err_t test_node_ui_init(void) {
    ESP_LOGI(TAG, "Local UI disabled by CONFIG_TEST_NODE_UI_ENABLE");
    return ESP_OK;
}

void test_node_ui_show_step(const char *step) {
    (void)step;
}

void test_node_ui_log_event(const char *node_uid, const char *message) {
    (void)node_uid;
    (void)message;
}

void test_node_ui_set_wifi_status(bool connected, const char *status_text) {
    (void)connected;
    (void)status_text;
}

void test_node_ui_set_mqtt_status(bool connected, const char *status_text) {
    (void)connected;
    (void)status_text;
}

void test_node_ui_set_mode(const char *mode) {
    (void)mode;
}

void test_node_ui_set_setup_info(const char *ssid, const char *password_text, const char *pin) {
    (void)ssid;
    (void)password_text;
    (void)pin;
}

void test_node_ui_register_settings_action_cb(test_node_ui_settings_action_cb_t cb, void *user_ctx) {
    (void)cb;
    (void)user_ctx;
}

void test_node_ui_register_node(const char *node_uid, const char *zone_uid) {
    (void)node_uid;
    (void)zone_uid;
}

void test_node_ui_set_node_zone(const char *node_uid, const char *zone_uid) {
    (void)node_uid;
    (void)zone_uid;
}

void test_node_ui_mark_node_heartbeat(const char *node_uid) {
    (void)node_uid;
}

void test_node_ui_mark_node_lwt(const char *node_uid) {
    (void)node_uid;
}

void test_node_ui_set_node_status(const char *node_uid, const char *status) {
    (void)node_uid;
    (void)status;
}

#endif
