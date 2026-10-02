"""数据集版本维护（数据接入链路专用）。

设计约定：

1. 只增不改：每次接入成功就追一条版本记录，不覆盖、不更新旧版本。
2. 数据行带版本：接入的数据行写进 dataset_records 时必须带 dataset_version_id，
   这样每一行都能回答"我属于哪个版本"。
3. datasets.version 只是"当前版本指针"；历史版本一律从 dataset_versions 查。
4. v1.0.0 是数据集建立时的基线版本；第一次接入成功才产出 v1.0.1。

升版规则（patch 满 10 进 minor，minor 满 10 进 major）：
    v1.0.0 → v1.0.1 → … → v1.0.9 → v1.1.0 → … → v1.9.9 → v2.0.0
    major 只会由这个进位规则触发，没有"人工标记重大变更"的入口。
"""

from __future__ import annotations

import re
from typing import Any

from sqlalchemy import func, select, update as sql_update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import Session

from app.core.time import now_shanghai
from app.models.tables import Dataset, DatasetRecord, DatasetVersion

VERSION_PATTERN = re.compile(r"^v?(\d+)\.(\d+)\.(\d+)$")
MAX_VERSION_ATTEMPTS = 5
# 版本号的进位基数：patch 到 9 就进 minor，minor 到 9 就进 major。
VERSION_RADIX = 10


def build_version(major: int, minor: int, patch: int) -> str:
    """拼出版本号，统一 v主.次.修订 格式。"""
    return f"v{major}.{minor}.{patch}"


def parse_version(value: str | None) -> tuple[int, int, int] | None:
    """解析版本号；解析不了的（例如人工写的说明文字）返回 None。"""
    if not isinstance(value, str):
        return None
    matched = VERSION_PATTERN.match(value.strip())
    if matched is None:
        return None
    return (int(matched.group(1)), int(matched.group(2)), int(matched.group(3)))


def next_dataset_version(current: str | None) -> str:
    """升版函数：给定当前版本号，返回下一个版本号。

    这是唯一的升版实现；数据处理、异常治理以后要升版也复用它。
    解析不了当前版本号时，从 v1.0.0 的下一号 v1.0.1 开始。
    """
    parsed = parse_version(current)
    if parsed is None:
        return build_version(1, 0, 1)

    major, minor, patch = parsed
    patch += 1
    if patch >= VERSION_RADIX:
        patch = 0
        minor += 1
    if minor >= VERSION_RADIX:
        minor = 0
        major += 1
    return build_version(major, minor, patch)


def _next_version_number(db: Session, dataset_id: int) -> str:
    """算出该数据集应该用的下一个版本号。

    取"该数据集已用过的最大版本号"的下一个；一条版本都没有时，
    以 datasets.version（基线 v1.0.0）为起点算下一个。
    """
    existing = dataset_version_names(db, dataset_id)

    highest: tuple[int, int, int] | None = None
    highest_text: str | None = None

    for value in existing:
        parsed = parse_version(value)
        if parsed is None:
            continue
        if highest is None or parsed > highest:
            highest = parsed
            highest_text = value

    dataset = db.get(Dataset, dataset_id)

    if highest is None:
        # 还没有任何版本记录：从数据集当前版本号（基线）往上走一号。
        base = getattr(dataset, "version", None) or "v1.0.0"
        return next_dataset_version(base)

    dataset_parsed = parse_version(getattr(dataset, "version", None)) if dataset else None
    if dataset_parsed is not None and dataset_parsed > highest:
        return next_dataset_version(dataset.version)

    return next_dataset_version(highest_text)


def dataset_versions(db: Session, dataset_id: int) -> list[DatasetVersion]:
    """数据集登记过的全部版本，按 id 升序返回。

    dataset_versions 是"只增不改"的顺序表，id 就是登记先后；
    这里统一按 id 排序，调用方不必各自写 where + order_by。
    """
    return list(
        db.scalars(
            select(DatasetVersion)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.id.asc())
        ).all()
    )


def dataset_version_names(db: Session, dataset_id: int) -> list[str]:
    """只取版本号字符串，顺序与 dataset_versions() 一致。"""
    return [
        str(value)
        for value in db.scalars(
            select(DatasetVersion.version)
            .where(DatasetVersion.dataset_id == dataset_id)
            .order_by(DatasetVersion.id.asc())
        ).all()
        if value is not None and str(value).strip() != ""
    ]


def current_dataset_version_name(db: Session, dataset_id: int) -> str | None:
    """数据集当前版本号 = dataset_versions 里最后登记的那一版。

    优先认 is_current 标记；标记缺失（老库或回滚）时按 id 取最后一条，
    也就是追加顺序上的最新版本。任何一处都不再读 datasets.version。
    """
    current = db.scalar(
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset_id)
        .order_by(DatasetVersion.is_current.desc(), DatasetVersion.id.desc())
        .limit(1)
    )
    return str(current.version) if current is not None else None


