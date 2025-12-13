import os
import json
import tempfile
from flask import Flask, request, jsonify
from vosk import Model, KaldiRecognizer, SetLogLevel
from pydub import AudioSegment
from flask_cors import CORS
import urllib.request
import zipfile

app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})

print("=" * 50)
print("🚀 ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ")
print("=" * 50)

# ===== ЗАГРУЗКА МОДЕЛЕЙ =====

def download_vosk_model():
    """Скачиваем Vosk модель для английского"""
    model_path = "/tmp/vosk_model"
    
    if not os.path.exists(model_path):
        print("\n⏳ Скачиваю Vosk модель для английского...")
        
        model_url = "https://alphacephei.com/vosk/models/vosk-model-en-us-0.42.zip"
        zip_path = "/tmp/vosk_model.zip"
        
        try:
            urllib.request.urlretrieve(model_url, zip_path)
            print("   ✓ Загружена")
            
            print("   Распаковываю...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall("/tmp/")
            
            os.rename("/tmp/vosk-model-en-us-0.42", model_path)
            os.remove(zip_path)
            print("   ✓ Распакована")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            raise
    else:
        print("\n✅ Vosk модель уже загружена")
    
    return model_path

def init_recasepunc_model():
    """Инициализируем recasepunc для пунктуации"""
    print("\n⏳ Загружаю модель recasepunc для пунктуации...")
    try:
        from recasepunc import RecasePunc
        
        # Используем предтренированную модель для английского
        model = RecasePunc.load_from_checkpoint(
            "checkpoint/checkpoint_en_transformer.pt"
        )
        print("✅ Модель recasepunc готова\n")
        return model
    except Exception as e:
        print(f"⚠️ Ошибка загрузки recasepunc: {e}")
        print("   Буду использовать простую пунктуацию\n")
        return None

# Загружаем при старте
VOSK_MODEL_PATH = download_vosk_model()
RECASEPUNC_MODEL = init_recasepunc_model()

print("=" * 50)
print("✅ ПРИЛОЖЕНИЕ ГОТОВО К РАБОТЕ")
print("=" * 50)

# ===== ФУНКЦИИ ДЛЯ ПУНКТУАЦИИ =====

def simple_punctuate(text):
    """Простая капитализация + точка"""
    if not text or not text.strip():
        return text
    
    text = text.strip()
    text = text[0].upper() + text[1:] if len(text) > 1 else text.upper()
    
    if text[-1] not in '.!?':
        text += '.'
    
    return text

def recasepunc_punctuate(text):
    """Использует recasepunc для качественной пунктуации"""
    if not text or not text.strip():
        return text
    
    try:
        if RECASEPUNC_MODEL is None:
            return simple_punctuate(text)
        
        # recasepunc требует токены
        from recasepunc import RecasePunc
        
        # Берем текст
        camel_text = RECASEPUNC_MODEL.predict([text.lower()])
        
        return camel_text[0] if camel_text else simple_punctuate(text)
    
    except Exception as e:
        print(f"   Ошибка в recasepunc: {e}, использую fallback")
        return simple_punctuate(text)

# ===== API ENDPOINT =====

@app.route('/api', methods=['POST'])
def process_audio():
    """Распознает речь и добавляет пунктуацию"""
    try:
        if '111' not in request.files:
            return jsonify({"error": "No file provided"}), 400
        
        file = request.files['111']
        
        if file.filename == '':
            return jsonify({"error": "Empty filename"}), 400
        
        print(f"\n📥 Получен файл: {file.filename}")
        
        # ===== КОНВЕРТИРУЕМ В WAV =====
        print("🔄 Конвертирую в WAV 16kHz...")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            audio_path = tmp.name
        
        try:
            song = AudioSegment.from_file(file)
            song = song.set_channels(1).set_frame_rate(16000)
            song.export(audio_path, format="wav")
            print("   ✓ Готово")
        except Exception as e:
            print(f"   ❌ Ошибка конвертации: {str(e)}")
            return jsonify({"error": f"Audio conversion error: {str(e)}"}), 400
        
        # ===== РАСПОЗНАВАНИЕ РЕЧИ (VOSK) =====
        print("🎤 Распознаю речь...")
        
        try:
            SetLogLevel(-1)
            
            model = Model(VOSK_MODEL_PATH)
            recognizer = KaldiRecognizer(model, 16000)
            recognizer.SetWords(True)
            
            with open(audio_path, "rb") as audio_file:
                while True:
                    data = audio_file.read(4096)
                    if not data:
                        break
                    recognizer.AcceptWaveform(data)
            
            result_json = recognizer.FinalResult()
            result_data = json.loads(result_json)
            
            if "result" in result_data and result_data["result"]:
                text = " ".join([item.get("conf", "") for item in result_data["result"] if "conf" in item])
            else:
                text = result_data.get("text", "")
            
            if not text.strip():
                print("   ⚠️ Речь не распознана")
                return jsonify({"error": "No speech detected"}), 400
            
            print(f"   ✓ Распознано: {text}")
            
        except Exception as e:
            print(f"   ❌ Ошибка: {str(e)}")
            return jsonify({"error": f"Speech recognition error: {str(e)}"}), 500
        finally:
            if os.path.exists(audio_path):
                os.unlink(audio_path)
        
        # ===== ДОБАВЛЯЕМ ПУНКТУАЦИЮ =====
        print("✏️ Добавляю пунктуацию (recasepunc)...")
        final_text = recasepunc_punctuate(text)
        print(f"   ✓ Готово")
        print(f"✅ РЕЗУЛЬТАТ: {final_text}\n")
        
        return jsonify({
            "text": final_text,
            "raw_text": text
        })
    
    except Exception as e:
        print(f"❌ ОШИБКА: {str(e)}\n")
        return jsonify({"error": str(e)}), 500

@app.route('/health', methods=['GET'])
def health():
    """Проверка, живо ли приложение"""
    return jsonify({"status": "ok"}), 200

if __name__ == '__main__':
    print("\n🌐 Запускаю Flask на http://0.0.0.0:5000")
    app.run(host='0.0.0.0', port=5000, debug=False)
