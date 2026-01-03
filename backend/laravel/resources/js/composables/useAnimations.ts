import { ref, onMounted, onUnmounted, getCurrentInstance } from 'vue'

/**
 * Composable для управления анимациями и переходами
 * Обеспечивает плавные переходы и микро-интерактивности
 */

export interface AnimationConfig {
  duration?: number
  easing?: string
  delay?: number
}

const defaultConfig: Required<AnimationConfig> = {
  duration: 300,
  easing: 'cubic-bezier(0.4, 0, 0.2, 1)',
  delay: 0,
}

/**
 * Создает плавную анимацию изменения числового значения
 */
export function useNumberAnimation(
  targetValue: () => number | null,
  config: AnimationConfig = {}
) {
  const animatedValue = ref<number | null>(null)
  const isAnimating = ref(false)
  
  const mergedConfig = { ...defaultConfig, ...config }
  let animationFrameId: number | null = null
  let startTime: number | null = null
  let startValue: number | null = null
  
  const animate = (timestamp: number) => {
    if (!startTime) {
      startTime = timestamp
      startValue = animatedValue.value ?? targetValue() ?? 0
    }
    
    const elapsed = timestamp - startTime
    const progress = Math.min(elapsed / mergedConfig.duration, 1)
    
    // Easing function (ease-in-out)
    const eased = progress < 0.5
      ? 2 * progress * progress
      : 1 - Math.pow(-2 * progress + 2, 2) / 2
    
    const current = targetValue()
    if (current !== null && startValue !== null) {
      animatedValue.value = startValue + (current - startValue) * eased
    }
    
    if (progress < 1) {
      animationFrameId = requestAnimationFrame(animate)
    } else {
      animatedValue.value = current
      isAnimating.value = false
      startTime = null
      startValue = null
    }
  }
  
  const start = () => {
    if (animationFrameId !== null) {
      cancelAnimationFrame(animationFrameId)
    }
    isAnimating.value = true
    startTime = null
    animationFrameId = requestAnimationFrame(animate)
  }
  
  const hasInstance = !!getCurrentInstance()

  if (hasInstance) {
    onMounted(() => {
      animatedValue.value = targetValue() ?? null
    })
    
    onUnmounted(() => {
      if (animationFrameId !== null) {
        cancelAnimationFrame(animationFrameId)
      }
    })
  }
  
  return {
    animatedValue,
    isAnimating,
    start,
  }
}

/**
 * Создает анимацию появления/исчезновения элемента
 */
export function useFadeAnimation(show: () => boolean, config: AnimationConfig = {}) {
  const mergedConfig = { ...defaultConfig, ...config }
  const opacity = ref(0)
  const isVisible = ref(false)
  
  const showElement = () => {
    isVisible.value = true
    opacity.value = 0
    requestAnimationFrame(() => {
      opacity.value = 1
    })
  }
  
  const hideElement = () => {
    opacity.value = 0
    setTimeout(() => {
      isVisible.value = false
    }, mergedConfig.duration)
  }
  
  return {
    opacity,
    isVisible,
    showElement,
    hideElement,
  }
}

/**
 * Создает анимацию для списка элементов (stagger)
 */
export function useStaggerAnimation(itemCount: () => number, config: AnimationConfig = {}) {
  const mergedConfig = { ...defaultConfig, ...config }
  const staggerDelay = 50
  
  const getItemDelay = (index: number) => {
    return index * staggerDelay
  }
  
  return {
    getItemDelay,
    duration: mergedConfig.duration,
    easing: mergedConfig.easing,
  }
}

/**
 * CSS классы для переходов
 */
export const transitionClasses = {
  fade: {
    enter: 'transition-opacity duration-300 ease-in-out',
    enterFrom: 'opacity-0',
    enterTo: 'opacity-100',
    leave: 'transition-opacity duration-300 ease-in-out',
    leaveFrom: 'opacity-100',
    leaveTo: 'opacity-0',
  },
  slide: {
    enter: 'transition-transform duration-300 ease-in-out',
    enterFrom: 'transform translate-x-full',
    enterTo: 'transform translate-x-0',
    leave: 'transition-transform duration-300 ease-in-out',
    leaveFrom: 'transform translate-x-0',
    leaveTo: 'transform translate-x-full',
  },
  scale: {
    enter: 'transition-all duration-300 ease-in-out',
    enterFrom: 'opacity-0 scale-95',
    enterTo: 'opacity-100 scale-100',
    leave: 'transition-all duration-300 ease-in-out',
    leaveFrom: 'opacity-100 scale-100',
    leaveTo: 'opacity-0 scale-95',
  },
}

/**
 * Утилита для создания плавного перехода между страницами
 */
export function usePageTransition() {
  const isTransitioning = ref(false)
  
  const startTransition = () => {
    isTransitioning.value = true
  }
  
  const endTransition = () => {
    setTimeout(() => {
      isTransitioning.value = false
    }, 300)
  }
  
  return {
    isTransitioning,
    startTransition,
    endTransition,
  }
}
