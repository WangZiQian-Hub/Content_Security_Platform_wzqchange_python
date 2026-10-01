"""本地文件接入：解析上传的文件，并逐条生成可入库的样本记录。

支持格式：TXT（Tab 分隔）、CSV、XLSX、JSON（数组或 JSONL）。
每行 / 每个对象 = 一个样本；PDF 不再支持。

字段契约（标准字段名 ← 可接受的别名，大小写不敏感）：
    source_id    ← id / 样本id / sample_id / 编号
    title        ← title / 标题 / 题目 / 名称 / name          必填
    content      ← content / 内容 / 正文 / 文本 / text / body  必填
    language     ← language / lang / 语言                      可选（缺失则识别）
    published_at ← published_at / publish_time / 发布时间 / 日期 可选（缺失则用数据集创建日期）
"""
from __future__ import annotations

import csv
import io
import json
import re
from datetime import date, datetime, timezone, timedelta
from pathlib import Path
from typing import Any

SUPPORTED_EXTENSIONS = (".txt", ".csv", ".xlsx", ".json", ".jsonl")
UPLOAD_DIR = Path("storage/uploads")
MAX_ROWS = 100_000
MAX_SKIPPED_DETAIL = 100
RAW_PREVIEW_CHARS = 200

FIELD_ALIASES: dict[str, str] = {}
for _standard, _names in (
    ("source_id", ("id", "样本id", "样本编号", "sample_id", "source_id", "编号")),
    ("title", ("title", "标题", "题目", "名称", "name")),
    ("content", ("content", "内容", "正文", "文本", "text", "body")),
    ("language", ("language", "lang", "语言")),
    ("published_at", ("published_at", "publish_time", "published", "发布时间", "日期", "date")),
):
    for _name in _names:
        FIELD_ALIASES[_name.strip().lower()] = _standard
del _standard, _names, _name

# TXT 文件没有表头时，字段按这个顺序排列
TXT_FIELD_ORDER = ("source_id", "title", "content", "language", "published_at")
REQUIRED_FIELDS = ("title", "content")

ZH_VALUES = {"zh", "cn", "zh-cn", "zh_cn", "中文", "汉语", "简体中文", "chinese"}
EN_VALUES = {"en", "eng", "en-us", "en_us", "英文", "英语", "english"}
DATE_FORMATS = ("%Y-%m-%d", "%Y/%m/%d", "%Y.%m.%d", "%Y年%m月%d日", "%Y%m%d")


# ---------------------------------------------------------------- 基础工具

def _clean_key(value: Any) -> str:
    return str(value if value is not None else "").strip().lower()


def map_field_name(raw: Any) -> str | None:
    """把文件里的列名映射成平台标准字段名；无法识别返回 None。"""
    return FIELD_ALIASES.get(_clean_key(raw))


def text_value(value: Any) -> str:
    """把任意单元格值转成干净的字符串。"""
    if value is None:
        return ""
    if isinstance(value, str):
        return value.strip()
    if isinstance(value, datetime):
        return value.strftime("%Y-%m-%d %H:%M:%S")
    if isinstance(value, date):
        return value.isoformat()
    if isinstance(value, bool):
        return "true" if value else "false"
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return str(value).strip()


def detect_language(text: str) -> str:
    """判断文本主要语言：zh / en / other（不依赖任何第三方库）。"""
    if not isinstance(text, str) or not text.strip():
        return "other"
    counters = {
        "kana": len(re.findall(r"[\u3040-\u30ff]", text)),
        "hangul": len(re.findall(r"[\uac00-\ud7af\u1100-\u11ff]", text)),
        "han": len(re.findall(r"[\u4e00-\u9fff]", text)),
        "latin": len(re.findall(r"[A-Za-z]", text)),
    }
    if counters["kana"] > 0 or counters["hangul"] > 0:
        return "other"
    if counters["han"] > counters["latin"]:
        return "zh"
    if counters["latin"] > 0:
        return "en"
    if counters["han"] > 0:
        return "zh"
    return "other"


def normalize_language(raw: Any) -> tuple[str, str]:
    """返回 (标准语言码, 取值来源)。空值返回 ('', '')，表示需要自动识别。"""
    value = _clean_key(raw)
    if not value:
        return "", ""
    if value in ZH_VALUES:
        return "zh", "given"
    if value in EN_VALUES:
        return "en", "given"
    return "other", "given"


