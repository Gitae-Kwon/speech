# app.py
# -*- coding: utf-8 -*-
import os
from datetime import date
from dateutil.relativedelta import relativedelta
from urllib.parse import quote

import streamlit as st
import pandas as pd
import numpy as np
import requests
from requests.adapters import HTTPAdapter, Retry
from pytrends.request import TrendReq

# =========================
# 기본 설정
# =========================
st.set_page_config(page_title="AI Tools Tracker (Persistent)", page_icon="📊", layout="wide")

DATA_DIR = "./data"
FIG_DIR = "./figures"
os.makedirs(DATA_DIR, exist_ok=True)
os.makedirs(FIG_DIR, exist_ok=True)

# 추적 기본값
DEFAULT_REGION = "US"     # '', 'US', 'KR', ...
DEFAULT_START = date(2022, 1, 1)
DEFAULT_END = date.today()

# 6개 분야와 키워드(원하면 자유롭게 수정/추가)
CATEGORIES = {
    "1. 생산성/업무보조": ["ChatGPT", "Microsoft Copilot", "Google Gemini", "Notion AI", "Grammarly"],
    "2. 마케팅": ["Jasper", "Copy.ai", "Anyword", "HubSpot AI", "Grammarly Business"],
    "3. 디자인/영상/이미지": ["Canva", "Midjourney", "Adobe Firefly", "Runway", "DALL·E"],
    "4. 개발/코딩": ["GitHub Copilot", "ChatGPT", "Cursor", "Codeium", "Claude"],
    "5. 고객서비스/챗봇": ["Zendesk AI", "Intercom", "Salesforce Einstein", "Dialogflow", "ChatGPT"],
    "6. 운영/자동화": ["Zapier", "Make", "UiPath", "Power Automate", "n8n"]
}
# 위키 문서 매핑(영문 위키)
WIKI_PAGES_DEFAULT = {
    "ChatGPT": "ChatGPT",
    "Microsoft Copilot": "Microsoft_Copilot",
    "Google Gemini": "Google_Gemini",
    "Notion AI": "Notion_(product)",  # 통합 페이지 조회수로 대략적 인지도 추적
    "Grammarly": "Grammarly",

    "Jasper": "Jasper_(software)",    # 필요 시 정확 문서명으로 수정
    "Copy.ai": "Copy.ai",             # 없으면 빈 시리즈 처리됨
    "Anyword": "Anyword",
    "HubSpot AI": "HubSpot",
    "Grammarly Business": "Grammarly",

    "Canva": "Canva",
    "Midjourney": "Midjourney",
    "Adobe Firefly": "Adobe_Firefly",
    "Runway": "Runway_(company)",
    "DALL·E": "DALL-E",

    "GitHub Copilot": "GitHub_Copilot",
    "Cursor": "Cursor_(software)",    # 없으면 빈 처리
    "Codeium": "Codeium",
    "Claude": "Claude_(language_model)",

    "Zendesk AI": "Zendesk",
    "Intercom": "Intercom_(company)",
    "Salesforce Einstein": "Salesforce_Einstein",
    "Dialogflow": "Dialogflow",

    "Zapier": "Zapier",
    "Make": "Integromat",
    "UiPath": "UiPath",
    "Power Automate": "Power_Automate",
    "n8n": "N8n"
}

# Wikimedia 요청 세션 (User-Agent 필수)
SESSION = requests.Session()
SESSION.headers.update({
    "User-Agent": "AI-Tools-Tracker/1.0 (contact: your_email@example.com)"  # 본인 이메일/깃헙 이슈 URL 등으로 교체
})
retries = Retry(
    total=5, backoff_factor=1.5,
    status_forcelist=[403, 429, 500, 502, 503, 504],
    allowed_methods=["GET"]
)
SESSION.mount("https://", HTTPAdapter(max_retries=retries))

# =========================
# 유틸
# =========================
def ensure_month(dt: date) -> pd.Timestamp:
    return pd.Timestamp(year=dt.year, month=dt.month, day=1)

def chunks(lst, n):
    for i in range(0, len(lst), n):
        yield lst[i:i+n]

# =========================
# Google Trends
# =========================
def build_pytrends():
    return TrendReq(hl="en-US", tz=360)

