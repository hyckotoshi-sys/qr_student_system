import mysql.connector

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        port=3307,                # match your Workbench port
        user="school_user",       # ✅ must include the user
        password="qrcode12345!",  # your MySQL password
        database="school_system",
        autocommit=True
    )
