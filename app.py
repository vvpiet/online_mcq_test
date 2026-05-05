import os
import secrets
import io
import traceback
from datetime import date, datetime
import pandas as pd
import streamlit as st
import streamlit.components.v1 as components
from db import (
    init_db,
    create_admin,
    authenticate_admin,
    get_admin_count,
    add_allowed_network,
    list_allowed_networks,
    set_exam_setting,
    get_exam_setting,
    upsert_student,
    get_student,
    set_student_password,
    hash_password,
    create_question_paper,
    add_question,
    list_question_papers,
    get_questions_for_paper,
    create_test_session,
    submit_test_session,
    save_answer,
    list_test_results,
)

BRANCHES = {
    "CIVIL (11191)": "CIVIL",
    "AI&DS (11995)": "AI&DS",
    "ARTIFICIAL INTELLIGENCE (AI) & DS (11263)": "AI_DS",
    "CSE (11242)": "CSE",
    "ELECTRICAL (11293)": "ELECTRICAL",
    "E&TC (11372)": "E&TC",
    "MECHANICAL (11216)": "MECHANICAL",
    "BCA (11101)": "BCA",
    "MCA (22241)": "MCA",
    "M.tech (CSE) (12242)": "MTECH_CSE",
    "M.tech (Design) (12601)": "MTECH_DESIGN",
}
CLASS_OPTIONS = ["FY", "SY", "TY", "B.Tech", "BCA", "MCA", "M.tech (CSE)", "M.tech (Design)"]
SEMESTER_OPTIONS = [1, 2, 3, 4, 5, 6, 7, 8]


def page_setup():
    st.set_page_config(page_title="Engineering MCQ Test Portal", layout="wide")
    st.title("Engineering College Online MCQ Test Portal")


def _safe_rerun():
    if hasattr(st, "experimental_rerun"):
        st.experimental_rerun()
    elif hasattr(st, "rerun"):
        st.rerun()
    else:
        st.stop()


@st.cache_resource
def load_startup():
    init_db()
    if get_admin_count() == 0:
        create_admin("admin", "admin123")
    return True


