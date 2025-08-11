import os
import psycopg2
import psycopg2.extras
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify, send_file
from functools import wraps
import secrets
import math
import io

app = Flask(__name__)
app.secret_key = os.urandom(24)

CONTROLLER_USERNAME = "controller"
CONTROLLER_PASSWORD = "controller_pass_123"

DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    try:
        conn = psycopg2.connect(DATABASE_URL)
        conn.cursor().execute("SET TIME ZONE 'UTC';")
        conn.commit()
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None

def controller_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'controller':
            flash("You must be logged in as the controller to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_class_id_by_name(class_name):
    conn = get_db_connection()
    if conn is None: return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM classes WHERE class_name = %s", (class_name,))
        result = cur.fetchone()
        return result[0] if result else None
    finally:
        if conn: conn.close()

def get_controller_id_by_username(username):
    conn = get_db_connection()
    if conn is None: return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s AND role = 'controller'", (username,))
        result = cur.fetchone()
        return result[0] if result else None
    finally:
        if conn: conn.close()

def get_active_ba_anthropology_session():
    class_id = get_class_id_by_name('BA - Anthropology')
    if not class_id: return None
    conn = get_db_connection()
    if not conn: return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "SELECT * FROM attendance_sessions WHERE class_id = %s AND is_active = TRUE AND end_time > %s ORDER BY start_time DESC LIMIT 1",
            (class_id, datetime.now(timezone.utc))
        )
        session_data = cur.fetchone()
        if not session_data: return None
        end_time_utc = session_data['end_time'].astimezone(timezone.utc)
        time_remaining = (end_time_utc - datetime.now(timezone.utc)).total_seconds()
        if time_remaining <= 0:
            cur.execute("UPDATE attendance_sessions SET is_active = FALSE WHERE id = %s", (session_data['id'],))
            conn.commit()
            return None
        session_dict = dict(session_data)
        session_dict['class_name'] = 'BA - Anthropology'
        session_dict['remaining_time'] = math.ceil(time_remaining)
        return session_dict
    finally:
        if conn: conn.close()

