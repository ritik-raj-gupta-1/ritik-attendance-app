import os
import psycopg2
import psycopg2.extras # Import for DictCursor
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
            flash("You must be logged in as a controller to access this page.", "warning")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated_function

# --- New Helper Function for Class ID Lookup ---
def get_class_id_by_name(class_name):
    """
    Retrieves the ID of a class given its name.
    Adds print statements for debugging.
    """
    conn = get_db_connection()
    if conn is None:
        print("DEBUG: get_class_id_by_name: Could not connect to database.")
        return None
    try:
        cur = conn.cursor()
        cur.execute("SELECT id FROM classes WHERE class_name = %s", (class_name,))
        class_id_result = cur.fetchone()
        if class_id_result:
            class_id = class_id_result[0]
            print(f"DEBUG: get_class_id_by_name: Found class '{class_name}' with ID: {class_id}")
            return class_id
        else:
            print(f"DEBUG: get_class_id_by_name: Class '{class_name}' not found in database.")
            return None
    except Exception as e:
        print(f"ERROR: get_class_id_by_name: Exception fetching class ID for {class_name}: {e}")
        return None
    finally:
        if conn:
            cur.close()
            conn.close()

def get_active_session_for_class(class_name='BA - Anthropology'):
    """
    Retrieves the active attendance session for a specific class.
    Calculates remaining time and handles expired sessions.
    Adds print statements for debugging.
    """
    conn = get_db_connection()
    if conn is None:
        print("DEBUG: get_active_session_for_class: Could not connect to database.")
        return None
    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
        
        # First, get the class_id for the given class_name
        class_id = get_class_id_by_name(class_name)
        if class_id is None:
            print(f"DEBUG: get_active_session_for_class: Class ID not found for '{class_name}'. Cannot check for active session.")
            return None

        # Now, query for the active session using the class_id
        cur.execute("""
            SELECT
                s.id,
                s.session_token,
                s.start_time,
                s.end_time,
                s.is_active,
                c.class_name
            FROM attendance_sessions s
            JOIN classes c ON s.class_id = c.id
            WHERE s.class_id = %s AND s.is_active = TRUE
            ORDER BY s.start_time DESC
            LIMIT 1
        """, (class_id,))
        session_data = cur.fetchone()

        if session_data:
            session_dict = dict(session_data)
            
            # Calculate remaining time (always convert to UTC for consistent comparison)
            end_time_utc = session_dict['end_time'].astimezone(timezone.utc)
            current_time_utc = datetime.now(timezone.utc)
            time_remaining = (end_time_utc - current_time_utc).total_seconds()

            if time_remaining <= 0:
                # Session has expired, mark it inactive and return None
                cur.execute("UPDATE attendance_sessions SET is_active = FALSE WHERE id = %s", (session_dict['id'],))
                conn.commit()
                print(f"DEBUG: Session {session_dict['id']} for '{class_name}' expired and marked inactive. Remaining: {time_remaining}s")
                return None
            
            session_dict['remaining_time'] = math.ceil(time_remaining)
            print(f"DEBUG: Found active session {session_dict['id']} for '{class_name}'. Remaining time: {session_dict['remaining_time']}s")
            return session_dict
        else:
            print(f"DEBUG: No active session found for class '{class_name}' (Class ID: {class_id}).")
            return None
    except Exception as e:
        print(f"ERROR: get_active_session_for_class: Exception fetching active session for {class_name}: {e}")
        return None
    finally:
        if conn:
            cur.close()
            conn.close()

# --- ROUTES ---

@app.route('/')
def index():
    return redirect(url_for('student_attendance'))

@app.route('/login', methods=['GET', 'POST'])
def login():
    if request.method == 'POST':
        username = request.form['username']
        password = request.form['password']

        if username == CONTROLLER_USERNAME and password == CONTROLLER_PASSWORD:
            session['user_id'] = 1 # Hardcoded ID for the single controller user
            session['role'] = 'controller'
            flash("Logged in successfully!", "success")
            return redirect(url_for('controller_dashboard'))
        else:
            flash("Invalid credentials.", "error")
    return render_template('login.html')

