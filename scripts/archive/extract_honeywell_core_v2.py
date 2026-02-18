import pandas as pd
import re
import sys

# Force UTF-8 for stdout if needed, but file output is safer
sys.stdout.reconfigure(encoding='utf-8')

FILE_PATH = "downloads/Ханивелл_enriched.xlsx"
TARGET_LOTS = [17, 30]
CORE_THRESHOLD = 0.30

def get_lot_id(val):
    try:
        s = str(val).lower()
        nums = re.findall(r'\d+', s)
        return int(nums[0]) if nums else -1
    except:
        return -1

def extract_core():
    output_lines = []
    
    try:
        df = pd.read_excel(FILE_PATH)
    except FileNotFoundError:
        df = pd.read_excel("downloads/Honeywell_enriched.xlsx")
    
    df['LotID'] = df['SheetName'].apply(get_lot_id)
    df['LineValue'] = pd.to_numeric(df['CalculatedLotCost'], errors='coerce').fillna(0)
    df['UnitPrice'] = pd.to_numeric(df['UnitPriceRef'], errors='coerce').fillna(0)
    df['Desc'] = df['RawText'].astype(str).fillna("")
    df['SKU'] = df['SKU'].astype(str).fillna("")
    
    for lot_id in TARGET_LOTS:
        output_lines.append(f"\n{'='*20} LOT {lot_id} {'='*20}")
        subset = df[df['LotID'] == lot_id].copy()
        
        if subset.empty:
            output_lines.append(f"Lot {lot_id} not found.")
            continue
            
        subset = subset.sort_values('LineValue', ascending=False)
        total_value = subset['LineValue'].sum()
        subset['CumSum'] = subset['LineValue'].cumsum()
        subset['CumShare'] = subset['CumSum'] / total_value
        
        # Core selection logic: take items until we cross ~30-40%
        core_subset = subset[subset['CumShare'] <= (CORE_THRESHOLD + 0.15)]
        if len(core_subset) < 3:
             core_subset = subset.head(3)

        output_lines.append(f"Total Lot Value: {total_value:,.2f}")
        output_lines.append(f"Core Items: {len(core_subset)} of {len(subset)}")
        output_lines.append("-" * 140)
        output_lines.append(f"{'SKU':<20} | {'Description':<60} | {'Qty':<5} | {'Unit Price':<10} | {'Total':<10} | {'Share'}")
        output_lines.append("-" * 140)
        
        for _, row in core_subset.iterrows():
            share = row['LineValue'] / total_value
            desc = row['Desc'].replace('\n', ' ')[:58]
            sku = row['SKU'][:18]
            output_lines.append(f"{sku:<20} | {desc:<60} | {row['QtyLot']:<5} | {row['UnitPrice']:<10.2f} | {row['LineValue']:<10.2f} | {share:.1%}")

    # Write to file
    with open("core_analysis_input.txt", "w", encoding="utf-8") as f:
        f.write("\n".join(output_lines))
    print("Analysis written to core_analysis_input.txt")

if __name__ == "__main__":
    extract_core()

