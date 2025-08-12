import streamlit as st
from audio_recorder_streamlit import audio_recorder
from google.cloud import speech, texttospeech, translate_v2 as translate
import io

# ------------------- 페이지 설정 -------------------
st.set_page_config(page_title="통역 MVP", page_icon="🗣️", layout="centered")

# ------------------- CSS 스타일 -------------------
st.markdown("""
<style>
/* 버튼 중앙 정렬 */
div.stButton > button { display:block; margin: 0 auto; }

/* 스왑 아이콘 버튼 크기 줄이기 */
div.stButton > button {
    width: 50px;
    height: 50px;
    font-size: 20px;
    border-radius: 50%;
    padding: 0;
}

/* 오디오 녹음 아이콘 중앙 정렬 */
div[data-testid="stVerticalBlock"] .st-audio-recorder,  
div[data-testid="stVerticalBlock"] .stAudioRecorder,    
div[data-testid="stVerticalBlock"] div:has(> .stAudioRecorder) { 
  display:flex; justify-content:center; 
}

/* 마이크 캡션 */
.rec-caption { 
  margin-top: -6px; 
  text-align:center; 
  font-size: 0.85rem; 
  color:#666; 
}
</style>
""", unsafe_allow_html=True)

# ------------------- 언어 목록 -------------------
LANGS = ["한국어", "영어", "프랑스어", "이탈리아어", "베트남어", "일본어", "중국어(간체)"]

# ------------------- 세션 상태 초기화 -------------------
if "src_name" not in st.session_state: 
    st.session_state.src_name = "한국어"
if "tgt_name" not in st.session_state: 
    st.session_state.tgt_name = "영어"

# ------------------- 스왑 함수 -------------------
def _swap_langs():
    st.session_state.src_name, st.session_state.tgt_name = (
        st.session_state.tgt_name, st.session_state.src_name
    )

# ------------------- UI -------------------
st.title("🗣️ 통역 MVP")

# 입력 언어
st.selectbox("입력 언어", LANGS, key="src_name")

# 스왑 버튼 (아이콘)
st.button("🔁", key="swap_btn", on_click=_swap_langs)

# 목표 언어
st.selectbox("목표 언어", LANGS, key="tgt_name")

# 번역 음성 출력 토글
say_out_loud = st.toggle("번역 음성 출력", value=False)

st.divider()

# 마이크 녹음 (중앙)
_, mic_col, _ = st.columns([1, 2, 1])
with mic_col:
    audio_bytes = audio_recorder(
        text="",
        recording_color="#ff4b4b",
        neutral_color="#2b2b2b",
        icon_size="2x"
    )
    st.markdown("<div class='rec-caption'>눌러서 녹음 / 다시 눌러서 정지</div>", unsafe_allow_html=True)

# ------------------- Google API 클라이언트 -------------------
speech_client = speech.SpeechClient()
translate_client = translate.Client()
tts_client = texttospeech.TextToSpeechClient()

# ------------------- 언어 코드 매핑 -------------------
lang_code_map = {
    "한국어": "ko-KR",
    "영어": "en-US",
    "프랑스어": "fr-FR",
    "이탈리아어": "it-IT",
    "베트남어": "vi-VN",
    "일본어": "ja-JP",
    "중국어(간체)": "zh-CN"
}

# ------------------- 변환 버튼 -------------------
if st.button("변환 실행"):
    if audio_bytes:
        # STT 변환
        audio = speech.RecognitionAudio(content=audio_bytes)
        config = speech.RecognitionConfig(
            encoding=speech.RecognitionConfig.AudioEncoding.LINEAR16,
            sample_rate_hertz=16000,
            language_code=lang_code_map[st.session_state.src_name],
            model="short"
        )
        response = speech_client.recognize(config=config, audio=audio)
        text_input = response.results[0].alternatives[0].transcript if response.results else ""
        st.write("🎤 인식된 문장:", text_input)

        # 번역
        if text_input:
            target_code = lang_code_map[st.session_state.tgt_name].split("-")[0]
            translated_text = translate_client.translate(text_input, target_language=target_code)["translatedText"]
            st.write("🌐 번역:", translated_text)

            # 음성 출력
            if say_out_loud:
                synthesis_input = texttospeech.SynthesisInput(text=translated_text)
                voice = texttospeech.VoiceSelectionParams(
                    language_code=lang_code_map[st.session_state.tgt_name],
                    ssml_gender=texttospeech.SsmlVoiceGender.NEUTRAL
                )
                audio_config = texttospeech.AudioConfig(audio_encoding=texttospeech.AudioEncoding.MP3)
                tts_response = tts_client.synthesize_speech(
                    input=synthesis_input, voice=voice, audio_config=audio_config
                )
                st.audio(tts_response.audio_content, format="audio/mp3")
