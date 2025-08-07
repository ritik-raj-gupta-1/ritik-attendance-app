import os
import psycopg2
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
        
        # --- SIMPLE LOGIN VERIFICATION ---
        if username == CONTROLLER_USERNAME and password == CONTROLLER_PASSWORD:
            conn = get_db_connection()
            if conn:
                cur = conn.cursor()
                # Retrieve controller ID and role from DB (assuming 'controller' user exists)
                cur.execute("SELECT id, username, role FROM users WHERE username = %s AND role = 'controller'", (username,))
                user_data = cur.fetchone()
                cur.close()
                conn.close()

                if user_data:
                    session['user_id'] = user_data[0]
                    session['username'] = user_data[1]
                    session['role'] = user_data[2] # Should always be 'controller'
                    flash(f"Welcome, {user_data[1]} (Controller)!", "success")
                    return redirect(url_for('controller_dashboard'))
                else:
                    # This case should ideally not happen if database_setup.sql runs correctly
                    flash("Controller user not found in database. Please contact support.", "danger")
            else:
                flash("Database connection error. Please try again later.", "danger")
        else:
            flash("Invalid username or password. Please try again.", "danger")
    return render_template('login.html')

@app.route('/logout')
@controller_required
def logout():
    """Logs out the controller."""
    session.clear()
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/controller_dashboard')
@controller_required
def controller_dashboard():
    """Controller dashboard: manages sessions, views reports, etc."""
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        return redirect(url_for('login')) # Redirect to login if no DB connection

    cur = conn.cursor()
    active_session = None
    remaining_time = 0
    ba_anthropology_class_id = None
    all_sessions = [] # To display past sessions for editing

    try:
        # Get the BA - Anthropology class ID
        cur.execute("SELECT id FROM classes WHERE class_name = 'BA - Anthropology'")
        class_id_result = cur.fetchone()
        if class_id_result:
            ba_anthropology_class_id = class_id_result[0]

        # Fetch active session for BA - Anthropology class
        if ba_anthropology_class_id:
            cur.execute("""
                SELECT id, session_token, start_time, end_time, last_updated
                FROM attendance_sessions
                WHERE class_id = %s AND is_active = TRUE
                ORDER BY start_time DESC
                LIMIT 1
            """, (ba_anthropology_class_id,))
            active_session_raw = cur.fetchone()

            if active_session_raw:
                end_time = active_session_raw[3] # end_time is the 4th element (index 3)
                time_difference = end_time - datetime.now(timezone.utc)
                remaining_time = int(time_difference.total_seconds())
                if remaining_time < 0:
                    remaining_time = 0 # Ensure it doesn't go negative

                active_session = {
                    'id': active_session_raw[0],
                    'session_token': active_session_raw[1],
                    'start_time': active_session_raw[2].strftime('%Y-%m-%d %H:%M:%S %Z'),
                    'end_time': active_session_raw[3].strftime('%Y-%m-%d %H:%M:%S %Z'),
                    'last_updated': active_session_raw[4].strftime('%Y-%m-%d %H:%M:%S %Z') if active_session_raw[4] else 'N/A',
                    'class_name': 'BA - Anthropology', # Hardcode as only one class
                    'remaining_time': remaining_time
                }
        
        # Fetch all past and active sessions for the BA - Anthropology class for editing
        if ba_anthropology_class_id:
            cur.execute("""
                SELECT id, start_time, end_time, is_active
                FROM attendance_sessions
                WHERE class_id = %s
                ORDER BY start_time DESC
            """, (ba_anthropology_class_id,))
            all_sessions_raw = cur.fetchall()
            all_sessions = [{
                'id': s[0],
                'start_time': s[1].strftime('%Y-%m-%d %H:%M:%S %Z'),
                'end_time': s[2].strftime('%Y-%m-%d %H:%M:%S %Z'),
                'is_active': s[3]
            } for s in all_sessions_raw]

    except Exception as e:
        print(f"Error fetching data for controller dashboard: {e}")
        flash("An error occurred while fetching dashboard data.", "danger")
    finally:
        cur.close()
        conn.close()

    return render_template('admin_dashboard.html', # Reusing admin_dashboard template for controller
                           active_session=active_session,
                           remaining_time=remaining_time,
                           username=session.get('username'),
                           ba_anthropology_class_id=ba_anthropology_class_id,
                           all_sessions=all_sessions)


