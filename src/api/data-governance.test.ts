import { beforeEach, describe, expect, it, vi } from 'vitest'
const backend = vi.hoisted(() => ({ isMock: true, request: vi.fn() }))
vi.mock('./request', () => backend)
import {
  createProcessTask,
  previewProcess,
  getProcessOptions,
  listProcessTasks,
  getProcessTask,
} from './data-governance'
import { PROCESS_KIND } from '../types/data-governance'
import type { ProcessCreateInput } from '../types/data-governance'
const input: ProcessCreateInput = {
  datasetId: 3,
  datasetVersionId: 'dsv_000003',
  outputVersionName: '清洗版-v1.1.0',
  scope: 'batch',
  batchId: 'batch_1',
  templateId: 'standard',
  rules: ['normalize_text', 'deduplicate'],
}
describe('数据处理接口契约', () => {
  beforeEach(() => {
    backend.isMock = true
    backend.request.mockReset()
  })
  it('真实查询统一传递 kind 和分页，不回退示例', async () => {
    backend.isMock = false
    backend.request.mockImplementation(async ({ url }) =>
      url === '/datasets' ? { items: [], total: 0 } : { rules: [], templates: [] },
    )
    await getProcessOptions()
    expect(backend.request).toHaveBeenCalledWith({
      url: '/data-governance/options',
      params: { kind: PROCESS_KIND },
    })
    backend.request.mockReset()
    backend.request.mockResolvedValueOnce({
      items: [],
      total: 0,
      page: 2,
      pageSize: 10,
      totalPages: 0,
    })
    await listProcessTasks(2, 10)
    expect(backend.request).toHaveBeenLastCalledWith({
      url: '/tasks',
      params: { kind: PROCESS_KIND, page: 2, pageSize: 10 },
    })
    backend.request.mockRejectedValue(new Error('offline'))
    await expect(getProcessTask('tsk_1')).rejects.toThrow('offline')
  })
  it('演示模式创建与预览仍请求后端，保留版本和规则顺序', async () => {
    await previewProcess(input)
    expect(backend.request).toHaveBeenLastCalledWith({
      url: '/data-governance/preview',
      method: 'POST',
      data: { kind: PROCESS_KIND, input },
    })
    await createProcessTask(input)
    expect(backend.request).toHaveBeenLastCalledWith({
      url: '/tasks',
      method: 'POST',
      data: { kind: PROCESS_KIND, name: '数据清洗任务', input },
    })
    backend.request.mockRejectedValue(new Error('offline'))
    await expect(createProcessTask(input)).rejects.toThrow('offline')
  })
  it('只读快照分页并保持数据集与输入版本对应', async () => {
    const options = await getProcessOptions()
    const tasks = await listProcessTasks(2, 1)
    expect(tasks.items).toHaveLength(1)
    const task = tasks.items[0]!
    expect(
      options.datasets
        .find((item) => item.id === task.input.datasetId)
        ?.versions.some((item) => item.versionId === task.input.datasetVersionId),
    ).toBe(true)
    expect((await listProcessTasks(5, 10)).items).toEqual([])
    await expect(getProcessTask('demo_missing')).rejects.toThrow('任务不存在')
  })
  it('正式接口把整数主键映射为版本号字符串', async () => {
    backend.isMock = false
    backend.request.mockImplementation(async ({ url, params }) => {
      if (url === '/data-governance/options') return { rules: [], templates: [] }
      if (url === '/datasets') return { items: [{ id: 14, name: '测试数据集' }], total: 1 }
      if (url === '/datasets/14/versions') {
        return {
          items: [
            { id: 10, version_id: 'v1.0.1', version: 'v1.0.1', label: 'v1.0.1', languages: ['zh'] },
          ],
          total: 1,
        }
      }
      throw new Error(`unexpected request: ${url} ${JSON.stringify(params)}`)
    })
    const options = await getProcessOptions()
    expect(options.datasets[0]!.versions[0]!.versionId).toBe('v1.0.1')
    expect(options.datasets[0]!.versions[0]!.versionId).not.toBe('10')
  })
})
