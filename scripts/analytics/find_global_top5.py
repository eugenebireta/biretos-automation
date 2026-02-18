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

    # 1. ANALYZE ALL LOTS to find TRUE TOP 5
    lot_stats = []
    unique_lots = df['LotID'].unique()
    
    for lot in unique_lots:
        if lot < 0: continue
        subset = df[df['LotID'] == lot]
        if subset.empty: continue
        
        total_val = subset['LineValue'].sum()
        if total_val < 1_000_000: continue # Skip tiny lots
        
        # Scoring logic: 
        # - High Total Value is good
        # - Low Concentration (Top 1 item share) is good
        # - "Good" keywords in Top 40% is good
        
        subset = subset.sort_values('LineValue', ascending=False)
        top_1_share = subset.iloc[0]['LineValue'] / total_val
        
        # Count "Core Quality" in Top 40%
        count_40pct = int(len(subset) * 0.40)
        core_slice = subset.head(count_40pct)
        
        good_keywords = ['detector', 'sensor', 'module', 'controller', 'valve', 'actuator', 'transponder', 'извещатель', 'датчик', 'fire', 'gas']
        bad_keywords = ['battery', 'cable', 'cord', 'mounting', 'kit', 'screw', 'manual', 'bracket', 'monitor', 'keyboard']
        
        quality_score = 0
        for d in core_slice['Desc']:
            d_lower = d.lower()
            if any(k in d_lower for k in good_keywords): quality_score += 1
            if any(k in d_lower for k in bad_keywords): quality_score -= 1
            
        # Normalize quality score by size of core
        norm_quality = quality_score / count_40pct if count_40pct > 0 else 0
        
        lot_stats.append({
            'id': lot,
            'val': total_val,
            'top1_share': top_1_share,
            'quality': norm_quality,
            'subset': subset # Keep data for printing
        })

    # Sort lots by a weighted formula: Value * Quality
    # Penalize lots with > 50% concentration
    lot_stats.sort(key=lambda x: (x['val'] * (0.5 if x['top1_share'] > 0.5 else 1.0) * (1 + x['quality'])), reverse=True)
    
    top_5_lots = lot_stats[:5]

    print(f"\n{'='*80}")
    print(f"GLOBAL TOP 5 LOTS (From all 33) - DEEP 40% CORE ANALYSIS")
    print(f"{'='*80}")

    for rank, lot_data in enumerate(top_5_lots, 1):
        lot_id = lot_data['id']
        subset = lot_data['subset']
        total_items = len(subset)
        count_40pct = int(total_items * 0.40)
        core_slice = subset.head(count_40pct)
        
        print(f"\n🏆 RANK #{rank}: LOT {lot_id}")
        print(f"   Total Value: ${lot_data['val']:,.0f}")
        print(f"   Items Analysis: Top {count_40pct} items (40% of {total_items})")
        print(f"{'-'*80}")
        
        # Show breakdown of the 40% core
        print("   --- HEAD (Top 3) ---")
        for _, row in core_slice.head(3).iterrows():
            print(f"   ${row['LineValue']:,.0f} | {row['Desc'][:70]}")
            
        print("\n   --- MID-CORE (Sample from middle of 40%) ---")
        if len(core_slice) > 10:
            mid = len(core_slice) // 2
            for _, row in core_slice.iloc[mid:mid+3].iterrows():
                print(f"   ${row['LineValue']:,.0f} | {row['Desc'][:70]}")
        
        print("\n   --- TAIL (Bottom of 40% Core) ---")
        if len(core_slice) > 5:
            for _, row in core_slice.tail(3).iterrows():
                print(f"   ${row['LineValue']:,.0f} | {row['Desc'][:70]}")

except Exception as e:
    print(f"Error: {e}")

