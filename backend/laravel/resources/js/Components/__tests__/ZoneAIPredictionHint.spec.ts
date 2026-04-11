import { mount, flushPromises } from '@vue/test-utils'
import { describe, it, expect, vi, beforeEach } from 'vitest'
import ZoneAIPredictionHint from '../ZoneAIPredictionHint.vue'

// ─── Mocks ────────────────────────────────────────────────────────────────────

const aiPredictMock = vi.hoisted(() => vi.fn())

vi.mock('@/services/api', () => ({
  api: {
    ai: {
      predict: aiPredictMock,
    },
  },
}))

vi.mock('@/utils/logger', () => ({
  logger: { debug: vi.fn(), error: vi.fn(), info: vi.fn(), warn: vi.fn() },
}))

// ─── Helpers ──────────────────────────────────────────────────────────────────

function makePrediction(predicted_value: number, confidence = 0.85) {
  return {
    status: 'ok',
    data: {
      predicted_value,
      confidence,
      predicted_at: '2025-01-01T00:00:00Z',
      horizon_minutes: 90,
    },
  }
}

const defaultProps = {
  zoneId: 1,
  metricType: 'PH' as const,
  targetMin: 5.8,
  targetMax: 6.2,
  horizonMinutes: 90,
}

// ─── Tests ────────────────────────────────────────────────────────────────────

