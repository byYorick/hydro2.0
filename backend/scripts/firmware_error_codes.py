"""Извлечение и кураторский manifest error_code прошивок / MQTT command_response (фаза 5)."""

from __future__ import annotations

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
FIRMWARE = ROOT / "firmware"
DOC_MQTT = ROOT / "doc_ai" / "03_TRANSPORT_MQTT"

# (code, title, message, category)
# category: security | framework | pump | relay | irrigation | diagnostics
FIRMWARE_ERROR_MANIFEST: list[tuple[str, str, str, str]] = [
    # --- Security / HMAC (node_command_handler.c) ---
    ("invalid_command_format", "Некорректный формат команды", "Тело команды не соответствует протоколу hydro.", "framework"),
    ("invalid_hmac_format", "Некорректный HMAC", "Поля ts/sig отсутствуют или заданы частично.", "security"),
    ("hmac_required", "Требуется HMAC", "Команда отклонена: для узла включена обязательная подпись HMAC.", "security"),
    ("missing_node_secret", "Нет node_secret", "В NodeConfig отсутствует node_secret для проверки подписи.", "security"),
    ("time_not_synced", "Время не синхронизировано", "Узел ещё не получил время от брокера — команда с ts отклонена.", "security"),
    ("invalid_signature", "Неверная подпись", "HMAC-подпись команды не прошла проверку.", "security"),
    ("timestamp_expired", "Истёк timestamp", "Метка времени команды вне допустимого окна (±10 с).", "security"),
    ("command_already_failed", "Команда уже завершена с ошибкой", "Повторный ответ по cmd_id после terminal ERROR.", "framework"),
    # --- Pump / INA209 ---
    ("pump_error", "Ошибка насоса", "Общая ошибка драйвера насоса.", "pump"),
    ("pump_driver_failed", "Ошибка драйвера насоса", "Драйвер насоса не выполнил команду.", "pump"),
    ("pump_busy", "Насос занят", "Канал насоса занят предыдущей операцией.", "pump"),
    ("cooldown_active", "Cooldown насоса", "Команда отклонена: активна защитная пауза между включениями.", "pump"),
    ("current_unavailable", "Ток недоступен", "Не удалось получить показание тока (INA209/I²C).", "pump"),
    ("current_not_detected", "Ток не обнаружен", "После включения насоса ток ниже минимального порога.", "pump"),
    ("overcurrent", "Сверхток", "Ток канала превысил допустимый верхний предел.", "pump"),
    ("pump_current_over_range", "Ток насоса выше нормы", "Ток насоса выше допустимого диапазона NodeConfig.", "pump"),
    ("pump_current_under_range", "Ток насоса ниже нормы", "Ток насоса ниже ожидаемого при работе (недоток).", "pump"),
    ("pump_ina_read_failed", "Ошибка чтения INA209", "Не удалось прочитать ток с датчика INA209.", "pump"),
    ("pump_in_cooldown", "Насос в cooldown", "Команда отклонена: канал насоса в интервале cooldown.", "pump"),
    ("pump_interlock_blocked", "Interlock насоса", "Команда заблокирована гидравлическим interlock (flow-path).", "irrigation"),
    # --- Relay ---
    ("relay_gpio_error", "Ошибка GPIO реле", "Ошибка GPIO при переключении реле.", "relay"),
    ("relay_not_initialized", "Реле не инициализировано", "Драйвер реле не инициализирован.", "relay"),
    ("relay_invalid_channel", "Неверный канал реле", "Указан недопустимый канал реле.", "relay"),
    ("relay_channel_not_found", "Канал реле не найден", "Канал реле отсутствует в NodeConfig.", "relay"),
    ("relay_mutex_timeout", "Таймаут реле", "Не удалось захватить mutex реле за отведённое время.", "relay"),
    ("relay_error", "Ошибка реле", "Команда реле завершилась с ошибкой.", "relay"),
    # --- Actuator / IRR node ---
    ("actuator_apply_failed", "Ошибка исполнительного канала", "Не удалось применить команду к исполнительному каналу.", "irrigation"),
    ("actuator_busy", "Исполнительный канал занят", "Канал занят — команда отклонена (BUSY).", "irrigation"),
    ("stage_timeout", "Таймаут стадии", "Истекло время stage-guard (pump_main timeout_ms).", "irrigation"),
    ("clean_fill_source_empty", "Нет воды для чистого бака", "При наполнении чистого бака нижний датчик уровня не сработал.", "irrigation"),
    ("clean_fill_completed", "Наполнение чистого бака завершено", "Чистый бак наполнен (level_clean_max).", "irrigation"),
    ("clean_tank_not_filled_timeout", "Таймаут наполнения чистого бака", "Чистый бак не наполнился за отведённое время.", "irrigation"),
    ("clean_fill_timeout", "Таймаут clean fill", "Этап наполнения чистого бака превысил лимит времени.", "irrigation"),
    ("solution_fill_source_empty", "Нет воды для раствора", "При наполнении раствора не хватает воды в чистом баке.", "irrigation"),
    ("solution_fill_leak_detected", "Утечка при наполнении раствора", "Нижний уровень раствора пропал после guard-delay.", "irrigation"),
    ("solution_fill_completed", "Наполнение раствора завершено", "Бак раствора наполнен (level_solution_max).", "irrigation"),
    ("solution_tank_not_filled_timeout", "Таймаут бака раствора", "Бак раствора не наполнился за отведённое время.", "irrigation"),
    ("solution_fill_timeout", "Таймаут solution fill", "Этап наполнения раствора превысил лимит времени.", "irrigation"),
    ("prepare_recirculation_timeout", "Таймаут prepare-recirculation", "Подготовка рециркуляции превысила timeout_ms.", "irrigation"),
    ("recirculation_solution_low", "Низкий уровень при рециркуляции", "Уровень раствора ниже минимума при подготовке рециркуляции.", "irrigation"),
    ("emergency_stop_activated", "Аварийный останов (E-STOP)", "На узле активирован аварийный останов.", "irrigation"),
    # --- Node framework / sim ---
    ("invalid_json", "Некорректный JSON", "Тело MQTT-сообщения содержит некорректный JSON.", "framework"),
    ("unsupported_channel_cmd", "Команда не поддерживается", "Канал не поддерживает запрошенную команду.", "framework"),
    ("invalid_params_format", "Некорректные параметры", "Параметры команды не прошли проверку формата.", "framework"),
    ("node_not_activated", "Узел не активирован", "Команда отклонена: узел не активирован в системе.", "framework"),
    ("unsupported_correction_command", "Коррекция не поддерживается", "Канал не поддерживает correction-команду.", "framework"),
    ("set_time_failed", "Не удалось установить время", "Узел не применил системное время (set_time).", "framework"),
    ("config_report_failed", "Ошибка config_report", "Узел не смог опубликовать config_report.", "framework"),
    ("restart_schedule_failed", "Ошибка перезапуска", "Не удалось запланировать перезапуск узла.", "framework"),
    # --- Diagnostics MQTT (node_state_manager) ---
    ("motor_error", "Ошибка мотора", "Ошибка привода/мотора на узле.", "diagnostics"),
    # --- ESP-IDF diagnostics (MQTT diagnostics/error) ---
    ("esp_esp_err_invalid_state", "Некорректное состояние ESP", "Узел в недопустимом состоянии для операции (ESP_ERR_INVALID_STATE).", "diagnostics"),
]