def normalize_date(raw: Any) -> str | None:
    """把常见日期写法统一成 YYYY-MM-DD；无法识别返回 None。"""
    if isinstance(raw, datetime):
        return raw.date().isoformat()
    if isinstance(raw, date):
        return raw.isoformat()
    value = text_value(raw)
    if not value:
        return None
    value = value.replace("T", " ").split(" ")[0].strip()
    for fmt in DATE_FORMATS:
        try:
            return datetime.strptime(value, fmt).date().isoformat()
        except ValueError:
            continue
    return None


def _read_text(path: Path) -> str:
    """按 UTF-8（含 BOM）优先、GBK 兜底读取文本文件。"""
    data = path.read_bytes()
    for encoding in ("utf-8-sig", "gbk"):
        try:
            return data.decode(encoding)
        except UnicodeDecodeError:
            continue
    raise ValueError(f"文件编码无法识别（既不是 UTF-8 也不是 GBK）：{path.name}")


def _raw_preview(row: dict[str, Any]) -> str:
    parts = [
        f"{key}={text_value(row.get(key))}"
        for key in ("source_id", "title", "content", "language", "published_at")
        if text_value(row.get(key))
    ]
    preview = " | ".join(parts)
    return preview[:RAW_PREVIEW_CHARS]


# ---------------------------------------------------------------- 各格式解析

def _build_rows(header: list[str | None], body: list[tuple[int, list[Any]]]) -> list[dict[str, Any]]:
    """按表头（或固定顺序）把二维表转成字典列表，附带 _row_number 行号。"""
    rows: list[dict[str, Any]] = []
    for line_number, cells in body:
        record: dict[str, Any] = {"_row_number": line_number}
        for position, value in enumerate(cells):
            if position >= len(header):
                break
            field = header[position]
            if field:
                record[field] = value
        rows.append(record)
    return rows


def _non_empty_lines(text: str) -> list[tuple[int, str]]:
    return [(number, line) for number, line in enumerate(text.splitlines(), start=1) if line.strip()]


def parse_txt(path: Path) -> list[dict[str, Any]]:
    """TXT：一行一条，字段用 Tab 分隔；首行若是字段名则按名字匹配。"""
    numbered = _non_empty_lines(_read_text(path))
    if not numbered:
        raise ValueError("文件里没有有效数据行")
    first_line = numbered[0][1]
    if "\t" in first_line:
        delimiter = "\t"
    elif "|" in first_line:
        delimiter = "|"
    else:
        raise ValueError("TXT 文件需要用 Tab（制表符）分隔字段，或用竖线 | 分隔")
    table = [(number, [cell.strip() for cell in line.split(delimiter)]) for number, line in numbered]
    mapped = [map_field_name(cell) for cell in table[0][1]]
    if sum(1 for item in mapped if item) >= 2:
        return _build_rows(mapped, table[1:])
    return _build_rows(list(TXT_FIELD_ORDER), table)


def parse_csv(path: Path) -> list[dict[str, Any]]:
    """CSV：首行必须是表头，按表头名匹配字段。"""
    reader = csv.reader(io.StringIO(_read_text(path)))
    numbered = [
        (number, cells)
        for number, cells in enumerate(reader, start=1)
        if any(text_value(cell) for cell in cells)
    ]
    if not numbered:
        raise ValueError("文件里没有有效数据行")
    header = [map_field_name(cell) for cell in numbered[0][1]]
    if not any(header):
        raise ValueError("CSV 文件第一行必须是表头（字段名），例如：id,标题,内容,语言,发布时间")
    return _build_rows(header, numbered[1:])


def parse_xlsx(path: Path) -> list[dict[str, Any]]:
    """XLSX：取第一个工作表，首行必须是表头。"""
    try:
        from openpyxl import load_workbook
    except ImportError as error:  # pragma: no cover - 依赖缺失时的明确提示
        raise ValueError("解析 XLSX 需要安装 openpyxl：在后端目录执行 uv add openpyxl") from error

    workbook = load_workbook(path, read_only=True, data_only=True)
    try:
        sheet = workbook.worksheets[0]
        numbered: list[tuple[int, list[Any]]] = []
        for number, cells in enumerate(sheet.iter_rows(values_only=True), start=1):
            values = list(cells)
            if any(text_value(cell) for cell in values):
                numbered.append((number, values))
    finally:
        workbook.close()

    if not numbered:
        raise ValueError("文件里没有有效数据行")
    header = [map_field_name(cell) for cell in numbered[0][1]]
    if not any(header):
        raise ValueError("XLSX 文件第一行必须是表头（字段名），例如：id,标题,内容,语言,发布时间")
    return _build_rows(header, numbered[1:])