describe('ZoneAIPredictionHint', () => {
  beforeEach(() => {
    vi.clearAllMocks()
  })

  // ─── Visibility ─────────────────────────────────────────────────────────

  it('не рендерит ничего пока API ещё не ответил', () => {
    aiPredictMock.mockReturnValue(new Promise(() => {})) // зависает навсегда

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })

    // Hint скрыт (v-if="hintText", hintText=null пока нет prediction)
    expect(wrapper.find('div').exists()).toBe(false)
  })

  it('не рендерит ничего когда API вернул пустой data', async () => {
    aiPredictMock.mockResolvedValue({ status: 'ok', data: null })

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()

    expect(wrapper.find('div').exists()).toBe(false)
  })

  it('не рендерит ничего при ошибке API', async () => {
    aiPredictMock.mockRejectedValue(new Error('Network error'))

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()

    expect(wrapper.find('div').exists()).toBe(false)
  })

  it('не рендерит ничего когда confidence низкий и значение в норме', async () => {
    // In range, but confidence < 0.75 → hintText = null
    aiPredictMock.mockResolvedValue(makePrediction(6.0, 0.5))

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()

    expect(wrapper.find('div').exists()).toBe(false)
  })

  // ─── Stable hint ─────────────────────────────────────────────────────────

  it('показывает stable хинт для уверенного прогноза в норме', async () => {
    // 6.0 ∈ [5.8, 6.2], не у границы (span=0.4, margin=0.04 → near if >6.16 or <5.84)
    aiPredictMock.mockResolvedValue(makePrediction(6.0, 0.85))

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()

    expect(wrapper.find('div').exists()).toBe(true)
    expect(wrapper.text()).toContain('pH стабилен')
    expect(wrapper.text()).toContain('6.00')
    expect(wrapper.text()).toContain('✦')
  })

  it('показывает время прогноза в часах (≥60 мин)', async () => {
    aiPredictMock.mockResolvedValue(makePrediction(6.0, 0.85))

    const wrapper = mount(ZoneAIPredictionHint, {
      props: { ...defaultProps, horizonMinutes: 90 },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('1.5 ч')
  })

  it('показывает время прогноза в минутах (<60 мин)', async () => {
    aiPredictMock.mockResolvedValue(makePrediction(6.0, 0.85))

    const wrapper = mount(ZoneAIPredictionHint, {
      props: { ...defaultProps, horizonMinutes: 30 },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('30 мин')
  })

  // ─── Near edge hint ───────────────────────────────────────────────────────

  it('показывает хинт "у границы" для значения у верхней границы', async () => {
    // span=0.4, margin=0.04; near edge if v > 6.2-0.04=6.16
    aiPredictMock.mockResolvedValue(makePrediction(6.18, 0.85))

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()

    expect(wrapper.text()).toContain('у границы')
    expect(wrapper.text()).toContain('⚠️')
  })

  it('показывает хинт "у границы" для значения у нижней границы', async () => {
    // near edge if v < 5.8+0.04=5.84
    aiPredictMock.mockResolvedValue(makePrediction(5.82, 0.85))

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()

    expect(wrapper.text()).toContain('у границы')
    expect(wrapper.text()).toContain('⚠️')
  })

  // ─── Out of range hint ────────────────────────────────────────────────────

  it('показывает хинт "выйдет ↑" когда прогноз выше max', async () => {
    aiPredictMock.mockResolvedValue(makePrediction(6.5, 0.9))

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()

    expect(wrapper.text()).toContain('выйдет ↑')
    expect(wrapper.text()).toContain('⚡')
    expect(wrapper.text()).toContain('6.50')
  })

  it('показывает хинт "выйдет ↓" когда прогноз ниже min', async () => {
    aiPredictMock.mockResolvedValue(makePrediction(5.3, 0.9))

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()

    expect(wrapper.text()).toContain('выйдет ↓')
    expect(wrapper.text()).toContain('⚡')
  })

  // ─── EC metric ────────────────────────────────────────────────────────────

  it('показывает EC label и единицы для metricType=EC', async () => {
    aiPredictMock.mockResolvedValue(makePrediction(1.7, 0.85))

    const wrapper = mount(ZoneAIPredictionHint, {
      props: { zoneId: 1, metricType: 'EC', targetMin: 1.4, targetMax: 1.8, horizonMinutes: 90 },
    })
    await flushPromises()

    expect(wrapper.text()).toContain('EC стабилен')
    expect(wrapper.text()).toContain('мСм/см')
  })

  // ─── API call parameters ─────────────────────────────────────────────────

  it('вызывает API с корректными параметрами', async () => {
    aiPredictMock.mockResolvedValue({ status: 'ok', data: null })

    mount(ZoneAIPredictionHint, {
      props: { zoneId: 42, metricType: 'EC', targetMin: 1.4, targetMax: 1.8, horizonMinutes: 60 },
    })
    await flushPromises()

    expect(aiPredictMock).toHaveBeenCalledWith({
      zone_id: 42,
      metric_type: 'EC',
      horizon_minutes: 60,
    })
  })

  it('вызывает API один раз при монтировании', async () => {
    aiPredictMock.mockResolvedValue({ status: 'ok', data: null })

    mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()

    expect(aiPredictMock).toHaveBeenCalledTimes(1)
  })

  // ─── Reactivity ──────────────────────────────────────────────────────────

  it('повторно запрашивает API при смене zoneId', async () => {
    aiPredictMock.mockResolvedValue({ status: 'ok', data: null })

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()
    expect(aiPredictMock).toHaveBeenCalledTimes(1)

    await wrapper.setProps({ zoneId: 2 })
    await flushPromises()

    expect(aiPredictMock).toHaveBeenCalledTimes(2)
    expect(aiPredictMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ zone_id: 2 }),
    )
  })

  it('повторно запрашивает API при смене metricType', async () => {
    aiPredictMock.mockResolvedValue({ status: 'ok', data: null })

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()

    await wrapper.setProps({ metricType: 'EC' })
    await flushPromises()

    expect(aiPredictMock).toHaveBeenCalledTimes(2)
    expect(aiPredictMock).toHaveBeenLastCalledWith(
      expect.objectContaining({ metric_type: 'EC' }),
    )
  })

  it('сбрасывает prediction при смене zoneId', async () => {
    // Первый вызов — данные есть
    aiPredictMock.mockResolvedValueOnce(makePrediction(6.0, 0.85))
    // Второй вызов — данных нет
    aiPredictMock.mockResolvedValueOnce({ status: 'ok', data: null })

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()
    expect(wrapper.find('div').exists()).toBe(true) // хинт виден

    await wrapper.setProps({ zoneId: 2 })
    await flushPromises()
    expect(wrapper.find('div').exists()).toBe(false) // хинт исчез
  })

  // ─── CSS classes ─────────────────────────────────────────────────────────

  it('применяет нейтральный стиль для stable хинта', async () => {
    aiPredictMock.mockResolvedValue(makePrediction(6.0, 0.85))

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()

    const hint = wrapper.find('div')
    // Нейтральный: border-muted класс, не danger и не warning
    expect(hint.classes().join(' ')).toContain('border')
    expect(hint.classes().join(' ')).not.toMatch(/danger/)
    expect(hint.classes().join(' ')).not.toMatch(/warning/)
  })

  it('применяет warning стиль для хинта у границы', async () => {
    aiPredictMock.mockResolvedValue(makePrediction(6.18, 0.85))

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()

    const hint = wrapper.find('div')
    expect(hint.classes().join(' ')).toMatch(/warning/)
  })

  it('применяет danger стиль для хинта выхода за границу', async () => {
    aiPredictMock.mockResolvedValue(makePrediction(7.0, 0.9))

    const wrapper = mount(ZoneAIPredictionHint, { props: defaultProps })
    await flushPromises()

    const hint = wrapper.find('div')
    expect(hint.classes().join(' ')).toMatch(/danger/)
  })
})
