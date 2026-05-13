from werkzeug.security import generate_password_hash, check_password_hash
from flask import Flask, render_template, request, redirect, url_for, session, flash, Response, send_file, jsonify
import os, mysql.connector, random, datetime, uuid, io, re
from werkzeug.utils import secure_filename
from sendgrid import SendGridAPIClient
from sendgrid.helpers.mail import Mail, Email
import qrcode
from jinja2 import Environment, FileSystemLoader

# ---------------- Flask Config ----------------
app = Flask(__name__)
app.secret_key = "secretkey"

# ---------------- Database Connection ----------------
def get_connection():
    return mysql.connector.connect(
        host="localhost",
        port=3307,
        user="school_user",
        password="qrcode12345!",
        database="school_system",
        autocommit=True
    )

# ---------------- Email Function ----------------
SENDGRID_API_KEY = os.environ.get("SENDGRID_API_KEY")
FROM_EMAIL = Email("hyckotoshi@gmail.com", name="FCD Central Institute")

def send_email(to_email, subject, body_text=None, body_html=None):
    message = Mail(
        from_email=FROM_EMAIL,
        to_emails=to_email,
        subject=subject,
        plain_text_content=body_text if body_text else "",
        html_content=body_html if body_html else body_text
    )
    try:
        sg = SendGridAPIClient(SENDGRID_API_KEY)
        response = sg.send(message)
        print(f"Email sent to {to_email}, status code: {response.status_code}")
        return response
    except Exception as e:
        print(f"Error sending email: {str(e)}")
        return None

# ---------------- Password Validation ----------------
def is_strong_password(password):
    if len(password) < 8: return False
    if not re.search(r"\d", password): return False
    if not re.search(r"[!@#$%^&*(),.?\":{}|<>]", password): return False
    return True

# ---------------- OTP Function ----------------
def generate_and_send_otp(email, subject="Your Secure Login OTP", role="student"):
    otp = str(random.randint(100000, 999999))
    expires = datetime.datetime.now() + datetime.timedelta(minutes=5)
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO otps (email, otp_code, expires_at) VALUES (%s,%s,%s)", (email, otp, expires))
    conn.commit()
    conn.close()

    body_text = f"Your OTP is: {otp} (expires in 5 minutes)."
    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("otp_template.html")
    body_html = template.render(otp=otp, role=role)

    send_email(email, subject, body_text, body_html)
    return otp

# ---------------- Root Route ----------------
@app.route("/")
def index():
    return render_template("index.html")


# ---------------- Student Signup ----------------
@app.route("/signup/student", methods=["GET","POST"])
def signup_student():
    if request.method == "POST":
        try:
            password = request.form["password"]
            if not is_strong_password(password):
                flash("Password must be at least 8 characters and include a number and special character.", "error")
                return redirect(url_for("signup_student"))
            hashed_pass = generate_password_hash(password)
            pin_value = request.form["pin"]
            data = (
                request.form["full_name"], request.form["school_id"], request.form["email"],
                request.form["contact_number"], request.form["strand"], request.form["guardian_name"],
                request.form["parent_email"], request.form["grade_level"],
                hashed_pass, pin_value,
                request.form["security_q1"], request.form["security_a1"],
                request.form["security_q2"], request.form["security_a2"],
                request.form["security_q3"], request.form["security_a3"]
            )
            conn = get_connection()
            cursor = conn.cursor()
            cursor.execute("""INSERT INTO students
                (full_name, school_id, email, contact_number, strand, guardian_name, parent_email, grade_level,
                 password, pin, security_q1, security_a1, security_q2, security_a2, security_q3, security_a3)
                VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s,%s)""", data)
            conn.commit()
            cursor.execute("SELECT full_name, email FROM students WHERE email=%s", (request.form["email"],))
            student = cursor.fetchone()
            conn.close()
            if student:
                flash(f"Signup successful for {student[0]} ({student[1]}). Please log in.", "success")
                return redirect(url_for("signin_student"))
            else:
                flash("Signup failed. Please try again.", "error")
                return redirect(url_for("signup_student"))
        except Exception as e:
            flash(f"Database error: {str(e)}", "error")
            return redirect(url_for("signup_student"))
    return render_template("signup_student.html")

