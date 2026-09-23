from __future__ import annotations

import csv
import io

from .models import CATEGORY_LABELS, AnalysisResult, FileReadResult


def _quote(text: str) -> str:
    return "\n".join("> " + line for line in text.splitlines()) or "> "


def build_markdown_report(result: AnalysisResult, files: list[FileReadResult]) -> str:
    documents = "\n".join(
        f"- {item.side}: {item.filename} — "
        f"{'обработан' if item.status == 'ok' else 'не обработан'}"
        + (f" ({len(item.fragments)} фрагм.)" if item.fragments else "")
        + (f"; {item.message}" if item.message else "")
        for item in files
    ) or "- Документы не загружены"
    lines = [
        "# Заключение по сравнению организационных документов",
        "",
        f"Статус анализа: {'частичный' if result.partial else 'по загруженным и обработанным фрагментам'}",
        "",
        "## Обработанные документы",
        "",
        documents,
        "",
        "## Сводка по категориям",
        "",
    ]
    for category, label in CATEGORY_LABELS.items():
        count = sum(finding.category == category for finding in result.findings)
        lines.append(f"- {label}: {count}")
    lines.extend(
        [
            "",
        "## Основные изменения",
        "",
        ]
    )
    if not result.findings:
        lines.append("Подтверждённых выводов не получено.")
    for index, finding in enumerate(result.findings, start=1):
        lines.extend(
            [
                f"### {index}. {CATEGORY_LABELS[finding.category]}",
                "",
                f"**Функция:** {finding.function}",
                f"**Подразделение ДО:** {finding.before_unit}",
                f"**Подразделение ПОСЛЕ:** {finding.after_unit}",
                f"**Объяснение:** {finding.explanation or 'Не указано.'}",
                f"**Что проверить:** {finding.recommendation or 'Сверить вывод с владельцем процесса.'}",
                "",
            ]
        )
        if finding.before_evidence:
            lines.extend(["**Подтверждение ДО:**", ""])
            for item in finding.before_evidence:
                lines.extend([f"- {item.document}, {item.location}, ID {item.id}", _quote(item.text), ""])
        if finding.after_evidence:
            lines.extend(["**Подтверждение ПОСЛЕ:**", ""])
            for item in finding.after_evidence:
                lines.extend([f"- {item.document}, {item.location}, ID {item.id}", _quote(item.text), ""])

    missing = [item for item in result.findings if item.category == "not_found"]
    duplicates = [item for item in result.findings if item.category == "possible_duplicate"]
    lines.extend(["## Возможные потери и дублирования", ""])
    if missing:
        lines.append("**Не найдено соответствие в загруженных документах:**")
        lines.extend([f"- {item.function} — {item.before_unit}. Это не доказывает ликвидацию функции." for item in missing])
    else:
        lines.append("- Функций категории «Не найдено в загруженных документах» нет.")
    if duplicates:
        lines.append("")
        lines.append("**Возможное дублирование:**")
        lines.extend([f"- {item.function} — {item.after_unit}." for item in duplicates])
    else:
        lines.append("- Выводов о возможном дублировании нет.")

    lines.extend(["", "## Вопросы для ручной проверки", ""])
    questions: list[str] = []
    if missing:
        questions.append("Есть ли другие действующие документы, в которых сохранена функция без найденного соответствия?")
        questions.append("Подтверждена ли владельцем процесса ликвидация, передача или перенос этой функции?")
    if duplicates:
        questions.append("Описывают ли похожие обязанности одинаковый результат или разные этапы, например исполнение и контроль?")
    if any(item.category in {"changed", "transferred"} for item in result.findings):
        questions.append("Сохранены ли прежние объём работ, условия выполнения и ответственность после изменения или передачи функции?")
    if any(item.category == "insufficient_data" for item in result.findings):
        questions.append("Каких положений, приложений или сведений о подчинённости не хватает для сопоставления?")
    if not questions:
        questions.append("Сверены ли выводы и цитаты с полными утверждёнными комплектами документов и владельцами процессов?")
    lines.extend([f"- {item}" for item in questions])

    lines.extend(["", "## Рекомендации", ""])
    recommendations = list(dict.fromkeys(item.recommendation for item in result.findings if item.recommendation))
    lines.extend([f"- {item}" for item in recommendations] or ["- Сверить все выводы с владельцами процессов и утверждёнными положениями."])
    lines.extend(["", "## Ограничения анализа", ""])
    if result.limitations:
        lines.extend([f"- {item}" for item in result.limitations])
    else:
        lines.append("- Сравнение охватывает только загруженные документы и текст, извлечённый из них.")
    lines.extend(
        [
            "- «Не найдено в загруженных документах» не означает, что функция ликвидирована.",
            "- Заключение требует проверки человеком и не заменяет решение владельца процесса или юридическую оценку.",
            "",
        ]
    )
    return "\n".join(lines)


def results_csv(result: AnalysisResult) -> bytes:
    output = io.StringIO(newline="")
    writer = csv.DictWriter(
        output,
        fieldnames=[
            "категория",
            "функция",
            "подразделение_до",
            "подразделение_после",
            "объяснение",
            "рекомендация",
            "доказательства_до",
            "доказательства_после",
        ],
    )
    writer.writeheader()
    for finding in result.findings:
        before = " | ".join(f"{item.document}, {item.location}, ID {item.id}: {item.text}" for item in finding.before_evidence)
        after = " | ".join(f"{item.document}, {item.location}, ID {item.id}: {item.text}" for item in finding.after_evidence)
        writer.writerow(
            {
                "категория": CATEGORY_LABELS[finding.category],
                "функция": finding.function,
                "подразделение_до": finding.before_unit,
                "подразделение_после": finding.after_unit,
                "объяснение": finding.explanation,
                "рекомендация": finding.recommendation,
                "доказательства_до": before,
                "доказательства_после": after,
            }
        )
    return output.getvalue().encode("utf-8-sig")

