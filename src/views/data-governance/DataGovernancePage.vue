// “数据治理” 页面
<script setup lang="ts">
import KpiStrip from '../../components/KpiStrip.vue'
import AppIcon from '../../components/AppIcon.vue'
import { navigation } from '../../router/navigation'
import { PROCESS_KIND } from '../../types/data-governance'
import { useRoute } from 'vue-router'
import { ref } from 'vue'
import AnomalyOverview from './components/AnomalyOverview.vue'
import RiskOverview from './components/RiskOverview.vue'
import ProcessOverview from './components/ProcessOverview.vue'
import ValueOverview from './components/ValueOverview.vue'
import GovernanceTokenBar from './components/GovernanceTokenBar.vue'
const riskRevision = ref(0)
const anomalyRevision = ref(0)
const route = useRoute()
const tabs = navigation.find((item) => item.path === '/data-governance')!.tabs
const icons = ['Coin', 'TrendCharts', 'Shield', 'WarningFilled', 'PieChart']
</script>
<template>
  <div class="governance-workspace">
    <GovernanceTokenBar />
    <AnomalyOverview v-if="route.name === 'governance-anomaly'" :key="anomalyRevision" />
    <RiskOverview v-else-if="route.name === 'governance-risk'" :key="riskRevision" />
    <ProcessOverview v-else-if="route.name === 'governance-process'" />
    <ValueOverview v-else-if="route.name === 'governance-value'" />
    <KpiStrip v-else :kind="PROCESS_KIND" comparison-label="暂无可比数据" />
    <nav class="governance-tabs" aria-label="数据治理子页面">
      <template v-for="(tab, index) in tabs" :key="tab.path">
        <router-link
          v-if="['process', 'value-analysis', 'anomaly', 'risk-classification'].includes(tab.path)"
          :to="tab.path === 'process' ? '/data-governance' : `/data-governance/${tab.path}`"
          :class="{
            selected:
              tab.path === 'risk-classification'
                ? route.name === 'governance-risk'
                : tab.path === 'anomaly'
                  ? route.name === 'governance-anomaly'
                  : tab.path === 'value-analysis'
                    ? route.name === 'governance-value'
                    : route.name === 'governance-process',
          }"
          :aria-current="
            (
              tab.path === 'risk-classification'
                ? route.name === 'governance-risk'
                : tab.path === 'anomaly'
                  ? route.name === 'governance-anomaly'
                  : tab.path === 'value-analysis'
                    ? route.name === 'governance-value'
                    : route.name === 'governance-process'
            )
              ? 'page'
              : undefined
          "
        >
          <AppIcon :name="icons[index]" />{{ tab.title }}
        </router-link>
        <button v-else type="button" disabled :title="`${tab.title}暂未开放`">
          <AppIcon :name="icons[index]" />{{ tab.title }}
        </button>
      </template>
    </nav>
    <router-view v-slot="{ Component }">
      <Transition name="page-fade">
        <component :is="Component" @anomaly-updated="anomalyRevision++" @risk-updated="riskRevision++" />
      </Transition>
    </router-view>
  </div>
</template>
