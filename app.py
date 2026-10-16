from decimal import Decimal
from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, send_file, jsonify
import os, re, datetime, random, uuid, io, smtplib, qrcode, time
from werkzeug.utils import secure_filename
from email.mime.text import MIMEText
from email.mime.multipart import MIMEMultipart
from jinja2 import Environment, FileSystemLoader
import MySQLdb.cursors


# ✅ Import db from extensions
from extensions import db  

# ---------------- Flask Config ----------------
app = Flask(__name__)
app.secret_key = os.environ.get("SECRET_KEY", "fallback_key")

# ✅ Configure SQLAlchemy to connect to your MySQL database
app.config['SQLALCHEMY_DATABASE_URI'] = "mysql+pymysql://school_user:qrcode12345!@localhost:3307/school_system"
app.config['SQLALCHEMY_TRACK_MODIFICATIONS'] = False

# ✅ Initialize db with app
db.init_app(app)

# ✅ Import models AFTER db is initialized
from models import Student, Transaction
from flask_mysqldb import MySQL

app.config['MYSQL_USER'] = 'school_user'
app.config['MYSQL_PASSWORD'] = 'qrcode12345!'
app.config['MYSQL_DB'] = 'school_system'
app.config['MYSQL_HOST'] = 'localhost'
app.config['MYSQL_PORT'] = 3307

mysql = MySQL(app)


def generate_fixed_qr(student_id):
    # Create QR code with student_id (or school_id)
    qr = qrcode.make(student_id)

    # Ensure folder exists
    qr_folder = os.path.join("static", "qrcodes")
    os.makedirs(qr_folder, exist_ok=True)

    # Save QR file
    qr_path = os.path.join(qr_folder, f"{student_id}.png")
    qr.save(qr_path)

    return qr_path

                                
# ---------------- Upload Config ----------------
UPLOAD_FOLDER = "static/uploads"
ALLOWED_EXTENSIONS = {"png", "jpg", "jpeg", "gif"}
app.config["UPLOAD_FOLDER"] = UPLOAD_FOLDER

def allowed_file(filename):
    return "." in filename and filename.rsplit(".", 1)[1].lower() in ALLOWED_EXTENSIONS

# --------------- Routes ---------------

@app.route("/") 
def index():
    # Main landing page for students
    return render_template("index.html")

@app.route("/staff")
def index_staff():
    # Staff landing page
    return render_template("index_staff.html")

@app.route("/admin")
def index_admin():
    # Admin landing page
    return render_template("index_admin.html")

@app.route('/login_page')
def login_page():
    return render_template('login.html')


@app.route('/signup')
def signup():
    return render_template('signup.html')


# ---------------- Admin Pending Top-Ups ----------------
@app.route("/admin/pending_topups")
def admin_pending_topups():
    if "email" not in session or session.get("role") != "admin":
        flash("Unauthorized access.", "error")
        return redirect(url_for("signin_admin"))

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)


    # Fetch all pending top-ups
    cursor.execute("""
        SELECT t.topup_id, s.full_name, s.school_id, t.amount, t.payment_mode, 
               t.reference_number, t.created_at
        FROM topups t
        JOIN students s ON t.student_id = s.student_id
        WHERE t.status='pending'
        ORDER BY t.created_at DESC
    """)
    pending_topups = cursor.fetchall()
    conn.close()

    return render_template("admin_pending_topups.html", pending_topups=pending_topups)


# Registered Students
@app.route('/admin/registered')
def dashboard_registered():
    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    cursor.execute("""
        SELECT full_name, school_id, balance, status,
               DATEDIFF(CURDATE(), last_active) AS days_inactive
        FROM students
        ORDER BY full_name
    """)
    registered_students = cursor.fetchall()
    conn.close()

    return render_template('dashboard_admin.html',
                           section='registered',
                           registered_students=registered_students)

# Transactions
@app.route('/dashboard/transactions')
def dashboard_transactions():
    start = request.args.get("start_date")
    end = request.args.get("end_date")

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    query = """
        SELECT t.transaction_id, t.created_at, t.type, t.amount, t.payment_mode,
               COALESCE(s.full_name, a.full_name) AS performed_by,
               st.full_name AS customer_name, st.school_id AS id_no, t.remarks
        FROM transactions t
        LEFT JOIN staff s ON t.staff_id = s.staff_id
        LEFT JOIN admins a ON t.admin_id = a.admin_id
        LEFT JOIN students st ON t.student_id = st.student_id
        WHERE 1=1
    """
    params = []
    if start:
        query += " AND t.created_at >= %s"
        params.append(start)
    if end:
        query += " AND t.created_at <= %s"
        params.append(end)

    query += " ORDER BY t.created_at DESC"
    cursor.execute(query, params)
    transactions = cursor.fetchall()
    conn.close()

    return render_template('student_transactions.html', transactions=transactions)





# -------------------
# Authentication + Student Routes
# -------------------

@app.route("/logout")
def logout():
    session.clear()
    flash("You have been logged out.", "success")
    return redirect(url_for("login_page"))

@app.route("/profile")
def profile_student():
    if "email" not in session or session.get("role") != "student":
        return redirect(url_for("login_page"))

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM students WHERE email=%s", (session["email"],))
    student = cursor.fetchone()
    conn.close()

    return render_template("profile.html", student=student)




@app.route("/db_structure")
def db_structure():
    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    # Query all tables + columns in your current schema
    cursor.execute("""
        SELECT TABLE_NAME, COLUMN_NAME, COLUMN_TYPE, IS_NULLABLE,
               COLUMN_DEFAULT, COLUMN_KEY, EXTRA
        FROM information_schema.columns
        WHERE table_schema = DATABASE()
        ORDER BY TABLE_NAME, ORDINAL_POSITION;
    """)
    columns = cursor.fetchall()
    conn.close()

    # Group by table
    tables = {}
    for col in columns:
        table = col["TABLE_NAME"]
        if table not in tables:
            tables[table] = []
        tables[table].append(col)

    # Render HTML
    html = "<h2>Database Structure</h2>"
    for table, cols in tables.items():
        html += f"<h3>{table}</h3>"
        html += "<table border='1' cellpadding='6' style='border-collapse:collapse;'>"
        html += "<tr><th>Column</th><th>Type</th><th>Nullable</th><th>Default</th><th>Key</th><th>Extra</th></tr>"
        for c in cols:
            html += f"<tr><td>{c['COLUMN_NAME']}</td><td>{c['COLUMN_TYPE']}</td><td>{c['IS_NULLABLE']}</td>"
            html += f"<td>{c['COLUMN_DEFAULT']}</td><td>{c['COLUMN_KEY']}</td><td>{c['EXTRA']}</td></tr>"
        html += "</table><br>"
    return html

# --------------- Password Validation Function ---------------
import re

def is_strong_password(password):
    """
    Validates password strength:
    - At least 8 characters
    - Contains at least one number
    - Contains at least one special character
    """
    if len(password) < 8:
        return False
    if not re.search(r"\d", password):  # must contain a number
        return False
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password):  # must contain a special character
        return False
    return True


# ---------------- Database Connection ----------------
def get_connection():
    return mysql.connection

# ---------------- Email Function ----------------
FROM_EMAIL = "hyckotoshi@gmail.com"
REPLY_TO_EMAIL = "hyckotoshi@gmail.com"


def send_email(to_emails, subject, body_text=None, body_html=None):
    sender_email = "hyckotoshi@gmail.com"
    password = "jpxb fsam zljx zjgl"  # Use Gmail/Outlook App Password

    msg = MIMEMultipart("alternative")
    msg["From"] = f"FCD Central Institute <{sender_email}>"
    msg["To"] = ", ".join(to_emails)
    msg["Subject"] = subject

    if body_text:
        msg.attach(MIMEText(body_text, "plain"))
    if body_html:
        msg.attach(MIMEText(body_html, "html"))

    try:
        server = smtplib.SMTP("smtp.gmail.com", 587)  # Gmail SMTP
        server.starttls()
        server.login(sender_email, password)
        server.sendmail(sender_email, to_emails, msg.as_string())
        server.quit()
        print(f"Email sent to {to_emails}")
        return True
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return False


def generate_and_send_otp(email, subject="Your Secure Login OTP", role="student"):
    otp = str(random.randint(100000, 999999))
    expires = datetime.datetime.now() + datetime.timedelta(minutes=5)

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)
    cursor.execute("INSERT INTO otps (email, otp_code, expires_at) VALUES (%s,%s,%s)", (email, otp, expires))
    conn.commit()
    conn.close()

    # Role-specific body text
    if role == "student":
        body_text = f"Hello Student,\n\nYour OTP is: {otp} (expires in 5 minutes).\n\nUse this to access your student dashboard."
    elif role == "admin":
        body_text = f"Hello Admin,\n\nYour OTP is: {otp} (expires in 5 minutes).\n\nUse this to access the admin dashboard securely."
    elif role == "staff":
        body_text = f"Hello Staff,\n\nYour OTP is: {otp} (expires in 5 minutes).\n\nUse this to access the staff dashboard securely."
    else:
        body_text = f"Your OTP is: {otp} (expires in 5 minutes)."

    # Load HTML template with Jinja2
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("otp_template.html")
    body_html = template.render(otp=otp, role=role)

    # Send email via SMTP
    send_email([email], subject, body_text, body_html)

    return otp


