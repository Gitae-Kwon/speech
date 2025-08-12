# -*- coding: utf-8 -*-
# Voice → Translate → (optional) Speech
import io, wave
import streamlit as st

# ---------- GCP Clients ----------
@st.cache_resource
def get_speech_client():
    from google.cloud import speech
    return speech.SpeechClient.from_service_account_info(
        dict(st.secrets["gcp_service_account"])
    )

@st.cache_resource
def get_translate_client():
    from google.cloud import translate_v2 as translate  # v2가 간단
    return translate.Client.from_service_account_info(
        dict(st.secrets["gcp_service_account"])
    )

@st.cache_resource
def get_tts_client():
    from google.cloud import texttospeech
    return texttospeech.TextToSpeechClient.from_service_account_info(
        dict(st.secrets["gcp_service_account"])
    )

# ---------- Helpers ----------
def wav_info(wav_bytes: bytes):
    with wave.open(io.BytesIO(wav_bytes), "rb") as w:
        return w.getframerate(), w.getnchannels()

def stt_recognize(wav_bytes: bytes, lang_code: str, alt_codes=None, model="default") -> str:
    from google.cloud import speech
    client = get_speech_client()
    sr, ch = wav_info(wav_bytes)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        sample_rate_hertz=sr,
        language_code=lang_code,                       # 예: "ko-KR", "vi-VN"
        alternative_language_codes=alt_codes or [],    # 보조 언어
        enable_automatic_punctuation=True,
        audio_channel_count=ch,
        model=model,                                   # "default" | "video" | "phone_call"
    )
    audio = speech.RecognitionAudio(content=wav_bytes)
    resp = client.recognize(config=config, audio=audio)
    return " ".join(r.alternatives[0].transcript.strip() for r in resp.results).strip()

def translate_text(text: str, target_lang: str) -> str:
    # target_lang 예: "ko" "en" "vi" "ja"
    client = get_translate_client()
    return client.translate(text, target_language=target_lang)["translatedText"]

def tts_synthesize(text: str, language_code: str):
    # language_code 예: "vi-VN" "en-US" "ko-KR" …
    from google.cloud import texttospeech
    client = get_tts_client()
    input_text = texttospeech.SynthesisInput(text=text)

    # 보이스는 언어만 지정(이름 고정 X → 지역 가용성 이슈 줄임)
    voice = texttospeech.VoiceSelectionParams(
        language_code=language_code,
        ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL,
    )
    audio_config = texttospeech.AudioConfig(
        audio_encoding=texttospeech.AudioEncoding.MP3
    )
    audio = client.synthesize_speech(input=input_text, voice=voice, audio_config=audio_config)
    return audio.audio_content  # bytes (MP3)

# ---------- UI ----------
st.set_page_config(page_title="음성→번역→(음성)", page_icon="🗣️", layout="centered")
st.title("🗣️ 통역 MVP — 입력(음성) → 번역(텍스트) → 출력(음성 ON/OFF)")

st.caption("마이크로 녹음 → STT → 번역 → (선택) TTS.  *GCP Speech/Translate/TTS API 활성화 필요*")

# 언어 선택
LANG_INPUT = [
    ("한국어", "ko-KR"),
    ("영어(미국)", "en-US"),
    ("일본어", "ja-JP"),
    ("중국어(간체)", "zh-CN"),
    ("스페인어", "es-ES"),
    ("프랑스어", "fr-FR"),
    ("베트남어", "vi-VN"),
]
name2code_in = {n:c for n,c in LANG_INPUT}

LANG_TARGET = [
    ("한국어", "ko", "ko-KR"),
    ("영어", "en", "en-US"),
    ("일본어", "ja", "ja-JP"),
    ("중국어(간체)", "zh-CN", "zh-CN"),
    ("스페인어", "es", "es-ES"),
    ("프랑스어", "fr", "fr-FR"),
    ("베트남어", "vi", "vi-VN"),
]
tgt_map_iso = {n:iso for n,iso,_ in LANG_TARGET}      # 번역용
tgt_map_tts = {n:bcp for n,_,bcp in LANG_TARGET}      # TTS용

c1, c2 = st.columns(2)
with c1:
    src_name = st.selectbox("입력 음성 언어", [n for n,_ in LANG_INPUT], index=0)
    src_lang = name2code_in[src_name]
with c2:
    tgt_name = st.selectbox("번역 목표 언어", [n for n,_,_ in LANG_TARGET], index=6)  # 기본: 베트남어
    tgt_iso = tgt_map_iso[tgt_name]     # "vi"
    tgt_tts = tgt_map_tts[tgt_name]     # "vi-VN"

c3, c4 = st.columns(2)
with c3:
    autodetect = st.checkbox("보조 언어 허용(간이 자동감지)", True)
with c4:
    stt_model = st.selectbox("STT 모델", ["default", "video", "phone_call"], index=0)

alt_map = {
    "ko-KR": ["en-US", "ja-JP", "vi-VN"],
    "en-US": ["ko-KR", "ja-JP", "vi-VN"],
    "ja-JP": ["ko-KR", "en-US", "vi-VN"],
    "vi-VN": ["ko-KR", "en-US", "ja-JP"],
}
alt_codes = alt_map.get(src_lang, ["en-US", "ko-KR"]) if autodetect else []

say_out_loud = st.checkbox("번역 결과 음성으로 출력(TTS)", value=False)

st.divider()

# 녹음 위젯
from audio_recorder_streamlit import audio_recorder
st.subheader("🎤 마이크 녹음")
audio_bytes = audio_recorder(
    text="눌러서 녹음 / 다시 눌러서 정지",
    recording_color="#ff4b4b",
    neutral_color="#2b2b2b",
    icon_size="2x",
)

if audio_bytes:
    st.success("녹음 완료! 아래 버튼으로 변환하세요.")

if st.button("변환 실행 (STT → 번역 → TTS)", use_container_width=True, type="primary"):
    if not audio_bytes:
        st.warning("먼저 마이크로 녹음하세요.")
    else:
        try:
            # 1) STT
            src_text = stt_recognize(audio_bytes, src_lang, alt_codes, model=stt_model)
            if not src_text:
                st.warning("음성에서 텍스트를 인식하지 못했습니다.")
            st.text_area("원문 텍스트", src_text, height=140)

            # 2) Translate
            tr_text = translate_text(src_text, tgt_iso) if src_text else ""
            st.text_area(f"번역 텍스트 ({tgt_name})", tr_text, height=140)

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

st.divider()

# 파일 업로드 대안
st.subheader("📄 WAV 파일 업로드")
up = st.file_uploader("WAV(PCM) 파일 선택", type=["wav"])
if up and st.button("업로드 파일 변환", use_container_width=True):
    try:
        src_text = stt_recognize(up.getvalue(), src_lang, alt_codes, model=stt_model)
        st.text_area("원문 텍스트", src_text, height=140, key="up_src")
        tr_text = translate_text(src_text, tgt_iso) if src_text else ""
        st.text_area(f"번역 텍스트 ({tgt_name})", tr_text, height=140, key="up_tr")
        if say_out_loud and tr_text:
            audio_mp3 = tts_synthesize(tr_text, tgt_tts)
            st.audio(audio_mp3, format="audio/mp3")
    except Exception as e:
        st.error("변환 중 오류가 발생했습니다. (WAV/PCM인지 확인)")
        st.exception(e)
