from types import SimpleNamespace

from app.services.data_processing import _evaluate


def row(record_id: int, title: str, content: str):
    return SimpleNamespace(id=record_id, payload={"title": title, "content": content})


def test_complete_fields_then_deduplicate_is_deterministic():
    comparisons, kept, audits, counts = _evaluate([
        row(1, "A", "Hello  World"),
        row(2, "B", "hello world"),
        row(3, "", "discard"),
        row(4, "C", ""),
    ], ["complete_fields", "deduplicate"])
    assert [item.id for item in kept] == [1]
    assert counts["duplicate_count"] == 1
    assert counts["anomaly_count"] == 2
    assert [(item["record"].id, item["rule"], item["kept"].id if item["kept"] else None) for item in audits] == [
        (2, "deduplicate", 1), (3, "complete_fields", None), (4, "complete_fields", None)
    ]
    assert comparisons[0]["id"] == "1"


def test_unknown_rules_are_reported_without_becoming_fake_processing():
    _, kept, _, counts = _evaluate([row(1, "A", "same")], ["legacy_rule"])
    assert [item.id for item in kept] == [1]
    assert counts["unknown_rule_count"] == 1

