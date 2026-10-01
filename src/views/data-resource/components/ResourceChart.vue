<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue'
import type { ECharts, EChartsOption } from 'echarts'
import type { Distribution, ResourceSummary } from '../../../types/data-resource'
const props = withDefaults(
  defineProps<{
    kind: 'line' | 'donut' | 'radar'
    data?: Distribution[]
    trend?: ResourceSummary['trend']
    cumulative?: boolean
    centerText?: string
    centerLabel?: string
    height?: number
    donutLayout?: 'default' | 'spacious'
  }>(),
  { height: 245, centerText: '', centerLabel: '', data: () => [], trend: undefined, donutLayout: 'default' },
)
const element = ref<HTMLDivElement>()
let chart: ECharts | undefined
let observer: ResizeObserver | undefined
let disposed = false
type TrendUnit = 'GB' | 'MB' | 'KB'

function trendDisplay(values: number[]): { unit: TrendUnit; factor: number } {
  const maximum = Math.max(0, ...values.filter((value) => Number.isFinite(value) && value >= 0))
  if (maximum <= 0) return { unit: 'KB', factor: 1024 * 1024 }
  const exponent = Math.floor(Math.log10(maximum))
  if (exponent >= 0) return { unit: 'GB', factor: 1 }
  if (exponent >= -4) return { unit: 'MB', factor: 1024 }
  return { unit: 'KB', factor: 1024 * 1024 }
}

function formatTrendValue(value: unknown, unit: TrendUnit, factor: number): string {
  const numericValue = Number(value)
  if (!Number.isFinite(numericValue)) return '0.00'
  return (Math.max(0, numericValue) * factor).toFixed(2)
}

function option(): EChartsOption {
  const common = { color: ['#087bff', '#08c592', '#ffab40', '#9861ff', '#63a8ff'], tooltip: {textStyle: {fontSize: 18, },} }
  if (props.kind === 'donut')
    return {
      ...common,
      title: {
        text: props.centerText,
        subtext: props.centerLabel || '总数据量',
        left: props.donutLayout === 'spacious' ? '25%' : '29%',  // 越大越向右
        top: props.donutLayout === 'spacious' ? '40%' : '40%',  // 越大越向下
        padding: props.donutLayout === 'spacious' ? 0 : 5,
        textAlign: 'center',
        textStyle: { color: '#0a2c6b', fontSize: 22 },  // “12.56 TB”大小
        subtextStyle: { color: '#7c8799',
                        fontSize: 16,     // “总数据量”大小
                        lineHeight: 20,   // 与上方数值的距离
                      },
      },
      legend: {
        orient: 'vertical',
        right: props.donutLayout === 'spacious' ? '5%' : '12%',  // 越大越向左
        top: 'center',
        itemGap: 20,  // 每一行之间的距离
        itemWidth: 35,      // 彩色色块宽度
        itemHeight: 22,     // 彩色色块高度
        textStyle: {color: '#333',
                    fontSize: 17,     // 图例文字大小
                    lineHeight: 25,
                  },
        formatter: (name: string) =>
          `${name}  ${props.data?.find((item) => item.name === name)?.value ?? 0}%`,
      },
      // Override the spacious statistics layout with a fixed right-hand
      // legend column. This keeps long labels inside the card.
      ...(props.donutLayout === 'spacious'
        ? { legend: {
            orient: 'vertical' as const,
            left: '53%',
            right: '2%',
            top: 'center',
            itemGap: 14,
            itemWidth: 30,
            itemHeight: 20,
            textStyle: { color: '#333', fontSize: 16, lineHeight: 22 },
            formatter: (name: string) =>
              `${name}  ${props.data?.find((item) => item.name === name)?.value ?? 0}%`,
          } }
        : {}),
      series: [
        {
          type: 'pie',
          center: [props.donutLayout === 'spacious' ? '25%' : '30%', '50%'],  // 圆环位置：水平、垂直
          radius: props.donutLayout === 'spacious' ? ['55%', '82%'] : ['60%', '90%'],  // 内半径、外半径
          ...(props.donutLayout === 'spacious' ? { radius: ['52%', '76%'] } : {}),
          label: { show: false },
          data: props.data,
        },
      ],
    }
  if (props.kind === 'radar')
    return {
      ...common,
      radar: {
        radius: '68%',
        indicator: props.data?.map((item) => ({ name: `${item.name}\n${item.value}`, max: 100 })),
        axisName: { color: '#51709d', fontSize:16},
        splitArea: { areaStyle: { color: ['#f8fbff', '#edf5ff'] } },
        center: ['50%', '60%'],
      },
      series: [
        {
          type: 'radar',
          data: [
            { value: props.data?.map((item) => item.value) ?? [], areaStyle: { opacity: 0.25 } },
          ],
        },
      ],
    }
  const trendValues = props.trend?.added ?? []
  const trendDisplayUnit = trendDisplay(trendValues)
  const trendData = trendValues.map((value) => value * trendDisplayUnit.factor)
  const formatDisplayed = (value: unknown) => formatTrendValue(value, trendDisplayUnit.unit, 1)
  return {
    ...common,
    tooltip: {
      trigger: 'axis',
      axisPointer: { type: 'line', snap: true },
      textStyle: { fontSize: 17 },
      valueFormatter: (value: unknown) => `${formatDisplayed(value)} ${trendDisplayUnit.unit}`,
    },
    legend: { top: -3, right: 8, textStyle: { color: '#334e78', fontSize: 16, },},
    grid: { left: 48, right: 24, bottom: 28, top: 42 },
    xAxis: {
      type: 'category',
      boundaryGap: false,
      data: props.trend?.dates.map((date) => date.slice(5)),
      axisLine: { lineStyle: { color: '#dce8f6' } },
      axisLabel: { color: '#647ea5', fontSize: 13.5, },
    },
    yAxis: {
      type: 'value',
      name: `接入任务数据量（${trendDisplayUnit.unit}）`,
      nameTextStyle: { color: '#647ea5', fontSize: 15, fontWeight: 400,},
      splitLine: { lineStyle: { color: '#edf3fb' } },
      axisLabel: {
        color: '#647ea5',
        fontSize: 13.5,
        formatter: (value: number) => formatDisplayed(value),
      },
    },
    series: [
      {
        name: '接入任务数据量',
        type: 'line',
        data: trendData,
        symbolSize: 7,
        areaStyle: { opacity: 0.14 },
        label: {
          show: !props.cumulative,
          position: 'top',
          color: '#183d7b',
          fontSize: 13.5,
          formatter: (params: unknown) => {
            const value = params && typeof params === 'object' && 'value' in params
              ? params.value
              : 0
            return `${formatDisplayed(value)} ${trendDisplayUnit.unit}`
          },
        },
      },
    ],
  }
}
onMounted(async () => {
  const echarts = await import('echarts')
  if (disposed || !element.value) return
  chart = echarts.init(element.value)
  chart.setOption(option())
  observer = new ResizeObserver(() => chart?.resize())
  observer.observe(element.value)
})
watch(
  () => [props.data, props.trend, props.centerText, props.centerLabel, props.cumulative],
  () => chart?.setOption(option(), true),
  { deep: true },
)
onUnmounted(() => {
  disposed = true
  observer?.disconnect()
  chart?.dispose()
})
</script>
<template>
  <div
    ref="element"
    :style="{ height: `${height}px`, width: '100%' }"
    role="img"
    :aria-label="
      kind === 'line' ? '接入任务数据量图' : kind === 'donut' ? '数据占比分布图' : '数据质量雷达图'
    "
  />
</template>