# ---------------- Admin Sign In ----------------
@app.route("/signin/admin", methods=["GET","POST"])
def signin_admin():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT admin_id, email, password FROM admins WHERE email=%s", (email,))
        admin = cursor.fetchone()
        conn.close()
        if admin and check_password_hash(admin[2], password):
            session["pending_email"] = admin[1]
            session["role"] = "admin"
            session["admin_id"] = admin[0]
            generate_and_send_otp(email, subject="Your Admin OTP Code", role="admin")
            return redirect(url_for("verify_otp"))
        else:
            flash("Invalid admin credentials.", "error")
            return redirect(url_for("signin_admin"))
    return render_template("signin_admin.html")

# ---------------- Staff Sign In ----------------
@app.route("/signin/staff", methods=["GET","POST"])
def signin_staff():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT staff_id, email, password FROM staff WHERE email=%s", (email,))
        staff = cursor.fetchone()
        conn.close()
        if staff and check_password_hash(staff[2], password):
            session["pending_email"] = staff[1]
            session["role"] = "staff"
            session["staff_id"] = staff[0]
            generate_and_send_otp(email, subject="Your Staff OTP Code", role="staff")
            return redirect(url_for("verify_otp"))
        else:
            flash("Invalid staff credentials.", "error")
            return redirect(url_for("signin_staff"))
    return render_template("signin_staff.html")

# ---------------- Verify OTP ----------------
@app.route("/verify_otp", methods=["GET","POST"])
def verify_otp():
    if request.method == "POST":
        otp = request.form["otp"]
        email = session.get("pending_email")
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT otp_code, expires_at FROM otps WHERE email=%s ORDER BY id DESC LIMIT 1", (email,))
        record = cursor.fetchone()
        conn.close()
        if record and record[0] == otp and datetime.datetime.now() < record[1]:
            session["email"] = email
            role = session["role"]
            if role == "student":
                return redirect(url_for("dashboard_student"))
            elif role == "admin":
                return redirect(url_for("dashboard_admin"))
            else:
                return redirect(url_for("dashboard_staff"))
        else:
            return "Invalid or expired OTP"
    return render_template("otp.html")

# ---------------- Student Dashboard ----------------
@app.route("/dashboard/student")
def dashboard_student():
    if "email" not in session or session.get("role") != "student":
        return redirect(url_for("signin_student"))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("""SELECT student_id, full_name, school_id, grade_level, strand, balance
                      FROM students WHERE student_id=%s""", (session["student_id"],))
    student = cursor.fetchone()
    cursor.execute("""
        SELECT CASE
                 WHEN t.type = 'topup' THEN 'Top-Up'
                 WHEN t.type = 'purchase' THEN 'Purchase'
                 ELSE t.type
               END AS txn_type,
               t.amount, t.created_at,
               COALESCE(s.full_name, a.full_name) AS performed_by
        FROM transactions t
        LEFT JOIN staff s ON t.staff_id = s.staff_id
        LEFT JOIN admins a ON t.admin_id = a.admin_id
        WHERE t.student_id = %s
        ORDER BY t.created_at DESC
    """, (student["student_id"],))
    history = cursor.fetchall()
    conn.close()
    return render_template("dashboard_student.html", student=student, history=history)

