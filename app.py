import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
from functools import wraps
import secrets
import math

app = Flask(__name__)
# For production, set a strong, permanent key in your environment variables
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(32))

# --- Application Configuration ---
# All settings for the B.A. Anthropology course
CLASS_NAME = 'B.A. - Anthro'
BATCH_CODE = 'BA' # Corrected to match the database_setup.sql file
GEOFENCE_RADIUS = 50 # in meters

# --- Controller Credentials ---
# For security, these should be set as environment variables on Render
CONTROLLER_USERNAME = os.environ.get('BA_CONTROLLER_USER', 'ba_controller')
CONTROLLER_PASSWORD = os.environ.get('BA_CONTROLLER_PASS', 'ba_pass_789')
CONTROLLER_DISPLAY_NAME = "B.A. Anthro Dept Controller"

# --- Database Connection ---
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("FATAL: DATABASE_URL environment variable is not set.")

def get_db_connection():
    """Establishes a reliable connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        # Ensure all timestamps are handled in UTC
        with conn.cursor() as cur: cur.execute("SET TIME ZONE 'UTC';")
        conn.commit()
        return conn
    except psycopg2.OperationalError as e:
        print(f"FATAL: Database connection failed: {e}")
        return None

# --- Decorators for Authentication ---
def controller_required(f):
    """Decorator to protect routes, ensuring only logged-in controllers can access them."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'ba_controller':
            flash("You must be logged in as the controller to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions ---
def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates distance between two lat/lon coordinates in meters."""
    R, phi1, phi2 = 6371000, math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_class_id_by_name(cursor):
    """Retrieves the class ID from the database using the configured CLASS_NAME."""
    cursor.execute("SELECT id FROM classes WHERE class_name = %s", (CLASS_NAME,))
    return cursor.fetchone()[0] if cursor.rowcount > 0 else None

def get_controller_id_by_username(cursor, username):
    """Retrieves the controller's user ID from the database."""
    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
    return cursor.fetchone()[0] if cursor.rowcount > 0 else None

def get_active_class_session(conn):
    """
    Checks for an active session and returns its ID and precise end time.
    The end time is returned as an ISO 8601 string for JavaScript compatibility.
    """
    if not conn: return None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            class_id = get_class_id_by_name(cur)
            if not class_id: return None
            cur.execute(
                "SELECT id, end_time FROM attendance_sessions WHERE class_id = %s AND is_active = TRUE AND end_time > NOW() ORDER BY start_time DESC LIMIT 1",
                (class_id,)
            )
            session_data = cur.fetchone()
            if session_data:
                return {'id': session_data['id'], 'end_time': session_data['end_time'].isoformat()}
            return None
    except (Exception, psycopg2.Error) as e:
        print(f"ERROR in get_active_class_session: {e}")
        return None

# --- Main Page Routes ---
@app.route('/')
def home():
    """Redirects to the appropriate page based on login status."""
    if 'user_id' in session and session.get('role') == 'ba_controller':
        return redirect(url_for('controller_dashboard'))
    return redirect(url_for('student_page'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles controller login."""
    if 'user_id' in session and session.get('role') == 'ba_controller':
        return redirect(url_for('controller_dashboard'))
    if request.method == 'POST':
        username, password = request.form.get('username'), request.form.get('password')
        if username == CONTROLLER_USERNAME and password == CONTROLLER_PASSWORD:
            conn = get_db_connection()
            if not conn:
                flash("Database service is temporarily unavailable.", "danger")
            else:
                try:
                    with conn.cursor() as cur:
                        controller_id = get_controller_id_by_username(cur, username)
                        if controller_id:
                            session.clear()
                            session['user_id'] = controller_id
                            session['username'] = username
                            session['role'] = 'ba_controller'
                            return redirect(url_for('controller_dashboard'))
                        else:
                            flash("Controller user not configured in database.", "danger")
                finally:
                    conn.close()
        else:
            flash("Invalid username or password.", "danger")
    return render_template('login.html', class_name=CLASS_NAME)

@app.route('/logout')
def logout():
    """Handles controller logout."""
    session.clear()
    flash("You have been successfully logged out.", "info")
    return redirect(url_for('login'))

@app.route('/student')
def student_page():
    """Renders the main student attendance marking page."""
    conn = get_db_connection()
    active_session = get_active_class_session(conn)
    if conn: conn.close()
    # Get current time in Indian Standard Time for display
    ist = timezone(timedelta(hours=5, minutes=30))
    todays_date_str = datetime.now(ist).strftime('%A, %B %d, %Y')
    return render_template('student_attendance.html', active_session=active_session, class_name=CLASS_NAME, todays_date=todays_date_str)

@app.route('/controller_dashboard')
@controller_required
def controller_dashboard():
    """Renders the main dashboard for the logged-in controller."""
    conn = get_db_connection()
    active_session = get_active_class_session(conn)
    if conn: conn.close()
    return render_template('admin_dashboard.html', active_session=active_session, CONTROLLER_DISPLAY_NAME=CONTROLLER_DISPLAY_NAME, class_name=CLASS_NAME)

@app.route('/attendance_report')
@controller_required
def attendance_report():
    """Generates and displays the daily attendance report."""
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        return redirect(url_for('controller_dashboard'))
    report_data, students = [], []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            class_id = get_class_id_by_name(cur)
            cur.execute("SELECT id, name, enrollment_no FROM students WHERE batch = %s ORDER BY enrollment_no", (BATCH_CODE,))
            students = cur.fetchall()
            cur.execute("SELECT DISTINCT DATE(start_time AT TIME ZONE 'UTC') as class_date FROM attendance_sessions WHERE class_id = %s ORDER BY class_date DESC", (class_id,))
            class_dates = [row['class_date'] for row in cur.fetchall()]
            today_utc = datetime.now(timezone.utc).date()
            for class_date in class_dates:
                # FIX: Perform date logic here, not in the template
                is_editable = (today_utc - class_date).days < 7
                daily_entry = {'date': class_date.strftime('%Y-%m-%d'), 'students': [], 'is_editable': is_editable}
                cur.execute("SELECT DISTINCT student_id FROM attendance_records ar JOIN attendance_sessions s ON ar.session_id = s.id WHERE s.class_id = %s AND DATE(s.start_time AT TIME ZONE 'UTC') = %s", (class_id, class_date))
                present_ids = {row['student_id'] for row in cur.fetchall()}
                for student in students:
                    daily_entry['students'].append({'status': 'Present' if student['id'] in present_ids else 'Absent'})
                report_data.append(daily_entry)
    finally:
        if conn: conn.close()
    return render_template('attendance_report.html', report_data=report_data, students=students, class_name=CLASS_NAME)

@app.route('/edit_attendance/<date_str>')
@controller_required
def edit_attendance(date_str):
    """Renders the professional interface for editing a day's attendance."""
    return render_template('edit_attendance.html', attendance_date=date_str, class_name=CLASS_NAME)

# --- API Endpoints for Frontend Interactivity ---

@app.route('/api/mark_attendance', methods=['POST'])
def api_mark_attendance():
    """API for students to mark their attendance."""
    data, required = request.form, ['enrollment_no', 'session_id', 'latitude', 'longitude']
    if not all(field in data for field in required):
        return jsonify({"success": False, "message": "Missing required data."}), 400
    
    # Correctly read IP from Render's header
    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database unavailable."}), 503

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT id FROM students WHERE enrollment_no = %s AND batch = %s", (data['enrollment_no'].strip().upper(), BATCH_CODE))
            student = cur.fetchone()
            if not student:
                return jsonify({"success": False, "message": f"Enrollment number not found for {CLASS_NAME}."}), 404
            
            cur.execute("SELECT id, session_lat, session_lon FROM attendance_sessions WHERE id = %s AND is_active = TRUE AND end_time > NOW()", (data['session_id'],))
            session_info = cur.fetchone()
            if not session_info:
                return jsonify({"success": False, "message": "Session expired or invalid."}), 400
            
            distance = haversine_distance(float(data['latitude']), float(data['longitude']), session_info['session_lat'], session_info['session_lon'])
            if distance > GEOFENCE_RADIUS:
                return jsonify({"success": False, "message": f"You are {distance:.0f}m away. Please move within the {GEOFENCE_RADIUS}m radius."}), 403
            
            cur.execute("SELECT student_id FROM attendance_records WHERE session_id = %s AND ip_address = %s", (session_info['id'], user_ip))
            ip_record = cur.fetchone()
            if ip_record and ip_record['student_id'] != student['id']:
                return jsonify({"success": False, "message": "This network has already been used by another student for this session."}), 403
            
            cur.execute(
                "INSERT INTO attendance_records (session_id, student_id, timestamp, ip_address, latitude, longitude) VALUES (%s, %s, NOW(), %s, %s, %s) ON CONFLICT (session_id, student_id) DO NOTHING",
                (session_info['id'], student['id'], user_ip, float(data['latitude']), float(data['longitude']))
            )
            
            if cur.rowcount == 0:
                conn.commit()
                return jsonify({"success": False, "message": "You have already marked attendance for this session."}), 409
            
            conn.commit()
            return jsonify({"success": True, "message": "Attendance marked successfully!"})
    except (Exception, psycopg2.Error) as e:
        if conn: conn.rollback()
        print(f"ERROR in api_mark_attendance: {e}")
        return jsonify({"success": False, "message": "A server error occurred."}), 500
    finally:
        if conn: conn.close()

@app.route('/api/start_session', methods=['POST'])
@controller_required
def api_start_session():
    """API for the controller to start a new session."""
    data = request.get_json()
    if not data or 'latitude' not in data or 'longitude' not in data:
        return jsonify({"success": False, "message": "Location data not provided."}), 400
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database connection failed."}), 503
    if get_active_class_session(conn):
        conn.close()
        return jsonify({"success": False, "message": "An active session already exists."}), 409
    try:
        with conn.cursor() as cur:
            class_id = get_class_id_by_name(cur)
            if not class_id: return jsonify({"success": False, "message": f"Class '{CLASS_NAME}' not found."}), 500
            start_time = datetime.now(timezone.utc)
            end_time = start_time + timedelta(minutes=5)
            cur.execute(
                "INSERT INTO attendance_sessions (class_id, controller_id, session_token, start_time, end_time, is_active, session_lat, session_lon) VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s)",
                (class_id, session['user_id'], secrets.token_hex(16), start_time, end_time, data['latitude'], data['longitude'])
            )
            conn.commit()
            return jsonify({"success": True, "message": "New 5-minute session started!"})
    except (Exception, psycopg2.Error) as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "message": "Error starting session."}), 500
    finally:
        if conn: conn.close()

@app.route('/api/end_session/<int:session_id>', methods=['POST'])
@controller_required
def api_end_session(session_id):
    """API for the controller to end the active session."""
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database connection failed."})
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE attendance_sessions SET is_active = FALSE, end_time = NOW() WHERE id = %s AND controller_id = %s", (session_id, session['user_id']))
            conn.commit()
            return jsonify({"success": True, "message": "Session ended successfully."})
    except (Exception, psycopg2.Error) as e:
        return jsonify({"success": False, "message": "An error occurred."})
    finally:
        if conn: conn.close()

@app.route('/api/get_student_name/<enrollment_no>')
def api_get_student_name(enrollment_no):
    """API for the student page to verify a name from an enrollment number."""
    conn = get_db_connection()
    if not conn: return jsonify({"success": False}), 503
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM students WHERE enrollment_no = %s AND batch = %s", (enrollment_no.strip().upper(), BATCH_CODE))
            student = cur.fetchone()
            if student:
                return jsonify({"success": True, "name": student[0]})
            else:
                return jsonify({"success": False, "name": "Student not found"})
    finally:
        if conn: conn.close()

@app.route('/api/get_present_students/<int:session_id>')
def api_get_present_students(session_id):
    """API for the student page to get a live list of present students."""
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "students": []}), 503
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT s.name, s.enrollment_no FROM attendance_records ar JOIN students s ON ar.student_id = s.id WHERE ar.session_id = %s ORDER BY s.enrollment_no ASC", (session_id,))
            return jsonify({"success": True, "students": cur.fetchall()})
    finally:
        if conn: conn.close()