def parse_json(path: Path) -> list[dict[str, Any]]:
    """JSON：支持顶层数组，也支持一行一个对象的 JSONL。"""
    text = _read_text(path)
    payload: Any = None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        payload = None

    items: list[tuple[int, Any]] = []
    if payload is None:
        for number, line in enumerate(text.splitlines(), start=1):
            line = line.strip()
            if not line:
                continue
            try:
                items.append((number, json.loads(line)))
            except json.JSONDecodeError as error:
                raise ValueError(f"第 {number} 行不是合法 JSON：{error}") from error
    elif isinstance(payload, list):
        items = list(enumerate(payload, start=1))
    elif isinstance(payload, dict):
        items = [(1, payload)]
    else:
        raise ValueError("JSON 顶层必须是数组或对象")

    rows: list[dict[str, Any]] = []
    for number, item in items:
        if not isinstance(item, dict):
            raise ValueError(f"第 {number} 条不是 JSON 对象")
        record: dict[str, Any] = {"_row_number": number}
        for key, value in item.items():
            field = map_field_name(key)
            if field:
                record[field] = value
        rows.append(record)
    if not rows:
        raise ValueError("文件里没有有效数据行")
    return rows


PARSERS = {
    ".txt": parse_txt,
    ".csv": parse_csv,
    ".xlsx": parse_xlsx,
    ".json": parse_json,
    ".jsonl": parse_json,
}


# ---------------------------------------------------------------- 对外入口

def parse_file(path: Path) -> list[dict[str, Any]]:
    """按扩展名选择解析器。"""
    extension = path.suffix.lower()
    parser = PARSERS.get(extension)
    if parser is None:
        raise ValueError(f"不支持的文件类型：{extension or path.name}")
    rows = parser(path)
    if len(rows) > MAX_ROWS:
        raise ValueError(f"单个文件最多解析 {MAX_ROWS} 行，请拆分后再上传")
    return rows


def locate_uploaded_files(file_ids: object) -> list[Path]:
    """根据上传接口返回的 file_id 在 uploads 目录里找到真实文件。"""
    if not isinstance(file_ids, list):
        return []
    found: list[Path] = []
    for file_id in file_ids:
        if not isinstance(file_id, str) or not file_id.startswith("file_"):
            continue
        if not file_id.replace("_", "").isalnum():
            continue
        for candidate in sorted(UPLOAD_DIR.glob(f"{file_id}.*")):
            if candidate.is_file():
                found.append(candidate)
    return found


def parse_local_files(file_ids: object) -> dict[str, Any]:
    """解析本次任务上传的全部文件，返回原始行和文件信息。"""
    paths = locate_uploaded_files(file_ids)
    if not paths:
        raise ValueError("没有找到上传的文件，请重新选择文件后再提交")
    rows: list[dict[str, Any]] = []
    total_rows = 0
    byte_count = 0
    names: list[str] = []
    for path in paths:
        parsed = parse_file(path)
        total_rows += len(parsed)
        byte_count += path.stat().st_size
        names.append(path.name)
        rows.extend(parsed)
    if total_rows > MAX_ROWS:
        raise ValueError(f"本次接入共 {total_rows} 行，超过单次上限 {MAX_ROWS} 行，请分批上传")
    return {"rows": rows, "total_rows": total_rows, "bytes": byte_count, "file_names": names}


def normalize_rows(
    rows: list[dict[str, Any]],
    *,
    detect_language_enabled: bool,
    fallback_published_at: str | None,
) -> tuple[list[dict[str, Any]], list[dict[str, Any]]]:
    """逐行校验并归一化字段；返回 (通过的行, 跳过明细)。

    通过的行还**没有** sample_id，需要等目标数据集确定后再补。
    """
    accepted: list[dict[str, Any]] = []
    skipped: list[dict[str, Any]] = []

    for row in rows:
        line_number = row.get("_row_number")
        title = text_value(row.get("title"))
        content = text_value(row.get("content"))

        reason = None
        if not title:
            reason = "title 为空"
        elif not content:
            reason = "content 为空"
        if reason:
            skipped.append(
                {"row": line_number, "reason": reason, "raw": _raw_preview(row)}
            )
            continue

        language, language_source = normalize_language(row.get("language"))
        if not language:
            if detect_language_enabled:
                language, language_source = detect_language(content), "detected"
            else:
                language, language_source = "", ""

        published_at = normalize_date(row.get("published_at"))
        published_at_source = "given"
        if not published_at:
            published_at = fallback_published_at
            published_at_source = "fallback"

        item: dict[str, Any] = {
            "_row_number": line_number,
            "title": title,
            "content": content,
            "language": language,
            "language_source": language_source,
            "published_at": published_at,
            "published_at_source": published_at_source,
        }
        source_id = text_value(row.get("source_id"))
        if source_id:
            item["source_id"] = source_id
        if row.get("_dedup_key"):
            item["_dedup_key"] = row["_dedup_key"]
        accepted.append(item)

    return accepted, skipped