# ---------------- OTP Function ----------------
def generate_and_send_otp(email, subject="Your Secure Login OTP", role="student"):
    otp = str(random.randint(100000, 999999))
    expires = datetime.datetime.now() + datetime.timedelta(minutes=5)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO otps (email, otp_code, expires_at) VALUES (%s,%s,%s)", (email, otp, expires))
    conn.commit()
    conn.close()

    # Role‑specific body text
    if role == "student":
        body_text = f"Hello Student,\n\nYour OTP is: {otp} (expires in 5 minutes).\n\nUse this to access your student dashboard."
    elif role == "admin":
        body_text = f"Hello Admin,\n\nYour OTP is: {otp} (expires in 5 minutes).\n\nUse this to access the admin dashboard securely."
    elif role == "staff":
        body_text = f"Hello Staff,\n\nYour OTP is: {otp} (expires in 5 minutes).\n\nUse this to access the staff dashboard securely."
    else:
        body_text = f"Your OTP is: {otp} (expires in 5 minutes)."

    # Load HTML template with Jinja2
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("otp_template.html")
    body_html = template.render(otp=otp, role=role)

    send_email([email], subject, body_text, body_html)
    return otp


# ---------------- Forgot Password (Student) ----------------
@app.route("/forgot_password/student", methods=["GET","POST"])
def forgot_password_student():
    if request.method == "POST":
        email = request.form.get("email")

        conn = get_connection()
        cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)
        cursor.execute("SELECT security_q1, security_q2, security_q3 FROM students WHERE email=%s", (email,))
        student = cursor.fetchone()
        conn.close()

        if not student:
            flash("No account found with that email.", "error")
            return redirect(url_for("forgot_password_student"))

        # Store email in session for later steps
        session["reset_email"] = email
        return render_template("answer_security.html", student=student)

    return render_template("forgot_password_student.html")



@app.route("/verify_security_answers", methods=["POST"])
def verify_security_answers():
    email = session.get("reset_email")
    a1 = request.form.get("security_a1")
    a2 = request.form.get("security_a2")
    a3 = request.form.get("security_a3")

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT security_a1, security_a2, security_a3 FROM students WHERE email=%s", (email,))
    student = cursor.fetchone()
    conn.close()

    if student and student["security_a1"].lower() == a1.lower() \
       and student["security_a2"].lower() == a2.lower() \
       and student["security_a3"].lower() == a3.lower():
        return redirect(url_for("reset_password_student"))
    else:
        flash("Security answers did not match.", "error")
        return redirect(url_for("forgot_password_student"))



@app.route("/reset_password/student", methods=["GET","POST"])
def reset_password_student():
    email = session.get("reset_email")

    if request.method == "POST":
        new_password = request.form.get("new_password")
        confirm_password = request.form.get("confirm_password")

        password_regex = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$")
        if not password_regex.match(new_password):
            flash("Password must meet complexity requirements.", "error")
            return redirect(url_for("reset_password_student"))

        if new_password != confirm_password:
            flash("Passwords do not match.", "error")
            return redirect(url_for("reset_password_student"))

        hashed_pass = generate_password_hash(new_password)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE students SET password=%s WHERE email=%s", (hashed_pass, email))
        conn.commit()
        conn.close()

        # 🔹 Send OTP for final confirmation
        generate_and_send_otp(email, subject="Confirm Your Password Reset", role="student")

        flash("Password updated. Please check your email for OTP confirmation.", "success")
        return redirect(url_for("verify_otp"))

    return render_template("reset_password_student.html")





# ---------------- Forgot Password (Admin) ----------------
@app.route("/forgot_password/admin", methods=["GET", "POST"])
def forgot_password_admin():
    if request.method == "POST":
        if "email" in request.form:
            # Step 1: user entered their email
            email = request.form["email"]
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT security_q1, security_q2, security_q3 
                              FROM admins WHERE email=%s""", (email,))
            record = cursor.fetchone()
            conn.close()

            if record:
                session["pending_email"] = email
                return render_template("forgot_admin_questions.html",
                                       question1=record[0],
                                       question2=record[1],
                                       question3=record[2])
            else:
                flash("Admin email not found.")
                return redirect(url_for("forgot_password_admin"))
        else:
            # Step 2: user answered questions
            a1 = request.form["answer1"]
            a2 = request.form["answer2"]
            a3 = request.form["answer3"]

            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT security_a1, security_a2, security_a3 
                              FROM admins WHERE email=%s""", (session["pending_email"],))
            answers = cursor.fetchone()
            conn.close()

            if answers and answers[0] == a1 and answers[1] == a2 and answers[2] == a3:
                return redirect(url_for("reset_password_admin"))
            else:
                flash("Incorrect answers.")
                return redirect(url_for("forgot_password_admin"))

    return render_template("forgot_admin.html")




# ---------------- Forgot Password (Staff) ----------------
@app.route("/forgot_password/staff", methods=["GET", "POST"])
def forgot_password_staff():
    if request.method == "POST":
        if "email" in request.form:
            # Step 1: user entered their email
            email = request.form["email"]
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT security_q1, security_q2, security_q3 
                              FROM staff WHERE email=%s""", (email,))
            record = cursor.fetchone()
            conn.close()

            if record:
                session["pending_email"] = email
                return render_template("forgot_staff_questions.html",
                                       question1=record[0],
                                       question2=record[1],
                                       question3=record[2])
            else:
                flash("Staff email not found.")
                return redirect(url_for("forgot_password_staff"))
        else:
            # Step 2: user answered questions
            a1 = request.form["answer1"]
            a2 = request.form["answer2"]
            a3 = request.form["answer3"]

            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""SELECT security_a1, security_a2, security_a3 
                              FROM staff WHERE email=%s""", (session["pending_email"],))
            answers = cursor.fetchone()
            conn.close()

            if answers and answers[0] == a1 and answers[1] == a2 and answers[2] == a3:
                return redirect(url_for("reset_password_staff"))
            else:
                flash("Incorrect answers.")
                return redirect(url_for("forgot_password_staff"))

    return render_template("forgot_staff.html")



# ---------------- Login ----------------

@app.route("/login", methods=["GET", "POST"])
def login():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor()

        # Check Student
        cursor.execute("SELECT student_id, email, password FROM students WHERE email=%s", (email,))
        student = cursor.fetchone()
        if student and check_password_hash(student[2], password):
            session["role"] = "student"
            session["student_id"] = student[0]
            session["pending_email"] = student[1]
            generate_and_send_otp(email, subject="Your Student OTP Code", role="student")
            conn.close()
            return redirect(url_for("verify_otp"))

        # Check Admin
        cursor.execute("SELECT admin_id, email, password FROM admins WHERE email=%s", (email,))
        admin = cursor.fetchone()
        if admin and check_password_hash(admin[2], password):
            session["role"] = "admin"
            session["admin_id"] = admin[0]
            session["pending_email"] = admin[1]
            generate_and_send_otp(email, subject="Your Admin OTP Code", role="admin")
            conn.close()
            return redirect(url_for("verify_otp"))

        # Check Staff
        cursor.execute("SELECT staff_id, email, password FROM staff WHERE email=%s", (email,))
        staff = cursor.fetchone()
        if staff and check_password_hash(staff[2], password):
            session["role"] = "staff"
            session["staff_id"] = staff[0]
            session["pending_email"] = staff[1]
            generate_and_send_otp(email, subject="Your Staff OTP Code", role="staff")
            conn.close()
            return redirect(url_for("verify_otp"))

        conn.close()
        flash("Invalid credentials.", "error")
        return redirect(url_for("login"))

    return render_template("login.html")


# ---------------- Student Sign Up ----------------
@app.route("/signup/student", methods=["GET","POST"])
def signup_student():
    if request.method == "POST":
        try:
            # Collect and validate form data
            full_name = request.form.get("full_name")
            school_id = request.form.get("school_id")
            email = request.form.get("email")
            parent_email = request.form.get("parent_email")
            contact_number = request.form.get("contact_number")
            strand = request.form.get("strand")
            guardian_name = request.form.get("guardian_name")
            grade_level = request.form.get("grade_level")
            password = request.form.get("password")
            confirm_password = request.form.get("confirm_password")

            # 🔹 Validations (same as before)
            if not re.match(r"^\d{7}$", school_id):
                flash("❌ School ID must be exactly 7 digits.", "error")
                return redirect(url_for("signup_student"))
            if not re.match(r"^09\d{9}$", contact_number):
                flash("❌ Phone number must start with 09 and be 11 digits.", "error")
                return redirect(url_for("signup_student"))
            if not email.endswith("@gmail.com") or not parent_email.endswith("@gmail.com"):
                flash("❌ Emails must be Gmail addresses.", "error")
                return redirect(url_for("signup_student"))
            password_regex = re.compile(r"^(?=.*[a-z])(?=.*[A-Z])(?=.*\d)(?=.*[\W_]).{8,}$")
            if not password_regex.match(password):
                flash("❌ Password must meet complexity requirements.", "error")
                return redirect(url_for("signup_student"))
            if password != confirm_password:
                flash("❌ Passwords do not match.", "error")
                return redirect(url_for("signup_student"))
            if len(request.form.get("security_a1","")) < 3 or len(request.form.get("security_a2","")) < 3 or len(request.form.get("security_a3","")) < 3:
                flash("❌ Security answers must be at least 3 characters long.", "error")
                return redirect(url_for("signup_student"))

            # 🔹 Save data temporarily in session
            session["pending_signup"] = {
                "full_name": full_name,
                "school_id": school_id,
                "email": email,
                "parent_email": parent_email,
                "contact_number": contact_number,
                "strand": strand,
                "guardian_name": guardian_name,
                "grade_level": grade_level,
                "hashed_pass": generate_password_hash(password),
                "security_q1": request.form["security_q1"],
                "security_a1": request.form["security_a1"],
                "security_q2": request.form["security_q2"],
                "security_a2": request.form["security_a2"],
                "security_q3": request.form["security_q3"],
                "security_a3": request.form["security_a3"],
            }

            # 🔹 Generate OTP and send email using template
            otp = str(random.randint(100000, 999999))
            session["pending_otp"] = otp
            

            env = Environment(loader=FileSystemLoader("templates"))
            template = env.get_template("otp_template.html")
            body_html = template.render(otp=otp, role="student")

            body_text = f"Hello Student,\n\nYour OTP is: {otp} (expires in 5 minutes).\n\nUse this to access your student dashboard."

            send_email([email], "Your Secure OTP Code", body_text, body_html)

            flash("We sent an OTP to your email. Please verify.", "info")
            return redirect(url_for("verify_otp"))

        except Exception as e:
            flash(f"General error: {str(e)}", "error")
            return redirect(url_for("signup_student"))

    return render_template("signup_student.html")


       


