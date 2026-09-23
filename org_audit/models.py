from __future__ import annotations

from dataclasses import dataclass, field


CATEGORY_LABELS = {
    "preserved": "Функция сохранена",
    "changed": "Функция изменена",
    "transferred": "Функция передана другому подразделению",
    "new": "Новая функция",
    "not_found": "Не найдено в загруженных документах",
    "possible_duplicate": "Возможное дублирование",
    "insufficient_data": "Недостаточно данных для вывода",
}


@dataclass(frozen=True)
class Fragment:
    id: str
    side: str
    document: str
    location: str
    text: str
    unit: str = ""


@dataclass
class FileReadResult:
    side: str
    filename: str
    status: str
    fragments: list[Fragment] = field(default_factory=list)
    message: str = ""


@dataclass
class Finding:
    category: str
    function: str
    before_unit: str
    after_unit: str
    explanation: str
    recommendation: str
    before_evidence: list[Fragment] = field(default_factory=list)
    after_evidence: list[Fragment] = field(default_factory=list)


@dataclass
class AnalysisResult:
    findings: list[Finding]
    partial: bool
    limitations: list[str] = field(default_factory=list)
    events: list[str] = field(default_factory=list)

