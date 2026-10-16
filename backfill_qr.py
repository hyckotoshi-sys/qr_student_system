from app import get_connection, generate_fixed_qr

conn = get_connection()
cursor = conn.cursor()
cursor.execute("SELECT school_id FROM students WHERE qr_code IS NULL")
students = cursor.fetchall()

for (school_id,) in students:
    qr_path = generate_fixed_qr(school_id)
    cursor.execute("UPDATE students SET qr_code=%s WHERE school_id=%s", (qr_path, school_id))

conn.commit()
conn.close()

print("✅ Backfill complete: QR codes generated for existing students.")
