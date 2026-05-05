import os
import hashlib
import psycopg2
from psycopg2.extras import RealDictCursor
from datetime import datetime
from contextlib import contextmanager

# Use Neon/PostgreSQL database
DATABASE_URL = os.getenv("DATABASE_URL", "postgresql://user:password@localhost/online_mcq")

@contextmanager
def get_conn():
    conn = psycopg2.connect(DATABASE_URL)
    try:
        yield conn
        conn.commit()
    except Exception:
        conn.rollback()
        raise
    finally:
        conn.close()


def _dict_from_row(cursor, row):
    """Convert database row to dict"""
    if row is None:
        return None
    cols = [desc[0] for desc in cursor.description]
    return dict(zip(cols, row))


def _single_value(row, key=None):
    if row is None:
        return None
    if isinstance(row, dict):
        return row.get(key) if key else next(iter(row.values()), None)
    try:
        if key is not None and isinstance(row, (list, tuple)):
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
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS allowed_networks (
            id SERIAL PRIMARY KEY,
            prefix TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT now()
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
            id SERIAL PRIMARY KEY,
            prn TEXT UNIQUE NOT NULL,
            name TEXT NOT NULL,
            class TEXT NOT NULL,
            branch TEXT NOT NULL,
            semester INTEGER NOT NULL,
            password TEXT,
            active BOOLEAN DEFAULT true,
            created_at TIMESTAMP DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS question_papers (
            id SERIAL PRIMARY KEY,
            title TEXT NOT NULL,
            branch TEXT NOT NULL,
            semester INTEGER NOT NULL,
            class TEXT NOT NULL,
            schedule_date DATE,
            duration_minutes INTEGER DEFAULT 30,
            active BOOLEAN DEFAULT true,
            uploaded_at TIMESTAMP DEFAULT now()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
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
            id SERIAL PRIMARY KEY,
            session_id INTEGER REFERENCES test_sessions(id) ON DELETE CASCADE,
            question_id INTEGER REFERENCES questions(id) ON DELETE CASCADE,
            selected_option TEXT,
            correct BOOLEAN
        )
        """
    ]
    with get_conn() as conn:
        cursor = conn.cursor()
        for statement in sql:
            try:
                cursor.execute(statement)
            except Exception as e:
                print(f"Table creation note: {e}")
        cursor.close()


def create_admin(username: str, password: str):
    hashed = hash_password(password)
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO admins (username, password) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING",
            (username, hashed),
        )
        cursor.close()


def authenticate_admin(username: str, password: str) -> bool:
    hashed = hash_password(password)
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT password FROM admins WHERE username = %s", (username,))
        row = cursor.fetchone()
        cursor.close()
        if not row:
            return False
        return row[0] == hashed


def get_admin_count() -> int:
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT COUNT(*) FROM admins")
        row = cursor.fetchone()
        cursor.close()
        count = row[0] if row else 0
        return int(count) if count is not None else 0


def add_allowed_network(prefix: str, description: str = None):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO allowed_networks (prefix, description) VALUES (%s, %s) ON CONFLICT (prefix) DO UPDATE SET description = %s",
            (prefix, description, description),
        )
        cursor.close()


def list_allowed_networks():
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT prefix, description, created_at FROM allowed_networks ORDER BY id")
        rows = cursor.fetchall()
        cursor.close()
        return [dict(row) for row in rows]


def set_exam_setting(key: str, value: str):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO exam_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = %s",
            (key, value, value),
        )
        cursor.close()


def get_exam_setting(key: str, default=None):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("SELECT value FROM exam_settings WHERE key=%s", (key,))
        row = cursor.fetchone()
        cursor.close()
        value = row[0] if row else None
        return value if value is not None else default


def upsert_student(prn: str, name: str, class_name: str, branch: str, semester: int, password: str = None):
    hashed = hash_password(password) if password else None
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            """
            INSERT INTO students (prn, name, class, branch, semester, password) VALUES (%s, %s, %s, %s, %s, %s)
            ON CONFLICT (prn) DO UPDATE SET name=excluded.name, class=excluded.class, branch=excluded.branch, semester=excluded.semester, password=COALESCE(excluded.password, students.password)
            """,
            (prn, name, class_name, branch, semester, hashed),
        )
        cursor.close()


def get_student(prn: str):
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute("SELECT * FROM students WHERE prn = %s", (prn,))
        row = cursor.fetchone()
        cursor.close()
        return dict(row) if row else None


def set_student_password(prn: str, password: str):
    hashed = hash_password(password)
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute("UPDATE students SET password=%s WHERE prn=%s", (hashed, prn))
        cursor.close()


def create_question_paper(title: str, branch: str, semester: int, class_name: str, schedule_date=None, duration_minutes=30):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO question_papers (title, branch, semester, class, schedule_date, duration_minutes) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
            (title, branch, semester, class_name, schedule_date, duration_minutes),
        )
        paper_id = cursor.fetchone()[0]
        cursor.close()
    return paper_id


def add_question(paper_id: int, question: str, option_a: str, option_b: str, option_c: str, option_d: str, answer: str):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO questions (paper_id, question, option_a, option_b, option_c, option_d, answer) VALUES (%s, %s, %s, %s, %s, %s, %s)",
            (paper_id, question, option_a, option_b, option_c, option_d, answer),
        )
        cursor.close()


def list_question_papers(branch: str = None, semester: int = None, class_name: str = None):
    conditions = []
    params = []
    if branch:
        conditions.append("branch = %s")
        params.append(branch)
    if semester:
        conditions.append("semester = %s")
        params.append(semester)
    if class_name:
        conditions.append("class = %s")
        params.append(class_name)
    where = "WHERE " + " AND ".join(conditions) if conditions else ""
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(f"SELECT * FROM question_papers {where} ORDER BY uploaded_at DESC", tuple(params))
        rows = cursor.fetchall()
        cursor.close()
        return [dict(row) for row in rows]


def get_questions_for_paper(paper_id: int, hide_answers: bool = True):
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        if hide_answers:
            cursor.execute(
                "SELECT id, paper_id, question, option_a, option_b, option_c, option_d FROM questions WHERE paper_id = %s ORDER BY id", 
                (paper_id,)
            )
        else:
            cursor.execute(
                "SELECT * FROM questions WHERE paper_id = %s ORDER BY id", 
                (paper_id,)
            )
        rows = cursor.fetchall()
        cursor.close()
        return [dict(row) for row in rows]


def create_test_session(student_id: int, paper_id: int, ip_address: str):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO test_sessions (student_id, paper_id, started_at, ip_address, status) VALUES (%s, %s, %s, %s, %s) RETURNING id",
            (student_id, paper_id, datetime.now(), ip_address, "started"),
        )
        session_id = cursor.fetchone()[0]
        cursor.close()
    return session_id


def save_answer(session_id: int, question_id: int, selected_option: str, correct: bool = None):
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "INSERT INTO answers (session_id, question_id, selected_option, correct) VALUES (%s, %s, %s, %s)",
            (session_id, question_id, selected_option, correct),
        )
        cursor.close()


def submit_test_session(session_id: int, score: int, max_score: int, percentage: float = None, warnings: int = 0):
    if percentage is None:
        percentage = (score / max_score * 100) if max_score > 0 else 0
    with get_conn() as conn:
        cursor = conn.cursor()
        cursor.execute(
            "UPDATE test_sessions SET completed_at=%s, score=%s, max_score=%s, percentage=%s, status=%s, warnings=%s WHERE id=%s",
            (datetime.now(), score, max_score, percentage, "completed", warnings, session_id),
        )
        cursor.close()


def list_test_results(branch: str = None, semester: int = None, class_name: str = None):
    conditions = ["ts.status = %s"]
    params = ["completed"]
    if branch:
        conditions.append("s.branch = %s")
        params.append(branch)
    if semester:
        conditions.append("s.semester = %s")
        params.append(semester)
    if class_name:
        conditions.append("s.class = %s")
        params.append(class_name)
    where = "WHERE " + " AND ".join(conditions)
    query = f"""
        SELECT s.prn, s.name, s.class, s.branch, s.semester, qp.title, ts.score, ts.max_score, ts.percentage, ts.completed_at
        FROM test_sessions ts
        JOIN students s ON ts.student_id = s.id
        JOIN question_papers qp ON ts.paper_id = qp.id
        {where}
        ORDER BY ts.completed_at DESC
    """
    with get_conn() as conn:
        cursor = conn.cursor(cursor_factory=RealDictCursor)
        cursor.execute(query, tuple(params))
        rows = cursor.fetchall()
        cursor.close()
        return [dict(row) for row in rows]
