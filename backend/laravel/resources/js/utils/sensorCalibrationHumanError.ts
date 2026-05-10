/**
 * Человекочитаемые сообщения об ошибках калибровки сенсора (ответ узла / MQTT command_response).
 */

export function formatSensorCalibrationPointError(
  sensorType: 'ph' | 'ec',
  stage: 1 | 2,
  rawError: string | null,
  errorCode?: string | null,
): string {
  const raw = (rawError ?? '').trim()
  const code = (errorCode ?? '').trim().toLowerCase()
  const rawLc = raw.toLowerCase()

  const isTimeout =
    code === 'timeout' ||
    code === 'time_out' ||
    rawLc.includes('timed out') ||
    rawLc === 'timeout'

  if (isTimeout) {
    return 'Таймаут: узел не подтвердил калибровку в отведённое время. Проверьте Wi‑Fi, MQTT и что нода в сети, затем начните новую сессию.'
  }

  if (code === 'invalid_parameter' || rawLc.includes('invalid_parameter') || rawLc.includes('missing or invalid stage')) {
    return 'Неверные параметры команды калибровки (стадия или эталон). Проверьте значения буферов и начните сессию заново.'
  }

  if (code === 'invalid_channel' || rawLc.includes('invalid_channel')) {
    return 'Команда отправлена не на тот канал. Убедитесь, что в зоне выбран канал ph_sensor / ec_sensor согласно прошивке.'
  }

  if (sensorType === 'ph') {
    if (code === 'i2c_not_initialized' || rawLc.includes('i2c')) {
      return 'Шина I²C для pH не готова. Перезагрузите узел; если ошибка повторяется — проверьте проводку и питание модуля Trema.'
    }
    if (code === 'sensor_init_failed' || rawLc.includes('failed to initialize pH sensor')) {
      return 'Не удалось инициализировать модуль pH. Проверьте подключение Trema по I²C и адрес на шине.'
    }
    if (code === 'sensor_stub' || rawLc.includes('stub')) {
      return 'Датчик в режиме заглушки (нет реального ответа от модуля). Проверьте подключение pH‑метра.'
    }
    if (code === 'read_failed' || rawLc.includes('failed to read pH')) {
      return 'Не удалось прочитать показание pH с модуля. Проверьте щуп, I²C и питание.'
    }

    if (
      code === 'calibration_nvs_sync_failed' ||
      rawLc.includes('calibration_nvs_sync_failed') ||
      rawLc.includes('persist calibration')
    ) {
      return 'Модуль откалиброван, но узел не смог сохранить калибровку во внутреннюю память (NVS). Перезагрузите ноду и повторите вторую точку; если ошибка остаётся — проверьте свободное место NVS и прошивку.'
    }

    const calibFail =
      code === 'calibration_failed' ||
      rawLc.includes('failed to calibrate ph') ||
      rawLc.includes('calibration_failed')

    if (calibFail) {
      if (stage === 1) {
        return 'Первая точка не принята модулем Trema (ошибка расчёта или нестабильное показание). Держите щуп в кислом буфере без движения до стабилизации, проверьте качество раствора и повторите.'
      }
      return 'Вторая точка не принята модулем Trema. Частая причина — показание ещё «плавает» (флаги STAB_ERR / CALC_ERR): дольше выдерживайте щуп в щелочном буфере после промывки, проверьте буфер 9.18 и электрод, затем новая сессия.'
    }
  }

  if (sensorType === 'ec') {
    const calibFail =
      code === 'calibration_failed' ||
      rawLc.includes('calibration failed') ||
      rawLc.includes('calibration_failed')

    if (calibFail) {
      return stage === 1
        ? 'Первая точка EC/TDS не принята модулем. Проверьте раствор, стабилизацию щупа и повторите.'
        : 'Вторая точка EC/TDS не принята. Проверьте второй эталон, промывку и стабилизацию, затем новая сессия.'
    }
  }

  if (raw === '') {
    return 'Калибровка отклонена узлом. Начните новую сессию или проверьте логи ноды.'
  }

  return `Калибровка не выполнена (этап ${stage}). Сообщение от узла: ${raw}`
}
