import type { SvgNode } from '@/Components/Icons/svgNode'

function path(d: string): SvgNode {
  return { tag: 'path', d }
}

const DEVICE_ICONS: Record<string, SvgNode[]> = {
  ph: [
    path('M8 3h8'),
    path('M9 3v6L5 17a1 1 0 00.9 1.5h12.2A1 1 0 0019 17l-4-8V3'),
    { tag: 'line', x1: 8, y1: 14, x2: 16, y2: 14 },
  ],
  ec: [path('M2 12c2-6 4-6 6 0s4 6 6 0 4-6 6 0')],
  sensor: [
    { tag: 'circle', cx: 12, cy: 12, r: 9 },
    { tag: 'circle', cx: 12, cy: 12, r: 4 },
    { tag: 'circle', cx: 12, cy: 12, r: 1, fill: 'currentColor', stroke: 'none' },
  ],
  actuator: [
    { tag: 'circle', cx: 12, cy: 12, r: 3 },
    path('M19.4 15a1.65 1.65 0 00.33 1.82l.06.06a2 2 0 010 2.83 2 2 0 01-2.83 0l-.06-.06a1.65 1.65 0 00-1.82-.33 1.65 1.65 0 00-1 1.51V21a2 2 0 01-4 0v-.09A1.65 1.65 0 009 19.4a1.65 1.65 0 00-1.82.33l-.06.06a2 2 0 01-2.83-2.83l.06-.06A1.65 1.65 0 004.68 15a1.65 1.65 0 00-1.51-1H3a2 2 0 010-4h.09A1.65 1.65 0 004.6 9a1.65 1.65 0 00-.33-1.82l-.06-.06a2 2 0 012.83-2.83l.06.06A1.65 1.65 0 009 4.68a1.65 1.65 0 001-1.51V3a2 2 0 014 0v.09a1.65 1.65 0 001 1.51 1.65 1.65 0 001.82-.33l.06-.06a2 2 0 012.83 2.83l-.06.06A1.65 1.65 0 0019.4 9a1.65 1.65 0 001.51 1H21a2 2 0 010 4h-.09a1.65 1.65 0 00-1.51 1z'),
  ],
  controller: [
    { tag: 'rect', x: 4, y: 4, width: 16, height: 16, rx: 2 },
    { tag: 'rect', x: 9, y: 9, width: 6, height: 6 },
    { tag: 'line', x1: 9, y1: 1, x2: 9, y2: 4 },
    { tag: 'line', x1: 15, y1: 1, x2: 15, y2: 4 },
    { tag: 'line', x1: 9, y1: 20, x2: 9, y2: 23 },
    { tag: 'line', x1: 15, y1: 20, x2: 15, y2: 23 },
    { tag: 'line', x1: 20, y1: 9, x2: 23, y2: 9 },
    { tag: 'line', x1: 20, y1: 14, x2: 23, y2: 14 },
    { tag: 'line', x1: 1, y1: 9, x2: 4, y2: 9 },
    { tag: 'line', x1: 1, y1: 14, x2: 4, y2: 14 },
  ],
  irrig: [path('M12 2C6.5 9 4 13 4 16a8 8 0 0016 0c0-3-2.5-7-8-14z')],
  climate: [path('M14 14.76V3.5a2.5 2.5 0 00-5 0v11.26a4.5 4.5 0 105 0z')],
  light: [
    path('M9 18h6'),
    path('M10 22h4'),
    path('M12 2a7 7 0 014.95 11.95A5 5 0 0115 18H9a5 5 0 01-1.95-4.05A7 7 0 0112 2z'),
  ],
  relay: [
    { tag: 'rect', x: 1, y: 8, width: 22, height: 8, rx: 4 },
    { tag: 'circle', cx: 16, cy: 12, r: 3, fill: 'currentColor', stroke: 'none' },
  ],
  water_sensor: [
    path('M2 12c1.5-2 3-2 4.5 0s3 2 4.5 0 3-2 4.5 0 1.5 2 3 2'),
    path('M2 17c1.5-2 3-2 4.5 0s3 2 4.5 0 3-2 4.5 0 1.5 2 3 2'),
    { tag: 'line', x1: 12, y1: 3, x2: 12, y2: 9 },
  ],
  recirculation: [
    { tag: 'polyline', points: '23 4 23 10 17 10' },
    path('M20.49 15a9 9 0 11-2.12-9.36L23 10'),
  ],
}

const FALLBACK_ICON: SvgNode[] = [
  { tag: 'rect', x: 3, y: 3, width: 18, height: 18, rx: 3 },
  { tag: 'line', x1: 12, y1: 8, x2: 12, y2: 16 },
  { tag: 'line', x1: 8, y1: 12, x2: 16, y2: 12 },
]

export function deviceIconNodes(type: string | undefined): SvgNode[] {
  return DEVICE_ICONS[type ?? ''] ?? FALLBACK_ICON
}
