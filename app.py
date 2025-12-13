import os
import json
import tempfile
from flask import Flask, request, jsonify
from vosk import Model, KaldiRecognizer, SetLogLevel
from pydub import AudioSegment
from flask_cors import CORS
from sbert_punc_case_ru import SbertPuncCase
import urllib.request
import zipfile

app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})

print("=" * 50)
print("🚀 ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ")
print("=" * 50)

# ===== ЗАГРУЗКА МОДЕЛЕЙ (один раз при старте) =====

def download_vosk_model():
    """Скачиваем Vosk модель для английского"""
    model_path = "/tmp/vosk_model"
    
    if not os.path.exists(model_path):
        print("\n⏳ Скачиваю Vosk модель для английского...")
        print("   (это займет ~2-3 минуты, зависит от интернета)")
        
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

def init_punc_model():
    """Инициализируем модель для пунктуации"""
    print("\n⏳ Загружаю модель пунктуации SbertPuncCase...")
    try:
        punc_model = SbertPuncCase()
        print("✅ Модель пунктуации готова\n")
        return punc_model
    except Exception as e:
        print(f"⚠️ Ошибка: {e}\n")
        return None

# Загружаем при старте
VOSK_MODEL_PATH = download_vosk_model()
PUNC_MODEL = init_punc_model()

print("=" * 50)
print("✅ ПРИЛОЖЕНИЕ ГОТОВО К РАБОТЕ")
print("=" * 50)

# ===== API ENDPOINT =====

@app.route('/api', methods=['POST'])
def process_audio():
    """
    Принимает аудио файл, конвертирует в текст, добавляет пунктуацию
    
    Ожидает файл с ключом '111' (как в твоем React Native коде)
    """
    try:
        # Проверяем, есть ли файл
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
            # Загружаем аудио
            song = AudioSegment.from_file(file)
            
            # Преобразуем в моно + 16kHz (требует Vosk)
            song = song.set_channels(1).set_frame_rate(16000)
            
            # Сохраняем временный файл
            song.export(audio_path, format="wav")
            print("   ✓ Готово")
        except Exception as e:
            print(f"   ❌ Ошибка конвертации: {str(e)}")
            return jsonify({"error": f"Audio conversion error: {str(e)}"}), 400
        
        # ===== РАСПОЗНАВАНИЕ РЕЧИ (VOSK) =====
        print("🎤 Распознаю речь...")
        
        try:
            SetLogLevel(-1)  # Отключаем логи Vosk (много текста)
            
            # Инициализируем модель
            model = Model(VOSK_MODEL_PATH)
            recognizer = KaldiRecognizer(model, 16000)
            recognizer.SetWords(True)
            
            # Читаем аудио файл и распознаем
            with open(audio_path, "rb") as audio_file:
                while True:
                    data = audio_file.read(4096)
                    if not data:
                        break
                    recognizer.AcceptWaveform(data)
            
            # Получаем финальный результат
            result_json = recognizer.FinalResult()
            result_data = json.loads(result_json)
            
            # Извлекаем текст
            if "result" in result_data and result_data["result"]:
                # Если есть массив результатов (более точный)
                text = " ".join([item["conf"] for item in result_data["result"] if "conf" in item])
            else:
                # Иначе берем "text" поле
                text = result_data.get("text", "")
            
            if not text.strip():
                print("   ⚠️ Речь не распознана")
                return jsonify({"error": "No speech detected"}), 400
            
            print(f"   ✓ Распознано: {text}")
            
        except Exception as e:
            print(f"   ❌ Ошибка: {str(e)}")
            return jsonify({"error": f"Speech recognition error: {str(e)}"}), 500
        finally:
            # Удаляем временный файл
            if os.path.exists(audio_path):
                os.unlink(audio_path)
        
        # ===== ДОБАВЛЯЕМ ПУНКТУАЦИЮ И КАПИТАЛИЗАЦИЮ =====
        print("✏️ Добавляю пунктуацию...")
        
        try:
            if PUNC_MODEL:
                final_text = PUNC_MODEL.punctuate(text)
            else:
                # Fallback: простая капитализация
                final_text = text[0].upper() + text[1:] + '.' if text else text
            
            print(f"   ✓ Готово")
            print(f"✅ РЕЗУЛЬТАТ: {final_text}\n")
            
        except Exception as e:
            print(f"   ⚠️ Ошибка пунктуации: {e}")
            final_text = text
        
        # ===== ВОЗВРАЩАЕМ РЕЗУЛЬТАТ =====
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


