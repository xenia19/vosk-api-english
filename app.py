import os
import json
import tempfile
import threading
from flask import Flask, request, jsonify
from vosk import Model, KaldiRecognizer, SetLogLevel
from pydub import AudioSegment
from flask_cors import CORS
import traceback

app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})

print("=" * 60)
print("🚀 ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ")
print("=" * 60)

VOSK_MODEL_PATH = None
MODELS_LOADED = False
LOAD_ERROR = None
PUNCTUATOR = None

def load_models_background():
    """Загружаем Vosk модель и пунктуатор"""
    global VOSK_MODEL_PATH, MODELS_LOADED, LOAD_ERROR, PUNCTUATOR
    
    try:
        print("\n" + "=" * 60)
        print("🔍 ЗАГРУЖАЮ МОДЕЛИ")
        print("=" * 60)
        
        # ===== VOSK =====
        model_path = "/app/vosk_model"
        
        if not os.path.exists(model_path):
            raise Exception(f"Model directory not found at {model_path}")
        
        print(f"✓ Vosk модель найдена в {model_path}")
        
        if not os.path.isdir(model_path):
            raise Exception(f"{model_path} is not a directory")
        
        if not os.path.exists(os.path.join(model_path, "conf")):
            raise Exception(f"Model structure invalid - no 'conf' directory")
        
        print("✓ Структура Vosk модели валидна")
        VOSK_MODEL_PATH = model_path
        
        # ===== PUNCTUATOR =====
        print("⏳ Загружаю модель пунктуации...")
        try:
            from deepmultilingualpunctuation import PunctuationModel
            PUNCTUATOR = PunctuationModel()
            print("✓ Модель пунктуации загружена")
        except Exception as e:
            print(f"⚠️ Пунктуатор не загружен: {e}")
            print("   Будет использована простая пунктуация")
            PUNCTUATOR = None
        
        MODELS_LOADED = True
        
        print("\n" + "=" * 60)
        print("✅ МОДЕЛИ ГОТОВЫ К ИСПОЛЬЗОВАНИЮ")
        print("=" * 60 + "\n")
    
    except Exception as e:
        LOAD_ERROR = str(e)
        print(f"\n❌ ОШИБКА: {LOAD_ERROR}\n")
        MODELS_LOADED = False

print("⏳ Загружаю модели в фоне...\n")
model_thread = threading.Thread(target=load_models_background, daemon=True)
model_thread.start()

def smart_punctuate(text):
    """Умная пунктуация с помощью ML модели"""
    global PUNCTUATOR
    
    if not text or not text.strip():
        return text
    
    text = text.strip()
    
    # Если пунктуатор загружен - используем его
    if PUNCTUATOR is not None:
        try:
            result = PUNCTUATOR.restore_punctuation(text)
            print(f"   ✓ ML пунктуация: '{result}'")
            return result
        except Exception as e:
            print(f"   ⚠️ ML пунктуация не сработала: {e}")
    
    # Fallback: простая пунктуация
    if len(text) > 0:
        text = text[0].upper() + text[1:]
    
    if text and text[-1] not in '.!?,;:':
        text += '.'
    
    return text

@app.route('/', methods=['GET'])
def index():
    """Главная страница"""
    return jsonify({
        "name": "Vosk API - English Speech to Text",
        "version": "2.0",
        "status": "running",
        "models_loaded": MODELS_LOADED,
        "punctuation": "ML" if PUNCTUATOR else "simple",
        "endpoints": {
            "health": "GET /health",
            "api": "POST /api (с файлом audio в поле '111')"
        }
    }), 200

@app.route('/health', methods=['GET'])
def health():
    """Проверка здоровья приложения"""
    return jsonify({
        "status": "ok",
        "app_running": True,
        "models_loaded": MODELS_LOADED,
        "load_error": LOAD_ERROR,
        "vosk_ready": VOSK_MODEL_PATH is not None,
        "punctuator_ready": PUNCTUATOR is not None
    }), 200

