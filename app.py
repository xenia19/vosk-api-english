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

def load_models_background():
    """Проверяем что модель уже есть в /tmp (из Docker build)"""
    global VOSK_MODEL_PATH, MODELS_LOADED, LOAD_ERROR
    
    try:
        print("\n" + "=" * 60)
        print("🔍 ПРОВЕРЯЮ VOSK МОДЕЛЬ")
        print("=" * 60)
        
        model_path = "/tmp/vosk_model"
        
        # Проверяем что модель существует (она была скачана при Docker build)
        if not os.path.exists(model_path):
            raise Exception(f"Model directory not found at {model_path}")
        
        print(f"✓ Модель найдена в {model_path}")
        
        # Проверяем структуру
        if not os.path.isdir(model_path):
            raise Exception(f"{model_path} is not a directory")
        
        if not os.path.exists(os.path.join(model_path, "conf")):
            raise Exception(f"Model structure invalid - no 'conf' directory")
        
        print("✓ Структура модели валидна")
        
        VOSK_MODEL_PATH = model_path
        MODELS_LOADED = True
        
        print("\n" + "=" * 60)
        print("✅ VOSK МОДЕЛЬ ГОТОВА К ИСПОЛЬЗОВАНИЮ")
        print("=" * 60 + "\n")
    
    except Exception as e:
        LOAD_ERROR = str(e)
        print(f"\n❌ ОШИБКА: {LOAD_ERROR}\n")
        MODELS_LOADED = False

# Запускаем проверку моделей в отдельном потоке
print("⏳ Проверяю загруженные модели...\n")
model_thread = threading.Thread(target=load_models_background, daemon=True)
model_thread.start()

def simple_punctuate(text):
    """Добавляет заглавную букву и точку"""
    if not text or not text.strip():
        return text
    
    text = text.strip()
    
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
        "version": "1.0",
        "status": "running",
        "models_loaded": MODELS_LOADED,
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
        "load_error": LOAD_ERROR
    }), 200

@app.route('/api', methods=['POST'])
def process_audio():
    """Распознает речь и добавляет пунктуацию"""
    
    print("\n" + "=" * 60)
    print("🔵 ПОЛУЧЕН ЗАПРОС /api")
    print("=" * 60)
    
    print(f"📊 Статус моделей: MODELS_LOADED={MODELS_LOADED}")
    
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
        print("🔄 Начинаю конвертацию в WAV 16kHz...")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            audio_path = tmp.name
        
        try:
            print(f"   ⏳ Загружаю аудио...")
            song = AudioSegment.from_file(file)
            original_duration = len(song)
            print(f"   ✓ Загружено ({original_duration}ms)")
            
            print(f"   🔧 Конвертирую в моно + 16kHz...")
            song = song.set_channels(1).set_frame_rate(16000)
            print(f"   ✓ Конвертировано ({len(song)}ms)")
            
            print(f"   💾 Экспортирую в WAV...")
            song.export(audio_path, format="wav")
            print(f"   ✓ Экспортировано")
            
            if not os.path.exists(audio_path):
                raise Exception(f"WAV file not created at {audio_path}")
            
            file_stat = os.stat(audio_path)
            print(f"   ✓ Файл существует ({file_stat.st_size} bytes)")
            
        except Exception as e:
            print(f"   ❌ ОШИБКА КОНВЕРТАЦИИ: {str(e)}")
            traceback.print_exc()
            print("=" * 60 + "\n")
            return jsonify({"error": f"Audio conversion failed: {str(e)}"}), 400
        
        # ===== РАСПОЗНАВАНИЕ РЕЧИ (VOSK) =====
        print("🎤 Начинаю распознавание речи...")
        
        try:
            print(f"   ✓ Проверяю модель...")
            if not os.path.exists(VOSK_MODEL_PATH):
                raise Exception(f"Model path not found: {VOSK_MODEL_PATH}")
            print(f"   ✓ Путь к модели существует")
            
            print(f"   ⏳ Инициализирую Vosk...")
            SetLogLevel(-1)
            model = Model(VOSK_MODEL_PATH)
            print(f"   ✓ Модель загружена")
            
            print(f"   ⏳ Создаю KaldiRecognizer...")
            recognizer = KaldiRecognizer(model, 16000)
            recognizer.SetWords(True)
            print(f"   ✓ Recognizer готов")
            
            print(f"   ⏳ Читаю WAV файл...")
            bytes_read = 0
            with open(audio_path, "rb") as audio_file:
                while True:
                    data = audio_file.read(4096)
                    if not data:
                        break
                    recognizer.AcceptWaveform(data)
                    bytes_read += len(data)
            print(f"   ✓ Прочитано {bytes_read} байт")
            
            print(f"   ⏳ Получаю финальный результат...")
            result_json = recognizer.FinalResult()
            print(f"   ✓ JSON получен")
            
            result_data = json.loads(result_json)
            
            if "result" in result_data and result_data["result"]:
                text = " ".join([item.get("conf", "") for item in result_data["result"] if "conf" in item])
            else:
                text = result_data.get("text", "")
            
            print(f"   📝 Текст: '{text}'")
            
            if not text or not text.strip():
                print("   ⚠️ Речь не распознана")
                print("=" * 60 + "\n")
                return jsonify({"error": "No speech detected in audio"}), 400
            
            print(f"   ✓ Распознано")
            
        except Exception as e:
            print(f"   ❌ ОШИБКА STT: {str(e)}")
            traceback.print_exc()
            print("=" * 60 + "\n")
            return jsonify({"error": f"Speech recognition error: {str(e)}"}), 500
        finally:
            print(f"   🧹 Удаляю временный файл...")
            if os.path.exists(audio_path):
                try:
                    os.unlink(audio_path)
                    print(f"   ✓ Файл удален")
                except Exception as e:
                    print(f"   ⚠️ Не удалось удалить: {e}")
        
        # ===== ДОБАВЛЯЕМ ПУНКТУАЦИЮ =====
        print("✏️  Добавляю пунктуацию...")
        try:
            final_text = simple_punctuate(text)
            print(f"   ✓ Пунктуация добавлена")
            print(f"✅ РЕЗУЛЬТАТ: '{final_text}'")
        except Exception as e:
            print(f"   ❌ Ошибка пунктуации: {e}")
            final_text = text
        
        print("=" * 60 + "\n")
        
        return jsonify({
            "text": final_text,
            "raw_text": text,
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
    print("📡 Слушаю на http://0.0.0.0:5000")
    print("🔗 Главная: GET /")
    print("🔗 Здоровье: GET /health")
    print("📤 API: POST /api")
    print("=" * 60 + "\n")
    
    app.run(host='0.0.0.0', port=5000, debug=False, use_reloader=False)
