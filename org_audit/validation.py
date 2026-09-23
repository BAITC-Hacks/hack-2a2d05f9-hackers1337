from __future__ import annotations

import json
from collections.abc import Iterable

from .models import CATEGORY_LABELS, Finding, Fragment


class ModelOutputError(ValueError):
    pass


def parse_json_object(raw: str) -> dict:
    try:
        value = json.loads(raw)
    except (TypeError, json.JSONDecodeError) as exc:
        raise ModelOutputError("Ответ модели не является корректным JSON.") from exc
    if not isinstance(value, dict):
        raise ModelOutputError("Ответ модели должен быть JSON-объектом.")
    return value


def validate_extractions(raw: str, fragments: Iterable[Fragment]) -> tuple[dict[str, list[dict]], list[str]]:
    by_id = {fragment.id: fragment for fragment in fragments}
    value = parse_json_object(raw)
    result: dict[str, list[dict]] = {"ДО": [], "ПОСЛЕ": []}
    issues: list[str] = []
    for side, key in (("ДО", "before_functions"), ("ПОСЛЕ", "after_functions")):
        rows = value.get(key)
        if not isinstance(rows, list):
            issues.append(f"Извлечение функций для комплекта {side} имеет неверный формат.")
            continue
        for row in rows:
            if not isinstance(row, dict):
                issues.append(f"Из комплекта {side} пропущена запись функции неверного формата.")
                continue
            function = row.get("function")
            ids = row.get("evidence_ids")
            if not isinstance(function, str) or not function.strip() or not isinstance(ids, list) or not ids:
                issues.append(f"В комплекте {side} пропущена функция без текста или ID доказательств.")
                continue
            if not all(isinstance(item, str) and item in by_id for item in ids):
                issues.append(f"Функция «{function[:80]}» из комплекта {side} ссылается на неизвестный ID.")
                continue
            evidence = [by_id[item] for item in dict.fromkeys(ids)]
            if any(item.side != side for item in evidence):
                issues.append(f"Функция «{function[:80]}» содержит ID из другого комплекта.")
                continue
            units = list(dict.fromkeys(item.unit for item in evidence if item.unit))
            result[side].append(
                {
                    "function": function.strip()[:500],
                    "unit": ", ".join(units),
                    "evidence_ids": [item.id for item in evidence],
                }
            )
    return result, issues


def _units(evidence: list[Fragment]) -> str:
    values = []
    for item in evidence:
        value = item.unit.strip()
        if not value:
            continue
        if value not in values:
            values.append(value)
    return ", ".join(values) if values else "Не указано в цитированном фрагменте"


def validate_findings(raw: str, fragments: Iterable[Fragment]) -> tuple[list[Finding], list[str]]:
    by_id = {fragment.id: fragment for fragment in fragments}
    value = parse_json_object(raw)
    rows = value.get("findings")
    if not isinstance(rows, list):
        raise ModelOutputError("В ответе модели нет списка findings.")
    findings: list[Finding] = []
    issues: list[str] = []

    for index, row in enumerate(rows, start=1):
        if not isinstance(row, dict):
            issues.append(f"Вывод {index} пропущен: неверный формат.")
            continue
        category = row.get("category")
        if category not in CATEGORY_LABELS:
            issues.append(f"Вывод {index} пропущен: неизвестная категория.")
            continue
        function = row.get("function")
        if not isinstance(function, str) or not function.strip():
            issues.append(f"Вывод {index} пропущен: не указана функция.")
            continue
        before_ids = row.get("before_evidence_ids", [])
        after_ids = row.get("after_evidence_ids", [])
        if not isinstance(before_ids, list) or not isinstance(after_ids, list):
            issues.append(f"Вывод {index} пропущен: ID доказательств должны быть списками.")
            continue
        all_ids = before_ids + after_ids
        if any(not isinstance(item, str) or item not in by_id for item in all_ids):
            issues.append(f"Вывод «{function[:80]}» пропущен: модель указала неизвестный ID доказательства.")
            continue
        before = [by_id[item] for item in dict.fromkeys(before_ids)]
        after = [by_id[item] for item in dict.fromkeys(after_ids)]
        if any(item.side != "ДО" for item in before) or any(item.side != "ПОСЛЕ" for item in after):
            issues.append(f"Вывод «{function[:80]}» пропущен: доказательство указано не для того комплекта.")
            continue

        valid = True
        if category in {"preserved", "changed", "transferred"}:
            valid = bool(before and after)
        elif category == "not_found":
            valid = bool(before and not after)
        elif category == "new":
            valid = bool(after and not before)
        elif category == "possible_duplicate":
            valid = len(after) >= 2 and len({item.unit.strip().casefold() for item in after if item.unit.strip()}) >= 2
        elif category == "insufficient_data":
            valid = bool(before or after)
        if not valid:
            issues.append(f"Вывод «{function[:80]}» пропущен: для категории недостаточно подходящих подтверждённых цитат.")
            continue

        explanation = row.get("explanation", "")
        recommendation = row.get("recommendation", "")
        findings.append(
            Finding(
                category=category,
                function=function.strip()[:500],
                before_unit=_units(before) if before else "Не применимо",
                after_unit=_units(after) if after else "Не найдено",
                explanation=explanation.strip()[:1600] if isinstance(explanation, str) else "",
                recommendation=recommendation.strip()[:800] if isinstance(recommendation, str) else "",
                before_evidence=before,
                after_evidence=after,
            )
        )
    return findings, issues


