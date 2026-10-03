import { beforeEach, describe, expect, it, vi } from 'vitest'
import { LLM_TOKEN_KEY, clearLlmToken, getLlmToken, llmRequest, saveLlmToken } from './governance-llm'
class MemoryStorage {
  private data = new Map<string, string>()
  getItem(key: string) {
    return this.data.has(key) ? this.data.get(key)! : null
  }
  setItem(key: string, value: string) {
    this.data.set(key, String(value))
  }
  removeItem(key: string) {
    this.data.delete(key)
  }
}
describe('模型服务访问令牌', () => {
  beforeEach(() => {
    vi.stubGlobal('sessionStorage', new MemoryStorage())
  })
  it('保存后按原样读取，清除后为空', () => {
    expect(getLlmToken()).toBe('')
    saveLlmToken('  issued-by-model-service  ')
    expect(getLlmToken()).toBe('issued-by-model-service')
    expect(sessionStorage.getItem(LLM_TOKEN_KEY)).toBe('issued-by-model-service')
    clearLlmToken()
    expect(getLlmToken()).toBe('')
  })
  it('缺少令牌时直接拒绝并给出明确提示，不发送请求也不回退模拟结果', async () => {
    await expect(llmRequest({ url: '/tasks' })).rejects.toThrow(
      '尚未填写模型服务访问令牌，请在数据治理页面填写后重试。',
    )
  })
})