@app.route('/logout')
def logout():
    session.pop('user_id', None)
    session.pop('role', None)
    flash("You have been logged out.", "info")
    return redirect(url_for('login'))

@app.route('/student_attendance')
def student_attendance():
    active_session = get_active_session_for_class('BA - Anthropology')
    if active_session:
        print(f"DEBUG: student_attendance route: Active session found: {active_session['id']}")
    else:
        print("DEBUG: student_attendance route: No active session found.")
    return render_template('student_attendance.html', active_session=active_session)

@app.route('/controller_dashboard')
@controller_required
def controller_dashboard():
    active_session = get_active_session_for_class('BA - Anthropology') # Pass the specific class name
    past_sessions = []
    conn = get_db_connection()
    if conn:
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            # Get the class_id for BA - Anthropology
            class_id = get_class_id_by_name('BA - Anthropology')
            if class_id is None:
                flash("Error: 'BA - Anthropology' class not found in database.", "error")
                print("ERROR: controller_dashboard: 'BA - Anthropology' class_id not found. Cannot fetch past sessions.")
                # This could cause an empty dashboard, so provide an empty list
                past_sessions = [] # Ensure it's an empty list to avoid iteration errors
            else:
                # Fetch only past (inactive) sessions for this specific class
                cur.execute("""
                    SELECT
                        s.id,
                        s.session_token,
                        s.start_time,
                        s.end_time,
                        s.is_active,
                        c.class_name
                    FROM attendance_sessions s
                    JOIN classes c ON s.class_id = c.id
                    WHERE s.class_id = %s AND s.is_active = FALSE
                    ORDER BY s.start_time DESC
                """, (class_id,))
                past_sessions = cur.fetchall()
                print(f"DEBUG: controller_dashboard: Retrieved {len(past_sessions)} past sessions for BA - Anthropology (Class ID: {class_id}).")
        except Exception as e:
            print(f"ERROR: controller_dashboard: Exception fetching past sessions: {e}")
            flash("An error occurred while fetching past sessions.", "error")
        finally:
            conn.close()
    else:
        flash("Database connection error.", "error")

    # Convert psycopg2 Row objects to dictionaries for easier access in Jinja
    past_sessions_list = []
    for session_row in past_sessions:
        session_dict = dict(session_row)
        session_dict['start_time'] = session_dict['start_time'].strftime('%Y-%m-%d %H:%M:%S')
        if session_dict['end_time']:
            session_dict['end_time'] = session_dict['end_time'].strftime('%Y-%m-%d %H:%M:%S')
        past_sessions_list.append(session_dict)

    print(f"DEBUG: controller_dashboard: Rendering with active_session: {active_session is not None}")
    return render_template('admin_dashboard.html', active_session=active_session, past_sessions=past_sessions_list)


