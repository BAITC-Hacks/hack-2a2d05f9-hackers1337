from __future__ import annotations

import hashlib
import io
import re
import textwrap
from collections import defaultdict

from .models import FileReadResult, Fragment


MAX_FILE_BYTES = 10 * 1024 * 1024
MAX_FILES_PER_SIDE = 8
MAX_TOTAL_BYTES = 40 * 1024 * 1024
MAX_FRAGMENT_CHARS = 1400
SUPPORTED_EXTENSIONS = {".txt", ".docx", ".pdf"}
UNIT_PREFIX = re.compile(
    r"^(?:(?:[А-ЯЁ][а-яё-]+\s+){0,3})?"
    r"(?:департамент|отдел|служба|управление|группа|комитет|дирекция|сектор|центр)\b",
    re.IGNORECASE,
)
LIST_PREFIX = re.compile(r"^\s*(?:\d+(?:\.\d+)*[.)]?|[-*•])\s+")


def _looks_like_unit_heading(text: str) -> bool:
    value = text.strip()
    return bool(
        len(value) <= 120
        and UNIT_PREFIX.search(value)
        and not re.search(r"[.!?;]", value)
        and len(value.split()) >= 2
    )


def _fragment_id(document_key: str, ordinal: int, text: str) -> str:
    value = f"{document_key}|{ordinal}|{text}".encode("utf-8", errors="replace")
    return "F-" + hashlib.sha256(value).hexdigest()[:14].upper()


def _split_text(text: str, side: str, filename: str, key: str, location_prefix: str, unit: str = "") -> list[Fragment]:
    """Split text while retaining the source line/page location for every piece."""
    fragments: list[Fragment] = []
    paragraph: list[str] = []
    paragraph_start = 1
    paragraph_end = 0
    line_number = 0
    current_unit = unit

    def flush() -> None:
        nonlocal paragraph, paragraph_end, current_unit
        if not paragraph:
            return
        value = "\n".join(paragraph).strip()
        paragraph = []
        end = paragraph_end
        paragraph_end = 0
        if not value:
            return
        start = paragraph_start
        if _looks_like_unit_heading(value):
            current_unit = value
        pieces = textwrap.wrap(
            value,
            width=MAX_FRAGMENT_CHARS,
            break_long_words=True,
            break_on_hyphens=False,
            replace_whitespace=False,
            drop_whitespace=True,
        ) or [value]
        for part_index, piece in enumerate(pieces, start=1):
            ordinal = len(fragments) + 1
            if location_prefix.startswith("страница "):
                location = location_prefix
            elif start == end:
                location = f"{location_prefix}, строка {start}"
            else:
                location = f"{location_prefix}, строки {start}–{end}"
            if len(pieces) > 1:
                location += f", фрагмент {part_index}/{len(pieces)}"
            fragments.append(
                Fragment(
                    id=_fragment_id(key, ordinal, piece),
                    side=side,
                    document=filename,
                    location=location,
                    text=piece,
                    unit=current_unit,
                )
            )

    for line_number, line in enumerate(text.splitlines(), start=1):
        if not line.strip():
            flush()
            paragraph_start = line_number + 1
            continue
        if paragraph and (_looks_like_unit_heading(line) or LIST_PREFIX.match(line)):
            flush()
            paragraph_start = line_number
        if not paragraph:
            paragraph_start = line_number
        paragraph.append(line)
        paragraph_end = line_number
    flush()
    return fragments


