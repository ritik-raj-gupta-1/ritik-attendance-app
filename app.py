import os
import psycopg2
import psycopg2.extras # Import for DictCursor for cleaner dictionary access
from datetime import datetime, timedelta, timezone
from flask import Flask, render_template, request, redirect, session, url_for, flash, jsonify, send_file
from functools import wraps
import secrets # For generating session tokens
import math # For geofencing calculation
import io # For CSV export

app = Flask(__name__)
app.secret_key = os.urandom(24) # Keep this secure and random

# --- HARDCODED CONTROLLER CREDENTIALS ---
# !!! WARNING: NOT RECOMMENDED FOR PRODUCTION ENVIRONMENTS !!!
# This is for a simplified, fixed-value verification as requested.
CONTROLLER_USERNAME = "controller"
CONTROLLER_PASSWORD = "controller_pass_123"
# --- END HARDCODED CREDENTIALS ---

# Database connection details from Render
DATABASE_URL = os.environ.get('DATABASE_URL')

def get_db_connection():
    """Establishes and returns a connection to the PostgreSQL database."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        # Set timezone to UTC for database session to match Python's datetime.now(timezone.utc)
        # This helps prevent timezone-related issues with TIMESTAMP WITH TIME ZONE
        conn.cursor().execute("SET TIME ZONE 'UTC';")
        conn.commit()
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None

# Decorator to ensure the single controller user is logged in
def controller_required(f):
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'controller':
            flash("You must be logged in as the controller to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# Haversine formula for calculating distance between two lat/lon points
def haversine_distance(lat1, lon1, lat2, lon2):
    R = 6371000 # Radius of Earth in meters
    phi1 = math.radians(lat1)
    phi2 = math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)

    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    distance = R * c # Distance in meters
    return distance

# Helper to get class ID (re-added for explicit usage)
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
            cur.close()
            conn.close()

# Helper to get controller ID (re-added for explicit usage)
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
            cur.close()
            conn.close()

# Helper to get active session for BA - Anthropology specifically
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
        cur.execute("""
            SELECT id, session_token, start_time, end_time, last_updated
            FROM attendance_sessions
            WHERE class_id = %s AND is_active = TRUE AND end_time > %s
            ORDER BY start_time DESC
            LIMIT 1
        """, (class_id, datetime.now(timezone.utc)))
        session_data = cur.fetchone()

        if session_data:
            session_dict = dict(session_data)
            end_time_utc = session_dict['end_time'].astimezone(timezone.utc)
            current_time_utc = datetime.now(timezone.utc)
            time_remaining = (end_time_utc - current_time_utc).total_seconds()

            if time_remaining <= 0:
                # Session has truly expired, mark inactive
                cur.execute("UPDATE attendance_sessions SET is_active = FALSE WHERE id = %s", (session_dict['id'],))
                conn.commit()
                print(f"DEBUG: Session {session_dict['id']} for '{class_name}' expired and marked inactive. Remaining: {time_remaining}s")
                return None
            
            session_dict['class_name'] = class_name # Add class name for template
            session_dict['remaining_time'] = math.ceil(time_remaining)
            # Format times for display in template
            session_dict['start_time'] = session_dict['start_time'].astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')
            session_dict['end_time'] = session_dict['end_time'].astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')
            session_dict['last_updated'] = session_dict['last_updated'].astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z') if session_dict['last_updated'] else 'N/A'
            
            print(f"DEBUG: Found active session {session_dict['id']} for '{class_name}'. Remaining time: {session_dict['remaining_time']}s")
            return session_dict
        else:
            print(f"DEBUG: No active session found for class '{class_name}' (Class ID: {class_id}).")
            return None
    except Exception as e:
        print(f"ERROR: get_active_ba_anthropology_session: Exception fetching active session for {class_name}: {e}")
        return None
    finally:
        if conn:
            cur.close()
            conn.close()

# --- ROUTES ---

@app.route('/')
def home():
    """Redirects to the controller dashboard if logged in, otherwise to login page."""
    if 'user_id' in session and session.get('role') == 'controller':
        return redirect(url_for('controller_dashboard'))
    return render_template('login.html')

@app.route('/login', methods=['GET', 'POST'])
def login():
    """Handles controller login with simple string comparison."""
    if request.method == 'POST':
        username = request.form.get('username')
        password = request.form.get('password')
        
        if username == CONTROLLER_USERNAME and password == CONTROLLER_PASSWORD:
            controller_id = get_controller_id_by_username(username)
            if controller_id:
                session['user_id'] = controller_id
                session['username'] = username
                session['role'] = 'controller'
                flash(f"Welcome, {username} (Controller)!", "success")
                return redirect(url_for('controller_dashboard'))
            else:
                flash("Controller user not found in database. Please contact support.", "danger")
        else:
            flash("Invalid username or password. Please try again.", "danger")
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
    """Controller dashboard: manages sessions, views reports, etc."""
    active_session = get_active_ba_anthropology_session() # Use helper for active session

    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        return redirect(url_for('login'))

    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    past_sessions = []
    
    ba_anthropology_class_id = get_class_id_by_name('BA - Anthropology')

    if ba_anthropology_class_id is None:
        flash("Error: 'BA - Anthropology' class not found in database. Please ensure setup.", "danger")
        print("ERROR: controller_dashboard: 'BA - Anthropology' class_id not found. Displaying empty dashboard.")
    else:
        try:
            # Fetch all past (inactive) sessions for this specific class
            cur.execute("""
                SELECT id, start_time, end_time, is_active
                FROM attendance_sessions
                WHERE class_id = %s AND is_active = FALSE
                ORDER BY start_time DESC
            """, (ba_anthropology_class_id,))
            all_sessions_raw = cur.fetchall()
            past_sessions = [{
                'id': s['id'],
                'start_time': s['start_time'].astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z'),
                'end_time': s['end_time'].astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z'),
                'is_active': s['is_active']
            } for s in all_sessions_raw]
            print(f"DEBUG: controller_dashboard: Retrieved {len(past_sessions)} past sessions for BA - Anthropology (Class ID: {ba_anthropology_class_id}).")

        except Exception as e:
            print(f"ERROR: controller_dashboard: Exception fetching past sessions: {e}")
            flash("An error occurred while fetching past sessions.", "danger")
        finally:
            cur.close()
            conn.close()

    print(f"DEBUG: controller_dashboard: Rendering with active_session: {active_session is not None}")
    return render_template('admin_dashboard.html',
                           active_session=active_session,
                           username=session.get('username'),
                           ba_anthropology_class_id=ba_anthropology_class_id, # Still passed for the form
                           all_sessions=past_sessions) # Renamed for clarity in template

@app.route('/start_session', methods=['POST'])
@controller_required
def start_session():
    """Starts a new attendance session for BA - Anthropology."""
    controller_id = session['user_id']
    
    existing_session = get_active_ba_anthropology_session()
    if existing_session:
        flash("An active attendance session for BA - Anthropology already exists. Please end it before starting a new one.", "info")
        print(f"DEBUG: start_session: Tried to start new session, but active session {existing_session['id']} already exists.")
        return redirect(url_for('controller_dashboard'))

    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        print("ERROR: start_session: Could not connect to database.")
        return redirect(url_for('controller_dashboard'))
    cur = conn.cursor()

    try:
        class_name = 'BA - Anthropology'
        ba_anthropology_class_id = get_class_id_by_name(class_name)

        if ba_anthropology_class_id is None:
            flash(f"Error: Class '{class_name}' not found in database. Cannot start session.", "danger")
            print(f"ERROR: start_session: Class ID for '{class_name}' not found. Cannot start session.")
            return redirect(url_for('controller_dashboard'))

        session_token = secrets.token_hex(16)
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(minutes=10)

        cur.execute(
            "INSERT INTO attendance_sessions (class_id, controller_id, session_token, start_time, end_time, is_active) VALUES (%s, %s, %s, %s, %s, TRUE) RETURNING id",
            (ba_anthropology_class_id, controller_id, session_token, start_time, end_time)
        )
        new_session_id = cur.fetchone()[0]
        conn.commit()
        flash(f"Attendance session for {class_name} started successfully! Session ID: {new_session_id}", "success")
        print(f"DEBUG: New session for '{class_name}' started successfully. ID: {new_session_id}")
    except Exception as e:
        print(f"ERROR: start_session: Exception starting attendance session: {e}")
        flash("An error occurred while starting the attendance session.", "danger")
        conn.rollback()
    finally:
        if conn:
            cur.close()
            conn.close()
    
    return redirect(url_for('controller_dashboard'))

@app.route('/end_session/<int:session_id>', methods=['POST'])
@controller_required
def end_session(session_id):
    """Ends an active attendance session via AJAX."""
    conn = get_db_connection()
    if not conn:
        print("ERROR: end_session: Database connection failed.")
        return jsonify({"success": False, "message": "Database connection failed.", "category": "error"})
    cur = conn.cursor()
    try:
        cur.execute(
            "UPDATE attendance_sessions SET is_active = FALSE, end_time = %s, last_updated = %s WHERE id = %s AND controller_id = %s AND is_active = TRUE",
            (datetime.now(timezone.utc), datetime.now(timezone.utc), session_id, session['user_id'])
        )
        conn.commit()
        if cur.rowcount > 0:
            print(f"DEBUG: Session {session_id} successfully ended by controller {session['user_id']}.")
            return jsonify({"success": True, "message": "Session ended successfully.", "category": "info"})
        else:
            print(f"DEBUG: Session {session_id} not found, not active, or not owned by controller {session['user_id']}. No update made.")
            return jsonify({"success": False, "message": "Session not found or already ended.", "category": "warning"})
    except Exception as e:
        print(f"ERROR: end_session: Exception ending session {session_id}: {e}")
        conn.rollback()
        return jsonify({"success": False, "message": "An error occurred while ending the session.", "category": "error"})
    finally:
        if conn:
            cur.close()
            conn.close()

# ==============================================================================
# === THIS IS THE PRIMARY MODIFIED FUNCTION ===
# It now includes device fingerprinting and passes geofence data to the template.
# ==============================================================================
@app.route('/mark_attendance', methods=['GET', 'POST'])
def mark_attendance():
    """
    Handles student attendance with device fingerprinting and on-load location check.
    """
    if request.method == 'POST':
        # --- POST: Handle Form Submission ---
        data = request.form
        required_fields = ['enrollment_no', 'session_id', 'latitude', 'longitude', 'device_fingerprint']
        if not all(field in data and data[field] for field in required_fields):
            return jsonify({"success": False, "message": "Missing required data from form.", "category": "error"}), 400

        # Get the real IP address from behind Render's proxy
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr)
        
        conn = get_db_connection()
        if not conn:
            return jsonify({"success": False, "message": "Database connection failed.", "category": "error"}), 500
        
        cur = conn.cursor()
        try:
            # 1. Verify Student
            cur.execute("SELECT id FROM students WHERE enrollment_no = %s AND batch = 'BA'", (data['enrollment_no'],))
            student_result = cur.fetchone()
            if not student_result:
                return jsonify({"success": False, "message": "Enrollment number not found.", "category": "danger"}), 404
            student_id = student_result[0]

            # 2. Verify Session and Geofence
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

            # 3. Device Fingerprint Verification
            cur.execute(
                "SELECT student_id FROM session_device_fingerprints WHERE session_id = %s AND fingerprint = %s",
                (data['session_id'], data['device_fingerprint'])
            )
            fingerprint_record = cur.fetchone()
            if fingerprint_record and fingerprint_record[0] != student_id:
                print(f"SECURITY: Device fingerprint {data['device_fingerprint']} already used by another student in session {data['session_id']}.")
                return jsonify({"success": False, "message": "This device has already marked attendance for another student in this session.", "category": "danger"}), 403

            # 4. Record Fingerprint and Attendance
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
                conn.commit() # Commit fingerprint insert even if attendance already marked
                return jsonify({"success": False, "message": "Attendance already marked for this session.", "category": "warning"}), 409

            conn.commit()
            return jsonify({"success": True, "message": "Attendance marked successfully!", "category": "success"})

        except Exception as e:
            conn.rollback()
            print(f"ERROR in mark_attendance POST: {e}")
            return jsonify({"success": False, "message": "A server error occurred.", "category": "error"}), 500
        finally:
            if conn:
                cur.close()
                conn.close()

    # --- GET: Display the Page ---
    active_session = get_active_ba_anthropology_session()
    geofence_data = {}
    if active_session:
        conn = get_db_connection()
        if conn:
            try:
                cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
                cur.execute("SELECT geofence_lat, geofence_lon, geofence_radius FROM classes WHERE class_name = 'BA - Anthropology' LIMIT 1")
                class_info = cur.fetchone()
                if class_info:
                    geofence_data = dict(class_info)
            except Exception as e:
                print(f"Error fetching geofence data: {e}")
            finally:
                if conn:
                    cur.close()
                    conn.close()

    return render_template('student_attendance.html', active_session=active_session, geofence_data=geofence_data)

@app.route('/api/get_student_name/<enrollment_no>')
def api_get_student_name(enrollment_no):
    """API endpoint to get student name by enrollment number (only for BA students)."""
    conn = get_db_connection()
    if not conn:
        print("ERROR: api_get_student_name: Database connection failed.")
        return jsonify({"success": False, "message": "Database connection failed."}), 500
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM students WHERE enrollment_no = %s AND batch = 'BA'", (enrollment_no,))
        student_name = cur.fetchone()
        if student_name:
            print(f"DEBUG: api_get_student_name: Found student {enrollment_no}: {student_name[0]}.")
            return jsonify({"success": True, "name": student_name[0]})
        else:
            print(f"DEBUG: api_get_student_name: Student {enrollment_no} not found or not a BA student.")
            return jsonify({"success": False, "message": "Student not found or not a BA student."})
    except Exception as e:
        print(f"ERROR: api_get_student_name: Exception fetching student name for {enrollment_no}: {e}")
        return jsonify({"success": False, "message": "An error occurred."}), 500
    finally:
        if conn:
            cur.close()
            conn.close()

@app.route('/api/get_active_ba_session')
def api_get_active_ba_session():
    """API endpoint to get the active BA - Anthropology session ID for students."""
    active_session = get_active_ba_anthropology_session()
    if active_session:
        print(f"DEBUG: api_get_active_ba_session: Found active session ID: {active_session['id']}.")
        return jsonify({"success": True, "session_id": active_session['id'], "remaining_time": active_session['remaining_time']})
    else:
        print("DEBUG: api_get_active_ba_session: No active BA Anthropology session found.")
        return jsonify({"success": False, "message": "No active BA - Anthropology session."})

@app.route('/attendance_report')
@controller_required
def attendance_report():
    """Displays a detailed attendance report for BA - Anthropology."""
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        print("ERROR: attendance_report: Database connection failed.")
        return redirect(url_for('controller_dashboard'))
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    report_data = []
    
    class_name = 'BA - Anthropology'
    ba_anthropology_class_id = get_class_id_by_name(class_name)

    if ba_anthropology_class_id is None:
        flash("Error: 'BA - Anthropology' class not found in database. Cannot generate report.", "danger")
        print(f"ERROR: attendance_report: Class ID for '{class_name}' not found. Cannot generate report.")
        return render_template('attendance_report.html', report_data=[], students=[])

    try:
        cur.execute("SELECT id, enrollment_no, name FROM students WHERE batch = 'BA' ORDER BY enrollment_no")
        all_students = cur.fetchall()
        print(f"DEBUG: attendance_report: Retrieved {len(all_students)} BA students for report.")

        cur.execute("""
            SELECT id, start_time
            FROM attendance_sessions
            WHERE class_id = %s
            ORDER BY start_time ASC
        """, (ba_anthropology_class_id,))
        all_sessions = cur.fetchall()
        print(f"DEBUG: attendance_report: Retrieved {len(all_sessions)} sessions for report.")

        if not all_sessions:
            if not all_students:
                return render_template('attendance_report.html', report_data=[], students=[])
            min_date = datetime.now(timezone.utc).date()
        else:
            min_date = min(s['start_time'].date() for s in all_sessions)
        
        max_date = datetime.now(timezone.utc).date()

        current_date = min_date
        while current_date <= max_date:
            daily_entry = {'date': current_date.strftime('%Y-%m-%d'), 'students': []}
            sessions_on_this_date = [s['id'] for s in all_sessions if s['start_time'].date() == current_date]

            is_weekend = current_date.weekday() in [5, 6]
            if not sessions_on_this_date and is_weekend:
                for student in all_students:
                    daily_entry['students'].append({'enrollment_no': student['enrollment_no'], 'name': student['name'], 'status': 'Holiday'})
            else:
                attended_student_ids = set()
                if sessions_on_this_date:
                    cur.execute("SELECT DISTINCT student_id FROM attendance_records WHERE session_id = ANY(%s)", (sessions_on_this_date,))
                    attended_student_ids = {row['student_id'] for row in cur.fetchall()}

                for student in all_students:
                    status = 'Present' if student['id'] in attended_student_ids else 'Absent'
                    daily_entry['students'].append({'enrollment_no': student['enrollment_no'], 'name': student['name'], 'status': status})
            
            report_data.append(daily_entry)
            current_date += timedelta(days=1)
        
        print(f"DEBUG: attendance_report: Generated summary for {len(report_data)} days.")

    except Exception as e:
        print(f"ERROR: attendance_report: Exception generating report: {e}")
        flash("An error occurred while generating the attendance report.", "danger")
    finally:
        if conn:
            cur.close()
            conn.close()
    
    return render_template('attendance_report.html', report_data=report_data, students=all_students)

# ==============================================================================
# === MODIFIED delete_daily_attendance ROUTE ===
# This is updated to also remove device fingerprints by relying on CASCADE.
# ==============================================================================
@app.route('/delete_daily_attendance', methods=['POST'])
@controller_required
def delete_daily_attendance():
    """Deletes all attendance records and sessions for a specific date and class."""
    data = request.get_json()
    date_str = data.get('date')

    if not date_str:
        print("ERROR: delete_daily_attendance: No date provided for deletion.")
        return jsonify({"success": False, "message": "No date provided.", "category": "error"}), 400

    conn = get_db_connection()
    if not conn:
        print("ERROR: delete_daily_attendance: Database connection failed.")
        return jsonify({"success": False, "message": "Database connection failed.", "category": "error"}), 500

    try:
        date_to_delete = datetime.strptime(date_str, '%Y-%m-%d').date()
        print(f"DEBUG: delete_daily_attendance: Attempting to delete attendance for date: {date_to_delete}.")

        cur = conn.cursor()

        class_name = 'BA - Anthropology'
        ba_anthropology_class_id = get_class_id_by_name(class_name)
        if ba_anthropology_class_id is None:
            raise Exception(f"Class '{class_name}' not found in database. Cannot delete.")

        cur.execute("""
            SELECT id FROM attendance_sessions
            WHERE DATE(start_time AT TIME ZONE 'UTC') = %s
            AND class_id = %s
        """, (date_to_delete, ba_anthropology_class_id))
        session_ids_to_delete = [row[0] for row in cur.fetchall()]

        if not session_ids_to_delete:
            print(f"DEBUG: delete_daily_attendance: No sessions found for date {date_to_delete} and class {class_name}.")
            return jsonify({"success": True, "message": f"No attendance records found for {date_to_delete} for {class_name}.", "category": "info"})

        # The ON DELETE CASCADE constraint on attendance_records and session_device_fingerprints
        # will automatically delete related records when a session is deleted.
        cur.execute("DELETE FROM attendance_sessions WHERE id = ANY(%s)", (session_ids_to_delete,))
        deleted_sessions_count = cur.rowcount
        print(f"DEBUG: Deleted {deleted_sessions_count} sessions. Related records for fingerprints and attendance were auto-deleted by CASCADE.")

        # Also remove the obsolete daily IP log if it exists for that day.
        cur.execute("DELETE FROM daily_attendance_ips WHERE date = %s", (date_to_delete,))
        print(f"DEBUG: Deleted {cur.rowcount} obsolete daily IP logs for date {date_to_delete}.")
        
        conn.commit()
        return jsonify({"success": True, "message": f"All attendance records, sessions, and fingerprints for {date_to_delete} have been deleted.", "category": "success"}), 200

    except Exception as e:
        print(f"ERROR: delete_daily_attendance: Exception during deletion for date {date_str}: {e}")
        conn.rollback()
        return jsonify({"success": False, "message": "An error occurred while deleting daily attendance.", "category": "error"}), 500
    finally:
        if conn:
            cur.close()
            conn.close()


@app.route('/export_attendance_csv')
@controller_required
def export_attendance_csv():
    """Exports attendance data to a CSV file."""
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed for export.", "danger")
        return redirect(url_for('attendance_report'))
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

    class_name = 'BA - Anthropology'
    ba_anthropology_class_id = get_class_id_by_name(class_name)
    if ba_anthropology_class_id is None:
        flash(f"Error: Class '{class_name}' not found in database. Cannot export report.", "danger")
        print(f"ERROR: export_attendance_csv: Class ID for '{class_name}' not found.")
        return redirect(url_for('attendance_report'))

    try:
        cur.execute("""
            SELECT s.enrollment_no, s.name, s.batch, c.class_name, asess.start_time, ar.timestamp, ar.latitude, ar.longitude, ar.ip_address
            FROM attendance_records ar
            JOIN students s ON ar.student_id = s.id
            JOIN attendance_sessions asess ON ar.session_id = asess.id
            JOIN classes c ON asess.class_id = c.id
            WHERE s.batch = 'BA' AND c.id = %s
            ORDER BY ar.timestamp DESC
        """, (ba_anthropology_class_id,))
        rows = cur.fetchall()

        output = io.StringIO()
        output.write("Enrollment No,Student Name,Batch,Class Name,Session Start Time,Attendance Marked Time,Latitude,Longitude,IP Address\n")
        for row in rows:
            formatted_row = [
                str(row['enrollment_no']),
                str(row['name']),
                str(row['batch']),
                str(row['class_name']),
                row['start_time'].astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z'),
                row['timestamp'].astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z'),
                str(row['latitude']) if row['latitude'] is not None else '',
                str(row['longitude']) if row['longitude'] is not None else '',
                str(row['ip_address']) if row['ip_address'] is not None else ''
            ]
            output.write(",".join(formatted_row) + "\n")
        
        output.seek(0)

        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name=f'attendance_report_{class_name.replace(" ", "_")}.csv'
        )

    except Exception as e:
        print(f"ERROR: export_attendance_csv: Exception during CSV export: {e}")
        flash("An error occurred during CSV export.", "danger")
        return redirect(url_for('attendance_report'))
    finally:
        if conn:
            cur.close()
            conn.close()

@app.route('/edit_attendance/<int:session_id>')
@controller_required
def edit_attendance(session_id):
    """Allows controller to manually edit attendance for a specific session."""
    conn = get_db_connection()
    session_info = None
    if conn is None:
        flash("Database connection failed.", "danger")
        return redirect(url_for('controller_dashboard'))
    
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        cur.execute("""
            SELECT asess.id, c.class_name, asess.start_time
            FROM attendance_sessions asess
            JOIN classes c ON asess.class_id = c.id
            WHERE asess.id = %s AND c.class_name = 'BA - Anthropology'
        """, (session_id,))
        session_info_raw = cur.fetchone()
        if session_info_raw:
            session_info = {
                'id': session_info_raw['id'],
                'class_name': session_info_raw['class_name'],
                'start_time': session_info_raw['start_time'].astimezone(timezone.utc).strftime('%Y-%m-%d %H:%M:%S %Z')
            }
            print(f"DEBUG: edit_attendance: Loaded session details for ID {session_id}.")
        else:
            flash("Session not found or not a BA - Anthropology session.", "danger")
            print(f"DEBUG: edit_attendance: Session ID {session_id} not found or not for BA - Anthropology.")
            return redirect(url_for('controller_dashboard'))
    except Exception as e:
        print(f"ERROR: edit_attendance: Exception fetching session info for {session_id}: {e}")
        flash("An error occurred while loading session details.", "danger")
        return redirect(url_for('controller_dashboard'))
    finally:
        if conn:
            cur.close()
            conn.close()
        
    return render_template('edit_attendance.html', session=session_info)

@app.route('/api/get_session_students_for_edit/<int:session_id>')
@controller_required
def api_get_session_students_for_edit(session_id):
    """API endpoint to get all BA students for a session, including their attendance status for editing."""
    conn = get_db_connection()
    if not conn:
        print("ERROR: api_get_session_students_for_edit: Database connection failed.")
        return jsonify({"success": False, "message": "Database connection failed.", "students": []}), 500
    cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
    try:
        cur.execute("SELECT id, enrollment_no, name, batch FROM students WHERE batch = 'BA' ORDER BY enrollment_no")
        all_ba_students_raw = cur.fetchall()

        cur.execute("SELECT student_id FROM attendance_records WHERE session_id = %s", (session_id,))
        present_student_ids = {row['student_id'] for row in cur.fetchall()}

        students_data = []
        for student in all_ba_students_raw:
            students_data.append({
                'id': student['id'],
                'enrollment_no': student['enrollment_no'],
                'name': student['name'],
                'batch': student['batch'],
                'is_present': student['id'] in present_student_ids
            })
        print(f"DEBUG: api_get_session_students_for_edit: Retrieved attendance for {len(students_data)} students in session {session_id}.")
        return jsonify({"success": True, "students": students_data})
    except Exception as e:
        print(f"ERROR: api_get_session_students_for_edit: Exception fetching session students for edit: {e}")
        return jsonify({"success": False, "message": "An error occurred while fetching student data."}), 500
    finally:
        if conn:
            cur.close()
            conn.close()

@app.route('/api/update_attendance_record', methods=['POST'])
@controller_required
def api_update_attendance_record():
    """API endpoint to manually update an attendance record (mark present/absent) by controller."""
    data = request.get_json()
    session_id = data.get('session_id')
    student_id = data.get('student_id')
    is_present = data.get('is_present')
    
    if not all([session_id, student_id is not None, is_present is not None]):
        print("ERROR: api_update_attendance_record: Missing session_id, student_id, or is_present in request.")
        return jsonify({"success": False, "message": "Missing required data.", "category": "error"}), 400

    conn = get_db_connection()
    if not conn:
        print("ERROR: api_update_attendance_record: Database connection failed.")
        return jsonify({"success": False, "message": "Database connection failed.", "category": "error"}), 500
    cur = conn.cursor()
    try:
        if is_present:
            # Directly use ON CONFLICT. If a record already exists, DO NOTHING.
            # This is robust because database_setup.sql now includes the UNIQUE constraint.
            cur.execute(
                """
                INSERT INTO attendance_records (session_id, student_id, timestamp, latitude, longitude, ip_address)
                VALUES (%s, %s, %s, NULL, NULL, 'Manual_Edit')
                ON CONFLICT (session_id, student_id) DO NOTHING
                """,
                (session_id, student_id, datetime.now(timezone.utc))
            )
            if cur.rowcount > 0:
                print(f"DEBUG: api_update_attendance_record: Inserted new record for student {student_id} in session {session_id}.")
            else:
                print(f"DEBUG: api_update_attendance_record: Record for student {student_id} in session {session_id} already exists (present). No change made.")
        else:
            # Delete the record if marking absent
            cur.execute(
                "DELETE FROM attendance_records WHERE session_id = %s AND student_id = %s",
                (session_id, student_id)
            )
            if cur.rowcount > 0:
                print(f"DEBUG: api_update_attendance_record: Deleted record for student {student_id} in session {session_id}.")
            else:
                print(f"DEBUG: api_update_attendance_record: Record for student {student_id} in session {session_id} not found (already absent?). No change made.")
        conn.commit()
        return jsonify({"success": True, "message": "Attendance updated.", "category": "success"})
    except Exception as e:
        print(f"ERROR: api_update_attendance_record: Exception updating attendance record: {e}")
        conn.rollback()
        return jsonify({"success": False, "message": "An error occurred while updating attendance.", "category": "error"}), 500
    finally:
        if conn:
            cur.close()
            conn.close()

# Utility route to generate password hashes (for local use, remove in production)
@app.route('/generate_hash/<password_text>')
def generate_hash_route(password_text):
    return "Password hashing utility is not active in this simplified version."

if __name__ == '__main__':
    # For Render, the Gunicorn command in Procfile runs the app.
    print("Running Flask app locally (for development purposes, use 'gunicorn app:app' for production deployments).")
    app.run(debug=True, port=5000)