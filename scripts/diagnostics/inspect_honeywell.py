import pandas as pd
import os
import re

files = [
    "downloads/Honeywell_Final_Decision_Matrix.xlsx"
]

target_lots = ["30", "17", "11", "22", "26"]

for file_path in files:
    if not os.path.exists(file_path):
        print(f"File not found: {file_path}")
        continue

    print(f"\n--- Analyzing {file_path} ---")
    try:
        df = pd.read_excel(file_path)
        
        # Normalize SheetName to string and try to match lot number
        # Assuming SheetName might be "Lot 30" or just "30"
        
        for index, row in df.iterrows():
            sheet_name = str(row['SheetName'])
            # Extract number from SheetName
            match = re.search(r'(\d+)', sheet_name)
            if match:
                lot_num = match.group(1)
                if lot_num in target_lots:
                    print(f"\nLOT {lot_num} (Sheet: {sheet_name}):")
                    print(f"  Final Score: {row.get('FinalScore', 'N/A')}")
                    print(f"  Decision: {row.get('Decision', 'N/A')}")
                    print(f"  Total Value (est): {row.get('TOTAL_value', 'N/A')}")
                    print(f"  Residual Value (Scenario C - Conservative): {row.get('Residual_C_value', 'N/A')}")
                    print(f"  IT/Consumer Junk %: {row.get('IT_Consumer_pct', 'N/A')}")
                    print(f"  Problem %: {row.get('PROBLEM_pct', 'N/A')}")
                    print(f"  Battery %: {row.get('Battery_pct', 'N/A')}")
                    print(f"  Avg Value Per Unit: {row.get('AverageValuePerUnit', 'N/A')}")

    except Exception as e:
        print(f"Error reading {file_path}: {e}")
