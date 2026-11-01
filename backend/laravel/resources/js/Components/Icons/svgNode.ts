export type SvgNode =
  | { tag: 'path'; d: string; fill?: string }
  | { tag: 'circle'; cx: number; cy: number; r: number; fill?: string; stroke?: string }
  | { tag: 'rect'; x: number; y: number; width: number; height: number; rx?: number }
  | { tag: 'line'; x1: number; y1: number; x2: number; y2: number }
  | { tag: 'polyline'; points: string }

export function svgNodeAttrs(node: SvgNode): Record<string, string | number> {
  const attrs: Record<string, string | number> = {}
  for (const [key, value] of Object.entries(node)) {
    if (key === 'tag' || value === undefined) continue
    attrs[key] = value
  }
  return attrs
}
