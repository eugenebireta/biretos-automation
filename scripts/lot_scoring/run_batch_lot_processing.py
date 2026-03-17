from __future__ import annotations

import time
from pathlib import Path

from scripts.lot_scoring.run_full_ranking_v341 import run_full_ranking


def is_lot_input(path: Path) -> bool:
    name = path.name.lower()
    return (
        path.is_file()
        and path.suffix.lower() == ".xlsx"
        and not name.startswith("report")
        and not name.startswith("~$")
        and not name.endswith("_enriched.xlsx")
        and not name.endswith("_full.xlsx")
        and not name.endswith("_ranked.xlsx")
        and not name.startswith("results_")
    )


def main() -> None:
    # Замените путь на локальную директорию с входными файлами.
    input_dir = Path(r"путь/к/папке")
    output_dir = input_dir / "downloads"

    if not input_dir.exists() or not input_dir.is_dir():
        raise FileNotFoundError(f"Директория не найдена: {input_dir}")

    existing = {item.name.lower(): item for item in input_dir.iterdir() if item.is_file()}

    required_reports = ["Report.xlsx", "Report2.xlsx", "Report3.xlsx"]
    missing_reports = [name for name in required_reports if name.lower() not in existing]

    lot_inputs = sorted((path for path in input_dir.iterdir() if is_lot_input(path)), key=lambda path: path.name.lower())

    if not lot_inputs:
        print("Не найдены входные файлы лотов (*.xlsx, кроме Report* и служебных файлов).")
        return

    if missing_reports:
        print("Не найдены report-файлы:", ", ".join(missing_reports))
        return

    success_count = 0
    error_count = 0
    failed_files: list[str] = []
    interrupted = False

    for input_path in lot_inputs:
        try:
            start_time = time.perf_counter()
            full_path, ranked_path = run_full_ranking(
                input_path=input_path,
                output_dir=output_dir,
            )
            elapsed = time.perf_counter() - start_time
            success_count += 1
            print(f"[OK] {input_path.name} обработан за {elapsed:.2f} секунд")
            print(f"  full:   {full_path}")
            print(f"  ranked: {ranked_path}")
        except KeyboardInterrupt:
            interrupted = True
            print("\n[INFO] Обработка прервана пользователем.")
            break
        except Exception as exc:
            error_count += 1
            print(f"[ERROR] {input_path.name}: {type(exc).__name__}: {exc}")
            failed_files.append(input_path.name)

    print(f"\nОбработка завершена: {success_count} успешно, {error_count} с ошибками.")
    if interrupted:
        print("\n[INFO] Прогон завершен досрочно.")
    if failed_files:
        print("\nНеудачные файлы для повторной обработки:")
        for failed in failed_files:
            print(f"  {failed}")


if __name__ == "__main__":
    main()