@app.route('/start_session', methods=['POST'])
@controller_required
def start_session():
    """Starts a new attendance session for BA - Anthropology."""
    controller_id = session['user_id']
    
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed.", "danger")
        return redirect(url_for('controller_dashboard'))
    cur = conn.cursor()

    try:
        # Get the BA - Anthropology class ID
        cur.execute("SELECT id FROM classes WHERE class_name = 'BA - Anthropology' AND controller_id = %s", (controller_id,))
        class_id_result = cur.fetchone()
        if not class_id_result:
            flash("BA - Anthropology class not found or not assigned to this controller.", "danger")
            return redirect(url_for('controller_dashboard'))
        ba_anthropology_class_id = class_id_result[0]

        # Check if there's an active session for this class already
        cur.execute("SELECT id FROM attendance_sessions WHERE class_id = %s AND is_active = TRUE", (ba_anthropology_class_id,))
        existing_session = cur.fetchone()
        if existing_session:
            flash("An active session for BA - Anthropology is already running. Please end it before starting a new one.", "warning")
            return redirect(url_for('controller_dashboard'))

        session_token = secrets.token_hex(16) # Generate a secure random token
        start_time = datetime.now(timezone.utc)
        end_time = start_time + timedelta(minutes=90) # Session lasts for 90 minutes (can be adjusted)

        cur.execute(
            "INSERT INTO attendance_sessions (class_id, controller_id, session_token, start_time, end_time, is_active) VALUES (%s, %s, %s, %s, %s, TRUE)",
            (ba_anthropology_class_id, controller_id, session_token, start_time, end_time)
        )
        conn.commit()
        flash("Attendance session for BA - Anthropology started successfully!", "success")
    except Exception as e:
        print(f"Error starting session: {e}")
        flash("An error occurred while starting the session.", "danger")
    finally:
        cur.close()
        conn.close()
    
    return redirect(url_for('controller_dashboard'))