def render_admin_panel():
    if "admin_logged_in" not in st.session_state:
        st.session_state.admin_logged_in = False

    if not st.session_state.admin_logged_in:
        st.subheader("Admin Login")
        username = st.text_input("Admin username")
        password = st.text_input("Admin password", type="password")
        if st.button("Login"):
            if authenticate_admin(username.strip(), password.strip()):
                st.session_state.admin_logged_in = True
                _safe_rerun()
            else:
                st.error("Invalid admin credentials")
        return

    st.sidebar.success("Admin signed in")
    section = st.sidebar.radio("Admin menu", ["IP Config", "Upload Questions", "Student Accounts", "Exam Schedule", "Results Download"])

    if section == "IP Config":
        st.header("IP Address Configuration")
        st.write("Only students from configured network prefixes can start the exam.")
        prefix = st.text_input("Allowed network prefix", "192.168.100.")
        description = st.text_input("Description (e.g. lab network)")
        if st.button("Save prefix"):
            if prefix:
                add_allowed_network(prefix, description)
                st.success(f"Saved allowed prefix {prefix}")
        networks = list_allowed_networks()
        if networks:
            st.table(pd.DataFrame(networks))

    elif section == "Upload Questions":
        st.header("Upload MCQ Question Paper")
        paper_title = st.text_input("Question paper title")
        branch = st.selectbox("Branch", list(BRANCHES.keys()))
        semester = st.selectbox("Semester", SEMESTER_OPTIONS)
        class_name = st.selectbox("Class", CLASS_OPTIONS)
        schedule_date = st.date_input("Activate on date", value=date.today())
        duration = st.slider("Exam duration (minutes)", min_value=30, max_value=45, value=int(get_exam_setting("default_duration") or 30))
        file = st.file_uploader("Upload MCQ question CSV or Excel", type=["csv", "xlsx"])

        if st.button("Save question paper"):
            if not paper_title:
                st.error("Please provide a title for the question paper.")
            elif not file:
                st.error("Please upload a question file.")
            else:
                try:
                    # Convert Streamlit UploadedFile to BytesIO for compatibility
                    if hasattr(file, 'read'):
                        file_bytes = file.read()
                        file.seek(0)  # Reset for potential re-reads
                    else:
                        file_bytes = file
                    
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
                        # Try CSV first, then Excel
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
                        st.error("Uploaded file must contain columns: question, a, b, c, d, answer")
                    else:
                        paper_id = create_question_paper(paper_title, branch, semester, class_name, schedule_date, duration)
                        for _, row in df.iterrows():
                            add_question(
                                paper_id,
                                str(row["question"]).strip() if "question" in row.index else "",
                                str(row["a"]).strip() if "a" in row.index else "",
                                str(row["b"]).strip() if "b" in row.index else "",
                                str(row["c"]).strip() if "c" in row.index else "",
                                str(row["d"]).strip() if "d" in row.index else "",
                                str(row["answer"]).strip() if "answer" in row.index else "",
                            )
                        st.success("Question paper uploaded and converted to MCQs.")
                except Exception as exc:
                    st.error(f"Unable to parse upload: {str(exc)}")
                    st.error(f"Error details: {traceback.format_exc()}")

        st.write("### Existing question papers")
        papers = list_question_papers()
        if papers:
            st.dataframe(pd.DataFrame(papers))
        else:
            st.info("No question papers uploaded yet.")

    elif section == "Student Accounts":
        st.header("Student Account Management")
        st.write("Upload a CSV with PRN, name, class, branch, semester to bulk-create student accounts.")
        file = st.file_uploader("Upload student list CSV", type=["csv"] )
        if st.button("Create / Update students"):
            if not file:
                st.error("Upload a CSV file first.")
            else:
                file.seek(0)
                df = pd.read_csv(file)
                df.columns = df.columns.str.lower()
                if not all(col in df.columns for col in ["prn", "name", "class", "branch", "semester"]):
                    st.error("CSV must contain columns: prn, name, class, branch, semester")
                else:
                    for _, row in df.iterrows():
                        upsert_student(
                            str(row["prn"]).strip(),
                            str(row["name"]).strip(),
                            str(row["class"]).strip(),
                            str(row["branch"]).strip(),
                            int(row["semester"]),
                        )
                    st.success("Student accounts imported successfully.")
        st.write("### Generate exam-day password")
        prn = st.text_input("Student PRN for password generation")
        if st.button("Generate password"):
            if not prn:
                st.error("Enter PRN")
            else:
                password = secrets.token_urlsafe(6)
                set_student_password(prn.strip(), password)
                st.success("Student password created")
                st.write("Password for student:", password)

    elif section == "Exam Schedule":
        st.header("Exam Schedule & Duration")
        duration = st.slider("Default exam duration (minutes)", min_value=30, max_value=45, value=int(get_exam_setting("default_duration") or 30))
        if st.button("Save default duration"):
            set_exam_setting("default_duration", str(duration))
            st.success("Default duration saved")
        st.write("Use the upload question panel to set a schedule date for each paper.")
        st.write("Schedule determines when a paper becomes visible for students.")

    elif section == "Results Download":
        st.header("Download Test Results")
        branch = st.selectbox("Branch filter", ["All"] + list(BRANCHES.keys()))
        class_name = st.selectbox("Class filter", ["All"] + CLASS_OPTIONS)
        if st.button("Load results"):
            branch_filter = None if branch == "All" else branch
            class_filter = None if class_name == "All" else class_name
            results = list_test_results(branch_filter, class_filter)
            if results:
                df = pd.DataFrame(results)
                st.dataframe(df)
                csv = df.to_csv(index=False).encode("utf-8")
                st.download_button("Download results CSV", data=csv, file_name="test_results.csv", mime="text/csv")
            else:
                st.info("No results available for this selection.")


def get_proctor_html():
    return """
    <style>
    #webcam-box {position:fixed; top:10px; right:10px; z-index:9999; width:260px; background:#111; color:#fff; padding:8px; border:2px solid #0066cc; border-radius:8px;}
    #webcam-box video {width:240px; height:180px; border-radius:6px;}
    #warning-text {font-weight:bold; color:#ff6666; margin-top:6px;}
    </style>
    <div id="webcam-box">
      <div><strong>Proctoring camera</strong></div>
      <video id="webcam" autoplay muted playsinline></video>
      <div id="warning-text">Warnings: 0</div>
    </div>
    <script>
      let warnings = 0;
      const warningText = document.getElementById('warning-text');
      async function startCamera() {
        try {
          const stream = await navigator.mediaDevices.getUserMedia({video:true});
          document.getElementById('webcam').srcObject = stream;
        } catch (err) {
          warningText.textContent = 'Camera disabled: allow camera access';
        }
      }
      startCamera();
      document.addEventListener('visibilitychange', () => {
        if (document.hidden) {
          warnings += 1;
          warningText.textContent = 'Warnings: ' + warnings;
          if (warnings >= 10) {
            alert('Too many tab changes. The exam will be auto-submitted.');
            const base = window.location.href.split('?')[0];
            window.location.href = base + '?auto_submit=1';
          }
        }
      });
    </script>
    """


