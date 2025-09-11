/**
 * Upgraded Frontend logic for the B.A. Anthropology Attendance System.
 * Handles student submissions, controller actions, and professional editing.
 */
document.addEventListener('DOMContentLoaded', () => {
    // Initialize logic based on the current page's content
    if (document.getElementById('attendance-form')) initStudentPage();
    if (document.getElementById('start-session-btn') || document.querySelector('.end-session-btn')) initControllerPage();
    if (document.getElementById('attendance-table')) initEditAttendancePage();
});

// --- UTILITY FUNCTIONS ---

/**
 * Delays the execution of a function until after a specified time has passed since the last time it was invoked.
 * @param {Function} func The function to debounce.
 * @param {number} delay The delay in milliseconds.
 * @returns {Function} The debounced function.
 */
const debounce = (func, delay) => {
    let timeout;
    return (...args) => {
        clearTimeout(timeout);
        timeout = setTimeout(() => func(...args), delay);
    };
};

/**
 * Displays a temporary status message to the user.
 * @param {string} message The message to display.
 * @param {string} type The category ('success', 'error', 'info').
 * @param {number} [duration=6000] The duration in milliseconds.
 */
function showStatusMessage(message, type, duration = 6000) {
    const el = document.getElementById('status-message');
    if (el) {
        el.textContent = message;
        el.className = `status-message ${type}`;
        el.style.display = 'block';
        setTimeout(() => {
            el.style.display = 'none';
        }, duration);
    }
}

/**
 * Creates a robust countdown timer that resists browser tab throttling.
 * @param {string} endTimeISO - The end time as an ISO 8601 string.
 * @param {HTMLElement} timerElement - The element to display the timer in.
 * @returns {number} The interval ID for the timer.
 */
function startRobustTimer(endTimeISO, timerElement) {
    if (!endTimeISO || !timerElement) return;
    const endTime = new Date(endTimeISO).getTime();

    const updateTimer = () => {
        const remaining = Math.round((endTime - Date.now()) / 1000);
        if (remaining <= 0) {
            clearInterval(timerInterval);
            timerElement.textContent = "Session has ended.";
            // If on the student page, hide the form
            const form = document.getElementById('attendance-form');
            if (form) form.style.display = 'none';
        } else {
            const minutes = Math.floor(remaining / 60);
            const seconds = remaining % 60;
            timerElement.textContent = `${minutes}m ${seconds.toString().padStart(2, '0')}s remaining`;
        }
    };

    const timerInterval = setInterval(updateTimer, 1000);
    updateTimer(); // Initial call to display immediately
    return timerInterval;
}


// --- STUDENT PAGE LOGIC ---

function initStudentPage() {
    // Ensure there is an active session before setting up event listeners
    if (!window.activeSessionDataStudent || !window.activeSessionDataStudent.id) return;
    
    const form = document.getElementById('attendance-form');
    const enrollmentInput = document.getElementById('enrollment_no');

    enrollmentInput.addEventListener('input', debounce(verifyStudentName, 350));
    startLiveAttendanceList(window.activeSessionDataStudent.id);
    startRobustTimer(window.activeSessionDataStudent.end_time, document.getElementById('timer-student'));
    form.addEventListener('submit', handleAttendanceSubmit);
}

async function verifyStudentName() {
    const enrollmentNo = document.getElementById('enrollment_no').value;
    const nameDisplay = document.getElementById('student-name-display');
    if (enrollmentNo.length < 5) {
        nameDisplay.textContent = '';
        return;
    }
    nameDisplay.textContent = 'Verifying...';
    try {
        const response = await fetch(`/api/get_student_name/${enrollmentNo}`);
        const result = await response.json();
        nameDisplay.textContent = result.name;
        nameDisplay.style.color = result.success ? 'green' : 'red';
    } catch (error) {
        nameDisplay.textContent = 'Network error.';
        nameDisplay.style.color = 'red';
    }
}

function startLiveAttendanceList(sessionId) {
    const listContainer = document.getElementById('present-students-list');
    if (!listContainer) return;
    
    const fetchAndUpdateList = async () => {
        try {
            const response = await fetch(`/api/get_present_students/${sessionId}`);
            const result = await response.json();
            const listElement = listContainer.querySelector('ul');
            const titleElement = listContainer.querySelector('h4');
            listElement.innerHTML = ''; // Clear previous list
            
            if (result.success && result.students.length > 0) {
                titleElement.style.display = 'block';
                result.students.forEach(s => {
                    const li = document.createElement('li');
                    li.textContent = `${s.enrollment_no} - ${s.name}`;
                    listElement.appendChild(li);
                });
            } else {
                titleElement.style.display = 'none';
            }
        } catch (error) {
            console.error('Failed to fetch present students:', error);
        }
    };

    fetchAndUpdateList(); // Initial fetch
    // Set up polling to refresh the list every 10 seconds
    window.attendanceListPoller = setInterval(fetchAndUpdateList, 10000);
}