@app.route("/generate_all_qr")
def generate_all_qr():
    try:
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT student_id FROM students WHERE qr_code IS NULL OR qr_code=''")
        students = cursor.fetchall()

        count = 0
        for (student_id,) in students:
            qr_path = generate_qr(student_id)
            cursor.execute("UPDATE students SET qr_code=%s WHERE student_id=%s", (qr_path, student_id))
            count += 1

        conn.commit()
        conn.close()
        return f"✅ Generated QR codes for {count} students."
    except Exception as e:
        return f"❌ Error generating QR codes: {str(e)}"

@app.route("/setup_pin", methods=["GET","POST"])
def setup_pin():
    try:
        if request.method == "POST":
            pin = request.form.get("pin")
            if not re.match(r"^\d{4}$", pin):
                flash("❌ PIN must be 4 digits.", "error")
                return redirect(url_for("setup_pin"))

            data = session.get("pending_signup")
            if not data:
                flash("❌ No signup data found.", "error")
                return redirect(url_for("signup_student"))

            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""INSERT INTO students 
                (full_name, school_id, email, contact_number, strand, guardian_name, parent_email, grade_level,
                 password, pin, security_q1, security_a1, security_q2, security_a2, security_q3, security_a3)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""",
                (data["full_name"], data["school_id"], data["email"], data["contact_number"], data["strand"],
                 data["guardian_name"], data["parent_email"], data["grade_level"], data["hashed_pass"], pin,
                 data["security_q1"], data["security_a1"], data["security_q2"], data["security_a2"],
                 data["security_q3"], data["security_a3"])
            )
            conn.commit()

            cursor.execute("SELECT student_id FROM students WHERE email=%s", (data["email"],))
            student_id = cursor.fetchone()[0]
            qr_path = generate_qr(student_id)
            cursor.execute("UPDATE students SET qr_code=%s WHERE student_id=%s", (qr_path, student_id))
            conn.commit()
            conn.close()

            flash("🎉 Account created successfully!", "success")
            session.pop("pending_signup", None)
            session.pop("pending_otp", None)
            return redirect(url_for("signin_student"))

        return render_template("setup_pin.html")
    except Exception as e:
        flash(f"Error setting PIN: {str(e)}", "error")
        return redirect(url_for("signup_student"))







@app.route("/confirm_signup", methods=["GET","POST"])
def confirm_signup():
    email = session.get("pending_email")
    if not email:
        flash("No pending signup found.", "error")
        return redirect(url_for("signup_student"))

    if request.method == "POST":
        otp = request.form["otp"]

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT otp_code, expires_at FROM otps WHERE email=%s ORDER BY id DESC LIMIT 1", (email,))
        record = cursor.fetchone()
        conn.close()

        if record and record[0] == otp and datetime.datetime.now() < record[1]:
            flash("Signup confirmed! Please log in.", "success")
            return redirect(url_for("signin_student"))
        else:
            flash("Invalid or expired confirmation code.", "error")
            return redirect(url_for("confirm_signup"))

    return render_template("confirm_signup.html", email=email)



# ---------------- Admin Sign Up ----------------

@app.route("/signup/admin", methods=["GET", "POST"])
def signup_admin():
    if request.method == "POST":
        full_name = request.form["full_name"]
        contact_number = request.form["contact_number"]
        email = request.form["email"]
        password = request.form["password"]

        # Security questions
        security_q1 = request.form["security_q1"]
        security_a1 = request.form["security_a1"]
        security_q2 = request.form["security_q2"]
        security_a2 = request.form["security_a2"]
        security_q3 = request.form["security_q3"]
        security_a3 = request.form["security_a3"]

        # Hash password
        hashed_pw = generate_password_hash(password)

        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO admins (full_name, contact_number, email, password,
                                    security_q1, security_a1, security_q2, security_a2,
                                    security_q3, security_a3)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (full_name, contact_number, email, hashed_pw,
                  security_q1, security_a1, security_q2, security_a2,
                  security_q3, security_a3))
            conn.commit()
            conn.close()
            flash("Admin account created successfully. Please log in.")
            return redirect(url_for("signin_admin"))
        except Exception as e:
            flash(f"Database error: {str(e)}", "error")
            return redirect(url_for("signup_admin"))

    return render_template("signup_admin.html")



# ---------------- Staff Sign Up ----------------

@app.route("/signup/staff", methods=["GET", "POST"])
def signup_staff():
    if request.method == "POST":
        full_name = request.form["full_name"]
        contact_number = request.form["contact_number"]
        email = request.form["email"]
        password = request.form["password"]

        # Security questions
        security_q1 = request.form["security_q1"]
        security_a1 = request.form["security_a1"]
        security_q2 = request.form["security_q2"]
        security_a2 = request.form["security_a2"]
        security_q3 = request.form["security_q3"]
        security_a3 = request.form["security_a3"]

        # Hash password
        hashed_pw = generate_password_hash(password)

        try:
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""
                INSERT INTO staff (full_name, contact_number, email, password,
                                   security_q1, security_a1, security_q2, security_a2,
                                   security_q3, security_a3)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
            """, (full_name, contact_number, email, hashed_pw,
                  security_q1, security_a1, security_q2, security_a2,
                  security_q3, security_a3))
            conn.commit()
            conn.close()
            flash("Staff account created successfully. Please log in.")
            return redirect(url_for("signin_staff"))
        except Exception as e:
            flash(f"Database error: {str(e)}", "error")
            return redirect(url_for("signup_staff"))

    return render_template("signup_staff.html")




# ---------------- Student Sign In ----------------
@app.route("/signin/student", methods=["GET","POST"])
def signin_student():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT student_id, password FROM students WHERE email=%s", (email,))
        student = cursor.fetchone()
        conn.close()

        if student and check_password_hash(student[1], password):
            try:
                otp = str(random.randint(100000, 999999))
                session["role"] = "student"       # ✅ unified role
                session["pending_email"] = email  # ✅ store email
                session["pending_otp"] = otp

                env = Environment(loader=FileSystemLoader("templates"))
                template = env.get_template("otp_template.html")
                body_html = template.render(otp=otp, role="student")
                body_text = f"Hello Student,\n\nYour login OTP is: {otp} (expires in 5 minutes)."

                send_email([email], "Your Secure Login OTP", body_text, body_html)

                flash("OTP sent to your email. Please verify.", "info")
                return redirect(url_for("verify_otp"))
            except Exception as e:
                flash(f"Error sending OTP: {str(e)}", "error")
                return redirect(url_for("signin_student"))
        else:
            flash("❌ Invalid credentials.", "error")
            return redirect(url_for("signin_student"))

    return render_template("signin_student.html")



# ---------------- Admin Sign In ----------------
@app.route("/signin/admin", methods=["GET","POST"])
def signin_admin():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT admin_id, password FROM admins WHERE email=%s", (email,))
        admin = cursor.fetchone()
        conn.close()

        if admin and check_password_hash(admin[1], password):
            try:
                otp = str(random.randint(100000, 999999))
                session["role"] = "admin"          # ✅ unified role
                session["pending_email"] = email   # ✅ store email
                session["pending_otp"] = otp
                session["admin_id"] = admin[0]     # ✅ store admin_id

                env = Environment(loader=FileSystemLoader("templates"))
                template = env.get_template("otp_template.html")
                body_html = template.render(otp=otp, role="admin")
                body_text = f"Hello Admin,\n\nYour login OTP is: {otp} (expires in 5 minutes)."

                send_email([email], "Your Admin Secure Login OTP", body_text, body_html)

                flash("OTP sent to your email. Please verify.", "info")
                return redirect(url_for("verify_otp"))
            except Exception as e:
                flash(f"Error sending OTP: {str(e)}", "error")
                return redirect(url_for("signin_admin"))
        else:
            flash("❌ Invalid credentials.", "error")
            return redirect(url_for("signin_admin"))

    return render_template("signin_admin.html")






# ---------------- Staff Sign In ----------------
@app.route("/signin/staff", methods=["GET","POST"])
def signin_staff():
    if request.method == "POST":
        email = request.form.get("email")
        password = request.form.get("password")

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT staff_id, password FROM staff WHERE email=%s", (email,))
        staff = cursor.fetchone()
        conn.close()

        if staff and check_password_hash(staff[1], password):
            try:
                otp = str(random.randint(100000, 999999))
                session["role"] = "staff"          # ✅ unified role
                session["pending_email"] = email   # ✅ store email
                session["pending_otp"] = otp
                session["staff_id"] = staff[0]     # ✅ store staff_id

                env = Environment(loader=FileSystemLoader("templates"))
                template = env.get_template("otp_template.html")
                body_html = template.render(otp=otp, role="staff")
                body_text = f"Hello Staff,\n\nYour login OTP is: {otp} (expires in 5 minutes)."

                send_email([email], "Your Staff Secure Login OTP", body_text, body_html)

                flash("OTP sent to your email. Please verify.", "info")
                return redirect(url_for("verify_otp"))
            except Exception as e:
                flash(f"Error sending OTP: {str(e)}", "error")
                return redirect(url_for("signin_staff"))
        else:
            flash("❌ Invalid credentials.", "error")
            return redirect(url_for("signin_staff"))

    return render_template("signin_staff.html")




