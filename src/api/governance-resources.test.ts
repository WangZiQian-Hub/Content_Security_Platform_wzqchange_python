import { beforeEach, describe, expect, it, vi } from 'vitest'
const backend = vi.hoisted(() => ({ isMock: true, request: vi.fn() }))
vi.mock('./request', () => backend)
vi.mock('./governance-llm', () => ({ isGovernanceLlm: false, llmRequest: vi.fn() }))
import { getGovernanceResources } from './governance-resources'
import { getProcessOptions, listProcessTasks } from './data-governance'
import { getValueOptions, getLatestValueResult, exportValueSamples } from './data-value'
import {
  getAnomalyOptions,
  getLatestAnomaly,
  checkAnomalyVersion,
  publishAnomalyVersion,
  startAnomaly,
  getAnomalyTask,
  getAnomalyResult,
} from './data-anomaly'
import { getRiskOptions, getLatestRisk, startRisk, getRiskTask, getRiskResult } from './data-risk'
import { getResourceSamples } from './data-resource'
import { resourceSamples } from '../mock/resource-samples'
import { getProcessKpis } from '../mock/data-governance'
import { languageName } from '../utils/governance-language'
const scope = {
  datasetId: 3,
  versionId: 'dsv_000003',
  language: 'zh',
  schemeId: 'anomaly-basic-v1',
}
const query = { page: 7, pageSize: 7, tier: 'all' as const, keyword: '', bin: '' }
async function options() {
  const [process, value, anomaly, risk] = await Promise.all([
    getProcessOptions(),
    getValueOptions(),
    getAnomalyOptions(),
    getRiskOptions(),
  ])
  return { process, value, anomaly, risk }
}
describe('数据治理统一资源目录及跨页版本链路', () => {
  beforeEach(() => {
    backend.isMock = true
    backend.request.mockReset()
  })
  it('四页共享六个数据集、顺序、名称、版本和语种，移除虚构 previous 版本', async () => {
    const { process, value, anomaly, risk } = await options()
    const catalog = await getGovernanceResources()
    expect(catalog).toHaveLength(6)
    expect(value.datasets).toEqual(catalog)
    expect(anomaly.datasets).toEqual(catalog)
    expect(
      process.datasets.map((d) => ({
        id: d.id,
        name: d.name,
        versions: d.versions.map((v) => v.versionId),
      })),
    ).toEqual(
      catalog.map((d) => ({ id: d.id, name: d.name, versions: d.versions.map((v) => v.id) })),
    )
    expect(catalog.every((d) => d.versions.every((v) => typeof v.id === 'string'))).toBe(true)
    expect(
      risk.datasets.map((d) => ({
        id: d.id,
        name: d.name,
        versions: d.versions.map((v) => ({ id: v.id, languages: v.languages })),
      })),
    ).toEqual(
      catalog.map((d) => ({
        id: d.id,
        name: d.name,
        versions: d.versions.map((v) => ({ id: v.id, languages: v.languages.map((l) => l.code) })),
      })),
    )
    expect(JSON.stringify(catalog)).not.toContain('_previous')
    expect(['zh', 'en', 'ja', 'all'].map(languageName)).toEqual([
      '中文',
      '英文',
      '日文',
      '全部语种',
    ])
    for (const d of catalog)
      for (const v of d.versions)
        expect(v.languages.every((l) => l.name === languageName(l.code))).toBe(true)
  })
  it('同一固定条件共享目标样本集合；有效评分数与风险候选数允许不同', async () => {
    const v = (await getLatestValueResult({ ...scope, schemeId: 'general-v1' }))!
    const a = (await getLatestAnomaly(scope))!
    // 风险已有全语种快照，中文查询需创建独立任务，不借用全语种结果。
    const task = await startRisk({ ...scope, schemeId: 'risk-v1' })
    const done = await getRiskTask(task.id)
    const r = await getRiskResult(done.resultId!)
    const source = resourceSamples.filter(
      (s) =>
        s.datasetId === scope.datasetId &&
        s.versionId === scope.versionId &&
        s.language === scope.language,
    )
    expect(v.targetCount).toBe(source.length)
    expect(a.validCount).toBe(source.length)
    expect(r.validCount).toBe(source.length)
    expect(v.validCount + v.unavailableCount + v.failedCount).toBe(source.length)
    const exported = await exportValueSamples(v.id, query)
    expect(exported.map((s) => s.id).sort()).toEqual(source.map((s) => s.id).sort())
    expect(exported.every((s) => s.language === 'zh')).toBe(true)
    expect(await exportValueSamples(v.id, { ...query, keyword: exported[0]!.id })).toHaveLength(1)
  })
  it('历史清洗任务计数对应资源集合，输出版本可读且保留原样本ID', async () => {
    const tasks = (await listProcessTasks(1, 20)).items
    for (const t of tasks) {
      const source = resourceSamples.filter(
        (s) => s.datasetId === t.input.datasetId && s.versionId === t.input.datasetVersionId,
      )
      expect(t.totalCount).toBe(source.length)
      expect(t.processedCount).toBeLessThanOrEqual(t.totalCount)
      if (!t.outputVersion) continue
      const output = await getResourceSamples(
        t.input.datasetId,
        t.outputVersion,
        source.map((s) => s.id),
      )
      expect(output.map((s) => s.id)).toEqual(source.map((s) => s.id))
      for (const c of t.comparisons) {
        expect(source.find((s) => s.id === c.id)!.text).toBe(c.original)
        expect(output.find((s) => s.id === c.id)!.text).toBe(c.processed)
      }
    }
    expect(getProcessKpis()[0]!.value).toBe(
      tasks.filter((task) => ['succeeded', 'failed'].includes(task.status)).length,
    )
    expect(getProcessKpis()[2]!.value).toBe(tasks.reduce((n, t) => n + t.processedCount, 0))
  })
  it('异常修复新版本进入四页目录与资源读取；旧版本不变，新版本需重新分析', async () => {
    const old = structuredClone(resourceSamples)
    const before = (await getLatestAnomaly(scope))!
    const check = await checkAnomalyVersion(scope)
    const published = await publishAnomalyVersion(scope, check.token)
    const next = { ...scope, versionId: published.newDatasetVersionId }
    const all = await options()
    for (const option of [all.value, all.anomaly, all.risk])
      expect(
        option.datasets
          .find((d) => d.id === scope.datasetId)
          ?.versions.some((v) => v.id === next.versionId),
      ).toBe(true)
    expect(
      all.process.datasets
        .find((d) => d.id === scope.datasetId)
        ?.versions.some((v) => v.versionId === next.versionId),
    ).toBe(true)
    const resources = await getResourceSamples(
      scope.datasetId,
      next.versionId,
      old.filter((s) => s.datasetId === scope.datasetId).map((s) => s.id),
    )
    expect(resources).toHaveLength(120)
    expect(resourceSamples).toEqual(old)
    expect(await getLatestValueResult({ ...next, schemeId: 'general-v1' })).toBeNull()
    expect(await getLatestRisk({ ...next, schemeId: 'risk-v1' })).toBeNull()
    vi.useFakeTimers()
    try {
      const t = await startAnomaly(next)
      vi.advanceTimersByTime(1500)
      const done = await getAnomalyTask(t.taskId)
      const result = await getAnomalyResult(done.resultId!)
      expect(result.validCount).toBe(before.validCount)
      expect(result.anomalyCount).toBe(before.anomalyCount - check.count)
    } finally {
      vi.useRealTimers()
    }
  })
  it('正式模式从同一资源API遍历数据集和版本分页，忽略模块中的旧目录', async () => {
    const config = await options()
    backend.isMock = false
    backend.request.mockImplementation(async ({ url, params }) => {
      if (url === '/datasets')
        return {
          items: [{ id: params.page === 1 ? 91 : 92, name: `统一资源${params.page}` }],
          total: 2,
        }
      if (/\/datasets\/\d+\/versions/.test(url))
        return {
          items: [
            {
              id: params.page,
              version_id: `v1.0.${params.page}`,
              version: `v1.0.${params.page}`,
              label: `版本${params.page}`,
              languages: ['zh', 'en'],
            },
          ],
          total: 2,
        }
      if (url === '/data-governance/risk-options') return config.risk
      return params.kind === 'governance-process'
        ? config.process
        : params.kind === 'governance-value'
          ? config.value
          : config.anomaly
    })
    const all = await options()
    for (const page of Object.values(all)) expect(page.datasets.map((d) => d.id)).toEqual([91, 92])
    expect(all.value.datasets[0]!.versions.map((v) => v.id)).toEqual(['v1.0.1', 'v1.0.2'])
    expect(all.value.datasets[0]!.versions.every((v) => typeof v.id === 'string')).toBe(true)
    expect(all.value.datasets[0]!.versions.map((v) => v.id)).not.toContain('1')
    expect(all.risk.defaultScope.datasetId).toBe(91)
    expect(backend.request).toHaveBeenCalledWith({
      url: '/datasets',
      params: { page: 2, pageSize: 100 },
    })
    backend.request.mockRejectedValue(new Error('资源服务不可用'))
    await expect(getValueOptions()).rejects.toThrow('资源服务不可用')
  })
})
