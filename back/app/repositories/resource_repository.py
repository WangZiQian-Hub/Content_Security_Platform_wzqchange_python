# 用字典和列表模拟数据库中的资源表
# 当前先只放数据集，后续会增加模型和指标。

# RESOURCES = {
#     "datasets": [
#         {
#             "id": 1,
#             "name": "跨文化交流语料",
#             "version": "v1.0.0",
#             "description": "用于内容安全测试的模拟数据集",
#         },
#         {
#             "id": 2,
#             "name": "行业风险标注数据集",
#             "version": "v1.0.0",
#             "description": "包含风险标签的模拟数据集",
#         },
#     ],

#     "models": [
#         {
#             "id": 1,
#             "name": "内容安全识别模型",
#             "version": "v1.0.0",
#             "status": "running",
#             "description": "用于模拟语义风险识别的模型",
#         },
#         {
#             "id": 2,
#             "name": "多模态审核模型",
#             "version": "v1.0.0",
#             "status": "ready",
#             "description": "用于模拟图文内容审核的模型",
#         },
#     ],

#     "metrics": [
#         {
#             "id": 1,
#             "code": "risk_recall",
#             "name": "风险召回率",
#             "target": 0.95,
#             "unit": "%",
#         },
#         {
#             "id": 2,
#             "code": "false_positive_rate",
#             "name": "误报率",
#             "target": 0.05,
#             "unit": "%",
#         },
#     ],
# }


# def list_resources(resource_type: str):
#     """
#     查询某一类资源的全部数据。
#     例如：list_resources("datasets")
#     """
#     return RESOURCES.get(resource_type, [])


# def find_resource(resource_type: str, resource_id: int):
#     """
#     根据资源类型和 ID 查询一条资源。
#     例如：find_resource("datasets", 1)
#     """
#     resources = list_resources(resource_type)

#     for resource in resources:
#         if resource["id"] == resource_id:
#             return resource

#     return None




# def create_dataset(data: dict):
#     """
#     把一个新数据集加入模拟资源表。

#     以后这里会改为：
#     INSERT INTO datasets (...)
#     """

#     datasets = RESOURCES["datasets"]

#     # 生成下一个 ID。
#     # 如果当前没有数据集，就从 1 开始。
#     if datasets:
#         new_id = max(dataset["id"] for dataset in datasets) + 1
#     else:
#         new_id = 1

#     new_dataset = {
#         "id": new_id,
#         "name": data["name"],
#         "version": "v1.0.0",
#         "description": data["description"],
#         "record_count": data["record_count"],
#         "languages": data["languages"],
#     }

#     datasets.append(new_dataset)

#     return new_dataset











from typing import Any

from sqlalchemy import func, select

from app.core.database import SessionLocal
from app.models.tables import (
    Dataset,
    DatasetRecord,
    DatasetVersion,
    Metric,
    Model,
    Resource,
    Task,
    TrainingTask,
)
from app.services.resource_display import dataset_display_defaults, model_version_default


def normalize_dataset_name(name: str) -> str:
    """Normalize dataset names for case-insensitive duplicate checks."""
    return " ".join((name or "").replace("\u3000", " ").split()).casefold()


def find_dataset_by_name(name: str, exclude_id: int | None = None) -> Dataset | None:
    """Find a dataset by normalized name without relying on MySQL collation."""
    normalized_name = normalize_dataset_name(name)
    with SessionLocal() as db:
        datasets = db.scalars(select(Dataset)).all()
        for dataset in datasets:
            if exclude_id is not None and dataset.id == exclude_id:
                continue
            if normalize_dataset_name(dataset.name) == normalized_name:
                return dataset
    return None


from typing import Any

MODALITY_LABELS = {
    "text": "文本",
    "image": "图片",
    "video": "视频",
    "audio": "音频",
}

SOURCE_LABELS = {
    "business": "业务系统",
    "internet": "互联网采集",
    "industry": "行业数据",
    "synthetic": "合成数据",
}


