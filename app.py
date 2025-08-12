# -*- coding: utf-8 -*-
# 통역 MVP — 입력(음성) → 번역(텍스트) → (옵션) 음성
import io, wave
import streamlit as st
from audio_recorder_streamlit import audio_recorder

# ---------- GCP Clients (secrets 사용) ----------
@st.cache_resource
def gcp_speech():
    from google.cloud import speech
    return speech.SpeechClient.from_service_account_info(dict(st.secrets["gcp_service_account"]))

@st.cache_resource
def gcp_translate():
    from google.cloud import translate_v2 as translate
    return translate.Client.from_service_account_info(dict(st.secrets["gcp_service_account"]))

@st.cache_resource
def gcp_tts():
    from google.cloud import texttospeech
    return texttospeech.TextToSpeechClient.from_service_account_info(dict(st.secrets["gcp_service_account"]))

# ---------- Helpers ----------
def wav_info(wav_bytes: bytes):
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        return w.getframerate(), w.getnchannels()

def stt_recognize(wav_bytes: bytes, lang_code: str, alt_codes=None) -> str:
    from google.cloud import speech
    client = gcp_speech()
    sr, ch = wav_info(wav_bytes)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sr,
        language_code=lang_code,
        alternative_language_codes=alt_codes or [],   # 보조언어 자동감지(기본)
        enable_automatic_punctuation=True,
        audio_channel_count=ch,
        model="latest_short",                         # 짧은 발화 최적화
    )
    audio = speech.RecognitionAudio(content=wav_bytes)
    resp = client.recognize(config=config, audio=audio)
    return " ".join(r.alternatives[0].transcript.strip() for r in resp.results).strip()

def translate_text(text: str, target_iso: str) -> str:
    if not text:
        return ""
    client = gcp_translate()
    return client.translate(text, target_language=target_iso)["translatedText"]

def tts_synthesize(text: str, bcp47_lang: str) -> bytes:
    from google.cloud import texttospeech
    client = gcp_tts()
    input_text = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code=bcp47_lang,
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
    )
    audio_cfg = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
    audio = client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_cfg)
    return audio.audio_content

# ---------- UI ----------
st.set_page_config(page_title="통역 MVP", page_icon="🗣️", layout="centered")
st.markdown("<h3 style='text-align:center;margin-top:0;'>🗣️ 통역 MVP</h3>", unsafe_allow_html=True)

# 공통 표시 이름과 코드 매핑 (요청 순서)
LANGS = ["한국어", "영어", "프랑스어", "이탈리아어", "베트남어", "일본어", "중국어(간체)"]
STT_BCP = {"한국어":"ko-KR","영어":"en-US","프랑스어":"fr-FR","이탈리아어":"it-IT","베트남어":"vi-VN","일본어":"ja-JP","중국어(간체)":"zh-CN"}
TRANS_ISO = {"한국어":"ko","영어":"en","프랑스어":"fr","이탈리아어":"it","베트남어":"vi","일본어":"ja","중국어(간체)":"zh"}
TTS_BCP  = {"한국어":"ko-KR","영어":"en-US","프랑스어":"fr-FR","이탈리아어":"it-IT","베트남어":"vi-VN","일본어":"ja-JP","중국어(간체)":"zh-CN"}

# 초기값 1회만 세팅
if "src_name" not in st.session_state: st.session_state.src_name = "한국어"
if "tgt_name" not in st.session_state: st.session_state.tgt_name = "영어"

# 🔁 스왑 콜백(진짜 동작)
def _swap_langs():
    st.session_state.src_name, st.session_state.tgt_name = (
        st.session_state.tgt_name, st.session_state.src_name
    )

# ===== 상단 언어 선택 =====
st.selectbox("입력 언어", LANGS, key="src_name")

# ===== 중앙 아이콘 스왑 버튼 (진짜 Streamlit 버튼 + CSS로 동그랗게) =====
st.markdown("""
<style>
/* 스왑 아이콘 버튼을 동그랗고 작게 */
div.swap-wrap { display:flex; justify-content:center; margin: 0.4rem 0 0.1rem 0; }
button.swap-btn {
  border: 1px solid rgba(100,100,100,0.35);
  background: white;
  border-radius: 999px;
  width: 44px; height: 44px;
  font-size: 20px;
  line-height: 1;
  cursor: pointer;
}
</style>
<div class="swap-wrap">
  </div>
""", unsafe_allow_html=True)

# 실제 동작하는 버튼은 Streamlit 버튼을 가운데 컬럼에 배치
lc, cc, rc = st.columns([1,1,1])
with cc:
    st.button("🔁", key="swap_btn", on_click=_swap_langs)

# ===== 목표 언어 =====
st.selectbox("목표 언어", LANGS, key="tgt_name")

# ===== TTS 여부 =====
say_out_loud = st.toggle("번역 음성 출력", value=False)

st.divider()

# ===== 마이크: 가운데 정렬 + 캡션 간격 줄이기 =====
st.markdown("""
<style>
/* 마이크 영역 중앙정렬 + 캡션 간격 */
div.mic-wrap { display:flex; flex-direction:column; align-items:center; }
div.mic-caption { margin-top: -8px; font-size: 0.85rem; color:#666; text-align:center; }
</style>
""", unsafe_allow_html=True)

st.markdown('<div class="mic-wrap">', unsafe_allow_html=True)
audio_bytes = audio_recorder(text="", recording_color="#ff4b4b", neutral_color="#2b2b2b", icon_size="2x")
st.markdown('<div class="mic-caption">눌러서 녹음 / 다시 눌러서 정지</div>', unsafe_allow_html=True)
st.markdown('</div>', unsafe_allow_html=True)

# ===== 인식/번역/음성 =====
fallbacks = {
    "ko-KR": ["en-US", "ja-JP"],
    "en-US": ["ko-KR", "fr-FR"],
    "fr-FR": ["en-US", "it-IT"],
    "it-IT": ["en-US", "fr-FR"],
    "vi-VN": ["en-US", "ko-KR"],
    "ja-JP": ["en-US", "ko-KR"],
    "zh-CN": ["en-US", "ko-KR"],
}
src_lang = STT_BCP[st.session_state.src_name]
tgt_iso  = TRANS_ISO[st.session_state.tgt_name]
tgt_tts  = TTS_BCP[st.session_state.tgt_name]
alt_codes = fallbacks.get(src_lang, ["en-US", "ko-KR"])

if st.button("변환 실행", use_container_width=True, type="primary"):
    if not audio_bytes:
        st.warning("먼저 마이크로 녹음하세요.")
    else:
        try:
            src_text = stt_recognize(audio_bytes, src_lang, alt_codes=alt_codes)
            st.text_area("원문", src_text, height=120)

            tr_text = translate_text(src_text, tgt_iso) if src_text else ""
            st.text_area("번역", tr_text, height=140)

            if say_out_loud and tr_text:
                try:
                    audio_mp3 = tts_synthesize(tr_text, tgt_tts)
                    st.audio(audio_mp3, format="audio/mp3")
                except Exception as e:
                    st.error("TTS 오류 발생")
                    st.exception(e)
        except Exception as e:
            st.error("변환 오류 발생")
            st.exception(e)
