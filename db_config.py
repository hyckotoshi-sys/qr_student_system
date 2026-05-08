import mysql.connector

def get_connection():
    return mysql.connector.connect(
        host="localhost",
        port= 3307,                     
        password="qrcode12345!",
        database="school_system",
        autocommit=True
    )


