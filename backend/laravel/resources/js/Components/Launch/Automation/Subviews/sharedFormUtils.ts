export type FieldMeta = {
  label: string
  hint: string
  details: string
}

export function toNum(event: Event): number {
  const value = Number((event.target as HTMLInputElement).value)
  return Number.isFinite(value) ? value : 0
}

export function toInt(event: Event): number {
  return Math.trunc(toNum(event))
}

export function toStr(event: Event): string {
  return (event.target as HTMLInputElement).value
}

export function createMetaResolver<T extends object>(
  source: Partial<Record<keyof T, FieldMeta>>,
  fallback: FieldMeta,
) {
  return (key: keyof T): FieldMeta => {
    const originalName = String(key)
    const base = source[key] ?? {
      ...fallback,
      label: originalName,
    }

    return {
      ...base,
      details: `${originalName}: ${base.details}`,
    }
  }
}