@app.route('/start_attendance_session', methods=['POST'])
@controller_required
def start_attendance_session():
    print("DEBUG: start_attendance_session route called.")
    # Ensure only one active session for 'BA - Anthropology' at a time
    existing_session = get_active_session_for_class('BA - Anthropology')
    if existing_session:
        flash("An active attendance session for BA - Anthropology already exists.", "info")
        print(f"DEBUG: start_attendance_session: Tried to start new session, but active session {existing_session['id']} already exists.")
        return redirect(url_for('controller_dashboard'))

    conn = get_db_connection()
    if conn is None:
        flash("Database connection error.", "error")
        print("ERROR: start_attendance_session: Could not connect to database.")
        return redirect(url_for('controller_dashboard'))

    try:
        cur = conn.cursor()
        class_name = 'BA - Anthropology'
        # Get the class_id for BA - Anthropology
        class_id = get_class_id_by_name(class_name)

        if class_id is None:
            flash(f"Error: Class '{class_name}' not found. Cannot start session.", "error")
            print(f"ERROR: start_attendance_session: Class ID for '{class_name}' not found. Cannot start session.")
            return redirect(url_for('controller_dashboard'))

        controller_id = session['user_id'] # Assuming user_id in session is the controller's ID
        session_token = secrets.token_hex(16) # Generate a 32-character hex token
        start_time = datetime.now(timezone.utc)
        # End time 10 minutes from now (adjust as needed)
        end_time = start_time + timedelta(minutes=10)

        cur.execute("""
            INSERT INTO attendance_sessions
            (class_id, controller_id, session_token, start_time, end_time, is_active)
            VALUES (%s, %s, %s, %s, %s, TRUE) RETURNING id
        """, (class_id, controller_id, session_token, start_time, end_time))
        new_session_id = cur.fetchone()[0]
        conn.commit()

        flash(f"Attendance session for {class_name} started successfully! Session ID: {new_session_id}", "success")
        print(f"DEBUG: New session {new_session_id} started for '{class_name}'. Token: {session_token}")
        return redirect(url_for('controller_dashboard'))
    except Exception as e:
        print(f"ERROR: start_attendance_session: Exception starting attendance session: {e}")
        flash("An error occurred while starting the attendance session.", "error")
        conn.rollback()
        return redirect(url_for('controller_dashboard'))
    finally:
        if conn:
            cur.close()
            conn.close()

