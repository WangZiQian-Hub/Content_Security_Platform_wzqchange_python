import { beforeEach, describe, expect, it, vi } from 'vitest'
const backend = vi.hoisted(() => ({ isMock: true, request: vi.fn() }))
vi.mock('./request', () => backend)
vi.mock('./governance-llm', () => ({ isGovernanceLlm: false, llmRequest: vi.fn() }))
import * as api from './data-anomaly'
import { anomalyMock, publishedSnapshots } from '../mock/data-anomaly'
import { resourceSamples } from '../mock/resource-samples'
import { latestDemoResult } from '../mock/data-value'
const scope = {
  datasetId: 3,
  versionId: 'dsv_000003',
  language: 'zh',
  schemeId: 'anomaly-basic-v1',
}
const q = { page: 1, pageSize: 5, keyword: '', type: '', status: '' }
describe('异常治理完整数据与事务工作流', () => {
  beforeEach(() => {
    backend.isMock = true
    backend.request.mockReset()
  })
  it('资源ID、正文、语种一致；分布及状态守恒，导出覆盖所有分页', async () => {
    const r = (await api.getLatestAnomaly(scope))!
    const all = await api.exportAnomalySamples(r.id, q)
    expect(all.length).toBeGreaterThan(q.pageSize)
    expect(all).toHaveLength(r.anomalyCount)
    expect(r.primaryTypeCounts.reduce((sum, t) => sum + t.count, 0)).toBe(r.anomalyCount)
    expect(r.pendingCount + r.reviewCount + r.processedCount).toBe(r.anomalyCount)
    const value = latestDemoResult({ ...scope, schemeId: 'general-v1' })!
    expect(value.scope.versionId).toBe(r.scope.versionId)
    for (const s of all) {
      const resource = resourceSamples.find(
        (row) => row.id === s.id && row.versionId === s.versionId,
      )!
      expect(s.text).toBe(resource.text)
      expect(s.language).toBe('zh')
      expect(s.findings.every((f) => s.text.includes(f.quote))).toBe(true)
    }
    const type = r.primaryTypeCounts[0]!
    expect((await api.listAnomalySamples(r.id, { ...q, type: type.type })).total).toBe(type.count)
    const single = await api.exportAnomalySamples(r.id, { ...q, keyword: all[0]!.id })
    expect(single).toHaveLength(1)
    expect((await api.getAnomalySample(r.id, single[0]!.id)).findings).toEqual(single[0]!.findings)
  })
  it('条件必须完全匹配，规则目录包含20项；创建任务与结果分离', async () => {
    expect(await api.getLatestAnomaly({ ...scope, language: 'en' })).toBeNull()
    expect((await api.getAnomalyOptions()).rules).toHaveLength(20)
    vi.useFakeTimers()
    try {
      const t = await api.startAnomaly({ ...scope, language: 'en' })
      expect(t.status).toBe('running')
      expect(t.resultId).toBeUndefined()
      vi.advanceTimersByTime(1500)
      const completed = await api.getAnomalyTask(t.taskId)
      const result = await api.getAnomalyResult(completed.resultId!)
      expect(result.anomalyCount).toBe(0)
      expect(result.validCount).toBeGreaterThan(0)
    } finally {
      vi.useRealTimers()
    }
  })
  it('12条审核项一次生成一个新版本，旧版本和原文不变，令牌不可重用', async () => {
    const old = structuredClone(resourceSamples)
    const set = await api.getAnomalyChangeSet(scope)
    expect(set.entries).toHaveLength(12)
    const check = await api.checkAnomalyVersion(scope)
    const count = publishedSnapshots.size
    const output = await api.publishAnomalyVersion(scope, check.token)
    expect(publishedSnapshots.size).toBe(count + 1)
    expect(
      publishedSnapshots
        .get(output.newDatasetVersionId)
        ?.filter((r) => r.metadata.topic_label === '文化'),
    ).toHaveLength(12)
    expect(resourceSamples).toEqual(old)
    expect((await api.getAnomalyChangeSet(scope)).entries).toHaveLength(0)
    await expect(api.publishAnomalyVersion(scope, check.token)).rejects.toThrow()
  })
  it('重生成取代草稿、提交对象不可覆盖；审核只入集合，移除导致旧校验失效', async () => {
    const r = (await api.getLatestAnomaly(scope))!
    const row = (await api.listAnomalySamples(r.id, { ...q, status: '待处理' })).items[0]!
    const draft = row.candidates.at(-1)!
    const next = await api.updateCandidate(
      r.id,
      row.id,
      'generate',
      draft.candidateId,
      row.revisionId,
    )
    expect(next.candidates.at(-1)!.replacesCandidateId).toBe(draft.candidateId)
    await api.updateCandidate(r.id, row.id, 'submit')
    await expect(api.updateCandidate(r.id, row.id, 'generate')).rejects.toThrow()
    await expect(api.updateCandidate(r.id, row.id, 'approve', 'stale')).rejects.toThrow()
    const before = publishedSnapshots.size
    await api.updateCandidate(r.id, row.id, 'approve')
    expect(publishedSnapshots.size).toBe(before)
    const check = await api.checkAnomalyVersion(scope)
    await api.removeAnomalyEntry(scope, next.candidates.at(-1)!.candidateId)
    await expect(api.publishAnomalyVersion(scope, check.token)).rejects.toThrow()
    expect(publishedSnapshots.size).toBe(before)
    expect(anomalyMock.detail(r.id, row.id).metadata.topic_label).toBe('体育')
  })
  it('真实接口沿用kind与统一请求封装，写入携带候选与修订标识', async () => {
    backend.isMock = false
    await api.getLatestAnomaly(scope)
    expect(backend.request).toHaveBeenLastCalledWith({
      url: '/data-governance/anomaly-results/latest',
      params: { kind: 'governance-anomaly', ...scope },
    })
    await api.startAnomaly(scope)
    expect(backend.request).toHaveBeenLastCalledWith({
      url: '/data-governance/anomaly-tasks',
      method: 'POST',
      data: { kind: 'governance-anomaly', name: '异常数据检测', input: scope },
    })
    await api.updateCandidate('r', 'sample', 'submit', 'candidate', 'revision')
    expect(backend.request).toHaveBeenLastCalledWith({
      url: '/data-governance/anomaly-results/r/samples/sample/candidates/submit',
      method: 'POST',
      data: {
        kind: 'governance-anomaly',
        candidateId: 'candidate',
        inputSampleRevisionId: 'revision',
      },
    })
  })
})
