// “数据集管理” 子页面
<script setup lang="ts">
import { computed, onMounted, reactive, ref } from 'vue'
import { useRouter } from 'vue-router'
import { ElMessage, ElMessageBox } from 'element-plus'
import PanelCard from '../../components/PanelCard.vue'
import DatasetDetailContent from './components/DatasetDetailContent.vue'
import { useDataResourceStore } from '../../stores/data-resource'
import { isMock } from '../../api/request'
import type { DatasetQuery, ResourceDataset } from '../../types/data-resource'
import { formatStorage } from '../../utils/file-size'
import { languageName } from '../../utils/governance-language'
const store = useDataResourceStore()
const router = useRouter()
const query = reactive<DatasetQuery>({
  page: 1,
  pageSize: 10,
  keyword: '',
  modality: '',
  language: '',
  sourceType: '',
  qualityStatus: '',
})
const selected = ref<ResourceDataset>()
const loading = ref(false)
const failed = ref(false)
const editorOpen = ref(false)
const saving = ref(false)
const deletingId = ref<number>()
const editId = ref<number>()
const form = reactive({
  name: '',
  description: '',
  owner: '',
  sourceType: 'business' as ResourceDataset['sourceType'],
  languages: ['zh'],
})
const languageNames = computed<Record<string, string>>(() => Object.fromEntries(store.filterOptions.languages.map(l => [l.code, languageName(l.code)])))
async function load() {
  loading.value = true
  failed.value = false
  try {
    await store.loadDatasets(query)
  } catch {
    failed.value = true
  } finally {
    loading.value = false
  }
}
function search() {
  query.page = 1
  void load()
}
function reset() {
  Object.assign(query, {
    page: 1,
    keyword: '',
    modality: '',
    language: '',
    sourceType: '',
    qualityStatus: '',
  })
  void load()
}
function sortByUpdatedAt(a: ResourceDataset, b: ResourceDataset) {
  return Date.parse(a.updatedAt) - Date.parse(b.updatedAt)
}
function openEditor(row: ResourceDataset) {
  editId.value = row.id
  Object.assign(form, {
    name: row.name,
    description: row.description,
    owner: row.owner,
    sourceType: row.sourceType,
    languages: [...row.languages],
  })
  editorOpen.value = true
}
async function save() {
  if (!editId.value) return
  if (!form.name.trim() || !form.owner.trim() || !form.languages.length) {
    ElMessage.warning('请填写数据集名称、所有者并选择语言')
    return
  }
  if (isMock) {
    ElMessage.info('当前为示例模式，编辑需连接后端服务。')
    return
  }
  saving.value = true
  try {
    const row = await store.saveDataset({ ...form, id: editId.value })
    selected.value = row
    editorOpen.value = false
    ElMessage.success('数据集已保存')
    await load()
    await Promise.all([store.loadOptions(), store.loadSummary('datasets')])
  } catch {
    /* 统一请求层已提示错误。 */
  } finally {
    saving.value = false
  }
}
async function removeDataset(row: ResourceDataset) {
  if (isMock) {
    ElMessage.info('当前为示例模式，删除需连接后端服务。')
    return
  }
  try {
    await ElMessageBox.confirm(
      `确定删除数据集“${row.name}”吗？删除后将一并删除该数据集的样本记录和接入任务，且无法恢复。`,
      '删除数据集',
      { confirmButtonText: '删除', cancelButtonText: '取消', type: 'warning' },
    )
  } catch {
    return
  }
  deletingId.value = row.id
  try {
    await store.deleteDataset(row.id)
    if (selected.value?.id === row.id) selected.value = undefined
    if (store.datasets.length === 1 && query.page > 1) query.page--
    ElMessage.success('数据集已删除')
    await load()
    await Promise.all([store.loadOptions(), store.loadSummary('datasets')])
  } catch {
    /* 统一请求层已提示错误。 */
  } finally {
    deletingId.value = undefined
  }
}
onMounted(load)
</script>
<template>
  <PanelCard title="数据集管理" icon="FolderOpened">
    <div class="resource-toolbar resource-dataset-filters">
      <el-input
        v-model="query.keyword"
        placeholder="搜索数据集名称"
        clearable
        aria-label="数据集名称"
        @input="search"
      />
      <el-select
        v-model="query.modality"
        placeholder="全部类型"
        clearable
        aria-label="数据类型"
        @change="search"
        ><el-option
          v-for="name in store.filterOptions.modalities"
          :key="name"
          :label="name"
          :value="name"
      /></el-select>
      <el-select
        v-model="query.language"
        placeholder="全部语言"
        clearable
        aria-label="数据语言"
        @change="search"
        ><el-option v-for="(name, code) in languageNames" :key="code" :label="name" :value="code"
      /></el-select>
      <el-select
        v-model="query.sourceType"
        placeholder="全部来源"
        clearable
        aria-label="数据来源"
        @change="search"
        ><el-option v-for="s in store.filterOptions.sources" :key="s.code" :label="s.name" :value="s.code"
      /></el-select>
      <el-select
        v-model="query.qualityStatus"
        placeholder="全部质量"
        clearable
        aria-label="质量状态"
        @change="search"
        ><el-option label="优秀" value="excellent" /><el-option
          label="良好"
          value="good" /><el-option label="异常" value="poor"
      /></el-select>
      <el-button @click="reset">重置</el-button>
    </div>
    <el-alert v-if="failed" title="数据集加载失败" type="error" :closable="false"
      ><el-button link @click="load">重试</el-button></el-alert
    >
    <el-table
      v-loading="loading"
      :data="store.datasets"
      highlight-current-row
      empty-text="暂无符合条件的数据集"
      @row-click="
        (row: ResourceDataset) => {
          selected = row
        }
      "
    >
      <el-table-column prop="name" label="数据集名称" min-width="210" />
      <el-table-column label="数据类型" min-width="110"
        ><template #default="{ row }">{{ row.modalities.join(' / ') }}</template></el-table-column
      >
      <el-table-column label="语言" min-width="100"
        ><template #default="{ row }: { row: ResourceDataset }">{{
          row.languages.map(languageName).join(' / ')
        }}</template></el-table-column
      >
      <el-table-column label="数据量" min-width="115"
        ><template #default="{ row }">{{
          row.rowCount.toLocaleString()
        }}</template></el-table-column
      >
      <el-table-column label="累计存储量" min-width="100"
        ><template #default="{ row }">{{ formatStorage(row.storageGb) }}</template></el-table-column
      >
      <el-table-column prop="sourceName" label="数据来源" min-width="110" />
      <el-table-column prop="versionId" label="当前版本" min-width="120"
        ><template #default="{ row }: { row: ResourceDataset }">{{
          row.versionId || '-'
        }}</template></el-table-column
      >
      <el-table-column prop="qualityScore" label="质量评分" width="120" sortable
        ><template #default="{ row }"
          ><el-tag :type="row.qualityStatus === 'poor' ? 'warning' : 'success'" round>{{
            row.qualityScore
          }}</el-tag></template
        ></el-table-column
      >
      <el-table-column prop="updatedAt" label="更新时间" min-width="145" sortable :sort-method="sortByUpdatedAt"
        ><template #default="{ row }">{{
          new Date(row.updatedAt).toLocaleDateString('zh-CN')
        }}</template></el-table-column
      >
      <el-table-column label="操作" width="170"
        ><template #default="{ row }: { row: ResourceDataset }"
          ><el-button link type="primary" @click.stop="selected = row">查看</el-button
          ><el-button link type="primary" @click.stop="openEditor(row)">编辑</el-button
          ><el-button
            link
            type="danger"
            :loading="deletingId === row.id"
            @click.stop="removeDataset(row)"
            >删除</el-button
          ></template
        ></el-table-column
      >
    </el-table>
    <el-pagination
      v-model:current-page="query.page"
      v-model:page-size="query.pageSize"
      :page-sizes="[5, 10, 20]"
      :total="store.datasetTotal"
      layout="total, sizes, prev, pager, next, jumper"
      @current-change="load"
      @size-change="search"
    />
  </PanelCard>
  <el-drawer
    :model-value="!!selected"
    :title="selected?.name"
    size="480px"
    class="resource-detail"
    @close="selected = undefined"
  >
    <DatasetDetailContent v-if="selected" :dataset="selected" />
    <template #footer
      ><el-button v-if="selected" @click="openEditor(selected)">编辑信息</el-button
      ><el-button
        type="primary"
        @click="router.push({ path: '/data-resource/ingest', query: { dataset: selected?.id } })"
        >＋ 添加数据</el-button
      ></template
    >
  </el-drawer>
  <el-dialog v-model="editorOpen" title="编辑数据集" width="540px">
    <el-alert
      v-if="isMock"
      title="示例模式：可填写表单，保存需连接后端服务"
      type="info"
      :closable="false"
    />
    <el-form label-position="top"
      ><el-form-item label="数据集名称" required
        ><el-input v-model="form.name" maxlength="255" /></el-form-item
      ><el-form-item label="数据所有者" required><el-input v-model="form.owner" /></el-form-item
      ><el-form-item label="数据语言" required
        ><el-select v-model="form.languages" multiple
          ><el-option
            v-for="(name, code) in languageNames"
            :key="code"
            :label="name"
            :value="code" /></el-select></el-form-item
      ><el-form-item label="来源类型"
        ><el-select v-model="form.sourceType"
          ><el-option label="业务数据" value="business" /><el-option
            label="互联网"
            value="internet" /><el-option label="行业数据" value="industry" /><el-option
            label="合成数据"
            value="synthetic" /></el-select></el-form-item
      ><el-form-item label="描述"
        ><el-input v-model="form.description" type="textarea" :rows="3" /></el-form-item
    ></el-form>
    <template #footer
      ><el-button @click="editorOpen = false">取消</el-button
      ><el-button type="primary" :loading="saving" @click="save">保存</el-button></template
    >
  </el-dialog>
</template>
