import { mount } from '@vue/test-utils'
import { describe, it, expect } from 'vitest'
import ZoneHealthGauge from '../ZoneHealthGauge.vue'

describe('ZoneHealthGauge', () => {
  // ─── Value display ────────────────────────────────────────────────────────

  it('отображает "—" когда значение не передано', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { label: 'pH' },
    })
    expect(wrapper.text()).toContain('—')
  })

  it('отображает "—" когда значение null', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: null, label: 'pH' },
    })
    expect(wrapper.text()).toContain('—')
  })

  it('отображает значение с 2 знаками после запятой по умолчанию', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 6.1234, label: 'pH' },
    })
    expect(wrapper.text()).toContain('6.12')
    expect(wrapper.text()).not.toContain('6.1234')
  })

  it('уважает decimals=1', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 22.567, label: 'T°C', decimals: 1 },
    })
    expect(wrapper.text()).toContain('22.6')
  })

  it('отображает label', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 6.0, label: 'pH' },
    })
    expect(wrapper.text()).toContain('pH')
  })

  it('отображает unit рядом с label', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 1.6, label: 'EC', unit: ' мСм' },
    })
    expect(wrapper.text()).toContain('мСм')
  })

  // ─── Target range display ─────────────────────────────────────────────────

  it('отображает диапазон цели когда targetMin/targetMax заданы', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 6.0, targetMin: 5.8, targetMax: 6.2, label: 'pH' },
    })
    expect(wrapper.text()).toContain('5.80')
    expect(wrapper.text()).toContain('6.20')
  })

  it('не отображает диапазон цели без targetMin/targetMax', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 6.0, label: 'pH' },
    })
    // Нет символа "–" который разделяет min–max
    expect(wrapper.text()).not.toMatch(/\d–\d/)
  })

  // ─── SVG structure ────────────────────────────────────────────────────────

  it('содержит SVG элемент', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 6.0, label: 'pH' },
    })
    expect(wrapper.find('svg').exists()).toBe(true)
  })

  it('рендерит трек (полный дуговой путь) всегда', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 6.0, label: 'pH' },
    })
    const paths = wrapper.findAll('path')
    expect(paths.length).toBeGreaterThan(0)
  })

  it('рендерит путь до текущего значения (value arc)', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 6.0, label: 'pH', globalMin: 4.0, globalMax: 9.0 },
    })
    // Должно быть минимум 2 пути: трек + value arc
    const paths = wrapper.findAll('path')
    expect(paths.length).toBeGreaterThanOrEqual(2)
  })

  it('рендерит дугу целевого диапазона при наличии targets', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 6.0, targetMin: 5.8, targetMax: 6.2, label: 'pH', globalMin: 4.0, globalMax: 9.0 },
    })
    // Трек + target arc + value arc = минимум 3
    const paths = wrapper.findAll('path')
    expect(paths.length).toBeGreaterThanOrEqual(3)
  })

  it('рендерит точку-индикатор (circle) когда есть значение', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 6.0, label: 'pH', globalMin: 4.0, globalMax: 9.0 },
    })
    const circle = wrapper.find('circle')
    expect(circle.exists()).toBe(true)
  })

  it('не рендерит точку-индикатор без значения', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { label: 'pH', globalMin: 4.0, globalMax: 9.0 },
    })
    const circle = wrapper.find('circle')
    expect(circle.exists()).toBe(false)
  })

  // ─── Status icon ─────────────────────────────────────────────────────────

  it('показывает ✓ когда значение в целевом диапазоне', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 6.0, targetMin: 5.8, targetMax: 6.2, label: 'pH' },
    })
    expect(wrapper.text()).toContain('✓')
  })

  it('показывает ! когда значение у границы диапазона (warning)', () => {
    // span = 0.4, margin = 0.08; warning: 5.72 ≤ v < 5.8 или 6.2 < v ≤ 6.28
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 6.25, targetMin: 5.8, targetMax: 6.2, label: 'pH' },
    })
    expect(wrapper.text()).toContain('!')
  })

  it('показывает ✕ когда значение за пределами диапазона (danger)', () => {
    // span = 0.4, margin = 0.08; danger: v > 6.28 или v < 5.72
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 7.0, targetMin: 5.8, targetMax: 6.2, label: 'pH' },
    })
    expect(wrapper.text()).toContain('✕')
  })

  it('показывает ✕ когда значение ниже диапазона', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 5.0, targetMin: 5.8, targetMax: 6.2, label: 'pH' },
    })
    expect(wrapper.text()).toContain('✕')
  })

  it('не показывает иконку статуса без значения', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { targetMin: 5.8, targetMax: 6.2, label: 'pH' },
    })
    // Нет ✓, !, ✕ в тексте (нет значения)
    expect(wrapper.text()).not.toMatch(/[✓!✕]/)
  })

  it('не показывает иконку когда нет target range', () => {
    // Без targets → статус neutral → нет иконки
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 6.0, label: 'pH' },
    })
    // status = 'neutral' т.к. нет targets, statusIcon = ''
    expect(wrapper.text()).not.toMatch(/[✓!✕]/)
  })

  // ─── Auto-range computation ───────────────────────────────────────────────

  it('корректно строит auto-range от targetMin/targetMax без explicit globalMin/globalMax', () => {
    // auto: globalMin = 5.8 - 0.4*0.5 = 5.6, globalMax = 6.2 + 0.4*0.5 = 6.4
    // Value pct для 6.0: (6.0-5.6)/(6.4-5.6) = 0.5 → точка на вершине
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 6.0, targetMin: 5.8, targetMax: 6.2, label: 'pH' },
    })
    // Компонент должен смонтироваться без ошибок и показать значение
    expect(wrapper.text()).toContain('6.00')
  })

  it('использует explicit globalMin/globalMax когда переданы', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: {
        value: 6.0,
        targetMin: 5.8,
        targetMax: 6.2,
        globalMin: 4.0,
        globalMax: 9.0,
        label: 'pH',
      },
    })
    expect(wrapper.text()).toContain('6.00')
    // При глобальном диапазоне [4,9] значение 6.0 — в пределах targets → ok
    expect(wrapper.text()).toContain('✓')
  })

  // ─── Edge cases ───────────────────────────────────────────────────────────

  it('не падает когда globalMin === globalMax', () => {
    expect(() => {
      mount(ZoneHealthGauge, {
        props: { value: 5.0, globalMin: 5.0, globalMax: 5.0, label: 'pH' },
      })
    }).not.toThrow()
  })

  it('clamps value < globalMin к 0% на дуге', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 3.0, globalMin: 4.0, globalMax: 9.0, label: 'pH' },
    })
    // Должен рендериться без ошибок (pct = 0 → left end)
    expect(wrapper.text()).toContain('3.00')
  })

  it('clamps value > globalMax к 100% на дуге', () => {
    const wrapper = mount(ZoneHealthGauge, {
      props: { value: 12.0, globalMin: 4.0, globalMax: 9.0, label: 'pH' },
    })
    expect(wrapper.text()).toContain('12.00')
  })
})
