import { resourceDatasets } from './resource-catalog'
import type { IngestTask } from '../types/data-resource'
/** 保存的演示任务记录，目标ID/版本/名称均绑定资源目录；不作为增长或使用日志。 */
export const ingestTasks: IngestTask[] = [2, 5, 4, 1, 6].map((id, index) => {
  const dataset = resourceDatasets.find((d) => d.id === id)!
  const status = (['succeeded', 'running', 'running', 'succeeded', 'failed'] as const)[index]!
  const progress = [100, 72, 45, 100, 18][index]!
  const totalRows = [120, 90, 75, 120, 60][index]!
  const duplicateCount = [4, 3, 2, 5, 1][index]!
  const anomalyCount = [2, 1, 3, 0, 2][index]!
  const failed = status === 'failed'
  const insertedCount = failed ? 0 : totalRows - duplicateCount - anomalyCount
  return {
    taskId: `demo_ingest_${index + 1}`,
    name: `${dataset.name}接入`,
    datasetId: dataset.id,
    datasetVersionId: dataset.versionId,
    datasetName: dataset.name,
    sourceName: dataset.sourceName,
    storageGb: dataset.storageGb,
    progress,
    status,
    createdAt: `2026-09-${[24, 25, 25, 25, 26][index]}T10:00:00+08:00`,
    successCount: insertedCount,
    duplicateCount: failed ? 0 : duplicateCount,
    anomalyCount: failed ? 0 : anomalyCount,
    traceId: `demo_trace_${index + 1}`,
    result: {
      statistics: {
        basis: '样本条数=本次解析出的全部样本；重复=同批或库内 content 重复；异常=content 缺失；入库条数=样本条数-重复-异常-标题缺失',
        total_rows: failed ? 0 : totalRows,
        success_count: insertedCount,
        duplicate_count: failed ? 0 : duplicateCount,
        anomaly_count: failed ? 0 : anomalyCount,
        inserted_count: insertedCount,
        title_missing_count: 0,
        content_column_found: true,
        cross_batch_dedup_skipped: false,
      },
    },
  }
})
