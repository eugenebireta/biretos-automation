import pandas as pd
import glob
import os

# Find proper files, excluding temps
files = [f for f in glob.glob("downloads/*.xlsx") if not os.path.basename(f).startswith("~$")]

# Prioritize the one containing "enriched" but not "path"
target_file = None
for f in files:
    if "enriched" in f and "path" not in f:
        target_file = f
        break

if not target_file:
    # Try looking for just "Ханивелл.xlsx"
    for f in files:
        if "Ханивелл.xlsx" in f:
            target_file = f
            break

if not target_file:
    # Manual fallback
    target_file = "downloads/Ханивелл_enriched.xlsx"

print(f"Selected file: {target_file}")

try:
    df = pd.read_excel(target_file)
    # Print columns nicely
    cols = df.columns.tolist()
    print("Columns found:")
    for i, c in enumerate(cols):
        print(f"{i}: {c}")
    
    # Try to identify Lot column
    lot_col = next((c for c in cols if 'lot' in str(c).lower() or 'лот' in str(c).lower()), None)
    if lot_col:
        print(f"\nUnique Lots: {df[lot_col].unique()[:10]} ...")

except Exception as e:
    print(f"Error: {e}")

