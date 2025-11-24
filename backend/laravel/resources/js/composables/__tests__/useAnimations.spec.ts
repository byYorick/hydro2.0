import { describe, it, expect, vi, beforeEach, afterEach } from 'vitest'
import { ref } from 'vue'
import { 
  useNumberAnimation, 
  useFadeAnimation, 
  useStaggerAnimation,
  transitionClasses,
  usePageTransition
} from '../useAnimations'

describe('useAnimations', () => {
  beforeEach(() => {
    vi.useFakeTimers()
  })

  afterEach(() => {
    vi.useRealTimers()
  })

  describe('useNumberAnimation', () => {
    it('should initialize with target value', () => {
      const targetValue = ref(10)
      const { animatedValue } = useNumberAnimation(() => targetValue.value)
      
      expect(animatedValue.value).toBe(10)
    })

    it('should handle null values', () => {
      const targetValue = ref<number | null>(null)
      const { animatedValue } = useNumberAnimation(() => targetValue.value)
      
      expect(animatedValue.value).toBeNull()
    })

    it('should start animation when value changes', () => {
      const targetValue = ref(10)
      const { animatedValue, isAnimating, start } = useNumberAnimation(() => targetValue.value)
      
      expect(animatedValue.value).toBe(10)
      expect(isAnimating.value).toBe(false)
      
      targetValue.value = 20
      start()
      
      expect(isAnimating.value).toBe(true)
    })
  })

  describe('useFadeAnimation', () => {
    it('should initialize with hidden state', () => {
      const show = ref(false)
      const { opacity, isVisible } = useFadeAnimation(() => show.value)
      
      expect(opacity.value).toBe(0)
      expect(isVisible.value).toBe(false)
    })

    it('should show element', () => {
      const show = ref(false)
      const { opacity, isVisible, showElement } = useFadeAnimation(() => show.value)
      
      showElement()
      
      expect(isVisible.value).toBe(true)
      // Opacity should be set to 1 in next frame
      vi.advanceTimersByTime(0)
      expect(opacity.value).toBe(1)
    })

    it('should hide element', () => {
      const show = ref(true)
      const { opacity, isVisible, hideElement } = useFadeAnimation(() => show.value, { duration: 300 })
      
      isVisible.value = true
      opacity.value = 1
      
      hideElement()
      
      expect(opacity.value).toBe(0)
      
      vi.advanceTimersByTime(300)
      expect(isVisible.value).toBe(false)
    })
  })

  describe('useStaggerAnimation', () => {
    it('should calculate item delays', () => {
      const itemCount = ref(5)
      const { getItemDelay, duration, easing } = useStaggerAnimation(() => itemCount.value)
      
      expect(getItemDelay(0)).toBe(0)
      expect(getItemDelay(1)).toBe(50)
      expect(getItemDelay(2)).toBe(100)
      expect(getItemDelay(3)).toBe(150)
      expect(getItemDelay(4)).toBe(200)
      
      expect(duration).toBe(300)
      expect(easing).toBe('cubic-bezier(0.4, 0, 0.2, 1)')
    })

    it('should use custom config', () => {
      const itemCount = ref(3)
      const { getItemDelay, duration } = useStaggerAnimation(() => itemCount.value, { duration: 500 })
      
      expect(duration).toBe(500)
      expect(getItemDelay(1)).toBe(50) // Stagger delay is still 50ms
    })
  })

  describe('transitionClasses', () => {
    it('should have fade transition classes', () => {
      expect(transitionClasses.fade).toHaveProperty('enter')
      expect(transitionClasses.fade).toHaveProperty('enterFrom')
      expect(transitionClasses.fade).toHaveProperty('enterTo')
      expect(transitionClasses.fade).toHaveProperty('leave')
      expect(transitionClasses.fade).toHaveProperty('leaveFrom')
      expect(transitionClasses.fade).toHaveProperty('leaveTo')
    })

    it('should have slide transition classes', () => {
      expect(transitionClasses.slide).toHaveProperty('enter')
      expect(transitionClasses.slide).toHaveProperty('enterFrom')
      expect(transitionClasses.slide.enterFrom).toContain('translate-x-full')
    })

    it('should have scale transition classes', () => {
      expect(transitionClasses.scale).toHaveProperty('enter')
      expect(transitionClasses.scale.enterFrom).toContain('scale-95')
      expect(transitionClasses.scale.enterTo).toContain('scale-100')
    })
  })

  describe('usePageTransition', () => {
    it('should initialize with not transitioning', () => {
      const { isTransitioning } = usePageTransition()
      
      expect(isTransitioning.value).toBe(false)
    })

    it('should start transition', () => {
      const { isTransitioning, startTransition } = usePageTransition()
      
      startTransition()
      
      expect(isTransitioning.value).toBe(true)
    })

    it('should end transition after delay', () => {
      const { isTransitioning, startTransition, endTransition } = usePageTransition()
      
      startTransition()
      expect(isTransitioning.value).toBe(true)
      
      endTransition()
      
      vi.advanceTimersByTime(300)
      expect(isTransitioning.value).toBe(false)
    })
  })
})

