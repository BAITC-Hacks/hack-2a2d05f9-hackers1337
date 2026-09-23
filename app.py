from __future__ import annotations

import hashlib
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from org_audit.agent import DEFAULT_MODEL, analyze_documents, provider_from_env
from org_audit.models import CATEGORY_LABELS
from org_audit.reader import MAX_FILES_PER_SIDE, MAX_TOTAL_BYTES, read_file_batch
from org_audit.report import build_markdown_report, results_csv


load_dotenv()
st.set_page_config(
    page_title="Контур — аудит оргструктуры",
    page_icon=":material/account_tree:",
    layout="wide",
)


def _uploaded_files(uploaded) -> list[tuple[str, bytes]]:
    return [(item.name, item.getvalue()) for item in (uploaded or [])]


def _demo_files() -> tuple[list[tuple[str, bytes]], list[tuple[str, bytes]]]:
    root = Path(__file__).parent / "examples"
    return (
        [("ДО — вымышленные данные.txt", (root / "before.txt").read_bytes())],
        [("ПОСЛЕ — вымышленные данные.txt", (root / "after.txt").read_bytes())],
    )


def _fingerprint(files) -> str:
    value = "|".join(fragment.id for item in files for fragment in item.fragments)
    value += "|" + "|".join(
        f"{item.side}:{item.filename}:{item.message}"
        for item in files
        if item.status != "ok"
    )
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _render_documents(files) -> None:
    if not files:
        st.caption("В этом комплекте пока нет файлов.")
        return

    status_labels = {"ok": "прочитан", "partial": "прочитан частично", "error": "ошибка чтения"}
    for item in files:
        with st.expander(
            f"{item.filename} · {status_labels.get(item.status, item.status)}",
            expanded=item.status == "error",
        ):
            st.caption(f"Комплект {item.side} · извлечено фрагментов: {len(item.fragments)}")
            if item.status == "error":
                st.error(item.message)
                continue
            if item.message:
                st.warning(item.message)
            if item.fragments:
                preview = item.fragments[:100]
                st.dataframe(
                    [
                        {
                            "Расположение": fragment.location,
                            "Подразделение": fragment.unit or "Не указано",
                            "Текст фрагмента": fragment.text,
                        }
                        for fragment in preview
                    ],
                    hide_index=True,
                    height=min(420, 140 + 42 * len(preview)),
                )
                if len(item.fragments) > len(preview):
                    st.caption(f"Показаны первые {len(preview)} фрагментов из {len(item.fragments)}.")


def _citations(fragments, heading: str) -> None:
    if not fragments:
        return
    st.markdown(f"**{heading}**")
    for item in fragments:
        with st.container(border=True):
            st.caption(f"{item.document} · {item.location} · ID {item.id}")
            st.text(item.text)


def _render_error(exc: Exception) -> None:
    message = f"Не удалось завершить анализ ({type(exc).__name__})."
    api_message = getattr(exc, "message", None)
    if isinstance(api_message, str) and api_message.strip():
        message += f" Ответ API: {api_message.strip()[:500]}"
    error_code = getattr(exc, "code", None)
    if error_code:
        message += f" Код: {error_code}."
    error_param = getattr(exc, "param", None)
    if error_param:
        message += f" Параметр: {error_param}."
    request_id = getattr(exc, "request_id", None)
    if request_id:
        message += f" ID запроса: {request_id}."
    st.error(message)


api_key = os.getenv("OPENAI_API_KEY", "").strip()
selected_model = os.getenv("OPENAI_MODEL", "").strip() or DEFAULT_MODEL

with st.sidebar:
    st.markdown("## :material/account_tree: Контур")
    st.caption("Аудит изменений в организационных документах")
    st.markdown("#### Подключение ИИ")
    st.badge(
        "Ключ задан" if api_key else "Ключ не настроен",
        icon=":material/key:",
        color="green" if api_key else "orange",
    )
    st.caption(f"Модель: `{selected_model}`")
    st.markdown("#### Как пользоваться")
    st.markdown(
        "1. Загрузи документы **до** и **после**.\n"
        "2. Проверь распознанные фрагменты.\n"
        "3. Подтверди отправку текста и запусти сравнение.\n"
        "4. Сверь каждое заключение с цитатами."
    )
    with st.expander("Форматы и ограничения"):
        st.write("Поддерживаются TXT, DOCX и PDF с текстовым слоем.")
        st.write(f"До {MAX_FILES_PER_SIDE} файлов и {MAX_TOTAL_BYTES // (1024 * 1024)} МБ на комплект.")
        st.write("Сканы PDF требуют OCR. Документы отправляются в OpenAI API только после подтверждения.")


st.caption("РАБОЧЕЕ ПРОСТРАНСТВО  /  ДОКУМЕНТАЛЬНЫЙ АУДИТ")
st.title("Контур", icon=":material/account_tree:")
st.subheader("Сравнение функций до и после реорганизации")
st.write(
    "Найди сохранённые, изменённые и переданные обязанности — и проверь каждый вывод "
    "по точной цитате из исходного документа."
)

