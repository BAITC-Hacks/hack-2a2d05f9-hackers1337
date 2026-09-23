from org_audit.models import AnalysisResult, FileReadResult, Finding, Fragment
from org_audit.report import build_markdown_report, results_csv


def test_report_contains_citations_limitations_and_utf8_csv():
    before = Fragment("F-1", "ДО", "до.txt", "текст, строка 4", "Ведёт учёт SIM-карт.", "Отдел связи")
    finding = Finding(
        category="not_found",
        function="Учёт SIM-карт",
        before_unit="Отдел связи",
        after_unit="Не найдено",
        explanation="Соответствие не найдено в загруженных документах.",
        recommendation="Проверить другие действующие положения.",
        before_evidence=[before],
    )
    result = AnalysisResult([finding], True, ["ПОСЛЕ: один PDF не обработан."])
    files = [FileReadResult("ДО", "до.txt", "ok", [before])]

    report = build_markdown_report(result, files)
    csv_data = results_csv(result)

    assert "Не найдено в загруженных документах" in report
    assert "до.txt, текст, строка 4" in report
    assert "PDF не обработан" in report
    assert "Вопросы для ручной проверки" in report
    assert "Рекомендации" in report
    assert csv_data.startswith(b"\xef\xbb\xbf")
    assert "Отдел связи".encode("utf-8") in csv_data

