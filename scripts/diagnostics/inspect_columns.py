import pandas as pd

try:
    df = pd.read_excel("downloads/Ханивелл_enriched.xlsx")
    print("Columns:", df.columns.tolist())
    print("Sample row:")
    print(df.iloc[0])
except Exception as e:
    print(e)
