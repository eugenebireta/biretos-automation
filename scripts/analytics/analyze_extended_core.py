import pandas as pd
import glob
import os
import sys

# Force output encoding
sys.stdout.reconfigure(encoding='utf-8')

TARGET_LOTS = [14, 9, 16, 20, 6]

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
    print(f"EXTENDED CORE ANALYSIS (TOP 40% of Items by Count)")
    print(f"{'='*80}")

    for lot in TARGET_LOTS:
        subset = df[df['LotID'] == lot].copy()
        if subset.empty: continue
            
        total_val = subset['LineValue'].sum()
        subset = subset.sort_values('LineValue', ascending=False)
        
        # Calculate how many items constitute 40% of the count (rows)
        total_items_count = len(subset)
        top_40_pct_count = int(total_items_count * 0.40)
        
        # Take the top slice
        core_slice = subset.head(top_40_pct_count)
        core_val = core_slice['LineValue'].sum()
        core_share_val = core_val / total_val if total_val > 0 else 0
        
        print(f"\n📦 LOT {lot} (Total Val: ${total_val:,.0f} | Items: {total_items_count})")
        print(f"   Analyzing Top {top_40_pct_count} items (40% of positions)")
        print(f"   Value Covered: {core_share_val:.1%} of total lot price")
        print(f"{'-'*80}")
        
        # Display top items with a limit to avoid flooding console, but deep enough to see "tail" quality
        # We will show: Top 5 (Head), Middle 5 (Mid-Core), and Last 5 of this slice (Lower-Core)
        
        def print_rows(rows, label):
            if rows.empty: return
            print(f"   --- {label} ---")
            for _, row in rows.iterrows():
                desc = row['Desc'].replace('\n', ' ').strip()
                short_desc = (desc[:60] + '..') if len(desc) > 60 else desc
                val = row['LineValue']
                qty = row['QtyLot']
                print(f"   ${val:,.0f} | {qty:<4} | {short_desc}")

        print_rows(core_slice.head(5), "HEAD (Most Expensive)")
        
        if len(core_slice) > 10:
            mid_idx = len(core_slice) // 2
            print_rows(core_slice.iloc[mid_idx-2:mid_idx+3], "MID-CORE (Average Value)")
            
        if len(core_slice) > 20:
             print_rows(core_slice.tail(5), "TAIL of 40% (Cheaper Core)")

except Exception as e:
    print(f"Error: {e}")

