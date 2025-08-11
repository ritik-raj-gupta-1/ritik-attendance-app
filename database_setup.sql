-- This script sets up the PostgreSQL database for the attendance system.
-- It is designed to be run once to create all necessary tables and insert initial data.

-- IMPORTANT: These DROP TABLE statements will delete all existing data in these tables.
-- This is crucial for a clean setup.
-- CASCADE ensures that dependent objects (like foreign keys) are also dropped.
DROP TABLE IF EXISTS attendance_records CASCADE;
DROP TABLE IF EXISTS attendance_sessions CASCADE;
DROP TABLE IF EXISTS classes CASCADE;
DROP TABLE IF EXISTS students CASCADE;
DROP TABLE IF EXISTS users CASCADE;
DROP TABLE IF EXISTS daily_attendance_ips CASCADE;
DROP TABLE IF EXISTS session_device_fingerprints CASCADE; -- Drop the new table if it exists

-- Table for the single controller user
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'controller' CHECK (role = 'controller')
);

-- Table for student data
CREATE TABLE students (
    id SERIAL PRIMARY KEY,
    enrollment_no VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    batch VARCHAR(50) NOT NULL
);

-- Table for class data
CREATE TABLE classes (
    id SERIAL PRIMARY KEY,
    class_name VARCHAR(100) UNIQUE NOT NULL,
    controller_id INTEGER REFERENCES users(id),
    geofence_lat REAL,
    geofence_lon REAL,
    geofence_radius INT
);

-- Table to log attendance sessions
CREATE TABLE attendance_sessions (
    id SERIAL PRIMARY KEY,
    class_id INT REFERENCES classes(id),
    controller_id INT REFERENCES users(id),
    session_token VARCHAR(32) UNIQUE NOT NULL,
    start_time TIMESTAMPTZ NOT NULL,
    end_time TIMESTAMPTZ NOT NULL,
    is_active BOOLEAN NOT NULL DEFAULT TRUE,
    last_updated TIMESTAMPTZ DEFAULT CURRENT_TIMESTAMP
);

-- Table to store attendance records
CREATE TABLE attendance_records (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    student_id INT REFERENCES students(id),
    timestamp TIMESTAMPTZ NOT NULL,
    latitude REAL,
    longitude REAL,
    ip_address TEXT,
    UNIQUE (session_id, student_id) -- CRITICAL: Ensures unique attendance per student per session
);

-- NEW, SIMPLE TABLE for Device Fingerprinting
CREATE TABLE session_device_fingerprints (
    id SERIAL PRIMARY KEY,
    session_id INT REFERENCES attendance_sessions(id) ON DELETE CASCADE,
    student_id INT REFERENCES students(id) ON DELETE CASCADE,
    fingerprint TEXT NOT NULL,
    UNIQUE (session_id, student_id), -- A student can only have one fingerprint per session
    UNIQUE (session_id, fingerprint) -- A fingerprint can only be used once per session
);

-- Insert the single controller user
INSERT INTO users (username, role) VALUES ('controller', 'controller') ON CONFLICT (username) DO NOTHING;

-- Insert the single class data for BA - Anthropology
INSERT INTO classes (class_name, controller_id, geofence_lat, geofence_lon, geofence_radius) VALUES
('BA - Anthropology', (SELECT id FROM users WHERE username = 'controller'), 23.828889, 78.775000, 1800) -- RADIUS SET TO 1800m FOR TESTING
ON CONFLICT (class_name) DO NOTHING;