@app.route('/api/mark_attendance', methods=['POST'])
def mark_attendance():
    data = request.get_json()
    enrollment_no = data.get('enrollment_no')
    session_id = data.get('session_id')
    latitude = data.get('latitude')
    longitude = data.get('longitude')
    ip_address = request.remote_addr # Get client IP

    if not all([enrollment_no, session_id]):
        print("ERROR: mark_attendance: Missing enrollment_no or session_id in request.")
        return jsonify({"success": False, "message": "Missing required data."}), 400

    conn = get_db_connection()
    if conn is None:
        print("ERROR: mark_attendance: Database connection error.")
        return jsonify({"success": False, "message": "Database connection error."}), 500

    try:
        cur = conn.cursor()

        # 1. Check if the session is active and valid
        cur.execute("""
            SELECT id, class_id, end_time, geofence_lat, geofence_lon, geofence_radius
            FROM attendance_sessions s
            JOIN classes c ON s.class_id = c.id
            WHERE s.id = %s AND s.is_active = TRUE
        """, (session_id,))
        session_data = cur.fetchone()

        if not session_data:
            print(f"DEBUG: mark_attendance: Session {session_id} not found or not active.")
            return jsonify({"success": False, "message": "Session is not active or invalid."}), 400

        session_end_time = session_data[2]
        geofence_lat = session_data[3]
        geofence_lon = session_data[4]
        geofence_radius = session_data[5]

        # Check if session has expired
        if datetime.now(timezone.utc) > session_end_time.astimezone(timezone.utc):
            cur.execute("UPDATE attendance_sessions SET is_active = FALSE WHERE id = %s", (session_id,))
            conn.commit()
            print(f"DEBUG: mark_attendance: Session {session_id} expired during attendance attempt.")
            return jsonify({"success": False, "message": "Session has expired."}), 400

        # 2. Check student enrollment number
        cur.execute("SELECT id FROM students WHERE enrollment_no = %s", (enrollment_no,))
        student_data = cur.fetchone()
        if not student_data:
            print(f"DEBUG: mark_attendance: Student with enrollment no. {enrollment_no} not found.")
            return jsonify({"success": False, "message": "Enrollment number not found."}), 404

        student_id = student_data[0]

        # 3. Check if attendance already marked for this student in this session
        cur.execute("SELECT id FROM attendance_records WHERE session_id = %s AND student_id = %s", (session_id, student_id))
        if cur.fetchone():
            print(f"DEBUG: mark_attendance: Attendance already marked for student {enrollment_no} in session {session_id}.")
            return jsonify({"success": False, "message": "Attendance already marked for this session."}), 409

        # 4. Check for duplicate IP address for the day (basic security)
        today = datetime.now(timezone.utc).date()
        cur.execute("SELECT id FROM daily_attendance_ips WHERE ip_address = %s AND date = %s", (ip_address, today))
        if cur.fetchone():
            print(f"SECURITY: mark_attendance: IP address {ip_address} has already marked attendance today.")
            # return jsonify({"success": False, "message": "You can only mark attendance once per day from this device."}), 403
            # Temporarily disable for testing if needed, or keep for security
            pass

        # 5. Geofencing check (if lat/lon are provided)
        if latitude is not None and longitude is not None and geofence_lat is not None and geofence_lon is not None and geofence_radius is not None:
            # Haversine formula to calculate distance between two lat/lon points
            R = 6371000  # Radius of Earth in meters
            lat1_rad = math.radians(geofence_lat)
            lon1_rad = math.radians(geofence_lon)
            lat2_rad = math.radians(latitude)
            lon2_rad = math.radians(longitude)

            dlon = lon2_rad - lon1_rad
            dlat = lat2_rad - lat1_rad

            a = math.sin(dlat / 2)**2 + math.cos(lat1_rad) * math.cos(lat2_rad) * math.sin(dlon / 2)**2
            c = 2 * math.atan2(math.sqrt(a), math.sqrt(1 - a))
            distance = R * c

            print(f"DEBUG: mark_attendance: Calculated distance: {distance:.2f}m. Geofence radius: {geofence_radius}m.")

            if distance > geofence_radius:
                print(f"SECURITY: mark_attendance: Student {enrollment_no} outside geofence. Distance: {distance:.2f}m, Radius: {geofence_radius}m.")
                return jsonify({"success": False, "message": "You are outside the attendance area. Distance: {:.0f}m".format(distance)}), 403

        # 6. Record attendance
        cur.execute(
            "INSERT INTO attendance_records (session_id, student_id, timestamp, latitude, longitude, ip_address) VALUES (%s, %s, %s, %s, %s, %s)",
            (session_id, student_id, datetime.now(timezone.utc), latitude, longitude, ip_address)
        )
        # Record IP for daily check (only if attendance was successfully marked)
        cur.execute(
            "INSERT INTO daily_attendance_ips (ip_address, date) VALUES (%s, %s) ON CONFLICT (ip_address, date) DO NOTHING",
            (ip_address, today)
        )
        conn.commit()
        print(f"SUCCESS: mark_attendance: Attendance marked for student {enrollment_no} in session {session_id}.")
        return jsonify({"success": True, "message": "Attendance marked successfully!"})

    except Exception as e:
        print(f"ERROR: mark_attendance: Exception marking attendance: {e}")
        conn.rollback()
        return jsonify({"success": False, "message": "An error occurred while marking attendance."}), 500
    finally:
        if conn:
            cur.close()
            conn.close()

@app.route('/api/get_student_name/<enrollment_no>')
def get_student_name(enrollment_no):
    conn = get_db_connection()
    if conn is None:
        print("ERROR: get_student_name: Database connection error.")
        return jsonify({"name": None, "error": "Database connection error."}), 500
    try:
        cur = conn.cursor()
        cur.execute("SELECT name FROM students WHERE enrollment_no = %s", (enrollment_no,))
        result = cur.fetchone()
        if result:
            print(f"DEBUG: get_student_name: Found student {enrollment_no}: {result[0]}.")
            return jsonify({"name": result[0]})
        else:
            print(f"DEBUG: get_student_name: Student {enrollment_no} not found.")
            return jsonify({"name": None})
    except Exception as e:
        print(f"ERROR: get_student_name: Exception fetching student name: {e}")
        return jsonify({"name": None, "error": "An error occurred."}), 500
    finally:
        if conn:
            cur.close()
            conn.close()