@app.route('/api/get_students_for_day_edit/<date_str>')
@controller_required
def api_get_students_for_day_edit(date_str):
    """API to get all students and their attendance status for the edit page."""
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database failed."}), 500
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            class_id = get_class_id_by_name(cur)
            day_to_query = datetime.strptime(date_str, '%Y-%m-%d').date()
            cur.execute("SELECT id, enrollment_no, name FROM students WHERE batch = %s ORDER BY enrollment_no", (BATCH_CODE,))
            all_students = cur.fetchall()
            cur.execute("SELECT DISTINCT ar.student_id FROM attendance_records ar JOIN attendance_sessions s ON ar.session_id = s.id WHERE s.class_id = %s AND DATE(s.start_time AT TIME ZONE 'UTC') = %s", (class_id, day_to_query))
            present_student_ids = {row['student_id'] for row in cur.fetchall()}
            student_data = [{'id': s['id'], 'enrollment_no': s['enrollment_no'], 'name': s['name'], 'is_present': s['id'] in present_student_ids} for s in all_students]
            return jsonify({"success": True, "students": student_data})
    except (Exception, psycopg2.Error) as e:
        print(f"ERROR: api_get_students_for_day_edit: {e}")
        return jsonify({"success": False, "message": "An error occurred fetching student data."}), 500
    finally:
        if conn: conn.close()

