import { expect, vi } from 'vitest'
import * as matchers from '@testing-library/jest-dom/matchers'
expect.extend(matchers.default ?? matchers)

// Мок для HTMLCanvasElement и getContext
const mockContext = {
  fillRect: vi.fn(),
  clearRect: vi.fn(),
  getImageData: vi.fn(() => ({ data: new Array(4) })),
  putImageData: vi.fn(),
  createImageData: vi.fn(() => ({ data: new Array(4) })),
  setTransform: vi.fn(),
  drawImage: vi.fn(),
  save: vi.fn(),
  restore: vi.fn(),
  beginPath: vi.fn(),
  moveTo: vi.fn(),
  lineTo: vi.fn(),
  closePath: vi.fn(),
  stroke: vi.fn(),
  translate: vi.fn(),
  scale: vi.fn(),
  rotate: vi.fn(),
  arc: vi.fn(),
  fill: vi.fn(),
  fillText: vi.fn(),
  strokeText: vi.fn(),
  setLineDash: vi.fn(),
  bezierCurveTo: vi.fn(),
  quadraticCurveTo: vi.fn(),
  ellipse: vi.fn(),
  createLinearGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
  createRadialGradient: vi.fn(() => ({ addColorStop: vi.fn() })),
  createPattern: vi.fn(),
  globalAlpha: 1,
  globalCompositeOperation: 'source-over',
  lineWidth: 1,
  lineCap: 'butt',
  lineJoin: 'miter',
  miterLimit: 10,
  measureText: vi.fn(() => ({ width: 0 })),
  transform: vi.fn(),
  rect: vi.fn(),
  clip: vi.fn(),
  canvas: {
    width: 800,
    height: 600,
    style: {},
  },
  set dpr(value) {},
  get dpr() { return 1 },
}

Object.defineProperty(HTMLCanvasElement.prototype, 'getContext', {
  value: vi.fn(() => mockContext),
  writable: true,
  configurable: true,
})

Object.defineProperty(HTMLCanvasElement.prototype, 'clientWidth', {
  get: vi.fn(() => 800),
  configurable: true,
})

Object.defineProperty(HTMLCanvasElement.prototype, 'clientHeight', {
  get: vi.fn(() => 600),
  configurable: true,
})

// Глобальный мок для logger (если не замокан в конкретном тесте)
vi.mock('@/utils/logger', async () => {
  const actual = await vi.importActual('@/utils/logger')
  return {
    ...actual,
    logger: {
      debug: vi.fn(),
      info: vi.fn(),
      warn: vi.fn(),
      error: vi.fn(),
      group: vi.fn(),
      groupEnd: vi.fn(),
      groupCollapsed: vi.fn(),
      table: vi.fn(),
      time: vi.fn(),
      timeEnd: vi.fn(),
      isDev: true,
      isProd: false
    }
  }
})

// Глобальные моки для виртуализации компонентов
// Используем простые компоненты-обертки, которые просто рендерят слоты
vi.mock('vue-virtual-scroller', () => {
  return {
    DynamicScroller: {
      name: 'DynamicScroller',
      props: ['items', 'minItemSize', 'keyField'],
      template: `
        <div class="dynamic-scroller">
          <template v-for="(item, index) in (items || [])" :key="getKey(item, index)">
            <slot :item="item" :index="index" :active="true" />
          </template>
        </div>
      `,
      methods: {
        getKey(item: any, index: number) {
          const keyField = this.$props.keyField || 'id'
          return item?.[keyField] ?? index
        }
      }
    },
    DynamicScrollerItem: {
      name: 'DynamicScrollerItem',
      props: ['item', 'active', 'sizeDependencies'],
      template: '<div class="dynamic-scroller-item"><slot /></div>'
    },
    RecycleScroller: {
      name: 'RecycleScroller',
      props: ['items', 'itemSize', 'keyField'],
      template: `
        <div class="recycle-scroller">
          <template v-for="(item, index) in (items || [])" :key="getKey(item, index)">
            <slot :item="item" :index="index" />
          </template>
        </div>
      `,
      methods: {
        getKey(item: any, index: number) {
          const keyField = this.$props.keyField || 'id'
          return item?.[keyField] ?? index
        }
      }
    }
  }
})

// Моки для window.setInterval и window.clearInterval (нужны для WebSocket тестов)
const mockSetInterval = vi.fn((callback: Function, delay?: number) => {
  return 123 as any
})

const mockClearInterval = vi.fn((id?: number) => {
  // Ничего не делаем в моке
})

global.setInterval = mockSetInterval
global.clearInterval = mockClearInterval

// Также добавляем в window, если он существует
if (typeof window !== 'undefined') {
  (window as any).setInterval = mockSetInterval
  (window as any).clearInterval = mockClearInterval
}