step_columns = st.columns(3)
for column, number, title, description in zip(
    step_columns,
    ("01", "02", "03"),
    ("Загрузка", "Проверка", "Сравнение"),
    (
        "Добавь комплекты документов до и после.",
        "Убедись, что нужный текст извлечён.",
        "Изучи выводы вместе с подтверждениями.",
    ),
):
    with column.container(border=True):
        st.caption(f"ШАГ {number}")
        st.markdown(f"#### {title}")
        st.caption(description)

st.header("1. Добавьте комплекты", icon=":material/folder_open:")
with st.container(border=True):
    before_col, after_col = st.columns(2)
    with before_col:
        st.markdown("#### :material/history: До изменений")
        st.caption("Утверждённые положения и описания текущих функций")
        before_uploads = st.file_uploader(
            "Файлы до реорганизации",
            type=["txt", "docx", "pdf"],
            accept_multiple_files=True,
            key="before_uploads",
            help="Можно выбрать несколько документов.",
        )
    with after_col:
        st.markdown("#### :material/auto_awesome: После изменений")
        st.caption("Новая редакция документов или целевая структура")
        after_uploads = st.file_uploader(
            "Файлы после реорганизации",
            type=["txt", "docx", "pdf"],
            accept_multiple_files=True,
            key="after_uploads",
            help="Можно выбрать несколько документов.",
        )

use_demo = st.checkbox(
    "Добавить вымышленные демонстрационные документы",
    help="Удобно для первого знакомства. Примерные файлы добавятся к выбранным документам.",
)

before_files = _uploaded_files(before_uploads)
after_files = _uploaded_files(after_uploads)
if use_demo:
    demo_before, demo_after = _demo_files()
    before_files += demo_before
    after_files += demo_after

read_files = read_file_batch(before_files, "ДО") + read_file_batch(after_files, "ПОСЛЕ")
before_items = [item for item in read_files if item.side == "ДО"]
after_items = [item for item in read_files if item.side == "ПОСЛЕ"]
before_count = sum(len(item.fragments) for item in before_items)
after_count = sum(len(item.fragments) for item in after_items)
successful_before = before_count > 0
successful_after = after_count > 0
current_fingerprint = _fingerprint(read_files)
has_uploads = bool(before_files or after_files)

st.header("2. Проверьте извлечённый текст", icon=":material/fact_check:")
if has_uploads:
    issue_count = sum(item.status != "ok" for item in read_files)
    with st.container(border=True):
        metric_cols = st.columns(4)
        metric_cols[0].metric("Файлов до", len(before_items), border=True)
        metric_cols[1].metric("Файлов после", len(after_items), border=True)
        metric_cols[2].metric("Фрагментов", before_count + after_count, border=True)
        metric_cols[3].metric("Проблемы чтения", issue_count, border=True)

    preview_side = st.segmented_control(
        "Комплект для просмотра",
        ["До реорганизации", "После реорганизации"],
        default="До реорганизации",
        key="preview_side",
    )
    _render_documents(before_items if preview_side == "До реорганизации" else after_items)
else:
    with st.container(border=True):
        st.info("Загрузи хотя бы один файл в каждый комплект. Для знакомства можно включить демонстрационные данные.")

st.header("3. Запустите сравнение", icon=":material/compare_arrows:")
privacy_confirmed = False
with st.container(border=True):
    if not api_key:
        st.warning("ИИ-анализ пока не подключён: на сайте не задан OPENAI_API_KEY.")
    elif not successful_before or not successful_after:
        st.info("Для сравнения нужен хотя бы один успешно прочитанный документ в каждом комплекте.")
    else:
        st.warning(
            "Текст извлечённых фрагментов будет отправлен в OpenAI API. "
            "Продолжай только с материалами, которые разрешено передавать внешнему сервису."
        )
        privacy_confirmed = st.checkbox(
            "Я вправе передавать эти материалы и подтверждаю отправку для анализа.",
            key=f"privacy_confirmed_{current_fingerprint}",
        )

    can_compare = bool(api_key and successful_before and successful_after and privacy_confirmed)
    compare_clicked = st.button(
        "Сравнить комплекты",
        type="primary",
        icon=":material/auto_awesome:",
        disabled=not can_compare,
    )

if compare_clicked:
    provider = provider_from_env()
    if provider is None:
        st.error("Ключ API не найден. Настрой OPENAI_API_KEY и повтори попытку.")
    else:
        limitations = [
            (
                f"{item.side}: {item.filename} обработан частично — {item.message}"
                if item.status == "partial"
                else f"{item.side}: {item.filename} не обработан — {item.message}"
            )
            for item in read_files
            if item.status != "ok"
        ]
        fragments = [fragment for item in read_files for fragment in item.fragments]
        progress = st.empty()
        try:
            with st.status("Сверяем документы и подтверждения…", expanded=True) as status:
                def on_event(message: str) -> None:
                    progress.write(message)

                analysis = analyze_documents(provider, fragments, limitations, on_event=on_event)
                st.session_state["audit_result"] = {
                    "fingerprint": current_fingerprint,
                    "result": analysis,
                    "files": read_files,
                }
                status.update(label="Сравнение завершено", state="complete", expanded=False)
        except Exception as exc:
            _render_error(exc)

