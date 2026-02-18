#!/usr/bin/env python3
"""Тест ru_worker - обработка одной задачи"""
import os
import sys
from pathlib import Path
import json
import psycopg2
from psycopg2.extras import RealDictCursor


def _load_env_file() -> None:
    try:
        from dotenv import load_dotenv

        env_path = Path(__file__).parent.parent / ".env"
        load_dotenv(env_path)
    except ImportError:
        pass


def main() -> int:
    from config import get_config

    # Добавляем путь к ru_worker
    sys.path.insert(0, os.path.join(os.path.dirname(__file__), "ru_worker"))

    _load_env_file()
    config = get_config()

    postgres_host = config.postgres_host or "localhost"
    postgres_port = config.postgres_port or 5432
    postgres_db = config.postgres_db or "biretos_automation"
    postgres_user = config.postgres_user or "biretos_user"
    postgres_password = config.postgres_password

    # Импортируем функции из ru_worker только в runtime manual-script mode.
    from ru_worker import process_job

    print("=== TEST: ru_worker processing ===")

    try:
        # Подключаемся напрямую с правильными параметрами
        conn = psycopg2.connect(
            host=postgres_host,
            port=postgres_port,
            dbname=postgres_db,
            user=postgres_user,
            password=postgres_password,
        )
        cursor = conn.cursor(cursor_factory=RealDictCursor)

        # SELECT pending задачу (любую из поддерживаемых)
        cursor.execute(
            """
            SELECT * FROM job_queue
            WHERE status = 'pending'
              AND job_type IN ('telegram_update', 'telegram_command', 'test_job')
            ORDER BY created_at ASC
            LIMIT 1
            FOR UPDATE SKIP LOCKED
            """
        )

        job = cursor.fetchone()

        if not job:
            print("Нет pending задач telegram_update")
            conn.close()
            return 0

        print(f"Найдена задача: {job['id']} ({job['job_type']})")

        # UPDATE на processing
        cursor.execute(
            """
            UPDATE job_queue
            SET status = 'processing', updated_at = NOW()
            WHERE id = %s
            """,
            (job["id"],),
        )
        conn.commit()
        print("Статус изменен на processing")

        # Обрабатываем задачу
        try:
            result = process_job(dict(job), conn)
            print(f"Результат: {json.dumps(result, indent=2, ensure_ascii=False)}")

            # UPDATE на completed
            cursor.execute(
                """
                UPDATE job_queue
                SET status = 'completed',
                    result = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (json.dumps(result), job["id"]),
            )
            conn.commit()
            print("Статус изменен на completed")
        except Exception as e:
            error_msg = str(e)
            print(f"Ошибка обработки: {error_msg}")
            import traceback

            traceback.print_exc()

            # UPDATE на failed
            cursor.execute(
                """
                UPDATE job_queue
                SET status = 'failed',
                    error = %s,
                    updated_at = NOW()
                WHERE id = %s
                """,
                (error_msg, job["id"]),
            )
            conn.commit()
            print("Статус изменен на failed")

        conn.close()
        return 0

    except Exception as e:
        print(f"Ошибка: {e}")
        import traceback

        traceback.print_exc()
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