def resource_to_dict(resource, version_count: int | None = None) -> dict[str, Any]:
    metadata = dict(resource.metadata_json or {})

    modalities = [
        MODALITY_LABELS.get(item, item)
        for item in metadata.get("modalities", ["text"])
    ]

    languages = metadata.get("languages", ["zh"])

    result = {
        "id": resource.id,
        "name": resource.name,
        "category": resource.category,

        "source_type": getattr(resource, "source_type", "business"),
        "source_name": metadata.get(
            "source_name",
            SOURCE_LABELS.get(
                getattr(resource, "source_type", "business"),
                getattr(resource, "source_type", "business"),
            ),
        ),

        # 内部任务服务使用 version
        "version": resource.version,

        # 前端数据集页面使用 versionId
        "version_id": resource.version,

        "status": resource.status,
        "description": resource.description,
        "modalities": modalities,
        "languages": languages,
        "row_count": int(metadata.get("record_count", 0) or 0),
        "storage_gb": float(metadata.get("storage_gb", 0) or 0),
        "quality_score": float(metadata.get("quality_score", 0) or 0),
        "quality_status": metadata.get("quality_status", "good"),
        "owner": metadata.get("owner", "平台管理员"),
        "created_at": (
            resource.created_at.isoformat()
            if resource.created_at
            else None
        ),
        "updated_at": (
            resource.created_at.isoformat()
            if resource.created_at
            else None
        ),
        "metadata": metadata,
    }

    if version_count is not None:
        # 数据集列表直接显示"共几个版本"，前端不必逐条再问版本接口。
        result["version_count"] = int(version_count)
        result["versionCount"] = int(version_count)

    return result


def metric_to_dict(metric: Metric) -> dict[str, Any]:
    """
    把指标对象转换成接口返回字典。
    """

    return {
        "metric_code": metric.metric_code,
        "name": metric.name,
        "category": metric.category,
        "target": metric.target_value,
        "unit": metric.unit,
        "description": metric.description,
    }


def list_resources(resource_type: str):
    """
    查询数据集或模型。

    resource_type:
    datasets -> 查询数据集
    models   -> 查询模型
    metrics  -> 查询指标
    """

    with SessionLocal() as db:
        if resource_type == "metrics":
            metrics = db.scalars(
                select(Metric).order_by(Metric.metric_code.asc())
            ).all()

            return [
                metric_to_dict(metric)
                for metric in metrics
            ]

        resource_model = {
            "datasets": Dataset,
            "models": Model,
        }.get(resource_type)

        if resource_model is None:
            return []

        resources = db.scalars(
            select(resource_model).order_by(resource_model.id.desc())
        ).all()

        if resource_type == "models":
            # “内容安全识别模型”是训练与调用面板的内置当前模型，
            # 不再重复展示在下方模型管理列表中。
            resources = [
                resource
                for resource in resources
                if resource.name != "内容安全识别模型"
            ]

            # 模型管理页同名模型只展示最新注册的一条，历史版本仍保留在数据库。
            unique_resources = []
            seen_names = set()

            for resource in resources:
                normalized_name = " ".join(
                    (resource.name or "").split()
                ).casefold()

                if normalized_name in seen_names:
                    continue

                seen_names.add(normalized_name)
                unique_resources.append(resource)

            resources = unique_resources

        # 数据集附带版本数量；查不到时按 0 处理，不影响列表返回。
        counts: dict[int, int] = {}
        if resource_type == "datasets" and resources:
            counts = dict(
                db.execute(
                    select(DatasetVersion.dataset_id, func.count(DatasetVersion.id))
                    .where(
                        DatasetVersion.dataset_id.in_(
                            [resource.id for resource in resources]
                        )
                    )
                    .group_by(DatasetVersion.dataset_id)
                ).all()
            )

        return [
            resource_to_dict(resource, counts.get(resource.id))
            if resource_type == "datasets"
            else resource_to_dict(resource)
            for resource in resources
        ]


def find_resource(resource_type: str, resource_id: int):
    """
    根据资源类型和 ID 查询数据集或模型。
    """

    resource_model = {
        "datasets": Dataset,
        "models": Model,
    }.get(resource_type)

    if resource_model is None:
        return None

    with SessionLocal() as db:
        resource = db.scalar(
            select(resource_model).where(resource_model.id == resource_id)
        )

        if resource is None:
            return None

        return resource_to_dict(resource)


def create_dataset(data: dict[str, Any]):
    """
    在 MySQL 中创建一条数据集记录。
    """

    metadata = {
        "record_count": data.get("record_count", 0),
        "languages": data.get("languages", []),
    }

    dataset = Dataset(
        name=data["name"],
        category=data.get("category", "通用"),
        source_type=data.get("source_type", "business"),
        version=data.get("version", "v1.0.0"),
        status=data.get("status", "ready"),
        description=data.get("description", ""),
        metadata_json=metadata,
    )

    with SessionLocal() as db:
        db.add(dataset)
        db.commit()
        db.refresh(dataset)

        storage_gb, record_count, quality_score = dataset_display_defaults(
            f"{dataset.id}:{dataset.name}"
        )
        metadata = dict(dataset.metadata_json or {})
        if int(metadata.get("record_count", 0) or 0) <= 0:
            metadata["record_count"] = record_count
        if float(metadata.get("storage_gb", 0) or 0) <= 0:
            metadata["storage_gb"] = storage_gb
        if float(metadata.get("quality_score", 0) or 0) <= 0:
            metadata["quality_score"] = quality_score
        dataset.metadata_json = metadata
        db.commit()
        db.refresh(dataset)

        # 新建数据集立刻补一条初始版本记录，保证它一出生就有版本清单。
        from app.services.versioning import ensure_dataset_versions

        if ensure_dataset_versions(db, dataset.id):
            db.commit()
            db.refresh(dataset)

        return resource_to_dict(dataset, 1)


