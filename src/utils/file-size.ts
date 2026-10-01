export type StorageDisplayUnit = 'GB' | 'MB' | 'KB'

export function storageDisplayUnit(gb: number | null | undefined): StorageDisplayUnit | null {
  if (gb == null || !Number.isFinite(gb) || gb < 0) return null
  if (gb === 0) return 'KB'
  const exponent = Math.floor(Math.log10(gb))
  if (exponent >= 0) return 'GB'
  if (exponent >= -4) return 'MB'
  return 'KB'
}

function numericStorage(gb: number | null | undefined): { value: number; unit: StorageDisplayUnit } | null {
  const unit = storageDisplayUnit(gb)
  if (unit == null || gb == null) return null
  const factor = unit === 'GB' ? 1 : unit === 'MB' ? 1024 : 1024 * 1024
  return { value: gb * factor, unit }
}

export function formatStorageValue(gb: number | null | undefined): string {
  const value = numericStorage(gb)
  if (value == null) return '—'
  return value.value.toFixed(2)
}

export function formatStorage(gb: number | null | undefined): string {
  const value = formatStorageValue(gb)
  const unit = storageDisplayUnit(gb)
  return value === '—' || unit == null ? value : `${value}${unit}`
}
