import base64
import os
from pathlib import Path
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote, urljoin, urlparse

import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI

APP_TITLE = "K-water 연구보고서 요약 & 퀴즈 챗봇"
PERSONA = "물관리 전문 K-water연구원"
LOGO_PATH = Path("assets/kwater-ai-lab-logo.svg")
ALIO_SEARCH_URL = (
    "https://www.alio.go.kr/search/searchTotal.do?word=%ED%95%9C%EA%B5%AD%EC%88%98%EC%9E%90%EC%9B%90%EA%B3%B5%EC%82%AC+%EC%97%B0%EA%B5%AC%EB%B3%B4%EA%B3%A0%EC%84%9C"
    "&apbaNm=&targetList=jeonggi%2Csusi%2CinfoCenter%2Cemployment%2Cbid%2Cnotice&attachFileYn=Y&sortType=LATEST"
)
ALIO_ORGAN_LIST_URL = "https://alio.go.kr/item/itemOrganList.do?apbaId=C0221&reportFormRootNo=B1040"


@dataclass
class SourceResult:
    url: str
    text: str
    is_fallback: bool


def clean_text(raw_text: str) -> str:
    cleaned = " ".join(raw_text.split())
    return cleaned.strip()


def fetch_url_text(url: str, timeout: int = 12) -> Optional[str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    for tag in soup(["script", "style", "noscript"]):
        tag.decompose()
    text = soup.get_text(" ")
    cleaned = clean_text(text)
    if len(cleaned) < 500:
        return None
    return cleaned


def fetch_html(url: str, timeout: int = 12) -> str:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    return response.text


@st.cache_data(show_spinner=False)
def fetch_binary(url: str, timeout: int = 20) -> tuple[bytes, str]:
    headers = {
        "User-Agent": (
            "Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 "
            "(KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"
        )
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    mimetype = response.headers.get("Content-Type", "application/pdf").split(";")[0]
    return response.content, mimetype


def extract_alio_report_links(page_url: str, html: str, max_links: int = 8) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    base_url = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    candidates = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        if any(token in href for token in ("itemDetail.do", "itemDetail", "itemDetailInfo")):
            candidates.append(urljoin(base_url, href))
        if len(candidates) >= max_links:
            break
    seen = set()
    deduped = []
    for link in candidates:
        if link not in seen:
            seen.add(link)
            deduped.append(link)
    return deduped


def extract_pdf_links(page_url: str, html: str, max_links: int = 6) -> List[str]:
    soup = BeautifulSoup(html, "lxml")
    base_url = f"{urlparse(page_url).scheme}://{urlparse(page_url).netloc}"
    candidates = []
    for anchor in soup.select("a[href]"):
        href = anchor.get("href", "")
        lower_href = href.lower()
        if ".pdf" in lower_href or "filedown" in lower_href or "download" in lower_href:
            candidates.append(urljoin(base_url, href))
        if len(candidates) >= max_links:
            break
    seen = set()
    deduped = []
    for link in candidates:
        if link not in seen:
            seen.add(link)
            deduped.append(link)
    return deduped


def looks_like_alio_listing(url: str) -> bool:
    return "searchTotal.do" in url or "itemOrganList.do" in url


def search_kwater_reports(query: str, max_results: int = 5) -> List[str]:
    search_url = f"https://duckduckgo.com/html/?q={quote(query)}"
    response = requests.get(search_url, timeout=12)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, "lxml")
    results = []
    for link in soup.select("a.result__a"):
        href = link.get("href")
        if href and href.startswith("http"):
            results.append(href)
        if len(results) >= max_results:
            break
    return results


def get_source_text(primary_url: str, fallback_query: str) -> Optional[SourceResult]:
    if looks_like_alio_listing(primary_url):
        try:
            html = fetch_html(primary_url)
            candidates = extract_alio_report_links(primary_url, html)
        except requests.RequestException:
            candidates = []
        for candidate in candidates:
            try:
                text = fetch_url_text(candidate)
            except requests.RequestException:
                continue
            if text:
                return SourceResult(url=candidate, text=text, is_fallback=False)

    try:
        text = fetch_url_text(primary_url)
        if text:
            return SourceResult(url=primary_url, text=text, is_fallback=False)
    except requests.RequestException:
        text = None

    try:
        candidates = search_kwater_reports(fallback_query)
    except requests.RequestException:
        return None

    for candidate in candidates:
        try:
            text = fetch_url_text(candidate)
        except requests.RequestException:
            continue
        if text:
            return SourceResult(url=candidate, text=text, is_fallback=True)
    return None


def set_source_state(source: SourceResult) -> None:
    st.session_state.report_text = source.text
    st.session_state.source_url = source.url
    st.session_state.pdf_links = []
    try:
        html = fetch_html(source.url)
        st.session_state.pdf_links = extract_pdf_links(source.url, html)
    except requests.RequestException:
        st.session_state.pdf_links = []


def get_openai_client(api_key: str) -> OpenAI:
    return OpenAI(api_key=api_key)


def get_secret_value(key: str) -> Optional[str]:
    try:
        return st.secrets.get(key)
    except Exception:
        return None


def build_summary_prompt(text: str, language: str, max_bullets: int) -> List[dict]:
    return [
        {
            "role": "system",
            "content": (
                f"당신은 {PERSONA}입니다. 다음 보고서를 {language}로 간결하게 요약하세요. "
                f"핵심 요점 {max_bullets}개를 불릿으로 제공하고, 마지막에 정책/현업 적용 포인트를 1줄로 덧붙이세요."
            ),
        },
        {"role": "user", "content": text},
    ]


def build_quiz_prompt(text: str, language: str, question_count: int) -> List[dict]:
    return [
        {
            "role": "system",
            "content": (
                f"당신은 {PERSONA}입니다. 다음 보고서를 바탕으로 {language}로 퀴즈를 만드세요. "
                f"퀴즈는 총 {question_count}문항이며, 각 문항은 질문과 간단한 정답/해설을 포함합니다."
            ),
        },
        {"role": "user", "content": text},
    ]


def call_openai(client: OpenAI, model: str, messages: List[dict]) -> str:
    response = client.chat.completions.create(model=model, messages=messages)
    return response.choices[0].message.content.strip()


st.set_page_config(page_title=APP_TITLE, page_icon="💧", layout="wide")

with st.sidebar:
    if LOGO_PATH.exists():
        try:
            svg_text = LOGO_PATH.read_text(encoding="utf-8")
            encoded = base64.b64encode(svg_text.encode("utf-8")).decode("utf-8")
            st.markdown(
                f'<img src="data:image/svg+xml;base64,{encoded}" style="width:100%; height:auto;" />',
                unsafe_allow_html=True,
            )
        except OSError:
            st.markdown("**K-water AI Lab**")
    else:
        st.markdown("**K-water AI Lab**")
    st.markdown("### 설정")
    api_key = st.text_input(
        "OpenAI API Key",
        type="password",
        value=get_secret_value("OPENAI_API_KEY") or os.getenv("OPENAI_API_KEY", ""),
        help="Streamlit Cloud에서는 Secrets에 저장된 키를 자동으로 불러옵니다.",
    )
    model = st.text_input("모델", value="gpt-4o-mini")
    language = st.selectbox("출력 언어", ["한국어", "영어"], index=0)
    max_bullets = st.slider("요약 불릿 개수", min_value=3, max_value=10, value=5)
    question_count = st.slider("퀴즈 문항 수", min_value=3, max_value=8, value=5)

st.title(APP_TITLE)

col_left, col_right = st.columns([2, 1])

with col_left:
    st.subheader("보고서 불러오기")
    st.markdown("공식 보고서 검색 페이지 또는 검색 결과 URL을 입력하세요.")
    quick_link_col1, quick_link_col2 = st.columns(2)
    with quick_link_col1:
        if st.button("ALIO 보고서 검색", use_container_width=True):
            st.session_state.alio_url = ALIO_ORGAN_LIST_URL
    with quick_link_col2:
        if st.button("ALIO 통합검색 예시", use_container_width=True):
            st.session_state.alio_url = ALIO_SEARCH_URL
    alio_url = st.text_input(
        "ALIO 보고서 URL",
        value=st.session_state.get("alio_url", ""),
        placeholder=ALIO_ORGAN_LIST_URL,
        key="alio_url",
    )
    fallback_query = st.text_input(
        "대체 검색 쿼리",
        value="K-water 연구보고서 생산보고서 논문 물관리",
        help="ALIO 스크래핑 실패 시 인터넷에서 추가 검색합니다.",
    )
    load_button = st.button("보고서 불러오기", type="primary")

with col_right:
    st.subheader("진행 상태")
    status_box = st.empty()
    source_box = st.empty()

if "report_text" not in st.session_state:
    st.session_state.report_text = ""
if "source_url" not in st.session_state:
    st.session_state.source_url = ""
if "summary" not in st.session_state:
    st.session_state.summary = ""
if "quiz" not in st.session_state:
    st.session_state.quiz = ""
if "messages" not in st.session_state:
    st.session_state.messages = []
if "pdf_links" not in st.session_state:
    st.session_state.pdf_links = []
if "alio_candidates" not in st.session_state:
    st.session_state.alio_candidates = []

if load_button:
    if not alio_url:
        status_box.warning("ALIO 보고서 URL을 입력하세요.")
    else:
        status_box.info("보고서를 불러오는 중입니다...")
        st.session_state.alio_candidates = []
        if looks_like_alio_listing(alio_url):
            try:
                listing_html = fetch_html(alio_url)
                st.session_state.alio_candidates = extract_alio_report_links(alio_url, listing_html)
            except requests.RequestException:
                st.session_state.alio_candidates = []
        source = get_source_text(alio_url, fallback_query)
        if not source:
            if st.session_state.alio_candidates:
                status_box.warning("보고서를 찾지 못했습니다. 아래 목록에서 보고서를 선택해 주세요.")
            else:
                status_box.error("보고서를 찾지 못했습니다. URL 또는 검색 쿼리를 확인하세요.")
        else:
            set_source_state(source)
            fallback_label = "(대체 검색 결과)" if source.is_fallback else "(ALIO 원문)"
            status_box.success(f"보고서 로딩 완료 {fallback_label}")
            source_box.markdown(f"**사용한 소스:** {source.url}")

st.divider()

st.subheader("보고서 목록")
if st.session_state.alio_candidates:
    selected_url = st.selectbox(
        "목록에서 보고서를 선택하세요.",
        st.session_state.alio_candidates,
        format_func=lambda url: url.replace("https://", ""),
    )
    if st.button("선택한 보고서 불러오기"):
        status_box.info("선택한 보고서를 불러오는 중입니다...")
        st.session_state.alio_url = selected_url
        source = get_source_text(selected_url, fallback_query)
        if not source:
            status_box.error("선택한 보고서를 불러오지 못했습니다. 다른 항목을 선택해 주세요.")
        else:
            set_source_state(source)
            fallback_label = "(대체 검색 결과)" if source.is_fallback else "(ALIO 원문)"
            status_box.success(f"보고서 로딩 완료 {fallback_label}")
            source_box.markdown(f"**사용한 소스:** {source.url}")
else:
    st.info("검색 결과 목록이 없습니다. ALIO 검색 결과 URL을 입력해 주세요.")

st.divider()

st.subheader("PDF 다운로드")
if st.session_state.pdf_links:
    st.caption("ALIO 페이지에서 PDF 링크를 발견하면 바로 다운로드할 수 있습니다.")
    for idx, link in enumerate(st.session_state.pdf_links, start=1):
        filename = Path(urlparse(link).path).name or f"report_{idx}.pdf"
        try:
            data, mimetype = fetch_binary(link)
            st.download_button(
                label=f"PDF 다운로드 {idx}",
                data=data,
                file_name=filename,
                mime=mimetype,
            )
            st.markdown(f"[원문 링크]({link})")
        except requests.RequestException:
            st.warning(f"PDF를 불러오지 못했습니다: {link}")
else:
    st.info("보고서에서 PDF 링크를 찾지 못했습니다. 다른 페이지를 시도해 주세요.")

st.divider()

st.subheader("요약 생성")
if st.button("요약 만들기"):
    if not api_key:
        st.warning("OpenAI API Key를 입력하세요.")
    elif not st.session_state.report_text:
        st.warning("먼저 보고서를 불러오세요.")
    else:
        with st.spinner("요약 생성 중..."):
            client = get_openai_client(api_key)
            prompt = build_summary_prompt(st.session_state.report_text, language, max_bullets)
            st.session_state.summary = call_openai(client, model, prompt)

if st.session_state.summary:
    st.markdown(st.session_state.summary)

st.divider()

st.subheader("퀴즈 챗봇")
if st.button("퀴즈 만들기"):
    if not api_key:
        st.warning("OpenAI API Key를 입력하세요.")
    elif not st.session_state.report_text:
        st.warning("먼저 보고서를 불러오세요.")
    else:
        with st.spinner("퀴즈 생성 중..."):
            client = get_openai_client(api_key)
            prompt = build_quiz_prompt(st.session_state.report_text, language, question_count)
            st.session_state.quiz = call_openai(client, model, prompt)
            st.session_state.messages = []

if st.session_state.quiz:
    st.markdown(st.session_state.quiz)

st.markdown("### 챗봇과 대화")
user_message = st.chat_input("질문을 입력하세요")
if user_message:
    if not api_key:
        st.warning("OpenAI API Key를 입력하세요.")
    elif not st.session_state.report_text:
        st.warning("먼저 보고서를 불러오세요.")
    else:
        st.session_state.messages.append({"role": "user", "content": user_message})
        with st.spinner("답변 작성 중..."):
            client = get_openai_client(api_key)
            system_prompt = (
                f"당신은 {PERSONA}입니다. 보고서 내용을 기반으로 질문에 답하세요. "
                "정확하고 실무적으로 답변합니다."
            )
            messages = [{"role": "system", "content": system_prompt}]
            messages.extend(st.session_state.messages)
            reply = call_openai(client, model, messages)
            st.session_state.messages.append({"role": "assistant", "content": reply})

for message in st.session_state.messages:
    with st.chat_message(message["role"]):
        st.markdown(message["content"])
