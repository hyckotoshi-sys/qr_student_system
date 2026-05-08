import mysql.connector

try:
    conn = mysql.connector.connect(
        host="localhost",
        port= 3307,
        user="school_user",
        password="qrcode12345!",
        database="school_system",
        autocommit=True
    )
    print("✅ Connected to MySQL!")
    conn.close()
except mysql.connector.Error as err:
    print("❌ Error:", err)
