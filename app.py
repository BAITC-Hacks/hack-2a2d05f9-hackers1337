from __future__ import annotations

import hashlib
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from org_audit.agent import analyze_documents, provider_from_env
from org_audit.models import CATEGORY_LABELS
from org_audit.reader import MAX_FILES_PER_SIDE, MAX_TOTAL_BYTES, read_file_batch
from org_audit.report import build_markdown_report, results_csv


load_dotenv()
st.set_page_config(page_title="Оргструктура — сравнение документов", page_icon="🧭", layout="wide")


def _uploaded_files(uploaded) -> list[tuple[str, bytes]]:
    return [(item.name, item.getvalue()) for item in (uploaded or [])]


def _demo_files() -> tuple[list[tuple[str, bytes]], list[tuple[str, bytes]]]:
    root = Path(__file__).parent / "examples"
    return (
        [("ДО — вымышленные данные.txt", (root / "before.txt").read_bytes())],
        [("ПОСЛЕ — вымышленные данные.txt", (root / "after.txt").read_bytes())],
    )


def _render_documents(files) -> None:
    if not files:
        st.caption("Пока нет загруженных документов.")
        return
    for item in files:
        title = f"{item.side}: {item.filename}"
        with st.expander(title, expanded=item.status == "error"):
            if item.status == "error":
                st.error(item.message)
                continue
            if item.message:
                st.warning(item.message)
            st.caption(f"Извлечено фрагментов: {len(item.fragments)}")
            for fragment in item.fragments:
                st.markdown(f"**{fragment.location}** · {fragment.id}")
                if fragment.unit:
                    st.caption(f"Подразделение / стиль: {fragment.unit}")
                st.text(fragment.text)


def _fingerprint(files) -> str:
    value = "|".join(fragment.id for item in files for fragment in item.fragments)
    value += "|" + "|".join(f"{item.side}:{item.filename}:{item.message}" for item in files if item.status != "ok")
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def _citations(fragments, heading: str) -> None:
    if not fragments:
        return
    st.markdown(f"**{heading}**")
    for item in fragments:
        st.markdown(f"- **{item.document}**, {item.location} · ID {item.id}")
        st.markdown("> " + item.text.replace("\n", "\n> "))


st.title("Сравнение организационных документов")
st.write("Сверьте функции подразделений до и после реорганизации и получите заключение с цитатами из источников.")
st.info(
    "Анализ помогает найти расхождения в загруженных материалах. "
    "«Не найдено в загруженных документах» не доказывает, что функцию ликвидировали."
)

api_key = os.getenv("OPENAI_API_KEY", "").strip()
if not api_key:
    st.warning(
        "ИИ-анализ выключен: OPENAI_API_KEY не задан. Загрузка и предпросмотр документов доступны. "
        "Создайте .env по образцу .env.example и задайте ключ; пример настройки есть в README.md."
    )

st.subheader("1. Загрузите комплекты")
st.caption(
    f"TXT, DOCX и PDF с текстовым слоем · не более {MAX_FILES_PER_SIDE} файлов на комплект · "
    f"до {MAX_TOTAL_BYTES // (1024 * 1024)} МБ на комплект."
)
before_col, after_col = st.columns(2)
with before_col:
    before_uploads = st.file_uploader(
        "До реорганизации",
        type=["txt", "docx", "pdf"],
        accept_multiple_files=True,
        key="before_uploads",
        help="Можно выбрать несколько файлов.",
    )
with after_col:
    after_uploads = st.file_uploader(
        "После реорганизации",
        type=["txt", "docx", "pdf"],
        accept_multiple_files=True,
        key="after_uploads",
        help="Можно выбрать несколько файлов.",
    )
use_demo = st.checkbox("Добавить вымышленные демонстрационные данные", value=False)

before_files = _uploaded_files(before_uploads)
after_files = _uploaded_files(after_uploads)
if use_demo:
    demo_before, demo_after = _demo_files()
    before_files += demo_before
    after_files += demo_after

read_files = read_file_batch(before_files, "ДО") + read_file_batch(after_files, "ПОСЛЕ")
before_count = sum(len(item.fragments) for item in read_files if item.side == "ДО")
after_count = sum(len(item.fragments) for item in read_files if item.side == "ПОСЛЕ")
st.subheader("2. Предпросмотр извлечённого текста")
_render_documents(read_files)