@app.route('/api', methods=['POST'])
def process_audio():
    """Распознает речь и добавляет пунктуацию"""
    
    print("\n" + "=" * 60)
    print("🔵 ПОЛУЧЕН ЗАПРОС /api")
    print("=" * 60)
    
    print(f"📊 Статус: MODELS_LOADED={MODELS_LOADED}, PUNCTUATOR={PUNCTUATOR is not None}")
    
    if not MODELS_LOADED or VOSK_MODEL_PATH is None:
        error_msg = LOAD_ERROR or "Models not loaded"
        print(f"❌ Модели не готовы: {error_msg}")
        print("=" * 60 + "\n")
        return jsonify({
            "error": error_msg,
            "status": "models_not_ready"
        }), 503
    
    try:
        print("📥 Проверяю наличие файла...")
        if '111' not in request.files:
            print("❌ Ошибка: нет файла в поле '111'")
            print("=" * 60 + "\n")
            return jsonify({"error": "No file provided (expected key: '111')"}), 400
        
        file = request.files['111']
        print(f"✓ Файл найден: {file.filename}")
        
        if file.filename == '':
            print("❌ Ошибка: пустое имя файла")
            print("=" * 60 + "\n")
            return jsonify({"error": "Empty filename"}), 400
        
        file_size = len(file.read())
        file.seek(0)
        print(f"📥 Получен файл: {file.filename} ({file_size} bytes)")
        
        # ===== КОНВЕРТИРУЕМ В WAV =====
        print("🔄 Конвертирую в WAV 16kHz...")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            audio_path = tmp.name
        
        try:
            song = AudioSegment.from_file(file)
            original_duration = len(song)
            print(f"   ✓ Загружено ({original_duration}ms)")
            
            song = song.set_channels(1).set_frame_rate(16000)
            song.export(audio_path, format="wav")
            
            file_stat = os.stat(audio_path)
            print(f"   ✓ Конвертировано ({file_stat.st_size} bytes)")
            
        except Exception as e:
            print(f"   ❌ ОШИБКА КОНВЕРТАЦИИ: {str(e)}")
            traceback.print_exc()
            print("=" * 60 + "\n")
            return jsonify({"error": f"Audio conversion failed: {str(e)}"}), 400
        
        # ===== РАСПОЗНАВАНИЕ РЕЧИ (VOSK) =====
        print("🎤 Распознаю речь...")
        
        try:
            SetLogLevel(-1)
            model = Model(VOSK_MODEL_PATH)
            recognizer = KaldiRecognizer(model, 16000)
            recognizer.SetWords(True)
            
            bytes_read = 0
            with open(audio_path, "rb") as audio_file:
                while True:
                    data = audio_file.read(4096)
                    if not data:
                        break
                    recognizer.AcceptWaveform(data)
                    bytes_read += len(data)
            
            result_json = recognizer.FinalResult()
            result_data = json.loads(result_json)
            print(f"   📋 Raw: {result_data}")
            
            text = result_data.get("text", "")
            print(f"   📝 Распознано: '{text}'")
            
            if not text or not text.strip():
                print("   ⚠️ Речь не распознана")
                print("=" * 60 + "\n")
                return jsonify({"error": "No speech detected in audio"}), 400
            
        except Exception as e:
            print(f"   ❌ ОШИБКА STT: {str(e)}")
            traceback.print_exc()
            print("=" * 60 + "\n")
            return jsonify({"error": f"Speech recognition error: {str(e)}"}), 500
        finally:
            if os.path.exists(audio_path):
                try:
                    os.unlink(audio_path)
                except:
                    pass
        
        # ===== ДОБАВЛЯЕМ ПУНКТУАЦИЮ =====
        print("✏️  Добавляю пунктуацию...")
        try:
            final_text = smart_punctuate(text)
            print(f"✅ РЕЗУЛЬТАТ: '{final_text}'")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            final_text = text
        
        print("=" * 60 + "\n")
        
        return jsonify({
            "text": final_text,
            "raw_text": text,
            "punctuation": "ML" if PUNCTUATOR else "simple",
            "status": "success"
        }), 200
    
    except Exception as e:
        print(f"❌ КРИТИЧНАЯ ОШИБКА: {str(e)}")
        traceback.print_exc()
        print("=" * 60 + "\n")
        return jsonify({"error": f"Processing error: {str(e)}"}), 500

@app.errorhandler(404)
def not_found(error):
    return jsonify({"error": "Endpoint not found"}), 404

@app.errorhandler(500)
def server_error(error):
    print(f"❌ UNHANDLED ERROR: {error}")
    traceback.print_exc()
    return jsonify({"error": "Internal server error"}), 500

if __name__ == '__main__':
    print("\n" + "=" * 60)
    print("🌐 ЗАПУСКАЮ FLASK")
    print("=" * 60)
    print("📡 http://0.0.0.0:5000")
    print("=" * 60 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
