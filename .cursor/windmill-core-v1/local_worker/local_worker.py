"""
Windmill Execution Core v1 - Local PC Worker
Асинхронный worker для выполнения задач через polling + callback

Требования:
- Только outbound HTTPS
- Никакого listening server
- Простая обработка ошибок
"""

import json
import random
import time
from typing import Dict, Any, Optional

import httpx

from config import get_config

_CONFIG = get_config()

# Конфигурация
RU_BASE_URL = _CONFIG.ru_base_url or "https://n8n.biretos.ae"
POLL_INTERVAL = _CONFIG.poll_interval or 5  # секунды
WORKER_ID = _CONFIG.worker_id or "local-pc-worker"

# HTTP клиент
client = httpx.Client(timeout=30.0)


def poll_job() -> Optional[Dict[str, Any]]:
    """Polling задач с RU-VPS"""
    try:
        response = client.get(
            f"{RU_BASE_URL}/api/jobs/poll",
            params={"worker_id": WORKER_ID}
        )
        
        if response.status_code == 204:
            # Нет задач
            return None
        
        if response.status_code == 200:
            return response.json()
        
        print(f"Error polling job: {response.status_code} - {response.text}")
        return None
        
    except Exception as e:
        print(f"Exception during polling: {e}")
        return None


def execute_heavy_compute(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Выполняет GPU-light heavy compute workload на torch
    
    - Пытается использовать CUDA если доступно
    - Fallback на CPU если CUDA недоступна или ошибка
    - Возвращает метрики выполнения
    """
    try:
        import torch
    except ImportError:
        raise Exception("torch not installed")
    
    # Параметры из payload
    matrix_size = payload.get("matrix", 4096)
    iterations = payload.get("iters", 8)
    
    # Определяем device
    cuda_available = torch.cuda.is_available()
    device_name = "cuda" if cuda_available else "cpu"
    device = torch.device(device_name)
    
    torch_version = torch.__version__
    error_note = None
    
    try:
        # Создаем тензоры
        dtype = torch.float32  # Используем float32 для стабильности
        tensor_a = torch.randn(matrix_size, matrix_size, dtype=dtype, device=device)
        tensor_b = torch.randn(matrix_size, matrix_size, dtype=dtype, device=device)
        
        # Выполняем вычисления
        start_time = time.perf_counter()
        
        for _ in range(iterations):
            tensor_c = torch.matmul(tensor_a, tensor_b)
            tensor_a = tensor_c  # Цепочка вычислений
        
        # Синхронизируем для точного измерения времени
        if cuda_available:
            torch.cuda.synchronize()
        
        elapsed_time = time.perf_counter() - start_time
        elapsed_ms = elapsed_time * 1000
        
        # Получаем checksum
        checksum = float(tensor_c.sum().item())
        
        # Очистка памяти
        del tensor_a, tensor_b, tensor_c
        if cuda_available:
            torch.cuda.empty_cache()
        
        return {
            "job_type": "heavy_compute_test",
            "device": device_name,
            "cuda_available": cuda_available,
            "torch_version": torch_version,
            "elapsed_ms": round(elapsed_ms, 2),
            "checksum": round(checksum, 6),
            "shape": [matrix_size, matrix_size],
            "dtype": str(dtype),
            "iterations": iterations,
            "error_note": error_note
        }
        
    except Exception as e:
        # Если CUDA ошибка, пробуем CPU fallback
        if cuda_available and "cuda" in str(e).lower():
            error_note = f"CUDA error, fallback to CPU: {str(e)}"
            device_name = "cpu"
            device = torch.device("cpu")
            
            # Очистка CUDA памяти перед fallback
            try:
                torch.cuda.empty_cache()
            except:
                pass
            
            # Повторяем на CPU
            try:
                tensor_a = torch.randn(matrix_size, matrix_size, dtype=torch.float32, device=device)
                tensor_b = torch.randn(matrix_size, matrix_size, dtype=torch.float32, device=device)
                
                start_time = time.perf_counter()
                for _ in range(iterations):
                    tensor_c = torch.matmul(tensor_a, tensor_b)
                    tensor_a = tensor_c
                elapsed_time = time.perf_counter() - start_time
                elapsed_ms = elapsed_time * 1000
                checksum = float(tensor_c.sum().item())
                
                del tensor_a, tensor_b, tensor_c
                
                return {
                    "job_type": "heavy_compute_test",
                    "device": device_name,
                    "cuda_available": cuda_available,
                    "torch_version": torch_version,
                    "elapsed_ms": round(elapsed_ms, 2),
                    "checksum": round(checksum, 6),
                    "shape": [matrix_size, matrix_size],
                    "dtype": "torch.float32",
                    "iterations": iterations,
                    "error_note": error_note
                }
            except Exception as cpu_error:
                raise Exception(f"CPU fallback failed: {str(cpu_error)}")
        else:
            raise


def execute_ocr_test(payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Выполняет OCR-stub обработку файла
    
    - Пытается использовать pytesseract если доступно
    - Fallback на mock результат если OCR недоступен
    - Обрабатывает PDF и изображения
    """
    start_time = time.perf_counter()
    
    file_path = payload.get("file_path", "")
    file_type = payload.get("file_type", "image")
    language = payload.get("language", "auto")
    
    # Проверяем наличие pytesseract
    try:
        import pytesseract
        ocr_available = True
    except ImportError:
        ocr_available = False
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return {
            "job_type": "ocr_test",
            "success": False,
            "ocr_engine": "none",
            "language": language,
            "text_length": 0,
            "sample_text": "",
            "elapsed_ms": round(elapsed_ms, 2),
            "error": "pytesseract not installed"
        }
    
    # Проверяем наличие tesseract binary
    try:
        pytesseract.get_tesseract_version()
        tesseract_available = True
    except Exception:
        tesseract_available = False
    
    # Fallback режим (mock)
    if not tesseract_available:
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return {
            "job_type": "ocr_test",
            "success": True,  # Stub режим считается успешным
            "ocr_engine": "mock",
            "language": language,
            "text_length": 0,
            "sample_text": "[OCR MOCK]",
            "elapsed_ms": round(elapsed_ms, 2),
            "note": "tesseract not available",
            "file_path": file_path,
            "file_type": file_type
        }
    
    # Реальный OCR
    try:
        from PIL import Image
        
        images = []
        
        if file_type == "pdf":
            # Попытка использовать pdf2image
            try:
                from pdf2image import convert_from_path
                images = convert_from_path(file_path, first_page=1, last_page=2)  # Первые 2 страницы
            except ImportError:
                # pdf2image не доступен
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return {
                    "job_type": "ocr_test",
                    "success": False,
                    "ocr_engine": "tesseract",
                    "language": language,
                    "text_length": 0,
                    "sample_text": "",
                    "elapsed_ms": round(elapsed_ms, 2),
                    "error": "pdf2image not installed for PDF processing",
                    "file_path": file_path
                }
            except Exception as e:
                # Ошибка при конвертации PDF
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return {
                    "job_type": "ocr_test",
                    "success": False,
                    "ocr_engine": "tesseract",
                    "language": language,
                    "text_length": 0,
                    "sample_text": "",
                    "elapsed_ms": round(elapsed_ms, 2),
                    "error": f"PDF conversion failed: {str(e)}",
                    "file_path": file_path
                }
        else:
            # Обработка изображения
            try:
                image = Image.open(file_path)
                images = [image]
            except Exception as e:
                elapsed_ms = (time.perf_counter() - start_time) * 1000
                return {
                    "job_type": "ocr_test",
                    "success": False,
                    "ocr_engine": "tesseract",
                    "language": language,
                    "text_length": 0,
                    "sample_text": "",
                    "elapsed_ms": round(elapsed_ms, 2),
                    "error": f"Image loading failed: {str(e)}",
                    "file_path": file_path
                }
        
        # Выполняем OCR на всех изображениях
        all_text = []
        lang_param = language if language != "auto" else None
        
        for img in images:
            try:
                text = pytesseract.image_to_string(img, lang=lang_param)
                all_text.append(text)
            except Exception as e:
                # Пропускаем страницу с ошибкой, продолжаем
                all_text.append(f"[OCR ERROR on page: {str(e)}]")
        
        combined_text = "\n".join(all_text)
        text_length = len(combined_text)
        
        # Ограничиваем текст (первые 10k символов)
        sample_text = combined_text[:10000] if text_length > 10000 else combined_text
        
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        
        return {
            "job_type": "ocr_test",
            "success": True,
            "ocr_engine": "tesseract",
            "language": language,
            "text_length": text_length,
            "sample_text": sample_text,
            "elapsed_ms": round(elapsed_ms, 2),
            "file_path": file_path,
            "file_type": file_type,
            "pages_processed": len(images)
        }
        
    except Exception as e:
        # Любая другая ошибка
        elapsed_ms = (time.perf_counter() - start_time) * 1000
        return {
            "job_type": "ocr_test",
            "success": False,
            "ocr_engine": "tesseract",
            "language": language,
            "text_length": 0,
            "sample_text": "",
            "elapsed_ms": round(elapsed_ms, 2),
            "error": str(e),
            "file_path": file_path
        }


def execute_task(job_type: str, payload: Dict[str, Any]) -> Dict[str, Any]:
    """
    Выполняет задачу в зависимости от job_type
    
    - Если job_type == "heavy_compute_test": GPU-light torch workload
    - Если job_type == "ocr_test": OCR-stub обработка файла
    - Иначе: фиктивное выполнение (sleep 2-5 секунд + echo)
    """
    if job_type == "heavy_compute_test":
        return execute_heavy_compute(payload)
    
    if job_type == "ocr_test":
        return execute_ocr_test(payload)
    
    # Стандартная логика для других job_type
    import random
    sleep_time = random.uniform(2.0, 5.0)
    time.sleep(sleep_time)
    
    return {
        "echo": payload,
        "job_type": job_type,
        "execution_time": sleep_time
    }


def send_callback(job_id: str, job_token: str, result: Dict[str, Any], success: bool = True, error: Optional[str] = None):
    """Отправляет callback с результатом выполнения"""
    try:
        payload = {
            "job_token": job_token,
            "result": result if success else None,
            "success": success,
            "error": error
        }
        
        response = client.post(
            f"{RU_BASE_URL}/api/jobs/{job_id}/callback",
            json=payload
        )
        
        if response.status_code == 200:
            return True
        else:
            print(f"Error sending callback: {response.status_code} - {response.text}")
            return False
            
    except Exception as e:
        print(f"Exception sending callback: {e}")
        return False


def main():
    """Главный цикл worker"""
    print(f"Local PC Worker started")
    print(f"RU_BASE_URL: {RU_BASE_URL}")
    print(f"POLL_INTERVAL: {POLL_INTERVAL}s")
    print(f"WORKER_ID: {WORKER_ID}")
    print("Press Ctrl+C to stop\n")
    
    while True:
        try:
            # Polling задачи
            job = poll_job()
            
            if job is None:
                # Нет задач, ждем перед следующим polling
                time.sleep(POLL_INTERVAL)
                continue
            
            job_id = job["job_id"]
            job_type = job["job_type"]
            payload = job["payload"]
            job_token = job["job_token"]
            
            print(f"Received job: {job_id} ({job_type})")
            
            # Выполняем задачу
            try:
                result = execute_task(job_type, payload)
                print(f"Job {job_id} executed successfully")
                
                # Отправляем callback с успехом
                if send_callback(job_id, job_token, result, success=True):
                    print(f"Callback sent for job {job_id}\n")
                else:
                    print(f"Failed to send callback for job {job_id}\n")
                    
            except Exception as e:
                error_msg = str(e)
                print(f"Job {job_id} failed: {error_msg}")
                
                # Отправляем callback с ошибкой
                if send_callback(job_id, job_token, {}, success=False, error=error_msg):
                    print(f"Error callback sent for job {job_id}\n")
                else:
                    print(f"Failed to send error callback for job {job_id}\n")
            
        except KeyboardInterrupt:
            print("\nStopping worker...")
            break
        except Exception as e:
            print(f"Unexpected error in main loop: {e}")
            time.sleep(POLL_INTERVAL)
    
    client.close()
    print("Worker stopped")


if __name__ == "__main__":
    main()

