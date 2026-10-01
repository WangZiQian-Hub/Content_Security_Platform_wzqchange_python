// “数据资源统计” 子页面
<script setup lang="ts">
import { computed, reactive, ref } from 'vue'
import PanelCard from '../../components/PanelCard.vue'
import ResourceChart from './components/ResourceChart.vue'
import DistributionBars from './components/DistributionBars.vue'
import { useDataResourceStore } from '../../stores/data-resource'
import { isMock } from '../../api/request'
import type { StatisticsQuery } from '../../types/data-resource'
import { formatResourceComparison } from '../../utils/resource-comparison'
import { formatStorage, formatStorageValue } from '../../utils/file-size'
import { languageName } from '../../utils/governance-language'
import { displayLanguageDistribution } from '../../utils/resource-language'
const store = useDataResourceStore()
const dates = ref<[string, string]>()
const filters = reactive<StatisticsQuery>({ sourceType: '', language: '' })
const summary = computed(() => store.summary)
const displayedLanguages = computed(() => displayLanguageDistribution(summary.value?.languages ?? []))
async function search() {
  await store.loadSummary('statistics', {
    ...filters,
    startDate: dates.value?.[0],
    endDate: dates.value?.[1],
  })
}
function exportReport() {
  if (!summary.value) return
  const escape = (value: string | number) => `"${String(value).replace(/^[\s]*[=+@-]/, "'$&").replace(/"/g, '""')}"`
  const rows: (string | number)[][] = [
    ['数据资源统计报表', isMock ? '示例数据' : '后端数据'],
    ['统计快照时间', summary.value.generatedAt || '服务端未提供'],
    ['生效筛选', JSON.stringify(summary.value.filters || {})],
    ['数据截止时间', summary.value.asOf || '服务端未提供'],
    ['指标', '数值', '单位', '日环比', '比较时点', '前期时点', '前期值'],
    ...summary.value.kpis.map((item) => [item.label, item.displayValue ?? item.value, item.unit,
      formatResourceComparison(item.comparison), item.comparison?.currentAt || '',
      item.comparison?.previousAt || '', item.comparison?.previousValue ?? '—']),
    ...(['sources', 'languages', 'modalities', 'issues'] as const).flatMap(key => [[key, summary.value!.basis?.[key] || ''], ...summary.value![key].map(item => [item.name, item.value])]),
    ['日期', '接入任务数据量'],
    ...summary.value.trend.dates.map((date, i) => [date, summary.value!.trend.added[i]!]),
    [],
    ['数据集', '来源', '存储量', '使用次数', '使用占比(%)'],
    ...summary.value.ranking.map((item) => [
      item.name,
      item.source,
      formatStorageValue(item.storageGb),
      item.uses,
      item.share,
    ]),
  ]
  const url = URL.createObjectURL(
    new Blob(['\uFEFF' + rows.map((row) => row.map(escape).join(',')).join('\r\n')], {
      type: 'text/csv;charset=utf-8',
    }),
  )
  const link = document.createElement('a')
  link.href = url
  link.download = `数据资源统计${isMock ? '-示例' : ''}.csv`
  link.click()
  setTimeout(() => URL.revokeObjectURL(url), 1000)
}
</script>
<template>
  <div class="resource-statistics-filter">
    <el-date-picker
      v-model="dates"
      type="daterange"
      range-separator="至"
      start-placeholder="开始日期"
      end-placeholder="结束日期"
      value-format="YYYY-MM-DD"
    /><el-select
      v-model="filters.sourceType"
      clearable
      placeholder="全部来源"
      aria-label="统计数据来源"
      ><el-option v-for="s in store.filterOptions.sources" :key="s.code" :label="s.name" :value="s.code" /></el-select
    ><el-select v-model="filters.language" clearable placeholder="全部语言" aria-label="统计语言"
      ><el-option v-for="l in store.filterOptions.languages" :key="l.code" :label="languageName(l.code)" :value="l.code" /></el-select
    ><el-button type="primary" :loading="store.loading" @click="search">查询</el-button
    ><el-button :disabled="!summary || store.loading" @click="exportReport">↓ 导出报表</el-button>
  </div>
  <div class="resource-statistics-top">
    <PanelCard title="接入任务数据量" icon="TrendCharts"
      ><ResourceChart v-if="summary?.trend.dates.length" kind="line" :trend="summary?.trend" :height="235" /><p v-else>{{ summary?.basis?.trend || '暂无接入任务数据' }}</p><p class="resource-trend-note">按接入任务统计的数据量，与上方数据总量口径不同</p></PanelCard
    ><PanelCard title="数据来源分布" icon="PieChart"
      ><ResourceChart
        v-if="summary?.sources.length"
        kind="donut"
        donut-layout="spacious"
        :data="summary?.sources"
        :center-text="formatStorage(summary?.kpis.find((item) => item.id === 'storage')?.value)"
        :height="235" /><p>{{ summary?.basis?.sources }}</p></PanelCard
    >
  </div>
  <div class="resource-statistics-bottom">
    <PanelCard title="语言分布" icon="Document"
      ><DistributionBars :data="displayedLanguages" /><p>{{ summary?.basis?.languages }}</p></PanelCard
    ><PanelCard title="数据模态分布" icon="Grid"
      ><DistributionBars :data="summary?.modalities ?? []"
    /><p>{{ summary?.basis?.modalities }}</p></PanelCard
    ><PanelCard title="数据问题统计" icon="Grid"
      ><div v-for="(item, index) in summary?.issues" :key="item.name" class="resource-issue">
        <i :class="{ danger: index > 1 }">≡</i
        ><span>{{ item.name }}</span
        ><b>{{ item.value.toLocaleString() }}</b
        ><span class="resource-issue-track"
          ><i :style="{ width: `${item.value / Math.max(1, ...(summary?.issues.map(v => v.value) || [])) * 100}%` }"
        /></span></div>
      <p>{{ summary?.basis?.issues }}</p></PanelCard>
  </div>
  <PanelCard title="数据集使用排行" icon="List" link="/data-resource/datasets"
    ><el-table :data="summary?.ranking ?? []" :empty-text="summary?.basis?.ranking || '暂无统计数据'"
      ><el-table-column type="index" label="排名" width="75" /><el-table-column
        prop="name"
        label="数据集名称"
        min-width="220" /><el-table-column
        prop="source"
        label="数据来源"
        min-width="130" /><el-table-column label="数据量" min-width="120"
        ><template #default="{ row }">{{ formatStorage(row.storageGb) }}</template></el-table-column
      ><el-table-column label="使用次数" min-width="120"
        ><template #default="{ row }">{{ row.uses.toLocaleString() }}</template></el-table-column
      ><el-table-column label="使用占比" min-width="220"
        ><template #default="{ row }"
          ><el-progress
            :percentage="row.share"
            :stroke-width="8" /></template></el-table-column></el-table
  ></PanelCard>
</template>
