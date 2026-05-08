from flask import Flask, render_template, request, redirect, url_for, session, send_file
import mysql.connector, random, datetime, os, io, uuid
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
REPLY_TO_EMAIL = Email("hyckotoshi@gmail.com", name="Support Team")

def send_email(to_email, subject, body_text=None, body_html=None):
    message = Mail(
        from_email=Email("hyckotoshi@gmail.com", "FCD Central Institute"),
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

# ---------------- OTP Function ----------------
def generate_and_send_otp(email):
    otp = str(random.randint(100000, 999999))
    expires = datetime.datetime.now() + datetime.timedelta(minutes=5)

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO otps (email, otp_code, expires_at) VALUES (%s,%s,%s)", (email, otp, expires))
    conn.commit()
    conn.close()

    subject = "Your Secure Login OTP"
    body_text = f"Your OTP is: {otp} (expires in 5 minutes)."

    env = Environment(loader=FileSystemLoader("templates"))
    template = env.get_template("otp_template.html")
    body_html = template.render(otp=otp)

    send_email(email, subject, body_text, body_html)
    return otp

# ---------------- Sign Up ----------------
@app.route("/signup/student", methods=["GET","POST"])
def signup_student():
    if request.method == "POST":
        data = (
            request.form["full_name"], request.form["school_id"], request.form["email"],
            request.form["contact_number"], request.form["strand"], request.form["guardian_name"],
            request.form["parent_email"], request.form["password"], request.form["pin"]
        )
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO students 
            (full_name, school_id, email, contact_number, strand, guardian_name, parent_email, password, pin) 
            VALUES (%s,%s,%s,%s,%s,%s,%s,%s,%s)""", data)
        conn.commit()
        conn.close()
        return redirect(url_for("signin_student"))
    return render_template("signup_student.html")

@app.route("/signup/admin", methods=["GET","POST"])
def signup_admin():
    if request.method == "POST":
        data = (request.form["full_name"], request.form["contact_number"], request.form["email"], request.form["password"])
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO admins (full_name, contact_number, email, password) VALUES (%s,%s,%s,%s)", data)
        conn.commit()
        conn.close()
        return redirect(url_for("signin_admin"))
    return render_template("signup_admin.html")

@app.route("/signup/staff", methods=["GET","POST"])
def signup_staff():
    if request.method == "POST":
        data = (request.form["full_name"], request.form["contact_number"], request.form["email"], request.form["password"])
        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("INSERT INTO staff (full_name, contact_number, email, password) VALUES (%s,%s,%s,%s)", data)
        conn.commit()
        conn.close()
        return redirect(url_for("signin_staff"))
    return render_template("signup_staff.html")
# ---------------- Student Sign In ----------------
@app.route("/signin/student", methods=["GET","POST"])
def signin_student():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT student_id, email FROM students WHERE email=%s AND password=%s", (email,password))
        student = cursor.fetchone()
        conn.close()

        if student:
            session["pending_email"] = student[1]
            session["role"] = "student"
            session["student_id"] = student[0]
            generate_and_send_otp(email)
            return redirect(url_for("verify_otp"))
        else:
            return "Invalid student credentials"
    return render_template("signin_student.html")

# ---------------- Admin Sign In ----------------
@app.route("/signin/admin", methods=["GET","POST"])
def signin_admin():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT admin_id, email FROM admins WHERE email=%s AND password=%s", (email,password))
        admin = cursor.fetchone()
        conn.close()

        if admin:
            session["pending_email"] = admin[1]
            session["role"] = "admin"
            session["admin_id"] = admin[0]
            generate_and_send_otp(email)
            return redirect(url_for("verify_otp"))
        else:
            return "Invalid admin credentials"
    return render_template("signin_admin.html")

# ---------------- Staff Sign In ----------------
@app.route("/signin/staff", methods=["GET","POST"])
def signin_staff():
    if request.method == "POST":
        email = request.form["email"]
        password = request.form["password"]

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("SELECT staff_id, email FROM staff WHERE email=%s AND password=%s", (email,password))
        staff = cursor.fetchone()
        conn.close()

        if staff:
            session["pending_email"] = staff[1]
            session["role"] = "staff"
            session["staff_id"] = staff[0]
            generate_and_send_otp(email)
            return redirect(url_for("verify_otp"))
        else:
            return "Invalid staff credentials"
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
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, school_id, email, balance FROM students WHERE email=%s", (session["email"],))
    student = cursor.fetchone()
    conn.close()
    return render_template("dashboard_student.html", student=student)

@app.route("/topup", methods=["GET","POST"])
def topup():
    if "email" not in session or session.get("role") != "student":
        return redirect(url_for("signin_student"))

    if request.method == "POST":
        method = request.form["method"]   # ewallet or bank
        amount = float(request.form["amount"])
        screenshot = request.files["screenshot"]

        filename = secure_filename(screenshot.filename)
        path = os.path.join("static/topups", filename)
        screenshot.save(path)

        conn = get_connection()
        cursor = conn.cursor()
        cursor.execute("""INSERT INTO topups (student_id, method, amount, screenshot_path, status, created_at)
                          VALUES (%s,%s,%s,%s,'pending',NOW())""",
                       (session["student_id"], method, amount, path))
        conn.commit()
        conn.close()

        return "Top-up submitted successfully! Await admin approval."
    return render_template("topup.html")

# ---------------- Generate QR (unique each time) ----------------
@app.route("/generate_qr")
def generate_qr():
    if "student_id" not in session:
        return redirect(url_for("signin_student"))

    student_id = session["student_id"]

    token = str(uuid.uuid4())

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO qr_tokens (student_id, token, created_at) VALUES (%s,%s,NOW())",
                   (student_id, token))
    conn.commit()
    conn.close()

    qr_img = qrcode.make(token)
    img_io = io.BytesIO()
    qr_img.save(img_io, 'PNG')
    img_io.seek(0)

    return send_file(img_io, mimetype='image/png')
# ---------------- Admin Dashboard ----------------
@app.route("/dashboard/admin")
def dashboard_admin():
    if "email" not in session or session.get("role") != "admin":
        return redirect(url_for("signin_admin"))

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT full_name, school_id, email, balance FROM students")
    students = cursor.fetchall()
    cursor.execute("SELECT topup_id, student_id, method, amount, screenshot_path FROM topups WHERE status='pending'")
    topups = cursor.fetchall()
    conn.close()
    return render_template("dashboard_admin.html", students=students, topups=topups)

# ---------------- Approve Top-Up ----------------
@app.route("/approve_topup", methods=["POST"])
def approve_topup():
    if "email" not in session or session.get("role") != "admin":
        return redirect(url_for("signin_admin"))

    topup_id = request.form["topup_id"]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT student_id, amount FROM topups WHERE topup_id=%s", (topup_id,))
    topup = cursor.fetchone()
    student_id, amount = topup

    # Update balance
    cursor.execute("UPDATE students SET balance = balance + %s WHERE student_id=%s", (amount, student_id))
    cursor.execute("UPDATE topups SET status='approved' WHERE topup_id=%s", (topup_id,))
    conn.commit()

    # Get student + parent email
    cursor.execute("SELECT email, parent_email FROM students WHERE student_id=%s", (student_id,))
    student = cursor.fetchone()
    student_email, parent_email = student
    conn.close()

    # Send email notification
    send_email([student_email, parent_email], "Top-Up Approved",
               f"Your top-up of {amount} has been approved. Your new balance is updated.")

    return redirect(url_for("dashboard_admin"))

# ---------------- Reject Top-Up ----------------
@app.route("/reject_topup", methods=["POST"])
def reject_topup():
    if "email" not in session or session.get("role") != "admin":
        return redirect(url_for("signin_admin"))

    topup_id = request.form["topup_id"]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("UPDATE topups SET status='rejected' WHERE topup_id=%s", (topup_id,))
    conn.commit()

    cursor.execute("SELECT student_id FROM topups WHERE topup_id=%s", (topup_id,))
    student_id = cursor.fetchone()[0]
    cursor.execute("SELECT email, parent_email FROM students WHERE student_id=%s", (student_id,))
    student = cursor.fetchone()
    student_email, parent_email = student
    conn.close()

    # Send rejection email
    send_email([student_email, parent_email], "Top-Up Rejected",
               "Your top-up request was rejected. Please contact admin.")
    return redirect(url_for("dashboard_admin"))

# ---------------- Staff QR Generation ----------------
@app.route("/generate_staff_qr")
def generate_staff_qr():
    if "staff_id" not in session:
        return redirect(url_for("signin_staff"))

    staff_id = session["staff_id"]
    token = str(uuid.uuid4())

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("INSERT INTO qr_tokens (student_id, token, created_at) VALUES (%s,%s,NOW())",
                   (staff_id, token))  # reuse qr_tokens table
    conn.commit()
    conn.close()

    qr_img = qrcode.make(token)
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

    cursor.execute("SELECT * FROM transactions WHERE staff_id=%s ORDER BY timestamp DESC", (session.get("staff_id"),))
    registered_txns = cursor.fetchall()

    cursor.execute("SELECT * FROM unregistered_transactions WHERE staff_id=%s ORDER BY timestamp DESC", (session.get("staff_id"),))
    unregistered_txns = cursor.fetchall()

    conn.close()

    return render_template("dashboard_staff.html",
                           registered_txns=registered_txns,
                           unregistered_txns=unregistered_txns)

# ---------------- Manual Input for Unregistered Students ----------------
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

    return "Unregistered student transaction recorded."

# ---------------- Real-Time QR Scanning (token lookup) ----------------
@app.route("/scan_qr", methods=["GET","POST"])
def scan_qr():
    if request.method == "GET":
        return render_template("scan_qr.html")

    if "role" not in session or session["role"] != "staff":
        return redirect(url_for("signin_staff"))

    token = request.form["student_id"]
    amount = float(request.form["amount"])

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT student_id FROM qr_tokens WHERE token=%s ORDER BY created_at DESC LIMIT 1", (token,))
    result = cursor.fetchone()
    conn.close()

    if result:
        student_id = result[0]
        session["pending_student"] = student_id
        session["pending_amount"] = amount
        return redirect(url_for("confirm_transaction"))
    else:
        return "Invalid or expired QR code"

# ---------------- Student Scans Staff QR ----------------
@app.route("/scan_staff_qr", methods=["GET","POST"])
def scan_staff_qr():
    if request.method == "GET":
        return render_template("scan_staff_qr.html")

    staff_token = request.form["staff_token"]

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT student_id FROM qr_tokens WHERE token=%s ORDER BY created_at DESC LIMIT 1", (staff_token,))
    result = cursor.fetchone()
    conn.close()

    if result:
        staff_id = result[0]
        return f"Staff QR confirmed for staff_id {staff_id}"
    else:
        return "Invalid or expired staff QR"

# ---------------- Staff Transaction (Registered Students Only) ----------------
@app.route("/staff_transaction", methods=["POST"])
def staff_transaction():
    if "email" not in session or session.get("role") != "staff":
        return redirect(url_for("signin_staff"))

    school_id = request.form["school_id"]
    amount = float(request.form["amount"])

    conn = get_connection()
    cursor = conn.cursor()
    cursor.execute("SELECT student_id, full_name, email, balance, pin FROM students WHERE school_id=%s", (school_id,))
    student = cursor.fetchone()

    if student:
        student_id, full_name, email, balance, pin = student
        if balance >= amount:
            new_balance = balance - amount
            cursor.execute("UPDATE students SET balance=%s WHERE student_id=%s", (new_balance, student_id))

            staff_id = session.get("staff_id")
            cursor.execute("INSERT INTO transactions (student_id, staff_id, amount, type, status) VALUES (%s,%s,%s,'purchase','pending')",
                           (student_id, staff_id, amount))
            conn.commit()
            txn_id = cursor.lastrowid
            conn.close()

            session["pending_txn"] = txn_id
            return redirect(url_for("confirm_transaction"))
        else:
            conn.close()
            return "Insufficient balance, please try again."
    else:
        conn.close()
        return "Student not found. Please use the Unregistered Student form."

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