def find_metric(metric_code: str):
    """
    根据指标编码查询指标。
    """
    with SessionLocal() as db:
        metric = db.scalar(
            select(Metric).where(
                Metric.metric_code == metric_code
            )
        )

        if metric is None:
            return None

        return metric_to_dict(metric)


def create_model(data: dict[str, Any]):
    """
    在 MySQL 中注册一个模型。
    """

    requested_version = data.get("version")
    model = Model(
        name=data["name"],
        category=data.get(
            "category",
            "内容审核",
        ),
        version=requested_version or "v1.0.0",
        status="ready",
        description=data.get(
            "description",
            "",
        ),
        metadata_json=data.get(
            "metadata",
            {},
        ),
    )

    with SessionLocal() as db:
        db.add(model)
        db.flush()
        # 前端表单默认值为 v1.0.0 时，自动改为该模型独有的语义化版本。
        if not requested_version or requested_version == "v1.0.0":
            model.version = model_version_default(model.id, model.name)
        db.commit()
        db.refresh(model)

        return resource_to_dict(model)

def update_dataset(dataset_id: int, data: dict[str, Any]):
    with SessionLocal() as db:
        dataset = db.scalar(
            select(Dataset).where(Dataset.id == dataset_id)
        )

        if dataset is None:
            return None

        if "name" in data:
            duplicate = find_dataset_by_name(data["name"], exclude_id=dataset_id)
            if duplicate is not None:
                raise ValueError(f"已存在同名数据集：{data['name']}")

        # 更新数据表中的普通字段
        for field in (
            "name",
            "category",
            "source_type",
            "version",
            "status",
            "description",
        ):
            if field in data:
                setattr(dataset, field, data[field])

        # 保留原有元数据，再覆盖本次传入的值
        metadata = dict(dataset.metadata_json or {})

        if data.get("metadata"):
            metadata.update(data["metadata"])

        for field in (
            "record_count",
            "languages",
            "modalities",
        ):
            if field in data:
                metadata[field] = data[field]

        dataset.metadata_json = metadata

        db.commit()
        db.refresh(dataset)

        return resource_to_dict(dataset)


def delete_dataset(dataset_id: int) -> int:
    """Delete exactly one dataset and its own ingest records in one transaction."""
    if not isinstance(dataset_id, int) or isinstance(dataset_id, bool) or dataset_id <= 0:
        raise ValueError("数据集 id 必须是正整数")
    with SessionLocal() as db:
        dataset = db.scalar(select(Dataset).where(Dataset.id == dataset_id))
        if dataset is None:
            raise LookupError(f"数据集不存在：{dataset_id}")
        if dataset_id in {1, 2, 3, 4}:
            raise ValueError("演示数据集不允许删除")
        ingest_tasks: list[Task] = []
        governance_refs: list[Task] = []
        for task in db.scalars(select(Task)).all():
            references = [
                (task.input_data or {}).get("dataset_id"),
                (task.result or {}).get("dataset_id"),
            ]
            references = [
                value
                for value in references
                if isinstance(value, (int, str))
                and not isinstance(value, bool)
                and str(value).strip().lower() != "null"
            ]
            if not any(str(value) == str(dataset_id) for value in references):
                continue
            if task.capability_code == "data_ingest":
                ingest_tasks.append(task)
            else:
                governance_refs.append(task)
        training_refs = [item for item in db.scalars(select(TrainingTask)).all() if str(item.dataset_id) == str(dataset_id)]
        if training_refs:
            raise ValueError("数据集已被模型训练任务引用，无法删除")
        if governance_refs:
            raise ValueError("数据集已被数据治理任务引用，无法删除")
        db.query(DatasetRecord).filter(DatasetRecord.dataset_id == dataset_id).delete(synchronize_session=False)
        # 版本记录属于数据集本身，删除数据集时一并清理，避免留下无主版本。
        db.query(DatasetVersion).filter(DatasetVersion.dataset_id == dataset_id).delete(synchronize_session=False)
        for task in ingest_tasks:
            db.delete(task)
        db.delete(dataset)
        db.commit()
        return dataset_id
