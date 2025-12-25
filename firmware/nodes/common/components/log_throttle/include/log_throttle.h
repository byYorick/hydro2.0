#ifndef LOG_THROTTLE_H
#define LOG_THROTTLE_H

#include <stdbool.h>
#include <stdint.h>
#include <stddef.h>

/**
 * @brief Разрешить логирование по ключу с заданным интервалом.
 *
 * @param key Уникальный статический ключ (строка или константа).
 * @param interval_ms Минимальный интервал между логами в миллисекундах.
 * @return true если логировать сейчас, false если нужно пропустить.
 */
bool log_throttle_allow(const char *key, uint32_t interval_ms);

#endif  // LOG_THROTTLE_H