@app.route('/end_session/<int:session_id>', methods=['POST'])
@controller_required
def end_session(session_id):
    """Ends an active attendance session."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection failed."})
    cur = conn.cursor()
    try:
        # Ensure only the current controller can end their session
        cur.execute(
            "UPDATE attendance_sessions SET is_active = FALSE, end_time = %s WHERE id = %s AND controller_id = %s",
            (datetime.now(timezone.utc), session_id, session['user_id'])
        )
        conn.commit()
        flash("Session ended.", "info")
        return jsonify({"success": True, "message": "Session ended successfully."})
    except Exception as e:
        print(f"Error ending session: {e}")
        flash("An error occurred while ending the session.", "danger")
        return jsonify({"success": False, "message": "An error occurred while ending the session."})
    finally:
        cur.close()
        conn.close()

@app.route('/mark_attendance', methods=['GET', 'POST'])
def mark_attendance():
    """Allows students to mark their attendance."""
    if request.method == 'POST':
        enrollment_no = request.form.get('enrollment_no')
        session_id = request.form.get('session_id') # This is the session ID
        latitude = request.form.get('latitude')
        longitude = request.form.get('longitude')
        ip_address = request.remote_addr # Get client IP address

        conn = get_db_connection()
        if not conn:
            flash("Database connection failed.", "danger")
            return redirect(url_for('mark_attendance')) # Redirect to student page
        cur = conn.cursor()
        
        try:
            # 1. Verify session exists, is active, and is for BA-Anthropology
            cur.execute("""
                SELECT asess.class_id, c.geofence_lat, c.geofence_lon, c.geofence_radius
                FROM attendance_sessions AS asess
                JOIN classes AS c ON asess.class_id = c.id
                WHERE asess.id = %s AND asess.is_active = TRUE AND asess.end_time > %s
                AND c.class_name = 'BA - Anthropology'
            """, (session_id, datetime.now(timezone.utc)))
            session_info = cur.fetchone()

            if not session_info:
                flash("Invalid, inactive, or expired session for BA - Anthropology.", "danger")
                return redirect(url_for('mark_attendance'))

            class_id, geofence_lat, geofence_lon, geofence_radius = session_info

            # 2. Get student ID from enrollment number and verify batch is BA
            cur.execute("SELECT id, batch FROM students WHERE enrollment_no = %s AND batch = 'BA'", (enrollment_no,))
            student_result = cur.fetchone()
            if not student_result:
                flash("Invalid enrollment number or not a BA student.", "danger")
                return redirect(url_for('mark_attendance'))
            student_id = student_result[0]

            # 3. Check if student already marked attendance for this session
            cur.execute("SELECT COUNT(*) FROM attendance_records WHERE session_id = %s AND student_id = %s", (session_id, student_id))
            if cur.fetchone()[0] > 0:
                flash("Attendance already marked for this session.", "warning")
                return redirect(url_for('mark_attendance'))

            # 4. Geofence check
            if latitude and longitude and geofence_lat and geofence_lon and geofence_radius:
                user_lat = float(latitude)
                user_lon = float(longitude)
                
                distance = haversine_distance(user_lat, user_lon, geofence_lat, geofence_lon)
                if distance > geofence_radius:
                    flash(f"You are {distance:.2f} meters away. Attendance can only be marked within {geofence_radius} meters of the Anthropology Department.", "danger")
                    return redirect(url_for('mark_attendance'))
            else:
                flash("Location data missing for geofence check. Please enable location services.", "danger")
                return redirect(url_for('mark_attendance'))

            # 5. IP Address check (preventing multiple marks from same IP on same day)
            today_date = datetime.now(timezone.utc).date()
            cur.execute("SELECT COUNT(*) FROM daily_attendance_ips WHERE ip_address = %s AND date = %s", (ip_address, today_date))
            if cur.fetchone()[0] > 0:
                flash("Attendance already marked from this IP address today. Only one submission per IP per day.", "warning")
                return redirect(url_for('mark_attendance'))

            # 6. Mark attendance
            timestamp = datetime.now(timezone.utc)
            cur.execute(
                "INSERT INTO attendance_records (session_id, student_id, timestamp, latitude, longitude, ip_address) VALUES (%s, %s, %s, %s, %s, %s)",
                (session_id, student_id, timestamp, latitude, longitude, ip_address)
            )
            
            # 7. Record IP for today (only if not already recorded)
            cur.execute(
                "INSERT INTO daily_attendance_ips (ip_address, date) VALUES (%s, %s) ON CONFLICT (ip_address, date) DO NOTHING",
                (ip_address, today_date)
            )
            
            conn.commit()
            flash("Attendance marked successfully!", "success")

        except Exception as e:
            print(f"Error marking attendance: {e}")
            flash("An error occurred while marking attendance. Please try again.", "danger")
        finally:
            cur.close()
            conn.close()

        return redirect(url_for('mark_attendance'))
    
    # For GET request, display active BA - Anthropology session for students
    conn = get_db_connection()
    active_session_for_student = None
    if conn:
        cur = conn.cursor()
        try:
            # Get the BA - Anthropology class ID
            cur.execute("SELECT id FROM classes WHERE class_name = 'BA - Anthropology'")
            ba_anthropology_class_id = cur.fetchone()[0]

            cur.execute("""
                SELECT asess.id, c.class_name, asess.end_time
                FROM attendance_sessions asess
                JOIN classes c ON asess.class_id = c.id
                WHERE asess.is_active = TRUE AND asess.end_time > %s
                AND c.id = %s -- Filter for BA - Anthropology class
                ORDER BY asess.end_time ASC
                LIMIT 1
            """, (datetime.now(timezone.utc), ba_anthropology_class_id))
            session_raw = cur.fetchone()

            if session_raw:
                end_time = session_raw[2]
                time_difference = end_time - datetime.now(timezone.utc)
                remaining_time_seconds = int(time_difference.total_seconds())
                if remaining_time_seconds > 0:
                    active_session_for_student = {
                        'id': session_raw[0],
                        'class_name': session_raw[1],
                        'remaining_time': remaining_time_seconds
                    }
        except Exception as e:
            print(f"Error fetching active session for student: {e}")
            flash("Could not fetch active attendance session.", "danger")
        finally:
            cur.close()
            conn.close()

    return render_template('student_attendance.html', active_session=active_session_for_student)


@app.route('/api/get_student_name/<enrollment_no>')
def api_get_student_name(enrollment_no):
    """API endpoint to get student name by enrollment number (only for BA students)."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection failed."})
    cur = conn.cursor()
    try:
        cur.execute("SELECT name FROM students WHERE enrollment_no = %s AND batch = 'BA'", (enrollment_no,))
        student_name = cur.fetchone()
        if student_name:
            return jsonify({"success": True, "name": student_name[0]})
        else:
            return jsonify({"success": False, "message": "Student not found or not a BA student."})
    except Exception as e:
        print(f"Error fetching student name: {e}")
        return jsonify({"success": False, "message": "An error occurred."})
    finally:
        cur.close()
        conn.close()