@st.cache_data(ttl=60*60)
def fetch_google_trends_monthly_mean(keywords, start: date, end: date, region: str = "") -> pd.DataFrame:
    """키워드를 5개 이하 배치로 나눠 안정적으로 수집 → 월 평균으로 리샘플"""
    if not keywords:
        return pd.DataFrame()
    time_window = f"{start.isoformat()} {end.isoformat()}"
    pytrends = build_pytrends()
    frames = []
    for batch in chunks(keywords, 5):
        try:
            pytrends.build_payload(batch, timeframe=time_window, geo=region)
            df = pytrends.interest_over_time()
            if df is None or df.empty:
                continue
            if "isPartial" in df.columns:
                df = df.drop(columns=["isPartial"])
            df = df.resample("MS").mean().round(2)
            frames.append(df)
        except Exception as e:
            st.warning(f"⚠️ Google Trends 일부 실패: {batch} | {e}")
            continue
    if not frames:
        return pd.DataFrame()
    base = frames[0]
    for f in frames[1:]:
        base = base.join(f, how="outer")
    base.index.name = "month"
    # 원래 키워드 순서대로
    cols = [k for k in keywords if k in base.columns]
    return base[cols].sort_index()

# =========================
# Wikimedia Pageviews
# =========================
def wiki_month_bounds(start: date, end: date):
    start_str = pd.Timestamp(start).strftime("%Y%m01")
    end_last = (pd.Timestamp(end) + relativedelta(day=31)).strftime("%Y%m%d")
    return start_str, end_last

def wiki_url(project, access, agent, article, start_str, end_last):
    encoded_title = quote(article, safe="")
    return (f"https://wikimedia.org/api/rest_v1/metrics/pageviews/per-article/"
            f"{project}/{access}/{agent}/{encoded_title}/monthly/{start_str}/{end_last}")

def fetch_wiki_one(title: str, start: date, end: date,
                   project="en.wikipedia", access="all-access", agent="user") -> pd.Series:
    start_str, end_last = wiki_month_bounds(start, end)
    url = wiki_url(project, access, agent, title, start_str, end_last)
    try:
        r = SESSION.get(url, timeout=30)
        r.raise_for_status()
        items = r.json().get("items", [])
        if not items:
            return pd.Series(dtype="float64")
        data = {}
        for it in items:
            ts = str(it["timestamp"])
            y, m = int(ts[:4]), int(ts[4:6])
            data[pd.Timestamp(year=y, month=m, day=1)] = it["views"]
        return pd.Series(data).sort_index()
    except Exception as e:
        st.info(f"ℹ️ 위키 조회 실패: {title} | {e}")
        return pd.Series(dtype="float64")

@st.cache_data(ttl=60*60)
def fetch_wiki_map(page_map: dict, start: date, end: date) -> pd.DataFrame:
    if not page_map:
        return pd.DataFrame()
    series = []
    for key, title in page_map.items():
        s = fetch_wiki_one(title, start, end)
        s.name = key
        series.append(s)
    if not series:
        return pd.DataFrame()
    df = pd.concat(series, axis=1)
    df.index.name = "month"
    return df.sort_index()

# =========================
# 지속 추적(히스토리 누적) 로직
# =========================
def load_history(path: str) -> pd.DataFrame:
    if os.path.exists(path):
        try:
            df = pd.read_csv(path, parse_dates=["month"])
            df["month"] = pd.to_datetime(df["month"]).dt.to_period("M").dt.to_timestamp()
            df = df.set_index("month").sort_index()
            return df
        except Exception:
            return pd.DataFrame()
    return pd.DataFrame()

def save_history(path: str, df: pd.DataFrame):
    if df.empty: 
        return
    out = df.copy()
    out = out.sort_index()
    out.index.name = "month"
    out.to_csv(path, index=True)

def merge_history(history: pd.DataFrame, new_df: pd.DataFrame) -> pd.DataFrame:
    if history.empty:
        return new_df
    merged = history.combine_first(new_df).copy()
    # 새 데이터로 덮어쓰기(동월 갱신)
    for col in new_df.columns:
        merged[col].update(new_df[col])
    return merged

