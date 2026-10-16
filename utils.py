import qrcode

def generate_student_qr(student_id):
    # Path to save QR codes
    qr_folder = os.path.join("static", "qrcodes")
    os.makedirs(qr_folder, exist_ok=True)

    # File path for this student's QR
    qr_path = os.path.join(qr_folder, f"{student_id}.png")

    # Generate QR code with student_id encoded
    qr_img = qrcode.make(student_id)
    qr_img.save(qr_path)

    return qr_path
