import type {
  CorrectionCatalogField,
  CorrectionCatalogSection,
  CorrectionPhase,
} from '@/types/CorrectionConfig'

export interface CorrectionDiff {
  section: string
  sectionLabel: string
  path: string
  label: string
  phase: 'base' | CorrectionPhase
  oldVal: unknown
  newVal: unknown
}

export interface DiffLine {
  t: 'ctx' | 'add' | 'del' | 'hdr'
  n: string
  c: string
}

export interface ConfigShape {
  base: Record<string, unknown>
  phases: Record<CorrectionPhase, Record<string, unknown>>
}

function getByPath(target: Record<string, unknown>, path: string): unknown {
  return path.split('.').reduce<unknown>((cur, seg) => {
    if (!cur || typeof cur !== 'object' || Array.isArray(cur)) return undefined
    return (cur as Record<string, unknown>)[seg]
  }, target)
}

function areEq(a: unknown, b: unknown): boolean {
  return JSON.stringify(a) === JSON.stringify(b)
}

function fmtVal(v: unknown): string {
  if (v === undefined) return '<unset>'
  if (typeof v === 'string') return JSON.stringify(v)
  return String(v)
}

/**
 * Composable: считает поле-по-полю diff двух ConfigShape и рендерит в YAML / JSON / fields.
 *
 * Side A — "было" (левая колонка), Side B — "стало" (правая колонка).
 * Для preset-compare: A = текущая форма, B = preset.
 * Для history: A = snapshot старой ревизии, B = текущая форма.
 */
export function useCorrectionDiff() {
  function diffConfigs(
    sideA: ConfigShape,
    sideB: ConfigShape,
    sections: CorrectionCatalogSection[],
    phases: CorrectionPhase[],
  ): CorrectionDiff[] {
    const out: CorrectionDiff[] = []
    const scopes: Array<{ phase: 'base' | CorrectionPhase; a: Record<string, unknown>; b: Record<string, unknown> }> = [
      { phase: 'base', a: sideA.base, b: sideB.base },
      ...phases.map((ph) => ({ phase: ph, a: sideA.phases[ph] ?? {}, b: sideB.phases[ph] ?? {} })),
    ]
    for (const scope of scopes) {
      for (const section of sections) {
        for (const field of section.fields) {
          const oldVal = getByPath(scope.a, field.path)
          const newVal = getByPath(scope.b, field.path)
          if (!areEq(oldVal, newVal)) {
            out.push({
              section: section.key,
              sectionLabel: section.label,
              path: field.path,
              label: field.label,
              phase: scope.phase,
              oldVal,
              newVal,
            })
          }
        }
      }
    }
    return out
  }

  function groupBySection(diffs: CorrectionDiff[]): Array<{ section: string; label: string; phase: string; items: CorrectionDiff[] }> {
    const buckets = new Map<string, { section: string; label: string; phase: string; items: CorrectionDiff[] }>()
    for (const d of diffs) {
      const key = `${d.phase}::${d.section}`
      if (!buckets.has(key)) buckets.set(key, { section: d.section, label: d.sectionLabel, phase: d.phase, items: [] })
      buckets.get(key)!.items.push(d)
    }
    return Array.from(buckets.values())
  }

  function renderDiffYaml(diffs: CorrectionDiff[]): { before: DiffLine[]; after: DiffLine[] } {
    const before: DiffLine[] = []
    const after: DiffLine[] = []
    let n = 0
    for (const grp of groupBySection(diffs)) {
      n += 1
      const header = `# ${grp.phase === 'base' ? 'base' : `phase.${grp.phase}`} · ${grp.section}`
      before.push({ t: 'hdr', n: '', c: header })
      after.push({ t: 'hdr', n: '', c: header })
      for (const item of grp.items) {
        n += 1
        const leaf = item.path.split('.').pop() ?? item.path
        if (item.oldVal !== undefined) {
          before.push({ t: 'del', n: String(n), c: `  ${leaf}: ${fmtVal(item.oldVal)}` })
        } else {
          before.push({ t: 'ctx', n: String(n), c: `  # ${leaf}: <unset>` })
        }
        if (item.newVal !== undefined) {
          after.push({ t: 'add', n: String(n), c: `  ${leaf}: ${fmtVal(item.newVal)}` })
        } else {
          after.push({ t: 'ctx', n: String(n), c: `  # ${leaf}: <unset>` })
        }
      }
    }
    return { before, after }
  }

  function renderDiffJson(diffs: CorrectionDiff[]): { before: DiffLine[]; after: DiffLine[] } {
    const before: DiffLine[] = []
    const after: DiffLine[] = []
    before.push({ t: 'ctx', n: '1', c: '{' })
    after.push({ t: 'ctx', n: '1', c: '{' })
    let n = 1
    for (const grp of groupBySection(diffs)) {
      n += 1
      const scopeKey = grp.phase === 'base' ? 'base' : `phase_overrides.${grp.phase}`
      before.push({ t: 'ctx', n: String(n), c: `  "${scopeKey}": {` })
      after.push({ t: 'ctx', n: String(n), c: `  "${scopeKey}": {` })
      for (const item of grp.items) {
        n += 1
        if (item.oldVal !== undefined) {
          before.push({ t: 'del', n: String(n), c: `    "${item.path}": ${JSON.stringify(item.oldVal)},` })
        }
        if (item.newVal !== undefined) {
          after.push({ t: 'add', n: String(n), c: `    "${item.path}": ${JSON.stringify(item.newVal)},` })
        }
      }
      n += 1
      before.push({ t: 'ctx', n: String(n), c: '  },' })
      after.push({ t: 'ctx', n: String(n), c: '  },' })
    }
    return { before, after }
  }

  function renderDiffFields(diffs: CorrectionDiff[]): { before: DiffLine[]; after: DiffLine[] } {
    const before: DiffLine[] = []
    const after: DiffLine[] = []
    let n = 0
    for (const grp of groupBySection(diffs)) {
      n += 1
      const hdr = `${grp.phase === 'base' ? 'Base' : `Phase: ${grp.phase}`} → ${grp.label}`
      before.push({ t: 'hdr', n: '', c: hdr })
      after.push({ t: 'hdr', n: '', c: hdr })
      for (const item of grp.items) {
        n += 1
        before.push({ t: 'del', n: String(n), c: `${item.label}: ${fmtVal(item.oldVal)}` })
        after.push({ t: 'add', n: String(n), c: `${item.label}: ${fmtVal(item.newVal)}` })
      }
    }
    return { before, after }
  }

  return { diffConfigs, groupBySection, renderDiffYaml, renderDiffJson, renderDiffFields }
}