def _paragraph_number(paragraph, numbering, counters: dict[int, dict[int, int]]) -> str | None:
    """Return a real Word list number where the DOCX exposes one."""
    ppr = paragraph._p.pPr
    if ppr is None or ppr.numPr is None or ppr.numPr.numId is None:
        return None
    num_id = int(ppr.numPr.numId.val)
    ilvl = int(ppr.numPr.ilvl.val) if ppr.numPr.ilvl is not None else 0
    num = numbering.num_having_numId(num_id)
    if num is None:
        return None
    abstract = numbering.abstract_num_having_abstractNumId(int(num.abstractNumId.val))
    if abstract is None:
        return None
    levels = {int(item.ilvl): item for item in abstract.lvl_lst}
    level = levels.get(ilvl)
    if level is None or level.numFmt is None or level.lvlText is None:
        return None
    fmt = str(level.numFmt.val)
    if fmt in {"bullet", "none"}:
        return None

    values = counters.setdefault(num_id, {})
    start = int(level.start.val) if level.start is not None else 1
    values[ilvl] = values.get(ilvl, start - 1) + 1
    for deeper in list(values):
        if deeper > ilvl:
            del values[deeper]

    def format_value(number: int, number_format: str) -> str:
        if number_format in {"lowerLetter", "upperLetter"}:
            result = ""
            current = number
            while current:
                current, remainder = divmod(current - 1, 26)
                result = chr((97 if number_format == "lowerLetter" else 65) + remainder) + result
            return result or str(number)
        if number_format in {"lowerRoman", "upperRoman"}:
            pairs = ((1000, "M"), (900, "CM"), (500, "D"), (400, "CD"), (100, "C"), (90, "XC"),
                     (50, "L"), (40, "XL"), (10, "X"), (9, "IX"), (5, "V"), (4, "IV"), (1, "I"))
            n, out = number, ""
            for amount, symbol in pairs:
                count, n = divmod(n, amount)
                out += symbol * count
            return out.lower() if number_format == "lowerRoman" else out
        return str(number)

    pattern = str(level.lvlText.val)

    def substitute(match: re.Match[str]) -> str:
        referenced_level = int(match.group(1)) - 1
        number = values.get(referenced_level, 1)
        referenced = levels.get(referenced_level)
        referenced_format = str(referenced.numFmt.val) if referenced is not None and referenced.numFmt is not None else "decimal"
        return format_value(number, referenced_format)

    label = re.sub(r"%([1-9])", substitute, pattern).strip()
    return label or None


def _read_docx(data: bytes, side: str, filename: str, key: str) -> list[Fragment]:
    from docx import Document
    from docx.table import Table
    from docx.text.paragraph import Paragraph
    from docx.oxml.text.paragraph import CT_P
    from docx.oxml.table import CT_Tbl

    document = Document(io.BytesIO(data))
    numbering = document.part.numbering_part.element
    counters: dict[int, dict[int, int]] = defaultdict(dict)
    fragments: list[Fragment] = []
    paragraph_index = 0
    table_index = 0
    current_unit = ""

    for child in document.element.body.iterchildren():
        if isinstance(child, CT_P):
            paragraph = Paragraph(child, document)
            paragraph_index += 1
            value = paragraph.text.strip()
            if not value:
                continue
            manual_number = re.match(r"^\s*((?:\d+\.)+\d+\.?|\d+[.)])\s+", value)
            number = manual_number.group(1).rstrip(".)") if manual_number else _paragraph_number(paragraph, numbering, counters)
            location = f"пункт {number}" if number else f"абзац {paragraph_index}"
            style_name = paragraph.style.name if paragraph.style is not None else ""
            if _looks_like_unit_heading(value) or style_name.casefold().startswith("heading") or "заголов" in style_name.casefold():
                current_unit = value
            fragments.append(
                Fragment(
                    id=_fragment_id(key, len(fragments) + 1, value),
                    side=side,
                    document=filename,
                    location=location,
                    text=value,
                    unit=current_unit,
                )
            )
        elif isinstance(child, CT_Tbl):
            table_index += 1
            table = Table(child, document)
            for row_index, row in enumerate(table.rows, start=1):
                cells: list[str] = []
                for column_index, cell in enumerate(row.cells, start=1):
                    cell_text = " ".join(part.strip() for part in cell.text.splitlines() if part.strip())
                    if cell_text:
                        cells.append(f"столбец {column_index}: {cell_text}")
                value = " | ".join(cells).strip()
                if value:
                    fragments.append(
                        Fragment(
                            id=_fragment_id(key, len(fragments) + 1, value),
                            side=side,
                            document=filename,
                            location=f"таблица {table_index}, строка {row_index}",
                            text=value,
                            unit=current_unit,
                        )
                    )
    return fragments


