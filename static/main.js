/**
 * Frontend logic for the B.A. Anthropology Attendance System.
 * Handles student submissions, controller actions, and data editing.
 */

// =============================================================================
// === UTILITY & HELPER FUNCTIONS (MOVED TO TOP FOR GLOBAL ACCESS) ============
// =============================================================================

/**
 * Displays a temporary status message to the user.
 * @param {string} message The message to display.
 * @param {string} type The category of the message (e.g., 'success', 'error', 'info').
 */
function showStatusMessage(message, type) {
    const statusDiv = document.getElementById('status-message');
    if (statusDiv) {
        statusDiv.textContent = message;
        statusDiv.className = `status-message ${type}`;
        statusDiv.style.display = 'block';

        setTimeout(() => {
            statusDiv.style.display = 'none';
        }, 6000);
    }
}

/**
 * A more robust geolocation function with an accuracy check and retry mechanism.
 * @param {function} successCallback Called with the final position object.
 * @param {function} errorCallback Called with a final error message string.
 */
function getAccurateLocation(successCallback, errorCallback) {
    showStatusMessage('Getting location...', 'info');
    
    navigator.geolocation.getCurrentPosition(
        (pos) => {
            if (pos.coords.accuracy < 150) {
                showStatusMessage('Location found!', 'success');
                successCallback(pos);
                return;
            }

            showStatusMessage('Improving location accuracy...', 'info');
            const watchId = navigator.geolocation.watchPosition(
                (highAccPos) => {
                    navigator.geolocation.clearWatch(watchId);
                    showStatusMessage('High-accuracy location found!', 'success');
                    successCallback(highAccPos);
                },
                (err) => {
                    navigator.geolocation.clearWatch(watchId);
                    errorCallback('Could not get an accurate location. Error: ' + err.message);
                },
                { enableHighAccuracy: true, timeout: 20000, maximumAge: 0 }
            );
        },
        (err) => {
            errorCallback('Could not get location. Error: ' + err.message);
        },
        { enableHighAccuracy: false, timeout: 5000 }
    );
}

/**
 * Fetches the list of present students and updates the UI.
 * @param {number} sessionId The ID of the active session.
 * @param {HTMLElement} listElement The <ul> element to populate.
 */
async function fetchPresentStudents(sessionId, listElement) {
    if (!listElement) return;
    try {
        const response = await fetch(`/api/get_present_students/${sessionId}`);
        const data = await response.json();
        if (data.success && data.students) {
            listElement.innerHTML = data.students.map(s => `<li>${s.name} (${s.enrollment_no})</li>`).join('');
        }
    } catch (error) {
        console.error("Could not fetch present students:", error);
    }
}

/**
 * Fetches a student's name based on their enrollment number for verification.
 */
async function fetchStudentName() {
    const enrollmentInput = document.getElementById('enrollment_no');
    const studentNameDisplay = document.getElementById('student-name-display');
    const enrollmentNo = enrollmentInput.value.trim();
    if (enrollmentNo.length >= 5) {
        try {
            const response = await fetch(`/api/get_student_name/${enrollmentNo}`);
            const data = await response.json();
            studentNameDisplay.textContent = data.name ? `Name: ${data.name}` : 'Student not found.';
            studentNameDisplay.style.color = data.name ? '#0056b3' : '#dc3545';
        } catch {
            studentNameDisplay.textContent = 'Error fetching name.';
        }
    } else {
        studentNameDisplay.textContent = '';
    }
}

/**
 * A non-drifting timer that calculates remaining time from a fixed endpoint.
 * @param {string} endTimeIsoString The ISO 8601 formatted end time.
 * @param {HTMLElement} timerElement The element to display the countdown in.
 */
function startRobustTimer(endTimeIsoString, timerElement) {
    if (!endTimeIsoString || !timerElement) return;
    const endTime = new Date(endTimeIsoString).getTime();

    const timerInterval = setInterval(() => {
        const now = new Date().getTime();
        const remaining = endTime - now;

        if (remaining <= 0) {
            clearInterval(timerInterval);
            timerElement.textContent = "Session Ended";
            const markBtn = document.getElementById('mark-btn');
            if (markBtn) {
                 markBtn.disabled = true;
                 markBtn.closest('form').style.display = 'none';
            }
            return;
        }

        const minutes = Math.floor((remaining % (1000 * 60 * 60)) / (1000 * 60));
        const seconds = Math.floor((remaining % (1000 * 60)) / 1000);
        timerElement.textContent = `${minutes}m ${seconds.toString().padStart(2, '0')}s`;
    }, 1000);
}

function showTroubleshootingTips(show) {
    const tipsElement = document.getElementById('troubleshooting-tips');
    if (tipsElement) {
        tipsElement.style.display = show ? 'block' : 'none';
    }
}

function debounce(func, delay) {
    let timeout;
    return function(...args) {
        clearTimeout(timeout);
        timeout = setTimeout(() => func.apply(this, args), delay);
    };
}


// =============================================================================
// === PAGE INITIALIZERS =======================================================
// =============================================================================

document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('attendance-form')) {
        initStudentPage();
    }
    if (document.querySelector('#start-session-btn, .end-session-btn')) {
        initControllerPage();
    }
    if (document.getElementById('attendance-table')) {
        initEditAttendancePage();
    }
});

