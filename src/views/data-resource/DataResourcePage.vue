// “数据资源”
<script setup lang="ts">
import { computed, watch, onMounted } from 'vue'
import { useRoute } from 'vue-router'
import KpiStrip from '../../components/KpiStrip.vue'
import AppIcon from '../../components/AppIcon.vue'
import { useDataResourceStore } from '../../stores/data-resource'
import type { ResourceView } from '../../types/data-resource'
import { formatResourceComparison, resourceComparisonTitle, resourceComparisonTone } from '../../utils/resource-comparison'
import { formatStorage } from '../../utils/file-size'
const route = useRoute()
const store = useDataResourceStore()
function formatValue(value: number) {
  return new Intl.NumberFormat('zh-CN', { maximumFractionDigits: 10 }).format(value)
}
onMounted(() => store.loadOptions())
const view = computed(() => String(route.name).replace('resource-', '') as ResourceView)
// 资源卡片直接使用当前 summary 快照，与图表和导出保持同一口径。
const kpiKind = computed(() => `resource-${view.value}`)
const hideMiniBarsWithoutComparison = computed(() =>
  ['overview', 'statistics'].includes(view.value),
)
const links = [
  { path: '/data-resource', title: '资源总览', icon: 'House' },
  { path: '/data-resource/ingest', title: '数据接入', icon: 'UploadFilled' },
  { path: '/data-resource/datasets', title: '数据集管理', icon: 'FolderOpened' },
  { path: '/data-resource/statistics', title: '数据资源统计', icon: 'Histogram' },
]
watch(
  view,
  (value) => {
    void store.loadSummary(value)
  },
  { immediate: true },
)
</script>
<template>
  <div class="resource-workspace">
    <KpiStrip
      :kind="kpiKind"
      :snapshot-items="store.summary?.kpis ?? []"
      comparison-label="较前日"
      :hide-mini-bars-without-comparison="hideMiniBarsWithoutComparison"
    >
      <template #value="{ item }">
        <template v-if="item.id === 'storage'">{{ formatStorage(item.value) }}</template>
        <template v-else>{{ item.displayValue ?? formatValue(item.value) }} <small>{{ item.unit }}</small></template>
      </template>
      <template #comparison="{ item }">
        <p
          :class="resourceComparisonTone(item.comparison)"
          :style="!resourceComparisonTone(item.comparison) ? { color: '#909399' } : undefined"
          :title="resourceComparisonTitle(item)"
        >{{ formatResourceComparison(item.comparison) }}</p>
      </template>
    </KpiStrip>
    <nav class="resource-tabs" aria-label="数据资源页面导航">
      <router-link
        v-for="link in links"
        :key="link.path"
        :to="link.path"
        :class="{ selected: route.path === link.path }"
        :aria-current="route.path === link.path ? 'page' : undefined"
      >
        <AppIcon :name="link.icon" />{{ link.title }}
      </router-link>
    </nav>
    <el-alert v-if="store.error" :title="store.error" type="error" :closable="false" show-icon>
      <el-button link type="primary" @click="store.loadSummary(view)">重新加载</el-button>
    </el-alert>
    <el-alert v-if="store.optionsError" :title="store.optionsError" type="error" :closable="false"><el-button link @click="store.loadOptions">重试</el-button></el-alert>
    <div v-loading="store.loading" class="resource-page-body">
      <router-view v-slot="{ Component }">
        <Transition name="page-fade">
          <component :is="Component" />
        </Transition>
      </router-view>
    </div>
  </div>
</template>