@app.route('/')
def home():
    if 'user_id' in session and session.get('role') == 'controller':
        return redirect(url_for('controller_dashboard'))
    return redirect(url_for('login'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        if username == CONTROLLER_USERNAME and password == CONTROLLER_PASSWORD:
            controller_id = get_controller_id_by_username(username)
            if controller_id:
                session['user_id'] = controller_id
                session['username'] = username
                session['role'] = 'controller'
                flash(f"Welcome, {username}!", "success")
                return redirect(url_for('controller_dashboard'))
            else:
                flash("Controller user not found in database.", "danger")
        else:
            flash("Invalid username or password.", "danger")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/controller_dashboard')
@controller_required
def controller_dashboard():
    active_session = get_active_ba_anthropology_session()
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        return redirect(url_for('login'))
    
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    past_sessions = []
    ba_anthropology_class_id = get_class_id_by_name('BA - Anthropology')

    if ba_anthropology_class_id:
        try:
            cur.execute(
                "SELECT id, start_time, end_time, is_active FROM attendance_sessions WHERE class_id = %s AND is_active = FALSE ORDER BY start_time DESC",
                (ba_anthropology_class_id,)
            )
            past_sessions = [dict(s) for s in cur.fetchall()]
        except Exception as e:
            print(f"ERROR: controller_dashboard: {e}")
            flash("An error occurred while fetching past sessions.", "danger")
        finally:
            cur.close()
            conn.close()

    return render_template('admin_dashboard.html',
                           active_session=active_session,
                           username=session.get('username'),
                           ba_anthropology_class_id=ba_anthropology_class_id,
                           all_sessions=past_sessions)

@app.route('/start_session', methods=['POST'])
@controller_required
def start_session():
    if get_active_ba_anthropology_session():
        flash("An active session already exists.", "info")
        return redirect(url_for('controller_dashboard'))

    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        return redirect(url_for('controller_dashboard'))
    
    cur = conn.cursor()
    try:
        class_id = get_class_id_by_name('BA - Anthropology')
        if not class_id:
            raise Exception("BA - Anthropology class not found.")
            
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(minutes=10)
        session_token = secrets.token_hex(16)
        
        cur.execute(
            "INSERT INTO attendance_sessions (class_id, controller_id, session_token, start_time, end_time, is_active) VALUES (%s, %s, %s, %s, %s, TRUE)",
            (class_id, session['user_id'], session_token, start_time, end_time)
        )
        conn.commit()
        flash("New attendance session started successfully!", "success")
    except Exception as e:
        conn.rollback()
        print(f"ERROR: start_session: {e}")
        flash("An error occurred while starting the session.", "danger")
    finally:
        cur.close()
        conn.close()
        
    return redirect(url_for('controller_dashboard'))

@app.route('/end_session/<int:session_id>', methods=['POST'])
@controller_required
def end_session(session_id):
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database connection failed."})
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE attendance_sessions SET is_active = FALSE, end_time = %s WHERE id = %s AND controller_id = %s AND is_active = TRUE",
            (datetime.now(timezone.utc), session_id, session['user_id'])
        )
        conn.commit()
        return jsonify({"success": True, "message": "Session ended successfully."})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": "An error occurred."})
    finally:
        cur.close()
        conn.close()


# ==============================================================================
# === THIS IS THE PRIMARY MODIFIED FUNCTION ===
# ==============================================================================
@app.route('/mark_attendance', methods=['GET', 'POST'])
def mark_attendance():
    if request.method == 'POST':
        data = request.form
        required_fields = ['enrollment_no', 'session_id', 'latitude', 'longitude', 'device_fingerprint']
        if not all(field in data and data[field] for field in required_fields):
            return jsonify({"success": False, "message": "Missing required data.", "category": "error"}), 400

        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        conn = get_db_connection()
        if not conn: return jsonify({"success": False, "message": "Database connection failed."}), 500
        
        cur = conn.cursor()
        try:
            cur.execute("SELECT id FROM students WHERE enrollment_no = %s AND batch = 'BA'", (data['enrollment_no'],))
            student_result = cur.fetchone()
            if not student_result:
                return jsonify({"success": False, "message": "Enrollment number not found."}), 404
            student_id = student_result[0]

            cur.execute(
                "SELECT c.geofence_lat, c.geofence_lon, c.geofence_radius FROM attendance_sessions s JOIN classes c ON s.class_id = c.id WHERE s.id = %s AND s.is_active = TRUE AND s.end_time > %s",
                (data['session_id'], datetime.now(timezone.utc))
            )
            session_info = cur.fetchone()
            if not session_info:
                return jsonify({"success": False, "message": "Invalid or expired session."}), 400

            lat, lon, radius = session_info
            distance = haversine_distance(float(data['latitude']), float(data['longitude']), lat, lon)
            if distance > radius:
                return jsonify({"success": False, "message": f"You are {distance:.0f}m away and outside the allowed radius."}), 403

            cur.execute(
                "SELECT student_id FROM session_device_fingerprints WHERE session_id = %s AND fingerprint = %s",
                (data['session_id'], data['device_fingerprint'])
            )
            fingerprint_record = cur.fetchone()
            if fingerprint_record and fingerprint_record[0] != student_id:
                return jsonify({"success": False, "message": "This device has already marked attendance for another student."}), 403

            timestamp = datetime.now(timezone.utc)
            cur.execute(
                "INSERT INTO session_device_fingerprints (session_id, student_id, fingerprint) VALUES (%s, %s, %s) ON CONFLICT DO NOTHING",
                (data['session_id'], student_id, data['device_fingerprint'])
            )
            cur.execute(
                "INSERT INTO attendance_records (session_id, student_id, timestamp, latitude, longitude, ip_address) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (session_id, student_id) DO NOTHING",
                (data['session_id'], student_id, timestamp, float(data['latitude']), float(data['longitude']), ip_address)
            )
            if cur.rowcount == 0:
                conn.commit()
                return jsonify({"success": False, "message": "Attendance already marked for this session."}), 409

            conn.commit()
            return jsonify({"success": True, "message": "Attendance marked successfully!"})

        except Exception as e:
            conn.rollback()
            print(f"ERROR: {e}")
            return jsonify({"success": False, "message": "A server error occurred."}), 500
        finally:
            if conn: conn.close()

    # --- GET: Display the Page ---
    active_session = get_active_ba_anthropology_session()
    geofence_data = {}
    
    # FINAL FIX: Always fetch geofence data, regardless of whether a session is active.
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("SELECT geofence_lat, geofence_lon, geofence_radius FROM classes WHERE class_name = 'BA - Anthropology' LIMIT 1")
            class_info = cur.fetchone()
            if class_info: geofence_data = dict(class_info)
        except Exception as e:
            print(f"Error fetching geofence data: {e}")
        finally:
            if conn: conn.close()

    return render_template('student_attendance.html', active_session=active_session, geofence_data=geofence_data)

# (All other routes like /api/get_student_name, /attendance_report, /edit_attendance etc. remain the same)
# ... Your original code for those routes is correct ...