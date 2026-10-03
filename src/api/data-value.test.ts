import { beforeEach, describe, expect, it, vi } from 'vitest'
const backend = vi.hoisted(() => ({ isMock: true, request: vi.fn() }))
vi.mock('./request', () => backend)
vi.mock('./governance-llm', () => ({ isGovernanceLlm: false, llmRequest: vi.fn() }))
import {
  createValueTask,
  getLatestValueResult,
  getValueResult,
  listValueSamples,
  listValueTasks,
} from './data-value'
import { getResourceSamples } from './data-resource'
import { demoSamples, getValueKpis, valueOptions } from '../mock/data-value'
import { getProcessTask } from './data-governance'
const scope = { datasetId: 3, versionId: 'dsv_000003', language: 'all', schemeId: 'general-v1' }
const query = { page: 1, pageSize: 200, tier: 'all' as const, keyword: '', bin: '' }
describe('数据价值分析口径与接口', () => {
  beforeEach(() => {
    backend.isMock = true
    backend.request.mockReset()
  })
  it('顶部指标按所有数据集的样本汇总', () => {
    const samples = valueOptions.datasets.flatMap((dataset) =>
      demoSamples({
        datasetId: dataset.id,
        versionId: dataset.versions[0]!.id,
        language: 'all',
        schemeId: 'general-v1',
      }),
    )
    const scored = samples.filter((sample) => sample.score !== null)
    const kpis = getValueKpis()
    expect(kpis[0]!.value).toBeCloseTo(
      scored.reduce((sum, sample) => sum + sample.score!, 0) / scored.length,
      1,
    )
    expect(kpis[1]!.value).toBeCloseTo(
      (samples.filter((sample) => sample.tier === 'high').length / samples.length) * 100,
      1,
    )
    expect(kpis[2]!.value).toBe(scored.length)
  })
  it('汇总、分布、分档与样本评分来自同一结果', async () => {
    const result = (await getLatestValueResult(scope))!
    const samples = await listValueSamples(result.id, query)
    expect(result.validCount + result.unavailableCount + result.failedCount).toBe(
      result.targetCount,
    )
    expect(result.bins.reduce((sum, item) => sum + item.count, 0)).toBe(result.validCount)
    expect(samples.total).toBe(result.validCount + result.unavailableCount)
    expect(samples.items.filter((item) => item.tier === 'high')).toHaveLength(result.highCount)
    for (const row of samples.items.filter((item) => item.score !== null)) {
      expect(
        row.dimensions.reduce((sum, item) => sum + item.score, 0) / row.dimensions.length,
      ).toBe(row.score)
    }
    expect((await getValueResult(result.id)).scope).toEqual(scope)
  })
  it('语种筛选是全量样本的子集；分数筛选先于分页', async () => {
    const all = (await getLatestValueResult(scope))!
    const zh = (await getLatestValueResult({ ...scope, language: 'zh' }))!
    expect(zh.targetCount).toBeLessThan(all.targetCount)
    expect(zh.languages).toEqual(['zh'])
    const filtered = await listValueSamples(all.id, { ...query, pageSize: 5, bin: '4' })
    expect(filtered.total).toBe(all.bins[4]!.count)
    expect(filtered.items.every((item) => item.score! >= 80)).toBe(true)
    const empty = await listValueSamples(all.id, { ...query, keyword: '不存在的关键词' })
    expect(empty.total).toBe(0)
  })
  it('真实结果与任务统一使用请求层，任务创建不伪造成功', async () => {
    backend.isMock = false
    await getLatestValueResult(scope)
    expect(backend.request).toHaveBeenLastCalledWith({
      url: '/data-governance/value-results/latest',
      params: scope,
    })
    await listValueTasks(scope)
    expect(backend.request).toHaveBeenLastCalledWith({
      url: '/tasks',
      params: { kind: 'governance-value', ...scope, page: 1, pageSize: 20 },
    })
    backend.isMock = true
    backend.request.mockRejectedValue(new Error('offline'))
    await expect(createValueTask(scope)).rejects.toThrow('offline')
    expect(backend.request).toHaveBeenLastCalledWith({
      url: '/tasks',
      method: 'POST',
      data: { kind: 'governance-value', name: '数据价值分析', input: scope },
    })
  })
  it('评分和档位在全部匹配数据上排序后分页，不可评估始终置底', async () => {
    const result = (await getLatestValueResult(scope))!
    const original = await listValueSamples(result.id, query)
    const ranks = { low: 0, medium: 1, high: 2, unavailable: -1 }
    for (const sortBy of ['score', 'tier'] as const) {
      for (const sortOrder of ['asc', 'desc'] as const) {
        const sorted = await listValueSamples(result.id, { ...query, sortBy, sortOrder })
        const valid = sorted.items.filter((row) => row.score !== null)
        const values = valid.map((row) => (sortBy === 'score' ? row.score! : ranks[row.tier]))
        expect(
          values.every(
            (value, index) =>
              index === 0 ||
              (sortOrder === 'asc' ? value >= values[index - 1]! : value <= values[index - 1]!),
          ),
        ).toBe(true)
        expect(sorted.items.slice(valid.length).every((row) => row.tier === 'unavailable')).toBe(
          true,
        )
        const second = await listValueSamples(result.id, {
          ...query,
          sortBy,
          sortOrder,
          page: 2,
          pageSize: 10,
        })
        expect(second.items).toEqual(sorted.items.slice(10, 20))
        expect(second.total).toBe(original.total)
      }
    }
    const filtered = await listValueSamples(result.id, {
      ...query,
      bin: '4',
      sortBy: 'score',
      sortOrder: 'asc',
      pageSize: 5,
    })
    expect(filtered.items.every((row) => row.score! >= 80)).toBe(true)
    expect(filtered.total).toBe(result.bins[4]!.count)
    expect((await listValueSamples(result.id, query)).items).toEqual(original.items)
    expect(await getValueResult(result.id)).toEqual(result)
  })
  it('真实接口携带全量排序参数，前端不做当前页排序', async () => {
    const result = (await getLatestValueResult(scope))!
    const samples = await listValueSamples(result.id, { ...query, pageSize: 2 })
    const resources = await getResourceSamples(
      scope.datasetId,
      scope.versionId,
      samples.items.map((row) => row.id),
    )
    backend.isMock = false
    backend.request.mockImplementation(({ url }: { url: string }) =>
      Promise.resolve(
        url.startsWith('/datasets/') ? resources : url.endsWith('/samples') ? samples : result,
      ),
    )
    const sortedQuery = { ...query, sortBy: 'score' as const, sortOrder: 'desc' as const }
    await listValueSamples(result.id, sortedQuery)
    expect(backend.request).toHaveBeenCalledWith({
      url: `/data-governance/value-results/${result.id}/samples`,
      params: sortedQuery,
    })
  })
})

