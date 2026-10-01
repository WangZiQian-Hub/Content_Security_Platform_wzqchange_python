from collections import Counter
from datetime import timedelta

from fastapi import APIRouter, Query
from sqlalchemy import select

from app.core.response import success
from app.core.time import now_shanghai
from app.core.database import SessionLocal
from app.models.tables import Dataset, Task

MODALITY_LABELS = {
    "text": "文本",
    "image": "图片",
    "video": "视频",
    "audio": "音频",
    "文本": "文本",
    "图片": "图片",
    "视频": "视频",
    "音频": "音频",
}


SOURCE_LABELS = {
    "business": "业务系统",
    "internet": "互联网采集",
    "industry": "行业数据",
    "synthetic": "合成数据",
}

router = APIRouter()

#保证数据是一个字典
def _metadata(dataset: Dataset) -> dict:
    return dataset.metadata_json or {}#前面没值，就返回后面这个空字典

#统计出现的次数，占总次数的百分比
def _distribution(counter: Counter[str], total: int) -> list[dict]:
    if not total:
        return []
    return [
        {"name": name, "value": round(value * 100 / total, 1)}
        for name, value in counter.most_common()
    ]


@router.get("/data-resources/options")
def resource_filter_options():
    """返回数据资源页面筛选器所需的真实数据库选项。"""
    with SessionLocal() as db:
        datasets = list(db.scalars(select(Dataset)).all())
    languages = sorted(
        {
            language
            for dataset in datasets
            for language in (_metadata(dataset).get("languages") or [])
        }
    )
    source_types = sorted({dataset.source_type for dataset in datasets if dataset.source_type})
    modalities = sorted(
        {
            MODALITY_LABELS.get(modality, modality)
            for dataset in datasets
            for modality in (_metadata(dataset).get("modalities") or [])
        }
    )
    return success(
        data={
            "languages": [{"code": language, "name": language} for language in languages],
            "sources": [
                {"code": source_type, "name": SOURCE_LABELS.get(source_type, source_type)}
                for source_type in source_types
            ],
            "modalities": modalities,
        },
        message="数据资源筛选选项查询成功",
    )


