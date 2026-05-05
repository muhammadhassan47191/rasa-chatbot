import os
import requests
from flask import Flask, request, jsonify, send_file
from flask_cors import CORS
import speech_recognition as sr
from gtts import gTTS
from googletrans import Translator
from pydub import AudioSegment
import io

app = Flask(__name__)
CORS(app)  # Enable CORS for frontend communication

# Rasa Endpoint
RASA_URL = "http://localhost:5005/webhooks/rest/webhook"

# Initialize tools
recognizer = sr.Recognizer()
translator = Translator()

def get_rasa_response(text):
    """Sends text to Rasa and returns the bot's response text."""
    try:
        payload = {"sender": "user", "message": text}
        response = requests.post(RASA_URL, json=payload)
        response_data = response.json()
        if response_data:
            return response_data[0].get("text", "Sorry, I didn't understand that.")
        return "No response from bot."
    except Exception as e:
        print(f"Rasa Error: {e}")
        return "Rasa server is down."

@app.route('/process_audio', methods=['POST'])
def process_audio():
    # 1. Receive Audio File and Language Hint
    if 'audio' not in request.files:
        return jsonify({"error": "No audio file provided"}), 400
    
    audio_file = request.files['audio']
    # The frontend tells us which button was pressed ('en' or 'ur')
    # We use this to guide the Speech Recognition for better accuracy.
    lang_code = request.form.get('language', 'en') 
    
    # 2. Convert Audio to WAV (Standard format for SpeechRecognition)
    try:
        audio = AudioSegment.from_file(audio_file)
        wav_io = io.BytesIO()
        audio.export(wav_io, format="wav")
        wav_io.seek(0)  
    except Exception as e:
        return jsonify({"error": f"Audio conversion failed: {str(e)}"}), 500

    # 3. Speech to Text (STT)
    user_text = ""
    detected_lang = lang_code # Default to what user clicked
    
    with sr.AudioFile(wav_io) as source:
        audio_data = recognizer.record(source)
        try:
            # We use the button click to choose the recognition language model
            # 'ur-PK' for Urdu, 'en-US' for English
            rec_lang = 'ur-PK' if lang_code == 'ur' else 'en-US'
            user_text = recognizer.recognize_google(audio_data, language=rec_lang)
        except sr.UnknownValueError:
            return jsonify({"error": "Could not understand audio"}), 400
        except sr.RequestError:
            return jsonify({"error": "Speech service unavailable"}), 503

    print(f"User said ({lang_code}): {user_text}")

    # 4. Translation & Rasa Logic
    rasa_input_text = user_text
    
    # If Urdu, Translate to English for Rasa
    if lang_code == 'ur':
        translation = translator.translate(user_text, src='ur', dest='en')
        rasa_input_text = translation.text
        print(f"Translated to English: {rasa_input_text}")

    # 5. Get Response from Rasa
    bot_response_en = get_rasa_response(rasa_input_text)
    print(f"Rasa Response: {bot_response_en}")

    # 6. Translate back if necessary
    final_response_text = bot_response_en
    if lang_code == 'ur':
        translation = translator.translate(bot_response_en, src='en', dest='ur')
        final_response_text = translation.text
        print(f"Translated back to Urdu: {final_response_text}")

    # 7. Text to Speech (TTS)
    tts_lang = 'ur' if lang_code == 'ur' else 'en'
    tts = gTTS(text=final_response_text, lang=tts_lang, slow=False)
    
    # Save audio to a buffer
    mp3_fp = io.BytesIO()
    tts.write_to_fp(mp3_fp)
    mp3_fp.seek(0)

    # 8. Return Response
    # We return the audio file directly, but we add headers so frontend knows the text too.
    # Alternatively, we could base64 encode the audio inside a JSON response. 
    # Here, let's return JSON with Base64 audio for cleaner frontend handling.
    import base64
    audio_base64 = base64.b64encode(mp3_fp.read()).decode('utf-8')

    return jsonify({
        "user_text": user_text,
        "bot_text": final_response_text,
        "audio_base64": audio_base64
    })

if __name__ == '__main__':
    app.run(debug=True, port=5000)