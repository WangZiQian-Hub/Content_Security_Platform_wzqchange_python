<script setup lang="ts">
import { computed, onMounted, onUnmounted, reactive, ref, watch } from 'vue'
import { ElMessage, ElMessageBox } from 'element-plus'
import PanelCard from '../../components/PanelCard.vue'
import AppIcon from '../../components/AppIcon.vue'
import ProcessTaskPanel from './components/ProcessTaskPanel.vue'
import ProcessTaskHistory from './components/ProcessTaskHistory.vue'
import ProcessComparisonTable from './components/ProcessComparisonTable.vue'
import { useDataGovernanceStore } from '../../stores/data-governance'
import { isMock } from '../../api/request'
import type { ProcessCreateInput, ProcessInput, ProcessPreview } from '../../types/data-governance'
const store = useDataGovernanceStore()
const form = reactive<ProcessInput>({
  datasetId: 0,
  datasetVersionId: '',
  scope: 'all',
  rules: [],
  templateId: '',
  batchId: '',
  filter: { keyword: '' },
})
const versions = computed(
  () => store.options?.datasets.find((item) => item.id === form.datasetId)?.versions ?? [],
)
const busy = ref(false)
const actionError = ref('')
const previewResult = ref<ProcessPreview>()
const previewOpen = ref(false)
const updatedAt = ref('')
let disposed = false
let pollTimer: ReturnType<typeof setTimeout> | undefined
watch(
  () => JSON.stringify(form),
  () => {
    previewResult.value = undefined
    previewOpen.value = false
  },
  { flush: 'sync' },
)
watch(
  () => form.datasetId,
  () => {
    form.datasetVersionId = String(versions.value[0]?.versionId ?? '')
  },
)
watch(
  () => form.templateId,
  (id) => {
    form.rules = [...(store.options?.templates.find((item) => item.id === id)?.rules ?? [])]
  },
)
async function initialize() {
  await store.initialize()
  if (disposed) return
  form.datasetId =
    store.options?.datasets.find((item) => item.id === 3)?.id ?? store.options?.datasets[0]?.id ?? 0
  form.datasetVersionId = String(versions.value[0]?.versionId ?? '')
  form.templateId = store.options?.templates[0]?.id ?? ''
  form.rules = [...(store.options?.templates[0]?.rules ?? [])]
  updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
}
function validatedInput(): ProcessInput | undefined {
  if (
    !form.datasetId ||
    !versions.value.some((item) => String(item.versionId) === String(form.datasetVersionId)) ||
    !form.rules.length ||
    !form.templateId
  ) {
    ElMessage.warning('请选择数据集、有效版本、处理模板和至少一项处理规则。')
    return
  }
  if (form.scope === 'batch' && !form.batchId?.trim()) {
    ElMessage.warning('请输入接入批次 ID。')
    return
  }
  if (form.scope === 'filtered' && !form.filter?.keyword.trim()) {
    ElMessage.warning('请输入样本筛选关键词。')
    return
  }
  const order = store.options!.templates.find((item) => item.id === form.templateId)!.rules
  const rules = [...new Set([...order, ...store.options!.rules.map((item) => item.code)])].filter(
    (code) => form.rules.includes(code),
  )
  return {
    datasetId: form.datasetId,
    datasetVersionId: form.datasetVersionId,
    templateId: form.templateId,
    scope: form.scope,
    rules,
    ...(form.scope === 'batch' ? { batchId: form.batchId!.trim() } : {}),
    ...(form.scope === 'filtered' ? { filter: { keyword: form.filter!.keyword.trim() } } : {}),
  }
}
async function runAction(action: 'preview' | 'create') {
  const input = validatedInput()
  if (!input || busy.value) return
  let createInput: ProcessCreateInput | undefined
  if (action === 'create') {
    createInput = input
  }
  busy.value = true
  actionError.value = ''
  const inputKey = JSON.stringify(form)
  try {
    if (action === 'preview') {
      const preview = await store.preview(input)
      if (disposed || inputKey !== JSON.stringify(form)) return
      previewResult.value = preview
      previewOpen.value = true
    } else {
      try {
        await ElMessageBox.confirm(
          `输入版本：${input.datasetVersionId}；规则顺序：${input.rules.map((code) => store.options?.rules.find((rule) => rule.code === code)?.label ?? code).join(' → ')}。处理完成后自动生成新版本，保留原始数据。`,
          '确认创建处理任务',
          {
            confirmButtonText: '创建任务',
            cancelButtonText: '返回修改',
            type: 'info',
            customClass: 'process-confirm-dialog',
          },
        )
      } catch {
        return
      }
      await store.createTask(createInput!)
      ElMessage.success('处理任务已创建')
      try {
        if (!isMock) await store.loadTasks()
      } catch {
        actionError.value = '任务已创建，但列表刷新失败，请稍后刷新。'
      }
    }
  } catch {
    actionError.value =
      action === 'preview'
        ? '预览失败，请检查处理服务后重试。'
        : '创建任务失败，请检查处理服务后重试。'
  } finally {
    busy.value = false
  }
}
function schedulePoll() {
  pollTimer = setTimeout(async () => {
    if (disposed) return
    const task = store.currentTask
    if (task && !task.taskId.startsWith('demo_') && ['pending', 'running'].includes(task.status)) {
      try {
        await store.refreshCurrentTask()
        // A transient polling error must not outlive a successful refresh;
        // otherwise a completed task is incorrectly presented as failed.
        actionError.value = ''
        updatedAt.value = new Date().toLocaleTimeString('zh-CN', { hour12: false })
      } catch {
        actionError.value = '任务状态刷新失败，将自动重试。'
      }
    }
    if (!disposed) schedulePoll()
  }, 5000)
}
onMounted(() => {
  void initialize()
  schedulePoll()
})
onUnmounted(() => {
  disposed = true
  clearTimeout(pollTimer)
})
</script>
<template>
  <div v-loading="store.loading" class="process-page">
    <el-alert v-if="store.error" :title="store.error" type="error" :closable="false"
      ><el-button link @click="initialize">重新加载</el-button></el-alert
    >
    <el-alert
      v-if="actionError"
      :title="actionError"
      type="error"
      show-icon
      closable
      @close="actionError = ''"
    />
    <div class="process-main-grid">
      <PanelCard title="数据处理控制台" icon="Tools" class="process-console">
        <div class="process-info"><AppIcon name="InfoFilled" />数据已由数据资源模块接入。</div>
        <el-form label-position="top" :disabled="busy || !store.options" @submit.prevent>
          <div class="process-input-pair">
            <el-form-item label="数据集"
              ><el-select v-model="form.datasetId" aria-label="数据集" placeholder="选择数据集"
                ><el-option
                  v-for="item in store.options?.datasets"
                  :key="item.id"
                  :label="item.name"
                  :value="item.id" /></el-select
            ></el-form-item>
            <el-form-item label="数据版本"
              ><el-select
                v-model="form.datasetVersionId"
                aria-label="数据版本"
                placeholder="选择版本"
                ><el-option
                  v-for="item in versions"
                  :key="item.versionId"
                  :label="item.label"
                  :value="item.versionId" /></el-select
            ></el-form-item>
          </div>
          <div class="process-input-pair process-scope">
            <el-form-item label="处理范围"
              ><el-select v-model="form.scope" aria-label="处理范围"
                ><el-option label="全量数据" value="all" /><el-option
                  label="指定批次"
                  value="batch" /><el-option label="筛选后的样本" value="filtered" /></el-select
            ></el-form-item>
          </div>
          <el-form-item v-if="form.scope === 'batch'" label="接入批次 ID"
            ><el-input v-model="form.batchId" placeholder="输入数据资源模块的批次 ID"
          /></el-form-item>
          <el-form-item v-if="form.scope === 'filtered' && form.filter" label="样本筛选关键词"
            ><el-input v-model="form.filter.keyword" placeholder="由后端在所选版本内匹配"
          /></el-form-item>
          <el-form-item label="处理规则（可多选）"
            ><el-checkbox-group v-model="form.rules"
              ><el-checkbox
                v-for="rule in store.options?.rules"
                :key="rule.code"
                :value="rule.code"
                :title="rule.description"
                >{{ rule.label }}</el-checkbox
              ></el-checkbox-group
            ></el-form-item
          >
          <el-form-item label="处理模板"
            ><el-select v-model="form.templateId" aria-label="处理模板"
              ><el-option
                v-for="item in store.options?.templates"
                :key="item.id"
                :label="item.name"
                :value="item.id" /></el-select
          ></el-form-item>
          <div class="process-actions">
            <el-button type="primary" plain :loading="busy" @click="runAction('preview')"
              ><AppIcon name="View" />预览处理</el-button
            ><el-button type="primary" :loading="busy" @click="runAction('create')"
              ><AppIcon name="VideoPlay" />创建任务</el-button
            >
          </div>
        </el-form>
      </PanelCard>
      <ProcessTaskPanel :task="store.currentTask" />
    </div>
    <ProcessTaskHistory />
    <el-dialog
      v-model="previewOpen"
      title="处理预览 · 不生成数据版本"
      width="1000px"
      class="governance-dialog"
      ><p>预览样本 {{ previewResult?.sampleCount ?? 0 }} 条</p>
      <ProcessComparisonTable :items="previewResult?.items ?? []"
    /></el-dialog>
  </div>
</template>

<style scoped>
.process-scope {
  grid-template-columns: 1fr;
}
</style>