function initStudentPage() {
    const attendanceForm = document.getElementById('attendance-form');
    if (!attendanceForm) return;

    const markButton = document.getElementById('mark-btn');
    const enrollmentInput = document.getElementById('enrollment_no');
    const timerElement = document.getElementById('timer-student');
    const presentList = document.getElementById('present-students-list');

    if (!window.activeSessionDataStudent || !window.activeSessionDataStudent.id) {
        if (markButton) markButton.disabled = true;
        return;
    }

    startRobustTimer(window.activeSessionDataStudent.end_time, timerElement);
    const liveListInterval = setInterval(() => fetchPresentStudents(window.activeSessionDataStudent.id, presentList), 10000);
    fetchPresentStudents(window.activeSessionDataStudent.id, presentList);

    enrollmentInput.addEventListener('input', debounce(fetchStudentName, 300));
    attendanceForm.addEventListener('submit', handleAttendanceSubmit);

    async function handleAttendanceSubmit(e) {
        e.preventDefault();
        markButton.disabled = true;
        markButton.textContent = 'Verifying Location...';
        showTroubleshootingTips(false);

        getAccurateLocation(
            async (position) => {
                markButton.textContent = 'Submitting...';
                const { latitude, longitude, accuracy } = position.coords;
                
                try {
                    const formData = new URLSearchParams({
                        enrollment_no: enrollmentInput.value.trim().toUpperCase(),
                        session_id: window.activeSessionDataStudent.id,
                        latitude: latitude,
                        longitude: longitude,
                        accuracy: accuracy 
                    });

                    const response = await fetch('/api/mark_attendance', {
                        method: 'POST',
                        body: formData,
                    });

                    const result = await response.json();
                    showStatusMessage(result.message, result.category);

                    if (result.success) {
                        attendanceForm.style.display = 'none';
                        fetchPresentStudents(window.activeSessionDataStudent.id, presentList);
                        clearInterval(liveListInterval);
                    } else {
                        markButton.disabled = false;
                        markButton.textContent = 'Mark My Attendance';
                        if (result.message.includes("away")) {
                             showTroubleshootingTips(true);
                        }
                    }
                } catch (error) {
                    showStatusMessage('A network error occurred. Please try again.', 'error');
                    markButton.disabled = false;
                    markButton.textContent = 'Mark My Attendance';
                }
            },
            (error) => {
                showStatusMessage(error, 'error');
                markButton.disabled = false;
                markButton.textContent = 'Mark My Attendance';
                showTroubleshootingTips(true);
            }
        );
    }
}

function initControllerPage() {
    const startButton = document.getElementById('start-session-btn');
    const endButton = document.querySelector('.end-session-btn');
    const timerElement = document.getElementById(`timer-${window.activeSessionData?.id}`);

    if (window.activeSessionData?.end_time && timerElement) {
        startRobustTimer(window.activeSessionData.end_time, timerElement);
    }

    if (startButton) {
        startButton.addEventListener('click', async () => {
            startButton.disabled = true;
            startButton.textContent = 'Getting Location...';
            // THIS IS LINE 126 from the error - now it will work
            showStatusMessage('Getting your location to start the session.', 'info');

            getAccurateLocation(
                async (position) => {
                    startButton.textContent = 'Starting Session...';
                    const { latitude, longitude } = position.coords;
                    try {
                        const response = await fetch('/api/start_session', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({ latitude, longitude }),
                        });
                        const result = await response.json();
                        showStatusMessage(result.message, result.category);
                        if (result.success) {
                            setTimeout(() => window.location.reload(), 1500);
                        } else {
                            startButton.disabled = false;
                            startButton.textContent = 'Start New Session';
                        }
                    } catch (error) {
                        showStatusMessage('A network error occurred.', 'error');
                        startButton.disabled = false;
                        startButton.textContent = 'Start New Session';
                    }
                },
                (error) => {
                    showStatusMessage(error, 'error');
                    startButton.disabled = false;
                    startButton.textContent = 'Start New Session';
                }
            );
        });
    }
    
    if(endButton) {
        endButton.addEventListener('click', async function() {
            this.disabled = true;
            const sessionId = this.dataset.sessionId;
            const response = await fetch(`/api/end_session/${sessionId}`, { method: 'POST' });
            const result = await response.json();
            showStatusMessage(result.message, 'info');
            setTimeout(() => window.location.reload(), 1500);
        });
    }
}

function initEditAttendancePage() {
    const table = document.getElementById('attendance-table');
    const tbody = table.querySelector('tbody');
    const attendanceDate = table.dataset.attendanceDate;

    fetch(`/api/get_students_for_edit/${attendanceDate}`)
        .then(response => response.json())
        .then(data => {
            if (data.success) {
                tbody.innerHTML = '';
                data.students.forEach(student => {
                    const row = `
                        <tr>
                            <td>${student.enrollment_no}</td>
                            <td>${student.name}</td>
                            <td>
                                <label class="switch">
                                    <input type="checkbox" class="attendance-toggle" data-student-id="${student.id}" ${student.is_present ? 'checked' : ''}>
                                    <span class="slider round"></span>
                                </label>
                            </td>
                        </tr>
                    `;
                    tbody.insertAdjacentHTML('beforeend', row);
                });

                document.querySelectorAll('.attendance-toggle').forEach(toggle => {
                    toggle.addEventListener('change', async (event) => {
                        const studentId = event.target.dataset.studentId;
                        const isPresent = event.target.checked;
                        try {
                            const response = await fetch('/api/update_daily_attendance', {
                                method: 'POST',
                                headers: { 'Content-Type': 'application/json' },
                                body: JSON.stringify({
                                    date: attendanceDate,
                                    student_id: studentId,
                                    is_present: isPresent,
                                }),
                            });
                            const result = await response.json();
                            showStatusMessage(result.message, result.success ? 'success' : 'error');
                        } catch {
                            showStatusMessage('Network error. Could not update.', 'error');
                            event.target.checked = !isPresent;
                        }
                    });
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="3" class="error">${data.message}</td></tr>`;
            }
        });
}

