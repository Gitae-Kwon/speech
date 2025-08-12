# -*- coding: utf-8 -*-
import io, wave, os
import streamlit as st
from audio_recorder_streamlit import audio_recorder

# ---------------- Page & CSS ----------------
st.set_page_config(page_title="통역 MVP", page_icon="🗣️", layout="centered")
st.markdown("""
<style>
div.stButton > button#swap_btn { width:52px; height:52px; font-size:22px; border-radius:50%; padding:0; }

/* 변환 실행 버튼 스타일 복사 (마이크 버튼 동일) */
.stButton > button.primary-btn {
    background-color: rgb(19, 23, 32);
    color: white;
    border: none;
    padding: 0.5rem 1rem;
    font-weight: 600;
    border-radius: 0.25rem;
    cursor: pointer;
    width: 100%;
}
.stButton > button.primary-btn:hover {
    background-color: rgb(32, 37, 48);
}

/* audio_recorder 숨기기 */
iframe[title^="audio_recorder_streamlit"] {
    display:none !important;
}

.rec-caption { 
    margin-top:-8px; 
    text-align:center; 
    font-size:0.85rem; 
    color:#666; 
}

.main .block-container {
    padding-top: 2rem;
    max-width: 600px;
}
</style>
""", unsafe_allow_html=True)

st.markdown("<h3 style='text-align:center;'>🗣️ 통역 MVP</h3>", unsafe_allow_html=True)

# ----------- 환경변수 제거 ------------
os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

# -------------- secrets 검증 & 공용 로더 ----------------
def _load_sa_info():
    try:
        info = dict(st.secrets["gcp_service_account"])
        required = ["type","project_id","private_key","client_email","token_uri"]
        if not all(k in info and info[k] for k in required):
            raise ValueError
        return info
    except:
        st.error("❌ .streamlit/secrets.toml의 [gcp_service_account] 설정을 확인하세요.")
        st.stop()

SA_INFO = _load_sa_info()

@st.cache_resource
def gcp_speech():
    from google.cloud import speech
    return speech.SpeechClient.from_service_account_info(SA_INFO)

@st.cache_resource
def gcp_translate():
    from google.cloud import translate_v2 as translate
    return translate.Client.from_service_account_info(SA_INFO)

@st.cache_resource
def gcp_tts():
    from google.cloud import texttospeech
    return texttospeech.TextToSpeechClient.from_service_account_info(SA_INFO)

# 변환 헬퍼
def _wav_info(wav_bytes: bytes):
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        return w.getframerate(), w.getnchannels()

def stt_recognize(wav_bytes: bytes, lang_code: str, alt_codes=None) -> str:
    from google.cloud import speech
    client = gcp_speech()
    sr, ch = _wav_info(wav_bytes)
    cfg = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sr,
        language_code=lang_code,
        alternative_language_codes=alt_codes or [],
        enable_automatic_punctuation=True,
        audio_channel_count=ch,
        model="latest_short",
    )
    audio = speech.RecognitionAudio(content=wav_bytes)
    resp = client.recognize(config=cfg, audio=audio)
    return " ".join(r.alternatives[0].transcript.strip() for r in resp.results).strip()

def translate_text(text: str, target_iso: str) -> str:
    if not text: return ""
    client = gcp_translate()
    return client.translate(text, target_language=target_iso)["translatedText"]

def tts_synthesize(text: str, bcp47_lang: str) -> bytes:
    from google.cloud import texttospeech
    client = gcp_tts()
    s_input = texttospeech.SynthesisInput(text=text)
    voice = texttospeech.VoiceSelectionParams(
        language_code=bcp47_lang, ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
    )
    cfg = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
    return client.synthesize_speech(input=s_input, voice=voice, audio_config=cfg).audio_content

# 언어/코드
LANGS = ["한국어","영어","프랑스어","이탈리아어","베트남어","일본어","중국어(간체)"]
STT_BCP = {"한국어":"ko-KR","영어":"en-US","프랑스어":"fr-FR","이탈리아어":"it-IT","베트남어":"vi-VN","일본어":"ja-JP","중국어(간체)":"zh-CN"}
TRANS_ISO = {"한국어":"ko","영어":"en","프랑스어":"fr","이탈리아어":"it","베트남어":"vi","일본어":"ja","중국어(간체)":"zh"}
TTS_BCP  = {"한국어":"ko-KR","영어":"en-US","프랑스어":"fr-FR","이탈리아어":"it-IT","베트남어":"vi-VN","일본어":"ja-JP","중국어(간체)":"zh-CN"}

# 상태
if "src_name" not in st.session_state: st.session_state.src_name = "한국어"
if "tgt_name" not in st.session_state: st.session_state.tgt_name = "영어"

# 언어 선택 + 스왑
st.selectbox("입력 언어", LANGS, key="src_name")
def _swap():
    st.session_state.src_name, st.session_state.tgt_name = st.session_state.tgt_name, st.session_state.src_name
st.button("🔁", key="swap_btn", on_click=_swap)
st.selectbox("목표 언어", LANGS, key="tgt_name")

say_out_loud = st.toggle("번역 음성 출력", value=False)

st.divider()

# 마이크 버튼 (변환 실행과 동일 스타일)
if st.button("마이크", key="mic_btn", type="primary", use_container_width=True):
    # JS로 숨겨진 audio_recorder 클릭
    st.markdown("""
        <script>
        const iframe = parent.document.querySelector('iframe[title^="audio_recorder_streamlit"]');
        if (iframe) { iframe.contentWindow.document.querySelector('button')?.click(); }
        </script>
    """, unsafe_allow_html=True)

# 실제 audio_recorder (숨김 상태)
audio_bytes = audio_recorder(text="", recording_color="#ff4b4b",
                             neutral_color="#2b2b2b", icon_size="2x")

st.markdown("<div class='rec-caption'>눌러서 녹음 / 다시 눌러서 정지</div>", unsafe_allow_html=True)

# 실행
fallbacks = {
    "ko-KR":["en-US","ja-JP"], "en-US":["ko-KR","fr-FR"], "fr-FR":["en-US","it-IT"],
    "it-IT":["en-US","fr-FR"], "vi-VN":["en-US","ko-KR"], "ja-JP":["en-US","ko-KR"], "zh-CN":["en-US","ko-KR"],
}
src_lang = STT_BCP[st.session_state.src_name]
tgt_iso  = TRANS_ISO[st.session_state.tgt_name]
tgt_tts  = TTS_BCP[st.session_state.tgt_name]
alt_codes = fallbacks.get(src_lang, ["en-US","ko-KR"])

if st.button("변환 실행", type="primary", use_container_width=True):
    if not audio_bytes:
        st.warning("먼저 마이크로 녹음하세요.")
    else:
        try:
            src_text = stt_recognize(audio_bytes, src_lang, alt_codes)
            st.text_area("원문", src_text, height=120)
            tr_text = translate_text(src_text, tgt_iso) if src_text else ""
            st.text_area("번역", tr_text, height=140)
            if say_out_loud and tr_text:
                try:
                    mp3 = tts_synthesize(tr_text, tgt_tts)
                    st.audio(mp3, format="audio/mp3")
                except Exception as e:
                    st.error("TTS 출력 오류"); st.exception(e)
        except Exception as e:
            st.error("변환 오류"); st.exception(e)
