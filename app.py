import streamlit as st
from google.cloud import speech, translate_v2 as translate, texttospeech
import tempfile
import os

# GCP 인증 키 설정 (Secrets에 GOOGLE_APPLICATION_CREDENTIALS JSON 저장)
os.environ["GOOGLE_APPLICATION_CREDENTIALS"] = "gcp_service_account.json"

# 번역 언어 옵션
LANG_OPTIONS = {
    "한국어": "ko",
    "영어": "en",
    "베트남어": "vi",
    "일본어": "ja",
    "중국어": "zh",
    "이탈리아어": "it"
}

st.set_page_config(page_title="통역 MVP", layout="centered")

# 제목
st.markdown("<h2 style='text-align:center;'>🗣️ 통역 MVP</h2>", unsafe_allow_html=True)

# 입력/목표 언어 선택 UI
col1, col2, col3 = st.columns([4, 1, 4])
with col1:
    src_lang = st.selectbox("입력 언어", list(LANG_OPTIONS.keys()), index=0)
with col2:
    if st.button("🔄"):
        src_lang, tgt_lang = tgt_lang, src_lang
with col3:
    tgt_lang = st.selectbox("목표 언어", list(LANG_OPTIONS.keys()), index=1)

# 음성 출력 여부
tts_enabled = st.toggle("번역 음성 출력", value=True)

# 음성 녹음
audio_file = st.audio_input("🎙️ 말하기 시작하세요")

if audio_file:
    with tempfile.NamedTemporaryFile(delete=False, suffix=".wav") as temp_audio:
        temp_audio.write(audio_file.read())
        temp_path = temp_audio.name

    # 1. STT
    stt_client = speech.SpeechClient()
    with open(temp_path, "rb") as f:
        audio_data = f.read()

    audio = speech.RecognitionAudio(content=audio_data)
    config = speech.RecognitionConfig(
        encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
        language_code=LANG_OPTIONS[src_lang],
        model="latest_short"
    )

    response = stt_client.recognize(config=config, audio=audio)
    recognized_text = response.results[0].alternatives[0].transcript if response.results else ""

    # 2. 번역
    translate_client = translate.Client()
    translated_text = translate_client.translate(
        recognized_text, target_language=LANG_OPTIONS[tgt_lang]
    )["translatedText"]

    # 결과 표시
    st.markdown(f"**입력문장:** {recognized_text}")
    st.markdown(f"**번역문장:** {translated_text}")

    # 3. TTS (옵션)
    if tts_enabled:
        tts_client = texttospeech.TextToSpeechClient()
        synthesis_input = texttospeech.SynthesisInput(text=translated_text)
        voice = texttospeech.VoiceSelectionParams(
            language_code=LANG_OPTIONS[tgt_lang],
            ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
        )
        audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)

        tts_response = tts_client.synthesize_speech(
            input=synthesis_input, voice=voice, audio_config=audio_config
        )

        tts_path = tempfile.NamedTemporaryFile(delete=False, suffix=".mp3").name
        with open(tts_path, "wb") as out:
            out.write(tts_response.audio_content)
        st.audio(tts_path)
