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
    if conn is None:
        print(f"DEBUG: get_class_id_by_name: Could not connect to database for class '{class_name}'.")
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM classes WHERE class_name = %s", (class_name,))
        result = cur.fetchone()
        if result:
            print(f"DEBUG: get_class_id_by_name: Found class '{class_name}' with ID: {result[0]}.")
            return result[0]
        else:
            print(f"DEBUG: get_class_id_by_name: Class '{class_name}' not found in DB.")
            return None
    except Exception as e:
        print(f"ERROR: get_class_id_by_name: Exception fetching class ID for '{class_name}': {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_controller_id_by_username(username):
    conn = get_db_connection()
    if conn is None:
        print(f"DEBUG: get_controller_id_by_username: Could not connect to database for user '{username}'.")
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM users WHERE username = %s AND role = 'controller'", (username,))
        result = cur.fetchone()
        if result:
            print(f"DEBUG: get_controller_id_by_username: Found controller '{username}' with ID: {result[0]}.")
            return result[0]
        else:
            print(f"DEBUG: get_controller_id_by_username: Controller '{username}' not found in DB or not a controller role.")
            return None
    except Exception as e:
        print(f"ERROR: get_controller_id_by_username: Exception fetching controller ID for '{username}': {e}")
        return None
    finally:
        if conn:
            conn.close()

def get_active_ba_anthropology_session():
    class_name = 'BA - Anthropology'
    class_id = get_class_id_by_name(class_name)
    if class_id is None:
        print(f"DEBUG: get_active_ba_anthropology_session: Class ID for '{class_name}' not found. Cannot fetch active session.")
        return None
    conn = get_db_connection()
    if conn is None:
        print("DEBUG: get_active_ba_anthropology_session: Could not connect to database.")
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute(
            "SELECT id, session_token, start_time, end_time FROM attendance_sessions WHERE class_id = %s AND is_active = TRUE AND end_time > %s ORDER BY start_time DESC LIMIT 1",
            (class_id, datetime.now(timezone.utc))
        )
        session_data = cur.fetchone()
        if session_data:
            session_dict = dict(session_data)
            end_time_utc = session_dict['end_time'].astimezone(timezone.utc)
            time_remaining = (end_time_utc - datetime.now(timezone.utc)).total_seconds()
            if time_remaining <= 0:
                cur.execute("UPDATE attendance_sessions SET is_active = FALSE WHERE id = %s", (session_dict['id'],))
                conn.commit()
                print(f"DEBUG: Session {session_dict['id']} for '{class_name}' expired and marked inactive.")
                return None
            session_dict['class_name'] = class_name
            session_dict['remaining_time'] = math.ceil(time_remaining)
            return session_dict
        else:
            print(f"DEBUG: No active session found for class '{class_name}' (Class ID: {class_id}).")
            return None
    except Exception as e:
        print(f"ERROR: get_active_ba_anthropology_session: Exception fetching active session for {class_name}: {e}")
        return None
    finally:
        if conn:
            conn.close()

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
            past_sessions_raw = cur.fetchall()
            past_sessions = [
                {
                    'id': s['id'],
                    'start_time': s['start_time'].astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z'),
                    'end_time': s['end_time'].astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z'),
                    'is_active': s['is_active']
                } for s in past_sessions_raw
            ]
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
            "INSERT INTO attendance_sessions (class_id, controller_id, session_token, start_time, end_time, is_active) VALUES (%s, %s, %s, %s, %s, TRUE) RETURNING id",
            (class_id, session['user_id'], session_token, start_time, end_time)
        )
        new_session_id = cur.fetchone()[0]
        conn.commit()
        flash(f"New attendance session (ID: {new_session_id}) started successfully!", "success")
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
        if cur.rowcount > 0:
            return jsonify({"success": True, "message": "Session ended successfully.", "category": "info"})
        else:
            return jsonify({"success": False, "message": "Session not found or already ended.", "category": "warning"})
    except Exception as e:
        conn.rollback()
        return jsonify({"success": False, "message": "An error occurred."})
    finally:
        cur.close()
        conn.close()

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
                return jsonify({"success": False, "message": "Enrollment number not found.", "category": "danger"}), 404
            student_id = student_result[0]

            cur.execute(
                "SELECT c.geofence_lat, c.geofence_lon, c.geofence_radius FROM attendance_sessions s JOIN classes c ON s.class_id = c.id WHERE s.id = %s AND s.is_active = TRUE AND s.end_time > %s",
                (data['session_id'], datetime.now(timezone.utc))
            )
            session_info = cur.fetchone()
            if not session_info:
                return jsonify({"success": False, "message": "Invalid or expired session.", "category": "danger"}), 400

            lat, lon, radius = session_info
            distance = haversine_distance(float(data['latitude']), float(data['longitude']), lat, lon)
            if distance > radius:
                return jsonify({"success": False, "message": f"You are {distance:.0f}m away and outside the allowed radius.", "category": "danger"}), 403

            cur.execute(
                "SELECT student_id FROM session_device_fingerprints WHERE session_id = %s AND fingerprint = %s",
                (data['session_id'], data['device_fingerprint'])
            )
            fingerprint_record = cur.fetchone()
            if fingerprint_record and fingerprint_record[0] != student_id:
                return jsonify({"success": False, "message": "This device has already marked attendance for another student.", "category": "danger"}), 403

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
                return jsonify({"success": False, "message": "Attendance already marked for this session.", "category": "warning"}), 409

            conn.commit()
            return jsonify({"success": True, "message": "Attendance marked successfully!", "category": "success"})

        except Exception as e:
            conn.rollback()
            print(f"ERROR: {e}")
            return jsonify({"success": False, "message": "A server error occurred.", "category": "error"}), 500
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

