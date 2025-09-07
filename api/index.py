import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify
from functools import wraps
import secrets
import math

# Vercel requires the Flask app instance to be named 'app'
app = Flask(__name__)

# --- Configuration ---
# Use a stable secret key from environment variables
app.secret_key = os.environ.get('FLASK_SECRET_KEY', 'a_default_secret_key_for_local_dev')
CONTROLLER_USERNAME = "controller"
CONTROLLER_PASSWORD = "controller_pass_123"
DATABASE_URL = os.environ.get('DATABASE_URL')

# --- Database Helper Functions ---
def get_db_connection():
    """Establishes and configures a connection to the database."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'UTC';")
        conn.commit()
        return conn
    except Exception as e:
        print(f"Database connection error: {e}")
        return None

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates the distance in meters between two GPS coordinates."""
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

# --- Decorators and Route Logic ---
def controller_required(f):
    """Decorator to protect routes that require controller login."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'controller':
            flash("You must be logged in as the controller to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def get_active_ba_anthropology_session():
    """Checks for and returns the currently active session."""
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT id FROM classes WHERE class_name = 'BA - Anthropology'")
            class_id_result = cur.fetchone()
            if not class_id_result: return None
            class_id = class_id_result['id']

            cur.execute(
                "SELECT * FROM attendance_sessions WHERE class_id = %s AND is_active = TRUE AND end_time > NOW() ORDER BY start_time DESC LIMIT 1",
                (class_id,)
            )
            session_data = cur.fetchone()
            if not session_data: return None
            
            time_remaining = (session_data['end_time'] - datetime.now(timezone.utc)).total_seconds()
            if time_remaining <= 0: return None
                
            session_data['remaining_time'] = math.ceil(time_remaining)
            return session_data
    finally:
        if conn: conn.close()


@app.route('/')
def home():
    """Homepage redirects to the student attendance page."""
    return redirect(url_for('mark_attendance'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles controller login."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == CONTROLLER_USERNAME and password == CONTROLLER_PASSWORD:
            conn = get_db_connection()
            if conn:
                try:
                    with conn.cursor() as cur:
                        cur.execute("SELECT id FROM users WHERE username = %s", (username,))
                        user = cur.fetchone()
                    if user:
                        session['user_id'] = user[0]
                        session['username'] = username
                        session['role'] = 'controller'
                        flash(f"Welcome, {username}!", "success")
                        return redirect(url_for('controller_dashboard'))
                finally:
                    conn.close()
            flash("Controller user not found in the database.", "danger")
        else:
            flash("Invalid username or password.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    """Logs out the controller."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/controller_dashboard')
@controller_required
def controller_dashboard():
    """Displays the main dashboard for the controller."""
    active_session = get_active_ba_anthropology_session()
    return render_template('admin_dashboard.html', active_session=active_session, username=session.get('username'))

