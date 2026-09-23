from __future__ import annotations

import json

import pytest

from org_audit.agent import MockProvider, analyze_documents
from org_audit.models import Fragment
from org_audit.validation import ModelOutputError, parse_json_object, validate_extractions, validate_findings


BEFORE = Fragment("F-BEFORE", "ДО", "before.txt", "текст, строка 2", "Проверяет резервное оборудование.", "Отдел эксплуатации")
AFTER = Fragment("F-AFTER", "ПОСЛЕ", "after.txt", "текст, строка 3", "Ежедневно осматривает резервное оборудование.", "Служба эксплуатации")
AFTER_DUP = Fragment("F-DUP", "ПОСЛЕ", "after.txt", "текст, строка 4", "Осматривает резервное оборудование.", "Группа контроля")


def test_extraction_rejects_unknown_ids():
    raw = json.dumps(
        {
            "before_functions": [{"function": "Осмотр", "unit": "Отдел", "evidence_ids": ["MISSING"]}],
            "after_functions": [],
        }
    )
    result, issues = validate_extractions(raw, [BEFORE])

    assert result["ДО"] == []
    assert any("неизвестный ID" in item for item in issues)


def test_findings_require_known_evidence_from_both_sides():
    raw = json.dumps(
        {
            "findings": [
                {
                    "category": "preserved",
                    "function": "Проверка оборудования",
                    "explanation": "Смысл сохранён.",
                    "recommendation": "Сверить регламент.",
                    "before_evidence_ids": [BEFORE.id],
                    "after_evidence_ids": [AFTER.id],
                }
            ]
        }
    )
    findings, issues = validate_findings(raw, [BEFORE, AFTER])

    assert not issues
    assert len(findings) == 1
    assert findings[0].before_unit == "Отдел эксплуатации"
    assert findings[0].after_unit == "Служба эксплуатации"
    assert findings[0].before_evidence[0].text == BEFORE.text


def test_unknown_or_wrong_side_citations_are_not_shown():
    unknown = json.dumps(
        {
            "findings": [
                {
                    "category": "not_found",
                    "function": "Учёт запасов",
                    "explanation": "Не найдено.",
                    "recommendation": "Проверить.",
                    "before_evidence_ids": [BEFORE.id],
                    "after_evidence_ids": ["MODEL-INVENTED"],
                }
            ]
        }
    )
    wrong_side = json.dumps(
        {
            "findings": [
                {
                    "category": "not_found",
                    "function": "Учёт запасов",
                    "explanation": "Не найдено.",
                    "recommendation": "Проверить.",
                    "before_evidence_ids": [AFTER.id],
                    "after_evidence_ids": [],
                }
            ]
        }
    )

    assert validate_findings(unknown, [BEFORE, AFTER])[0] == []
    assert validate_findings(wrong_side, [BEFORE, AFTER])[0] == []


def test_possible_duplicate_requires_two_distinct_after_units():
    row = {
        "category": "possible_duplicate",
        "function": "Осмотр резервного оборудования",
        "explanation": "Похожая работа указана в двух подразделениях.",
        "recommendation": "Уточнить границы ответственности.",
        "before_evidence_ids": [],
        "after_evidence_ids": [AFTER.id, AFTER_DUP.id],
    }
    findings, issues = validate_findings(json.dumps({"findings": [row]}), [AFTER, AFTER_DUP])
    assert not issues
    assert len(findings) == 1

    row["after_evidence_ids"] = [AFTER.id]
    findings, issues = validate_findings(json.dumps({"findings": [row]}), [AFTER, AFTER_DUP])
    assert not findings
    assert issues


def test_invalid_model_json_is_rejected():
    with pytest.raises(ModelOutputError):
        parse_json_object("{broken")


def test_missing_api_key_disables_real_provider(monkeypatch):
    from org_audit.agent import provider_from_env

    monkeypatch.delenv("OPENAI_API_KEY", raising=False)
    assert provider_from_env() is None


def test_mock_provider_invalid_response_marks_analysis_partial():
    provider = MockProvider('{"before_functions":[],"after_functions":[]}', "{broken")
    result = analyze_documents(provider, [BEFORE])

    assert result.partial
    assert result.findings == []
    assert any("JSON" in item for item in result.limitations)

