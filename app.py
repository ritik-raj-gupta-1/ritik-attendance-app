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

# Use environment variable for the database URL in production
DATABASE_URL = os.environ.get('DATABASE_URL', 'postgresql://user:password@localhost/attendance_db')

def get_db_connection():
    """Establishes a connection to the database."""
    try:
        conn = psycopg2.connect(DATABASE_URL)
        # It's good practice to set the time zone for the session
        with conn.cursor() as cur:
            cur.execute("SET TIME ZONE 'UTC';")
        conn.commit()
        return conn
    except Exception as e:
        print(f"Error connecting to the database: {e}")
        return None

def controller_required(f):
    """Decorator to protect routes that require controller access."""
    @wraps(f)
    def decorated_function(*args, **kwargs):
        if 'user_id' not in session or session.get('role') != 'controller':
            flash("You must be logged in as the controller to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

def haversine_distance(lat1, lon1, lat2, lon2):
    """Calculates the distance between two GPS coordinates."""
    R = 6371000  # Earth radius in meters
    phi1, phi2 = math.radians(lat1), math.radians(lat2)
    delta_phi = math.radians(lat2 - lat1)
    delta_lambda = math.radians(lon2 - lon1)
    a = math.sin(delta_phi / 2)**2 + math.cos(phi1) * math.cos(phi2) * math.sin(delta_lambda / 2)**2
    c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
    return R * c

def get_class_id_by_name(class_name):
    """Retrieves the ID of a class by its name."""
    conn = get_db_connection()
    if conn is None: return None
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT id FROM classes WHERE class_name = %s", (class_name,))
            result = cur.fetchone()
            return result[0] if result else None
    finally:
        if conn: conn.close()

def get_active_ba_anthropology_session():
    """Checks for and returns the currently active session for the specific class."""
    class_id = get_class_id_by_name('BA - Anthropology')
    if not class_id: return None
    conn = get_db_connection()
    if not conn: return None
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # Check for an active session that hasn't ended yet
            cur.execute(
                "SELECT id, session_token, start_time, end_time, geofence_lat, geofence_lon, geofence_radius FROM attendance_sessions WHERE class_id = %s AND is_active = TRUE AND end_time > NOW() ORDER BY start_time DESC LIMIT 1",
                (class_id,)
            )
            session_data = cur.fetchone()
            if not session_data: return None
            
            # Calculate remaining time and format the data
            time_remaining = (session_data['end_time'] - datetime.now(timezone.utc)).total_seconds()
            if time_remaining <= 0:
                # If time is up, deactivate the session in the DB
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
    """Redirects to the student attendance page by default."""
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
                with conn.cursor() as cur:
                    cur.execute("SELECT id FROM users WHERE username = %s", (username,))
                    user = cur.fetchone()
                conn.close()
                if user:
                    session['user_id'] = user[0]
                    session['username'] = username
                    session['role'] = 'controller'
                    flash(f"Welcome, {username}!", "success")
                    return redirect(url_for('controller_dashboard'))
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
    """Starts a new attendance session based on the controller's location."""
    if get_active_ba_anthropology_session():
        return jsonify({"success": False, "message": "An active session already exists.", "category": "info"}), 409

    data = request.get_json()
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    if not latitude or not longitude:
        return jsonify({"success": False, "message": "Location data is required to start a session.", "category": "danger"}), 400

    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection failed.", "category": "danger"}), 500
    
    try:
        with conn.cursor() as cur:
            class_id = get_class_id_by_name('BA - Anthropology')
            if not class_id:
                raise Exception("Class 'BA - Anthropology' not found.")
            
            start_time = datetime.now(timezone.utc)
            end_time = start_time + timedelta(minutes=5)
            session_token = secrets.token_hex(16)
            
            cur.execute(
                """
                INSERT INTO attendance_sessions 
                (class_id, controller_id, session_token, start_time, end_time, is_active, geofence_lat, geofence_lon, geofence_radius) 
                VALUES (%s, %s, %s, %s, %s, TRUE, %s, %s, %s) RETURNING id
                """,
                (class_id, session['user_id'], session_token, start_time, end_time, latitude, longitude, 40) # Radius is 40m
            )
            new_session_id = cur.fetchone()[0]
            conn.commit()
            return jsonify({"success": True, "message": f"New session (ID: {new_session_id}) started!", "category": "success"})
    except Exception as e:
        conn.rollback()
        print(f"ERROR starting session: {e}")
        return jsonify({"success": False, "message": "An error occurred while starting the session.", "category": "danger"}), 500
    finally:
        if conn: conn.close()

@app.route('/end_session/<int:session_id>', methods=['POST'])
@controller_required
def end_session(session_id):
    """Manually ends an active session."""
    conn = get_db_connection()
    if not conn: return jsonify({"success": False, "message": "Database connection failed."})
    try:
        with conn.cursor() as cur:
            cur.execute(
                "UPDATE attendance_sessions SET is_active = FALSE, end_time = NOW() WHERE id = %s AND controller_id = %s AND is_active = TRUE",
                (session_id, session['user_id'])
            )
            conn.commit()
            if cur.rowcount > 0:
                return jsonify({"success": True, "message": "Session ended successfully.", "category": "info"})
            else:
                return jsonify({"success": False, "message": "Session not found or already ended.", "category": "warning"})
    finally:
        if conn: conn.close()

@app.route('/mark_attendance', methods=['GET', 'POST'])
def mark_attendance():
    """Handles student attendance marking and displays the student-facing page."""
    if request.method == 'POST':
        data = request.form
        required_fields = ['enrollment_no', 'session_id', 'latitude', 'longitude']
        if not all(field in data and data[field] for field in required_fields):
            return jsonify({"success": False, "message": "Missing required data.", "category": "error"}), 400

        # Get the real user IP, cleaning up potential comma-separated lists from proxies
        ip_address = request.headers.get('X-Forwarded-For', request.remote_addr).split(',')[0].strip()
        
        conn = get_db_connection()
        if not conn: return jsonify({"success": False, "message": "Database connection failed."}), 500
        
        try:
            with conn.cursor() as cur:
                # 1. Validate Enrollment Number
                cur.execute("SELECT id FROM students WHERE enrollment_no = %s AND batch = 'BA'", (data['enrollment_no'],))
                student_result = cur.fetchone()
                if not student_result:
                    return jsonify({"success": False, "message": "Enrollment number not found.", "category": "danger"}), 404
                student_id = student_result[0]

                # 2. Validate Session
                cur.execute(
                    "SELECT geofence_lat, geofence_lon, geofence_radius FROM attendance_sessions WHERE id = %s AND is_active = TRUE AND end_time > NOW()",
                    (data['session_id'],)
                )
                session_info = cur.fetchone()
                if not session_info:
                    return jsonify({"success": False, "message": "Invalid or expired session.", "category": "danger"}), 400

                # 3. Validate Location
                lat, lon, radius = session_info
                distance = haversine_distance(float(data['latitude']), float(data['longitude']), lat, lon)
                if distance > radius:
                    return jsonify({"success": False, "message": f"You are {distance:.0f}m away and outside the allowed radius.", "category": "danger"}), 403

                # 4. PRIMARY VERIFICATION: Check if IP has already been used this session
                cur.execute(
                    "INSERT INTO session_ips (session_id, student_id, ip_address) VALUES (%s, %s, %s)",
                    (data['session_id'], student_id, ip_address)
                )

                # 5. Insert the main attendance record
                cur.execute(
                    "INSERT INTO attendance_records (session_id, student_id, timestamp, latitude, longitude, ip_address) VALUES (%s, %s, %s, %s, %s, %s) ON CONFLICT (session_id, student_id) DO NOTHING",
                    (data['session_id'], student_id, datetime.now(timezone.utc), float(data['latitude']), float(data['longitude']), ip_address)
                )

                if cur.rowcount == 0:
                    conn.rollback() # Rollback the IP insert if attendance was already marked
                    return jsonify({"success": False, "message": "Attendance already marked for this session.", "category": "warning"}), 409

                conn.commit()
                return jsonify({"success": True, "message": "Attendance marked successfully!", "category": "success"})

        except psycopg2.IntegrityError as e:
            conn.rollback()
            # This specific error is triggered if the UNIQUE constraint on (session_id, ip_address) fails
            if 'session_ips_session_id_ip_address_key' in str(e):
                return jsonify({"success": False, "message": "This device has already been used to mark attendance.", "category": "danger"}), 403
            return jsonify({"success": False, "message": "A database integrity error occurred.", "category": "error"}), 500
        except Exception as e:
            conn.rollback()
            print(f"ERROR marking attendance: {e}")
            return jsonify({"success": False, "message": "A server error occurred.", "category": "error"}), 500
        finally:
            if conn: conn.close()

    # --- GET Request Logic: Display the Page ---
    active_session = get_active_ba_anthropology_session()
    geofence_data = {}
    if active_session:
        geofence_data = {
            'geofence_lat': active_session['geofence_lat'],
            'geofence_lon': active_session['geofence_lon'],
            'geofence_radius': active_session['geofence_radius']
        }
    
    return render_template('student_attendance.html', active_session=active_session, geofence_data=geofence_data)

@app.route('/api/get_student_name/<enrollment_no>')
def api_get_student_name(enrollment_no):
    """API endpoint to get a student's name for the UI."""
    conn = get_db_connection()
    if not conn: return jsonify({"success": False}), 500
    try:
        with conn.cursor() as cur:
            cur.execute("SELECT name FROM students WHERE enrollment_no = %s AND batch = 'BA'", (enrollment_no,))
            student_name = cur.fetchone()
            if student_name:
                return jsonify({"success": True, "name": student_name[0]})
            else:
                return jsonify({"success": False})
    finally:
        if conn: conn.close()

@app.route('/attendance_report')
@controller_required
def attendance_report():
    """Generates and displays the main attendance report grid."""
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        return redirect(url_for('controller_dashboard'))
    
    report_data = []
    class_id = get_class_id_by_name('BA - Anthropology')
    if not class_id:
        flash("Error: 'BA - Anthropology' class not found.", "danger")
        return render_template('attendance_report.html', report_data=[])
        
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            # Get all students and all session dates
            cur.execute("SELECT id, enrollment_no, name FROM students WHERE batch = 'BA' ORDER BY enrollment_no")
            all_students = cur.fetchall()
            cur.execute("SELECT DISTINCT DATE(start_time) as date FROM attendance_sessions WHERE class_id = %s ORDER BY date", (class_id,))
            session_dates = [row['date'] for row in cur.fetchall()]

            if session_dates:
                # Create a map of (student_id, date) -> 'Present' for quick lookups
                cur.execute("""
                    SELECT ar.student_id, DATE(s.start_time) as date
                    FROM attendance_records ar
                    JOIN attendance_sessions s ON ar.session_id = s.id
                    WHERE s.class_id = %s
                """, (class_id,))
                attended_map = {(rec['student_id'], rec['date']) for rec in cur.fetchall()}

                # Build the report grid
                for current_date in session_dates:
                    daily_entry = {'date': current_date.strftime('%Y-%m-%d'), 'students': []}
                    for student in all_students:
                        status = "Present" if (student['id'], current_date) in attended_map else "Absent"
                        daily_entry['students'].append({'status': status})
                    report_data.append(daily_entry)
                
                # We pass students separately to build the header row in the template
                return render_template('attendance_report.html', report_data=report_data, students=all_students, now=datetime.now(timezone.utc))

    except Exception as e:
        print(f"ERROR generating report: {e}")
        flash("An error occurred generating the report.", "danger")
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
        flash("Invalid date format.", "danger")
        return redirect(url_for('attendance_report'))

    # Security check: Ensure the date is within the editable window
    if attendance_date < (datetime.now(timezone.utc).date() - timedelta(days=7)):
        flash("This attendance record is too old to be edited.", "warning")
        return redirect(url_for('attendance_report'))
    
    return render_template('edit_attendance.html', attendance_date=date_str, class_name='BA - Anthropology')

@app.route('/api/get_daily_attendance_for_edit/<date_str>')
@controller_required
def api_get_daily_attendance_for_edit(date_str):
    """API endpoint to get student presence for a specific day."""
    conn = get_db_connection()
    if not conn: return jsonify({"success": False}), 500
    try:
        with conn.cursor(cursor_factory=psycopg2.extras.DictCursor) as cur:
            attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            class_id = get_class_id_by_name('BA - Anthropology')
            
            cur.execute("SELECT id, enrollment_no, name FROM students WHERE batch = 'BA' ORDER BY enrollment_no")
            all_students = cur.fetchall()

            # Find all students present on that day
            cur.execute("""
                SELECT DISTINCT ar.student_id
                FROM attendance_records ar
                JOIN attendance_sessions s ON ar.session_id = s.id
                WHERE s.class_id = %s AND DATE(s.start_time) = %s
            """, (class_id, attendance_date))
            present_student_ids = {row['student_id'] for row in cur.fetchall()}

            student_data = [
                {'id': s['id'], 'enrollment_no': s['enrollment_no'], 'name': s['name'], 'is_present': s['id'] in present_student_ids}
                for s in all_students
            ]
            return jsonify({"success": True, "students": student_data})
    finally:
        if conn: conn.close()

@app.route('/api/update_daily_attendance_record', methods=['POST'])
@controller_required
def api_update_daily_attendance_record():
    """API endpoint to mark or unmark a student for a specific day."""
    data = request.get_json()
    date_str, student_id, is_present = data.get('date_str'), data.get('student_id'), data.get('is_present')
    if not all([date_str, student_id, is_present is not None]):
        return jsonify({"success": False, "message": "Missing data."}), 400

    conn = get_db_connection()
    if not conn: return jsonify({"success": False}), 500
    try:
        with conn.cursor() as cur:
            attendance_date = datetime.strptime(date_str, '%Y-%m-%d').date()
            class_id = get_class_id_by_name('BA - Anthropology')
            
            # Find a session for that day to link the record to, or create one if none exists
            cur.execute(
                "SELECT id FROM attendance_sessions WHERE DATE(start_time) = %s AND class_id = %s ORDER BY start_time DESC LIMIT 1",
                (attendance_date, class_id)
            )
            session_id_result = cur.fetchone()

            if not session_id_result:
                # If no session exists, create a dummy one for the record
                start_time = datetime.combine(attendance_date, datetime.min.time()).replace(tzinfo=timezone.utc)
                cur.execute(
                    "INSERT INTO attendance_sessions (class_id, controller_id, session_token, start_time, end_time, is_active) VALUES (%s, %s, %s, %s, %s, FALSE) RETURNING id",
                    (class_id, session['user_id'], secrets.token_hex(16), start_time, start_time + timedelta(minutes=1))
                )
                session_id = cur.fetchone()[0]
            else:
                session_id = session_id_result[0]
            
            # Insert or delete the attendance record
            if is_present:
                cur.execute(
                    "INSERT INTO attendance_records (session_id, student_id, timestamp, ip_address) VALUES (%s, %s, NOW(), 'Manual_Edit') ON CONFLICT (session_id, student_id) DO NOTHING",
                    (session_id, student_id)
                )
            else:
                cur.execute(
                    "DELETE FROM attendance_records WHERE session_id = %s AND student_id = %s",
                    (session_id, student_id)
                )
            conn.commit()
            return jsonify({"success": True, "message": "Attendance updated."})
    except Exception as e:
        conn.rollback()
        print(f"ERROR updating daily record: {e}")
        return jsonify({"success": False, "message": "An error occurred."}), 500
    finally:
        if conn: conn.close()

if __name__ == '__main__':
    # Use 0.0.0.0 to make it accessible on the network
    app.run(host='0.0.0.0', port=5000, debug=True)
