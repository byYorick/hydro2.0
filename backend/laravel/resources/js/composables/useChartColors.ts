import { computed, type Ref } from 'vue'

const resolveCssColor = (variable: string, fallback: string): string => {
  if (typeof window === 'undefined') {
    return fallback
  }

  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

export interface ChartPalette {
  tooltipBg: string
  borderMuted: string
  borderStrong: string
  textPrimary: string
  textDim: string
  badgeNeutralBg: string
  badgeInfoBg: string
  badgeSuccessBg: string
  accentCyan: string
  accentGreen: string
}

export function useChartColors(theme: Ref<unknown>) {
  const palette = computed<ChartPalette>(() => {
    theme.value

    return {
      tooltipBg: resolveCssColor('--bg-surface-strong', 'rgba(17, 24, 39, 0.95)'),
      borderMuted: resolveCssColor('--border-muted', '#374151'),
      borderStrong: resolveCssColor('--border-strong', '#4b5563'),
      textPrimary: resolveCssColor('--text-primary', '#f3f4f6'),
      textDim: resolveCssColor('--text-dim', '#9ca3af'),
      badgeNeutralBg: resolveCssColor('--badge-neutral-bg', 'rgba(75, 85, 99, 0.2)'),
      badgeInfoBg: resolveCssColor('--badge-info-bg', 'rgba(96, 165, 250, 0.2)'),
      badgeSuccessBg: resolveCssColor('--badge-success-bg', 'rgba(34, 197, 94, 0.15)'),
      accentCyan: resolveCssColor('--accent-cyan', '#60a5fa'),
      accentGreen: resolveCssColor('--accent-green', '#22c55e'),
    }
  })

  return { palette, resolveCssColor }
}