# Однословные коды без подчёркивания, допустимые в прошивке
SINGLE_WORD_FIRMWARE_CODES: frozenset[str] = frozenset({"overcurrent"})

FIRMWARE_CODE_DENYLIST: frozenset[str] = frozenset({
    "unknown",
    "default",
    "auto",
    "climate",
    "light",
    "pump",
    "relay",
    "irrig",
    "pump_main",
    "pump_acid",
    "pump_base",
    "node_secret",
    "allow_legacy_hmac",
    "node_command_handler",
    "ec_sensor",
    "ph_sensor",
    "config_storage",
    "wifi_manager",
    "i2c_bus",
    "pump_driver",
    "oled_ui",
    "mqtt_manager",
    "node_framework",
    "finalize",
    "wifi",
    "mqtt",
    "emergency_stop",
    "infra_overcurrent",
    "solution_temp_c",
    "clean_fill_min_check_delay_ms",
    "solution_fill_clean_min_check_delay_ms",
    "solution_fill_solution_min_check_delay_ms",
    # Python / pytest / logging ложные срабатывания
    "abcd",
    "asyncio",
    "bytes",
    "count",
    "empty",
    "error",
    "false",
    "global",
    "i386",
    "post",
    "progress",
    "skipped",
    "times",
    "true",
    "xfailed",
    "xpassed",
    "pump_bus_current",
})