-- Insert all BA student data (77 students)
INSERT INTO students (enrollment_no, name, batch) VALUES
('Y24120001', 'ANSHUL TAMRAKAR', 'BA'),
('Y24120002', 'KHUSHVEER SINGH SURYA', 'BA'),
('Y24120003', 'SHREYASHI JAIN', 'BA'),
('Y24120041', 'VIJAY KUMAR', 'BA'),
('Y24120060', 'AARYA GOANTIYA', 'BA'),
('Y24120061', 'ANIYA PARTE', 'BA'),
('Y24120062', 'SATYAM SEN', 'BA'),
('Y24120087', 'AGRATI AGRAWAL', 'BA'),
('Y24120088', 'SHUBHAM CHOUBEY', 'BA'),
('Y24120116', 'HARSH LODHI', 'BA'),
('Y24120127', 'RITIK RAJ', 'BA'),
('Y24120129', 'BOBI RAJA', 'BA'),
('Y24120150', 'JAYA RAIKWAR', 'BA'),
('Y24120151', 'KUNDAN RAJAK', 'BA'),
('Y24120152', 'VINAY SINGH THAKUR', 'BA'),
('Y24120184', 'BHARTESHU GRAY', 'BA'),
('Y24120185', 'RAGINI GOUND', 'BA'),
('Y24120187', 'RAMPAL SINGH THAKUR', 'BA'),
('Y24120188', 'SHREYA THAKUR', 'BA'),
('Y24120203', 'ABHISHEK YADAV', 'BA'),
('Y24120204', 'ADITYA SINGH', 'BA'),
('Y24120205', 'AVINASH AHIRWAR', 'BA'),
('Y24120206', 'HARSH KHANGAR', 'BA'),
('Y24120207', 'KRISH YADAV', 'BA'),
('Y24120244', 'ARJUN PATEL', 'BA'),
('Y24120245', 'DEEPAK SANJAY MUNDHE', 'BA'),
('Y24120246', 'NANCY PANDEY', 'BA'),
('Y24120260', 'AYUSH AHIRWAR', 'BA'),
('Y24120261', 'NEERAJ YADAV', 'BA'),
('Y24120280', 'ADITYA VINODIYA', 'BA'),
('Y24120282', 'RIMJHIM SONI', 'BA'),
('Y24120283', 'SHIVANSHU MISHRA', 'BA'),
('Y24120293', 'ABHI YADAV', 'BA'),
('Y24120294', 'ADITYA TIWARI', 'BA'),
('Y24120296', 'KRASHITA PANDEY', 'BA'),
('Y24120298', 'PRIYANSH SHRIVASTAVA', 'BA'),
('Y24120325', 'KRISHNA RAIKWAR', 'BA'),
('Y24120333', 'AYUSHI SURYAVANSHI', 'BA'),
('Y24120334', 'KHUSHI AHIRWAR', 'BA'),
('Y24120337', 'SHUBHAM AHIRWAR', 'BA'),
('Y24120339', 'ASHISH KUMAR', 'BA'),
('Y24120355', 'KULDEEP YADAV', 'BA'),
('Y24120356', 'NEETESH DANGI', 'BA'),
('Y24120393', 'NANCY JAIN', 'BA'),
('Y24120395', 'MEENAKSHI SEN', 'BA'),
('Y24120449', 'HARSH YADAV', 'BA'),
('Y24120526', 'RISHITA YADAV', 'BA'),
('Y24120547', 'NIHAL KAROSIA', 'BA'),
('Y24120548', 'SOMIL KAROSIYA', 'BA'),
('Y24120549', 'VINAY KUMAR YADAV', 'BA'),
('Y24120553', 'KHUSHI YADAV', 'BA'),
('Y24120554', 'PRATHMESH AHIRWAR', 'BA'),
('Y24120555', 'UDIT NAMDEV', 'BA'),
('Y24120556', 'VAISHALI SEN', 'BA'),
('Y24120594', 'SOURABH SINGH LODHI', 'BA'),
('Y24120599', 'KHUSHI SONI', 'BA'),
('Y24120600', 'MUKESH PRAJAPATI', 'BA'),
('Y24120607', 'JIYA SEN', 'BA'),
('Y24120618', 'ANSHIKA SIROTHIYA', 'BA'),
('Y24120621', 'APRAJITA PATHAK', 'BA'),
('Y24120634', 'PUNEET SEN', 'BA'),
('Y24120640', 'PRINCI JAIN', 'BA'),
('Y24120641', 'VIVEK AHIRWAR', 'BA'),
('Y24120646', 'ANJLEE YADAV', 'BA'),
('Y24120647', 'APOORVA THAKUR', 'BA'),
('Y24120657', 'AMAN KUMAR MARAVI', 'BA'),
('Y24120659', 'SHIVANSH VISHWAKARMA', 'BA'),
('Y24120661', 'SIMRAN BEE', 'BA'),
('Y24120664', 'HARSH SEN', 'BA'),
('Y24120665', 'PRATEEK NEGI', 'BA'),
('Y24120678', 'JIYA DUBEY', 'BA'),
('Y24120691', 'KHUSHBOO AHIRWAR', 'BA'),
('Y24120692', 'JAYANT SEN', 'BA'),
('Y24120697', 'JIGYASHA SHARMA', 'BA'),
('Y24130025', 'RAKSHA SINGH', 'BA'),
('Y24130066', 'AASHIYA RANGREJ', 'BA'),
('Y24130071', 'AMAN GHARU', 'BA')
ON CONFLICT (enrollment_no) DO NOTHING;
