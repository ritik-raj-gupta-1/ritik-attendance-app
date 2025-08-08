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

-- Table for the single controller user (no password column here as it's hardcoded in app.py)
CREATE TABLE users (
    id SERIAL PRIMARY KEY,
    username VARCHAR(50) UNIQUE NOT NULL,
    role VARCHAR(20) NOT NULL DEFAULT 'controller' CHECK (role = 'controller') -- Only 'controller' role
);

-- Table for student data
CREATE TABLE students (
    id SERIAL PRIMARY KEY,
    enrollment_no VARCHAR(20) UNIQUE NOT NULL,
    name VARCHAR(100) NOT NULL,
    batch VARCHAR(50) NOT NULL
);

-- Table for class data (only BA - Anthropology this time)
CREATE TABLE classes (
    id SERIAL PRIMARY KEY,
    class_name VARCHAR(100) NOT NULL,
    controller_id INTEGER, -- Renamed from teacher_id to reflect single controller
    geofence_lat REAL,
    geofence_lon REAL,
    geofence_radius REAL, -- Radius in meters for geofencing
    FOREIGN KEY (controller_id) REFERENCES users(id)
);

-- Table for attendance sessions
CREATE TABLE attendance_sessions (
    id SERIAL PRIMARY KEY,
    class_id INTEGER NOT NULL,
    controller_id INTEGER NOT NULL,
    session_token VARCHAR(32) UNIQUE NOT NULL,
    start_time TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    end_time TIMESTAMP WITH TIME ZONE,
    is_active BOOLEAN DEFAULT TRUE,
    last_updated TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    FOREIGN KEY (class_id) REFERENCES classes(id),
    FOREIGN KEY (controller_id) REFERENCES users(id)
);

-- Table for individual attendance records
CREATE TABLE attendance_records (
    id SERIAL PRIMARY KEY,
    session_id INTEGER NOT NULL,
    student_id INTEGER NOT NULL,
    timestamp TIMESTAMP WITH TIME ZONE DEFAULT CURRENT_TIMESTAMP,
    latitude REAL,
    longitude REAL,
    ip_address VARCHAR(45), -- Increased length for IPv6
    -- Add a UNIQUE constraint on session_id and student_id
    UNIQUE (session_id, student_id),
    FOREIGN KEY (session_id) REFERENCES attendance_sessions(id),
    FOREIGN KEY (student_id) REFERENCES students(id)
);

-- Table to track IP addresses that have marked attendance for a given day
CREATE TABLE daily_attendance_ips (
    id SERIAL PRIMARY KEY,
    ip_address VARCHAR(45) NOT NULL,
    date DATE NOT NULL,
    UNIQUE (ip_address, date) -- Ensure only one entry per IP per day
);

-- Insert initial data
INSERT INTO users (username, role) VALUES ('controller', 'controller') ON CONFLICT (username) DO NOTHING;

-- Get the controller_id after insertion (or if it already exists)
DO $$
DECLARE
    controller_user_id INT;
BEGIN
    SELECT id INTO controller_user_id FROM users WHERE username = 'controller';

    -- Insert BA - Anthropology class, linking to the controller
    INSERT INTO classes (class_name, controller_id, geofence_lat, geofence_lon, geofence_radius) VALUES
    ('BA - Anthropology', controller_user_id, 23.828889, 78.775000, 100) -- Example coordinates for Anthropology Department, radius 100 meters
    ON CONFLICT (class_name) DO NOTHING;
END $$;


-- Insert sample student data for BA batch (77 students)
INSERT INTO students (enrollment_no, name, batch) VALUES
('Y24120001', 'ALOK KUMAR', 'BA'),
('Y24120002', 'ANJALI SINGH', 'BA'),
('Y24120003', 'RAHUL SHARMA', 'BA'),
('Y24120004', 'PRIYA GUPTA', 'BA'),
('Y24120005', 'SANJAY VERMA', 'BA'),
('Y24120006', 'POOJA YADAV', 'BA'),
('Y24120007', 'MOHIT SAHU', 'BA'),
('Y24120008', 'SHWETA SINGH', 'BA'),
('Y24120009', 'AMIT KUMAR', 'BA'),
('Y24120010', 'NEHA PATEL', 'BA'),
('Y24120011', 'VIKAS JAIN', 'BA'),
('Y24120012', 'RITU KUSHWAHA', 'BA'),
('Y24120013', 'GAURAV MISHRA', 'BA'),
('Y24120014', 'DIVYA SINGH', 'BA'),
('Y24120015', 'ARJUN CHOUHAN', 'BA'),
('Y24120016', 'KOMAL SHARMA', 'BA'),
('Y24120017', 'MANISH KUMAR', 'BA'),
('Y24120018', 'SONAM SAHU', 'BA'),
('Y24120019', 'DEEPAK YADAV', 'BA'),
('Y24120020', 'SHALINI SINGH', 'BA'),
('Y24120021', 'PRASHANT GUPTA', 'BA'),
('Y24120022', 'ANURADHA VERMA', 'BA'),
('Y24120023', 'ROHIT SAHU', 'BA'),
('Y24120024', 'SWATI SINGH', 'BA'),
('Y24120025', 'VIVEK KUMAR', 'BA'),
('Y24120026', 'ANJALI SHARMA', 'BA'),
('Y24120027', 'HARSHIT JAIN', 'BA'),
('Y24120028', 'KHUSHI YADAV', 'BA'),
('Y24120029', 'AYUSH SINGH', 'BA'),
('Y24120030', 'MUSKAN SAHU', 'BA'),
('Y24120031', 'ADITYA KUMAR', 'BA'),
('Y24120032', 'SHIVANI PATEL', 'BA'),
('Y24120033', 'SACHIN VERMA', 'BA'),
('Y24120034', 'RASHMI SINGH', 'BA'),
('Y24120035', 'PIYUSH JAIN', 'BA'),
('Y24120036', 'NISHA KUSHWAHA', 'BA'),
('Y24120037', 'RAVI SHANKAR', 'BA'),
('Y24120038', 'MONIKA SINGH', 'BA'),
('Y24120039', 'AKASH YADAV', 'BA'),
('Y24120040', 'PREETI GUPTA', 'BA'),
('Y24120041', 'SOURABH SAHU', 'BA'),
('Y24120042', 'DIKSHA SINGH', 'BA'),
('Y24120043', 'ABHISHEK KUMAR', 'BA'),
('Y24120044', 'SHRUTI SHARMA', 'BA'),
('Y24120045', 'ASHISH JAIN', 'BA'),
('Y24120046', 'ANJALI KUSHWAHA', 'BA'),
('Y24120047', 'VISHAL SINGH', 'BA'),
('Y24120048', 'PRIYANKA YADAV', 'BA'),
('Y24120049', 'KARAN VERMA', 'BA'),
('Y24120050', 'MANSI SAHU', 'BA'),
('Y24120051', 'ALOK AHIRWAR', 'BA'),
('Y24120052', 'ANJALI AHIRWAR', 'BA'),
('Y24120053', 'RAHUL AHIRWAR', 'BA'),
('Y24120054', 'PRIYA AHIRWAR', 'BA'),
('Y24120055', 'SANJAY AHIRWAR', 'BA'),
('Y24120056', 'POOJA AHIRWAR', 'BA'),
('Y24120057', 'MOHIT AHIRWAR', 'BA'),
('Y24120058', 'SHWETA AHIRWAR', 'BA'),
('Y24120059', 'AMIT AHIRWAR', 'BA'),
('Y24120060', 'NEHA AHIRWAR', 'BA'),
('Y24120061', 'VIKAS AHIRWAR', 'BA'),
('Y24120062', 'RITU AHIRWAR', 'BA'),
('Y24120063', 'GAURAV AHIRWAR', 'BA'),
('Y24120064', 'DIVYA AHIRWAR', 'BA'),
('Y24120065', 'ARJUN AHIRWAR', 'BA'),
('Y24120066', 'KOMAL AHIRWAR', 'BA'),
('Y24120067', 'MANISH AHIRWAR', 'BA'),
('Y24120068', 'SONAM AHIRWAR', 'BA'),
('Y24120069', 'DEEPAK AHIRWAR', 'BA'),
('Y24120070', 'SHALINI AHIRWAR', 'BA'),
('Y24120071', 'PRASHANT AHIRWAR', 'BA'),
('Y24120072', 'ANURADHA AHIRWAR', 'BA'),
('Y24120073', 'ROHIT AHIRWAR', 'BA'),
('Y24120074', 'SWATI AHIRWAR', 'BA'),
('Y24120075', 'VIVEK AHIRWAR', 'BA'),
('Y24120076', 'ANJALI AHIRWAR', 'BA'),
('Y24120077', 'HARSHIT AHIRWAR', 'BA')
ON CONFLICT (enrollment_no) DO NOTHING;
