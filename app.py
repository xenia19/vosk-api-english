def download_vosk_model():
    """Скачиваем Vosk модель для английского"""
    model_path = "/tmp/vosk_model"
    
    if not os.path.exists(model_path):
        print("\n⏳ Скачиваю Vosk модель для английского...")
        
        # Используем актуальную ссылку
        model_url = "https://alphacephei.com/vosk/models/vosk-model-en-us-0.22.zip"
        zip_path = "/tmp/vosk_model.zip"
        
        try:
            urllib.request.urlretrieve(model_url, zip_path)
            print("   ✓ Загружена")
            
            print("   Распаковываю...")
            with zipfile.ZipFile(zip_path, 'r') as zip_ref:
                zip_ref.extractall("/tmp/")
            
            # Переименовываем папку (зависит от того, как она называется в архиве)
            import glob
            model_dirs = glob.glob("/tmp/vosk-model-*")
            if model_dirs:
                os.rename(model_dirs[0], model_path)
            
            os.remove(zip_path)
            print("   ✓ Распакована")
        except Exception as e:
            print(f"   ❌ Ошибка: {e}")
            raise
    else:
        print("\n✅ Vosk модель уже загружена")
    
    return model_path
