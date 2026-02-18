import pandas as pd
import os
import re

def analyze_lot_extended(df, lot_id, pct=0.5):
    # Filter for the specific lot
    lot_df = df[df['LotID'] == lot_id].copy()
    if lot_df.empty:
        return None
        
    # Sort by value descending
    lot_df = lot_df.sort_values(by='LineValueRub', ascending=False)
    
    # Calculate how many items constitute the top pct (by count of items)
    num_items = len(lot_df)
    top_n = max(1, int(num_items * pct))
    
    top_df = lot_df.head(top_n)
    
    results = []
    for _, row in top_df.iterrows():
        desc = str(row['Desc'])
        qty = row['QtyLot']
        total_rub = row['LineValueRub']
        unit_price_rub = total_rub / qty if qty > 0 else 0
        
        # Check for keywords indicating packs
        is_pack = any(kw in desc.lower() for kw in ['pack', 'упак', 'компл', 'kit', 'set', 'roll', 'рулон', 'уп.'])
        
        results.append({
            'SKU': row.get('SKU', 'N/A'),
            'Description': desc[:100] + ('...' if len(desc) > 100 else ''),
            'Qty': qty,
            'Unit Price (RUB)': unit_price_rub,
            'Total (RUB)': total_rub,
            'Is Pack?': 'YES' if is_pack else 'No'
        })
        
    return results, total_rub, lot_df['LineValueRub'].sum()

def main():
    file_path = "downloads/Ханивелл_enriched.xlsx"
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        return

    try:
        df = pd.read_excel(file_path)
        
        # Preprocessing as per previous steps
        df['LineValueRub'] = pd.to_numeric(df['CalculatedLotCost'], errors='coerce').fillna(0)
        df['Desc'] = df['RawText'].astype(str).fillna("")
        
        def extract_lot_num(val):
            nums = re.findall(r'\d+', str(val))
            return int(nums[0]) if nums else -1

        df['LotID'] = df['SheetName'].apply(extract_lot_num)
        
        target_lots = [14, 16]
        
        print(f"\n{'='*100}")
        print(f"DEEP DIVE: TOP 50% ITEMS ANALYSIS FOR LOTS 14 & 16 (Prices in RUB)")
        print(f"{'='*100}")
        
        for lot_id in target_lots:
            analysis, top_val, total_lot_val = analyze_lot_extended(df, lot_id, 0.5)
            if not analysis:
                print(f"Lot {lot_id} not found.")
                continue
                
            print(f"\nLOT {lot_id} | Total Value: {total_lot_val:,.2f} RUB | Top 50% Coverage: {len(analysis)} items")
            print("-" * 120)
            print(f"{'Description':<60} | {'Qty':<6} | {'Unit RUB':<12} | {'Total RUB':<15} | {'Pack?'}")
            print("-" * 120)
            
            for item in analysis[:20]: # Show top 20 for brevity
                print(f"{item['Description'][:60]:<60} | {item['Qty']:<6} | {item['Unit Price (RUB)']:<12,.0f} | {item['Total (RUB)']:<15,.0f} | {item['Is Pack?']}")
            
            if len(analysis) > 20:
                print(f"... and {len(analysis) - 20} more items in top 50%")

    except Exception as e:
        print(f"Error: {e}")

if __name__ == "__main__":
    main()