# ---------------- Admin Dashboard ----------------
@app.route("/dashboard/admin")
def dashboard_admin():
    if "email" not in session or session.get("role") != "admin":
        return redirect(url_for("signin_admin"))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT student_id, full_name, school_id, email, balance FROM students")
    students = cursor.fetchall()
    cursor.execute("SELECT topup_id, student_id, method, amount, screenshot_path, created_at FROM topups WHERE status='pending'")
    pending_topups = cursor.fetchall()
    cursor.execute("""
        SELECT t.transaction_id, st.school_id, st.full_name AS student_name,
               t.amount, t.created_at, t.type,
               COALESCE(s.full_name, a.full_name) AS performed_by, t.student_id
        FROM transactions t
        JOIN students st ON t.student_id = st.student_id
        LEFT JOIN staff s ON t.staff_id = s.staff_id
        LEFT JOIN admins a ON t.admin_id = a.admin_id
        ORDER BY t.created_at DESC
    """)
    transactions = cursor.fetchall()
    cursor.execute("SELECT COUNT(*) AS total_students FROM students")
    total_students = cursor.fetchone()["total_students"]
    cursor.execute("SELECT COUNT(*) AS unregistered FROM unregistered_students")
    unregistered = cursor.fetchone()["unregistered"]
    cursor.execute("SELECT SUM(amount) AS topups_today FROM transactions WHERE DATE(created_at)=CURDATE() AND type='topup'")
    topups_today = cursor.fetchone()["topups_today"] or 0
    cursor.execute("SELECT SUM(balance) AS overall_balance FROM students")
    overall_balance = cursor.fetchone()["overall_balance"] or 0
    conn.close()
    return render_template("dashboard_admin.html",
                           students=students,
                           pending_topups=pending_topups,
                           transactions=transactions,
                           total_students=total_students,
                           unregistered=unregistered,
                           topups_today=topups_today,
                           overall_balance=overall_balance)

# ---------------- Manual Top-Up ----------------
@app.route("/manual_topup/<int:student_id>", methods=["POST"])
def manual_topup(student_id):
    if "email" not in session or session.get("role") != "admin":
        return redirect(url_for("signin_admin"))

    amount = float(request.form["amount"])
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Update balance
    cursor.execute("UPDATE students SET balance = balance + %s WHERE student_id=%s", (amount, student_id))

    # Record transaction
    cursor.execute("""
        INSERT INTO transactions (student_id, admin_id, amount, type, created_at)
        VALUES (%s, %s, %s, 'topup', NOW())
    """, (student_id, session["admin_id"], amount))
    conn.commit()

    # Fetch updated student info
    cursor.execute("SELECT full_name, school_id, balance, email, parent_email FROM students WHERE student_id=%s", (student_id,))
    student = cursor.fetchone()
    conn.close()

    # Send notifications
    send_email(student["email"], "Manual Top-Up Confirmed",
               f"Your account has been topped up with ₱{amount:.2f}. "
               f"Your new balance is ₱{student['balance']:.2f}.")
    send_email(student["parent_email"], "Manual Top-Up for Your Child",
               f"{student['full_name']} received a manual top-up of ₱{amount:.2f}. "
               f"Their new balance is ₱{student['balance']:.2f}.")

    flash("Manual top-up completed successfully.", "success")
    return redirect(url_for("dashboard_admin"))