@app.route('/api/get_active_ba_session')
def api_get_active_ba_session():
    """API endpoint to get the active BA - Anthropology session ID for students."""
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection failed."})
    cur = conn.cursor()
    try:
        # Get the BA - Anthropology class ID
        cur.execute("SELECT id FROM classes WHERE class_name = 'BA - Anthropology'")
        class_id_result = cur.fetchone()
        if not class_id_result:
            return jsonify({"success": False, "message": "BA - Anthropology class not configured."})
        ba_anthropology_class_id = class_id_result[0]

        cur.execute("""
            SELECT id FROM attendance_sessions
            WHERE class_id = %s AND is_active = TRUE AND end_time > %s
            ORDER BY end_time ASC LIMIT 1
        """, (ba_anthropology_class_id, datetime.now(timezone.utc)))
        session_id = cur.fetchone()
        if session_id:
            return jsonify({"success": True, "session_id": session_id[0]})
        else:
            return jsonify({"success": False, "message": "No active BA - Anthropology session."})
    except Exception as e:
        print(f"Error fetching active BA session: {e}")
        return jsonify({"success": False, "message": "An error occurred."})
    finally:
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
    cur = conn.cursor()

    attendance_data = []
    try:
        # Get the BA - Anthropology class ID
        cur.execute("SELECT id FROM classes WHERE class_name = 'BA - Anthropology'")
        ba_anthropology_class_id = cur.fetchone()[0]

        # Fetch attendance records only for BA - Anthropology students
        cur.execute("""
            SELECT s.enrollment_no, s.name, s.batch, c.class_name, asess.start_time, ar.timestamp, ar.latitude, ar.longitude, ar.ip_address
            FROM attendance_records ar
            JOIN students s ON ar.student_id = s.id
            JOIN attendance_sessions asess ON ar.session_id = asess.id
            JOIN classes c ON asess.class_id = c.id
            WHERE s.batch = 'BA' AND c.id = %s
            ORDER BY ar.timestamp DESC
        """, (ba_anthropology_class_id,))
        raw_data = cur.fetchall()
        
        for row in raw_data:
            attendance_data.append({
                'enrollment_no': row[0],
                'student_name': row[1],
                'student_batch': row[2],
                'class_name': row[3],
                'session_start_time': row[4].strftime('%Y-%m-%d %H:%M:%S %Z'),
                'marked_time': row[5].strftime('%Y-%m-%d %H:%M:%S %Z'),
                'latitude': row[6],
                'longitude': row[7],
                'ip_address': row[8]
            })
    except Exception as e:
        print(f"Error fetching attendance report: {e}")
        flash("An error occurred while fetching the attendance report.", "danger")
    finally:
        cur.close()
        conn.close()
    
    return render_template('attendance_report.html', attendance_data=attendance_data)

@app.route('/export_attendance_csv')
@controller_required
def export_attendance_csv():
    """Exports attendance data to a CSV file."""
    conn = get_db_connection()
    if not conn:
        flash("Database connection failed for export.", "danger")
        return redirect(url_for('attendance_report'))
    cur = conn.cursor()
    try:
        # Get the BA - Anthropology class ID
        cur.execute("SELECT id FROM classes WHERE class_name = 'BA - Anthropology'")
        ba_anthropology_class_id = cur.fetchone()[0]

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

        # Create a CSV in memory
        output = io.StringIO()
        # CSV Header
        output.write("Enrollment No,Student Name,Batch,Class Name,Session Start Time,Attendance Marked Time,Latitude,Longitude,IP Address\n")
        # CSV Data
        for row in rows:
            formatted_row = [
                str(row[0]), # enrollment_no
                str(row[1]), # student_name
                str(row[2]), # batch
                str(row[3]), # class_name
                row[4].strftime('%Y-%m-%d %H:%M:%S %Z'), # session_start_time
                row[5].strftime('%Y-%m-%d %H:%M:%S %Z'), # marked_time
                str(row[6]) if row[6] is not None else '', # latitude
                str(row[7]) if row[7] is not None else '', # longitude
                str(row[8]) if row[8] is not None else ''  # ip_address
            ]
            output.write(",".join(formatted_row) + "\n")
        
        output.seek(0) # Rewind to the beginning of the stream

        return send_file(
            io.BytesIO(output.getvalue().encode('utf-8')),
            mimetype='text/csv',
            as_attachment=True,
            download_name='attendance_report_BA_Anthropology.csv'
        )

    except Exception as e:
        print(f"Error exporting CSV: {e}")
        flash("An error occurred during CSV export.", "danger")
        return redirect(url_for('attendance_report'))
    finally:
        cur.close()
        conn.close()

