# -*- coding: utf-8 -*-
import io, wave, os
import streamlit as st
from audio_recorder_streamlit import audio_recorder

# ---------- Page ----------
st.set_page_config(page_title="통역 MVP", page_icon="🗣️", layout="centered")

# ---------- CSS ----------
st.markdown("""
<style>
/* 공통 중앙 정렬 유틸 */
.center-row { display:flex; justify-content:center; align-items:center; }

/* 둥근 아이콘 버튼(스왑/마이크 공용) */
.round-btn {
  width: 58px; height: 58px;
  border-radius: 14px;
  border: 2px solid #4a4a4a;
  background: rgba(255,255,255,0.05);
  display:flex; align-items:center; justify-content:center;
  margin: 0 auto;  /* 중앙 */
  transition: border-color .15s ease, background .15s ease;
}
.round-btn:hover { border-color: #ff7a7a; background: rgba(255,122,122,0.08); }

/* 스왑 버튼 안의 Streamlit 버튼을 아이콘처럼 보이게 */
.swap-btn > button {
  width: 100%; height: 100%;
  border-radius: 12px; padding: 0; font-size: 22px;
  background: transparent; border: none;
}

/* 🎤 마이크: 보이는 건 이모지, 실제 녹음은 투명 iframe이 덮음 */
#mic-box { position: relative; }
#mic-emoji { font-size: 26px; line-height: 1; }

/* 녹음 컴포넌트(iframe)를 100% 덮어서 클릭 잡기 */
#mic-box iframe {
  position: absolute; inset: 0;
  width: 100% !important; height: 100% !important;
  opacity: 0 !important;            /* 보이지 않게 */
  pointer-events: auto !important;   /* 클릭/터치 이벤트 수신 */
  cursor: pointer;
}

/* 캡션 */
.rec-caption { margin-top: 6px; text-align: center; font-size: .85rem; color: #999; }
</style>
""", unsafe_allow_html=True)

st.markdown("<h3 style='text-align:center;margin-top:.6rem;'>🗣️ 통역 MVP</h3>", unsafe_allow_html=True)

# ---------- (생략) GCP 인증/함수들 기존 코드 그대로 ----------

# ... 여기에 당신의 GCP client 로딩/ STT/번역/TTS 함수들 그대로 둡니다 ...
# gcp_speech(), gcp_translate(), gcp_tts(), stt_recognize(), translate_text(), tts_synthesize()
# LANGS / 코드 매핑 / 세션상태 / fallbacks 등도 기존 그대로 사용

# ===== 언어 선택 + 스왑 (가운데) =====
def _swap():
    st.session_state.src_name, st.session_state.tgt_name = st.session_state.tgt_name, st.session_state.src_name

st.selectbox("입력 언어", LANGS, key="src_name")

# 스왑 버튼 중앙
st.markdown('<div class="center-row"><div class="round-btn swap-btn">', unsafe_allow_html=True)
st.button("🔁", key="swap_btn", on_click=_swap)
st.markdown('</div></div>', unsafe_allow_html=True)

st.selectbox("목표 언어", LANGS, key="tgt_name")
say_out_loud = st.toggle("번역 음성 출력", value=False)

st.divider()

# ===== 🎤 마이크 버튼 (가운데, 스왑과 동일 스타일, 호버 효과) =====
st.markdown('<div class="round-btn" id="mic-box"><span id="mic-emoji">🎤</span>', unsafe_allow_html=True)
# 투명 iframe(실제 녹음) — 반드시 mic-box 내부에 있어야 클릭이 먹습니다
audio_bytes = audio_recorder(text="", recording_color="#ff4b4b",
                             neutral_color="#2b2b2b", icon_size="2x")
st.markdown('</div>', unsafe_allow_html=True)
st.markdown('<div class="rec-caption">눌러서 녹음 / 다시 눌러서 정지</div>', unsafe_allow_html=True)

# ===== 변환 실행 버튼 이후 로직 (기존 그대로) =====
if st.button("변환 실행", type="primary", use_container_width=True):
    if not audio_bytes:
        st.warning("먼저 마이크로 녹음하세요.")
    else:
        try:
            src_lang = STT_BCP[st.session_state.src_name]
            tgt_iso  = TRANS_ISO[st.session_state.tgt_name]
            tgt_tts  = TTS_BCP[st.session_state.tgt_name]
            alt_codes = fallbacks.get(src_lang, ["en-US","ko-KR"])

            src_text = stt_recognize(audio_bytes, src_lang, alt_codes)
            st.text_area("원문", src_text, height=120)

            tr_text = translate_text(src_text, tgt_iso) if src_text else ""
            st.text_area("번역", tr_text, height=140)

            if say_out_loud and tr_text:
                audio_mp3 = tts_synthesize(tr_text, tgt_tts)
                st.audio(audio_mp3, format="audio/mp3")
        except Exception as e:
            st.error("변환 중 오류가 발생했습니다.")
            st.exception(e)