saved = st.session_state.get("audit_result")
if saved and saved.get("fingerprint") == current_fingerprint:
    result = saved["result"]
    st.header("Результаты анализа", icon=":material/analytics:")
    if result.partial:
        st.warning("Проверь ограничения ниже: часть данных могла не попасть в выводы.")
    else:
        st.success("Сравнение обработанных документов завершено. Проверь выводы по цитатам.")

    counts = {key: sum(item.category == key for item in result.findings) for key in CATEGORY_LABELS}
    overview_tab, findings_tab, export_tab = st.tabs(["Обзор", "Все выводы", "Экспорт"])

    with overview_tab:
        metric_cols = st.columns(4)
        metric_cols[0].metric("Всего выводов", len(result.findings), border=True)
        metric_cols[1].metric("Сохранено", counts["preserved"], border=True)
        metric_cols[2].metric(
            "Передано или изменено",
            counts["transferred"] + counts["changed"],
            border=True,
        )
        metric_cols[3].metric(
            "Требует внимания",
            counts["not_found"] + counts["possible_duplicate"] + counts["insufficient_data"],
            border=True,
        )

        chart_categories = [key for key in CATEGORY_LABELS if counts[key] > 0]
        if chart_categories:
            st.subheader("Распределение выводов")
            st.bar_chart(
                {
                    "Категория": [CATEGORY_LABELS[key] for key in chart_categories],
                    "Количество": [counts[key] for key in chart_categories],
                },
                x="Категория",
                y="Количество",
                horizontal=True,
                sort="descending",
                height=320,
            )
        else:
            st.info("Пока нет подтверждённых выводов для диаграммы.")

        st.info(
            "«Не найдено в загруженных документах» не доказывает, что функция ликвидирована. "
            "Проверь полный комплект и уточни результат у владельца процесса."
        )
        if result.limitations:
            with st.expander("Ограничения и неполная обработка", expanded=result.partial):
                for item in result.limitations:
                    st.markdown(f"- {item}")
        if result.events:
            with st.expander("Этапы анализа"):
                for event in result.events:
                    st.markdown(f"- {event}")

    with findings_tab:
        filter_options = ["Все категории", *CATEGORY_LABELS.values()]
        selected = st.selectbox("Показать категорию", filter_options, key="finding_category_filter")
        visible = [
            item
            for item in result.findings
            if selected == "Все категории" or CATEGORY_LABELS[item.category] == selected
        ]
        if not visible:
            st.info("По этому фильтру выводов нет.")
        else:
            st.dataframe(
                [
                    {
                        "Категория": CATEGORY_LABELS[item.category],
                        "Функция": item.function,
                        "Подразделение ДО": item.before_unit,
                        "Подразделение ПОСЛЕ": item.after_unit,
                        "Объяснение": item.explanation,
                    }
                    for item in visible
                ],
                hide_index=True,
                height=min(520, 140 + 54 * len(visible)),
            )
            selected_finding = st.selectbox(
                "Открой вывод для проверки",
                range(len(visible)),
                format_func=lambda index: (
                    f"{index + 1}. {CATEGORY_LABELS[visible[index].category]} · "
                    f"{visible[index].function[:100]}"
                ),
                key=f"finding_detail_{selected}",
            )
            item = visible[selected_finding]
            with st.container(border=True):
                st.subheader(item.function)
                st.caption(CATEGORY_LABELS[item.category])
                st.write(item.explanation or "Объяснение не указано.")
                detail_cols = st.columns(2)
                detail_cols[0].markdown(f"**Подразделение ДО**  \n{item.before_unit}")
                detail_cols[1].markdown(f"**Подразделение ПОСЛЕ**  \n{item.after_unit}")
                st.markdown(f"**Что проверить:** {item.recommendation or 'Сверить вывод с владельцем процесса.'}")
                _citations(item.before_evidence, "Подтверждение ДО")
                _citations(item.after_evidence, "Подтверждение ПОСЛЕ")

    with export_tab:
        st.write("Скачай отчёт для обсуждения и ручной проверки. Источники и ограничения включены в заключение.")
        report = build_markdown_report(result, saved["files"])
        download_cols = st.columns(2)
        with download_cols[0].container(border=True):
            st.markdown("#### Заключение")
            st.caption("Читаемый отчёт с выводами, цитатами и ограничениями")
            st.download_button(
                "Скачать Markdown",
                data=report,
                file_name="zaklyuchenie.md",
                mime="text/markdown",
                icon=":material/description:",
            )
        with download_cols[1].container(border=True):
            st.markdown("#### Таблица")
            st.caption("Категории, объяснения и подтверждающие фрагменты")
            st.download_button(
                "Скачать CSV",
                data=results_csv(result),
                file_name="rezultaty.csv",
                mime="text/csv; charset=utf-8",
                icon=":material/table_view:",
            )
elif saved:
    st.caption("Результаты скрыты, потому что загруженные документы изменились. Запусти сравнение заново.")

st.caption(
    "Контур помогает систематизировать проверку. Каждое расхождение нужно сверить с полными "
    "утверждёнными документами и владельцем процесса."
)

