import pandas as pd
import glob
import os
import sys

# Force output encoding
sys.stdout.reconfigure(encoding='utf-8')

# Market Assumptions (Average Dealer Prices in USD)
REAL_PRICES = {
    # Lot 14
    'BWC4': 500,        # Gas Detector
    'CPO-RL4': 800,     # HVAC Controller
    '802371': 60,       # Smoke Detector (Optical)
    
    # Lot 16
    'IQ8FCT': 250,      # Transponder
    '808606': 250,      # Transponder
    
    # Lot 9
    'CPO-PC200': 2000,  # Plant Controller
    'SOCKET': 10,       # Relay Socket (Cheap)
    
    # Lot 6
    '40PC250G': 150,    # Pressure Sensor
    'THERMOSTAT': 50,   # Thermostat
    
    # Lot 26
    'LABEL': 0.05,      # Label (Cheap)
    'PCB': 100,         # Board
}

TARGET_LOTS = [14, 16, 9, 6, 26, 20]
USD_RATE = 80 # As requested

try:
    target_file = "downloads/Ханивелл_enriched.xlsx"
    if not os.path.exists(target_file):
        files = glob.glob("downloads/*enriched.xlsx")
        target_file = next((f for f in files if "path" not in f), target_file)

    df = pd.read_excel(target_file)
    # The 'CalculatedLotCost' is in RUBLES as per user correction
    df['LineValueRub'] = pd.to_numeric(df['CalculatedLotCost'], errors='coerce').fillna(0)
    df['Desc'] = df['RawText'].astype(str).fillna("")
    
    def extract_lot_num(val):
        import re
        nums = re.findall(r'\d+', str(val))
        return int(nums[0]) if nums else -1

    df['LotID'] = df['SheetName'].apply(extract_lot_num)

    print(f"\n{'='*80}")
    print(f"REALITY CHECK (Rubles to USD @ {USD_RATE})")
    print(f"{'='*80}")

    for lot in TARGET_LOTS:
        subset = df[df['LotID'] == lot].copy()
        if subset.empty: continue
        
        subset = subset.sort_values('LineValueRub', ascending=False)
        top_item = subset.iloc[0]
        
        # Calculate AI implied Unit Price in USD
        ai_total_rub = top_item['LineValueRub']
        qty = top_item['QtyLot']
        ai_unit_rub = ai_total_rub / qty if qty > 0 else 0
        ai_unit_usd = ai_unit_rub / USD_RATE
        
        # Try to match real price
        desc_upper = top_item['Desc'].upper()
        real_price = 0
        match_name = "Unknown"
        
        for k, p in REAL_PRICES.items():
            if k in desc_upper or k in top_item['SKU']:
                real_price = p
                match_name = k
                break
        
        # If no exact match, guess category
        if real_price == 0:
            if 'DETECTOR' in desc_upper: real_price = 100
            elif 'SENSOR' in desc_upper: real_price = 150
            elif 'CONTROLLER' in desc_upper: real_price = 1500
            elif 'LABEL' in desc_upper or 'ЭТИКЕТКА' in desc_upper: real_price = 0.1
        
        print(f"\n📦 LOT {lot}")
        print(f"   Top Item: {top_item['Desc'][:50]}...")
        print(f"   Qty: {qty}")
        print(f"   AI Value (RUB): {ai_total_rub:,.0f} RUB")
        print(f"   AI Unit Price: {ai_unit_rub:,.0f} RUB (~${ai_unit_usd:,.2f})")
        
        if real_price > 0:
            diff = ai_unit_usd / real_price
            status = "✅ FAIR" if 0.5 < diff < 2.0 else ("🚨 OVERPRICED" if diff > 2.0 else "💰 UNDERVALUED")
            print(f"   Real Market Price: ~${real_price}")
            print(f"   Verdict: {status} (x{diff:.1f} factor)")
        else:
            print(f"   Real Market Price: Unknown")

except Exception as e:
    print(f"Error: {e}")

