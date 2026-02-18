import pandas as pd
import glob
import os
import sys

# Force output encoding
sys.stdout.reconfigure(encoding='utf-8')

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

    # Lots already analyzed in detail: 16, 14, 6, 9, 20
    # Also touched: 30, 26, 3
    # Let's group all remaining significant lots (> $1M value)
    
    analyzed_lots = [16, 14, 6, 9, 20]
    
    print(f"\n{'='*80}")
    print(f"CORE ANALYSIS OF REMAINING LOTS (Top 3 items per lot)")
    print(f"{'='*80}")

    unique_lots = sorted(df['LotID'].unique())
    
    for lot in unique_lots:
        if lot < 0 or lot in analyzed_lots: continue
        
        subset = df[df['LotID'] == lot].copy()
        total_val = subset['LineValue'].sum()
        if total_val < 1_000_000: continue # Skip small lots
        
        subset = subset.sort_values('LineValue', ascending=False)
        
        print(f"\n📦 LOT {lot} (Total: ${total_val:,.0f})")
        print(f"{'-'*60}")
        
        for i, row in subset.head(3).iterrows():
            desc = row['Desc'].replace('\n', ' ').strip()
            short_desc = (desc[:60] + '..') if len(desc) > 60 else desc
            share = row['LineValue'] / total_val
            print(f"   ${row['LineValue']:,.0f} ({share:.1%}) | {short_desc}")

except Exception as e:
    print(f"Error: {e}")