describe('精确历史与共享资源身份', () => {
  beforeEach(() => {
    backend.isMock = true
    backend.request.mockReset()
  })
  it('无历史的每个范围维度均返回 null，不创建任务', async () => {
    for (const change of [
      { datasetId: 999 },
      { versionId: 'dsv_000003_previous' },
      { language: 'en' },
      { schemeId: 'general-v2' },
    ]) {
      const emptyScope = { ...scope, ...change }
      expect(await getLatestValueResult(emptyScope)).toBeNull()
      expect((await listValueTasks(emptyScope)).items).toEqual([])
    }
    expect(backend.request).not.toHaveBeenCalled()
  })
  it('评分、清洗与资源接口共用 ID，证据属于原文，总体统计稳定', async () => {
    const before = getValueKpis()
    const result = (await getLatestValueResult(scope))!
    const page = await listValueSamples(result.id, query)
    const resources = await getResourceSamples(
      scope.datasetId,
      scope.versionId,
      page.items.map((row) => row.id),
    )
    for (const row of page.items) {
      expect(resources.find((sample) => sample.id === row.id)?.text).toBe(row.text)
      expect(row.id).not.toMatch(/^V-/)
      expect(row.id).not.toBe(scope.versionId)
      for (const dim of row.dimensions) {
        expect(dim.evidence?.length).toBeGreaterThan(0)
        expect(dim.evidence?.every((quote) => row.text.includes(quote))).toBe(true)
      }
    }
    const process = await getProcessTask('demo_process_008')
    expect(process.comparisons.map((row) => row.id)).toEqual(
      page.items.slice(0, 2).map((row) => row.id),
    )
    await getLatestValueResult({ ...scope, language: 'en' })
    expect(getValueKpis()).toEqual(before)
    expect(backend.request).not.toHaveBeenCalled()
  })
  it('拒绝资源服务中不存在的评分样本', async () => {
    const result = (await getLatestValueResult(scope))!
    const page = await listValueSamples(result.id, { ...query, pageSize: 1 })
    backend.isMock = false
    backend.request.mockImplementation(({ url }: { url: string }) => {
      if (url.endsWith('/samples') && url.startsWith('/datasets/')) return Promise.resolve([])
      if (url.endsWith('/samples')) return Promise.resolve(page)
      return Promise.resolve(result)
    })
    await expect(listValueSamples(result.id, query)).rejects.toThrow('数据资源版本不一致')
  })
})
