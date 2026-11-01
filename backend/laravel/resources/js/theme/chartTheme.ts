import type { EChartsOption } from 'echarts'

export const CHART_FONT_FAMILY = '"IBM Plex Sans", Figtree, sans-serif'
export const CHART_FONT_MONO = '"JetBrains Mono", ui-monospace, SFMono-Regular, monospace'

export interface HydroChartPalette {
  tooltipBg: string
  borderMuted: string
  borderStrong: string
  textPrimary: string
  textMuted: string
  textDim: string
  badgeNeutralBg: string
  badgeInfoBg: string
  badgeSuccessBg: string
  accentCyan: string
  accentGreen: string
  accentAmber: string
  statusOk: string
  statusWarning: string
  statusCritical: string
  statusOffline: string
  statusInfo: string
  fontFamily: string
  fontMono: string
}

export function readCssVar(variable: string, fallback: string): string {
  if (typeof window === 'undefined' || typeof document === 'undefined') {
    return fallback
  }

  const value = getComputedStyle(document.documentElement).getPropertyValue(variable).trim()
  return value || fallback
}

export function readChartPalette(): HydroChartPalette {
  return {
    tooltipBg: readCssVar('--bg-surface-strong', 'rgba(17, 24, 39, 0.95)'),
    borderMuted: readCssVar('--border-muted', '#374151'),
    borderStrong: readCssVar('--border-strong', '#4b5563'),
    textPrimary: readCssVar('--text-primary', '#f3f4f6'),
    textMuted: readCssVar('--text-muted', '#a3b4c7'),
    textDim: readCssVar('--text-dim', '#9ca3af'),
    badgeNeutralBg: readCssVar('--badge-neutral-bg', 'rgba(75, 85, 99, 0.2)'),
    badgeInfoBg: readCssVar('--badge-info-bg', 'rgba(96, 165, 250, 0.2)'),
    badgeSuccessBg: readCssVar('--badge-success-bg', 'rgba(34, 197, 94, 0.15)'),
    accentCyan: readCssVar('--accent-cyan', '#5dd6ff'),
    accentGreen: readCssVar('--accent-green', '#49e08a'),
    accentAmber: readCssVar('--accent-amber', '#f0b268'),
    statusOk: readCssVar('--status-ok', '#49e08a'),
    statusWarning: readCssVar('--status-warning', '#f0b268'),
    statusCritical: readCssVar('--status-critical', '#ff6c6c'),
    statusOffline: readCssVar('--status-offline', '#9aabbf'),
    statusInfo: readCssVar('--status-info', '#5dd6ff'),
    fontFamily: CHART_FONT_FAMILY,
    fontMono: CHART_FONT_MONO,
  }
}

function isRecord(value: unknown): value is Record<string, unknown> {
  return Boolean(value) && typeof value === 'object' && !Array.isArray(value)
}

/**
 * Базовая тема ECharts: прозрачный холст, шрифты оболочки и tooltip,
 * цвета которого читаются из CSS-переменных текущей темы (light/dark).
 * Встроенная тема `dark` не используется: она закрашивает canvas своим фоном.
 */
export function hydroChartBaseOption(): EChartsOption {
  const palette = readChartPalette()

  return {
    backgroundColor: 'transparent',
    textStyle: {
      fontFamily: palette.fontFamily,
      color: palette.textPrimary,
    },
    tooltip: {
      backgroundColor: palette.tooltipBg,
      borderColor: palette.borderMuted,
      borderWidth: 1,
      textStyle: {
        color: palette.textPrimary,
        fontSize: 12,
        fontFamily: palette.fontFamily,
      },
      extraCssText: 'z-index: 99999 !important; border-radius: 8px; box-shadow: var(--shadow-card);',
    },
    axisPointer: {
      lineStyle: { color: palette.borderStrong },
    },
  }
}

export function mergeChartOption(option: EChartsOption): EChartsOption {
  const base = hydroChartBaseOption()
  const merged: EChartsOption = {
    ...base,
    ...option,
    textStyle: {
      ...(isRecord(base.textStyle) ? base.textStyle : {}),
      ...(isRecord(option.textStyle) ? option.textStyle : {}),
    },
  }

  if (!Array.isArray(option.tooltip) && isRecord(option.tooltip) && isRecord(base.tooltip)) {
    merged.tooltip = {
      ...base.tooltip,
      ...option.tooltip,
      textStyle: {
        ...(isRecord(base.tooltip.textStyle) ? base.tooltip.textStyle : {}),
        ...(isRecord(option.tooltip.textStyle) ? option.tooltip.textStyle : {}),
      },
    }
  }

  return merged
}