successful_before = before_count > 0
successful_after = after_count > 0
current_fingerprint = _fingerprint(read_files)

if api_key and successful_before and successful_after:
    st.subheader("3. Подтверждение передачи документов")
    st.warning(
        "Для ИИ-сравнения текст загруженных документов будет передан OpenAI API. "
        "Передайте только материалы, которыми вы вправе делиться с внешним сервисом. "
        "Файлы не сохраняются приложением на диск."
    )
    privacy_confirmed = st.checkbox(
        "Я вправе передавать эти материалы внешнему API и подтверждаю отправку для анализа.",
        key=f"privacy_confirmed_{current_fingerprint}",
    )
else:
    privacy_confirmed = False

can_compare = bool(api_key and successful_before and successful_after and privacy_confirmed)
if not successful_before or not successful_after:
    st.info("Для сравнения нужен хотя бы один успешно прочитанный документ в каждом комплекте.")

if st.button("Сравнить документы", type="primary", disabled=not can_compare):
    provider = provider_from_env()
    if provider is None:
        st.error("Ключ API не найден. Настройте OPENAI_API_KEY и повторите попытку.")
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
            with st.status("Сравнение выполняется…", expanded=True) as status:
                def on_event(message: str) -> None:
                    progress.write(message)

                analysis = analyze_documents(provider, fragments, limitations, on_event=on_event)
                st.session_state["audit_result"] = {
                    "fingerprint": current_fingerprint,
                    "result": analysis,
                    "files": read_files,
                }
                status.update(label="Анализ завершён", state="complete", expanded=False)
        except Exception as exc:
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

saved = st.session_state.get("audit_result")
if saved and saved.get("fingerprint") == current_fingerprint:
    result = saved["result"]
    st.subheader("4. Результаты")
    if result.partial:
        st.warning("Анализ частичный. Перед использованием заключения прочитайте перечисленные ограничения.")
    else:
        st.success("Анализ по обработанным загруженным документам завершён.")

    counts = {key: sum(item.category == key for item in result.findings) for key in CATEGORY_LABELS}
    metric_cols = st.columns(len(CATEGORY_LABELS))
    for column, (key, label) in zip(metric_cols, CATEGORY_LABELS.items()):
        column.metric(label, counts[key])

    filter_options = ["Все категории", *CATEGORY_LABELS.values()]
    selected = st.selectbox("Фильтр по категории", filter_options)
    visible = [
        item
        for item in result.findings
        if selected == "Все категории" or CATEGORY_LABELS[item.category] == selected
    ]
    if not visible:
        st.info("По выбранному фильтру выводов нет.")
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
            use_container_width=True,
            hide_index=True,
        )
        for item in visible:
            with st.expander(f"{CATEGORY_LABELS[item.category]} · {item.function}"):
                st.write(item.explanation or "Объяснение не указано.")
                st.markdown(f"**Подразделение ДО:** {item.before_unit}")
                st.markdown(f"**Подразделение ПОСЛЕ:** {item.after_unit}")
                st.markdown(f"**Что проверить:** {item.recommendation or 'Сверить вывод с владельцем процесса.'}")
                _citations(item.before_evidence, "Подтверждение ДО")
                _citations(item.after_evidence, "Подтверждение ПОСЛЕ")

    if result.limitations:
        with st.expander("Ограничения и неполная обработка", expanded=result.partial):
            for item in result.limitations:
                st.markdown(f"- {item}")
    if result.events:
        with st.expander("Этапы и вызовы инструментов"):
            for event in result.events:
                st.markdown(f"- {event}")

    st.subheader("5. Скачать")
    report = build_markdown_report(result, saved["files"])
    download_col1, download_col2 = st.columns(2)
    download_col1.download_button(
        "Скачать заключение в Markdown",
        data=report,
        file_name="zaklyuchenie.md",
        mime="text/markdown",
    )
    download_col2.download_button(
        "Скачать таблицу результатов в CSV",
        data=results_csv(result),
        file_name="rezultaty.csv",
        mime="text/csv; charset=utf-8",
    )
elif saved:
    st.caption("Результаты скрыты, потому что загруженные документы изменились. Запустите сравнение заново.")

