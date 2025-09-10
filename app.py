import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
from functools import wraps
import secrets
import math

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', os.urandom(32))

# --- Configuration ---
CLASS_NAME = 'B.A. - Anthro'
BATCH_CODE = 'BA'  # Corrected to match your database
GEOFENCE_RADIUS = 50

CONTROLLER_USERNAME = os.environ.get('BA_CONTROLLER_USER', 'ba_controller')
CONTROLLER_PASSWORD = os.environ.get('BA_CONTROLLER_PASS', 'ba_pass_789')
CONTROLLER_DISPLAY_NAME = "B.A. Anthro Dept Controller"

DATABASE_URL = os.environ.get('DATABASE_URL')
if not DATABASE_URL:
    raise RuntimeError("FATAL: DATABASE_URL environment variable is not set.")

# --- Database & Auth ---

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur: cur.execute("SET TIME ZONE 'UTC';")
        conn.commit()
        return conn
    except psycopg2.OperationalError as e:
        print(f"FATAL: Database connection failed: {e}")
        return None

def controller_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'ba_controller':
            flash("You must be logged in as the controller to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- Helper Functions ---
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi, delta_lambda = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    return R * 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))

def get_class_id_by_name(cursor):
    cursor.execute("SELECT id FROM classes WHERE class_name = %s", (CLASS_NAME,))
    result = cursor.fetchone()
    return result[0] if result else None

def get_controller_id_by_username(cursor, username):
    cursor.execute("SELECT id FROM users WHERE username = %s", (username,))
    result = cursor.fetchone()
    return result[0] if result else None
    
def get_active_class_session(conn):
    if not conn: return None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            class_id = get_class_id_by_name(cur)
            if not class_id: return None
            cur.execute("SELECT id, end_time FROM attendance_sessions WHERE class_id = %s AND is_active = TRUE AND end_time > NOW() ORDER BY start_time DESC LIMIT 1", (class_id,))
            session_data = cur.fetchone()
            if not session_data: return None
            time_remaining = (session_data['end_time'] - datetime.now(timezone.utc)).total_seconds()
            return {'id': session_data['id'], 'remaining_time': math.ceil(time_remaining)}
    except (Exception, psycopg2.Error) as e:
        print(f"ERROR in get_active_class_session: {e}")
        return None

# --- Main Routes ---
@app.route('/')
def home():
    if 'user_id' in session and session.get('role') == 'ba_controller':
        return redirect(url_for('controller_dashboard'))
    return redirect(url_for('student_page'))

@app.route('/login', methods=['GET', 'POST'])
def login():
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
                            flash("Controller user not found in database.", "danger")
                finally:
                    conn.close()
        else:
            flash("Invalid username or password.", "danger")
    return render_template('login.html', class_name=CLASS_NAME)

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been successfully logged out.", "info")
    return redirect(url_for('login'))

@app.route('/student')
def student_page():
    conn = get_db_connection()
    active_session = get_active_class_session(conn)
    if conn: conn.close()
    return render_template('student_attendance.html', active_session=active_session, class_name=CLASS_NAME)

@app.route('/controller_dashboard')
@controller_required
def controller_dashboard():
    conn = get_db_connection()
    active_session = get_active_class_session(conn)
    if conn: conn.close()
    return render_template('admin_dashboard.html', active_session=active_session, username=session.get('username'), class_name=CLASS_NAME)

@app.route('/attendance_report')
@controller_required
def attendance_report():
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
            student_map = {s['id']: s for s in students}
            
            cur.execute("SELECT DISTINCT DATE(start_time AT TIME ZONE 'UTC') as class_date FROM attendance_sessions WHERE class_id = %s ORDER BY class_date DESC", (class_id,))
            class_dates = [row['class_date'] for row in cur.fetchall()]

            for class_date in class_dates:
                daily_entry = {'date': class_date.strftime('%Y-%m-%d'), 'students': []}
                cur.execute("SELECT DISTINCT student_id FROM attendance_records ar JOIN attendance_sessions s ON ar.session_id = s.id WHERE s.class_id = %s AND DATE(s.start_time AT TIME ZONE 'UTC') = %s", (class_id, class_date))
                present_ids = {row['student_id'] for row in cur.fetchall()}
                
                for student in students:
                    daily_entry['students'].append({'status': 'Present' if student['id'] in present_ids else 'Absent'})
                report_data.append(daily_entry)
    finally:
        conn.close()
    return render_template('attendance_report.html', report_data=report_data, students=students, class_name=CLASS_NAME, now=datetime.now(timezone.utc))

@app.route('/edit_attendance/<date_str>')
@controller_required
def edit_attendance(date_str):
    try:
        datetime.strptime(date_str, '%Y-%m-%d')
        return render_template('edit_attendance.html', attendance_date=date_str, class_name=CLASS_NAME)
    except ValueError:
        flash("Invalid date format.", "danger")
        return redirect(url_for('attendance_report'))

