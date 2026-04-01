import { ref, onUnmounted } from 'vue'

/**
 * Реактивный таймер "сейчас" для вычисления прогресса до следующего запуска цикла.
 * Обновляется каждые `intervalMs` миллисекунд и автоматически очищается при размонтировании.
 */
export function useCycleTimer(intervalMs = 30_000) {
  const now = ref(Date.now())
  const timer = setInterval(() => {
    now.value = Date.now()
  }, intervalMs)

  onUnmounted(() => clearInterval(timer))

  return { now }
}