@app.route('/attendance_report')
@controller_required
def attendance_report():
    conn = get_db_connection()
    daily_attendance_summary = []
    student_list = []
    
    if conn:
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

            # Get the class_id for BA - Anthropology
            class_id = get_class_id_by_name('BA - Anthropology')
            if class_id is None:
                flash("Error: 'BA - Anthropology' class not found in database. Cannot generate report.", "error")
                print("ERROR: attendance_report: 'BA - Anthropology' class_id not found. Cannot generate report.")
                return render_template('attendance_report.html', daily_attendance_summary=[], student_list=[])

            # Get all students for the BA batch, ordered by enrollment number
            cur.execute("SELECT enrollment_no, name, id FROM students WHERE batch = 'BA' ORDER BY enrollment_no")
            student_records = cur.fetchall()
            student_list = [dict(s) for s in student_records]
            student_ids_map = {s['id']: s['enrollment_no'] for s in student_records}
            
            print(f"DEBUG: attendance_report: Retrieved {len(student_list)} BA students.")

            # Fetch attendance data, grouped by day and including class_id filter
            cur.execute("""
                SELECT
                    DATE(ar.timestamp AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') AS attendance_date,
                    ar.student_id
                FROM attendance_records ar
                JOIN attendance_sessions ases ON ar.session_id = ases.id
                WHERE ases.class_id = %s
                ORDER BY attendance_date, ar.student_id
            """, (class_id,))
            all_attendance_records = cur.fetchall()
            print(f"DEBUG: attendance_report: Retrieved {len(all_attendance_records)} attendance records for BA - Anthropology.")

            # Process the records to create a daily summary
            daily_summary_map = {}
            for record in all_attendance_records:
                att_date = record['attendance_date'].isoformat() # Use ISO format for consistent date string
                student_id = record['student_id']

                if att_date not in daily_summary_map:
                    daily_summary_map[att_date] = {
                        'date': att_date,
                        'present_students': set() # Use a set for efficient lookup
                    }
                daily_summary_map[att_date]['present_students'].add(student_id)

            # Convert to desired structure for template
            for date_str, data in sorted(daily_summary_map.items()):
                students_status = []
                for student in student_list:
                    status = "Present" if student['id'] in data['present_students'] else "Absent"
                    students_status.append({
                        'enrollment_no': student['enrollment_no'],
                        'name': student['name'],
                        'status': status
                    })
                daily_attendance_summary.append({
                    'date': date_str,
                    'students': students_status
                })
            
            print(f"DEBUG: attendance_report: Generated summary for {len(daily_attendance_summary)} days.")

        except Exception as e:
            print(f"ERROR: attendance_report: Exception generating report: {e}")
            flash("An error occurred while generating the attendance report.", "error")
        finally:
            conn.close()
    else:
        flash("Database connection error.", "error")

    return render_template('attendance_report.html', daily_attendance_summary=daily_attendance_summary, student_list=student_list)


