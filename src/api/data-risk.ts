import { isMock as businessMock, request as businessRequest } from './request'
import { isGovernanceLlm, llmRequest } from './governance-llm'
import { getGovernanceResources } from './governance-resources'
import type { PageResult } from '../types'
import type {
  Options,
  Overview,
  Query,
  Result,
  ReviewInput,
  Rule,
  Sample,
  Scope,
  Task,
} from '../types/data-risk'
// 模型模式下三类分析整体改走本项目模型服务，不回落模拟结果；其余情况沿用业务请求层原来的判定。
// 这里保留为取值函数而不是常量：业务请求层的 isMock 是模块活绑定，用例会在运行过程中切换它。
const useMock = () => businessMock && !isGovernanceLlm
const request: typeof businessRequest = isGovernanceLlm ? llmRequest : businessRequest
const kind = 'governance-risk'
const base = '/data-governance/risk-results'
const path = (id: string) => `${base}/${encodeURIComponent(id)}`
const samplePath = (id: string, sample: string) =>
  `${path(id)}/samples/${encodeURIComponent(sample)}`
const mock = async () => (await import('../mock/data-risk')).riskMock
export async function getRiskOptions(): Promise<Options> {
  const [options, datasets] = await Promise.all([
    useMock()
      ? (await mock()).options()
      : request<Options>({ url: '/data-governance/risk-options', params: { kind } }),
    getGovernanceResources(),
  ])
  const dataset =
    datasets.find((d) => d.id === options.defaultScope.datasetId && d.versions.length) ||
    datasets.find((d) => d.versions.length)
  if (!dataset) throw new Error('没有可用的数据资源版本')
  const version =
    dataset.versions.find((v) => v.id === options.defaultScope.versionId) || dataset.versions[0]!
  return {
    ...options,
    defaultScope: {
      ...options.defaultScope,
      datasetId: dataset.id,
      versionId: version.id,
      language: version.languages.some((l) => l.code === options.defaultScope.language)
        ? options.defaultScope.language
        : 'all',
    },
    datasets: datasets.map((d) => ({
      ...d,
      versions: d.versions.map((v) => ({ ...v, languages: v.languages.map((l) => l.code) })),
    })),
  }
}
export async function getRiskOverview(): Promise<Overview> {
  return useMock()
    ? (await mock()).overview()
    : request({ url: '/data-governance/risk-overview', params: { kind } })
}
export async function getLatestRisk(scope: Scope): Promise<Result | null> {
  return useMock()
    ? (await mock()).latest(scope)
    : request({ url: `${base}/latest`, params: { kind, ...scope } })
}
export async function getRiskResult(id: string): Promise<Result> {
  return useMock() ? (await mock()).result(id) : request({ url: path(id) })
}
export async function listRiskSamples(id: string, q: Query): Promise<PageResult<Sample>> {
  return useMock()
    ? (await mock()).samples(id, q)
    : request({ url: `${path(id)}/samples`, params: { ...q } })
}
export async function getRiskSample(id: string, sample: string): Promise<Sample> {
  return useMock() ? (await mock()).detail(id, sample) : request({ url: samplePath(id, sample) })
}
export async function getRiskHistory(scope: Scope): Promise<Result[]> {
  return useMock() ? (await mock()).history(scope) : request({ url: base, params: { kind, ...scope } })
}
export async function startRisk(scope: Scope): Promise<Task> {
  if (useMock()) return (await mock()).start(scope)
  return normalizeTask(
    await request<TaskResponse>({
      url: '/data-governance/risk-tasks',
      method: 'POST',
      data: { kind, name: '内容风险识别与分级', input: scope },
    }),
  )
}
type TaskResponse = Omit<Task, 'id'> & { id?: string; taskId?: string }
function normalizeTask(task: TaskResponse): Task {
  const id = task.taskId || task.id
  if (!id) throw new Error('任务接口缺少任务标识')
  return { ...task, id }
}
export async function getRiskTask(id: string): Promise<Task> {
  if (useMock()) return (await mock()).task(id)
  return normalizeTask(
    await request<TaskResponse>({
      url: `/data-governance/risk-tasks/${encodeURIComponent(id)}`,
      params: { kind },
    }),
  )
}
export async function reviewRisk(
  id: string,
  sample: string,
  revisionId: string,
  input: ReviewInput,
  reviewId?: string,
): Promise<Sample> {
  return useMock()
    ? (await mock()).review(id, sample, revisionId, input, reviewId)
    : request({
        url: `${samplePath(id, sample)}/reviews`,
        method: 'POST',
        data: { inputSampleRevisionId: revisionId, reviewId, ...input },
      })
}
export async function searchRiskKnowledge(
  id: string,
  sample: string,
  keyword: string,
): Promise<Rule[]> {
  return useMock()
    ? (await mock()).knowledge(id, sample, keyword)
    : request({ url: '/risk-knowledge', params: { resultId: id, sampleId: sample, keyword } })
}
export async function exportRiskSamples(id: string, q: Query): Promise<Sample[]> {
  if (useMock()) return (await mock()).export(id, q)
  // 由服务端导出当前保存结果下全部匹配记录，不传分页窗口。
  return request({
    url: `${path(id)}/export`,
    method: 'POST',
    data: { keyword: q.keyword, level: q.level, status: q.status },
  })
}
