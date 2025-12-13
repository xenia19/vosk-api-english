def download_vosk_model():
    """Скачиваем Vosk модель для английского"""
    model_path = "/tmp/vosk_model"
    
    # Проверяем, уже ли загружена
    if os.path.exists(model_path) and os.path.isdir(model_path):
        print("✅ Vosk модель уже загружена (из кэша)")
        return model_path
    
    print("\n⏳ Скачиваю Vosk модель для английского (это может занять несколько минут)...")
    
    # Пробуем несколько URL
    urls = [
        "https://alphacephei.com/vosk/models/vosk-model-small-en-us-0.15.zip",
        "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip"
    ]
    
    for model_url in urls:
        zip_path = "/tmp/vosk_model.zip"
        
        try:
            print(f"   Попытка загрузить с: {model_url.split('/')[-1]}")
            
            # Скачиваем БЕЗ timeout (убрал ошибку)
            urllib.request.urlretrieve(model_url, zip_path)
            print("   ✓ Загружена")
            
            print("   Распаковываю...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall("/tmp/")
            
            # Находим распакованную папку
            model_dirs = glob.glob("/tmp/vosk-model-*")
            if model_dirs:
                source_dir = model_dirs[0]
                os.rename(source_dir, model_path)
                print("   ✓ Распакована")
                
                # Проверяем, что модель нормальная
                if os.path.exists(os.path.join(model_path, "conf")):
                    print(f"   ✓ Модель валидна")
                    return model_path
            
            if os.path.exists(zip_path):
                os.remove(zip_path)
        
        except Exception as e:
            print(f"   ❌ Не удалось загрузить: {str(e)[:100]}")
            if os.path.exists(zip_path):
                try:
                    os.remove(zip_path)
                except:
                    pass
            continue
    
    # Если ничего не сработало
    return None