@router.get("/data-resources/summary")
def resource_summary(#参数全是前端的url请求里面的内容
    view: str = Query(default="overview"),
    start_date: str | None = Query(default=None),
    end_date: str | None = Query(default=None),
    source_type: str | None = Query(default=None),
    dataset_id: int | None = Query(default=None),
    language: str | None = Query(default=None),
):
    """返回数据资源页面所需的统一汇总结构。"""
    #所有数据集对象，按创建时间从早到晚排序。
    with SessionLocal() as db:
        query = select(Dataset).order_by(Dataset.created_at.asc())
        datasets = list(db.scalars(query).all())
        # 趋势、来源分布只统计真实的数据接入任务；其他治理任务的展示容量
        # 不属于数据接入量，不能混入资源页的统计口径。
        tasks = list(
            db.scalars(
                select(Task)
                .where(
                    Task.capability_code == "data_ingest",
                    Task.status == "succeeded",
                    Task.progress >= 100,
                )
                .order_by(Task.created_at.asc())
            ).all()
        )
        # Only completed ingests that carry parser statistics have a measured
        # source size. Older/demo tasks were populated with display defaults;
        # keeping them out prevents those values from creating fake spikes.
        tasks = [
            task
            for task in tasks
            if isinstance((task.result or {}).get("statistics"), dict)
        ]
        ingest_tasks_all = list(
            db.scalars(select(Task).where(Task.capability_code == "data_ingest")).all()
        )
        # Usage is derived from task references, never from hand-maintained metadata.
        usage_counts = {dataset.id: 0 for dataset in datasets}
        for task in db.scalars(select(Task)).all():
            # Ingest tasks create/populate a dataset; they are not dataset usage.
            if task.capability_code == "data_ingest":
                continue
            references = [
                (task.result or {}).get("dataset_id"),
                (task.input_data or {}).get("dataset_id"),
            ]
            referenced_ids = {
                int(value)
                for value in references
                if isinstance(value, (int, str))
                and not isinstance(value, bool)
                and str(value).strip().lower() != "null"
                and str(value).strip().lstrip("+").isdigit()
            }
            for referenced_id in referenced_ids:
                if referenced_id in usage_counts:
                    usage_counts[referenced_id] += 1
        #如果调用接口时传了 dataset_id，就只保留 id 等于该值的数据集。
    if dataset_id is not None:
        datasets = [item for item in datasets if item.id == dataset_id]
        #只保留元数据中 languages 列表包含指定语言的数据集
    if language:
        datasets = [item for item in datasets if language in (_metadata(item).get("languages") or [])]
        #只保留元数据中 source_type 列表包含指定语言的数据集
    if source_type:
        datasets = [item for item in datasets if item.source_type == source_type]

    selected_dataset_ids = {item.id for item in datasets}
    duplicate_total = 0
    anomaly_total = 0
    for task in ingest_tasks_all:
        references = [
            (task.result or {}).get("dataset_id"),
            (task.input_data or {}).get("dataset_id"),
        ]
        if any(
            isinstance(value, (int, str))
            and not isinstance(value, bool)
            and str(value).strip().lstrip("+").isdigit()
            and int(value) in selected_dataset_ids
            for value in references
        ):
            duplicate_total += int(task.duplicate_count or 0)
            anomaly_total += int(task.anomaly_count or 0)


    #得到数据集的个数
    total_rows = sum(int(_metadata(item).get("record_count", 0) or 0) for item in datasets)


    #数据集总存储量（GB）
    total_storage = sum(
        float(
            (_metadata(item).get("storage_gb", 0))
            or 0
        )
        for item in datasets
    )

    #统计所有数据集中每种语言出现的次数，最终得到一个 Counter 对象，键是语言名称，值是出现次数。
    languages = Counter(
        language_name
        for item in datasets
        for language_name in (_metadata(item).get("languages") or ["zh"])
    )

    # 数据集表是资源容量的唯一口径；接入任务成功后会实时累加到该表，
    # 因而资源页和首页不会因重复统计任务容量而出现不同的“数据总量”。
    displayed_total_storage = total_storage

    # 来源分布按已接入任务的数据量加权，而非仅按数据集个数计数。
    # 历史任务在启动时已补齐 source_name / storage_gb，因此每个来源都有可展示的数据量。
    sources = Counter()
    for task in tasks:
        sources[task.source_name or "未填写来源"] += float(task.storage_gb or 0)
    if not sources:
        for item in datasets:
            sources[_metadata(item).get(
                "source_name",
                SOURCE_LABELS.get(item.source_type, item.source_type),
            )] += float(_metadata(item).get("storage_gb", 0) or 0)

    # 统计所有数据集中每种“模态”（modalities）出现的次数，最终得到一个 Counter 对象。
    modalities = Counter(
        MODALITY_LABELS.get(modality, modality)
        for item in datasets
        for modality in (
            _metadata(item).get("modalities")
            or ["text"]
        )
    )
    #统计所有数据集中每个“质量状态”（quality_status）出现的次数，最终得到一个 Counter 对象。
    quality = Counter(_metadata(item).get("quality_status", "good") for item in datasets)
    #把之前统计出的 quality（质量状态计数）转换成带中文标签的百分比分布列表，用于前端展示。
    quality_labels = {"excellent": "优秀", "good": "良好", "poor": "较差"}
    quality_distribution = [
        {"name": quality_labels.get(name, name), "value": round(value * 100 / len(datasets), 1)}
        for name, value in quality.most_common()
    ] if datasets else []
    # 最近七天新增数据量（GB）由已接入任务的实际数据量汇总。
    now = now_shanghai()
    dates = [(now - timedelta(days=offset)).date().isoformat() for offset in range(6, -1, -1)]
    daily_amounts = Counter()
    for task in tasks:
        if task.created_at:
            daily_amounts[task.created_at.date().isoformat()] += float(task.storage_gb or 0)
    # Keep enough precision for small file ingests; rounding to one GB would
    # turn legitimate KB-sized uploads into a misleading zero.
    added = [round(daily_amounts[day], 9) for day in dates]
    # The trend answers a different question from the dataset total: it is
    # daily measured ingest-task volume. Do not backfill a cumulative series
    # from dataset storage, which would mix two incompatible measures.
    totals = []

    quality_score = round(
        sum(float(_metadata(item).get("quality_score", 95.0) or 95.0) for item in datasets) / len(datasets),
        1,
    ) if datasets else 0
    # 生成数据集使用排行榜：先按真实任务引用次数排序，再计算使用占比并截取前十名。
    ranked_datasets = sorted(
        datasets,
        key=lambda item: usage_counts.get(item.id, 0),
        reverse=True,
    )[:10]
    total_uses = sum(usage_counts.get(item.id, 0) for item in datasets)
    ranking = [
        {
            "name": item.name,
            "source": _metadata(item).get("source_name", "数据集"),
            "storageGb": float(_metadata(item).get("storage_gb", 0) or 0),
            "uses": usage_counts.get(item.id, 0),
            "share": round((usage_counts.get(item.id, 0) / total_uses) * 100, 1) if total_uses else 0,
        }
        for item in ranked_datasets
    ]

    kpis = [
        {"id": "resource-datasets", "label": "数据集数量", "value": len(datasets), "unit": "个", "change_rate": 0, "icon": "Coin"},
        {"id": "resource-records", "label": "数据记录数", "value": total_rows, "unit": "条", "change_rate": 0, "icon": "Document"},
        {"id": "storage", "label": "数据总量", "value": round(displayed_total_storage, 3), "unit": "GB", "change_rate": 0, "icon": "Box"},
        {"id": "resource-quality", "label": "平均质量分", "value": quality_score, "unit": "%", "change_rate": 0, "icon": "CircleCheckFilled"},
    ]
    result = {
        "kpis": kpis,
        "trend": {"dates": dates, "added": added, "total": totals},
        "modalities": _distribution(modalities, sum(modalities.values())),
        # 与模态分布使用同一份数据库元数据，供前端环形图圆心展示标签累计数。
        "modalityCount": sum(modalities.values()),
        "sources": _distribution(sources, sum(sources.values())),
        "languages": _distribution(languages, sum(languages.values())),
        "quality": quality_distribution,
        "qualityScore": quality_score,
        "issues": [
            {"name": "重复样本总数", "value": duplicate_total},
            {"name": "缺失样本总数", "value": anomaly_total},
        ],
        "ranking": ranking,
    }
    return success(data=result, message=f"数据资源{view}汇总查询成功")
