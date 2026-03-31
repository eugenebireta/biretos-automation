import pandas as pd
import glob
import os

# Папка с исходными Excel-файлами
input_folder = r'C:\Users\Евгений\Desktop\для работы\Python\возвраты\csv'

# Финальный файл
output_file = r'C:\Users\Евгений\Desktop\для работы\Python\возвраты\Возвраты_Объединенные_Очищенные.xlsx'

try:
    # Получаем все .xlsx файлы, исключая временные (~$...)
    all_files = glob.glob(os.path.join(input_folder, '*.xlsx'))
    excel_files = [f for f in all_files if not os.path.basename(f).startswith('~$')]

    if not excel_files:
        raise FileNotFoundError("❌ В указанной папке нет Excel-файлов (.xlsx)")

    data_frames = []
    for file in excel_files:
        # Пропускаем первые 5 строк (заголовки начинаются с 6-й строки)
        df = pd.read_excel(file, skiprows=5, engine='openpyxl')
        data_frames.append(df)

    # Объединение и удаление дубликатов
    combined_df = pd.concat(data_frames, ignore_index=True)
    cleaned_df = combined_df.drop_duplicates()

    # Сохраняем как Excel
    cleaned_df.to_excel(output_file, index=False, engine='openpyxl')

    print(f"✅ Успешно объединено: {len(excel_files)} файлов")
    print(f"🧹 Строк до очистки: {len(combined_df)}, после: {len(cleaned_df)}")
    print(f"💾 Сохранено: {output_file}")
    input("Нажмите Enter для выхода...")

except Exception as e:
    print(f"❌ Произошла ошибка: {e}")
    input("Нажмите Enter для выхода...")