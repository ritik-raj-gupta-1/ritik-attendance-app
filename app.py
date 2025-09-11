import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
from functools import wraps
import secrets
import math

app = Flask(__name__)
# For production, always use a strong secret key from an environment variable.
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(32))

# --- Application Configuration ---
CLASS_NAME = 'B.A. - Anthro'
BATCH_CODE = 'BA' # Corrected to match your database_setup.sql file
GEOFENCE_RADIUS = 50  # Radius in meters for geolocation check

# --- Controller Credentials (best practice: use environment variables) ---
CONTROLLER_USERNAME = os.environ.get('BA_CONTROLLER_USER', 'ba_controller')
CONTROLLER_PASSWORD = os.environ.get('BA_CONTROLLER_PASS', 'ba_pass_789')
CONTROLLER_DISPLAY_NAME = "B.A. Anthro Dept Controller"

# --- Database Connection ---
DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("FATAL: The DATABASE_URL environment variable is not set.")

def get_db_connection():
    """Establishes a reliable connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'UTC';")
        conn.commit()
        return conn
    except psycopg2.OperationalError as e:
        print(f"FATAL: Database connection failed: {e}")
        return None

def controller_required(f):
    """Decorator to protect routes that require controller login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'ba_controller':
            flash("You must be logged in as the B.A. controller to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions ---
def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates the distance between two GPS coordinates in meters."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_class_id_by_name(cursor):
    """Gets the class ID from the database using the configured CLASS_NAME."""
    cursor.execute("SELECT id FROM classes WHERE class_name = %s", (CLASS_NAME,))
    result = cursor.fetchone()
    return result[0] if result else None

def get_controller_id_by_username(cursor):
    """Gets the controller's user ID from the database."""
    cursor.execute("SELECT id FROM users WHERE username = %s", (CONTROLLER_USERNAME,))
    result = cursor.fetchone()
    return result[0] if result else None

# --- Main Routes ---
@app.route('/')
def home():
    """Redirects users to the appropriate starting page."""
    if 'user_id' in session and session.get('role') == 'ba_controller':
        return redirect(url_for('controller_dashboard'))
    return redirect(url_for('student_page'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles controller login."""
    if request.method == 'POST':
        username, password = request.form.get('username'), request.form.get('password')
        conn = get_db_connection()
        if not conn:
            flash("Database service is temporarily unavailable.", "danger")
            return render_template('login.html', class_name=CLASS_NAME)
        try:
            with conn.cursor() as cur:
                if username == CONTROLLER_USERNAME and password == CONTROLLER_PASSWORD:
                    controller_id = get_controller_id_by_username(cur)
                    if controller_id:
                        session.clear()
                        session['user_id'] = controller_id
                        session['username'] = username
                        session['role'] = 'ba_controller'
                        return redirect(url_for('controller_dashboard'))
                    else:
                        flash("Controller user is not configured correctly in the database.", "danger")
                else:
                    flash("Invalid username or password provided.", "danger")
        finally:
            conn.close()
    return render_template('login.html', class_name=CLASS_NAME)

@app.route('/logout')
def logout():
    """Logs out the controller."""
    session.clear()
    flash("You have been successfully logged out.", "info")
    return redirect(url_for('login'))

@app.route('/student')
def student_page():
    """Renders the main page for students to mark attendance."""
    active_session = None
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                class_id = get_class_id_by_name(cur)
                if class_id:
                    # Find the currently active session for this class
                    cur.execute("""
                        SELECT id, end_time 
                        FROM attendance_sessions 
                        WHERE class_id = %s AND is_active = TRUE AND end_time > NOW() 
                        LIMIT 1
                    """, (class_id,))
                    session_data = cur.fetchone()
                    if session_data:
                        # Pass the end_time as an ISO formatted string for the robust timer
                        active_session = {
                            'id': session_data['id'],
                            'end_time': session_data['end_time'].isoformat()
                        }
        finally:
            conn.close()
    
    todays_date = datetime.now(timezone.utc).strftime('%A, %B %d, %Y')
    return render_template('student_attendance.html', active_session=active_session, class_name=CLASS_NAME, todays_date=todays_date)

@app.route('/controller_dashboard')
@controller_required
def controller_dashboard():
    """Renders the main dashboard for the logged-in controller."""
    active_session = None
    conn = get_db_connection()
    if conn:
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                class_id = get_class_id_by_name(cur)
                if class_id:
                    cur.execute("""
                        SELECT id, end_time 
                        FROM attendance_sessions 
                        WHERE class_id = %s AND is_active = TRUE AND end_time > NOW() 
                        LIMIT 1
                    """, (class_id,))
                    session_data = cur.fetchone()
                    if session_data:
                        active_session = {
                            'id': session_data['id'],
                            'end_time': session_data['end_time'].isoformat()
                        }
        finally:
            conn.close()
    return render_template('admin_dashboard.html', active_session=active_session, controller_name=CONTROLLER_DISPLAY_NAME, class_name=CLASS_NAME)

@app.route('/attendance_report')
@controller_required
def attendance_report():
    """Generates and displays the daily attendance report for the controller."""
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        return redirect(url_for('controller_dashboard'))
    
    report_data = []
    students = []
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            class_id = get_class_id_by_name(cur)
            if not class_id:
                flash(f"Class '{CLASS_NAME}' not found.", "danger")
                return render_template('attendance_report.html', report_data=[], students=[], class_name=CLASS_NAME)

            cur.execute("SELECT id, name, enrollment_no FROM students WHERE batch = %s ORDER BY enrollment_no", (BATCH_CODE,))
            students = cur.fetchall()
            
            cur.execute("""
                SELECT DISTINCT DATE(start_time AT TIME ZONE 'UTC') as class_date 
                FROM attendance_sessions 
                WHERE class_id = %s 
                ORDER BY class_date DESC
            """, (class_id,))
            class_dates = [row['class_date'] for row in cur.fetchall()]

            today_utc = datetime.now(timezone.utc).date()

            for class_date in class_dates:
                is_editable = (today_utc - class_date).days < 7
                daily_entry = {
                    'date': class_date.strftime('%Y-%m-%d'), 
                    'students': [], 
                    'is_editable': is_editable
                }
                
                cur.execute("""
                    SELECT DISTINCT ar.student_id 
                    FROM attendance_records ar 
                    JOIN attendance_sessions s ON ar.session_id = s.id 
                    WHERE s.class_id = %s AND DATE(s.start_time AT TIME ZONE 'UTC') = %s
                """, (class_id, class_date))
                present_ids = {row['student_id'] for row in cur.fetchall()}
                
                for student in students:
                    status = 'Present' if student['id'] in present_ids else 'Absent'
                    daily_entry['students'].append({'status': status})
                
                report_data.append(daily_entry)
                
    except (Exception, psycopg2.Error) as e:
        print(f"ERROR in attendance_report: {e}")
        flash("An error occurred while generating the report.", "danger")
    finally:
        if conn: conn.close()
    
    return render_template('attendance_report.html', report_data=report_data, students=students, class_name=CLASS_NAME)

@app.route('/edit_attendance/<date_str>')
@controller_required
def edit_attendance(date_str):
    """Renders the professional interface for editing a single day's attendance."""
    try:
        # Validate date format to prevent errors
        day_to_edit = datetime.strptime(date_str, '%Y-%m-%d').date()
        return render_template('edit_attendance.html', attendance_date=day_to_edit.strftime('%Y-%m-%d'), class_name=CLASS_NAME)
    except ValueError:
        flash("Invalid date format provided.", "danger")
        return redirect(url_for('attendance_report'))

# --- API Endpoints ---

@app.route('/api/mark_attendance', methods=['POST'])
def api_mark_attendance():
    """API endpoint for students to mark their attendance."""
    data = request.form
    required_fields = ['enrollment_no', 'session_id', 'latitude', 'longitude', 'accuracy']
    if not all(field in data for field in required_fields):
        return jsonify({"success": False, "message": "Missing required data.", "category": "error"}), 400

    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database service is temporarily unavailable."}), 503

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            enrollment_no_upper = data['enrollment_no'].strip().upper()
            cur.execute("SELECT id FROM students WHERE enrollment_no = %s AND batch = %s", (enrollment_no_upper, BATCH_CODE))
            student = cur.fetchone()
            if not student:
                return jsonify({"success": False, "message": f"Enrollment number not found for the {CLASS_NAME} batch.", "category": "danger"}), 404
            student_id = student['id']

            cur.execute("SELECT id, session_lat, session_lon FROM attendance_sessions WHERE id = %s AND is_active = TRUE AND end_time > NOW()", (data['session_id'],))
            session_info = cur.fetchone()
            if not session_info or not session_info['session_lat']:
                return jsonify({"success": False, "message": "This attendance session has expired or is invalid.", "category": "danger"}), 400

            distance = haversine_distance(float(data['latitude']), float(data['longitude']), session_info['session_lat'], session_info['session_lon'])
            if distance > GEOFENCE_RADIUS:
                return jsonify({"success": False, "message": f"You are {distance:.0f}m away. Please move within the {GEOFENCE_RADIUS}m radius.", "category": "danger"}), 403

            cur.execute("SELECT student_id FROM attendance_records WHERE session_id = %s AND ip_address = %s", (session_info['id'], user_ip))
            ip_record = cur.fetchone()
            if ip_record and ip_record['student_id'] != student_id:
                return jsonify({"success": False, "message": "This network has already been used by another student for this session.", "category": "danger"}), 403

            cur.execute("""
                INSERT INTO attendance_records (session_id, student_id, timestamp, latitude, longitude, ip_address, accuracy) 
                VALUES (%s, %s, NOW(), %s, %s, %s, %s) 
                ON CONFLICT (session_id, student_id) DO NOTHING
            """, (session_info['id'], student_id, float(data['latitude']), float(data['longitude']), user_ip, float(data['accuracy'])))
            
            if cur.rowcount == 0:
                conn.commit()
                return jsonify({"success": False, "message": "You have already marked attendance for this session.", "category": "warning"}), 409
            
            conn.commit()
            return jsonify({"success": True, "message": "Attendance marked successfully!", "category": "success"})
    except (Exception, psycopg2.Error) as e:
        if conn: conn.rollback()
        print(f"ERROR in api_mark_attendance: {e}")
        return jsonify({"success": False, "message": "A server error occurred. Please try again.", "category": "error"}), 500
    finally:
        if conn: conn.close()

@app.route('/api/start_session', methods=['POST'])
@controller_required
def api_start_session():
    """API endpoint for the controller to start a new session."""
    data = request.get_json()
    if not data or 'latitude' not in data or 'longitude' not in data:
        return jsonify({"success": False, "message": "Location data not provided.", "category": "danger"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection failed."}), 503

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            class_id = get_class_id_by_name(cur)
            if class_id:
                cur.execute("SELECT id FROM attendance_sessions WHERE class_id = %s AND is_active = TRUE AND end_time > NOW() LIMIT 1", (class_id,))
                if cur.fetchone():
                    return jsonify({"success": False, "message": "An active session already exists.", "category": "info"}), 409
            
            start_time, end_time = datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(minutes=5)
            cur.execute("""
                INSERT INTO attendance_sessions (class_id, controller_id, session_token, start_time, end_time, is_active, session_lat, session_lon) 
                VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s)
            """, (class_id, session['user_id'], secrets.token_hex(16), start_time, end_time, data['latitude'], data['longitude']))
            conn.commit()
            return jsonify({"success": True, "message": "New 5-minute session started!", "category": "success"})
    except (Exception, psycopg2.Error) as e:
        if conn: conn.rollback()
        print(f"ERROR in api_start_session: {e}")
        return jsonify({"success": False, "message": "Error starting session."}), 500
    finally:
        if conn: conn.close()

@app.route('/api/end_session/<int:session_id>', methods=['POST'])
@controller_required
def api_end_session(session_id):
    """API endpoint for the controller to manually end a session."""
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database connection failed."})
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE attendance_sessions SET is_active = FALSE, end_time = NOW() WHERE id = %s AND controller_id = %s", (session_id, session['user_id']))
            conn.commit()
            return jsonify({"success": True, "message": "Session ended successfully."})
    finally:
        if conn: conn.close()

@app.route('/api/get_student_name/<enrollment_no>')
def api_get_student_name(enrollment_no):
    """API for the live student name verification feature."""
    conn = get_db_connection()
    if not conn: return jsonify({"success": False}), 503
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM students WHERE enrollment_no = %s AND batch = %s", (enrollment_no.strip().upper(), BATCH_CODE))
            student = cur.fetchone()
            if student:
                return jsonify({"success": True, "name": student[0]})
            else:
                return jsonify({"success": False})
    finally:
        if conn: conn.close()

@app.route('/api/get_present_students/<int:session_id>')
def api_get_present_students(session_id):
    """API for the live list of present students on the student page."""
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "students": []}), 503
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("""
                SELECT s.name, s.enrollment_no 
                FROM attendance_records ar 
                JOIN students s ON ar.student_id = s.id 
                WHERE ar.session_id = %s 
                ORDER BY s.enrollment_no ASC
            """, (session_id,))
            students = cur.fetchall()
            return jsonify({"success": True, "students": students})
    finally:
        if conn: conn.close()

@app.route('/api/get_students_for_edit/<date_str>')
@controller_required
def api_get_students_for_edit(date_str):
    """API to get all students and their status for the professional edit page."""
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database failed."}), 500
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            class_id = get_class_id_by_name(cur)
            day_to_query = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            cur.execute("SELECT id, enrollment_no, name FROM students WHERE batch = %s ORDER BY enrollment_no", (BATCH_CODE,))
            all_students = cur.fetchall()
            
            cur.execute("""
                SELECT DISTINCT ar.student_id
                FROM attendance_records ar
                JOIN attendance_sessions s ON ar.session_id = s.id
                WHERE s.class_id = %s AND DATE(s.start_time AT TIME ZONE 'UTC') = %s
            """, (class_id, day_to_query))
            
            present_student_ids = {row['student_id'] for row in cur.fetchall()}
            student_data = [
                {'id': s['id'], 'enrollment_no': s['enrollment_no'], 'name': s['name'], 'is_present': s['id'] in present_student_ids}
                for s in all_students
            ]
            return jsonify({"success": True, "students": student_data})
    except Exception as e:
        print(f"ERROR: api_get_students_for_edit: {e}")
        return jsonify({"success": False, "message": "An error occurred."}), 500
    finally:
        if conn: conn.close()

@app.route('/api/update_daily_attendance', methods=['POST'])
@controller_required
def api_update_daily_attendance():
    """API to handle the attendance toggle changes from the edit page."""
    data = request.get_json()
    date_str = data.get('date')
    student_id = data.get('student_id')
    is_present = data.get('is_present')

    if not all([date_str, student_id, isinstance(is_present, bool)]):
        return jsonify({"success": False, "message": "Missing or invalid data."}), 400

    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database failed."}), 500

    try:
        with conn.cursor() as cur:
            class_id = get_class_id_by_name(cur)
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            cur.execute(
                "SELECT id FROM attendance_sessions WHERE class_id = %s AND DATE(start_time AT TIME ZONE 'UTC') = %s ORDER BY start_time ASC",
                (class_id, target_date)
            )
            session_ids_for_day = [row[0] for row in cur.fetchall()]

            if is_present:
                if not session_ids_for_day:
                    # If no session exists, we cannot mark them present.
                    return jsonify({"success": False, "message": "Cannot mark present: no session exists for this day."}), 404
                # Add student to the first session of the day
                first_session_id = session_ids_for_day[0]
                cur.execute("""
                    INSERT INTO attendance_records (session_id, student_id, timestamp, ip_address, accuracy) 
                    VALUES (%s, %s, NOW(), 'Manual_Edit', -1) 
                    ON CONFLICT (session_id, student_id) DO NOTHING
                """, (first_session_id, student_id))
            else:
                # Remove student from ALL sessions of that day if any exist
                if session_ids_for_day:
                    cur.execute(
                        "DELETE FROM attendance_records WHERE student_id = %s AND session_id = ANY(%s)",
                        (student_id, session_ids_for_day)
                    )
            conn.commit()
            return jsonify({"success": True, "message": "Attendance updated."})
    except Exception as e:
        conn.rollback()
        print(f"ERROR: api_update_daily_attendance: {e}")
        return jsonify({"success": False, "message": "A server-side error occurred."}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    # Use environment variables for port and debug settings, Render will set PORT automatically.
    port = int(os.environ.get('PORT', 5000))
    debug = os.environ.get('FLASK_DEBUG', 'False').lower() == 'true'
    app.run(host='0.0.0.0', port=port, debug=debug)