# =========================
# 점수 산출(정규화 + 가중합)
# =========================
def minmax_norm(s: pd.Series) -> pd.Series:
    if s.dropna().empty:
        return s
    mn, mx = s.min(), s.max()
    if mx == mn:
        return s * 0  # 전부 동일하면 0으로
    return (s - mn) / (mx - mn)

def zscore_norm(s: pd.Series) -> pd.Series:
    if s.dropna().empty:
        return s
    mu, sd = s.mean(), s.std(ddof=0)
    if sd == 0:
        return s * 0
    return (s - mu) / sd

def compute_scores(trends_df: pd.DataFrame, wiki_df: pd.DataFrame,
                   w_trends: float = 0.6, w_wiki: float = 0.4) -> pd.DataFrame:
    """
    월별/도구별 점수 산출:
    - Trends: min-max 정규화
    - Wiki: z-score → min-max로 한 번 더 스케일링(음수/스케일 차이 보정)
    - 복합 점수 = 0.6*Trends_norm + 0.4*Wiki_norm
    """
    all_tools = sorted(list(set(trends_df.columns.tolist()) | set(wiki_df.columns.tolist())))
    idx = trends_df.index.union(wiki_df.index).sort_values()
    trends_norm = pd.DataFrame(index=idx, columns=all_tools, dtype=float)
    wiki_norm = pd.DataFrame(index=idx, columns=all_tools, dtype=float)

    for t in all_tools:
        if t in trends_df.columns:
            trends_norm[t] = minmax_norm(trends_df[t])
        if t in wiki_df.columns:
            wiki_norm[t] = minmax_norm(zscore_norm(wiki_df[t]))

    score = (w_trends * trends_norm.fillna(0) + w_wiki * wiki_norm.fillna(0))
    score.index.name = "month"
    return score

# =========================
# UI - 사이드바
# =========================
st.title("📊 AI 도구 지속 추적 & 분야별 리더보드")
with st.sidebar:
    st.header("⚙️ 설정")
    region = st.selectbox("Google Trends 지역 (빈값=글로벌)", ["", "US", "KR", "BR", "JP", "GB", "DE", "FR"], index=1)
    start = st.date_input("시작일", value=DEFAULT_START, min_value=date(2019,1,1), max_value=DEFAULT_END)
    end = st.date_input("종료일", value=DEFAULT_END, min_value=DEFAULT_START, max_value=DEFAULT_END)
    use_wiki = st.checkbox("Wikipedia Pageviews 사용", value=True)
    st.markdown("---")
    st.caption("Tip: 처음엔 기본값 그대로 실행 → 이후 사이드바에서 조정")

# 추적 대상 키워드/위키 매핑 생성
ALL_TOOLS = sorted({tool for v in CATEGORIES.values() for tool in v})
WIKI_MAP = {k: WIKI_PAGES_DEFAULT.get(k, k.replace(" ", "_")) for k in ALL_TOOLS}

# =========================
# 데이터 수집 (이번 실행분)
# =========================
with st.spinner("Google Trends 수집 중..."):
    trends_now = fetch_google_trends_monthly_mean(ALL_TOOLS, start, end, region)

if use_wiki:
    with st.spinner("Wikipedia Pageviews 수집 중..."):
        wiki_now = fetch_wiki_map(WIKI_MAP, start, end)
else:
    wiki_now = pd.DataFrame()

# =========================
# 히스토리 로드 & 병합 & 저장
# =========================
hist_trends_path = os.path.join(DATA_DIR, f"history_trends_{region or 'GLOBAL'}.csv")
hist_wiki_path = os.path.join(DATA_DIR, "history_wiki.csv")
hist_score_path = os.path.join(DATA_DIR, f"history_scores_{region or 'GLOBAL'}.csv")

hist_trends = load_history(hist_trends_path)
hist_wiki = load_history(hist_wiki_path)

trends_hist_new = merge_history(hist_trends, trends_now) if not trends_now.empty else hist_trends
wiki_hist_new = merge_history(hist_wiki, wiki_now) if not wiki_now.empty else hist_wiki

# 저장
save_history(hist_trends_path, trends_hist_new)
if use_wiki:
    save_history(hist_wiki_path, wiki_hist_new)

