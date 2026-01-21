# K-water 연구보고서 요약 & 퀴즈 챗봇

K-water연구원이 올린 연구보고서를 공공기관 ALIO에서 불러와 요약하고, "물관리 전문 K-water연구원" 페르소나로 퀴즈 챗봇을 제공하는 스트림릿 앱입니다. ALIO 페이지 스크래핑이 어려울 경우, 인터넷에서 K-water 연구보고서/생산보고서/논문을 추가로 검색하여 대체 요약 소스를 확보합니다.

## 구성
- `app.py`: 스트림릿 앱
- `assets/kwater-ai-lab-logo.svg`: K-water AI Lab 로고(텍스트 기반)

## 실행 방법
```bash
python -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt

export OPENAI_API_KEY=your_key_here
streamlit run app.py
```

## 사용 방법
1. ALIO 보고서 URL을 입력하고 **보고서 불러오기**를 클릭합니다.
2. 스크래핑 실패 시 자동으로 검색 쿼리를 사용해 대체 보고서를 찾습니다.
3. 요약 생성 및 퀴즈 챗봇을 활용합니다.

## 참고
- 네트워크 환경에 따라 일부 사이트는 스크래핑이 제한될 수 있습니다.
- 요약/퀴즈 생성에는 OpenAI API 키가 필요합니다.
