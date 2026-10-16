from extensions import db
from datetime import datetime

class Student(db.Model):
    __tablename__ = "students"
    student_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    school_id = db.Column(db.String(50), unique=True, nullable=False)
    full_name = db.Column(db.String(100), nullable=False)
    grade_level = db.Column(db.String(20))
    strand = db.Column(db.String(50))
    balance = db.Column(db.Numeric(10,2), default=0.00)
    qr_code = db.Column(db.String(255), unique=True)
    status = db.Column(db.Enum("active", "inactive"), default="active")
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)

    transactions = db.relationship("Transaction", backref="student", lazy=True)


class Transaction(db.Model):
    __tablename__ = "transactions"
    transaction_id = db.Column(db.Integer, primary_key=True, autoincrement=True)
    student_id = db.Column(db.Integer, db.ForeignKey("students.student_id"), nullable=True)
    amount = db.Column(db.Numeric(10,2), nullable=False)
    previous_balance = db.Column(db.Numeric(10,2))
    new_balance = db.Column(db.Numeric(10,2))
    status = db.Column(db.Enum("pending", "completed", "failed"), default="pending")
    remarks = db.Column(db.Text)
    created_at = db.Column(db.TIMESTAMP, default=datetime.utcnow)
    type = db.Column(db.Enum("topup", "purchase"), default="purchase")
    payment_mode = db.Column(db.Enum("cash", "gcash", "bank"), default="cash")
