import pandas as pd
import glob
import os
import sys
from collections import Counter

# Force output encoding
sys.stdout.reconfigure(encoding='utf-8')

TARGET_LOTS = [16, 14]

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
    
    # Helper to categorize items
    def categorize(desc):
        d = desc.lower()
        if any(x in d for x in ['smoke', 'optical', 'heat', 'detector', 'извещатель', 'fire']): return '🔥 Fire Detectors'
        if any(x in d for x in ['transponder', 'module', 'input', 'output', 'транспондер', 'io']): return '🎛️ Modules/IO'
        if any(x in d for x in ['valve', 'actuator', 'клапан', 'привод']): return '🚰 Valves/Actuators'
        if any(x in d for x in ['gas', 'bwc4', 'lel', 'h2s', 'co', 'газоанализатор']): return '⚠️ Gas Safety'
        if any(x in d for x in ['power', 'psu', 'supply', 'battery']): return '⚡ Power'
        if any(x in d for x in ['controller', 'plc', 'facp', 'panel']): return '🧠 Controllers'
        if any(x in d for x in ['camera', 'nvr', 'dome', 'lens']): return '📹 CCTV'
        if any(x in d for x in ['base', 'mount', 'bracket', 'cover', 'socket', 'база']): return '🔧 Accessories/Mounts'
        return '📦 Other'

    print(f"\n{'='*80}")
    print(f"DEEP CATEGORY ANALYSIS (TOP 40% vs TOP 70%)")
    print(f"{'='*80}")

    for lot in TARGET_LOTS:
        subset = df[df['LotID'] == lot].copy()
        if subset.empty: continue
            
        total_val = subset['LineValue'].sum()
        subset = subset.sort_values('LineValue', ascending=False)
        total_items = len(subset)
        
        for pct in [0.40, 0.70]:
            count = int(total_items * pct)
            slice_data = subset.head(count)
            slice_val = slice_data['LineValue'].sum()
            
            # Analyze types
            categories = [categorize(r['Desc']) for _, r in slice_data.iterrows()]
            cat_counts = Counter(categories)
            
            # Calculate value per category
            cat_values = {}
            for _, r in slice_data.iterrows():
                cat = categorize(r['Desc'])
                cat_values[cat] = cat_values.get(cat, 0) + r['LineValue']
            
            print(f"\n📦 LOT {lot} - TOP {pct:.0%} of Items ({count} positions)")
            print(f"   Value Covered: {slice_val/total_val:.1%} of Total")
            print(f"{'-'*80}")
            print(f"   {'CATEGORY':<25} | {'COUNT':<5} | {'VALUE ($)':<12} | {'SHARE'}")
            print(f"   {'-'*25}-|-{'-'*5}-|-{'-'*12}-|-{'-'*5}")
            
            sorted_cats = sorted(cat_values.items(), key=lambda x: x[1], reverse=True)
            for cat, val in sorted_cats:
                count_in_cat = cat_counts[cat]
                share = val / slice_val
                print(f"   {cat:<25} | {count_in_cat:<5} | ${val:,.0f}    | {share:.1%}")

except Exception as e:
    print(f"Error: {e}")