def _read_pdf(data: bytes, side: str, filename: str, key: str) -> tuple[list[Fragment], list[int]]:
    from pypdf import PdfReader

    reader = PdfReader(io.BytesIO(data), strict=False)
    fragments: list[Fragment] = []
    pages_without_text: list[int] = []
    for page_number, page in enumerate(reader.pages, start=1):
        value = page.extract_text(extraction_mode="layout") or page.extract_text() or ""
        if not value.strip():
            pages_without_text.append(page_number)
            continue
        page_fragments = _split_text(value, side, filename, key, f"страница {page_number}")
        for item in page_fragments:
            fragments.append(
                Fragment(
                    id=_fragment_id(key, len(fragments) + 1, item.text),
                    side=side,
                    document=filename,
                    location=item.location,
                    text=item.text,
                    unit="",
                )
            )
    if not fragments:
        raise ValueError("В PDF не найден текстовый слой. Возможно, это скан; для него нужно распознавание текста (OCR).")
    return fragments, pages_without_text


def read_uploaded_file(filename: str, data: bytes, side: str, file_index: int = 0) -> FileReadResult:
    side = "ДО" if side.strip().upper() in {"ДО", "BEFORE"} else "ПОСЛЕ"
    extension = "." + filename.rsplit(".", 1)[-1].lower() if "." in filename else ""
    if extension not in SUPPORTED_EXTENSIONS:
        return FileReadResult(side, filename, "error", message="Формат не поддерживается. Загрузите TXT, DOCX или PDF.")
    if not data:
        return FileReadResult(side, filename, "error", message="Файл пуст.")
    if len(data) > MAX_FILE_BYTES:
        return FileReadResult(side, filename, "error", message=f"Размер превышает лимит {MAX_FILE_BYTES // (1024 * 1024)} МБ.")

    source_hash = hashlib.sha256(data).hexdigest()
    key = f"{side}|{filename}|{file_index}|{source_hash}"
    try:
        if extension == ".txt":
            decode_note = ""
            try:
                content = data.decode("utf-8-sig")
            except UnicodeDecodeError:
                try:
                    content = data.decode("cp1251")
                except UnicodeDecodeError:
                    content = data.decode("utf-8", errors="replace")
                    decode_note = "Часть байтов не удалось декодировать и заменена символом замены."
            fragments = _split_text(content, side, filename, key, "текст")
            if not fragments:
                raise ValueError("В TXT нет текста.")
            return FileReadResult(side, filename, "ok", fragments, decode_note)
        if extension == ".docx":
            fragments = _read_docx(data, side, filename, key)
            if not fragments:
                raise ValueError("В DOCX нет извлекаемого текста.")
            return FileReadResult(side, filename, "ok", fragments)
        fragments, pages_without_text = _read_pdf(data, side, filename, key)
        if pages_without_text:
            page_list = ", ".join(str(item) for item in pages_without_text)
            return FileReadResult(
                side,
                filename,
                "partial",
                fragments,
                f"Нет извлекаемого текстового слоя на страницах {page_list}; возможно, там сканы. Для них нужно OCR.",
            )
        return FileReadResult(side, filename, "ok", fragments)
    except ValueError as exc:
        return FileReadResult(side, filename, "error", message=str(exc))
    except Exception as exc:
        return FileReadResult(
            side,
            filename,
            "error",
            message=f"Не удалось прочитать файл ({type(exc).__name__}). Проверьте, что файл не повреждён.",
        )


def read_file_batch(files: list[tuple[str, bytes]], side: str) -> list[FileReadResult]:
    if len(files) > MAX_FILES_PER_SIDE:
        accepted = files[:MAX_FILES_PER_SIDE]
    else:
        accepted = files
    results = [read_uploaded_file(name, data, side, index) for index, (name, data) in enumerate(accepted)]
    if len(files) > MAX_FILES_PER_SIDE:
        results.append(
            FileReadResult(
                "ДО" if side.strip().upper() in {"ДО", "BEFORE"} else "ПОСЛЕ",
                "Остальные файлы",
                "error",
                message=f"Приняты первые {MAX_FILES_PER_SIDE} файлов; остальные не обработаны из-за ограничения количества.",
            )
        )
    total = sum(len(data) for _, data in accepted)
    if total > MAX_TOTAL_BYTES:
        return [
            FileReadResult(
                "ДО" if side.strip().upper() in {"ДО", "BEFORE"} else "ПОСЛЕ",
                "Комплект документов",
                "error",
                message=f"Общий размер комплекта превышает лимит {MAX_TOTAL_BYTES // (1024 * 1024)} МБ.",
            )
        ]
    return results

