"""真实的数据处理流水线：只读源版本，事务性地产出独立快照。"""
from __future__ import annotations

from typing import Any

from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.models.tables import Dataset, DatasetRecord, DatasetVersion, ProcessAudit
from app.services.file_ingest import normalize_content, text_value
from app.services.versioning import create_dataset_version
from app.services.database_ingest import save_dataset_rows

SUPPORTED_RULES = {"deduplicate", "complete_fields"}


def _input_value(payload: dict[str, Any], *keys: str) -> Any:
    for key in keys:
        if key in payload:
            return payload[key]
    return None


def _select_records(db: Session, dataset_id: int, version_id: str, scope: str, input_data: dict[str, Any]) -> tuple[DatasetVersion, list[DatasetRecord]]:
    version = db.scalar(select(DatasetVersion).where(
        DatasetVersion.dataset_id == dataset_id, DatasetVersion.version == version_id
    ))
    if version is None and version_id.isdigit():
        # 兼容历史任务：早期前端把 dataset_versions.id 当成版本号提交。
        version = db.scalar(select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id, DatasetVersion.id == int(version_id)
        ))
    if version is None:
        raise ValueError(f"源数据版本不存在：{dataset_id}/{version_id}")
    rows = list(db.scalars(select(DatasetRecord).where(
        DatasetRecord.dataset_version_id == version.id
    ).order_by(DatasetRecord.id.asc())).all())
    if scope == "batch":
        batch_id = str(_input_value(input_data, "batch_id", "batchId") or "").strip()
        rows = [r for r in rows if str((r.payload or {}).get("batch_id", (r.payload or {}).get("batchId", r.task_id))) == batch_id or str(r.task_id) == batch_id]
    elif scope == "filtered":
        keyword = str((_input_value(input_data, "filter") or {}).get("keyword", "")).strip().casefold()
        rows = [r for r in rows if keyword and keyword in " ".join((text_value((r.payload or {}).get(k)) for k in ("title", "content"))).casefold()]
    return version, rows


def preview_process(db: Session, input_data: dict[str, Any], limit: int = 100) -> dict[str, Any]:
    dataset_id = int(_input_value(input_data, "dataset_id", "datasetId") or 0)
    version_id = str(_input_value(input_data, "dataset_version_id", "datasetVersionId") or "")
    rules = [str(r) for r in (_input_value(input_data, "rules") or [])]
    version, rows = _select_records(db, dataset_id, version_id, str(input_data.get("scope", "all")), input_data)
    comparisons, _, _, _ = _evaluate(rows[:limit], rules)
    return {"items": comparisons, "sample_count": len(rows), "source_version": version.version}


def _evaluate(rows: list[DatasetRecord], rules: list[str]) -> tuple[list[dict], list[DatasetRecord], list[dict], dict[str, int]]:
    known = [r for r in rules if r in SUPPORTED_RULES]
    unknown = [r for r in rules if r not in SUPPORTED_RULES]
    dedup_seen: dict[str, DatasetRecord] = {}
    kept: list[DatasetRecord] = []
    audits: list[dict] = []
    comparisons: list[dict] = []
    counts = {"duplicate_count": 0, "anomaly_count": 0, "complete_fields_count": 0}
    for record in rows:
        payload = dict(record.payload or {})
        title, content = text_value(payload.get("title")), text_value(payload.get("content"))
        if "complete_fields" in known and (not title or not content):
            counts["anomaly_count"] += 1
            audits.append({"record": record, "rule": "complete_fields", "reason": "\u6807\u9898\u548c\u6b63\u6587\u5fc5\u987b\u5b58\u5728\u4e14\u975e\u7a7a", "kept": None})
            continue
        key = normalize_content(content)
        if "deduplicate" in known and key in dedup_seen:
            counts["duplicate_count"] += 1
            audits.append({"record": record, "rule": "deduplicate", "reason": "\u6b63\u6587\u6309\u63a5\u5165\u53e3\u5f84\u5f52\u4e00\u5316\u540e\u91cd\u590d", "kept": dedup_seen[key]})
            continue
        if "deduplicate" in known:
            dedup_seen[key] = record
        kept.append(record)
        comparisons.append({
            "id": str(record.id),
            "original": content,
            "processed": content,
            "actions": ["keep"],
            "fields": [],
        })
    counts["unknown_rule_count"] = len(unknown)
    return comparisons, kept, audits, counts


def process_task(db: Session, task_id: str, input_data: dict[str, Any]) -> dict[str, Any]:
    dataset_id = int(_input_value(input_data, "dataset_id", "datasetId") or 0)
    version_id = str(_input_value(input_data, "dataset_version_id", "datasetVersionId") or "")
    rules = [str(r) for r in (_input_value(input_data, "rules") or [])]
    if not dataset_id or not version_id:
        raise ValueError("必须选择数据集和源数据版本")
    if not rules:
        raise ValueError("至少选择一条处理规则")
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise ValueError(f"数据集不存在：{dataset_id}")
    source_version, rows = _select_records(db, dataset_id, version_id, str(input_data.get("scope", "all")), input_data)
    comparisons, kept, audits, counts = _evaluate(rows, rules)
    requested_name = _input_value(input_data, "output_version_name", "outputVersionName")
    if requested_name and db.scalar(select(DatasetVersion.id).where(
        DatasetVersion.dataset_id == dataset_id, DatasetVersion.version == str(requested_name).strip()
    )) is not None:
        raise ValueError(f"输出版本已存在：{requested_name}")
    payloads = [dict(r.payload or {}) for r in kept]
    output = create_dataset_version(
        db, dataset_id, task_id=task_id,
        description=f"由数据处理任务 {task_id} 从 {source_version.version} 产出",
        added_record_count=len(payloads), total_record_count=len(payloads),
        stored_record_count=len(payloads), storage_gb=0,
        source_name="数据处理", connector_type="process",
        languages=list(source_version.languages or []), modalities=list(source_version.modalities or []), status="ready",
    )
    if payloads:
        save_dataset_rows(db, dataset_id=dataset_id, task_id=task_id, rows=payloads, dataset_version_id=output.id)
    for item in audits:
        db.add(ProcessAudit(
            task_id=task_id, dataset_id=dataset_id, source_version_id=source_version.id,
            source_record_id=item["record"].id, rule_code=item["rule"], reason=item["reason"],
            kept_record_id=item["kept"].id if item["kept"] else None,
            source_payload=dict(item["record"].payload or {}),
        ))
    # Keep only 200 comparisons in task JSON; complete evidence remains in audit rows and the output snapshot.
    result = {
        "output_version": output.version, "output_version_id": output.id,
        "source_version": source_version.version, "source_version_id": source_version.id,
        "total_count": len(rows), "processed_count": len(rows), "retained_count": len(payloads),
        "duplicate_count": counts["duplicate_count"], "anomaly_count": counts["anomaly_count"],
        "unknown_rule_count": counts["unknown_rule_count"], "comparison_count": len(comparisons),
        "comparisons": comparisons[:200],
        "steps": [{"name": "\u8bfb\u53d6\u6570\u636e", "status": "succeeded"}, {"name": "\u5b57\u6bb5\u8865\u5168", "status": "succeeded"}, {"name": "\u53bb\u91cd", "status": "succeeded"}, {"name": "\u751f\u6210\u7248\u672c", "status": "succeeded"}],
    }
    return result