@app.route('/api/get_student_name/<enrollment_no>')
def api_get_student_name(enrollment_no):
    """API endpoint to get student name by enrollment number (only for BA students)."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection failed."}), 500
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM students WHERE enrollment_no = %s AND batch = 'BA'", (enrollment_no,))
        student_name = cur.fetchone()
        if student_name:
            return jsonify({"success": True, "name": student_name[0]})
        else:
            return jsonify({"success": False, "message": "Student not found or not a BA student."})
    except Exception as e:
        print(f"ERROR: api_get_student_name: Exception fetching student name for {enrollment_no}: {e}")
        return jsonify({"success": False, "message": "An error occurred."}), 500
    finally:
        if conn:
            cur.close()
            conn.close()
            
@app.route('/attendance_report')
@controller_required
def attendance_report():
    """Displays a detailed attendance report for BA - Anthropology."""
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        return redirect(url_for('controller_dashboard'))
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    report_data = []
    class_id = get_class_id_by_name('BA - Anthropology')
    
    if not class_id:
        flash("Error: 'BA - Anthropology' class not found.", "danger")
        return render_template('attendance_report.html', report_data=[])
        
    try:
        cur.execute("SELECT id, enrollment_no, name FROM students WHERE batch = 'BA' ORDER BY enrollment_no")
        all_students = cur.fetchall()
        cur.execute("SELECT id, start_time FROM attendance_sessions WHERE class_id = %s ORDER BY start_time", (class_id,))
        all_sessions = cur.fetchall()

        if all_sessions:
            min_date = min(s['start_time'].date() for s in all_sessions)
            max_date = datetime.now(timezone.utc).date()
            date_range = [min_date + timedelta(days=x) for x in range((max_date - min_date).days + 1)]

            for current_date in date_range:
                daily_entry = {'date': current_date.strftime('%Y-%m-%d'), 'students': []}
                sessions_on_date = [s['id'] for s in all_sessions if s['start_time'].date() == current_date]
                attended_student_ids = set()
                if sessions_on_date:
                    cur.execute("SELECT DISTINCT student_id FROM attendance_records WHERE session_id = ANY(%s)", (sessions_on_date,))
                    attended_student_ids = {row['student_id'] for row in cur.fetchall()}

                is_weekend = current_date.weekday() >= 5
                for student in all_students:
                    status = "Present" if student['id'] in attended_student_ids else "Absent"
                    if not sessions_on_date and is_weekend:
                        status = "Holiday"
                    daily_entry['students'].append({'name': student['name'], 'enrollment_no': student['enrollment_no'], 'status': status})
                report_data.append(daily_entry)
    except Exception as e:
        print(f"ERROR: attendance_report: {e}")
        flash("An error occurred generating the report.", "danger")
    finally:
        if conn: conn.close()
        
    return render_template('attendance_report.html', report_data=report_data, students=all_students)

@app.route('/delete_daily_attendance', methods=['POST'])
@controller_required
def delete_daily_attendance():
    date_str = request.get_json().get('date')
    if not date_str:
        return jsonify({"success": False, "message": "No date provided."}), 400
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection failed."}), 500
    try:
        cur = conn.cursor()
        class_id = get_class_id_by_name('BA - Anthropology')
        date_to_delete = datetime.strptime(date_str, '%Y-%m-%d').date()
        cur.execute(
            "SELECT id FROM attendance_sessions WHERE DATE(start_time AT TIME ZONE 'UTC') = %s AND class_id = %s",
            (date_to_delete, class_id)
        )
        session_ids_to_delete = [row[0] for row in cur.fetchall()]
        if session_ids_to_delete:
            cur.execute("DELETE FROM attendance_sessions WHERE id = ANY(%s)", (session_ids_to_delete,))
            conn.commit()
            return jsonify({"success": True, "message": f"All records for {date_str} deleted."})
        else:
            return jsonify({"success": True, "message": f"No records found for {date_str}."})
    except Exception as e:
        conn.rollback()
        print(f"ERROR: delete_daily_attendance: {e}")
        return jsonify({"success": False, "message": "An error occurred."}), 500
    finally:
        if conn: conn.close()

@app.route('/export_attendance_csv')
@controller_required
def export_attendance_csv():
    # ... This route is unchanged from your original file
    pass
    
@app.route('/edit_attendance/<int:session_id>')
@controller_required
def edit_attendance(session_id):
    # ... This route is unchanged from your original file
    pass
    
@app.route('/api/get_session_students_for_edit/<int:session_id>')
@controller_required
def api_get_session_students_for_edit(session_id):
    # ... This route is unchanged from your original file
    pass
    
@app.route('/api/update_attendance_record', methods=['POST'])
@controller_required
def api_update_attendance_record():
    # ... This route is unchanged from your original file
    pass

if __name__ == '__main__':
    app.run(debug=True, port=5000)