@app.route('/api/delete_daily_attendance', methods=['POST'])
@controller_required
def delete_daily_attendance():
    data = request.get_json()
    date_to_delete_str = data.get('date')

    if not date_to_delete_str:
        print("ERROR: delete_daily_attendance: No date provided for deletion.")
        return jsonify({"success": False, "message": "No date provided."}), 400

    conn = get_db_connection()
    if conn is None:
        print("ERROR: delete_daily_attendance: Database connection error.")
        return jsonify({"success": False, "message": "Database connection error."}), 500

    try:
        # Parse the date string into a date object
        date_to_delete = datetime.strptime(date_to_delete_str, '%Y-%m-%d').date()
        print(f"DEBUG: delete_daily_attendance: Attempting to delete attendance for date: {date_to_delete}.")

        cur = conn.cursor()

        # Get the class_id for BA - Anthropology
        class_id = get_class_id_by_name('BA - Anthropology')
        if class_id is None:
            print("ERROR: delete_daily_attendance: 'BA - Anthropology' class not found in database. Cannot delete.")
            return jsonify({"success": False, "message": "Class 'BA - Anthropology' not found. Cannot delete attendance."}), 500

        # Find all session IDs for the given date and class
        cur.execute("""
            SELECT s.id FROM attendance_sessions s
            WHERE DATE(s.start_time AT TIME ZONE 'UTC' AT TIME ZONE 'Asia/Kolkata') = %s
            AND s.class_id = %s
        """, (date_to_delete, class_id))
        session_ids_to_delete = [row[0] for row in cur.fetchall()]

        if not session_ids_to_delete:
            print(f"DEBUG: delete_daily_attendance: No sessions found for date {date_to_delete} and class {class_id}.")
            return jsonify({"success": True, "message": f"No attendance records found for {date_to_delete}."})

        # Delete attendance records associated with these sessions
        cur.execute("DELETE FROM attendance_records WHERE session_id = ANY(%s)", (session_ids_to_delete,))
        deleted_records_count = cur.rowcount
        print(f"DEBUG: Deleted {deleted_records_count} attendance records for sessions: {session_ids_to_delete}.")

        # Delete the sessions themselves
        cur.execute("DELETE FROM attendance_sessions WHERE id = ANY(%s)", (session_ids_to_delete,))
        deleted_sessions_count = cur.rowcount
        print(f"DEBUG: Deleted {deleted_sessions_count} sessions for date {date_to_delete}.")

        conn.commit()
        flash(f"All attendance records for {date_to_delete} have been deleted.", "success")
        return jsonify({"success": True, "message": f"All attendance records for {date_to_delete} have been deleted ({deleted_records_count} records, {deleted_sessions_count} sessions)."}), 200

    except Exception as e:
        print(f"ERROR: delete_daily_attendance: Exception during deletion for date {date_to_delete_str}: {e}")
        conn.rollback()
        return jsonify({"success": False, "message": "An error occurred while deleting daily attendance."}), 500
    finally:
        if conn:
            cur.close()
            conn.close()

@app.route('/edit_attendance/<int:session_id>')
@controller_required
def edit_attendance(session_id):
    conn = get_db_connection()
    session_details = None
    if conn:
        try:
            cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)
            cur.execute("""
                SELECT
                    s.id,
                    s.session_token,
                    s.start_time,
                    s.end_time,
                    s.is_active,
                    c.class_name
                FROM attendance_sessions s
                JOIN classes c ON s.class_id = c.id
                WHERE s.id = %s
            """, (session_id,))
            session_details = cur.fetchone()
            if session_details:
                session_details = dict(session_details)
                session_details['start_time'] = session_details['start_time'].strftime('%Y-%m-%d %H:%M:%S')
                if session_details['end_time']:
                    session_details['end_time'] = session_details['end_time'].strftime('%Y-%m-%d %H:%M:%S')
                print(f"DEBUG: edit_attendance: Loaded session details for ID {session_id}.")
            else:
                flash("Session not found.", "error")
                print(f"DEBUG: edit_attendance: Session ID {session_id} not found.")
                return redirect(url_for('controller_dashboard'))
        except Exception as e:
            print(f"ERROR: edit_attendance: Exception loading session details for {session_id}: {e}")
            flash("An error occurred while loading session details.", "error")
            return redirect(url_for('controller_dashboard'))
        finally:
            conn.close()
    else:
        flash("Database connection error.", "error")
        return redirect(url_for('controller_dashboard'))

    return render_template('edit_attendance.html', session=session_details)


