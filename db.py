import os
import hashlib
import sqlite3
from datetime import datetime
from contextlib import contextmanager

DB_FILE = "online_test.db"

@contextmanager
def get_conn():
    conn = sqlite3.connect(DB_FILE)
    conn.row_factory = sqlite3.Row
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _single_value(row, key=None):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key) if key else next(iter(row.values()), None)
    try:
        if key is not None and isinstance(row, (list, tuple)):
            # fallback to first column if explicit key not available
            return row[0]
        return row[0]
    except Exception:
        return None


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def init_db():
    sql = [
        """
        CREATE TABLE IF NOT EXISTS admins (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS allowed_networks (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prefix TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS exam_settings (
            key TEXT PRIMARY KEY,
            value TEXT NOT NULL
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS students (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            prn TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            class TEXT NOT NULL,
            branch TEXT NOT NULL,
            semester INTEGER NOT NULL,
            password TEXT,
            active BOOLEAN DEFAULT 1,
            created_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS question_papers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            title TEXT NOT NULL,
            branch TEXT NOT NULL,
            semester INTEGER NOT NULL,
            class TEXT NOT NULL,
            schedule_date DATE,
            duration_minutes INTEGER DEFAULT 30,
            active BOOLEAN DEFAULT 1,
            uploaded_at TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS questions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            paper_id INTEGER NOT NULL,
            question TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            answer TEXT NOT NULL,
            FOREIGN KEY (paper_id) REFERENCES question_papers(id) ON DELETE CASCADE
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS test_sessions (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            student_id INTEGER REFERENCES students(id) ON DELETE CASCADE,
            paper_id INTEGER REFERENCES question_papers(id) ON DELETE CASCADE,
            started_at TIMESTAMP,
            completed_at TIMESTAMP,
            score INTEGER,
            max_score INTEGER,
            percentage REAL,
            warnings INTEGER DEFAULT 0,
            status TEXT,
            ip_address TEXT
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS answers (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            session_id INTEGER REFERENCES test_sessions(id) ON DELETE CASCADE,
            question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
            selected_option TEXT,
            correct BOOLEAN
        )
        """
    ]
    with get_conn() as conn:
        for statement in sql:
            conn.execute(statement)


def create_admin(username: str, password: str):
    hashed = hash_password(password)
    with get_conn() as conn:
        conn.execute(
            "INSERT OR IGNORE INTO admins (username, password) VALUES (?, ?)",
            (username, hashed),
        )


def authenticate_admin(username: str, password: str) -> bool:
    hashed = hash_password(password)
    with get_conn() as conn:
        row = conn.execute("SELECT password FROM admins WHERE username = ?", (username,)).fetchone()
        if not row:
            return False
        return row[0] == hashed


def get_admin_count() -> int:
    with get_conn() as conn:
        row = conn.execute("SELECT COUNT(*) FROM admins").fetchone()
        count = row[0] if row else 0
        return int(count) if count is not None else 0


def add_allowed_network(prefix: str, description: str = None):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO allowed_networks (prefix, description) VALUES (?, ?)",
            (prefix, description),
        )


def list_allowed_networks():
    with get_conn() as conn:
        rows = conn.execute("SELECT prefix, description, created_at FROM allowed_networks ORDER BY id").fetchall()
        return [dict(row) for row in rows]


def set_exam_setting(key: str, value: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT OR REPLACE INTO exam_settings (key, value) VALUES (?, ?)",
            (key, value),
        )


def get_exam_setting(key: str, default=None):
    with get_conn() as conn:
        row = conn.execute("SELECT value FROM exam_settings WHERE key=?", (key,)).fetchone()
        value = row[0] if row else None
        return value if value is not None else default


def upsert_student(prn: str, name: str, class_name: str, branch: str, semester: int, password: str = None):
    hashed = hash_password(password) if password else None
    with get_conn() as conn:
        conn.execute(
            """
            INSERT INTO students (prn, name, class, branch, semester, password) VALUES (?, ?, ?, ?, ?, ?)
            ON CONFLICT(prn) DO UPDATE SET name=excluded.name, class=excluded.class, branch=excluded.branch, semester=excluded.semester, password=COALESCE(excluded.password, students.password)
            """,
            (prn, name, class_name, branch, semester, hashed),
        )


