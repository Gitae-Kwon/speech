# -*- coding: utf-8 -*-
# 통역 MVP — 입력(음성) → 번역(텍스트) → (옵션) 음성
import io, wave
import streamlit as st

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
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,  # audio_recorder_streamlit: PCM WAV
        sample_rate_hertz=sr,
        language_code=lang_code,
        alternative_language_codes=alt_codes or [],   # 간이 자동감지
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

# 공통 표시 이름과 코드 매핑
LANGS = ["한국어", "영어", "베트남어", "일본어", "중국어(간체)", "이탈리아어"]
STT_BCP = { "한국어":"ko-KR","영어":"en-US","베트남어":"vi-VN","일본어":"ja-JP","중국어(간체)":"zh-CN","이탈리아어":"it-IT" }
TRANS_ISO = {"한국어":"ko","영어":"en","베트남어":"vi","일본어":"ja","중국어(간체)":"zh","이탈리아어":"it"}
TTS_BCP  = { "한국어":"ko-KR","영어":"en-US","베트남어":"vi-VN","일본어":"ja-JP","중국어(간체)":"zh-CN","이탈리아어":"it-IT" }

# 상태 초기값
if "src_name" not in st.session_state:
    st.session_state.src_name = "한국어"
if "tgt_name" not in st.session_state:
    st.session_state.tgt_name = "영어"

# 입력/목표 + 전환
col1, colswap, col2 = st.columns([4,1,4])
with col1:
    st.session_state.src_name = st.selectbox("입력 언어", LANGS, index=LANGS.index(st.session_state.src_name))
with colswap:
    if st.button("🔄", use_container_width=True):
        st.session_state.src_name, st.session_state.tgt_name = st.session_state.tgt_name, st.session_state.src_name
with col2:
    st.session_state.tgt_name = st.selectbox("목표 언어", LANGS, index=LANGS.index(st.session_state.tgt_name))

src_lang = STT_BCP[st.session_state.src_name]   # STT용
tgt_iso  = TRANS_ISO[st.session_state.tgt_name] # 번역용
tgt_tts  = TTS_BCP[st.session_state.tgt_name]   # TTS용

# 번역 음성 출력 ON/OFF
say_out_loud = st.toggle("번역 음성 출력", value=False)

st.divider()

# 마이크 녹음 (모바일 친화)
from audio_recorder_streamlit import audio_recorder
audio_bytes = audio_recorder(
    text="눌러서 녹음 / 다시 눌러서 정지",
    recording_color="#ff4b4b",
    neutral_color="#2b2b2b",
    icon_size="2x",
)

# 간이 자동감지(보조언어) 기본 적용
fallbacks = {
    "ko-KR": ["en-US", "vi-VN"],
    "en-US": ["ko-KR", "vi-VN"],
    "vi-VN": ["ko-KR", "en-US"],
    "ja-JP": ["ko-KR", "en-US"],
    "zh-CN": ["en-US", "ko-KR"],
    "it-IT": ["en-US", "ko-KR"],
}
alt_codes = fallbacks.get(src_lang, ["en-US", "ko-KR"])

if st.button("변환 실행", use_container_width=True, type="primary"):
    if not audio_bytes:
        st.warning("먼저 마이크로 녹음하세요.")
    else:
        try:
            # 1) STT
            src_text = stt_recognize(audio_bytes, src_lang, alt_codes=alt_codes)
            st.text_area("원문", src_text, height=120)

            # 2) 번역
            tr_text = translate_text(src_text, tgt_iso) if src_text else ""
            st.text_area("번역", tr_text, height=140)

            # 3) (옵션) TTS
            if say_out_loud and tr_text:
                try:
                    audio_mp3 = tts_synthesize(tr_text, tgt_tts)
                    st.audio(audio_mp3, format="audio/mp3")
                except Exception as e:
                    st.error("TTS 출력 중 오류가 발생했습니다.")
                    st.exception(e)
        except Exception as e:
            st.error("변환 중 오류가 발생했습니다.")
            st.exception(e)
