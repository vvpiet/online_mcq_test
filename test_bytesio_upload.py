#!/usr/bin/env python
"""
Test the upload parsing with BytesIO (mimicking Streamlit UploadedFile behavior)
"""
import io
import pandas as pd
from db import init_db, create_question_paper, add_question
import traceback

# Initialize database
init_db()
print("✓ Database initialized")

# Test with BytesIO (exactly how Streamlit UploadedFile works)
csv_content = """question,a,b,c,d,answer
What is 2+2?,3,4,5,6,b
What is the capital of France?,London,Paris,Berlin,Madrid,b"""

# Create a BytesIO object simulating Streamlit's UploadedFile
class MockUploadedFile:
    def __init__(self, content, name, file_type):
        self.content = content
        self.name = name
        self.type = file_type
        self._buffer = io.BytesIO(content.encode("utf-8"))
    
    def read(self):
        return self._buffer.getvalue()
    
    def seek(self, pos):
        return self._buffer.seek(pos)

file = MockUploadedFile(csv_content, "questions.csv", "text/csv")

print("\n✓ Simulating Streamlit file upload...")
try:
    # This is the EXACT parsing logic from the updated app.py
    file_bytes = file.read()
    file.seek(0)
    
    filename = str(file.name or "").lower()
    
    if file.type == "text/csv" or filename.endswith(".csv"):
        df = pd.read_csv(
            io.BytesIO(file_bytes),
            encoding="utf-8",
            engine="python",
            quotechar='"',
            skipinitialspace=True,
            on_bad_lines="warn",
        )
    elif filename.endswith((".xls", ".xlsx")):
        df = pd.read_excel(io.BytesIO(file_bytes))
    else:
        try:
            df = pd.read_csv(
                io.BytesIO(file_bytes),
                encoding="utf-8",
                engine="python",
                quotechar='"',
                skipinitialspace=True,
                on_bad_lines="warn",
            )
        except Exception:
            df = pd.read_excel(io.BytesIO(file_bytes))
    
    df.columns = df.columns.str.lower()
    required = ["question", "a", "b", "c", "d", "answer"]
    
    if not all(col in df.columns for col in required):
        print(f"✗ ERROR: Missing columns. Found: {list(df.columns)}")
    else:
        print(f"✓ CSV parsed successfully with {len(df)} questions")
        
        # Try to insert into database
        paper_id = create_question_paper(
            title="Test Paper BytesIO",
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
                str(row["question"]).strip() if "question" in row.index else "",
                str(row["a"]).strip() if "a" in row.index else "",
                str(row["b"]).strip() if "b" in row.index else "",
                str(row["c"]).strip() if "c" in row.index else "",
                str(row["d"]).strip() if "d" in row.index else "",
                str(row["answer"]).strip() if "answer" in row.index else "",
            )
            print(f"  ✓ Added question {idx + 1}")
        
        print(f"\n✓✓✓ SUCCESS! Upload parsing with BytesIO is working! ✓✓✓")

except Exception as exc:
    print(f"✗ ERROR: Unable to parse upload: {str(exc)}")
    print(f"\nFull traceback:\n{traceback.format_exc()}")