def get_student(prn: str):
    with get_conn() as conn:
        row = conn.execute("SELECT * FROM students WHERE prn = ?", (prn,)).fetchone()
        return dict(row) if row else None


def set_student_password(prn: str, password: str):
    hashed = hash_password(password)
    with get_conn() as conn:
        conn.execute("UPDATE students SET password=? WHERE prn=?", (hashed, prn))


def create_question_paper(title: str, branch: str, semester: int, class_name: str, schedule_date=None, duration_minutes=30):
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO question_papers (title, branch, semester, class, schedule_date, duration_minutes) VALUES (?, ?, ?, ?, ?, ?)",
            (title, branch, semester, class_name, schedule_date, duration_minutes),
        )
        paper_id = cursor.lastrowid
    return paper_id


def add_question(paper_id: int, question: str, option_a: str, option_b: str, option_c: str, option_d: str, answer: str):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO questions (paper_id, question, option_a, option_b, option_c, option_d, answer) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (paper_id, question, option_a, option_b, option_c, option_d, answer),
        )


def list_question_papers(branch: str = None, semester: int = None, class_name: str = None):
    conditions = []
    params = []
    if branch:
        conditions.append("branch = ?")
        params.append(branch)
    if semester:
        conditions.append("semester = ?")
        params.append(semester)
    if class_name:
        conditions.append("class = ?")
        params.append(class_name)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    with get_conn() as conn:
        rows = conn.execute(f"SELECT * FROM question_papers {where} ORDER BY uploaded_at DESC", tuple(params)).fetchall()
        return [dict(row) for row in rows]


def get_questions_for_paper(paper_id: int):
    with get_conn() as conn:
        rows = conn.execute("SELECT * FROM questions WHERE paper_id = ? ORDER BY id", (paper_id,)).fetchall()
        return [dict(row) for row in rows]


def create_test_session(student_id: int, paper_id: int, ip_address: str):
    with get_conn() as conn:
        cursor = conn.execute(
            "INSERT INTO test_sessions (student_id, paper_id, started_at, status, ip_address) VALUES (?, ?, CURRENT_TIMESTAMP, ?, ?)",
            (student_id, paper_id, "in_progress", ip_address),
        )
        session_id = cursor.lastrowid
    return session_id


def submit_test_session(session_id: int, score: int, max_score: int, percentage: float, warnings: int):
    with get_conn() as conn:
        conn.execute(
            "UPDATE test_sessions SET completed_at = CURRENT_TIMESTAMP, score = ?, max_score = ?, percentage = ?, warnings = ?, status = ? WHERE id = ?",
            (score, max_score, percentage, warnings, "completed", session_id),
        )


def save_answer(session_id: int, question_id: int, selected_option: str, correct: bool):
    with get_conn() as conn:
        conn.execute(
            "INSERT INTO answers (session_id, question_id, selected_option, correct) VALUES (?, ?, ?, ?)",
            (session_id, question_id, selected_option, correct),
        )


def list_test_results(branch: str = None, class_name: str = None):
    conditions = ["status = 'completed'"]
    params = []
    if branch:
        conditions.append("students.branch = ?")
        params.append(branch)
    if class_name:
        conditions.append("students.class = ?")
        params.append(class_name)
    where = " AND ".join(conditions)
    with get_conn() as conn:
        rows = conn.execute(
            f"SELECT ts.*, students.prn, students.name, students.branch, students.class, students.semester, qp.title AS paper_title "
            f"FROM test_sessions ts "
            f"JOIN students ON ts.student_id = students.id "
            f"JOIN question_papers qp ON ts.paper_id = qp.id "
            f"WHERE {where} ORDER BY ts.completed_at DESC",
            tuple(params),
        ).fetchall()
        return [dict(row) for row in rows]