def normalize_all_rows(
    rows: list[dict[str, Any]],
    *,
    detect_language_enabled: bool,
    fallback_published_at: str | None,
) -> list[dict[str, Any]]:
    """Normalize every parsed row for raw retention, including invalid rows."""
    normalized: list[dict[str, Any]] = []
    for row in rows:
        content = text_value(row.get("content"))
        language, language_source = normalize_language(row.get("language"))
        if not language and detect_language_enabled:
            language, language_source = detect_language(content), "detected"
        published_at = normalize_date(row.get("published_at")) or fallback_published_at
        item: dict[str, Any] = {
            "_row_number": row.get("_row_number"),
            "title": text_value(row.get("title")),
            "content": content,
            "language": language,
            "language_source": language_source,
            "published_at": published_at,
            "published_at_source": "given" if normalize_date(row.get("published_at")) else "fallback",
        }
        source_id = text_value(row.get("source_id"))
        if source_id:
            item["source_id"] = source_id
        if row.get("_dedup_key"):
            item["_dedup_key"] = row["_dedup_key"]
        normalized.append(item)
    return normalized


def assign_sample_ids(items: list[dict[str, Any]], dataset_id: int, start_sequence: int) -> list[dict[str, Any]]:
    """给通过校验的样本按 {datasetId}_{序号} 编号，序号从 start_sequence 开始。"""
    payloads: list[dict[str, Any]] = []
    sequence = start_sequence
    for item in items:
        payload = {"sample_id": f"{dataset_id}_{sequence}", **item}
        payload.pop("_row_number", None)
        payload.pop("_dedup_key", None)
        payloads.append(payload)
        sequence += 1
    return payloads


def quality_score_from(total_rows: int, skipped_rows: int) -> float:
    """基础质量检测：100 × (1 - 跳过行数 / 总行数)，保留 1 位小数。"""
    if total_rows <= 0:
        return 100.0
    passed = max(0, total_rows - skipped_rows)
    return round(passed * 100 / total_rows, 1)


def normalize_content(value: Any) -> str:
    return " ".join(text_value(value).replace("\u3000", " ").split()).casefold()


def summarize(
    parsed_rows: list[dict[str, Any]],
    accepted: list[dict[str, Any]],
    skipped: list[dict[str, Any]],
    *,
    existing_contents: set[str] | None = None,
) -> dict[str, Any]:
    """Calculate this batch's real sample, duplicate, anomaly, and insert counts.

    Duplicate rows are counted for statistics but remain eligible for raw retention.
    Passing ``None`` for existing_contents records that cross-batch deduplication was
    skipped because the target dataset is larger than the configured threshold.
    """
    total_rows = len(parsed_rows)
    title_missing_count = sum(1 for item in skipped if item.get("reason") == "title 为空")
    anomaly_count = sum(
        1
        for item in skipped
        if item.get("reason") == "content 为空"
    )
    seen = set(existing_contents or ())
    duplicate_count = 0
    duplicate_detail: list[dict[str, Any]] = []
    for item in accepted:
        key = item.get("_dedup_key") or normalize_content(item.get("content"))
        if key in seen:
            duplicate_count += 1
            duplicate_detail.append({"row": item.get("_row_number"), "reason": "content 重复"})
            continue
        seen.add(key)
    skipped_detail = (list(skipped) + duplicate_detail)[:MAX_SKIPPED_DETAIL]
    inserted_count = total_rows
    return {
        "total_rows": total_rows,
        "success_count": inserted_count,
        "duplicate_count": duplicate_count,
        "anomaly_count": anomaly_count,
        "title_missing_count": title_missing_count,
        "inserted_count": inserted_count,
        "content_column_found": True,
        "cross_batch_dedup_skipped": existing_contents is None,
        "skipped_detail": skipped_detail,
    }


def today_text() -> str:
    """返回北京时间的今天（YYYY-MM-DD）。"""
    return (datetime.now(timezone(timedelta(hours=8))).date()).isoformat()
