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
// === STUDENT PAGE LOGIC (with simplified fingerprinting) ===
// ==============================================================================
function initStudentPage() {
    const attendanceForm = document.getElementById('attendance-form');
    const locationStatusDiv = document.getElementById('location-status');
    const markAttendanceButton = document.getElementById('mark-btn');
    const enrollmentNoInput = document.getElementById('enrollment_no');
    const studentNameDisplay = document.getElementById('student-name-display');
    const timerStudentSpan = document.getElementById('timer-student');

    if (!window.activeSessionDataStudent || !window.activeSessionDataStudent.id) {
        console.log('No active session data found on student page.');
        return;
    }

    startStudentTimer(window.activeSessionDataStudent.remaining_time, timerStudentSpan);
    checkLocationOnLoad();

    enrollmentNoInput.addEventListener('input', debounce(fetchStudentName, 300));
    attendanceForm.addEventListener('submit', handleAttendanceSubmit);

    function checkLocationOnLoad() {
        if (!navigator.geolocation) {
            updateLocationStatus('Geolocation is not supported by your browser.', 'error');
            return;
        }
        navigator.geolocation.getCurrentPosition(
            (position) => {
                if (!window.geofenceData || typeof window.geofenceData.geofence_lat === 'undefined') {
                    updateLocationStatus('Geofence data not loaded. Please refresh.', 'error');
                    return;
                }
                const { latitude, longitude } = position.coords;
                const distance = haversineDistance(latitude, longitude, window.geofenceData.geofence_lat, window.geofenceData.geofence_lon);
                if (distance <= window.geofenceData.geofence_radius) {
                    locationStatusDiv.style.display = 'none';
                    attendanceForm.style.display = 'block';
                } else {
                    updateLocationStatus(`You are too far from class (${distance.toFixed(0)}m away). Please move closer and refresh.`, 'error');
                }
            },
            () => {
                updateLocationStatus('Could not get your location. Please grant location permission and refresh.', 'error');
            },
            { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
        );
    }

    async function handleAttendanceSubmit(e) {
        e.preventDefault();
        markAttendanceButton.disabled = true;
        markAttendanceButton.textContent = "Processing...";
        showStatusMessage('Verifying device and location...', 'info');

        try {
            const visitorId = getCanvasFingerprint();

            navigator.geolocation.getCurrentPosition(
                async (position) => {
                    try {
                        const { latitude, longitude } = position.coords;
                        
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
                    } catch (fetchError) {
                        console.error('Error during fetch submission:', fetchError);
                        showStatusMessage('An unexpected error occurred during submission. Please check your network.', 'error');
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
        } catch (error) {
            console.error('Error during fingerprinting:', error);
            showStatusMessage('An unexpected error occurred. Could not verify device.', 'error');
            markAttendanceButton.disabled = false;
            markAttendanceButton.textContent = "Mark Attendance";
        }
    }

    async function fetchStudentName() {
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

    function updateLocationStatus(message, type) {
        locationStatusDiv.textContent = message;
        locationStatusDiv.className = `status-message ${type}`;
        locationStatusDiv.style.display = 'block';
    }
}

// ==============================================================================
// === CONTROLLER, REPORT, & EDIT PAGE LOGIC (UNCHANGED) ===
// ==============================================================================
// Your original, unchanged JavaScript for the admin pages would go here.
// For brevity, it is not repeated, but ensure you use your full, original code for these parts.

// ==============================================================================
// === UTILITY FUNCTIONS ===
// ==============================================================================
function getCanvasFingerprint() {
    const canvas = document.createElement('canvas');
    const ctx = canvas.getContext('2d');
    const txt = 'Browser-ID: Ritik Attendance App';
    ctx.textBaseline = "top";
    ctx.font = "14px 'Arial'";
    ctx.textBaseline = "alphabetic";
    ctx.fillStyle = "#f60";
    ctx.fillRect(125, 1, 62, 20);
    ctx.fillStyle = "#069";
    ctx.fillText(txt, 2, 15);
    ctx.fillStyle = "rgba(102, 204, 0, 0.7)";
    ctx.fillText(txt, 4, 17);
    return canvas.toDataURL();
}

function startStudentTimer(remainingTime, timerElement) { /* ... */ }
function showStatusMessage(message, type) { /* ... */ }
function haversineDistance(lat1, lon1, lat2, lon2) { /* ... */ }
function debounce(func, delay) { /* ... */ }

// Make sure to copy the full content of your original admin/utility functions into this file.