# ---------------- Approve Top-Up ----------------
@app.route("/approve_topup/<int:topup_id>", methods=["POST"])
def approve_topup(topup_id):
    if "email" not in session or session.get("role") != "admin":
        return redirect(url_for("signin_admin"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT student_id, amount FROM topups WHERE topup_id=%s", (topup_id,))
    topup = cursor.fetchone()
    if not topup:
        conn.close()
        flash("Top-up request not found.", "danger")
        return redirect(url_for("dashboard_admin"))

    student_id = topup["student_id"]
    amount = topup["amount"]

    cursor.execute("UPDATE students SET balance = balance + %s WHERE student_id=%s", (amount, student_id))
    cursor.execute("UPDATE topups SET status='approved' WHERE topup_id=%s", (topup_id,))
    cursor.execute("""
        INSERT INTO transactions (student_id, admin_id, amount, type, created_at)
        VALUES (%s, %s, %s, 'topup', NOW())
    """, (student_id, session["admin_id"], amount))
    conn.commit()

    cursor.execute("SELECT full_name, balance, email, parent_email FROM students WHERE student_id=%s", (student_id,))
    student = cursor.fetchone()
    conn.close()

    send_email(student["email"], "Top-Up Approved",
               f"Your top-up of ₱{amount:.2f} has been approved. "
               f"New balance: ₱{student['balance']:.2f}.")
    send_email(student["parent_email"], "Top-Up Approved for Your Child",
               f"{student['full_name']} had a top-up of ₱{amount:.2f} approved. "
               f"New balance: ₱{student['balance']:.2f}.")

    flash("Top-up approved successfully.", "success")
    return redirect(url_for("dashboard_admin"))

# ---------------- Reject Top-Up ----------------
@app.route("/reject_topup/<int:topup_id>", methods=["POST"])
def reject_topup(topup_id):
    if "email" not in session or session.get("role") != "admin":
        return redirect(url_for("signin_admin"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("UPDATE topups SET status='rejected' WHERE topup_id=%s", (topup_id,))
    conn.commit()

    cursor.execute("SELECT student_id FROM topups WHERE topup_id=%s", (topup_id,))
    student_id = cursor.fetchone()["student_id"]
    cursor.execute("SELECT full_name, email, parent_email FROM students WHERE student_id=%s", (student_id,))
    student = cursor.fetchone()
    conn.close()

    send_email(student["email"], "Top-Up Rejected",
               "Your top-up request was rejected. Please contact admin.")
    send_email(student["parent_email"], "Top-Up Rejected for Your Child",
               f"{student['full_name']}'s top-up request was rejected.")

    flash("Top-up rejected.", "danger")
    return redirect(url_for("dashboard_admin"))


# ---------------- QR Routes ----------------
@app.route("/generate_qr")
def generate_qr():
    if "student_id" not in session:
        return redirect(url_for("signin_student"))
    student_id = session["student_id"]
    token = str(uuid.uuid4())
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO qr_tokens (student_id, token, created_at) VALUES (%s,%s,NOW())", (student_id, token))
    conn.commit()
    conn.close()
    qr_img = qrcode.make(token)
    img_io = io.BytesIO()
    qr_img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')


# ---------------- Edit Transaction ----------------
@app.route("/edit_transaction/<int:transaction_id>", methods=["POST"])
def edit_transaction(transaction_id):
    if "email" not in session or session.get("role") != "admin":
        return redirect(url_for("signin_admin"))

    new_amount = float(request.form["amount"])
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)
    cursor.execute("SELECT student_id, amount FROM transactions WHERE transaction_id=%s", (transaction_id,))
    txn = cursor.fetchone()
    if not txn:
        conn.close()
        return jsonify({"error": "Transaction not found"}), 404

    student_id = txn["student_id"]
    old_amount = float(txn["amount"])

    cursor.execute("UPDATE transactions SET amount=%s WHERE transaction_id=%s", (new_amount, transaction_id))
    difference = new_amount - old_amount
    cursor.execute("UPDATE students SET balance = balance + %s WHERE student_id=%s", (difference, student_id))
    conn.commit()

    cursor.execute("SELECT full_name, school_id, balance, email, parent_email FROM students WHERE student_id=%s", (student_id,))
    student = cursor.fetchone()
    conn.close()

    send_email(student["email"], "Transaction Updated",
               f"Your transaction was updated from ₱{old_amount:.2f} to ₱{new_amount:.2f}. "
               f"New balance: ₱{student['balance']:.2f}.")
    send_email(student["parent_email"], "Transaction Updated for Your Child",
               f"{student['full_name']}'s transaction was updated from ₱{old_amount:.2f} to ₱{new_amount:.2f}. "
               f"New balance: ₱{student['balance']:.2f}.")

    return jsonify(student)

# ---------------- Delete Transaction ----------------
@app.route("/delete_transaction/<int:transaction_id>", methods=["POST"])
def delete_transaction(transaction_id):
    if "email" not in session or session.get("role") != "admin":
        return redirect(url_for("signin_admin"))
    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("DELETE FROM transactions WHERE transaction_id=%s", (transaction_id,))
    conn.commit()
    conn.close()
    flash("Transaction deleted.", "success")
    return redirect(url_for("dashboard_admin"))

@app.route("/fixed_qr")
def fixed_qr():
    if "student_id" not in session:
        return redirect(url_for("signin_student"))
    student_id = session["student_id"]
    qr_img = qrcode.make(student_id)
    img_io = io.BytesIO()
    qr_img.save(img_io, 'PNG')
    img_io.seek(0)
    return send_file(img_io, mimetype='image/png')

# ---------------- Staff Dashboard ----------------
@app.route("/dashboard/staff")
def dashboard_staff():
    if "email" not in session or session.get("role") != "staff":
        return redirect(url_for("signin_staff"))

    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Registered transactions
    cursor.execute("SELECT * FROM transactions WHERE staff_id=%s ORDER BY created_at DESC", (session.get("staff_id"),))
    registered_txns = cursor.fetchall()

    # Unregistered transactions
    cursor.execute("SELECT * FROM unregistered_transactions WHERE staff_id=%s ORDER BY created_at DESC", (session.get("staff_id"),))
    unregistered_txns = cursor.fetchall()

    conn.close()
    return render_template("dashboard_staff.html",
                           registered_txns=registered_txns,
                           unregistered_txns=unregistered_txns)

# ---------------- Staff Purchase ----------------
@app.route("/purchase/<int:student_id>", methods=["POST"])
def purchase(student_id):
    if "email" not in session or session.get("role") != "staff":
        return redirect(url_for("signin_staff"))

    amount = float(request.form.get("amount"))
    conn = get_connection()
    cursor = conn.cursor(dictionary=True)

    # Deduct from student balance
    cursor.execute("UPDATE students SET balance = balance - %s WHERE student_id=%s", (amount, student_id))

    # Record transaction
    cursor.execute("""
        INSERT INTO transactions (student_id, staff_id, amount, type, created_at)
        VALUES (%s, %s, %s, 'purchase', NOW())
    """, (student_id, session["staff_id"], amount))
    conn.commit()
    conn.close()

    flash("Purchase recorded successfully.", "success")
    return redirect(url_for("dashboard_staff"))

# ---------------- Staff Transaction (Registered Student) ----------------
@app.route("/staff_transaction", methods=["POST"])
def staff_transaction():
    if "email" not in session or session.get("role") != "staff":
        return redirect(url_for("signin_staff"))

    student_id = request.form["student_id"]
    amount = float(request.form["amount"])

    conn = get_connection()
    cursor = conn.cursor()

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

    # Record transaction
    cursor.execute("""
        INSERT INTO transactions (student_id, staff_id, amount, type, created_at)
        VALUES (%s,%s,%s,'purchase',NOW())
    """, (student_id, session["staff_id"], amount))
    conn.commit()
    conn.close()

    flash("Purchase recorded successfully!", "success")
    return redirect(url_for("dashboard_staff"))

# ---------------- Staff Transaction (Unregistered Student) ----------------
@app.route("/staff_unregistered_transaction", methods=["POST"])
def staff_unregistered_transaction():
    if "email" not in session or session.get("role") != "staff":
        return redirect(url_for("signin_staff"))

    school_id = request.form["school_id"]
    amount = float(request.form["amount"])

    conn = get_connection()
    cursor = conn.cursor()
    staff_id = session.get("staff_id")

    cursor.execute("INSERT INTO unregistered_transactions (school_id, amount, staff_id) VALUES (%s,%s,%s)",
                   (school_id, amount, staff_id))
    conn.commit()
    conn.close()

    flash("Unregistered student transaction recorded.", "success")
    return redirect(url_for("dashboard_staff"))

# ---------------- QR Scan ----------------
@app.route("/scan_qr", methods=["POST"])
def scan_qr():
    if "role" not in session or session["role"] != "staff":
        return redirect(url_for("signin_staff"))

    token = request.form["student_id"]
    amount = float(request.form["amount"])

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT student_id FROM qr_tokens WHERE token=%s ORDER BY created_at DESC LIMIT 1", (token,))
    record = cursor.fetchone()
    if not record:
        conn.close()
        flash("Invalid QR code.", "error")
        return redirect(url_for("dashboard_staff"))

    student_id = record[0]

    # Deduct balance
    cursor.execute("UPDATE students SET balance = balance - %s WHERE student_id=%s", (amount, student_id))
    conn.commit()

    # Record transaction
    cursor.execute("""
        INSERT INTO transactions (student_id, staff_id, amount, type, created_at)
        VALUES (%s,%s,%s,'purchase',NOW())
    """, (student_id, session["staff_id"], amount))
    conn.commit()
    conn.close()

    flash("QR transaction recorded successfully.", "success")
    return redirect(url_for("dashboard_staff"))

# ---------------- Run App ----------------
if __name__ == "__main__":
    os.makedirs("static/topups", exist_ok=True)
    os.makedirs("static/qrcodes", exist_ok=True)
    print("Starting Flask server...")
    app.run(debug=True)

