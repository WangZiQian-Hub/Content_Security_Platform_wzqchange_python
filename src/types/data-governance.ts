import type { Kpi, TaskStatus } from './index'
export const PROCESS_KIND = 'governance-process'
export interface ProcessKpi extends Kpi {
  // 仅成功率卡片使用；由后端返回实际成功任务数，不能由四舍五入后的百分比反推。
  succeededCount?: number
}
export interface ProcessInput {
  datasetId: number
  datasetVersionId: string
  // 用户指定的输出版本名称；旧任务和不生成版本的预览可以没有此字段。
  outputVersionName?: string
  scope: 'all' | 'batch' | 'filtered'
  batchId?: string
  filter?: { keyword: string }
  rules: string[]
  templateId: string
}
export type ProcessCreateInput = ProcessInput
export interface ProcessOptions {
  datasets: { id: number; name: string; versions: { versionId: string; label: string }[] }[]
  rules: { code: string; label: string; description: string }[]
  templates: { id: string; name: string; rules: string[] }[]
}
export interface ProcessComparison {
  id: string
  original: string
  processed: string
  actions: string[]
  fields: { name: string; before: string; after: string }[]
}
export interface ProcessTask {
  taskId: string
  name: string
  datasetName: string
  input: ProcessInput
  ruleName: string
  // 后端生成的不可变数据版本 ID，与用户填写的名称分开保存。
  outputVersion: string | null
  status: TaskStatus
  progress: number
  processedCount: number
  totalCount: number
  remainingSeconds: number | null
  steps: { name: string; status: TaskStatus }[]
  comparisons: ProcessComparison[]
  createdAt: string
  finishedAt: string | null
  traceId: string
  errorMessage?: string
}
export interface ProcessPreview {
  items: ProcessComparison[]
  sampleCount: number
}
