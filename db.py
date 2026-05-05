import os
import hashlib
from datetime import datetime
from dotenv import load_dotenv
import psycopg2
from psycopg2.extras import RealDictCursor

load_dotenv()
DATABASE_URL = os.getenv("DATABASE_URL")
if not DATABASE_URL:
    raise EnvironmentError("DATABASE_URL is required in environment variables")


def get_conn():
    return psycopg2.connect(DATABASE_URL, cursor_factory=RealDictCursor)


def hash_password(password: str) -> str:
    return hashlib.sha256(password.encode("utf-8")).hexdigest()


def init_db():
    sql = [
        """
        CREATE TABLE IF NOT EXISTS admins (
            id SERIAL PRIMARY KEY,
            username TEXT UNIQUE NOT NULL,
            password TEXT NOT NULL,
            created_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS allowed_networks (
            id SERIAL PRIMARY KEY,
            prefix TEXT UNIQUE NOT NULL,
            description TEXT,
            created_at TIMESTAMP DEFAULT NOW()
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
            active BOOLEAN DEFAULT TRUE,
            created_at TIMESTAMP DEFAULT NOW()
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
            active BOOLEAN DEFAULT TRUE,
            uploaded_at TIMESTAMP DEFAULT NOW()
        )
        """,
        """
        CREATE TABLE IF NOT EXISTS questions (
            id SERIAL PRIMARY KEY,
            paper_id INTEGER REFERENCES question_papers(id) ON DELETE CASCADE,
            question TEXT NOT NULL,
            option_a TEXT NOT NULL,
            option_b TEXT NOT NULL,
            option_c TEXT NOT NULL,
            option_d TEXT NOT NULL,
            answer TEXT NOT NULL
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
            percentage NUMERIC(5,2),
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
        with conn.cursor() as cur:
            for statement in sql:
                cur.execute(statement)
        conn.commit()


def create_admin(username: str, password: str):
    hashed = hash_password(password)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO admins (username, password) VALUES (%s, %s) ON CONFLICT (username) DO NOTHING",
                (username, hashed),
            )
        conn.commit()


def authenticate_admin(username: str, password: str) -> bool:
    hashed = hash_password(password)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT password FROM admins WHERE username = %s", (username,))
            row = cur.fetchone()
            if not row:
                return False
            return row["password"] == hashed


def get_admin_count() -> int:
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT COUNT(*) FROM admins")
            row = cur.fetchone()
            return row[0]


def add_allowed_network(prefix: str, description: str = None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO allowed_networks (prefix, description) VALUES (%s, %s) ON CONFLICT (prefix) DO UPDATE SET description = EXCLUDED.description",
                (prefix, description),
            )
        conn.commit()


def list_allowed_networks():
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM allowed_networks ORDER BY id")
            return cur.fetchall()


def set_exam_setting(key: str, value: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO exam_settings (key, value) VALUES (%s, %s) ON CONFLICT (key) DO UPDATE SET value = EXCLUDED.value",
                (key, value),
            )
        conn.commit()


def get_exam_setting(key: str, default=None):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT value FROM exam_settings WHERE key=%s", (key,))
            row = cur.fetchone()
            return row[0] if row else default


def upsert_student(prn: str, name: str, class_name: str, branch: str, semester: int, password: str = None):
    hashed = hash_password(password) if password else None
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO students (prn, name, class, branch, semester, password) VALUES (%s, %s, %s, %s, %s, %s) "
                "ON CONFLICT (prn) DO UPDATE SET name = EXCLUDED.name, class = EXCLUDED.class, branch = EXCLUDED.branch, semester = EXCLUDED.semester, password = COALESCE(EXCLUDED.password, students.password)",
                (prn, name, class_name, branch, semester, hashed),
            )
        conn.commit()


def get_student(prn: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM students WHERE prn = %s", (prn,))
            return cur.fetchone()


def set_student_password(prn: str, password: str):
    hashed = hash_password(password)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("UPDATE students SET password=%s WHERE prn=%s", (hashed, prn))
        conn.commit()


def create_question_paper(title: str, branch: str, semester: int, class_name: str, schedule_date=None, duration_minutes=30):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO question_papers (title, branch, semester, class, schedule_date, duration_minutes) VALUES (%s, %s, %s, %s, %s, %s) RETURNING id",
                (title, branch, semester, class_name, schedule_date, duration_minutes),
            )
            paper_id = cur.fetchone()[0]
        conn.commit()
    return paper_id


def add_question(paper_id: int, question: str, option_a: str, option_b: str, option_c: str, option_d: str, answer: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO questions (paper_id, question, option_a, option_b, option_c, option_d, answer) VALUES (%s, %s, %s, %s, %s, %s)",
                (paper_id, question, option_a, option_b, option_c, option_d, answer),
            )
        conn.commit()


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
        with conn.cursor() as cur:
            cur.execute(f"SELECT * FROM question_papers {where} ORDER BY uploaded_at DESC", tuple(params))
            return cur.fetchall()


def get_questions_for_paper(paper_id: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute("SELECT * FROM questions WHERE paper_id = %s ORDER BY id", (paper_id,))
            return cur.fetchall()


def create_test_session(student_id: int, paper_id: int, ip_address: str):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO test_sessions (student_id, paper_id, started_at, status, ip_address) VALUES (%s, %s, NOW(), %s, %s) RETURNING id",
                (student_id, paper_id, "in_progress", ip_address),
            )
            session_id = cur.fetchone()[0]
        conn.commit()
    return session_id


def submit_test_session(session_id: int, score: int, max_score: int, percentage: float, warnings: int):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE test_sessions SET completed_at = NOW(), score = %s, max_score = %s, percentage = %s, warnings = %s, status = %s WHERE id = %s",
                (score, max_score, percentage, warnings, "completed", session_id),
            )
        conn.commit()


def save_answer(session_id: int, question_id: int, selected_option: str, correct: bool):
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO answers (session_id, question_id, selected_option, correct) VALUES (%s, %s, %s, %s)",
                (session_id, question_id, selected_option, correct),
            )
        conn.commit()


def list_test_results(branch: str = None, class_name: str = None):
    conditions = ["status = 'completed'"]
    params = []
    if branch:
        conditions.append("students.branch = %s")
        params.append(branch)
    if class_name:
        conditions.append("students.class = %s")
        params.append(class_name)
    where = " AND ".join(conditions)
    with get_conn() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"SELECT ts.*, students.prn, students.name, students.branch, students.class, students.semester, qp.title AS paper_title "
                f"FROM test_sessions ts "
                f"JOIN students ON ts.student_id = students.id "
                f"JOIN question_papers qp ON ts.paper_id = qp.id "
                f"WHERE {where} ORDER BY ts.completed_at DESC",
                tuple(params),
            )
            return cur.fetchall()
