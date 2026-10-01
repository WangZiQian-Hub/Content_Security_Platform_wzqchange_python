// “数据资源” 总览主页面
<script setup lang="ts">
import { computed, ref } from 'vue'
import PanelCard from '../../components/PanelCard.vue'
import ResourceChart from './components/ResourceChart.vue'
import DistributionBars from './components/DistributionBars.vue'
import IngestTaskTable from './components/IngestTaskTable.vue'
import { useDataResourceStore } from '../../stores/data-resource'
import { displayLanguageDistribution } from '../../utils/resource-language'
const store = useDataResourceStore()
const days = ref(7)
const displayedLanguages = computed(() => displayLanguageDistribution(store.summary?.languages ?? []))
const trend = computed(() => {
  const data = store.summary?.trend
  return data
    ? {
        dates: data.dates.slice(-days.value),
        added: data.added.slice(-days.value),
        total: data.total.slice(-days.value),
      }
    : undefined
})
</script>
<template>
  <div class="resource-overview-top">
    <PanelCard title="接入任务数据量" icon="TrendCharts"
      ><template #extra
        ><el-select
          v-model="days"
          class="trend-days-select"
          popper-class="trend-days-popper"
          style="width: 120px"
          aria-label="接入任务数据量时间范围"
          ><el-option label="最近7天" :value="7" /><el-option
            label="最近3天"
            :value="3" /></el-select></template
      ><ResourceChart v-if="trend?.dates.length" kind="line" :trend="trend"
    /><p v-else>{{ store.summary?.basis?.trend || '暂无接入任务数据' }}</p><p class="resource-trend-note">按接入任务统计的数据量，与上方数据总量口径不同</p></PanelCard>
    <PanelCard title="数据类型分布" icon="PieChart"
      ><ResourceChart
        v-if="store.summary?.modalities.length"
        kind="donut"
        :data="store.summary?.modalities"
        :center-text="`${store.summary?.modalityCount ?? '—'} 次`"
        center-label="模态标签累计数"
    /><p>{{ store.summary?.basis?.modalities }}</p></PanelCard>
  </div>
  <div class="resource-overview-bottom">
    <PanelCard title="最近接入任务" icon="List" link="/data-resource/ingest"
      ><IngestTaskTable compact
    /></PanelCard>
    <PanelCard title="语言分布" icon="Location"
      ><DistributionBars :data="displayedLanguages"
    /><p>{{ store.summary?.basis?.languages }}</p></PanelCard>
  </div>
</template>
