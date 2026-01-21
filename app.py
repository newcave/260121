import os
from dataclasses import dataclass
from typing import List, Optional
from urllib.parse import quote

import requests
import streamlit as st
from bs4 import BeautifulSoup
from openai import OpenAI

APP_TITLE = K-water 연구보고서 요약 & 퀴즈 챗봇
PERSONA = 물관리 전문 K-water연구원
LOGO_PATH = assetskwater-ai-lab-logo.svg


@dataclass
class SourceResult
    url str
    text str
    is_fallback bool


def clean_text(raw_text str) - str
    cleaned =  .join(raw_text.split())
    return cleaned.strip()


def fetch_url_text(url str, timeout int = 12) - Optional[str]
    headers = {
        User-Agent (
            Mozilla5.0 (X11; Linux x86_64) AppleWebKit537.36 
            (KHTML, like Gecko) Chrome120.0.0.0 Safari537.36
        )
    }
    response = requests.get(url, headers=headers, timeout=timeout)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, lxml)
    for tag in soup([script, style, noscript])
        tag.decompose()
    text = soup.get_text( )
    cleaned = clean_text(text)
    if len(cleaned)  500
        return None
    return cleaned


def search_kwater_reports(query str, max_results int = 5) - List[str]
    search_url = fhttpsduckduckgo.comhtmlq={quote(query)}
    response = requests.get(search_url, timeout=12)
    response.raise_for_status()
    soup = BeautifulSoup(response.text, lxml)
    results = []
    for link in soup.select(a.result__a)
        href = link.get(href)
        if href and href.startswith(http)
            results.append(href)
        if len(results) = max_results
            break
    return results


def get_source_text(primary_url str, fallback_query str) - Optional[SourceResult]
    try
        text = fetch_url_text(primary_url)
        if text
            return SourceResult(url=primary_url, text=text, is_fallback=False)
    except requests.RequestException
        text = None

    try
        candidates = search_kwater_reports(fallback_query)
    except requests.RequestException
        return None

    for candidate in candidates
        try
            text = fetch_url_text(candidate)
        except requests.RequestException
            continue
        if text
            return SourceResult(url=candidate, text=text, is_fallback=True)
    return None


def get_openai_client(api_key str) - OpenAI
    return OpenAI(api_key=api_key)


def build_summary_prompt(text str, language str, max_bullets int) - List[dict]
    return [
        {
            role system,
            content (
                f당신은 {PERSONA}입니다. 다음 보고서를 {language}로 간결하게 요약하세요. 
                f핵심 요점 {max_bullets}개를 불릿으로 제공하고, 마지막에 정책현업 적용 포인트를 1줄로 덧붙이세요.
            ),
        },
        {role user, content text},
    ]


def build_quiz_prompt(text str, language str, question_count int) - List[dict]
    return [
        {
            role system,
            content (
                f당신은 {PERSONA}입니다. 다음 보고서를 바탕으로 {language}로 퀴즈를 만드세요. 
                f퀴즈는 총 {question_count}문항이며, 각 문항은 질문과 간단한 정답해설을 포함합니다.
            ),
        },
        {role user, content text},
    ]


def call_openai(client OpenAI, model str, messages List[dict]) - str
    response = client.chat.completions.create(model=model, messages=messages)
    return response.choices[0].message.content.strip()


st.set_page_config(page_title=APP_TITLE, page_icon=💧, layout=wide)

with st.sidebar
    st.image(LOGO_PATH, use_column_width=True)
    st.markdown(### 설정)
    api_key = st.text_input(OpenAI API Key, type=password, value=os.getenv(OPENAI_API_KEY, ))
    model = st.text_input(모델, value=gpt-4o-mini)
    language = st.selectbox(출력 언어, [한국어, 영어], index=0)
    max_bullets = st.slider(요약 불릿 개수, min_value=3, max_value=10, value=5)
    question_count = st.slider(퀴즈 문항 수, min_value=3, max_value=8, value=5)

st.title(APP_TITLE)

col_left, col_right = st.columns([2, 1])

with col_left
    st.subheader(보고서 불러오기)
    alio_url = st.text_input(ALIO 보고서 URL, placeholder=httpswww.alio.go.kr..., key=alio_url)
    fallback_query = st.text_input(
        대체 검색 쿼리,
        value=K-water 연구보고서 생산보고서 논문 물관리,
        help=ALIO 스크래핑 실패 시 인터넷에서 추가 검색합니다.,
    )
    load_button = st.button(보고서 불러오기, type=primary)

with col_right
    st.subheader(진행 상태)
    status_box = st.empty()
    source_box = st.empty()

if report_text not in st.session_state
    st.session_state.report_text = 
if source_url not in st.session_state
    st.session_state.source_url = 
if summary not in st.session_state
    st.session_state.summary = 
if quiz not in st.session_state
    st.session_state.quiz = 
if messages not in st.session_state
    st.session_state.messages = []

if load_button
    if not alio_url
        status_box.warning(ALIO 보고서 URL을 입력하세요.)
    else
        status_box.info(보고서를 불러오는 중입니다...)
        source = get_source_text(alio_url, fallback_query)
        if not source
            status_box.error(보고서를 찾지 못했습니다. URL 또는 검색 쿼리를 확인하세요.)
        else
            st.session_state.report_text = source.text
            st.session_state.source_url = source.url
            fallback_label = (대체 검색 결과) if source.is_fallback else (ALIO 원문)
            status_box.success(f보고서 로딩 완료 {fallback_label})
            source_box.markdown(f사용한 소스 {source.url})

st.divider()

st.subheader(요약 생성)
if st.button(요약 만들기)
    if not api_key
        st.warning(OpenAI API Key를 입력하세요.)
    elif not st.session_state.report_text
        st.warning(먼저 보고서를 불러오세요.)
    else
        with st.spinner(요약 생성 중...)
            client = get_openai_client(api_key)
            prompt = build_summary_prompt(st.session_state.report_text, language, max_bullets)
            st.session_state.summary = call_openai(client, model, prompt)

if st.session_state.summary
    st.markdown(st.session_state.summary)

st.divider()

st.subheader(퀴즈 챗봇)
if st.button(퀴즈 만들기)
    if not api_key
        st.warning(OpenAI API Key를 입력하세요.)
    elif not st.session_state.report_text
        st.warning(먼저 보고서를 불러오세요.)
    else
        with st.spinner(퀴즈 생성 중...)
            client = get_openai_client(api_key)
            prompt = build_quiz_prompt(st.session_state.report_text, language, question_count)
            st.session_state.quiz = call_openai(client, model, prompt)
            st.session_state.messages = []

if st.session_state.quiz
    st.markdown(st.session_state.quiz)

st.markdown(### 챗봇과 대화)
user_message = st.chat_input(질문을 입력하세요)
if user_message
    if not api_key
        st.warning(OpenAI API Key를 입력하세요.)
    elif not st.session_state.report_text
        st.warning(먼저 보고서를 불러오세요.)
    else
        st.session_state.messages.append({role user, content user_message})
        with st.spinner(답변 작성 중...)
            client = get_openai_client(api_key)
            system_prompt = (
                f당신은 {PERSONA}입니다. 보고서 내용을 기반으로 질문에 답하세요. 
                정확하고 실무적으로 답변합니다.
            )
            messages = [{role system, content system_prompt}]
            messages.extend(st.session_state.messages)
            reply = call_openai(client, model, messages)
            st.session_state.messages.append({role assistant, content reply})

for message in st.session_state.messages
    with st.chat_message(message[role])
        st.markdown(message[content])
