// static/main.js

document.addEventListener('DOMContentLoaded', () => {
    // Initialize logic based on the current page
    if (document.getElementById('attendance-form')) {
        initStudentPage();
    }
    if (document.getElementById('start-session-btn') || document.querySelector('.end-session-btn') || document.querySelector('.delete-day-btn')) {
        initControllerAndReportPage();
    }
    if (document.getElementById('attendance-table') && document.getElementById('attendance-table').dataset.attendanceDate) {
        initEditAttendancePage();
    }
});

// ==============================================================================
// === STUDENT PAGE LOGIC ===
// ==============================================================================
function initStudentPage() {
    const attendanceForm = document.getElementById('attendance-form');
    const markAttendanceButton = document.getElementById('mark-btn');
    const enrollmentNoInput = document.getElementById('enrollment_no');
    const studentNameDisplay = document.getElementById('student-name-display');
    const timerStudentSpan = document.getElementById('timer-student');

    if (!window.activeSessionDataStudent || !window.activeSessionDataStudent.id) {
        return; // No active session, so no JS logic needed.
    }

    startStudentTimer(window.activeSessionDataStudent.remaining_time, timerStudentSpan);
    
    enrollmentNoInput.addEventListener('input', debounce(fetchStudentName, 300));
    attendanceForm.addEventListener('submit', handleAttendanceSubmit);

    async function handleAttendanceSubmit(e) {
        e.preventDefault();
        markAttendanceButton.disabled = true;
        markAttendanceButton.textContent = "Processing...";
        showStatusMessage('Getting your location...', 'info');

        if (!navigator.geolocation) {
            showStatusMessage('Geolocation is not supported by your browser.', 'error');
            markAttendanceButton.disabled = false;
            markAttendanceButton.textContent = "Mark Attendance";
            return;
        }

        // Get student's current position
        navigator.geolocation.getCurrentPosition(
            async (position) => {
                const { latitude, longitude } = position.coords;
                
                // The canvas fingerprint is no longer needed.
                // We only send location and enrollment data.
                const formData = new URLSearchParams({
                    enrollment_no: enrollmentNoInput.value.trim().toUpperCase(),
                    session_id: window.activeSessionDataStudent.id,
                    latitude: latitude,
                    longitude: longitude,
                });

                try {
                    const response = await fetch('/mark_attendance', {
                        method: 'POST',
                        headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                        body: formData
                    });
                    const data = await response.json();
                    showStatusMessage(data.message, data.category);

                    if (data.success) {
                        // On success, disable the form to prevent resubmission
                        attendanceForm.innerHTML = `<p style="text-align:center; font-weight:bold; color:green;">${data.message}</p>`;
                    }
                } catch (error) {
                    showStatusMessage('An unexpected network error occurred.', 'error');
                } finally {
                    // Re-enable button only if there was a non-successful submission
                    if (!document.querySelector('#attendance-form p')) {
                        markAttendanceButton.disabled = false;
                        markAttendanceButton.textContent = "Mark Attendance";
                    }
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
// === CONTROLLER & REPORT PAGE LOGIC ===
// ==============================================================================
function initControllerAndReportPage() {
    const startSessionBtn = document.getElementById('start-session-btn');
    if (startSessionBtn) {
        startSessionBtn.addEventListener('click', startNewSessionWithLocation);
    }
    
    // Timer for active session on dashboard
    if (typeof window.activeSessionData !== 'undefined' && window.activeSessionData.id) {
        let remainingTime = window.activeSessionData.remaining_time;
        let timerDisplay = document.getElementById(`timer-${window.activeSessionData.id}`);
        if (timerDisplay && remainingTime > 0) {
            let controllerTimer = setInterval(() => {
                remainingTime--;
                if (remainingTime <= 0) {
                    clearInterval(controllerTimer);
                    window.location.reload();
                }
                let minutes = Math.floor(remainingTime / 60);
                let seconds = remainingTime % 60;
                timerDisplay.innerHTML = `${minutes}m ${seconds}s`;
            }, 1000);
        }
    }

    document.querySelectorAll('.end-session-btn').forEach(button => {
        button.addEventListener('click', async function() {
            const sessionId = this.dataset.sessionId;
            showStatusMessage('Ending session...', 'info');
            try {
                const response = await fetch(`/end_session/${sessionId}`, { method: 'POST' });
                const data = await response.json();
                showStatusMessage(data.message, data.category);
                if (data.success) {
                    setTimeout(() => window.location.reload(), 1500);
                }
            } catch (error) {
                showStatusMessage('An error occurred while ending the session.', 'error');
            }
        });
    });
}

async function startNewSessionWithLocation() {
    const startBtn = document.getElementById('start-session-btn');
    startBtn.disabled = true;
    startBtn.textContent = 'Getting Location...';
    showStatusMessage('Please allow location access to start the session.', 'info');

    if (!navigator.geolocation) {
        showStatusMessage('Geolocation is not supported by your browser.', 'error');
        startBtn.disabled = false;
        startBtn.textContent = 'Start New Session';
        return;
    }

    navigator.geolocation.getCurrentPosition(
        async (position) => {
            const { latitude, longitude } = position.coords;
            startBtn.textContent = 'Starting Session...';
            
            try {
                const response = await fetch('/start_session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ latitude, longitude })
                });
                const data = await response.json();
                showStatusMessage(data.message, data.category);
                if (data.success) {
                    setTimeout(() => window.location.reload(), 1500);
                } else {
                    startBtn.disabled = false;
                    startBtn.textContent = 'Start New Session';
                }
            } catch (error) {
                showStatusMessage('An error occurred.', 'error');
                startBtn.disabled = false;
                startBtn.textContent = 'Start New Session';
            }
        },
        (error) => {
            showStatusMessage(`Geolocation Error: ${error.message}`, 'error');
            startBtn.disabled = false;
            startBtn.textContent = 'Start New Session';
        },
        { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
    );
}

// ==============================================================================
// === EDIT ATTENDANCE PAGE LOGIC ===
// ==============================================================================
function initEditAttendancePage() {
    const editAttendanceTable = document.getElementById('attendance-table');
    const attendanceDate = editAttendanceTable.dataset.attendanceDate;

    async function fetchStudentsForEdit(dateStr) {
        const tbody = editAttendanceTable.querySelector('tbody');
        tbody.innerHTML = '<tr><td colspan="3">Loading students...</td></tr>';
        try {
            const response = await fetch(`/api/get_daily_attendance_for_edit/${dateStr}`);
            const data = await response.json();
            if (!data.success || !data.students) {
                tbody.innerHTML = `<tr><td colspan="3">${data.message || 'Failed to load students.'}</td></tr>`;
                return;
            }
            tbody.innerHTML = '';
            data.students.forEach(student => {
                const row = tbody.insertRow();
                row.innerHTML = `<td>${student.enrollment_no}</td><td>${student.name}</td><td><input type="checkbox" data-student-id="${student.id}" class="attendance-checkbox" ${student.is_present ? 'checked' : ''}></td>`;
            });
            tbody.querySelectorAll('.attendance-checkbox').forEach(checkbox => {
                checkbox.addEventListener('change', function() {
                    const studentId = this.dataset.studentId;
                    const isPresent = this.checked;
                    updateAttendanceRecord(dateStr, studentId, isPresent, this);
                });
            });
        } catch (error) {
            tbody.innerHTML = '<tr><td colspan="3">An unexpected error occurred.</td></tr>';
        }
    }

    async function updateAttendanceRecord(dateStr, studentId, isPresent, checkboxElement) {
        showStatusMessage('Updating attendance...', 'info');
        try {
            const response = await fetch('/api/update_daily_attendance_record', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date_str: dateStr, student_id: studentId, is_present: isPresent })
            });
            const data = await response.json();
            showStatusMessage(data.message, data.success ? 'success' : 'error');
            if (!data.success) {
                checkboxElement.checked = !isPresent; // Revert checkbox on failure
            }
        } catch (error) {
            showStatusMessage('An error occurred while updating.', 'error');
            checkboxElement.checked = !isPresent; // Revert checkbox on failure
        }
    }

    fetchStudentsForEdit(attendanceDate);
}

// ==============================================================================
// === UTILITY FUNCTIONS ===
// ==============================================================================
function startStudentTimer(remainingTime, timerElement) { if (!timerElement || remainingTime <= 0) return; let timer = setInterval(() => { remainingTime--; if (remainingTime <= 0) { clearInterval(timer); timerElement.innerHTML = "Session ended."; const markBtn = document.getElementById('mark-btn'); if(markBtn) {markBtn.disabled = true; markBtn.textContent = "Session Ended"; } return; } let minutes = Math.floor(remainingTime / 60); let seconds = remainingTime % 60; timerElement.innerHTML = `${minutes}m ${seconds.toString().padStart(2, '0')}s`; }, 1000); }
function showStatusMessage(message, type) { const statusMessageDiv = document.getElementById('status-message'); if (statusMessageDiv) { statusMessageDiv.textContent = message; statusMessageDiv.className = `status-message ${type}`; statusMessageDiv.style.display = 'block'; setTimeout(() => { statusMessageDiv.style.display = 'none'; }, 5000); } }
function haversineDistance(lat1, lon1, lat2, lon2) { const R = 6371e3; const φ1 = lat1 * Math.PI / 180; const φ2 = lat2 * Math.PI / 180; const Δφ = (lat2 - lat1) * Math.PI / 180; const Δλ = (lon2 - lon1) * Math.PI / 180; const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) + Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) * Math.sin(Δλ / 2); const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a)); return R * c; }
function debounce(func, delay) { let timeout; return function(...args) { clearTimeout(timeout); timeout = setTimeout(() => func.apply(this, args), delay); }; }
