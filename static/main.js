// static/main.js

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('attendance-form')) {
        console.log('Initializing Student Page Logic...');
        initStudentPage();
    }
    
    if (document.querySelector('.end-session-btn') || document.querySelector('.delete-day-btn')) {
        console.log('Initializing Controller/Report Page Logic...');
        initControllerAndReportPage();
    }

    if (document.getElementById('attendance-table')) {
        console.log('Initializing Edit Attendance Page Logic...');
        initEditAttendancePage();
    }
});

// ==============================================================================
// === STUDENT PAGE LOGIC (Location check on SUBMIT) ===
// ==============================================================================
function initStudentPage() {
    const attendanceForm = document.getElementById('attendance-form');
    const markAttendanceButton = document.getElementById('mark-btn');
    const enrollmentNoInput = document.getElementById('enrollment_no');
    const studentNameDisplay = document.getElementById('student-name-display');
    const timerStudentSpan = document.getElementById('timer-student');

    if (!window.activeSessionDataStudent || !window.activeSessionDataStudent.id) {
        console.log('No active session data found on student page.');
        return;
    }

    startStudentTimer(window.activeSessionDataStudent.remaining_time, timerStudentSpan);
    
    // The on-load location check has been REMOVED.

    enrollmentNoInput.addEventListener('input', debounce(fetchStudentName, 300));
    attendanceForm.addEventListener('submit', handleAttendanceSubmit);

    async function handleAttendanceSubmit(e) {
        e.preventDefault();
        markAttendanceButton.disabled = true;
        markAttendanceButton.textContent = "Processing...";
        showStatusMessage('Getting location and verifying device...', 'info');

        // Geolocation is now requested HERE, upon submission.
        if (!navigator.geolocation) {
            showStatusMessage('Geolocation is not supported. Cannot mark attendance.', 'error');
            markAttendanceButton.disabled = false;
            markAttendanceButton.textContent = "Mark Attendance";
            return;
        }

        navigator.geolocation.getCurrentPosition(
            async (position) => {
                const { latitude, longitude } = position.coords;
                const distance = haversineDistance(latitude, longitude, window.geofenceData.geofence_lat, window.geofenceData.geofence_lon);

                // Check if inside the radius
                if (distance > window.geofenceData.geofence_radius) {
                    showStatusMessage(`You are too far from class (${distance.toFixed(0)}m away). Please move closer.`, 'error');
                    markAttendanceButton.disabled = false;
                    markAttendanceButton.textContent = "Mark Attendance";
                    return;
                }

                // If location is valid, proceed with fingerprinting and submission
                try {
                    const visitorId = getCanvasFingerprint();
                    
                    const formData = new URLSearchParams({
                        enrollment_no: enrollmentNoInput.value.trim(),
                        session_id: window.activeSessionDataStudent.id,
                        latitude: latitude,
                        longitude: longitude,
                        device_fingerprint: visitorId
                    });

                    const response = await fetch('/mark_attendance', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: formData
                    });

                    const data = await response.json();
                    showStatusMessage(data.message, data.category);

                    if (data.success) {
                        enrollmentNoInput.value = '';
                        studentNameDisplay.textContent = '';
                    }
                } catch (error) {
                    console.error('Error during submission process:', error);
                    showStatusMessage('An unexpected error occurred.', 'error');
                } finally {
                    markAttendanceButton.disabled = false;
                    markAttendanceButton.textContent = "Mark Attendance";
                }
            },
            (geoError) => {
                showStatusMessage('Geolocation error: ' + geoError.message, 'error');
                markAttendanceButton.disabled = false;
                markAttendanceButton.textContent = "Mark Attendance";
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }

    async function fetchStudentName() {
        // This function remains unchanged
        const enrollmentNo = enrollmentNoInput.value.trim();
        if (enrollmentNo.length >= 5) {
            try {
                const response = await fetch(`/api/get_student_name/${enrollmentNo}`);
                const data = await response.json();
                studentNameDisplay.textContent = data.name ? `Name: ${data.name}` : 'Student not found.';
                studentNameDisplay.style.color = data.name ? '#0056b3' : '#dc3545';
            } catch (error) {
                studentNameDisplay.textContent = 'Error fetching name.';
            }
        } else {
            studentNameDisplay.textContent = '';
        }
    }
}

// ==============================================================================
// === CONTROLLER, REPORT, & EDIT PAGE LOGIC (UNCHANGED) ===
// ==============================================================================
function initControllerAndReportPage() { /* ... Your original, unchanged code ... */ }
function initEditAttendancePage() { /* ... Your original, unchanged code ... */ }

// ==============================================================================
// === UTILITY FUNCTIONS (UNCHANGED) ===
// ==============================================================================
function getCanvasFingerprint() { /* ... Your original, unchanged code ... */ }
function startStudentTimer(remainingTime, timerElement) { /* ... Your original, unchanged code ... */ }
function showStatusMessage(message, type) { /* ... Your original, unchanged code ... */ }
function haversineDistance(lat1, lon1, lat2, lon2) { /* ... Your original, unchanged code ... */ }
function debounce(func, delay) { /* ... Your original, unchanged code ... */ }

// NOTE: To save space, the unchanged functions are collapsed. 
// Your full, original code for those functions is correct.