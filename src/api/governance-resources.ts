import { listDatasets } from './data-resource'
import { isMock, request } from './request'
import { languageName } from '../utils/governance-language'
import type { GovernanceResource } from '../types/governance-resources'
import type { PageResult } from '../types'
/** 四个治理模块共用资源目录；模块 options 仅提供规则、方案与动作。 */
export async function getGovernanceResources(): Promise<GovernanceResource[]> {
  if (isMock) return (await import('../mock/governance-resources')).governanceResources()
  const datasets: GovernanceResource[] = []
  let page = 1
  while (true) {
    const resources = await listDatasets({ page, pageSize: 100 })
    for (const d of resources.items) {
      const versions: GovernanceResource['versions'] = []
      let versionPage = 1
      while (true) {
        const response = await request<
          PageResult<{
            id: number
            versionId?: string
            version_id?: string
            version?: string
            label?: string
            languages: string[]
          }>
        >({ url: `/datasets/${d.id}/versions`, params: { page: versionPage, pageSize: 100 } })
        versions.push(
          ...response.items.map((v) => {
            // 版本标识必须是版本号字符串，不能是 dataset_versions 的自增主键 id。
            const versionId = String(v.versionId ?? v.version_id ?? v.version ?? v.label ?? '')
            return {
              id: versionId,
              label: String(v.label ?? versionId),
              languages: v.languages.map((code) => ({ code, name: languageName(code) })),
            }
          }),
        )
        if (versions.length >= response.total) break
        if (!response.items.length) throw new Error('资源版本分页不完整')
        versionPage++
      }
      datasets.push({ id: d.id, name: d.name, versions })
    }
    if (datasets.length >= resources.total) break
    if (!resources.items.length) throw new Error('数据集分页不完整')
    page++
  }
  return datasets
}