@app.route('/start_session', methods=['POST'])
@controller_required
def start_session():
    """Starts a new attendance session based on the controller's current location."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection failed."}), 500
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM attendance_sessions WHERE is_active = TRUE AND end_time > NOW()")
            if cur.fetchone():
                return jsonify({"success": False, "message": "An active session already exists."}), 409
        
        data = request.get_json()
        latitude, longitude = data.get('latitude'), data.get('longitude')
        if not latitude or not longitude:
            return jsonify({"success": False, "message": "Location data is required."}), 400

        with conn.cursor() as cur:
            cur.execute("SELECT id FROM classes WHERE class_name = 'BA - Anthropology'")
            class_id = cur.fetchone()[0]
            
            start_time = datetime.now(timezone.utc)
            end_time = start_time + timedelta(minutes=5)
            session_token = secrets.token_hex(16)
            
            cur.execute(
                "INSERT INTO attendance_sessions (class_id, controller_id, session_token, start_time, end_time, is_active, geofence_lat, geofence_lon, geofence_radius) VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s, %s) RETURNING id",
                (class_id, session['user_id'], session_token, start_time, end_time, latitude, longitude, 40)
            )
            new_session_id = cur.fetchone()[0]
            conn.commit()
            return jsonify({"success": True, "message": f"New session (ID: {new_session_id}) started!"})
    except Exception as e:
        if conn: conn.rollback()
        print(f"Error starting session: {e}")
        return jsonify({"success": False, "message": "An error occurred."}), 500
    finally:
        if conn: conn.close()

@app.route('/end_session/<int:session_id>', methods=['POST'])
@controller_required
def end_session(session_id):
    """Manually ends an active session."""
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database error."})
    try:
        with conn.cursor() as cur:
            cur.execute("UPDATE attendance_sessions SET is_active = FALSE, end_time = NOW() WHERE id = %s AND is_active = TRUE", (session_id,))
            conn.commit()
            return jsonify({"success": True, "message": "Session ended."})
    finally:
        if conn: conn.close()

@app.route('/mark_attendance', methods=['GET', 'POST'])
def mark_attendance():
    """Handles student attendance marking and displays the student-facing page."""
    if request.method == 'POST':
        data = request.form
        required = ['enrollment_no', 'session_id', 'latitude', 'longitude']
        if not all(field in data for field in required):
            return jsonify({"success": False, "message": "Missing data."}), 400

        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
        conn = get_db_connection()
        if not conn: return jsonify({"success": False, "message": "Database error."}), 500
        
        try:
            with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
                # 1. Validate Enrollment & Session
                cur.execute("SELECT id FROM students WHERE enrollment_no = %s", (data['enrollment_no'].upper(),))
                student = cur.fetchone()
                if not student: return jsonify({"success": False, "message": "Enrollment number not found."}), 404
                student_id = student['id']
                
                cur.execute("SELECT * FROM attendance_sessions WHERE id = %s AND is_active = TRUE AND end_time > NOW()", (data['session_id'],))
                session_info = cur.fetchone()
                if not session_info: return jsonify({"success": False, "message": "Invalid or expired session."}), 400

                # 2. Validate Location
                dist = haversine_distance(float(data['latitude']), float(data['longitude']), session_info['geofence_lat'], session_info['geofence_lon'])
                if dist > session_info['geofence_radius']:
                    return jsonify({"success": False, "message": f"You are {dist:.0f}m away and outside the allowed radius."}), 403

                # 3. IP and Attendance Record Insertion (in a single transaction)
                cur.execute("INSERT INTO session_ips (session_id, student_id, ip_address) VALUES (%s, %s, %s)", (data['session_id'], student_id, ip_address))
                cur.execute("INSERT INTO attendance_records (session_id, student_id, timestamp, latitude, longitude, ip_address) VALUES (%s, %s, NOW(), %s, %s, %s) ON CONFLICT (session_id, student_id) DO NOTHING", (data['session_id'], student_id, data['latitude'], data['longitude'], ip_address))
                conn.commit()
                return jsonify({"success": True, "message": "Attendance marked successfully!"})

        except psycopg2.IntegrityError as e:
            conn.rollback()
            if 'session_ips_session_id_ip_address_key' in str(e):
                return jsonify({"success": False, "message": "This device has already marked attendance."}), 403
            if 'attendance_records_session_id_student_id_key' in str(e):
                return jsonify({"success": False, "message": "You have already marked attendance."}), 409
            return jsonify({"success": False, "message": "A database error occurred."}), 500
        except Exception as e:
            if conn: conn.rollback()
            print(f"Error marking attendance: {e}")
            return jsonify({"success": False, "message": "A server error occurred."}), 500
        finally:
            if conn: conn.close()

    # --- GET Request Logic ---
    active_session = get_active_ba_anthropology_session()
    return render_template('student_attendance.html', active_session=active_session)

@app.route('/attendance_report')
@controller_required
def attendance_report():
    """Generates and displays the main attendance report grid."""
    conn = get_db_connection()
    if not conn:
        flash("Database error.", "danger")
        return redirect(url_for('controller_dashboard'))
    
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            cur.execute("SELECT id FROM classes WHERE class_name = 'BA - Anthropology'")
            class_id = cur.fetchone()['id']
            
            cur.execute("SELECT id, enrollment_no, name FROM students WHERE batch = 'BA' ORDER BY enrollment_no")
            all_students = cur.fetchall()
            
            cur.execute("SELECT DISTINCT DATE(start_time) as date FROM attendance_sessions WHERE class_id = %s ORDER BY date", (class_id,))
            session_dates = [row['date'] for row in cur.fetchall()]

            if session_dates:
                cur.execute("SELECT ar.student_id, DATE(s.start_time) as date FROM attendance_records ar JOIN attendance_sessions s ON ar.session_id = s.id WHERE s.class_id = %s", (class_id,))
                attended_map = {(rec['student_id'], rec['date']) for rec in cur.fetchall()}

                report_data = []
                for current_date in session_dates:
                    entry = {'date': current_date.strftime('%Y-%m-%d'), 'students': []}
                    for student in all_students:
                        status = "Present" if (student['id'], current_date) in attended_map else "Absent"
                        entry['students'].append({'status': status})
                    report_data.append(entry)
                
                return render_template('attendance_report.html', report_data=report_data, students=all_students, now=datetime.now(timezone.utc))
    except Exception as e:
        print(f"Error generating report: {e}")
        flash("An error occurred.", "danger")
    finally:
        if conn: conn.close()
        
    return render_template('attendance_report.html', report_data=[], students=[])

@app.route('/edit_attendance/<date_str>')
@controller_required
def edit_attendance(date_str):
    """Serves the page for editing a single day's attendance."""
    try:
        attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
    except ValueError:
        return redirect(url_for('attendance_report'))

    if attendance_date < (datetime.now(timezone.utc).date() - timedelta(days=7)):
        flash("Record is too old to be edited.", "warning")
        return redirect(url_for('attendance_report'))
    
    return render_template('edit_attendance.html', attendance_date=date_str, class_name='BA - Anthropology')