_EXTRACT_PATTERNS = (
    re.compile(r'(?:error_code\s*=\s*|\*out_error_code\s*=\s*|\*error_code_out\s*=\s*)"([a-z][a-z0-9_]*)"'),
    re.compile(r'"error_code":\s*"([a-zA-Z0-9_]+)"'),
)

_FIRMWARE_RETURN_PATTERN = re.compile(r'return\s+"([a-z][a-z0-9_]{3,60})"')


def normalize_code(raw: str) -> str:
    return re.sub(r"[^a-z0-9_]", "_", raw.strip().lower()).strip("_")


_MANIFEST_CODES: frozenset[str] = frozenset(normalize_code(row[0]) for row in FIRMWARE_ERROR_MANIFEST)


def is_plausible_firmware_code(code: str) -> bool:
    if len(code) < 3 or code in FIRMWARE_CODE_DENYLIST:
        return False
    if code in SINGLE_WORD_FIRMWARE_CODES:
        return True
    if "_" in code:
        return True
    return code in _MANIFEST_CODES


def extract_firmware_error_codes() -> set[str]:
    found: set[str] = set()

    def add(raw: str | None) -> None:
        if not raw:
            return
        code = normalize_code(raw)
        if not is_plausible_firmware_code(code):
            return
        found.add(code)

    for entry in FIRMWARE_ERROR_MANIFEST:
        add(entry[0])

    for path in FIRMWARE.rglob("*.c"):
        if "build/" in str(path) or "managed_components" in str(path):
            continue
        text = path.read_text(encoding="utf-8", errors="ignore")
        for pattern in _EXTRACT_PATTERNS:
            for match in pattern.finditer(text):
                add(match.group(1))
        for match in _FIRMWARE_RETURN_PATTERN.finditer(text):
            add(match.group(1))

    for doc_path in (
        DOC_MQTT / "MQTT_SPEC_FULL.md",
        DOC_MQTT / "BACKEND_NODE_CONTRACT_FULL.md",
        DOC_MQTT / "COMMAND_VALIDATION_ENGINE.md",
        ROOT / "doc_ai" / "02_HARDWARE_FIRMWARE" / "NODE_LOGIC_FULL.md",
    ):
        if doc_path.is_file():
            for pattern in _EXTRACT_PATTERNS:
                for match in pattern.finditer(doc_path.read_text(encoding="utf-8", errors="ignore")):
                    add(match.group(1))

    node_sim = ROOT / "tests" / "node_sim"
    if node_sim.is_dir():
        for path in node_sim.rglob("*.py"):
            for pattern in _EXTRACT_PATTERNS:
                for match in pattern.finditer(path.read_text(encoding="utf-8", errors="ignore")):
                    add(match.group(1))

    return found


def manifest_by_code() -> dict[str, tuple[str, str, str, str]]:
    return {normalize_code(row[0]): row for row in FIRMWARE_ERROR_MANIFEST}
