import pandas as pd
import glob
import os
import sys

# Force output encoding
sys.stdout.reconfigure(encoding='utf-8')

TARGET_LOTS = [6, 20, 16, 9]

try:
    target_file = "downloads/Ханивелл_enriched.xlsx"
    if not os.path.exists(target_file):
        files = glob.glob("downloads/*enriched.xlsx")
        target_file = next((f for f in files if "path" not in f), target_file)

    df = pd.read_excel(target_file)
    df['LineValue'] = pd.to_numeric(df['CalculatedLotCost'], errors='coerce').fillna(0)
    df['Desc'] = df['RawText'].astype(str).fillna("")
    
    def extract_lot_num(val):
        import re
        nums = re.findall(r'\d+', str(val))
        return int(nums[0]) if nums else -1

    df['LotID'] = df['SheetName'].apply(extract_lot_num)

    print(f"\n{'='*80}")
    print(f"COMPARATIVE CORE ANALYSIS (TOP 20% by Value)")
    print(f"{'='*80}")

    for lot in TARGET_LOTS:
        subset = df[df['LotID'] == lot].copy()
        if subset.empty: continue
            
        total_val = subset['LineValue'].sum()
        subset = subset.sort_values('LineValue', ascending=False)
        
        top1_share = subset.iloc[0]['LineValue'] / total_val
        top3_share = subset.iloc[:3]['LineValue'].sum() / total_val
        
        print(f"\nLOT {lot} (Total: ${total_val:,.0f})")
        print(f"Risk Profile: Top1={top1_share:.1%}, Top3={top3_share:.1%}")
        print(f"{'-'*80}")
        
        for i, row in subset.head(5).iterrows():
            desc = row['Desc'].replace('\n', ' ').strip()
            # Clean up potential garbage chars if needed, but utf-8 stdout should handle it
            short_desc = (desc[:60] + '..') if len(desc) > 60 else desc
            print(f"   * ${row['LineValue']:,.0f} | {row['QtyLot']:<5} | {short_desc}")

except Exception as e:
    print(f"Error: {e}")

