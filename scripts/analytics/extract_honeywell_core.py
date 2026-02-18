import pandas as pd
import re

# Настройки
FILE_PATH = "downloads/Ханивелл_enriched.xlsx"
TARGET_LOTS = [17, 30]
CORE_THRESHOLD = 0.30  # 30% стоимости лота

def get_lot_id(val):
    try:
        s = str(val).lower()
        nums = re.findall(r'\d+', s)
        return int(nums[0]) if nums else -1
    except:
        return -1

def extract_core():
    print(f"Loading data from {FILE_PATH}...")
    try:
        df = pd.read_excel(FILE_PATH)
    except FileNotFoundError:
        # Fallback to alternative name if file not found
        df = pd.read_excel("downloads/Honeywell_enriched.xlsx")
    
    # Нормализация
    df['LotID'] = df['SheetName'].apply(get_lot_id)
    df['LineValue'] = pd.to_numeric(df['CalculatedLotCost'], errors='coerce').fillna(0)
    df['Desc'] = df['RawText'].astype(str).fillna("")
    
    for lot_id in TARGET_LOTS:
        print(f"\n{'='*20} LOT {lot_id} {'='*20}")
        subset = df[df['LotID'] == lot_id].copy()
        
        if subset.empty:
            print(f"Lot {lot_id} not found.")
            continue
            
        # Сортировка по убыванию стоимости
        subset = subset.sort_values('LineValue', ascending=False)
        
        # Расчет кумулятивной суммы
        total_value = subset['LineValue'].sum()
        subset['CumSum'] = subset['LineValue'].cumsum()
        subset['CumShare'] = subset['CumSum'] / total_value
        
        # Отбираем ядро (Top 30% value + buffer to include the item crossing the line)
        # We take items until CumShare > threshold, but include the one that crosses it.
        # Simple way: take head until CumShare > 0.35 roughly or top N items
        
        # Better approach: filter where CumShare - Share <= Threshold
        # But simply taking items until CumShare > 0.35 is safe to get >30%
        core_subset = subset[subset['CumShare'] <= (CORE_THRESHOLD + 0.15)] 
        
        # If core subset is too small (e.g. 1 huge item), take at least top 3
        if len(core_subset) < 3:
             core_subset = subset.head(3)

        print(f"Total Lot Value: ${total_value:,.2f}")
        print(f"Core Items: {len(core_subset)} of {len(subset)}")
        print("-" * 120)
        print(f"{'Description':<60} | {'Qty':<5} | {'Unit Price':<10} | {'Total':<10} | {'Share'}")
        print("-" * 120)
        
        for _, row in core_subset.iterrows():
            share = row['LineValue'] / total_value
            desc = row['Desc'].replace('\n', ' ')[:58]
            
            # Safely handle PriceFound
            try:
                price_val = float(row['PriceFound'])
                price_str = f"${price_val:<10.2f}"
            except:
                price_str = str(row['PriceFound'])[:10]

            print(f"{desc:<60} | {row['QtyLot']:<5} | {price_str:<11} | ${row['LineValue']:<10.2f} | {share:.1%}")

if __name__ == "__main__":
    extract_core()