# --- API Endpoints ---
@app.route('/api/mark_attendance', methods=['POST'])
def api_mark_attendance():
    data = request.form
    required = ['enrollment_no', 'session_id', 'latitude', 'longitude']
    if not all(field in data for field in required):
        return jsonify({"success": False, "message": "Missing required data."}), 400

    user_ip = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database unavailable."}), 503

    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT id FROM students WHERE enrollment_no = %s AND batch = %s", (data['enrollment_no'].strip().upper(), BATCH_CODE))
            student = cur.fetchone()
            if not student: return jsonify({"success": False, "message": f"Enrollment number not found for {CLASS_NAME}."}), 404
            
            cur.execute("SELECT id, session_lat, session_lon FROM attendance_sessions WHERE id = %s AND is_active = TRUE AND end_time > NOW()", (data['session_id'],))
            session_info = cur.fetchone()
            if not session_info: return jsonify({"success": False, "message": "Session expired or invalid."}), 400

            distance = haversine_distance(float(data['latitude']), float(data['longitude']), session_info['session_lat'], session_info['session_lon'])
            if distance > GEOFENCE_RADIUS:
                return jsonify({"success": False, "message": f"You are {distance:.0f}m away. Move within {GEOFENCE_RADIUS}m radius."}), 403

            cur.execute("SELECT student_id FROM attendance_records WHERE session_id = %s AND ip_address = %s", (session_info['id'], user_ip))
            ip_record = cur.fetchone()
            if ip_record and ip_record['student_id'] != student['id']:
                return jsonify({"success": False, "message": "This network has already been used by another student."}), 403

            cur.execute("INSERT INTO attendance_records (session_id, student_id, timestamp, ip_address, latitude, longitude) VALUES (%s, %s, NOW(), %s, %s, %s) ON CONFLICT (session_id, student_id) DO NOTHING",
                        (session_info['id'], student['id'], user_ip, float(data['latitude']), float(data['longitude'])))
            
            if cur.rowcount == 0:
                conn.commit()
                return jsonify({"success": False, "message": "Attendance already marked."}), 409
            
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
    data = request.get_json()
    if not data or 'latitude' not in data:
        return jsonify({"success": False, "message": "Location data not provided."}), 400
    
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database failed."}), 503
    if get_active_class_session(conn):
        conn.close()
        return jsonify({"success": False, "message": "An active session already exists."}), 409

    try:
        with conn.cursor() as cur:
            class_id = get_class_id_by_name(cur)
            start_time, end_time = datetime.now(timezone.utc), datetime.now(timezone.utc) + timedelta(minutes=5)
            cur.execute("INSERT INTO attendance_sessions (class_id, controller_id, session_token, start_time, end_time, is_active, session_lat, session_lon) VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s)",
                        (class_id, session['user_id'], secrets.token_hex(16), start_time, end_time, data['latitude'], data['longitude']))
            conn.commit()
            return jsonify({"success": True, "message": "New session started!"})
    finally:
        if conn: conn.close()

@app.route('/api/end_session/<int:session_id>', methods=['POST'])
@controller_required
def api_end_session(session_id):
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database failed."})
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE attendance_sessions SET is_active = FALSE, end_time = NOW() WHERE id = %s AND controller_id = %s", (session_id, session['user_id']))
            conn.commit()
            return jsonify({"success": True, "message": "Session ended."})
    finally:
        if conn: conn.close()

@app.route('/api/get_students_for_edit/<date_str>')
@controller_required
def api_get_students_for_edit(date_str):
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database failed."}), 500
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            class_id = get_class_id_by_name(cur)
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            cur.execute("SELECT id, enrollment_no, name FROM students WHERE batch = %s ORDER BY enrollment_no", (BATCH_CODE,))
            all_students = cur.fetchall()
            
            cur.execute("SELECT DISTINCT student_id FROM attendance_records ar JOIN attendance_sessions s ON ar.session_id = s.id WHERE s.class_id = %s AND DATE(s.start_time AT TIME ZONE 'UTC') = %s", (class_id, target_date))
            present_ids = {row['student_id'] for row in cur.fetchall()}
            
            student_data = [{'id': s['id'], 'enrollment_no': s['enrollment_no'], 'name': s['name'], 'is_present': s['id'] in present_ids} for s in all_students]
            return jsonify({"success": True, "students": student_data})
    finally:
        if conn: conn.close()

@app.route('/api/update_attendance', methods=['POST'])
@controller_required
def api_update_attendance():
    data = request.get_json()
    date_str, student_id, is_present = data.get('date'), data.get('student_id'), data.get('is_present')
    if not all([date_str, student_id, isinstance(is_present, bool)]):
        return jsonify({"success": False, "message": "Invalid data."}), 400

    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database failed."}), 500
    try:
        with conn.cursor() as cur:
            class_id = get_class_id_by_name(cur)
            target_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            
            cur.execute("SELECT id FROM attendance_sessions WHERE class_id = %s AND DATE(start_time AT TIME ZONE 'UTC') = %s", (class_id, target_date))
            session_ids = [row[0] for row in cur.fetchall()]
            if not session_ids: return jsonify({"success": False, "message": "No session found for this day."}), 404

            if is_present:
                cur.execute("INSERT INTO attendance_records (session_id, student_id, timestamp, ip_address) VALUES (%s, %s, NOW(), 'ManualEdit') ON CONFLICT (session_id, student_id) DO NOTHING", (session_ids[0], student_id))
            else:
                cur.execute("DELETE FROM attendance_records WHERE student_id = %s AND session_id = ANY(%s)", (student_id, session_ids))
            conn.commit()
            return jsonify({"success": True, "message": "Attendance updated."})
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    app.run(port=int(os.environ.get('PORT', 5000)))

