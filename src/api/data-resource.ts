import { isMock, request } from './request'
import { getResourceSummary, ingestTasks, resourceDatasets } from '../mock/data-resource'
import type { PageResult, ExecuteTaskReq, Task } from '../types'
import type {
  DatasetQuery,
  IngestTask,
  ResourceDataset,
  ResourceSummary,
  ResourceView,
  StatisticsQuery,
  ResourceFilterOptions,
} from '../types/data-resource'
export async function getSummary(
  view: ResourceView,
  filters: StatisticsQuery = {},
): Promise<ResourceSummary> {
  if (isMock) return getResourceSummary(view, filters)
  return request({ url: '/data-resources/summary', params: { view, ...filters } })
}
export async function getResourceFilterOptions(): Promise<ResourceFilterOptions> {
  if (isMock) return (await import('../mock/resource-statistics')).resourceFilterOptions()
  return request({ url: '/data-resources/options' })
}
export async function listDatasets(query: DatasetQuery): Promise<PageResult<ResourceDataset>> {
  if (!isMock) return request({ url: '/datasets', params: query })
  const rows = resourceDatasets.filter(
    (row) =>
      (!query.keyword || row.name.includes(query.keyword)) &&
      (!query.modality || row.modalities.includes(query.modality)) &&
      (!query.language || row.languages.includes(query.language)) &&
      (!query.sourceType || row.sourceType === query.sourceType) &&
      (!query.qualityStatus || row.qualityStatus === query.qualityStatus),
  )
  return {
    items: rows.slice((query.page - 1) * query.pageSize, query.page * query.pageSize),
    total: rows.length,
    page: query.page,
    pageSize: query.pageSize,
    totalPages: Math.ceil(rows.length / query.pageSize),
  }
}
export function getDataset(id: number): Promise<ResourceDataset> {
  if (isMock) {
    const dataset = resourceDatasets.find((row) => row.id === id)
    return dataset ? Promise.resolve(dataset) : Promise.reject(new Error('数据集不存在'))
  }
  return request({ url: `/datasets/${id}` })
}
export async function listIngestTasks(query: {
  page: number
  pageSize: number
  keyword?: string
  status?: string
}): Promise<PageResult<IngestTask> & { succeededTotal: number }> {
  if (!isMock)
    return request({ url: '/tasks', params: { ...query, capabilityCode: 'data_ingest' } })
  const rows = ingestTasks.filter(
    (row) =>
      (!query.keyword || `${row.name}${row.sourceName}`.includes(query.keyword)) &&
      (!query.status || row.status === query.status),
  )
  return {
    items: rows.slice((query.page - 1) * query.pageSize, query.page * query.pageSize),
    total: rows.length,
    page: query.page,
    pageSize: query.pageSize,
    totalPages: Math.ceil(rows.length / query.pageSize),
    // 保留旧字段名兼容已有调用方；数值改为成功任务的样本条数总和。
    succeededTotal: rows
      .filter((row) => row.status === 'succeeded')
      .reduce((total, row) => total + (row.result?.statistics?.total_rows ?? 0), 0),
  }
}
// 写入始终走真实接口；不生成模拟成功或伪造任务留痕。
export function saveDataset(data: Partial<ResourceDataset>) {
  return request<ResourceDataset>({
    url: data.id ? `/datasets/${data.id}` : '/datasets',
    method: data.id ? 'PATCH' : 'POST',
    data,
  })
}
export function deleteDataset(id: number) {
  return request<void>({ url: `/datasets/${id}`, method: 'DELETE' })
}
export function uploadResourceFile(file: File) {
  const data = new FormData()
  data.append('file', file)
  return request<{ fileId: string }>({ url: '/files', method: 'POST', data })
}
export function startIngest(data: ExecuteTaskReq) {
  return request<Task>({ url: '/tasks/execute', method: 'POST', data, timeout: 300000 })
}

export async function getResourceSamples(datasetId: number, versionId: string, ids: string[]) {
  if (isMock) {
    const { resourceVersionSamples } = await import('../mock/governance-resources')
    return resourceVersionSamples(datasetId, versionId).filter((row) => ids.includes(row.id))
  }
  return request<import('../types/data-resource').ResourceSample[]>({
    url: `/datasets/${datasetId}/versions/${encodeURIComponent(versionId)}/samples`,
    params: { ids },
  })
}