def resolve_dataset_version(
    db: Session, dataset_id: int, version_ref: Any
) -> DatasetVersion | None:
    """把"版本引用"解析成版本记录。

    先按版本号精确匹配；纯数字的引用再按 dataset_versions.id 兜底，
    兼容早期前端把主键当版本号提交的历史任务。
    """
    if version_ref is None:
        return None
    text = str(version_ref).strip()
    if not text:
        return None
    version = db.scalar(
        select(DatasetVersion).where(
            DatasetVersion.dataset_id == dataset_id,
            DatasetVersion.version == text,
        )
    )
    if version is None and text.isdigit():
        version = db.scalar(
            select(DatasetVersion).where(
                DatasetVersion.dataset_id == dataset_id,
                DatasetVersion.id == int(text),
            )
        )
    return version


def create_dataset_version(
    db: Session,
    dataset_id: int,
    *,
    task_id: str | None = None,
    description: str = "",
    added_record_count: int = 0,
    total_record_count: int | None = None,
    stored_record_count: int | None = None,
    storage_gb: float = 0.0,
    source_name: str = "",
    connector_type: str = "file",
    languages: list[str] | None = None,
    modalities: list[str] | None = None,
    file_ids: list[str] | None = None,
    status: str = "ready",
) -> DatasetVersion:
    """新建一个数据集版本，并把它设为当前版本。

    调用方负责提交事务：本函数只 flush，保证版本记录和同一次接入的数据行
    落在同一个事务里，要么一起成功，要么一起回滚。

    并发取号：版本号在事务内算，配合 (dataset_id, version) 唯一约束 +
    SAVEPOINT 重试，两个任务同时完成也不会撞号。
    """
    dataset = db.get(Dataset, dataset_id)
    if dataset is None:
        raise ValueError(f"数据集不存在：{dataset_id}")

    last_error: Exception | None = None

    for _ in range(MAX_VERSION_ATTEMPTS):
        version = _next_version_number(db, dataset_id)

        try:
            # SAVEPOINT 只保护本次版本插入：万一撞号，只回滚这一条，
            # 不会把调用方（接入任务）已经改好的数据集元数据一起丢掉。
            with db.begin_nested():
                # 先把旧版本降级，保证任一时刻只有一个 is_current。
                db.execute(
                    sql_update(DatasetVersion)
                    .where(DatasetVersion.dataset_id == dataset_id)
                    .values(is_current=False)
                )

                record = DatasetVersion(
                    dataset_id=dataset_id,
                    version=version,
                    task_id=task_id,
                    description=description,
                    added_record_count=int(added_record_count or 0),
                    total_record_count=(
                        int(total_record_count)
                        if total_record_count is not None
                        else int(added_record_count or 0)
                    ),
                    stored_record_count=(
                        int(stored_record_count)
                        if stored_record_count is not None
                        else int(added_record_count or 0)
                    ),
                    storage_gb=float(storage_gb or 0),
                    source_name=source_name or "",
                    connector_type=connector_type,
                    languages=list(languages or []),
                    modalities=list(modalities or []),
                    file_ids=list(file_ids or []),
                    status=status,
                    is_current=True,
                    is_backfilled=False,
                    has_snapshot=True,
                    created_at=now_shanghai(),
                )
                db.add(record)
                db.flush()
        except IntegrityError as error:
            last_error = error
            continue

        dataset.version = version
        db.flush()
        return record

    raise RuntimeError("版本号生成失败，请重试") from last_error


def count_version_records(db: Session, dataset_version_id: int) -> int:
    """这个版本在库里真实存了多少条数据行。"""
    return int(db.scalar(
        select(func.count(DatasetRecord.id)).where(
            DatasetRecord.dataset_version_id == dataset_version_id
        )
    ) or 0)


def version_has_snapshot(db: Session, version: DatasetVersion) -> bool:
    """判断这个版本在库里是不是真的留有它那一版的数据。

    比对的是"这一版新增了多少"和"库里这一版实际有多少行"：
    - 接入产出的版本：两者一致 → 有快照。
    - 老数据回填的版本：库里可能一行明细都没有 → 没有快照，
      避免被误当成"内容的完整快照"。
    total_record_count 是数据集到这一版为止的累计数（含之前所有版本），
    不能拿来和单版行数比较，否则从第二个版本起会系统性判错。
    """
    claimed = int(version.added_record_count or 0)
    stored = count_version_records(db, version.id)
    if stored <= 0:
        return False
    return claimed > 0 and stored >= claimed


