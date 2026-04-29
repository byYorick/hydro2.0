export type CsvCell = string | number | null | undefined

const escapeCell = (value: CsvCell): string => {
  if (value === null || value === undefined) {
    return ''
  }

  const raw = String(value)
  if (raw.includes('"') || raw.includes(',') || raw.includes('\n')) {
    return `"${raw.replace(/"/g, '""')}"`
  }

  return raw
}

export const toIsoTimestamp = (timestampMs: number): string => {
  return new Date(timestampMs).toISOString()
}

export function downloadCsv(filename: string, rows: CsvCell[][]): void {
  if (typeof window === 'undefined' || rows.length === 0) {
    return
  }

  const csv = rows
    .map((row) => row.map((cell) => escapeCell(cell)).join(','))
    .join('\n')

  const blob = new Blob([csv], { type: 'text/csv;charset=utf-8;' })
  const url = URL.createObjectURL(blob)
  const link = document.createElement('a')
  link.href = url
  link.download = filename
  link.click()
  URL.revokeObjectURL(url)
}
