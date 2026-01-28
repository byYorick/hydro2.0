/// <reference types="vite/client" />
/// <reference types="vitest/globals" />

declare const require: (moduleId: string) => any;

interface Window {
  __echartsTooltipStyleAdded?: boolean;
}

declare const Ziggy: unknown;

declare module '@/utils/formatTime' {
  export function formatTime(dateString?: string | Date | null): string;
  export function formatTimeShort(timestamp?: string | Date | null): string;
  export function formatInterval(seconds?: number | null): string;
  export function formatTimeAgo(timestamp?: number | string | Date | null): string;
}

declare module '@/utils/i18n' {
  export function translateStatus(status: string): string;
  export function translateEventKind(kind: string): string;
  export function translateRole(role: string): string;
  export function translateCycleType(cycleType: string): string;
  export function translateStrategy(strategy: string): string;
  export function translateDeviceType(type: string): string;
}

declare module '../../../vendor/tightenco/ziggy/dist/index.esm.js' {
  export const ZiggyVue: { install: (...args: any[]) => void } | ((...args: any[]) => any);
  const defaultExport: unknown;
  export default defaultExport;
}
