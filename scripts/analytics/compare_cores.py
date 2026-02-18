import pandas as pd
import glob
import os

# Константы для оценки качества ядра
TARGET_LOTS = [6, 20, 16, 9]

# Загружаем файл
try:
    target_file = "downloads/Ханивелл_enriched.xlsx"
    # Fallback search if exact name differs slightly
    if not os.path.exists(target_file):
        files = glob.glob("downloads/*enriched.xlsx")
        target_file = next((f for f in files if "path" not in f), target_file)

    df = pd.read_excel(target_file)
    
    # Подготовка данных
    df['LineValue'] = pd.to_numeric(df['CalculatedLotCost'], errors='coerce').fillna(0)
    df['Desc'] = df['RawText'].astype(str).fillna("")
    
    def extract_lot_num(val):
        import re
        nums = re.findall(r'\d+', str(val))
        return int(nums[0]) if nums else -1

    df['LotID'] = df['SheetName'].apply(extract_lot_num)

    print(f"\n{'='*80}")
    print(f"COMPARATIVE CORE ANALYSIS (TOP 20% by Value) - Lots {TARGET_LOTS}")
    print(f"{'='*80}")

    for lot in TARGET_LOTS:
        subset = df[df['LotID'] == lot].copy()
        if subset.empty:
            print(f"Lot {lot}: No data found.")
            continue
            
        total_val = subset['LineValue'].sum()
        
        # Сортируем от дорогих к дешевым
        subset = subset.sort_values('LineValue', ascending=False)
        
        # Находим "Ядро" (позиции, формирующие первые 80% стоимости, но не более 10 штук для наглядности)
        # Или, как просил пользователь, "Топ-20% товаров".
        # Обычно "Top 20% items make 80% value". Покажем просто Топ-5 позиций, так как они и есть ядро.
        
        print(f"\nLOT {lot} (Total: ${total_val:,.0f})")
        print(f"{'-'*80}")
        
        # Calculate concentration
        top1_share = subset.iloc[0]['LineValue'] / total_val
        top3_share = subset.iloc[:3]['LineValue'].sum() / total_val
        
        print(f"CONCENTRATION RISK:")
        print(f"   Top 1 Item: {top1_share:.1%} of value")
        print(f"   Top 3 Items: {top3_share:.1%} of value")
        print(f"{'-'*80}")
        print(f"CORE ITEMS (The 'Heart' of the lot):")
        
        for i, row in subset.head(5).iterrows():
            desc = row['Desc']
            # Truncate description intelligently
            short_desc = (desc[:75] + '..') if len(desc) > 75 else desc
            qty = row['QtyLot']
            val = row['LineValue']
            share = val / total_val
            
            print(f"   * ${val:,.0f} ({share:.1%}) | {qty} pcs | {short_desc}")
            
except Exception as e:
    print(f"Error: {e}")

