import axios, { type AxiosRequestConfig } from 'axios'
import { mapKeys } from '../utils/case'
import type { ApiResponse } from '../types'
/**
 * 本项目（模型服务）访问令牌的会话存储键。
 * 与业务登录令牌 accessToken 分开维护：模型令牌只由本项目签发，
 * 不能复用业务登录令牌、管理员初始化密钥或上游模型密钥。
 */
export const LLM_TOKEN_KEY = 'llmAccessToken'
/**
 * 三类分析（数据价值、异常数据、风险识别）的数据来源开关。
 *
 * 默认关闭，即继续沿用旧模式：由 VITE_USE_MOCK 决定走模拟数据还是业务后端。
 * 置为 llm 后仅这三类分析改走本项目模型服务（/llm-api/v1），
 * 数据接入、数据处理、业务任务中心等其他模块仍遵循原来的 VITE_USE_MOCK 配置。
 */
export const isGovernanceLlm = import.meta.env.VITE_GOVERNANCE_BACKEND === 'llm'
export function getLlmToken(): string {
  if (typeof sessionStorage === 'undefined') return ''
  return sessionStorage.getItem(LLM_TOKEN_KEY)?.trim() || ''
}
export function saveLlmToken(token: string): void {
  sessionStorage.setItem(LLM_TOKEN_KEY, token.trim())
}
export function clearLlmToken(): void {
  sessionStorage.removeItem(LLM_TOKEN_KEY)
}
const MISSING_TOKEN = '尚未填写模型服务访问令牌，请在数据治理页面填写后重试。'
const INVALID_TOKEN = '模型服务访问令牌无效或已失效，请在数据治理页面重新填写。'
/**
 * 弹出错误提示。
 *
 * element-plus 在 node 测试环境没有 document，因此延迟到真正需要提示时再加载；
 * 非浏览器环境直接跳过，只保留抛出的错误本身。
 */
async function notifyError(message: string) {
  if (typeof document === 'undefined') return
  const { ElMessage } = await import('element-plus')
  ElMessage.error(message)
}
let lastTraceId: string | undefined
// 模型服务独立于业务后端：独立的根地址、独立的令牌、独立的链路追踪编号。
const client = axios.create({
  baseURL: import.meta.env.VITE_LLM_API_BASE_URL || '/llm-api/v1',
  timeout: 30000,
})
client.interceptors.request.use((config) => {
  const token = getLlmToken()
  if (token) config.headers.set('Authorization', `Bearer ${token}`)
  if (lastTraceId) config.headers.set('X-Trace-Id', lastTraceId)
  if (!config.headers.has('X-Request-Id')) config.headers.set('X-Request-Id', crypto.randomUUID())
  config.data = mapKeys(config.data, 'snake')
  config.params = mapKeys(config.params, 'snake')
  return config
})
/**
 * 发往本项目模型服务的请求。
 *
 * 缺少令牌时直接提示并拒绝，不发送请求；请求失败时如实抛出，绝不回退到模拟结果，
 * 以便页面区分“没有真实数据”和“真实请求失败”。
 */
export async function llmRequest<T>(config: AxiosRequestConfig): Promise<T> {
  if (!getLlmToken()) {
    void notifyError(MISSING_TOKEN)
    throw new Error(MISSING_TOKEN)
  }
  try {
    const response = await client.request(config)
    const envelope = mapKeys(response.data, 'camel') as ApiResponse<T>
    lastTraceId = envelope.traceId
    if (envelope.code !== 0) throw new Error(envelope.message || '请求失败')
    return envelope.data
  } catch (error) {
    // 页面切换导致的中断属于正常生命周期，不提示为请求失败。
    if (axios.isCancel(error)) throw error
    const status = axios.isAxiosError(error) ? error.response?.status : undefined
    const message =
      status === 401 || status === 403
        ? INVALID_TOKEN
        : axios.isAxiosError(error)
          ? error.response?.data?.message || error.message
          : error instanceof Error
            ? error.message
            : '网络异常'
    void notifyError(String(message))
    throw error
  }
}