@app.route('/edit_attendance/<int:session_id>')
@controller_required
def edit_attendance(session_id):
    """Allows controller to manually edit attendance for a specific session."""
    conn = get_db_connection()
    session_info = None
    if conn:
        cur = conn.cursor()
        try:
            cur.execute("""
                SELECT asess.id, c.class_name, asess.start_time
                FROM attendance_sessions asess
                JOIN classes c ON asess.class_id = c.id
                WHERE asess.id = %s AND c.class_name = 'BA - Anthropology'
            """, (session_id,))
            session_info_raw = cur.fetchone()
            if session_info_raw:
                session_info = {
                    'id': session_info_raw[0],
                    'class_name': session_info_raw[1],
                    'start_time': session_info_raw[2].strftime('%Y-%m-%d %H:%M:%S %Z')
                }
        except Exception as e:
            print(f"Error fetching session info for edit: {e}")
            flash("Could not fetch session details for editing.", "danger")
        finally:
            cur.close()
            conn.close()
    
    if not session_info:
        flash("Session not found or not a BA - Anthropology session.", "danger")
        return redirect(url_for('controller_dashboard'))
        
    return render_template('edit_attendance.html', session=session_info)

@app.route('/api/get_session_students_for_edit/<int:session_id>')
@controller_required
def api_get_session_students_for_edit(session_id):
    """API endpoint to get all BA students for a session, including their attendance status for editing."""
    conn = get_db_connection()
    if not conn:
        return jsonify([]) # Return empty list on connection failure
    cur = conn.cursor()
    try:
        # Get all BA students
        cur.execute("SELECT id, enrollment_no, name, batch FROM students WHERE batch = 'BA' ORDER BY enrollment_no")
        all_ba_students_raw = cur.fetchall()

        # Get attendance records for the specific session
        cur.execute("SELECT student_id FROM attendance_records WHERE session_id = %s", (session_id,))
        attended_student_ids = {row[0] for row in cur.fetchall()}

        students_data = []
        for student in all_ba_students_raw:
            students_data.append({
                'id': student[0],
                'enrollment_no': student[1],
                'name': student[2],
                'batch': student[3],
                'is_present': student[0] in attended_student_ids
            })
        return jsonify(students_data)
    except Exception as e:
        print(f"Error fetching session students for edit: {e}")
        return jsonify([])
    finally:
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
    
    conn = get_db_connection()
    if not conn:
        return jsonify({"success": False, "message": "Database connection failed."})
    cur = conn.cursor()
    try:
        if is_present:
            # Insert if not exists, or do nothing if already present
            # We also record the timestamp, latitude, longitude, and IP if available,
            # but for manual edits, we can use current time and mark location/IP as N/A or default.
            # For simplicity, we'll use current timestamp and null for location/IP for manual edits.
            cur.execute(
                "INSERT INTO attendance_records (session_id, student_id, timestamp, latitude, longitude, ip_address) VALUES (%s, %s, %s, NULL, NULL, 'Manual_Edit')",
                (session_id, student_id, datetime.now(timezone.utc))
            )
        else:
            # Delete the record if marking absent
            cur.execute(
                "DELETE FROM attendance_records WHERE session_id = %s AND student_id = %s",
                (session_id, student_id)
            )
        conn.commit()
        return jsonify({"success": True, "message": "Attendance updated."})
    except Exception as e:
        print(f"Error updating attendance record: {e}")
        return jsonify({"success": False, "message": "An error occurred while updating attendance."})
    finally:
        cur.close()
        conn.close()

# Utility route to generate password hashes (for local use, remove in production)
# This route is no longer needed with hardcoded credentials, but keeping it as a utility example.
@app.route('/generate_hash/<password_text>')
def generate_hash_route(password_text):
    # This function now requires werkzeug.security, which is removed from imports.
    # If you need this utility, you'd need to re-add the import and bcrypt to requirements.txt
    # For this simplified app, it's best to remove this route entirely for clarity.
    return "Password hashing utility is not active in this simplified version."

if __name__ == '__main__':
    # This block is for local development only.
    # For Render, the Gunicorn command in Procfile runs the app.
    app.run(debug=True)