@app.route('/api/get_daily_attendance_for_edit/<date_str>')
@controller_required
def api_get_daily_attendance_for_edit(date_str):
    """API to get student presence for a specific day."""
    conn = get_db_connection()
    if not conn: return jsonify({"success": False})
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            cur.execute("SELECT id FROM classes WHERE class_name = 'BA - Anthropology'")
            class_id = cur.fetchone()['id']
            
            cur.execute("SELECT id, enrollment_no, name FROM students WHERE batch = 'BA' ORDER BY enrollment_no")
            all_students = cur.fetchall()

            cur.execute("SELECT DISTINCT ar.student_id FROM attendance_records ar JOIN attendance_sessions s ON ar.session_id = s.id WHERE s.class_id = %s AND DATE(s.start_time) = %s", (class_id, attendance_date))
            present_ids = {row['student_id'] for row in cur.fetchall()}

            student_data = [{'id': s['id'], 'enrollment_no': s['enrollment_no'], 'name': s['name'], 'is_present': s['id'] in present_ids} for s in all_students]
            return jsonify({"success": True, "students": student_data})
    finally:
        if conn: conn.close()

@app.route('/api/update_daily_attendance_record', methods=['POST'])
@controller_required
def api_update_daily_attendance_record():
    """API to mark or unmark a student for a specific day."""
    data = request.get_json()
    date_str, student_id, is_present = data.get('date_str'), data.get('student_id'), data.get('is_present')

    conn = get_db_connection()
    if not conn: return jsonify({"success": False})
    try:
        with conn.cursor() as cur:
            attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            cur.execute("SELECT id FROM classes WHERE class_name = 'BA - Anthropology'")
            class_id = cur.fetchone()['id']
            
            cur.execute("SELECT id FROM attendance_sessions WHERE DATE(start_time) = %s AND class_id = %s LIMIT 1", (attendance_date, class_id))
            session_result = cur.fetchone()

            if not session_result:
                start_time = datetime.combine(attendance_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                cur.execute("INSERT INTO attendance_sessions (class_id, controller_id, session_token, start_time, end_time, is_active) VALUES (%s, %s, %s, %s, %s, FALSE) RETURNING id", (class_id, session['user_id'], secrets.token_hex(16), start_time, start_time + timedelta(minutes=1)))
                session_id = cur.fetchone()[0]
            else:
                session_id = session_result[0]
            
            if is_present:
                cur.execute("INSERT INTO attendance_records (session_id, student_id, timestamp, ip_address) VALUES (%s, %s, NOW(), 'Manual_Edit') ON CONFLICT (session_id, student_id) DO NOTHING", (session_id, student_id))
            else:
                cur.execute("DELETE FROM attendance_records WHERE session_id = %s AND student_id = %s", (session_id, student_id))
            conn.commit()
            return jsonify({"success": True, "message": "Attendance updated."})
    except Exception as e:
        if conn: conn.rollback()
        return jsonify({"success": False, "message": "An error occurred."})
    finally:
        if conn: conn.close()
```

---

### Step 3: Push and Redeploy

1.  **Replace your files:** Make sure your local project has this new version of `api/index.py`.
2.  **Push to GitHub:** Use the standard git commands to upload your changes.
    ```bash
    git add .
    git commit -m "Fix: Add stable Flask secret key"
    git push
    

