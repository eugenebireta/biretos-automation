import pandas as pd
import glob
import os
import sys
import re

# Force output encoding to avoid character map errors
sys.stdout.reconfigure(encoding='utf-8')

TARGET_LOTS = [14, 16]
USD_RATE = 80

# Market benchmarks (rough dealer prices in USD)
BENCHMARKS = {
    'BWC4': 500,
    'CPO-RL4': 800,
    '802371': 60,
    'IQ8FCT': 250,
    '808606': 250,
    'VR420': 1000,
    'ML6421': 400,
    'TPPR': 1200,
}

def analyze():
    target_file = "downloads/Ханивелл_enriched.xlsx"
    df = pd.read_excel(target_file)
    df['LineValueRub'] = pd.to_numeric(df['CalculatedLotCost'], errors='coerce').fillna(0)
    df['Desc'] = df['RawText'].astype(str).fillna("")
    
    def extract_lot_num(val):
        nums = re.findall(r'\d+', str(val))
        return int(nums[0]) if nums else -1

    df['LotID'] = df['SheetName'].apply(extract_lot_num)

    print("\n" + "="*100)
    print("DETAILED CORE ANALYSIS (TOP 50% OF ITEMS) FOR LOTS 14 AND 16")
    print("="*100)

    for lot_id in TARGET_LOTS:
        subset = df[df['LotID'] == lot_id].copy()
        total_lot_val = subset['LineValueRub'].sum()
        subset = subset.sort_values(by='LineValueRub', ascending=False)
        
        n_50pct = max(1, int(len(subset) * 0.5))
        core = subset.head(n_50pct)
        core_val = core['LineValueRub'].sum()
        
        print(f"\n📦 LOT {lot_id} | TOTAL: {total_lot_val:,.0f} RUB | CORE (Top 50%): {core_val:,.0f} RUB ({core_val/total_lot_val:.1%})")
        print("-" * 100)
        
        # Breakdown by category
        categories = {
            'Gas Safety': 0,
            'Fire Safety': 0,
            'HVAC/Automation': 0,
            'Valves/Actuators': 0,
            'IT/Hardware': 0,
            'Other': 0
        }
        
        for _, row in core.iterrows():
            d = row['Desc'].lower()
            val = row['LineValueRub']
            if any(x in d for x in ['gas', 'bwc4', 'lel', 'h2s', 'co', 'xnx']): categories['Gas Safety'] += val
            elif any(x in d for x in ['smoke', 'optical', 'fire', 'извещатель', 'esser', '802371', 'iq8']): categories['Fire Safety'] += val
            elif any(x in d for x in ['controller', 'bacnet', 'cpo', 'hvac', 'module']): categories['HVAC/Automation'] += val
            elif any(x in d for x in ['valve', 'actuator', 'клапан', 'привод']): categories['Valves/Actuators'] += val
            elif any(x in d for x in ['wks', 'pc', 'dell', 'hp', 'raid', 'rack']): categories['IT/Hardware'] += val
            else: categories['Other'] += val
            
        print("CORE CATEGORY BREAKDOWN:")
        for cat, val in sorted(categories.items(), key=lambda x: x[1], reverse=True):
            if val > 0:
                print(f"   * {cat:<20}: {val:,.0f} RUB ({val/core_val:.1%})")
        
        print("\nTOP ITEMS IN THIS CORE (Sample):")
        for _, row in core.head(10).iterrows():
            qty = row['QtyLot']
            unit_rub = row['LineValueRub'] / qty if qty > 0 else 0
            unit_usd = unit_rub / USD_RATE
            desc = row['Desc'].replace('\n', ' ').strip()
            
            # Simple benchmark check
            bm = 0
            for k, v in BENCHMARKS.items():
                if k in desc.upper():
                    bm = v
                    break
            
            status = ""
            if bm > 0:
                ratio = unit_usd / bm
                if ratio > 2: status = "🚨 OVER"
                elif ratio < 0.5: status = "💰 UNDER"
                else: status = "✅ FAIR"
            
            print(f"   ${unit_usd:,.0f}/pc | Qty:{qty:<5} | {status:<8} | {desc[:60]}...")

if __name__ == "__main__":
    analyze()

