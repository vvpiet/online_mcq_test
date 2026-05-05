import io
import pandas as pd

# Simulate a Streamlit file upload by creating a BytesIO object
csv_data = """question,a,b,c,d,answer
What is the unit of electric current?,Volt,Ampere,Ohm,Watt,b
Which language is primarily used for data analysis and visualization?,Python,HTML,CSS,SQL,a"""

file = io.BytesIO(csv_data.encode("utf-8"))
file.name = "test.csv"
file.type = "text/csv"

# Test the parsing logic (same as in app.py)
try:
    filename = str(file.name or "").lower()
    if file.type == "text/csv" or filename.endswith(".csv"):
        file.seek(0)
        df = pd.read_csv(
            file,
            encoding="utf-8",
            engine="python",
            quotechar='"',
            skipinitialspace=True,
            on_bad_lines="warn",
        )
    
    df.columns = df.columns.str.lower()
    required = ["question", "a", "b", "c", "d", "answer"]
    if not all(col in df.columns.str.lower() for col in required):
        print("ERROR: Missing columns")
    else:
        print("SUCCESS: CSV parsed correctly!")
        print(f"Loaded {len(df)} questions")
        print(df)
except Exception as exc:
    print(f"ERROR: Unable to parse upload: {exc}")