def render_student_panel():
    st.header("Student Login")
    prn = st.text_input("PRN")
    branch = st.selectbox("Branch", list(BRANCHES.keys()))
    semester = st.selectbox("Semester", SEMESTER_OPTIONS)
    class_name = st.selectbox("Class", CLASS_OPTIONS)
    password = st.text_input("Exam password", type="password")
    client_ip = st.text_input("Client IP (e.g. 192.168.100.125)")

    if st.button("Login to exam"):
        student = get_student(prn.strip())
        if not student:
            st.error("Student record not found. Contact admin.")
            return
        if student["branch"] != branch or student["semester"] != semester or student["class"] != class_name:
            st.error("Selected branch / semester / class do not match the student record.")
            return
        if not student["password"]:
            st.error("Password not set by admin yet. Contact your administrator.")
            return
        if hash_password(password.strip()) != student["password"]:
            st.error("Incorrect exam password")
            return
        allowed_prefixes = [row["prefix"] for row in list_allowed_networks()]
        if allowed_prefixes:
            if not client_ip or not any(client_ip.strip().startswith(prefix) for prefix in allowed_prefixes):
                st.error("Your IP is not in the allowed exam network.")
                return
        st.session_state.student = student
        st.session_state.logged_in = True
        st.session_state.client_ip = client_ip.strip()
        _safe_rerun()

    if "logged_in" not in st.session_state or not st.session_state.logged_in:
        st.info("Login with PRN, branch, semester, class and exam password. Your assigned IP prefix must match admin settings.")
        return

    student = st.session_state.student
    st.success(f"Logged in as {student['name']} ({student['prn']})")
    papers = list_question_papers(branch, semester, class_name)
    today = date.today()
    available = [p for p in papers if p["active"] and (p["schedule_date"] is None or p["schedule_date"] <= today)]
    if not available:
        st.warning("No active exam paper is available right now.")
        return

    active_paper = available[0]
    st.subheader(f"Available exam: {active_paper['title']}")
    if st.button("Start exam"):
        st.session_state.paper_id = active_paper["id"]
        st.session_state.exam_active = True
        st.session_state.warnings = 0
        _safe_rerun()

    if "exam_active" in st.session_state and st.session_state.exam_active:
        if st.session_state.paper_id != active_paper["id"]:
            st.session_state.paper_id = active_paper["id"]
        render_exam(active_paper)


def render_exam(paper):
    query_params = st.experimental_get_query_params()
    if query_params.get("auto_submit"):
        st.session_state.auto_submit = True

    if "started_at" not in st.session_state:
        st.session_state.started_at = datetime.now()
        st.session_state.session_id = create_test_session(
            st.session_state.student["id"],
            paper["id"],
            st.session_state.client_ip,
        )
        st.session_state.answers = {}

    duration = paper["duration_minutes"] or int(get_exam_setting("default_duration") or 30)
    end_time = st.session_state.started_at + pd.Timedelta(minutes=duration)
    remaining = end_time - datetime.now()
    minutes, seconds = divmod(int(remaining.total_seconds()), 60)
    if remaining.total_seconds() <= 0 or st.session_state.get("auto_submit"):
        st.warning("Time is up or auto-submit triggered.")
        evaluate_exam(paper)
        return

    st.markdown(f"### Time remaining: {minutes:02d}:{seconds:02d}")
    st.markdown("#### Camera-based proctoring and tab-change detection is active.")
    components.html(get_proctor_html(), height=260)
    questions = get_questions_for_paper(paper["id"])
    responses = {}
    for question in questions:
        qid = question["id"]
        responses[f"q_{qid}"] = st.radio(
            f"{question['question']}",
            options=["a", "b", "c", "d"],
            format_func=lambda x, q=question: f"{x}) {q['option_' + x]}" if x in ['a','b','c','d'] else x,
            key=f"q_{qid}",
        )
    if st.button("Submit exam"):
        evaluate_exam(paper)


def evaluate_exam(paper):
    if "session_id" not in st.session_state:
        st.error("Exam session missing.")
        return
    questions = get_questions_for_paper(paper["id"])
    score = 0
    for question in questions:
        selected = st.session_state.get(f"q_{question['id']}")
        correct = selected == question["answer"]
        if correct:
            score += 1
        save_answer(st.session_state.session_id, question["id"], selected, correct)
    total = len(questions)
    percentage = round(score / total * 100, 2) if total else 0
    warnings = st.session_state.get("warnings", 0)
    submit_test_session(st.session_state.session_id, score, total, percentage, warnings)
    st.success(f"Exam submitted. Score: {score}/{total} ({percentage}%)")
    st.balloons()
    st.session_state.exam_active = False
    st.session_state.started_at = None


def main():
    page_setup()
    load_startup()
    st.sidebar.title("Navigation")
    mode = st.sidebar.selectbox("Choose mode", ["Student", "Admin"])
    if mode == "Admin":
        render_admin_panel()
    else:
        render_student_panel()


if __name__ == "__main__":
    main()
