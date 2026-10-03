import { isMock as businessMock, request as businessRequest } from './request'
import { isGovernanceLlm, llmRequest } from './governance-llm'
import { getGovernanceResources } from './governance-resources'
import { latestDemoResult, savedDemoResult, valueOptions } from '../mock/data-value'
import { getResourceSamples } from './data-resource'
import { VALUE_KIND } from '../types/data-value'
import type {
  ValueOptions,
  ValueResult,
  ValueSample,
  ValueSampleQuery,
  ValueScope,
  ValueTask,
} from '../types/data-value'
import type { PageResult } from '../types'
// 模型模式下三类分析整体改走本项目模型服务，不回落模拟结果；其余情况沿用业务请求层原来的判定。
// 这里保留为取值函数而不是常量：业务请求层的 isMock 是模块活绑定，用例会在运行过程中切换它。
const useMock = () => businessMock && !isGovernanceLlm
const request: typeof businessRequest = isGovernanceLlm ? llmRequest : businessRequest

export async function getValueOptions(): Promise<ValueOptions> {
  const [options, datasets] = await Promise.all([
    useMock()
      ? structuredClone(valueOptions)
      : request<ValueOptions>({ url: '/data-governance/options', params: { kind: VALUE_KIND } }),
    getGovernanceResources(),
  ])
  return { ...options, datasets }
}
export async function getLatestValueResult(scope: ValueScope): Promise<ValueResult | null> {
  return useMock()
    ? latestDemoResult(scope)
    : request({ url: '/data-governance/value-results/latest', params: scope })
}
export async function getValueResult(id: string): Promise<ValueResult> {
  return useMock()
    ? savedDemoResult(id).result
    : request({ url: `/data-governance/value-results/${encodeURIComponent(id)}` })
}
export async function listValueSamples(
  id: string,
  query: ValueSampleQuery,
): Promise<PageResult<ValueSample>> {
  if (!useMock()) {
    const [result, page] = await Promise.all([
      getValueResult(id),
      request<PageResult<ValueSample>>({
        url: `/data-governance/value-results/${encodeURIComponent(id)}/samples`,
        params: query,
      }),
    ])
    const resources = await getResourceSamples(
      result.scope.datasetId,
      result.scope.versionId,
      page.items.map((row) => row.id),
    )
    page.items = page.items.map((row) => {
      const sample = resources.find((item) => item.id === row.id)
      if (
        !sample ||
        (sample.datasetId != null && sample.datasetId !== result.scope.datasetId) ||
        (sample.versionId != null && sample.versionId !== result.scope.versionId) ||
        sample.text !== row.text
      )
        throw new Error('评分样本与数据资源版本不一致')
      return { ...row, id: sample.id, text: sample.text, language: sample.language }
    })
    return page
  }
  const rows = savedDemoResult(id).samples.filter(
    (item) =>
      (query.tier === 'all' || item.tier === query.tier) &&
      (!query.keyword || `${item.id}${item.text}`.includes(query.keyword)) &&
      (!query.bin ||
        (item.score !== null && String(Math.min(4, Math.floor(item.score / 20))) === query.bin)),
  )
  if (query.sortBy && query.sortOrder) {
    const ranks = { low: 0, medium: 1, high: 2, unavailable: -1 }
    const direction = query.sortOrder === 'asc' ? 1 : -1
    rows.sort((a, b) => {
      const aUnavailable = a.score === null || a.tier === 'unavailable'
      const bUnavailable = b.score === null || b.tier === 'unavailable'
      // 无论升降序，不可评估均置底；同值按资源 ID 稳定排序。
      if (aUnavailable !== bUnavailable) return aUnavailable ? 1 : -1
      const difference = aUnavailable
        ? 0
        : query.sortBy === 'score'
          ? a.score! - b.score!
          : ranks[a.tier] - ranks[b.tier]
      return difference * direction || a.id.localeCompare(b.id, 'en', { numeric: true })
    })
  }
  return {
    items: rows.slice((query.page - 1) * query.pageSize, query.page * query.pageSize),
    total: rows.length,
    page: query.page,
    pageSize: query.pageSize,
    totalPages: Math.ceil(rows.length / query.pageSize),
  }
}
export async function listValueTasks(scope: ValueScope): Promise<PageResult<ValueTask>> {
  if (!useMock())
    return request({ url: '/tasks', params: { kind: VALUE_KIND, ...scope, page: 1, pageSize: 20 } })
  const result = latestDemoResult(scope)
  return {
    items: result
      ? [
          {
            taskId: result.taskId,
            name: '数据价值分析',
            status: 'succeeded',
            createdAt: result.finishedAt,
            resultId: result.id,
          },
        ]
      : [],
    total: result ? 1 : 0,
    page: 1,
    pageSize: 20,
    totalPages: result ? 1 : 0,
  }
}
export async function exportValueSamples(
  id: string,
  query: ValueSampleQuery,
): Promise<ValueSample[]> {
  const rows: ValueSample[] = []
  let page = 1,
    expected: number | undefined
  while (true) {
    const result = await listValueSamples(id, { ...query, page })
    expected ??= result.total
    if (result.total !== expected || rows.some((s) => result.items.some((n) => n.id === s.id)))
      throw new Error('导出期间结果分页发生变化，请重试')
    rows.push(...result.items)
    if (rows.length === expected) return rows
    if (!result.items.length || rows.length > expected) throw new Error('导出记录不完整')
    page++
  }
}
export function createValueTask(scope: ValueScope): Promise<ValueTask> {
  return request({
    url: '/tasks',
    method: 'POST',
    data: { kind: VALUE_KIND, name: '数据价值分析', input: scope },
  })
}
export function getValueTask(taskId: string): Promise<ValueTask> {
  return request({ url: `/tasks/${encodeURIComponent(taskId)}`, params: { kind: VALUE_KIND } })
}