# =========================
# 점수 계산 & 저장
# =========================
score_hist = compute_scores(trends_hist_new if not trends_hist_new.empty else pd.DataFrame(),
                            wiki_hist_new if not wiki_hist_new.empty else pd.DataFrame(),
                            w_trends=0.6, w_wiki=0.4)
save_history(hist_score_path, score_hist)

# =========================
# 화면 표시
# =========================
c1, c2 = st.columns(2)
with c1:
    st.subheader("Google Trends (월 평균, 상대지표 0–100)")
    if not trends_hist_new.empty:
        st.line_chart(trends_hist_new[ALL_TOOLS].tail(36), height=320, use_container_width=True)
        st.dataframe(trends_hist_new.tail(12), use_container_width=True)
        st.download_button("⬇️ Trends 히스토리 CSV", trends_hist_new.to_csv().encode("utf-8"),
                           file_name=os.path.basename(hist_trends_path), mime="text/csv")
    else:
        st.info("Trends 데이터가 없습니다.")

with c2:
    st.subheader("Wikipedia Pageviews (월별 절대 조회수)")
    if use_wiki and not wiki_hist_new.empty:
        st.line_chart(wiki_hist_new[ALL_TOOLS].tail(36), height=320, use_container_width=True)
        st.dataframe(wiki_hist_new.tail(12), use_container_width=True)
        st.download_button("⬇️ Wiki 히스토리 CSV", wiki_hist_new.to_csv().encode("utf-8"),
                           file_name=os.path.basename(hist_wiki_path), mime="text/csv")
    else:
        st.info("Wiki 데이터를 사용하지 않거나 비어 있습니다.")

st.markdown("---")
st.subheader("🧮 복합 점수(정규화 결합) 히스토리")
if not score_hist.empty:
    st.line_chart(score_hist[ALL_TOOLS].tail(36), height=320, use_container_width=True)
    st.dataframe(score_hist.tail(12), use_container_width=True)
    st.download_button("⬇️ Score 히스토리 CSV", score_hist.to_csv().encode("utf-8"),
                       file_name=os.path.basename(hist_score_path), mime="text/csv")
else:
    st.info("점수 히스토리가 비어 있습니다.")

# =========================
# 분야별 리더보드 (최근 월 Top N)
# =========================
st.markdown("---")
st.header("🏆 분야별 리더보드 (최근 월 기준)")
top_n = st.slider("Top N", min_value=3, max_value=10, value=5, step=1)

if not score_hist.empty:
    latest_month = score_hist.index.max()
    st.caption(f"최근 월: **{latest_month.strftime('%Y-%m')}**")
    lb_cols = st.columns(3)
    i = 0
    for cat, tools in CATEGORIES.items():
        sub = score_hist.loc[latest_month, score_hist.columns.intersection(tools)].sort_values(ascending=False)
        df_show = pd.DataFrame({"Rank": range(1, len(sub)+1), "Tool": sub.index, "Score": sub.values}).head(top_n)
        with lb_cols[i % 3]:
            st.markdown(f"**{cat}**")
            st.dataframe(df_show, use_container_width=True, hide_index=True)
        i += 1
else:
    st.info("점수 데이터가 없어 리더보드를 만들 수 없습니다.")

# =========================
# 참고/주의
# =========================
with st.expander("ℹ️ 참고 및 주의사항"):
    st.markdown("""
- **지속 추적 방식**: 실행 시점 기준으로 새 월 데이터가 있으면 history CSV에 병합/갱신합니다. (다른 달은 기존 값 유지)
- **복합 점수**: Trends(min-max) 0.6 + Wiki(zscore→min-max) 0.4의 가중합입니다. 필요 시 사이드바 옵션으로 바꾸도록 확장 가능합니다.
- **Google Trends는 상대지표**이므로, 요청 세트가 바뀌면 스케일이 달라질 수 있습니다. 동일 키워드 세트를 유지하는 것이 좋습니다.
- **Wikipedia Pageviews**는 절대 조회수라 규모감을 보완하지만, 일부 도구는 정확한 위키 문서가 없을 수 있습니다(그 경우 빈값 처리).
- **403/429** 방지를 위해 User-Agent를 **본인 연락처**가 포함된 값으로 꼭 바꾸세요.
""")