# ---------------- Reset Password (Admin) ----------------
@app.route("/reset_password/admin", methods=["GET","POST"])
def reset_password_admin():
    if request.method == "POST":
        new_pass = request.form["new_password"]
        confirm_pass = request.form["confirm_password"]

        if new_pass == confirm_pass:
            hashed_pass = generate_password_hash(new_pass)

            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE admins SET password=%s WHERE email=%s",
                               (hashed_pass, session.get("pending_email")))
                conn.commit()
                conn.close()

                flash("Password reset successful. Please log in.")
                return redirect(url_for("signin_admin"))
            except Exception as e:
                flash(f"Database error: {str(e)}", "error")
                return redirect(url_for("reset_password_admin"))
        else:
            flash("Passwords do not match.")
            return redirect(url_for("reset_password_admin"))

    return render_template("reset_password_admin.html")



# ---------------- Reset Password (Staff) ----------------
@app.route("/reset_password/staff", methods=["GET","POST"])
def reset_password_staff():
    if request.method == "POST":
        new_pass = request.form["new_password"]
        confirm_pass = request.form["confirm_password"]

        if new_pass == confirm_pass:
            hashed_pass = generate_password_hash(new_pass)

            try:
                conn = get_connection()
                cursor = conn.cursor()
                cursor.execute("UPDATE staff SET password=%s WHERE email=%s",
                               (hashed_pass, session.get("pending_email")))
                conn.commit()
                conn.close()

                flash("Password reset successful. Please log in.")
                return redirect(url_for("signin_staff"))
            except Exception as e:
                flash(f"Database error: {str(e)}", "error")
                return redirect(url_for("reset_password_staff"))
        else:
            flash("Passwords do not match.")
            return redirect(url_for("reset_password_staff"))

    return render_template("reset_password_staff.html")



# ---------------- Verify OTP ----------------
@app.route("/verify_otp", methods=["GET","POST"])
def verify_otp():
    try:
        if request.method == "POST":
            entered_otp = request.form.get("otp")
            if entered_otp == session.get("pending_otp"):
                role = session.get("role")  # ✅ unified role

                # Case 1: Student Signup flow
                if role == "student" and session.get("student_signup"):
                    student_data = session["pending_signup"]
                    student_id = student_data["school_id"]

                    qr_path = generate_fixed_qr(student_id)

                    conn = get_connection()
                    cursor = conn.cursor()
                    cursor.execute("""
                        INSERT INTO students (full_name, school_id, email, parent_email, contact_number,
                                              strand, guardian_name, grade_level, password, security_q1,
                                              security_a1, security_q2, security_a2, security_q3, security_a3, qr_code)
                        VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)
                    """, (
                        student_data["full_name"], student_data["school_id"], student_data["email"],
                        student_data["parent_email"], student_data["contact_number"], student_data["strand"],
                        student_data["guardian_name"], student_data["grade_level"], student_data["hashed_pass"],
                        student_data["security_q1"], student_data["security_a1"], student_data["security_q2"],
                        student_data["security_a2"], student_data["security_q3"], student_data["security_a3"],
                        qr_path
                    ))
                    conn.commit()
                    conn.close()

                    flash("✅ OTP verified! Please set your PIN.", "success")
                    return redirect(url_for("setup_pin"))

                # Case 2: Student Signin flow
                elif role == "student":
                    session["email"] = session.get("pending_email")   # promote email
                    flash("✅ OTP verified! Please enter your PIN.", "success")
                    return redirect(url_for("verify_pin"))

                # Case 3: Admin Signin flow
                elif role == "admin":
                    session["email"] = session.get("pending_email")   # promote email
                    flash("✅ Admin OTP verified! Redirecting to dashboard...", "success")
                    return redirect(url_for("dashboard_admin"))

                # Case 4: Staff Signin flow
                elif role == "staff":
                    session["email"] = session.get("pending_email")   # promote email
                    flash("✅ Staff OTP verified! Redirecting to dashboard...", "success")
                    return redirect(url_for("dashboard_staff"))

                else:
                    flash("⚠️ No signup or signin context found.", "error")
                    return redirect(url_for("login"))

            else:
                flash("❌ Invalid OTP. Try again.", "error")
                return redirect(url_for("verify_otp"))

        return render_template("verify_otp.html")
    except Exception as e:
        flash(f"Error verifying OTP: {str(e)}", "error")
        return redirect(url_for("login"))