def ensure_dataset_versions(db: Session, dataset_id: int | None = None) -> int:
    """给还没有任何版本记录的数据集补一条基线版本记录。

    用于旧库升级：老代码只写了 datasets.version，这里按该版本号补一条，
    并标记 is_backfilled=True（表示"归到该版本名下"，不是接入任务的产出）。
    可以重复执行，不会重复写入。
    """
    created = 0
    query = select(Dataset)
    if dataset_id is not None:
        query = query.where(Dataset.id == dataset_id)

    for dataset in db.scalars(query).all():
        exists = db.scalar(
            select(DatasetVersion.id).where(DatasetVersion.dataset_id == dataset.id)
        )
        if exists is not None:
            continue

        metadata = dataset.metadata_json or {}
        record_count = int(metadata.get("record_count", 0) or 0)
        storage_gb = float(metadata.get("storage_gb", 0) or 0)
        languages = [str(item) for item in (metadata.get("languages") or [])]
        modalities = [str(item) for item in (metadata.get("modalities") or [])]

        version = dataset.version or "v1.0.0"
        conflict = db.scalar(
            select(DatasetVersion.id).where(
                DatasetVersion.dataset_id == dataset.id,
                DatasetVersion.version == version,
            )
        )
        if conflict is not None:
            continue

        db.add(DatasetVersion(
            dataset_id=dataset.id,
            version=version,
            task_id=None,
            description="历史版本补录：升级前已存在的数据，按原版本号归档",
            added_record_count=record_count,
            total_record_count=record_count,
            # 回填时还不知道库里有多少明细，由 mark_dataset_version_snapshots 按实际行数修正。
            stored_record_count=0,
            storage_gb=storage_gb,
            source_name=str(metadata.get("source_name", "") or ""),
            connector_type=str(metadata.get("connector_type", "legacy") or "legacy"),
            languages=languages,
            modalities=modalities,
            file_ids=[],
            status=dataset.status or "ready",
            is_current=True,
            # 明确标记：这条是升级回填出来的，不是某次接入任务的产出。
            is_backfilled=True,
            # 真实快照与否由 version_has_snapshot() 按实际落库行数判断。
            has_snapshot=False,
            created_at=dataset.created_at or now_shanghai(),
        ))
        created += 1

    if created:
        db.flush()

    return created


def dataset_version_to_dict(
    version: DatasetVersion,
    *,
    stored_record_count: int | None = None,
    has_snapshot: bool | None = None,
) -> dict[str, Any]:
    """版本记录转接口字典。

    字段名同时给出下划线和小驼峰两种写法，兼容新旧前端。
    languages 保持"语言代码字符串数组"，与前端既有约定一致。
    """
    created_at = version.created_at.isoformat() if version.created_at else None
    is_current = bool(version.is_current)
    added = int(version.added_record_count or 0)
    total = int(version.total_record_count or 0)
    stored = (
        int(version.stored_record_count or 0)
        if stored_record_count is None
        else int(stored_record_count)
    )
    snapshot = bool(version.has_snapshot) if has_snapshot is None else bool(has_snapshot)

    result = {
        "id": version.id,
        "dataset_id": version.dataset_id,
        "datasetId": version.dataset_id,
        "version_id": version.version,
        "versionId": version.version,
        "version": version.version,
        "label": version.version,
        "task_id": version.task_id,
        "taskId": version.task_id,
        "description": version.description,
        # 这一版新增了多少 / 到这一版累计多少，两个都保留。
        "added_record_count": added,
        "addedRecordCount": added,
        "total_record_count": total,
        "totalRecordCount": total,
        # 这一版在库里实际落了多少条数据行。
        "stored_record_count": stored,
        "storedRecordCount": stored,
        # 兼容旧字段名，值取"这一版新增"。
        "record_count": added,
        "recordCount": added,
        "storage_gb": float(version.storage_gb or 0),
        "storageGb": float(version.storage_gb or 0),
        "source_name": version.source_name,
        "sourceName": version.source_name,
        "connector_type": version.connector_type,
        "connectorType": version.connector_type,
        "languages": list(version.languages or []),
        "modalities": list(version.modalities or []),
        "file_ids": list(version.file_ids or []),
        "fileIds": list(version.file_ids or []),
        "status": version.status,
        "is_current": is_current,
        "isCurrent": is_current,
        # 老数据回填标记 + 是否真的留有数据快照。
        "is_backfilled": bool(version.is_backfilled),
        "isBackfilled": bool(version.is_backfilled),
        "has_snapshot": snapshot,
        "hasSnapshot": snapshot,
        "created_at": created_at,
        "createdAt": created_at,
    }

    if stored_record_count is not None:
        result["stored_record_count"] = int(stored_record_count)
        result["storedRecordCount"] = int(stored_record_count)

    return result

def dataset_version_summary(db: Session, dataset_id: int) -> dict[str, Any]:
    """数据集详情用的版本概况。"""
    total = int(db.scalar(
        select(func.count(DatasetVersion.id)).where(DatasetVersion.dataset_id == dataset_id)
    ) or 0)

    current = db.scalar(
        select(DatasetVersion)
        .where(DatasetVersion.dataset_id == dataset_id)
        .order_by(DatasetVersion.is_current.desc(), DatasetVersion.id.desc())
        .limit(1)
    )

    record_total = int(db.scalar(
        select(func.count(DatasetRecord.id)).where(DatasetRecord.dataset_id == dataset_id)
    ) or 0)

    current_dict = None
    if current is not None:
        current_dict = dataset_version_to_dict(
            current,
            stored_record_count=count_version_records(db, current.id),
            has_snapshot=version_has_snapshot(db, current),
        )

    return {
        "version_count": total,
        "versionCount": total,
        "current_version": current_dict,
        "currentVersion": current_dict,
        "stored_record_count": record_total,
        "storedRecordCount": record_total,
    }
