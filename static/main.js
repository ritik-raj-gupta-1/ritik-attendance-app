/**
 * Frontend logic for the B.A. Anthropology Attendance System.
 */
document.addEventListener('DOMContentLoaded', () => {
    if (document.getElementById('attendance-form')) initStudentPage();
    if (document.getElementById('start-session-btn') || document.querySelector('.end-session-btn')) initControllerPage();
    if (document.getElementById('attendance-table')) initEditAttendancePage();
});

// --- STUDENT PAGE ---
function initStudentPage() {
    const form = document.getElementById('attendance-form');
    const button = document.getElementById('mark-btn');
    if (!window.activeSessionDataStudent || !window.activeSessionDataStudent.id) {
        if (button) {
            button.disabled = true;
            button.textContent = 'No Active Session';
        }
        return;
    }
    form.addEventListener('submit', handleAttendanceSubmit);
}

async function handleAttendanceSubmit(e) {
    e.preventDefault();
    const button = document.getElementById('mark-btn');
    button.disabled = true;
    button.textContent = 'Verifying Location...';
    showStatusMessage('Please wait, getting your precise location.', 'info');

    if (!navigator.geolocation) {
        showStatusMessage('Geolocation is not supported by your browser.', 'error');
        button.disabled = false;
        button.textContent = 'Mark My Attendance';
        return;
    }

    navigator.geolocation.getCurrentPosition(
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
                if (result.success) document.getElementById('attendance-form').style.display = 'none';
                else {
                    button.disabled = false;
                    button.textContent = 'Mark My Attendance';
                }
            } catch (error) {
                showStatusMessage('A network error occurred.', 'error');
                button.disabled = false;
                button.textContent = 'Mark My Attendance';
            }
        },
        (geoError) => {
            let msg = geoError.code === 1 ? 'You must allow location access.' : `Geolocation Error: ${geoError.message}`;
            showStatusMessage(msg, 'error');
            button.disabled = false;
            button.textContent = 'Mark My Attendance';
        },
        { enableHighAccuracy: true, timeout: 15000, maximumAge: 0 }
    );
}

// --- CONTROLLER DASHBOARD ---
function initControllerPage() {
    const startBtn = document.getElementById('start-session-btn');
    const endBtns = document.querySelectorAll('.end-session-btn');

    if (startBtn) startBtn.addEventListener('click', startSessionHandler);
    endBtns.forEach(btn => btn.addEventListener('click', endSessionHandler));

    if (window.activeSessionData && window.activeSessionData.id) {
        let remaining = window.activeSessionData.remaining_time;
        const timerEl = document.getElementById(`timer-${window.activeSessionData.id}`);
        if (timerEl && remaining > 0) {
            const timer = setInterval(() => {
                remaining--;
                if (remaining <= 0) {
                    clearInterval(timer);
                    window.location.reload();
                }
                timerEl.textContent = `${Math.floor(remaining / 60)}m ${remaining % 60}s`;
            }, 1000);
        }
    }
}

async function startSessionHandler() {
    this.disabled = true;
    this.textContent = 'Getting Location...';
    showStatusMessage('Please allow location access to start the session.', 'info');

    navigator.geolocation.getCurrentPosition(async (position) => {
        this.textContent = 'Starting Session...';
        try {
            const response = await fetch('/api/start_session', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ latitude: position.coords.latitude, longitude: position.coords.longitude }),
            });
            const result = await response.json();
            showStatusMessage(result.message, result.success ? 'success' : 'error');
            if (result.success) setTimeout(() => window.location.reload(), 1500);
            else { this.disabled = false; this.textContent = 'Start New Session'; }
        } catch (error) {
            showStatusMessage('A network error occurred.', 'error');
            this.disabled = false; this.textContent = 'Start New Session';
        }
    }, (geoError) => {
        showStatusMessage(`Geolocation Error: ${geoError.message}`, 'error');
        this.disabled = false; this.textContent = 'Start New Session';
    });
}

async function endSessionHandler() {
    const sessionId = this.dataset.sessionId;
    if (!confirm('Are you sure you want to end this session?')) return;
    try {
        const response = await fetch(`/api/end_session/${sessionId}`, { method: 'POST' });
        const result = await response.json();
        showStatusMessage(result.message, result.success ? 'success' : 'info');
        if (result.success) setTimeout(() => window.location.reload(), 1500);
    } catch (error) {
        showStatusMessage('A network error occurred.', 'error');
    }
}

// --- EDIT ATTENDANCE PAGE ---
function initEditAttendancePage() {
    const table = document.getElementById('attendance-table');
    const date = table.dataset.attendanceDate;

    const fetchStudents = async () => {
        const response = await fetch(`/api/get_students_for_edit/${date}`);
        const data = await response.json();
        const tbody = table.querySelector('tbody');
        tbody.innerHTML = '';
        if (data.success) {
            data.students.forEach(s => {
                tbody.insertAdjacentHTML('beforeend', `<tr><td>${s.enrollment_no}</td><td>${s.name}</td><td><input type="checkbox" class="attendance-checkbox" data-student-id="${s.id}" ${s.is_present ? 'checked' : ''}></td></tr>`);
            });
        } else {
            tbody.innerHTML = `<tr><td colspan="3">${data.message}</td></tr>`;
        }
    };

    table.addEventListener('change', async (e) => {
        if (e.target.classList.contains('attendance-checkbox')) {
            try {
                const response = await fetch('/api/update_attendance', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ date: date, student_id: e.target.dataset.studentId, is_present: e.target.checked }),
                });
                const result = await response.json();
                showStatusMessage(result.message, result.success ? 'success' : 'error');
            } catch (error) {
                showStatusMessage('A network error occurred.', 'error');
            }
        }
    });

    fetchStudents();
}

// --- UTILITY ---
function showStatusMessage(message, type) {
    const el = document.getElementById('status-message');
    if (el) {
        el.textContent = message;
        el.className = `status-message ${type}`;
        el.style.display = 'block';
        setTimeout(() => { el.style.display = 'none'; }, 5000);
    }
}

