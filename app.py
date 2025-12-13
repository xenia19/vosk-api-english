import os
import json
import tempfile
import glob
import threading
import time
import shutil
from flask import Flask, request, jsonify
from vosk import Model, KaldiRecognizer, SetLogLevel
from pydub import AudioSegment
from flask_cors import CORS
import urllib.request
import zipfile
import traceback

app = Flask(__name__)
CORS(app, resources={r'/*': {'origins': '*'}})

print("=" * 60)
print("🚀 ИНИЦИАЛИЗАЦИЯ ПРИЛОЖЕНИЯ")
print("=" * 60)

VOSK_MODEL_PATH = None
MODELS_LOADED = False
LOAD_ERROR = None

def download_vosk_model():
    """Скачиваем Vosk модель для английского"""
    model_path = "/tmp/vosk_model"
    
    # Проверяем, уже ли загружена
    if os.path.exists(model_path) and os.path.isdir(model_path):
        print("✅ Vosk модель уже загружена (из кэша)")
        return model_path
    
    print("\n⏳ Скачиваю Vosk модель для английского...")
    
    # Используем МАЛЕНЬКУЮ модель (50MB вместо 150MB)
    urls = [
        "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip"
    ]
    
    for model_url in urls:
        zip_path = "/tmp/vosk_model.zip"
        
        try:
            print(f"   Попытка загрузить: {model_url.split('/')[-1]}")
            
            # Загружаем с User-Agent заголовком
            request_obj = urllib.request.Request(model_url)
            request_obj.add_header('User-Agent', 'Mozilla/5.0')
            
            # Скачиваем файл
            with urllib.request.urlopen(request_obj, timeout=300) as response, open(zip_path, 'wb') as out_file:
                shutil.copyfileobj(response, out_file)
            
            print("   ✓ Загружена")
            
            # Распаковываем
            print("   Распаковываю...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall("/tmp/")
            
            print("   ✓ Распакована")
            
            # Находим папку модели
            model_dirs = glob.glob("/tmp/vosk-model-*")
            if model_dirs:
                source_dir = model_dirs[0]
                os.rename(source_dir, model_path)
                
                # Проверяем, что модель валидна
                if os.path.exists(os.path.join(model_path, "conf")):
                    print("   ✓ Модель валидна")
                    
                    # Удаляем zip файл
                    if os.path.exists(zip_path):
                        os.remove(zip_path)
                    
                    return model_path
            
            # Удаляем zip если что-то не так
            if os.path.exists(zip_path):
                os.remove(zip_path)
        
        except urllib.error.URLError as e:
            print(f"   ❌ URL ошибка: {str(e)[:100]}")
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except:
                    pass
            continue
        
        except Exception as e:
            print(f"   ❌ Ошибка: {str(e)[:100]}")
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except:
                    pass
            continue
    
    # Если ничего не сработало
    return None

def load_models_background():
    """Загружаем модели в фоне"""
    global VOSK_MODEL_PATH, MODELS_LOADED, LOAD_ERROR
    
    try:
        print("\n" + "=" * 60)
        print("⏱️  ЗАГРУЗКА МОДЕЛЕЙ В ФОНОВОМ ПОТОКЕ")
        print("=" * 60)
        
        VOSK_MODEL_PATH = download_vosk_model()
        
        if VOSK_MODEL_PATH is None:
            LOAD_ERROR = "Failed to download Vosk model from all sources"
            print(f"\n❌ {LOAD_ERROR}")
            MODELS_LOADED = False
        else:
            MODELS_LOADED = True
            print("\n" + "=" * 60)
            print("✅ МОДЕЛИ УСПЕШНО ЗАГРУЖЕНЫ")
            print("=" * 60 + "\n")
    
    except Exception as e:
        LOAD_ERROR = str(e)
        print(f"\n❌ Ошибка при загрузке: {LOAD_ERROR}\n")
        MODELS_LOADED = False

# Запускаем загрузку моделей в отдельном потоке (не блокируем приложение!)
print("⏳ Запускаю загрузку моделей в фоновом потоке...\n")
model_thread = threading.Thread(target=load_models_background, daemon=True)
model_thread.start()

def simple_punctuate(text):
    """Добавляет заглавную букву и точку"""
    if not text or not text.strip():
        return text
    
    text = text.strip()
    
    # Капитализируем первое слово
    if len(text) > 0:
        text = text[0].upper() + text[1:]
    
    # Добавляем точку если её нет
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
    
    # Проверяем, загружены ли модели
    print(f"📊 Статус моделей: MODELS_LOADED={MODELS_LOADED}")
    print(f"📊 MODEL_PATH={VOSK_MODEL_PATH}")
    
    if not MODELS_LOADED or VOSK_MODEL_PATH is None:
        error_msg = LOAD_ERROR or "Models still loading..."
        print(f"❌ Модели не готовы: {error_msg}")
        print("=" * 60 + "\n")
        return jsonify({
            "error": error_msg,
            "status": "models_loading"
        }), 503
    
    try:
        # Проверяем файл
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
        file.seek(0)  # Возвращаемся в начало файла
        print(f"📥 Получен файл: {file.filename} ({file_size} bytes)")
        
        # ===== КОНВЕРТИРУЕМ В WAV =====
        print("🔄 Начинаю конвертацию в WAV 16kHz...")
        
        with tempfile.NamedTemporaryFile(delete=False, suffix='.wav') as tmp:
            audio_path = tmp.name
        
        try:
            print(f"   📂 Временный файл: {audio_path}")
            
            print(f"   ⏳ Загружаю аудио из файла...")
            song = AudioSegment.from_file(file)
            original_duration = len(song)
            print(f"   ✓ Загружено ({original_duration}ms, {len(song.get_array_of_samples())} samples)")
            
            print(f"   🔧 Конвертирую в моно + 16kHz...")
            song = song.set_channels(1).set_frame_rate(16000)
            print(f"   ✓ Конвертировано ({len(song)}ms)")
            
            print(f"   💾 Экспортирую в WAV...")
            song.export(audio_path, format="wav")
            print(f"   ✓ Экспортировано")
            
            # Проверяем что файл создан
            if not os.path.exists(audio_path):
                raise Exception(f"WAV file not created at {audio_path}")
            
            file_stat = os.stat(audio_path)
            print(f"   ✓ Файл существует ({file_stat.st_size} bytes)")
            
        except Exception as e:
            print(f"   ❌ ОШИБКА КОНВЕРТАЦИИ:")
            print(f"      Type: {type(e).__name__}")
            print(f"      Message: {str(e)}")
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
            
            print(f"   📊 Парсирую результат...")
            result_data = json.loads(result_json)
            print(f"   ✓ Распарсено")
            
            # Извлекаем текст
            if "result" in result_data and result_data["result"]:
                text = " ".join([item.get("conf", "") for item in result_data["result"] if "conf" in item])
            else:
                text = result_data.get("text", "")
            
            print(f"   📝 Извлеченный текст: '{text}'")
            
            if not text or not text.strip():
                print("   ⚠️ Речь не распознана (пустой результат)")
                print("=" * 60 + "\n")
                return jsonify({"error": "No speech detected in audio"}), 400
            
            print(f"   ✓ Распознано: '{text}'")
            
        except Exception as e:
            print(f"   ❌ ОШИБКА STT:")
            print(f"      Type: {type(e).__name__}")
            print(f"      Message: {str(e)}")
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
                    print(f"   ⚠️ Не удалось удалить файл: {e}")
        
        # ===== ДОБАВЛЯЕМ ПУНКТУАЦИЮ =====
        print("✏️  Добавляю пунктуацию...")
        try:
            final_text = simple_punctuate(text)
            print(f"   ✓ Пунктуация добавлена")
            print(f"✅ ФИНАЛЬНЫЙ РЕЗУЛЬТАТ: '{final_text}'")
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
        print(f"❌ КРИТИЧНАЯ ОШИБКА В MAIN HANDLER:")
        print(f"   Type: {type(e).__name__}")
        print(f"   Message: {str(e)}")
        print("   Stack trace:")
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
