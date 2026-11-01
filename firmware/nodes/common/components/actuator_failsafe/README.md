# actuator_failsafe

Общий аппаратный E-STOP для актуаторных нод `ph_node`, `ec_node`, `pump_node`.

## Контракт

- Вход по умолчанию: `GPIO32`, `active_low`, внутренняя подтяжка pull-up, debounce 80 мс.
  `GPIO32` не strapping pin. Канал насоса не должен занимать этот GPIO.
- Пока кнопка зажата, защёлка активна. `run_pump` и `dose` отклоняются сразу:
  `ERROR` / `error_code=estop_active`. Команда, уже принятая в очередь до нажатия,
  не стартует и завершается тем же `ERROR`.
- На фронте нажатия и пока кнопка удерживается нода вызывает safe-state callback.
  Для этих нод callback — `pump_driver_force_deenergize`: direct GPIO сбрасывается в 0
  без ожидания мьютекса драйвера; синхронизация software-state — best-effort.
  Если мьютекс занят, это пишется в лог, выходы уже OFF.
- Отпускание снимает защёлку и **не** включает насосы обратно.
- Boot и reset: `actuator_failsafe_init` один раз вызывает safe-state. Если кнопка уже
  зажата в первый отсчёт, защёлка ставится сразу, без ожидания debounce.
- Watchdog / link-loss safe mode по-прежнему гасит актуаторы; callback ноды зовёт
  `pump_driver_force_deenergize`, а не `pump_driver_emergency_stop` с таймаутом 1 с.
- `pump_driver_run` / `dose` / latched `set_state(true)` дополнительно смотрят
  `actuator_failsafe_is_latched` (weak-ссылка). Нода без компонента не меняет поведение:
  символ пустой, включение не блокируется.

Очередь дозирования pH/EC по-прежнему не запускает два насоса одновременно
(`pump_acid`/`pump_base`, компоненты EC). Это программный interlock очереди, не замена E-STOP.

## Проверка без железа

```bash
gcc -Wall -Wextra -Werror \
  -I firmware/nodes/common/components/actuator_failsafe/include \
  -o /tmp/test_actuator_failsafe_logic \
  firmware/tests/host/test_actuator_failsafe_logic.c \
  firmware/nodes/common/components/actuator_failsafe/actuator_failsafe_logic.c
/tmp/test_actuator_failsafe_logic
```

## Проверка на железе

1. Кнопка между `GPIO32` и GND, внешний pull-up не обязателен (включён внутренний).
   Не держать линию в `LOW`, если этот GPIO позже переиспользуют как выход.
2. Во время `dose`/`run_pump` зажать кнопку: насос гаснет, повторная ON-команда
   отвечает `estop_active`.
3. Отпустить кнопку: насос остаётся выключен, новая команда выполняется.
4. Reset с зажатой кнопкой: после boot ON-команды отклоняются, выходы OFF.
5. Safe mode (потеря связи / watchdog policy ноды) оставляет выходы OFF даже если
   мьютекс `pump_driver` занят — в логе `force_deenergize: mutex busy`.