async function handleAttendanceSubmit(e) {
    e.preventDefault();
    const button = document.getElementById('mark-btn');
    button.disabled = true;
    button.textContent = 'Getting Precise Location...';
    showStatusMessage('Please wait, getting your precise location. This may take up to 25 seconds.', 'info');

    navigator.geolocation.getCurrentPosition(
        // Success callback
        async (position) => {
            button.textContent = 'Submitting...';
            try {
                const formData = new URLSearchParams({
                    enrollment_no: document.getElementById('enrollment_no').value,
                    session_id: window.activeSessionDataStudent.id,
                    latitude: position.coords.latitude,
                    longitude: position.coords.longitude,
                });
                const response = await fetch('/api/mark_attendance', { method: 'POST', body: formData });
                const result = await response.json();
                showStatusMessage(result.message, result.success ? 'success' : 'error');

                if (result.success) {
                    document.getElementById('attendance-form').style.display = 'none';
                    // Immediately refresh the present list for instant feedback
                    if (window.attendanceListPoller) clearInterval(window.attendanceListPoller);
                    setTimeout(() => startLiveAttendanceList(window.activeSessionDataStudent.id), 500);
                } else {
                    button.disabled = false;
                    button.textContent = 'Mark My Attendance';
                }
            } catch (error) {
                showStatusMessage('A network error occurred during submission.', 'error');
                button.disabled = false;
                button.textContent = 'Mark My Attendance';
            }
        },
        // Error callback
        (geoError) => {
            let message = 'Geolocation Error: ' + geoError.message;
            if (geoError.code === 1) message = 'You must allow location access to mark attendance.';
            if (geoError.code === 3) message = 'Could not get location in time. Please try again from a clear area.';
            showStatusMessage(message, 'error');
            button.disabled = false;
            button.textContent = 'Mark My Attendance';
        },
        // Geolocation options for high accuracy and longer timeout
        { enableHighAccuracy: true, timeout: 25000, maximumAge: 0 }
    );
}

// --- CONTROLLER & EDIT PAGE LOGIC ---

function initControllerPage() {
    const startButton = document.getElementById('start-session-btn');
    if (startButton) startButton.addEventListener('click', handleStartSession);

    if (window.activeSessionData && window.activeSessionData.end_time) {
        startRobustTimer(window.activeSessionData.end_time, document.querySelector('[id^="timer-"]'));
        document.querySelectorAll('.end-session-btn').forEach(btn => btn.addEventListener('click', handleEndSession));
    }
}

function handleStartSession() {
    const button = this;
    button.disabled = true;
    button.textContent = 'Getting Location...';

    navigator.geolocation.getCurrentPosition(
        async (position) => {
            button.textContent = 'Starting Session...';
            try {
                const response = await fetch('/api/start_session', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ latitude: position.coords.latitude, longitude: position.coords.longitude }),
                });
                const result = await response.json();
                showStatusMessage(result.message, result.success ? 'success' : 'error');
                if(result.success) setTimeout(() => window.location.reload(), 1500);
                else { button.disabled = false; button.textContent = 'Start New Session'; }
            } catch (error) {
                showStatusMessage('Network error starting session.', 'error');
                button.disabled = false; button.textContent = 'Start New Session';
            }
        },
        (geoError) => {
            showStatusMessage('Geolocation Error: ' + geoError.message, 'error');
            button.disabled = false; button.textContent = 'Start New Session';
        },
        { enableHighAccuracy: true, timeout: 25000, maximumAge: 0 }
    );
}

async function handleEndSession() {
    const sessionId = this.dataset.sessionId;
    this.disabled = true;
    this.textContent = 'Ending...';
    try {
        await fetch(`/api/end_session/${sessionId}`, { method: 'POST' });
        window.location.reload();
    } catch(error) {
        showStatusMessage('Failed to end session.', 'error');
        this.disabled = false;
        this.textContent = 'End Session Now';
    }
}

function initEditAttendancePage() {
    const table = document.getElementById('attendance-table');
    const date = table.dataset.attendanceDate;
    const tbody = table.querySelector('tbody');

    fetch(`/api/get_students_for_day_edit/${date}`)
        .then(res => res.json())
        .then(data => {
            tbody.innerHTML = '';
            if (data.success) {
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
                    toggle.addEventListener('change', handleAttendanceToggle);
                });
            } else {
                tbody.innerHTML = `<tr><td colspan="3">${data.message}</td></tr>`;
            }
        });
}

async function handleAttendanceToggle() {
    const studentId = this.dataset.studentId;
    const isPresent = this.checked;
    const date = document.getElementById('attendance-table').dataset.attendanceDate;

    try {
        const response = await fetch('/api/update_daily_attendance', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ date, student_id: studentId, is_present: isPresent }),
        });
        const result = await response.json();
        // Use a shorter duration for the status message for a snappier feel
        showStatusMessage(result.message, result.success ? 'success' : 'error', 3000);
    } catch (error) {
        showStatusMessage('Network error updating attendance.', 'error');
        this.checked = !this.checked; // Revert the toggle on error
    }
}

