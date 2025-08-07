import os
import psycopg2
from datetime import datetime, timedelta, timezone
import io
import smtplib
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText
from email.mime.base import MIMEBase
from email import encoders

# Database connection details from Render environment variables
DATABASE_URL = os.environ.get('DATABASE_URL')

# Email Configuration from Render environment variables
EMAIL_SENDER = os.environ.get('EMAIL_SENDER') # Your sender email address (e.g., your_email@gmail.com)
EMAIL_PASSWORD = os.environ.get('EMAIL_PASSWORD') # Your sender email password or app-specific password
EMAIL_RECEIVER = os.environ.get('EMAIL_RECEIVER', 'ritikalwaysrock@gmail.com') # The email address where you want to receive backups
SMTP_SERVER = os.environ.get('SMTP_SERVER', 'smtp.gmail.com') # Common for Gmail
SMTP_PORT = int(os.environ.get('SMTP_PORT', 587)) # Common for TLS

def get_db_connection():
    """Establishes and returns a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None

def generate_weekly_attendance_csv():
    """Generates a CSV string of the last week's daily attendance report."""
    conn = get_db_connection()
    if not conn:
        print("Database connection failed for CSV generation.")
        return None
    cur = conn.cursor()

    output = io.StringIO()
    try:
        # Get the BA - Anthropology class ID
        cur.execute("SELECT id FROM classes WHERE class_name = 'BA - Anthropology'")
        ba_anthropology_class_id = cur.fetchone()[0]

        # Fetch all BA students
        cur.execute("SELECT id, enrollment_no, name FROM students WHERE batch = 'BA' ORDER BY enrollment_no")
        all_ba_students = cur.fetchall()
        students_info = {s_id: {'enrollment_no': s_enroll, 'name': s_name} for s_id, s_enroll, s_name in all_ba_students}

        # Calculate the date range for the last 7 days (inclusive of today)
        end_date = datetime.now(timezone.utc).date()
        start_date = end_date - timedelta(days=6) # Last 7 days including today

        # Fetch all attendance records for BA - Anthropology within the last 7 days
        cur.execute("""
            SELECT ar.student_id, ar.timestamp::date AS attendance_date
            FROM attendance_records ar
            JOIN attendance_sessions asess ON ar.session_id = asess.id
            WHERE asess.class_id = %s
            AND ar.timestamp::date BETWEEN %s AND %s
            GROUP BY ar.student_id, attendance_date
            ORDER BY attendance_date ASC
        """, (ba_anthropology_class_id, start_date, end_date))
        
        present_records = cur.fetchall()

        daily_attendance_summary = {} # Date -> {student_id -> True}
        for student_id, attendance_date in present_records:
            date_str = attendance_date.strftime('%Y-%m-%d')
            if date_str not in daily_attendance_summary:
                daily_attendance_summary[date_str] = {}
            daily_attendance_summary[date_str][student_id] = True

        # Generate a list of all dates in the last 7-day range
        date_range = [start_date + timedelta(days=x) for x in range(7)]
        date_range_str = [d.strftime('%Y-%m-%d') for d in date_range]
        
        # CSV Header: Date, Student1 Name (Enrollment), Student2 Name (Enrollment), ...
        header_parts = ["Date"]
        sorted_student_ids = sorted(students_info.keys())
        for s_id in sorted_student_ids:
            header_parts.append(f"{students_info[s_id]['name']} ({students_info[s_id]['enrollment_no']})")
        output.write(",".join(header_parts) + "\n")

        # CSV Data
        for date_str in sorted(date_range_str): # Iterate through all dates in range, sorted ascending
            current_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            row_parts = [date_str]
            is_weekend = current_date.weekday() >= 5 # Saturday is 5, Sunday is 6
            any_attendance_on_date = bool(daily_attendance_summary.get(date_str))

            for s_id in sorted_student_ids:
                is_present = daily_attendance_summary.get(date_str, {}).get(s_id, False)
                
                status = "Present" if is_present else "Absent"
                if is_weekend and not is_present and not any_attendance_on_date:
                    status = "Holiday"
                
                row_parts.append(status)
            output.write(",".join(row_parts) + "\n")
        
        return output.getvalue() # Return the CSV string
    except Exception as e:
        print(f"Error generating CSV: {e}")
        return None
    finally:
        cur.close()
        conn.close()

def send_email_backup(csv_data, sender_email, sender_password, receiver_email, smtp_server, smtp_port):
    """Sends the CSV data as an email attachment."""
    if not sender_email or not sender_password or not receiver_email:
        print("Email credentials or receiver email are missing. Cannot send email.")
        return False

    msg = MIMEMultipart()
    msg['From'] = sender_email
    msg['To'] = receiver_email
    
    today_date = datetime.now(timezone.utc).strftime('%Y-%m-%d')
    last_week_start_date = (datetime.now(timezone.utc) - timedelta(days=6)).strftime('%Y-%m-%d')
    msg['Subject'] = f"Weekly Attendance Report Backup ({last_week_start_date} to {today_date})"

    msg.attach(MIMEText("Please find the weekly attendance report attached.", 'plain'))

    # Attach the CSV file
    part = MIMEBase('application', 'octet-stream')
    part.set_payload(csv_data.encode('utf-8'))
    encoders.encode_base64(part)
    part.add_header('Content-Disposition', f"attachment; filename=weekly_attendance_report_{last_week_start_date}_to_{today_date}.csv")
    msg.attach(part)

    try:
        with smtplib.SMTP(smtp_server, smtp_port) as server:
            server.starttls() # Secure the connection
            server.login(sender_email, sender_password)
            server.send_message(msg)
        print(f"Successfully sent email backup to {receiver_email}")
        return True
    except Exception as e:
        print(f"Error sending email: {e}")
        return False

if __name__ == '__main__':
    print("Starting weekly attendance email backup script...")
    csv_content = generate_weekly_attendance_csv()
    
    if csv_content:
        if send_email_backup(csv_content, EMAIL_SENDER, EMAIL_PASSWORD, EMAIL_RECEIVER, SMTP_SERVER, SMTP_PORT):
            print("Weekly email backup completed successfully.")
        else:
            print("Weekly email backup failed.")
    else:
        print("Failed to generate CSV content. Email backup aborted.")