@app.route('/api/update_daily_attendance', methods=['POST'])
@controller_required
def api_update_daily_attendance():
    """API to handle the toggle switches on the edit attendance page."""
    data = request.get_json()
    date_str, student_id, is_present = data.get('date'), data.get('student_id'), data.get('is_present')
    if not all([date_str, student_id, isinstance(is_present, bool)]):
        return jsonify({"success": False, "message": "Missing or invalid data."}), 400
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database failed."}), 500
    try:
        with conn.cursor() as cur:
            class_id = get_class_id_by_name(cur)
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            cur.execute("SELECT id FROM attendance_sessions WHERE class_id = %s AND DATE(start_time AT TIME ZONE 'UTC') = %s ORDER BY start_time ASC", (class_id, target_date))
            session_ids_for_day = [row[0] for row in cur.fetchall()]
            if not session_ids_for_day:
                return jsonify({"success": False, "message": "No sessions found for this day to modify."}), 404
            if is_present:
                # Add student to the first session of the day to mark them present
                cur.execute(
                    "INSERT INTO attendance_records (session_id, student_id, timestamp, ip_address) VALUES (%s, %s, NOW(), 'Manual_Edit') ON CONFLICT (session_id, student_id) DO NOTHING",
                    (session_ids_for_day[0], student_id)
                )
            else:
                # Remove student from ALL sessions of that day
                cur.execute("DELETE FROM attendance_records WHERE student_id = %s AND session_id = ANY(%s)", (student_id, session_ids_for_day))
            conn.commit()
            return jsonify({"success": True, "message": "Attendance updated."})
    except (Exception, psycopg2.Error) as e:
        conn.rollback()
        print(f"ERROR: api_update_daily_attendance: {e}")
        return jsonify({"success": False, "message": "An error occurred during the update."}), 500
    finally:
        if conn: conn.close()

