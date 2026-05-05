#!/usr/bin/env python
"""
Test script to verify the upload parsing fix works without the Streamlit app running.
"""
import io
import pandas as pd
from db import init_db, create_question_paper, add_question

# Initialize database
init_db()
print("✓ Database initialized")

# Test CSV parsing (simulating Streamlit upload)
csv_content = """question,a,b,c,d,answer
What is 2+2?,3,4,5,6,b
What is the capital of France?,London,Paris,Berlin,Madrid,b"""

file_like = io.BytesIO(csv_content.encode("utf-8"))
file_like.name = "questions.csv"
file_like.type = "text/csv"

print("\n✓ Simulating file upload...")
try:
    # This is the same parsing logic from app.py
    filename = str(file_like.name or "").lower()
    if file_like.type == "text/csv" or filename.endswith(".csv"):
        file_like.seek(0)
        df = pd.read_csv(
            file_like,
            encoding="utf-8",
            engine="python",
            quotechar='"',
            skipinitialspace=True,
            on_bad_lines="warn",
        )
    
    df.columns = df.columns.str.lower()
    required = ["question", "a", "b", "c", "d", "answer"]
    
    if not all(col in df.columns for col in required):
        print(f"✗ ERROR: Missing columns. Found: {list(df.columns)}")
    else:
        print(f"✓ CSV parsed successfully with {len(df)} questions")
        
        # Try to insert into database
        paper_id = create_question_paper(
            title="Test Paper",
            branch="CSE",
            semester=4,
            class_name="TY",
            schedule_date=None,
            duration_minutes=30
        )
        print(f"✓ Question paper created with ID: {paper_id}")
        
        # Add questions
        for idx, row in df.iterrows():
            add_question(
                paper_id,
                str(row.get("question", "")).strip(),
                str(row.get("a", "")).strip(),
                str(row.get("b", "")).strip(),
                str(row.get("c", "")).strip(),
                str(row.get("d", "")).strip(),
                str(row.get("answer", "")).strip(),
            )
            print(f"  ✓ Added question {idx + 1}")
        
        print(f"\n✓✓✓ SUCCESS! Upload parsing is working correctly! ✓✓✓")

except Exception as exc:
    print(f"✗ ERROR: Unable to parse upload: {exc}")
    import traceback
    traceback.print_exc()
