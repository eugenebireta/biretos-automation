import pandas as pd
import glob
import os

TARGET_LOTS = [20, 6, 14, 16, 9]

# Use the same loading logic
files = [f for f in glob.glob("downloads/*.xlsx") if not os.path.basename(f).startswith("~$")]
target_file = next((f for f in files if "enriched" in f and "path" not in f), "downloads/Ханивелл_enriched.xlsx")
df = pd.read_excel(target_file)
df['LineValue'] = pd.to_numeric(df['CalculatedLotCost'], errors='coerce').fillna(0)
df['Desc'] = df['RawText'].astype(str).fillna("")

# Simple extraction of Lot ID
def extract_lot_num(val):
    import re
    nums = re.findall(r'\d+', str(val))
    return int(nums[0]) if nums else -1

df['LotID'] = df['SheetName'].apply(extract_lot_num)

print(f"CHECKING MY TOP 5 RECOMMENDATIONS from {target_file}")
for lot in TARGET_LOTS:
    subset = df[df['LotID'] == lot].sort_values('LineValue', ascending=False).head(3)
    print(f"\n--- LOT {lot} TOP ITEMS ---")
    for _, row in subset.iterrows():
        print(f"${row['LineValue']:,.0f} | {row['Desc'][:80]}")