@app.route("/forgot_pin", methods=["GET", "POST"])
def forgot_pin():
    email = session.get("email")
    if not email:
        flash("Session expired. Please log in again.", "error")
        return redirect(url_for("login"))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""SELECT security_q1, security_a1, security_q2, security_a2, security_q3, security_a3 
                      FROM students WHERE email=%s""", (email,))
    record = cursor.fetchone()
    conn.close()

    if not record:
        flash("No security questions found.", "error")
        return redirect(url_for("verify_pin"))

    # Pick one random question
    questions = [(record[0], record[1]), (record[2], record[3]), (record[4], record[5])]
    question, answer = random.choice(questions)
    session["pin_reset_answer"] = answer

    if request.method == "POST":
        user_answer = request.form["answer"]
        if user_answer == session.get("pin_reset_answer"):
            return redirect(url_for("reset_pin"))
        else:
            flash("Incorrect answer.", "error")
            return redirect(url_for("forgot_pin"))

    return render_template("forgot_pin.html", question=question)


@app.route("/reset_pin", methods=["GET", "POST"])
def reset_pin():
    if request.method == "POST":
        new_pin = request.form["new_pin"]
        email = session.get("email")

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("UPDATE students SET pin=%s WHERE email=%s", (new_pin, email))
        conn.commit()
        conn.close()

        flash("PIN reset successful. Please enter your new PIN.", "success")
        return redirect(url_for("verify_pin"))

    return render_template("reset_pin.html")



@app.route("/verify_pin", methods=["GET", "POST"])
def verify_pin():
    if request.method == "POST":
        entered_pin = request.form["pin"]
        email = session.get("pending_email")  # ✅ fixed

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT student_id, pin FROM students WHERE email=%s", (email,))
        record = cursor.fetchone()
        conn.close()

        if record and str(record[1]) == str(entered_pin):
            role = session.get("role")
            if role == "student":
                session["student_id"] = record[0]  # ✅ store student_id
                session["email"] = email           # ✅ store email for dashboard queries
                return redirect(url_for("dashboard_student"))
            elif role == "admin":
                return redirect(url_for("dashboard_admin"))
            elif role == "staff":
                return redirect(url_for("dashboard_staff"))
            else:
                flash("Unknown role.", "error")
                return redirect(url_for("login_page"))
        else:
            flash("Invalid PIN. Try again.", "error")
            return redirect(url_for("verify_pin"))

    return render_template("verify_pin.html")


@app.route("/resend_otp")
def resend_otp():
    email = session.get("pending_email")
    role = session.get("role")

    if not email or not role:
        flash("No pending OTP request.", "error")
        return redirect(url_for("login"))

    generate_and_send_otp(email, subject=f"Resent {role.capitalize()} OTP Code", role=role)
    flash("A new OTP has been sent to your email.", "success")
    return redirect(url_for("verify_otp"))



# ---------------- Student Dashboard ----------------
@app.route("/dashboard/student")
def dashboard_student():
    if "email" not in session or session.get("role") != "student":
        return redirect(url_for("signin_student"))

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    # Student info
    cursor.execute("""
        SELECT student_id, full_name, school_id, grade_level, strand, balance
        FROM students WHERE email=%s
    """, (session["email"],))
    student = cursor.fetchone()

    # Transaction history
    cursor.execute("""
        SELECT
            CASE
                WHEN t.type = 'topup' THEN 'Top-Up'
                WHEN t.type = 'purchase' THEN 'Purchase'
                ELSE t.type
            END AS type,
            t.amount,
            t.created_at,
            t.status,
            COALESCE(s.full_name, a.full_name) AS performed_by
        FROM transactions t
        LEFT JOIN staff s ON t.staff_id = s.staff_id
        LEFT JOIN admins a ON t.admin_id = a.admin_id
        WHERE t.student_id = %s
        ORDER BY t.created_at DESC
    """, (student["student_id"],))
    transactions = cursor.fetchall()

    # Balance trend
    cursor.execute("""
        SELECT DATE(created_at) AS date, new_balance
        FROM transactions
        WHERE student_id=%s AND status='completed'
        ORDER BY created_at
    """, (student["student_id"],))
    balance_data = cursor.fetchall()

    balance_dates = [row["date"].strftime("%Y-%m-%d") for row in balance_data]
    balance_values = [float(row["new_balance"]) if row["new_balance"] is not None else 0.0 for row in balance_data]

    # ⚠️ Do not manually close conn here — Flask handles teardown
    # conn.close()

    # ✅ Safe render_template return
    return render_template(
        "dashboard_student.html",
        student=student,
        transactions=transactions,
        balance_dates=balance_dates,
        balance_values=balance_values
    )


# ---------------- Fixed QR ----------------
@app.route("/fixed_qr", methods=["POST"])
def fixed_qr():
    pin = request.form.get("pin")
    student_id = session.get("student_id")

    if not student_id:
        return "No student logged in", 401

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT pin, qr_code FROM students WHERE student_id=%s", (student_id,))
    record = cursor.fetchone()
    # ⚠️ Do not manually close conn here — Flask handles teardown

    if not record:
        return "Student not found", 404

    # Debug logs
    print("Entered PIN:", pin)
    print("DB PIN:", record[0])
    print("QR Path:", record[1])

    if str(record[0]).strip() == str(pin).strip():
        qr_path = record[1]
        if not qr_path or not os.path.exists(qr_path):
            return "QR file not found", 404
        return send_file(qr_path, mimetype="image/png")
    else:
        return "Invalid PIN", 401



@app.route("/download_fixed_qr")
def download_fixed_qr():
    try:
        student_id = session.get("student_id")
        if not student_id:
            flash("⚠️ No student logged in.", "error")
            return redirect(url_for("signin_student"))

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT qr_code FROM students WHERE student_id=%s", (student_id,))
        record = cursor.fetchone()
        conn.close()

        if record and record[0]:
            qr_path = record[0]

            # Ensure absolute path
            if not os.path.isabs(qr_path):
                qr_path = os.path.join(os.getcwd(), qr_path)

            if os.path.exists(qr_path):
                return send_file(
                    qr_path,
                    mimetype="image/png",
                    as_attachment=True,   # 🔹 forces download
                    download_name=f"{student_id}_fixed_qr.png"  # 🔹 sets filename
                )
            else:
                flash("❌ QR file not found on disk.", "error")
                return redirect(url_for("dashboard_student"))
        else:
            flash("❌ QR not found in database.", "error")
            return redirect(url_for("dashboard_student"))
    except Exception as e:
        flash(f"Error downloading QR: {str(e)}", "error")
        return redirect(url_for("dashboard_student"))




# ---------------- Scan Staff QR ----------------
@app.route("/scan_staff_qr", methods=["POST"])
def scan_staff_qr():
    qr_value = request.form.get("qr")

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT * FROM staff WHERE staff_qr=%s", (qr_value,))
    staff = cursor.fetchone()
    conn.close()

    if staff:
        return jsonify(success=True, staff=staff)
    else:
        return jsonify(success=False, message="Invalid staff QR"), 400



@app.route("/download_transactions_pdf")
def download_transactions_pdf():
    if "email" not in session or session.get("role") != "student":
        return redirect(url_for("signin_student"))

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)
    cursor.execute("""
        SELECT 
            CASE 
                WHEN t.type = 'Top-Up' THEN 'Top-Up'
                WHEN t.type = 'Purchase' THEN 'Purchase'
                ELSE t.type
            END AS txn_type,
            t.created_at,
            t.amount,
            COALESCE(s.full_name, a.full_name) AS performed_by
        FROM transactions t
        LEFT JOIN staff s ON t.staff_id = s.staff_id
        LEFT JOIN admins a ON t.admin_id = a.admin_id
        WHERE t.student_id = %s
        ORDER BY t.created_at DESC
    """, (session["student_id"],))
    rows = cursor.fetchall()
    conn.close()

    # 🔹 Generate PDF
    from fpdf import FPDF
    pdf = FPDF()
    pdf.add_page()
    pdf.set_font("Arial", size=12)

    pdf.cell(200, 10, txt="Transaction History", ln=True, align="C")
    pdf.ln(10)

    # Table header
    pdf.set_font("Arial", 'B', 10)
    pdf.cell(40, 10, "Type", 1)
    pdf.cell(50, 10, "Date", 1)
    pdf.cell(40, 10, "Amount", 1)
    pdf.cell(60, 10, "Performed By", 1)
    pdf.ln()

    # Table rows
    pdf.set_font("Arial", size=10)
    for row in rows:
        pdf.cell(40, 10, row["txn_type"], 1)
        pdf.cell(50, 10, str(row["created_at"]), 1)
        pdf.cell(40, 10, f"₱{row['amount']}", 1)
        pdf.cell(60, 10, row["performed_by"] if row["performed_by"] else "-", 1)
        pdf.ln()

    # Output PDF
    response = Response(pdf.output(dest="S").encode("latin-1"))
    response.headers["Content-Type"] = "application/pdf"
    response.headers["Content-Disposition"] = "attachment; filename=transactions.pdf"
    return response


# ---------------- Student Top-Up ----------------
@app.route("/topup", methods=["POST"])
def topup():
    if "email" not in session or session.get("role") != "student":
        return redirect(url_for("login_page"))

    reference_number = request.form.get("reference_number")
    amount = Decimal(request.form.get("amount"))
    method = request.form.get("payment_mode", "ewallet")
    screenshot = request.files.get("screenshot")

    # Get student_id
    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT student_id FROM students WHERE email=%s", (session["email"],))
    student = cursor.fetchone()

    if not student:
        conn.close()
        flash("Student not found.", "error")
        return redirect(url_for("dashboard_student"))

    student_id = student["student_id"]

    # Save screenshot
    screenshot_filename = None
    if screenshot:
        screenshot_filename = secure_filename(screenshot.filename)
        screenshot.save(os.path.join("static/uploads", screenshot_filename))

    # Insert into topups table only (pending)
    cursor.execute("""
        INSERT INTO topups (student_id, payment_mode, amount, reference_number, screenshot_path, status)
        VALUES (%s, %s, %s, %s, %s, %s)
    """, (student_id, payment_mode, amount, reference_number, screenshot_filename, "pending"))

    conn.commit()
    conn.close()

    flash("Top-up submitted and awaiting admin approval.", "info")
    return redirect(url_for("dashboard_student"))

@app.route("/submit_topup", methods=["POST"])
def submit_topup():
    gcash_number = request.form.get("gcash_number")
    gcash_owner = request.form.get("gcash_owner")
    reference_number = request.form.get("reference_number")
    amount = request.form.get("amount")
    proof = request.files.get("proof")

    if not all([gcash_number, gcash_owner, reference_number, amount, proof]):
        flash("All fields are required.", "error")
        return redirect(url_for("dashboard_student"))

    filename = secure_filename(proof.filename)
    proof.save(os.path.join(app.config["UPLOAD_FOLDER"], filename))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("""
        INSERT INTO topups (student_id, gcash_number, gcash_owner, reference_number, amount, proof_image, status)
        VALUES (%s, %s, %s, %s, %s, %s, 'pending')
    """, (session["student_id"], gcash_number, gcash_owner, reference_number, amount, filename))
    conn.commit()
    conn.close()

    flash("Top-up request submitted. Please wait for admin approval.", "success")
    return redirect(url_for("dashboard_student"))




# ---------------- Parent Top-Up ----------------
@app.route("/parent_topup/<int:student_id>", methods=["GET","POST"])
def parent_topup(student_id):
    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    # Get student info
    cursor.execute("SELECT student_id, full_name FROM students WHERE student_id=%s", (student_id,))
    student = cursor.fetchone()

    if not student:
        conn.close()
        flash("Student not found.", "error")
        return redirect(url_for("signup_student"))

    if request.method == "POST":
        amount = request.form["amount"]
        payment_mode = request.form["payment_mode"]
        reference_number = request.form["reference_number"]

        # Insert into topups table with pending status
        cursor.execute("""
            INSERT INTO topups (student_id, amount, payment_mode, reference_number, status, created_at)
            VALUES (%s, %s, %s, %s, 'pending', NOW())
        """, (student_id, amount, payment_mode, reference_number))
        conn.commit()
        conn.close()

        flash("Top-up request submitted successfully! Awaiting admin approval.", "success")
        return redirect(url_for("parent_topup", student_id=student_id))

    conn.close()
    return render_template("parent_topup.html", student=student)


# ---------------- Generate QR (unique each time) ----------------
@app.route("/generate_qr")
def generate_qr():
    if "student_id" not in session:
        return redirect(url_for("signin_student"))

    student_id = session["student_id"]

    # Add timestamp to make QR unique each time
    unique_data = f"{student_id}-{int(time.time())}"

    qr_img = qrcode.make(unique_data)
    img_io = io.BytesIO()
    qr_img.save(img_io, 'PNG')
    img_io.seek(0)

    return send_file(img_io, mimetype='image/png')

def generate_staff_qr(staff_id):
    qr_img = qrcode.make(staff_id)
    qr_path = f"static/staff_qrcodes/{staff_id}.png"
    os.makedirs("static/staff_qrcodes", exist_ok=True)
    qr_img.save(qr_path)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE staff SET staff_qr=%s WHERE staff_id=%s", (qr_path, staff_id))
    conn.commit()
    conn.close()
# ---------------- Admin Dashboard ----------------

@app.route('/admin/dashboard')
def dashboard_admin():
    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)


    # ✅ Fetch logged-in admin details from the admins table
    cursor.execute("SELECT full_name, email, contact_number FROM admins WHERE admin_id=%s", (session["admin_id"],))
    admin = cursor.fetchone()

    # Totals
    cursor.execute("SELECT SUM(amount) AS total FROM transactions WHERE type='topup' AND status='completed'")
    total_topups = cursor.fetchone()["total"] or 0

    cursor.execute("SELECT SUM(amount) AS total FROM transactions WHERE status='completed'")
    total_received = cursor.fetchone()["total"] or 0

    cursor.execute("SELECT SUM(amount) AS total FROM transactions WHERE type='purchase' AND status='completed'")
    total_sales = cursor.fetchone()["total"] or 0

    # Chart data: Top-Ups vs Purchases
    cursor.execute("""
        SELECT DATE(created_at) AS date,
               SUM(CASE WHEN type='topup' THEN amount ELSE 0 END) AS topups,
               SUM(CASE WHEN type='purchase' THEN amount ELSE 0 END) AS purchases
        FROM transactions
        WHERE status='completed'
        GROUP BY DATE(created_at)
        ORDER BY date
    """)
    rows = cursor.fetchall()
    txn_dates = [row["date"].strftime("%Y-%m-%d") for row in rows]
    txn_topups = [float(row["topups"]) for row in rows]
    txn_purchases = [float(row["purchases"]) for row in rows]

    # Registered students chart
    cursor.execute("""
        SELECT DATE(created_at) AS date, COUNT(*) AS count
        FROM students
        GROUP BY DATE(created_at)
        ORDER BY date
    """)
    reg_rows = cursor.fetchall()
    reg_dates = [r["date"].strftime("%Y-%m-%d") for r in reg_rows]
    reg_counts = [r["count"] for r in reg_rows]

    # Active vs inactive students
    cursor.execute("SELECT COUNT(*) AS active_count FROM students WHERE status='active'")
    active_count = cursor.fetchone()["active_count"]
    cursor.execute("SELECT COUNT(*) AS inactive_count FROM students WHERE status='inactive'")
    inactive_count = cursor.fetchone()["inactive_count"]

    # Payment distribution totals
    cursor.execute("""
        SELECT DATE(created_at) AS date,
               SUM(CASE WHEN payment_mode='cash' THEN amount ELSE 0 END) AS manual,
               SUM(CASE WHEN payment_mode='bank' THEN amount ELSE 0 END) AS cashless,
               SUM(CASE WHEN payment_mode='gcash' THEN amount ELSE 0 END) AS others
        FROM transactions
        WHERE status='completed'
        GROUP BY DATE(created_at)
        ORDER BY date
    """)
    dist_rows = cursor.fetchall()
    totals_dates = [r["date"].strftime("%Y-%m-%d") for r in dist_rows]
    manual_totals = [float(r["manual"]) for r in dist_rows]
    cashless_totals = [float(r["cashless"]) for r in dist_rows]
    other_totals = [float(r["others"]) for r in dist_rows]

    # Registered students list
    cursor.execute("SELECT student_id, school_id, full_name, balance, status, created_at FROM students ORDER BY created_at DESC")
    registered_students = cursor.fetchall()

    # Pending top-ups
    cursor.execute("SELECT * FROM topups WHERE status='pending' ORDER BY created_at DESC")
    pending_topups = cursor.fetchall()

    # Transactions list
    cursor.execute("""
        SELECT t.transaction_id, t.created_at, t.type, t.amount, t.payment_mode,
               COALESCE(s.full_name, a.full_name) AS staff_name,
               st.full_name AS customer_name, st.school_id AS student_name, t.status, t.remarks
        FROM transactions t
        LEFT JOIN staff s ON t.staff_id = s.staff_id
        LEFT JOIN admins a ON t.admin_id = a.admin_id
        LEFT JOIN students st ON t.student_id = st.student_id
        ORDER BY t.created_at DESC
    """)
    transactions = cursor.fetchall()

    # Unregistered transactions
    cursor.execute("""
        SELECT u.transaction_id, u.created_at, u.amount, u.qr_code,
               u.customer_name, u.contact_number, u.status,
               s.full_name AS staff_name
        FROM unregistered_transactions u
        LEFT JOIN staff s ON u.staff_id = s.staff_id
        ORDER BY u.created_at DESC
    """)
    unregistered_transactions = cursor.fetchall() or []


    return render_template(
        "dashboard_admin.html",
        admin=admin,  # ✅ pass the single admin record
        total_topups=total_topups,
        total_received=total_received,
        total_sales=total_sales,
        txn_dates=txn_dates,
        txn_topups=txn_topups,
        txn_purchases=txn_purchases,
        reg_dates=reg_dates,
        reg_counts=reg_counts,
        active_count=active_count,
        inactive_count=inactive_count,
        totals_dates=totals_dates,
        manual_totals=manual_totals,
        cashless_totals=cashless_totals,
        other_totals=other_totals,
        registered_students=registered_students,
        pending_topups=pending_topups,
        transactions=transactions,
        unregistered_transactions=unregistered_transactions
    )



# Manual Top-Up
@app.route('/manual_topup', methods=['POST'])
def manual_topup():
    data = request.get_json()
    student_id = data.get("student_id")   # school_id from frontend
    amount = float(data.get("amount", 0))

    conn = get_connection()
    cursor = conn.cursor()

    # Update balance
    cursor.execute("UPDATE students SET balance = balance + %s WHERE school_id=%s", (amount, student_id))

    # Insert transaction (manual top-up → payment_mode = 'cash')
    cursor.execute("""
        INSERT INTO transactions (student_id, type, amount, payment_mode, status, remarks, created_at, admin_id)
        VALUES ((SELECT student_id FROM students WHERE school_id=%s), 'topup', %s, 'cash', 'completed', 'Manual top-up', NOW(), %s)
    """, (student_id, amount, session.get("admin_id")))

    conn.commit()
    conn.close()
    return jsonify(success=True, message="Manual top-up successful")




# ---------------- Search Students ----------------
@app.route('/admin/search_students')
def search_students():
    query = request.args.get("q", "")
    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)
    cursor.execute("SELECT student_id, full_name, school_id, balance FROM students WHERE full_name LIKE %s", ("%" + query + "%",))
    results = cursor.fetchall()
    conn.close()
    return render_template('dashboard_admin.html', section='search', students=results)





@app.route("/admin/topup", methods=["POST"])
def admin_topup():
    data = request.get_json()
    student_id = data["student_id"]
    amount = float(data["amount"])

    conn = get_connection()
    cursor = conn.cursor()

    # Insert into topups table as pending (for approval)
    cursor.execute("""
        INSERT INTO topups (student_id, method, amount, status)
        VALUES (%s, 'manual', %s, 'pending')
    """, (student_id, amount))
    conn.commit()

    # Get current balance for preview
    cursor.execute("SELECT balance FROM students WHERE student_id=%s", (student_id,))
    current_balance = cursor.fetchone()[0]

    new_balance = current_balance + amount

    conn.close()

    return jsonify({"success": True, "new_balance": new_balance})


# ---------------- Approve Top-Up ----------------
@app.route("/admin/approve_topup/<int:topup_id>", methods=["POST"])
def approve_topup(topup_id):
    if "email" not in session or session.get("role") != "admin":
        flash("Unauthorized access.", "error")
        return redirect(url_for("signin_admin"))

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    # Get top-up info
    cursor.execute("""
        SELECT t.topup_id, t.student_id, t.amount, s.full_name, s.parent_email
        FROM topups t
        JOIN students s ON t.student_id = s.student_id
        WHERE t.topup_id=%s AND t.status='pending'
    """, (topup_id,))
    topup = cursor.fetchone()

    if topup:
        # Update student balance
        cursor.execute("UPDATE students SET balance = balance + %s WHERE student_id=%s",
                       (topup["amount"], topup["student_id"]))
        # Mark top-up as completed
        cursor.execute("UPDATE topups SET status='completed' WHERE topup_id=%s", (topup_id,))
        conn.commit()
        conn.close()

        # 🔹 Notify parent
        send_email(
            to=topup["parent_email"],
            subject="Top-Up Approved",
            body=f"Dear Parent,\n\nYour top-up request of ₱{topup['amount']} for {topup['full_name']} has been approved and credited.\n\nRegards,\nFCD System"
        )

        flash("Top-up approved successfully.", "success")
    else:
        conn.close()
        flash("Top-up not found or already processed.", "error")

    return redirect(url_for("admin_pending_topups"))


@app.route("/admin/reject_topup/<int:topup_id>", methods=["POST"])
def reject_topup(topup_id):
    if "email" not in session or session.get("role") != "admin":
        flash("Unauthorized access.", "error")
        return redirect(url_for("signin_admin"))

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    # Get top-up info
    cursor.execute("""
        SELECT t.topup_id, t.amount, s.full_name, s.parent_email
        FROM topups t
        JOIN students s ON t.student_id = s.student_id
        WHERE t.topup_id=%s AND t.status='pending'
    """, (topup_id,))
    topup = cursor.fetchone()

    if topup:
        cursor.execute("UPDATE topups SET status='rejected' WHERE topup_id=%s", (topup_id,))
        conn.commit()
        conn.close()

        # 🔹 Notify parent
        send_email(
            to=topup["parent_email"],
            subject="Top-Up Rejected",
            body=f"Dear Parent,\n\nYour top-up request of ₱{topup['amount']} for {topup['full_name']} has been rejected by the admin. Please contact the school office for assistance.\n\nRegards,\nFCD System"
        )

        flash("Top-up rejected.", "info")
    else:
        conn.close()
        flash("Top-up not found or already processed.", "error")

    return redirect(url_for("admin_pending_topups"))



# ---------------- Reverse Top-Up ----------------
from decimal import Decimal

@app.route("/reverse_topup/<int:transaction_id>", methods=["POST"])
def reverse_topup(transaction_id):
    if "email" not in session or session.get("role") != "admin":
        return jsonify({"success": False, "message": "Unauthorized"}), 403

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    # 🔹 Get the original transaction
    cursor.execute("""
        SELECT student_id, amount, new_balance, payment_mode
        FROM transactions
        WHERE transaction_id=%s AND type='topup' AND status='completed'
    """, (transaction_id,))
    original = cursor.fetchone()

    if not original:
        conn.close()
        return jsonify({"success": False, "message": "Transaction not found"}), 404

    student_id = original["student_id"]
    amount = Decimal(original["amount"])

    # 🔹 If new_balance is NULL, fetch current balance from students table
    if original["new_balance"] is None:
        cursor.execute("SELECT balance FROM students WHERE student_id=%s", (student_id,))
        student = cursor.fetchone()
        prev_balance = Decimal(student["balance"]) if student and student["balance"] is not None else Decimal("0.00")
    else:
        prev_balance = Decimal(original["new_balance"])

    new_balance = prev_balance - amount

    # 🔹 Insert reversal transaction
    cursor.execute("""
        INSERT INTO transactions (student_id, admin_id, amount, previous_balance, new_balance,
                                  status, remarks, created_at, type, payment_mode)
        VALUES (%s,%s,%s,%s,%s,'completed','Reversal of mistaken top-up',NOW(),'topup',%s)
    """, (
        student_id,
        session.get("admin_id"),
        -amount,              # negative amount for reversal
        prev_balance,
        new_balance,
        original["payment_mode"]
    ))

    # 🔹 Update student balance
    cursor.execute("UPDATE students SET balance=%s WHERE student_id=%s", (new_balance, student_id))

    conn.commit()
    conn.close()

    return jsonify({"success": True, "new_balance": float(new_balance)})





@app.route("/edit_transaction/<int:transaction_id>", methods=["POST"])
def edit_transaction(transaction_id):
    if "email" not in session or session.get("role") != "admin":
        return redirect(url_for("signin_admin"))

    new_amount = float(request.form["amount"])
    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    cursor.execute("SELECT student_id, amount FROM transactions WHERE transaction_id=%s", (transaction_id,))
    txn = cursor.fetchone()
    if not txn:
        conn.close()
        return jsonify({"error": "Transaction not found"}), 404

    student_id = txn["student_id"]
    old_amount = float(txn["amount"])

    # Update transaction amount
    cursor.execute("UPDATE transactions SET amount=%s WHERE transaction_id=%s", (new_amount, transaction_id))

    # Adjust student balance
    difference = new_amount - old_amount
    cursor.execute("UPDATE students SET balance = balance + %s WHERE student_id=%s", (difference, student_id))

    conn.commit()

    # Fetch updated student info
    cursor.execute("SELECT full_name, school_id, balance FROM students WHERE student_id=%s", (student_id,))
    student = cursor.fetchone()
    conn.close()

    return jsonify(student)



@app.route("/delete_transaction/<int:transaction_id>", methods=["POST"])
def delete_transaction(transaction_id):
    if "email" not in session or session.get("role") != "admin":
        return redirect(url_for("signin_admin"))

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)
    cursor.execute("DELETE FROM transactions WHERE transaction_id=%s", (transaction_id,))
    conn.commit()
    conn.close()

    flash("Transaction deleted.", "success")
    return redirect(url_for("dashboard_admin"))




# ---------------- Staff QR Generation ----------------
@app.route("/dashboard/staff")
def dashboard_staff():
    if "email" not in session or session.get("role") != "staff":
        return redirect(url_for("signin_staff"))

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    # Staff profile
    cursor.execute("SELECT staff_id, full_name, email, contact_number, created_at FROM staff WHERE email=%s",
                   (session["email"],))
    staff = cursor.fetchone() or {}

    # All transactions handled by staff
    cursor.execute("""
        SELECT t.transaction_id, st.full_name AS student_name, t.amount, t.type, t.status, t.created_at, t.customer_name
        FROM transactions t
        LEFT JOIN students st ON t.student_id = st.student_id
        WHERE t.staff_id = %s
        ORDER BY t.created_at DESC
    """, (session["staff_id"],))
    staff_transactions = cursor.fetchall() or []

    # ✅ Today’s transactions only
    cursor.execute("""
        SELECT t.transaction_id, st.full_name AS student_name, t.amount, t.type, t.status, t.created_at, t.customer_name
        FROM transactions t
        LEFT JOIN students st ON t.student_id = st.student_id
        WHERE t.staff_id = %s AND DATE(t.created_at) = CURDATE()
        ORDER BY t.created_at DESC
    """, (session["staff_id"],))
    todays_transactions = cursor.fetchall() or []

    # Daily totals (raw table)
    cursor.execute("SELECT created_at, amount, mode, category FROM staff_totals")
    staff_totals = cursor.fetchall() or []

    # --- Chart datasets ---
    cursor.execute("""
        SELECT DATE(created_at) AS date, type, COUNT(*) AS cnt
        FROM transactions
        WHERE staff_id=%s
        GROUP BY DATE(created_at), type
        ORDER BY date
    """, (session["staff_id"],))
    txn_data = cursor.fetchall()
    txn_dates = sorted(set([row["date"].strftime("%Y-%m-%d") for row in txn_data]))
    txn_topups = [sum(row["cnt"] for row in txn_data if row["date"].strftime("%Y-%m-%d")==d and row["type"]=="topup") for d in txn_dates]
    txn_purchases = [sum(row["cnt"] for row in txn_data if row["date"].strftime("%Y-%m-%d")==d and row["type"]=="purchase") for d in txn_dates]

    cursor.execute("""
        SELECT DATE(created_at) AS date, mode, SUM(amount) AS total
        FROM staff_totals
        GROUP BY DATE(created_at), mode
        ORDER BY date
    """)
    totals_data = cursor.fetchall()
    totals_dates = sorted(set([row["date"].strftime("%Y-%m-%d") for row in totals_data]))
    manual_totals = [sum(row["total"] for row in totals_data if row["date"].strftime("%Y-%m-%d")==d and row["mode"]=="manual") for d in totals_dates]
    cashless_totals = [sum(row["total"] for row in totals_data if row["date"].strftime("%Y-%m-%d")==d and row["mode"]=="cashless") for d in totals_dates]
    other_totals = [sum(row["total"] for row in totals_data if row["date"].strftime("%Y-%m-%d")==d and row["mode"]=="others") for d in totals_dates]

    # --- Summary totals for cards ---
    cursor.execute("""
        SELECT SUM(amount) AS total
        FROM transactions
        WHERE staff_id=%s AND DATE(created_at)=CURDATE()
    """, (session["staff_id"],))
    todays_total = cursor.fetchone()["total"] or 0

    cursor.execute("""
        SELECT SUM(amount) AS total
        FROM transactions
        WHERE staff_id=%s
    """, (session["staff_id"],))
    total_sales = cursor.fetchone()["total"] or 0

    cursor.execute("""
        SELECT SUM(amount) AS total
        FROM transactions
        WHERE staff_id=%s AND student_id IS NULL
    """, (session["staff_id"],))
    visitors_total = cursor.fetchone()["total"] or 0

    return render_template("dashboard_staff.html",
                           staff=staff,
                           staff_id=session["staff_id"],
                           staff_transactions=staff_transactions,
                           todays_transactions=todays_transactions,
                           staff_totals=staff_totals,
                           txn_dates=txn_dates,
                           txn_topups=txn_topups,
                           txn_purchases=txn_purchases,
                           totals_dates=totals_dates,
                           manual_totals=manual_totals,
                           cashless_totals=cashless_totals,
                           other_totals=other_totals,
                           todays_total=todays_total,
                           total_sales=total_sales,
                           visitors_total=visitors_total)

# Scan QR
@app.route("/staff_qr_transaction", methods=["POST"])
def staff_qr_transaction():
    data = request.get_json()
    student_qr = data.get("studentQr")
    amount = data.get("amount")
    mode = data.get("mode")
    cart = data.get("cart", [])

    student = Student.query.filter_by(qr_code=student_qr).first()
    if not student:
        return jsonify({"success": False, "message": "Student not found!"})

    if student.balance < amount:
        return jsonify({"success": False, "message": "Insufficient balance!"})

    student.balance -= amount
    txn = Transaction(student_id=student.id, amount=amount, mode=mode, items=json.dumps(cart))
    db.session.add_all([student, txn])
    db.session.commit()

    return jsonify({"success": True, "student_name": student.name})

# Search Student
@app.route("/staff_search_student_transaction", methods=["POST"])
def staff_search_student_transaction():
    try:
        data = request.get_json()
        print("Incoming payload:", data)  # ✅ Debug print

        school_id = data.get("school_id")
        amount = float(data.get("amount", 0))
        cart = data.get("cart", [])

        # Lookup student by school_id
        student = Student.query.filter_by(school_id=school_id).first()
        if not student:
            return jsonify({"success": False, "message": "Student not found!"})

        # Ensure balance is numeric
        if student.balance is None:
            student.balance = 0

        if student.balance < amount:
            return jsonify({"success": False, "message": "Insufficient balance!"})

        # Deduct balance
        student.balance -= amount

        # Record transaction
        txn = Transaction(
            student_id=student.id,
            amount=amount,
            items=json.dumps(cart)  # ✅ cart must be serializable
        )
        db.session.add_all([student, txn])
        db.session.commit()

        return jsonify({"success": True, "student_name": student.full_name})

    except Exception as e:
        print("Error in staff_search_student_transaction:", e)  # ✅ Debug print
        db.session.rollback()
        return jsonify({"success": False, "message": "Server error"})


# Unregistered Student
@app.route("/staff_unregistered_transaction", methods=["POST"])
def staff_unregistered_transaction():
    data = request.get_json()
    school_id = data.get("schoolId")
    amount = data.get("amount")
    mode = data.get("mode")
    cart = data.get("cart", [])

    txn = Transaction(unregistered_id=school_id, amount=amount, mode=mode, items=json.dumps(cart))
    db.session.add(txn)
    db.session.commit()

    return jsonify({"success": True, "message": "Unregistered transaction recorded!"})

# Visitor/Personnel
@app.route("/staff_visitor_transaction", methods=["POST"])
def staff_visitor_transaction():
    data = request.get_json()
    amount = data.get("amount")
    mode = data.get("mode")
    cart = data.get("cart", [])

    txn = Transaction(visitor=True, amount=amount, mode=mode, items=json.dumps(cart))
    db.session.add(txn)
    db.session.commit()

    return jsonify({"success": True, "message": "Visitor transaction recorded!"})


@app.route("/purchase_unregistered", methods=["POST"])
def purchase_unregistered():
    if "staff_id" not in session:
        return redirect(url_for("login"))

    customer_name = request.form["customer_name"]
    amount = float(request.form["amount"])

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    cursor.execute("""
        INSERT INTO transactions (student_id, customer_name, staff_id, amount, status, type, payment_mode, created_at)
        VALUES (NULL, %s, %s, %s, 'completed', 'purchase', 'cash', NOW())
    """, (customer_name, session["staff_id"], amount))

    conn.commit()
    conn.close()

    flash("Unregistered purchase recorded successfully.", "success")
    return redirect(url_for("dashboard_admin"))


@app.route("/staff_students")
def staff_students():
    school_id = request.args.get("id")
    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)


    if school_id:
        cursor.execute("SELECT student_id, full_name, school_id, grade_level, strand, balance FROM students WHERE school_id=%s", (school_id,))
        student = cursor.fetchone()
        conn.close()
        if student:
            return jsonify(success=True, student=student)
        else:
            return jsonify(success=False, message="Not found")
    else:
        cursor.execute("SELECT student_id, full_name, school_id, grade_level, strand, balance FROM students")
        students = cursor.fetchall()
        conn.close()
        return jsonify(success=True, students=students)


@app.route("/staff_record_transaction", methods=["POST"])
def staff_record_transaction():
    data = request.get_json()
    txn_type = data.get("type")
    staff_id = session.get("staff_id")  # logged-in staff

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    try:
        # ✅ Case 1: QR Scan (registered student)
        if txn_type == "qr":
            qr_code = data.get("qr_code")
            amount = Decimal(data.get("amount", 0))

            cursor.execute("SELECT student_id, full_name, balance FROM students WHERE qr_code=%s", (qr_code,))
            student = cursor.fetchone()

            if student:
                if student["balance"] >= amount:
                    new_balance = student["balance"] - amount
                    cursor.execute("UPDATE students SET balance=%s WHERE student_id=%s",
                                   (new_balance, student["student_id"]))
                    cursor.execute("""
                        INSERT INTO transactions (student_id, staff_id, amount, previous_balance, new_balance,
                                                  status, type, created_at)
                        VALUES (%s,%s,%s,%s,%s,'completed','purchase',%s)
                    """, (student["student_id"], staff_id, amount, student["balance"], new_balance,
                          datetime.datetime.now()))
                    conn.commit()
                    return jsonify(success=True, transaction={
                        "student_name": student["full_name"],
                        "amount": float(amount),
                        "type": "purchase",
                        "status": "completed",
                        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                else:
                    return jsonify(success=False, message="Insufficient balance.")
            else:
                return jsonify(success=False, message="Student not found.")

        # ✅ Case 2: Search Student (manual entry)
        elif txn_type == "student":
            student_id = data.get("student_id")
            amount = Decimal(data.get("amount", 0))

            cursor.execute("SELECT student_id, full_name, balance FROM students WHERE school_id=%s", (student_id,))
            student = cursor.fetchone()

            if student:
                if student["balance"] >= amount:
                    new_balance = student["balance"] - amount
                    cursor.execute("UPDATE students SET balance=%s WHERE student_id=%s",
                                   (new_balance, student["student_id"]))
                    cursor.execute("""
                        INSERT INTO transactions (student_id, staff_id, amount, previous_balance, new_balance,
                                                  status, type, created_at)
                        VALUES (%s,%s,%s,%s,%s,'completed','purchase',%s)
                    """, (student["student_id"], staff_id, amount, student["balance"], new_balance,
                          datetime.datetime.now()))
                    conn.commit()
                    return jsonify(success=True, transaction={
                        "student_name": student["full_name"],
                        "amount": float(amount),
                        "type": "purchase",
                        "status": "completed",
                        "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
                    })
                else:
                    return jsonify(success=False, message="Insufficient balance.")
            else:
                return jsonify(success=False, message="Student not found.")

        # ✅ Case 3: Unregistered Student
        elif txn_type == "unregistered":
            school_id = data.get("student_id")
            amount = Decimal(data.get("amount", 0))
            mode = data.get("mode")

            cursor.execute("""
                INSERT INTO transactions (customer_name, staff_id, amount, status, type, payment_mode, created_at)
                VALUES (%s,%s,%s,'completed','purchase',%s,%s)
            """, (school_id, staff_id, amount, mode, datetime.datetime.now()))
            conn.commit()
            return jsonify(success=True, transaction={
                "customer_name": school_id,
                "amount": float(amount),
                "type": "purchase",
                "status": "completed",
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        # ✅ Case 4: Visitor/Personnel
        elif txn_type == "visitor":
            amount = Decimal(data.get("amount", 0))
            mode = data.get("mode")

            cursor.execute("""
                INSERT INTO transactions (customer_name, staff_id, amount, status, type, payment_mode, created_at)
                VALUES ('Visitor',%s,%s,'completed','purchase',%s,%s)
            """, (staff_id, amount, mode, datetime.datetime.now()))
            conn.commit()
            return jsonify(success=True, transaction={
                "customer_name": "Visitor",
                "amount": float(amount),
                "type": "purchase",
                "status": "completed",
                "created_at": datetime.datetime.now().strftime("%Y-%m-%d %H:%M:%S")
            })

        else:
            return jsonify(success=False, message="Invalid transaction type.")

    except Exception as e:
        conn.rollback()
        return jsonify(success=False, message=str(e))
    finally:
        conn.close()



# ---------------- Staff Registered Student Purchase ----------------
@app.route("/staff_transaction", methods=["POST"])
def staff_transaction():
    if "email" not in session or session.get("role") != "staff":
        return redirect(url_for("signin_staff"))

    student_id = request.form["student_id"]
    amount = float(request.form["amount"])

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    # Check balance
    cursor.execute("SELECT balance FROM students WHERE student_id=%s", (student_id,))
    student = cursor.fetchone()
    if not student:
        flash("Student not found.", "error")
        conn.close()
        return redirect(url_for("dashboard_staff"))

    balance = student[0]
    if balance < amount:
        flash("Insufficient balance.", "error")
        conn.close()
        return redirect(url_for("dashboard_staff"))

    # Deduct balance
    cursor.execute("UPDATE students SET balance = balance - %s WHERE student_id=%s", (amount, student_id))
    conn.commit()

    # ✅ Record the purchase transaction with proper casing
    cursor.execute("""INSERT INTO transactions (student_id, staff_id, amount, type, created_at)
                      VALUES (%s,%s,%s,'Purchase',NOW())""",
                   (student_id, session["staff_id"], amount))
    conn.commit()

    conn.close()
    flash("Purchase recorded successfully!", "success")
    return redirect(url_for("dashboard_staff"))



# ---------------- Manual Input for Unregistered Students ----------------


@app.route("/unregistered_transactions")
def unregistered_transactions():
    if "email" not in session or session.get("role") != "admin":
        return redirect(url_for("signin_admin"))

    conn = get_connection()
    cursor = conn.cursor(cursorclass=MySQLdb.cursors.DictCursor)

    cursor.execute("""
        SELECT ut.transaction_id, ut.customer_name, ut.amount, ut.payment_mode,
               ut.status, ut.created_at, s.full_name AS staff_name
        FROM unregistered_transactions ut
        LEFT JOIN staff s ON ut.staff_id = s.staff_id
        ORDER BY ut.created_at DESC
    """)
    rows = cursor.fetchall()
    conn.close()

    return render_template("dashboard_admin.html", unregistered_transactions=rows)



# ---------------- Real-Time QR Scanning (token lookup) ----------------






# ---------------- Confirm Transaction ----------------
@app.route("/confirm_transaction", methods=["GET","POST"])
def confirm_transaction():
    if "pending_txn" not in session:
        return "No transaction pending"

    txn_id = session["pending_txn"]
    if request.method == "POST":
        pin_entered = request.form["pin"]

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT student_id, amount FROM transactions WHERE transaction_id=%s", (txn_id,))
        txn = cursor.fetchone()
        student_id, amount = txn

        cursor.execute("SELECT pin, balance, email FROM students WHERE student_id=%s", (student_id,))
        student = cursor.fetchone()
        pin, balance, email = student

        if pin_entered == pin and balance >= amount:
            new_balance = balance - amount
            cursor.execute("UPDATE students SET balance=%s WHERE student_id=%s", (new_balance, student_id))
            cursor.execute("UPDATE transactions SET status='confirmed' WHERE transaction_id=%s", (txn_id,))
            conn.commit()
            conn.close()

            send_email(email, "Transaction Confirmed",
                       f"Your purchase of {amount} has been confirmed. Remaining balance: {new_balance}.")
            session.pop("pending_txn", None)
            return "Transaction successful!"
        else:
            cursor.execute("UPDATE transactions SET status='failed' WHERE transaction_id=%s", (txn_id,))
            conn.commit()
            conn.close()
            session.pop("pending_txn", None)
            return "Invalid PIN or insufficient balance"

    return '''
        <h2>Confirm Transaction</h2>
        <form method="POST">
            <label>Enter 4-digit PIN:</label>
            <input type="password" name="pin" maxlength="4" required><br><br>
            <button type="submit">Confirm</button>
        </form>
    '''

# ---------------- Run App ----------------
if __name__ == "__main__":
    os.makedirs("static/topups", exist_ok=True)
    os.makedirs("static/qrcodes", exist_ok=True)
    print("Starting Flask server...")
    app.run(debug=True)