@app.route('/api/get_session_attendance/<int:session_id>')
@controller_required
def get_session_attendance(session_id):
    conn = get_db_connection()
    students_attendance = []
    if conn is None:
        print("ERROR: get_session_attendance: Database connection error.")
        return jsonify({"success": False, "message": "Database connection error.", "students": []}), 500

    try:
        cur = conn.cursor(cursor_factory=psycopg2.extras.DictCursor)

        # First, determine the class_id associated with this session
        cur.execute("SELECT class_id FROM attendance_sessions WHERE id = %s", (session_id,))
        session_class_id_result = cur.fetchone()
        if not session_class_id_result:
            print(f"DEBUG: get_session_attendance: Session ID {session_id} not found in attendance_sessions.")
            return jsonify({"success": False, "message": "Session not found.", "students": []}), 404
        
        session_class_id = session_class_id_result[0]

        # Get all students for the batch associated with this class (assuming 'BA' for now)
        # Note: If you introduce more classes/batches, this logic needs to be dynamic.
        cur.execute("SELECT id, enrollment_no, name FROM students WHERE batch = 'BA' ORDER BY enrollment_no")
        all_students = {s['id']: dict(s) for s in cur.fetchall()}

        # Get attendance records for the specific session
        cur.execute("SELECT student_id FROM attendance_records WHERE session_id = %s", (session_id,))
        present_student_ids = {row[0] for row in cur.fetchall()}

        # Compile the list of all students with their attendance status
        for student_id, student_details in all_students.items():
            is_present = student_id in present_student_ids
            students_attendance.append({
                'id': student_details['id'],
                'enrollment_no': student_details['enrollment_no'],
                'name': student_details['name'],
                'is_present': is_present
            })
        
        # Sort by enrollment number for consistent display
        students_attendance.sort(key=lambda x: x['enrollment_no'])
        print(f"DEBUG: get_session_attendance: Retrieved attendance for {len(students_attendance)} students in session {session_id}.")
        return jsonify({"success": True, "students": students_attendance})

    except Exception as e:
        print(f"ERROR: get_session_attendance: Exception fetching session attendance for {session_id}: {e}")
        return jsonify({"success": False, "message": "An error occurred.", "students": []}), 500
    finally:
        if conn:
            cur.close()
            conn.close()


@app.route('/api/update_attendance_record', methods=['POST'])
@controller_required
def update_attendance_record():
    data = request.get_json()
    session_id = data.get('session_id')
    student_id = data.get('student_id')
    is_present = data.get('is_present')

    if not all([session_id, student_id is not None, is_present is not None]):
        print("ERROR: update_attendance_record: Missing session_id, student_id, or is_present.")
        return jsonify({"success": False, "message": "Missing required data."}), 400

    conn = get_db_connection()
    if conn is None:
        print("ERROR: update_attendance_record: Database connection error.")
        return jsonify({"success": False, "message": "Database connection error."}), 500

    try:
        cur = conn.cursor()
        if is_present:
            # Check if record already exists before inserting
            cur.execute(
                "SELECT id FROM attendance_records WHERE session_id = %s AND student_id = %s",
                (session_id, student_id)
            )
            if not cur.fetchone(): # If record doesn't exist, insert it
                cur.execute(
                    """
                    INSERT INTO attendance_records (session_id, student_id, timestamp, latitude, longitude, ip_address)
                    VALUES (%s, %s, %s, NULL, NULL, 'Manual_Edit')
                    """, # Latitude/Longitude/IP are NULL for manual edits
                    (session_id, student_id, datetime.now(timezone.utc))
                )
                print(f"DEBUG: update_attendance_record: Inserted record for student {student_id} in session {session_id}.")
            else:
                print(f"DEBUG: update_attendance_record: Record for student {student_id} in session {session_id} already exists (present). No change needed.")
        else:
            # Delete the record if marking absent
            cur.execute(
                "DELETE FROM attendance_records WHERE session_id = %s AND student_id = %s",
                (session_id, student_id)
            )
            if cur.rowcount > 0:
                print(f"DEBUG: update_attendance_record: Deleted record for student {student_id} in session {session_id}.")
            else:
                print(f"DEBUG: update_attendance_record: Record for student {student_id} in session {session_id} not found (already absent?). No change needed.")
        conn.commit()
        return jsonify({"success": True, "message": "Attendance updated."})
    except Exception as e:
        print(f"ERROR: update_attendance_record: Exception updating attendance record: {e}")
        conn.rollback()
        return jsonify({"success": False, "message": "An error occurred while updating attendance."})
    finally:
        if conn:
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
    # To run locally: flask run
    print("Running Flask app locally...")
    app.run(debug=True, port=5000)
