import type { Kpi, TaskStatus } from './index'
export type ResourceView = 'overview' | 'ingest' | 'datasets' | 'statistics'
export interface Distribution {
  name: string
  value: number
  count?: number
  code?: string
}
export interface ResourceDataset {
  id: number
  name: string
  sourceType: 'internet' | 'industry' | 'business' | 'synthetic'
  sourceName: string
  modalities: string[]
  languages: string[]
  rowCount: number
  storageGb: number
  qualityScore: number
  qualityStatus: 'excellent' | 'good' | 'poor'
  status: 'uploading' | 'ready' | 'processing' | 'archived'
  versionId: string
  owner: string
  description: string
  createdAt: string
  updatedAt: string
  statistics?: {
    qualityDimensions?: Distribution[]
    issues?: Distribution[]
    usageCount?: number
    storageEvents?: { at: string; deltaGb: number }[]
  }
}
export interface IngestTask {
  taskId: string
  name: string
  sourceName: string
  datasetName: string
  storageGb: number
  progress: number
  status: TaskStatus
  createdAt: string
  successCount: number
  duplicateCount: number
  anomalyCount: number
  traceId: string
  datasetId?: number
  datasetVersionId?: string
  result?: {
    error?: string
    error_code?: string
    error_type?: string
    duplicate_dataset_id?: number
    statistics?: {
      basis?: string
      total_rows?: number
      success_count?: number
      duplicate_count?: number
      anomaly_count?: number
      inserted_count?: number
      title_missing_count?: number
      content_column_found?: boolean
      cross_batch_dedup_skipped?: boolean
      totalRows?: number
      successCount?: number
      duplicateCount?: number
      anomalyCount?: number
      insertedCount?: number
      titleMissingCount?: number
      contentColumnFound?: boolean
      crossBatchDedupSkipped?: boolean
    }
    [key: string]: unknown
  }
}
export interface ResourceSummary {
  asOf?: string
  kpis: Kpi[]
  trend: { dates: string[]; added: number[]; total: number[] }
  modalities: Distribution[]
  sources: Distribution[]
  languages: Distribution[]
  quality: Distribution[]
  qualityScore: number | null
  issues: Distribution[]
  ranking: { name: string; source: string; storageGb: number; uses: number; share: number }[]
  filters?: StatisticsQuery
  generatedAt?: string
  datasetIds?: number[]
  modalityCount?: number
  basis?: {
    languages: string
    modalities: string
    sources: string
    quality: string
    trend: string
    issues: string
    ranking: string
  }
  options?: ResourceFilterOptions
}
export interface ResourceFilterOptions {
  languages: { code: string; name: string }[]
  sources: { code: string; name: string }[]
  modalities: string[]
}
/** 日快照保存各数据集、各任务的原始状态，不保存预先编写的涨跌幅。 */
export type ResourceKpiDataset = Pick<ResourceDataset,
  'id' | 'sourceType' | 'sourceName' | 'languages' | 'createdAt' |
  'rowCount' | 'storageGb' | 'status' | 'qualityStatus'>
export type ResourceKpiTask = Pick<IngestTask, 'taskId' | 'datasetId' | 'status' | 'createdAt'>
export interface ResourceDailyComparison {
  currentAt: string
  previousAt: string
  datasets: ResourceKpiDataset[]
  tasks: ResourceKpiTask[]
}
export interface DatasetQuery {
  page: number
  pageSize: number
  keyword?: string
  modality?: string
  language?: string
  sourceType?: string
  qualityStatus?: string
}
export interface StatisticsQuery {
  startDate?: string
  endDate?: string
  sourceType?: string
  datasetId?: number
  language?: string
}

export interface ResourceSample {
  id: string
  datasetId: number
  versionId: string
  text: string
  language: string
}
