<script setup lang="ts">
import { ref } from 'vue'
import {
  clearLlmToken,
  getLlmToken,
  isGovernanceLlm,
  saveLlmToken,
} from '../../../api/governance-llm'
// 令牌只保存在本会话：刷新页面仍在，关闭标签页即失效，不写入本地持久存储。
const input = ref('')
const saved = ref(getLlmToken())
const notice = ref('')
const error = ref('')
function save() {
  const token = input.value.trim()
  if (!token) {
    error.value = '请先填写本项目签发的访问令牌。'
    return
  }
  saveLlmToken(token)
  saved.value = getLlmToken()
  input.value = ''
  error.value = ''
  notice.value = '访问令牌已保存，三类模型请求将使用该令牌。'
}
function clear() {
  clearLlmToken()
  saved.value = ''
  input.value = ''
  error.value = ''
  notice.value = '访问令牌已清除，模型请求会提示需要重新填写。'
}
</script>
<template>
  <section v-if="isGovernanceLlm" class="governance-token" aria-label="模型服务访问令牌">
    <div class="token-head">
      <b>模型服务访问令牌</b>
      <el-tag :type="saved ? 'success' : 'warning'" effect="plain" size="small">
        {{ saved ? '已配置' : '未配置' }}
      </el-tag>
      <span class="token-hint">
        数据价值分析、异常数据、风险识别已改走本项目模型服务。令牌由本项目签发，与业务登录令牌分开保存；缺失或失效时如实提示，不会回退到模拟结果。
      </span>
    </div>
    <form class="token-form" @submit.prevent="save">
      <el-input
        v-model="input"
        type="password"
        show-password
        autocomplete="off"
        placeholder="粘贴本项目签发的访问令牌"
        aria-label="模型服务访问令牌"
      />
      <el-button native-type="submit" type="primary" :disabled="!input.trim()">保存</el-button>
      <el-button :disabled="!saved" @click="clear">清除</el-button>
    </form>
    <p v-if="error" class="token-error" role="alert">{{ error }}</p>
    <p v-else-if="notice" class="token-notice" role="status">{{ notice }}</p>
  </section>
</template>
<style scoped>
.governance-token {
  border: 1px solid #d8e2f0;
  border-radius: 8px;
  background: #f7fafd;
  padding: 10px 14px;
  margin-bottom: 12px;
}
.token-head {
  display: flex;
  align-items: center;
  flex-wrap: wrap;
  gap: 8px;
}
.token-hint {
  color: #5b6b80;
  font-size: 12px;
  line-height: 1.6;
}
.token-form {
  display: flex;
  gap: 8px;
  margin-top: 8px;
}
.token-form :deep(.el-input) {
  max-width: 420px;
}
.token-error {
  color: #c45656;
  font-size: 12px;
  margin: 6px 0 0;
}
.token-notice {
  color: #3a7d44;
  font-size: 12px;
  margin: 6px 0 0;
}
</style>
