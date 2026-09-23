from __future__ import annotations

import hashlib
import os
from pathlib import Path

import streamlit as st
from dotenv import load_dotenv

from org_audit.agent import DEFAULT_MODEL, analyze_documents, provider_from_env
from org_audit.models import CATEGORY_LABELS
from org_audit.reader import MAX_FILE_BYTES, MAX_FILES_PER_SIDE, MAX_TOTAL_BYTES, read_file_batch
from org_audit.report import build_markdown_report, results_csv


load_dotenv()
st.set_page_config(
    page_title="Контур — аудит оргструктуры",
    page_icon=":material/account_tree:",
    layout="wide",
)

st.html(
    """
    <style>
    .block-container {
        max-width: 1360px;
        padding-top: 2.2rem;
        padding-bottom: 4rem;
    }
    [data-testid="stAppViewContainer"] {
        background-image:
            radial-gradient(ellipse at 8% 0%, rgba(183, 208, 124, .13), transparent 28rem),
            radial-gradient(ellipse at 95% 8%, rgba(93, 144, 128, .08), transparent 25rem);
    }
    .stButton > button, .stDownloadButton > button {
        min-height: 2.8rem;
        font-weight: 650;
        transition: transform .16s ease, box-shadow .16s ease;
    }
    .stButton > button:hover, .stDownloadButton > button:hover {
        transform: translateY(-1px);
        box-shadow: 0 8px 22px rgba(20, 61, 51, .12);
    }
    [data-testid="stFileUploaderDropzone"] {
        border: 1px dashed #9eafa4;
        background: linear-gradient(135deg, #fbfcf8 0%, #f3f7ef 100%);
        transition: border-color .16s ease, background .16s ease;
    }
    [data-testid="stFileUploaderDropzone"]:hover {
        border-color: #327565;
        background: #f0f6ed;
    }
    div[data-testid="stMetric"] {
        padding: 1rem 1.1rem;
        border-radius: 18px;
        background: rgba(255, 255, 255, .78);
        box-shadow: 0 6px 22px rgba(29, 48, 40, .035);
    }
    .contour-hero {
        position: relative;
        isolation: isolate;
        display: grid;
        grid-template-columns: minmax(0, 1.25fr) minmax(290px, .75fr);
        gap: 2rem;
        align-items: center;
        overflow: hidden;
        min-height: 330px;
        padding: clamp(1.6rem, 4vw, 3.4rem);
        border: 1px solid rgba(255, 255, 255, .13);
        border-radius: 30px;
        color: #f3f6ed;
        background:
            radial-gradient(ellipse at 83% 50%, rgba(103, 159, 127, .29), transparent 32%),
            linear-gradient(118deg, #122c27 0%, #163a32 57%, #1d4940 100%);
        box-shadow: 0 24px 70px rgba(26, 54, 44, .16);
    }
    .contour-hero::before, .contour-hero::after {
        content: "";
        position: absolute;
        z-index: -1;
        width: 380px;
        height: 380px;
        border: 1px solid rgba(228, 242, 211, .11);
        border-radius: 50%;
        pointer-events: none;
    }
    .contour-hero::before {
        top: -245px;
        right: -46px;
        box-shadow: 0 0 0 30px rgba(228, 242, 211, .025), 0 0 0 70px rgba(228, 242, 211, .025);
    }
    .contour-hero::after {
        right: 80px;
        bottom: -326px;
        width: 290px;
        height: 290px;
        border-color: rgba(228, 242, 211, .08);
    }
    .hero-copy, .hero-visual { position: relative; z-index: 1; }
    .hero-kicker, .map-caption {
        display: flex;
        align-items: center;
        gap: .6rem;
        color: #c2d6c6;
        font-size: .69rem;
        font-weight: 700;
        letter-spacing: .14em;
        text-transform: uppercase;
    }
    .hero-spark {
        width: 8px;
        height: 8px;
        border-radius: 50%;
        background: #c4e77d;
        box-shadow: 0 0 0 5px rgba(196, 231, 125, .12), 0 0 18px rgba(196, 231, 125, .65);
    }
    .hero-copy h1 {
        margin: 1.1rem 0 .9rem;
        color: #f5f7ef;
        font-size: clamp(2.25rem, 4.7vw, 4.25rem);
        font-weight: 650;
        letter-spacing: -.055em;
        line-height: 1.02;
    }
    .hero-copy h1 em {
        color: #c9e88b;
        font-style: normal;
    }
    .hero-copy p {
        max-width: 610px;
        margin: 0;
        color: #c5d3ca;
        font-size: 1rem;
        line-height: 1.65;
    }
    .hero-tags {
        display: flex;
        flex-wrap: wrap;
        align-items: center;
        gap: .7rem;
        margin-top: 1.5rem;
    }
    .hero-tags span {
        padding: .37rem .65rem;
        border: 1px solid rgba(218, 237, 215, .2);
        border-radius: 999px;
        color: #eef5e6;
        background: rgba(255, 255, 255, .055);
        font-size: .72rem;
        font-weight: 700;
        letter-spacing: .08em;
    }
    .hero-tags b { color: #c9e88b; font-size: .85rem; }
    .hero-tags small { color: #b6c9bd; font-size: .72rem; }
    .hero-visual {
        max-width: 420px;
        justify-self: end;
        width: 100%;
        padding: 1.25rem;
        border: 1px solid rgba(226, 240, 221, .18);
        border-radius: 22px;
        background: linear-gradient(145deg, rgba(242, 248, 234, .10), rgba(242, 248, 234, .035));
        box-shadow: inset 0 1px rgba(255, 255, 255, .1), 0 18px 44px rgba(4, 18, 15, .12);
        backdrop-filter: blur(12px);
    }
    .map-caption { justify-content: space-between; font-size: .62rem; }
    .map-live { color: #c9e88b; letter-spacing: .08em; }
    .map-node {
        display: flex;
        align-items: center;
        gap: .8rem;
        padding: .8rem .85rem;
        border: 1px solid rgba(226, 240, 221, .15);
        border-radius: 15px;
        background: rgba(11, 33, 28, .35);
    }
    .map-node:not(.map-node--after) { margin-top: 1.1rem; }
    .map-node--after { background: rgba(201, 232, 139, .08); border-color: rgba(201, 232, 139, .26); }
    .map-key {
        display: grid;
        flex: 0 0 35px;
        width: 35px;
        height: 35px;
        place-items: center;
        border-radius: 12px;
        color: #102b25;
        background: #d1e99c;
        font-size: .84rem;
        font-weight: 800;
    }
    .map-node--after .map-key { color: #eef5e8; background: #497c6d; }
    .map-node-text { display: grid; gap: .15rem; }
    .map-node-text small { color: #a8c1b1; font-size: .61rem; letter-spacing: .12em; }
    .map-node-text strong { color: #f1f5ed; font-size: .9rem; font-weight: 650; }
    .map-step {
        margin-left: auto;
        color: #9cb7a8;
        font-family: monospace;
        font-size: .72rem;
    }
    .map-connector {
        display: flex;
        align-items: center;
        gap: .65rem;
        height: 42px;
        margin-left: 1.9rem;
        color: #badc8a;
    }
    .map-connector svg { width: 28px; height: 42px; flex: 0 0 28px; }
    .map-connector span { color: #b2c7ba; font-size: .68rem; }
    .map-foot {
        display: flex;
        align-items: center;
        gap: .5rem;
        margin-top: 1rem;
        color: #b7cabd;
        font-size: .68rem;
    }
    .map-foot-dot { width: 6px; height: 6px; border-radius: 50%; background: #c9e88b; }
    .flow-track {
        display: grid;
        grid-template-columns: 1fr 26px 1fr 26px 1fr;
        align-items: center;
        gap: .6rem;
        margin: 1.25rem 0 2.4rem;
        padding: .85rem 1.15rem;
        border: 1px solid #e0e7de;
        border-radius: 18px;
        background: rgba(255, 255, 255, .72);
    }
    .flow-step { display: flex; align-items: center; gap: .7rem; }
    .flow-number {
        display: grid;
        flex: 0 0 31px;
        width: 31px;
        height: 31px;
        place-items: center;
        border-radius: 11px;
        color: #1a574a;
        background: #e8f0df;
        font-size: .7rem;
        font-weight: 800;
    }
    .flow-step strong { display: block; color: #22332b; font-size: .79rem; font-weight: 700; }
    .flow-step small { display: block; margin-top: .12rem; color: #78877d; font-size: .68rem; }
    .flow-arrow { color: #a7b5a9; text-align: center; }
    @media (max-width: 760px) {
        .block-container { padding-top: 1.2rem; }
        .contour-hero { grid-template-columns: 1fr; gap: 1.5rem; min-height: 0; padding: 1.5rem; border-radius: 22px; }
        .hero-visual { justify-self: stretch; max-width: none; }
        .flow-track { grid-template-columns: 1fr; gap: .45rem; }
        .flow-arrow { display: none; }
    }
    @media (prefers-reduced-motion: reduce) {
        *, *::before, *::after { scroll-behavior: auto !important; transition-duration: .01ms !important; }
    }
    </style>
    """
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


def _render_hero() -> None:
    st.html(
        """
        <section class="contour-hero" aria-label="Аудит изменений организационной структуры">
          <div class="hero-copy">
            <div class="hero-kicker"><span class="hero-spark"></span> Контур · системный аудит функций</div>
            <h1>Структура меняется.<br><em>Смысл должен сойтись.</em></h1>
            <p>Сопоставь документы до и после реорганизации. Найди, что сохранилось, изменилось или перешло между командами — с точными цитатами из источников.</p>
            <div class="hero-tags"><span>ДО</span><b>→</b><span>ПОСЛЕ</span><small>от документов к проверяемой карте функций</small></div>
          </div>
          <div class="hero-visual" aria-hidden="true">
            <div class="map-caption"><span>КАРТА ИЗМЕНЕНИЙ</span><span class="map-live">● ГОТОВА К АНАЛИЗУ</span></div>
            <div class="map-node">
              <span class="map-key">A</span>
              <span class="map-node-text"><small>КОМПЛЕКТ 01</small><strong>До изменений</strong></span>
              <span class="map-step">01</span>
            </div>
            <div class="map-connector">
              <svg viewBox="0 0 28 42" fill="none" aria-hidden="true"><path d="M14 1v37m0 0-5-5m5 5 5-5" stroke="#badc8a" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round"/><circle cx="14" cy="9" r="3" fill="#c9e88b"/></svg>
              <span>смысл · подразделение · источник</span>
            </div>
            <div class="map-node map-node--after">
              <span class="map-key">B</span>
              <span class="map-node-text"><small>КОМПЛЕКТ 02</small><strong>После изменений</strong></span>
              <span class="map-step">02</span>
            </div>
            <div class="map-foot"><span class="map-foot-dot"></span> каждый вывод можно проверить по цитате</div>
          </div>
        </section>
        <div class="flow-track" aria-label="Этапы работы">
          <div class="flow-step"><span class="flow-number">01</span><span><strong>Загрузи документы</strong><small>Комплекты до и после</small></span></div>
          <span class="flow-arrow">→</span>
          <div class="flow-step"><span class="flow-number">02</span><span><strong>Проверь извлечение</strong><small>Текст и источники</small></span></div>
          <span class="flow-arrow">→</span>
          <div class="flow-step"><span class="flow-number">03</span><span><strong>Изучи карту функций</strong><small>Выводы и доказательства</small></span></div>
        </div>
        """
    )


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
        st.write(
            f"До {MAX_FILES_PER_SIDE} файлов, {MAX_FILE_BYTES // (1024 * 1024)} МБ на файл "
            f"и {MAX_TOTAL_BYTES // (1024 * 1024)} МБ на комплект."
        )
        st.write("Сканы PDF требуют OCR. Документы отправляются в OpenAI API только после подтверждения.")


_render_hero()

st.header("Подготовь пару документов", icon=":material/folder_open:")
with st.container(border=True):
    before_col, after_col = st.columns(2)
    with before_col:
        st.markdown("#### :material/history: До изменений")
        st.caption("Утверждённые положения и описания текущих функций")
        before_uploads = st.file_uploader(
            "Файлы до реорганизации",
            type=["txt", "docx", "pdf"],
            accept_multiple_files=True,
            max_upload_size=MAX_FILE_BYTES // (1024 * 1024),
            key="before_uploads",
            help=f"До {MAX_FILES_PER_SIDE} файлов; каждый не больше {MAX_FILE_BYTES // (1024 * 1024)} МБ.",
        )
    with after_col:
        st.markdown("#### :material/auto_awesome: После изменений")
        st.caption("Новая редакция документов или целевая структура")
        after_uploads = st.file_uploader(
            "Файлы после реорганизации",
            type=["txt", "docx", "pdf"],
            accept_multiple_files=True,
            max_upload_size=MAX_FILE_BYTES // (1024 * 1024),
            key="after_uploads",
            help=f"До {MAX_FILES_PER_SIDE} файлов; каждый не больше {MAX_FILE_BYTES // (1024 * 1024)} МБ.",
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

st.header("Проверь извлечённый текст", icon=":material/fact_check:")
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

st.header("Запусти сравнение", icon=":material/compare_arrows:")
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

