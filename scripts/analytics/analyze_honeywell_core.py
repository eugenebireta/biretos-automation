import pandas as pd
import glob
import os
import re

# --- CONFIG ---
TARGET_LOTS = [30, 17, 11, 22, 26]
BAD_KEYWORDS = ['mouse', 'keyboard', 'monitor', 'cable', 'cord', 'rack', 'cabinet', 'toner', 'cartridge', 'battery', 'mount', 'screw', 'manual']
GOOD_KEYWORDS = ['module', 'controller', 'sensor', 'detector', 'valve', 'actuator', 'transmitter', 'switch', 'plc', 'board', 'processor', 'scanner', 'interface']

# --- LOAD DATA ---
files = [f for f in glob.glob("downloads/*.xlsx") if not os.path.basename(f).startswith("~$")]
target_file = next((f for f in files if "enriched" in f and "path" not in f), "downloads/Ханивелл_enriched.xlsx")
print(f"Loading: {target_file}")

df = pd.read_excel(target_file)

# --- PREPROCESS ---
def extract_lot_num(val):
    try:
        # Handle "Lot 30", "30.0", 30
        s = str(val).lower()
        nums = re.findall(r'\d+', s)
        if nums:
            return int(nums[0])
        return -1
    except:
        return -1

df['LotID'] = df['SheetName'].apply(extract_lot_num)
df['LineValue'] = pd.to_numeric(df['CalculatedLotCost'], errors='coerce').fillna(0)
df['Desc'] = df['RawText'].astype(str).fillna("")

# --- ANALYZE FUNCTION ---
def analyze_lot(lot_id):
    subset = df[df['LotID'] == lot_id].copy()
    if subset.empty:
        return None

    total_value = subset['LineValue'].sum()
    subset = subset.sort_values('LineValue', ascending=False)
    
    top5 = subset.head(5)
    
    core_items = []
    junk_penalty = 0
    good_bonus = 0
    
    for _, row in top5.iterrows():
        desc = row['Desc'].lower()
        val = row['LineValue']
        share = val / total_value if total_value > 0 else 0
        
        is_junk = any(k in desc for k in BAD_KEYWORDS)
        is_good = any(k in desc for k in GOOD_KEYWORDS)
        
        if is_junk: junk_penalty += share * 100
        if is_good: good_bonus += share * 100
        
        core_items.append({
            'Description': row['Desc'][:60] + "..." if len(row['Desc'])>60 else row['Desc'],
            'Qty': row['QtyLot'],
            'Unit Price': row['PriceFound'],
            'Total Value': val,
            'Share': f"{share:.1%}",
            'Type': 'JUNK' if is_junk else ('CORE' if is_good else 'UNKNOWN')
        })
        
    return {
        'id': lot_id,
        'total_value': total_value,
        'top5_items': core_items,
        'junk_score': junk_penalty,
        'quality_score': good_bonus - junk_penalty
    }

# --- RUN FOR TARGET LOTS ---
print("\n" + "="*60)
print("DETAILED CORE ANALYSIS FOR REQUESTED LOTS")
print("="*60)

results = []
for lot_id in TARGET_LOTS:
    res = analyze_lot(lot_id)
    if res:
        results.append(res)
        print(f"\nLOT {lot_id} (Total Value: ${res['total_value']:,.0f})")
        print("-" * 80)
        print(f"{'Description':<65} | {'Qty':<5} | {'Total':<10} | {'Share':<6} | {'Type'}")
        print("-" * 80)
        for item in res['top5_items']:
            print(f"{item['Description']:<65} | {item['Qty']:<5} | ${item['Total Value']:<9,.0f} | {item['Share']:<6} | {item['Type']}")

# --- FIND GLOBAL TOP 5 ---
print("\n" + "="*60)
print("GLOBAL TOP 5 RECOMMENDATION (Based on Core Quality)")
print("="*60)

all_lots = df['LotID'].unique()
all_analyses = []
for lid in all_lots:
    if lid > 0:
        res = analyze_lot(lid)
        if res and res['total_value'] > 10000: # Ignore tiny lots
            all_analyses.append(res)

# Sort by Quality Score (descending), then Total Value
all_analyses.sort(key=lambda x: (x['quality_score'], x['total_value']), reverse=True)

print(f"{'Rank':<4} | {'Lot':<4} | {'Quality':<8} | {'Value':<12} | {'Top Item'}")
print("-" * 80)
for i, res in enumerate(all_analyses[:5], 1):
    top_item = res['top5_items'][0]['Description']
    print(f"#{i:<3} | {res['id']:<4} | {res['quality_score']:<8.1f} | ${res['total_value']:<11,.0f} | {top_item[:40]}")


