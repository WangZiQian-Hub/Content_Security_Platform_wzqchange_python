import type { Distribution } from '../types/data-resource'
import { languageName } from './governance-language'

export function displayLanguageDistribution(rows: Distribution[]): Distribution[] {
  const displayed = new Map<string, Distribution>()
  for (const row of rows) {
    const name = languageName(row.name)
    const existing = displayed.get(name)
    if (existing) {
      existing.value = Math.round((existing.value + row.value) * 10) / 10
      if (existing.count !== undefined || row.count !== undefined) {
        existing.count = (existing.count ?? 0) + (row.count ?? 0)
      }
    } else {
      displayed.set(name, { ...row, name })
    }
  }
  return [...displayed.values()]
}
