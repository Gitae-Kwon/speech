# -*- coding: utf-8 -*-
# 통역 MVP — 입력(음성) → 번역(텍스트) → (옵션) 음성
import io, wave, os
import streamlit as st
from audio_recorder_streamlit import audio_recorder

# ---------------- Page & CSS ----------------
st.set_page_config(page_title="통역 MVP", page_icon="🗣️", layout="centered")
st.markdown("""
<style>
/* 제목 여백 */
h3 { margin-top: .6rem; }

/* 공통 중앙 정렬 유틸 */
.center-row { display:flex; justify-content:center; align-items:center; }

/* 🔁 스왑 아이콘 버튼(정중앙) */
.center-row .swap-btn > button{
  width:52px;height:52px;border-radius:50%;font-size:22px;padding:0;
}

/* 🎤 마이크: 보이는 건 이모지, 실제 클릭/녹음은 아래에 겹친 iframe이 처리 */
#mic-emoji-box{
  position:relative;
  width:88px;height:88px;           /* 필요시 84~96px로 미세조정 */
  margin:0 auto;
  border:2px solid #4a4a4a;border-radius:12px;
  background:rgba(255,255,255,0.05);
  display:flex;align-items:center;justify-content:center;
}
#mic-emoji-box::after{              /* 실제로 보이는 아이콘 */
  content:"🎤";
  font-size:2rem;
  line-height:1;
}
#mic-emoji-box iframe{              /* 실제 마이크 컴포넌트 */
  position:absolute; inset:0;
  opacity:0;                        /* 보이지 않게 */
  pointer-events:auto;              /* 클릭/터치 이벤트는 그대로 통과 */
}

/* 캡션 */
.rec-caption{ margin-top:-6px;text-align:center;font-size:.85rem;color:#999; }
</style>
""", unsafe_allow_html=True)
st.markdown("<h3 style='text-align:center;'>🗣️ 통역 MVP</h3>", unsafe_allow_html=True)

# ----------- 환경변수 방식 비활성(혼선 방지) ------------
os.environ.pop("GOOGLE_APPLICATION_CREDENTIALS", None)

# -------------- secrets 검증 & 공용 로더 ----------------
def _load_sa_info():
    try:
        info = dict(st.secrets["gcp_service_account"])
        required = ["type","project_id","private_key","client_email","token_uri"]
        if not all(k in info and info[k] for k in required):
            raise ValueError("secrets 누락")
        return info
    except Exception:
        st.error("❌ `.streamlit/secrets.toml`의 [gcp_service_account] 설정을 확인하세요.")
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

# -------------- 변환 헬퍼 --------------
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

# -------------- 언어/코드 테이블 --------------
LANGS = ["한국어","영어","프랑스어","이탈리아어","베트남어","일본어","중국어(간체)"]
STT_BCP = {"한국어":"ko-KR","영어":"en-US","프랑스어":"fr-FR","이탈리아어":"it-IT","베트남어":"vi-VN","일본어":"ja-JP","중국어(간체)":"zh-CN"}
TRANS_ISO = {"한국어":"ko","영어":"en","프랑스어":"fr","이탈리아어":"it","베트남어":"vi","일본어":"ja","중국어(간체)":"zh"}
TTS_BCP  = {"한국어":"ko-KR","영어":"en-US","프랑스어":"fr-FR","이탈리아어":"it-IT","베트남어":"vi-VN","일본어":"ja-JP","중국어(간체)":"zh-CN"}

# -------------- 상태 기본값 --------------
if "src_name" not in st.session_state: st.session_state.src_name = "한국어"
if "tgt_name" not in st.session_state: st.session_state.tgt_name = "영어"

# -------------- 언어 선택 + 스왑(정중앙) --------------
def _swap():
    st.session_state.src_name, st.session_state.tgt_name = st.session_state.tgt_name, st.session_state.src_name

st.selectbox("입력 언어", LANGS, key="src_name")
st.markdown('<div class="center-row"><div class="swap-btn">', unsafe_allow_html=True)
st.button("🔁", key="swap_btn", on_click=_swap)
st.markdown('</div></div>', unsafe_allow_html=True)
st.selectbox("목표 언어", LANGS, key="tgt_name")

say_out_loud = st.toggle("번역 음성 출력", value=False)

st.divider()

# -------------- 🎤 이모지 마이크(오버레이) --------------
# 1) 이모지와 테두리를 보이는 박스 만들고
st.markdown('<div id="mic-emoji-box">', unsafe_allow_html=True)
# 2) 그 안에 녹음 컴포넌트를 투명하게 겹쳐서 클릭하면 실제 녹음이 동작
audio_bytes = audio_recorder(text="", recording_color="#ff4b4b",
                             neutral_color="#2b2b2b", icon_size="2x")
st.markdown('</div>', unsafe_allow_html=True)
st.markdown('<div class="rec-caption">눌러서 녹음 / 다시 눌러서 정지</div>', unsafe_allow_html=True)

# -------------- 실행 --------------
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
