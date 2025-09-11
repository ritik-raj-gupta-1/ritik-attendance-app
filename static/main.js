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
            studentNameDisplay.style.color = data.name ? 'var(--primary-blue)' : 'var(--danger-red)';
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
            if(document.body.contains(document.getElementById('attendance-form'))){
                 window.location.reload();
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
    // Determine which page is active and run its specific initializer
    if (document.getElementById('attendance-form')) {
        initStudentPage();
    }
    if (document.querySelector('.dashboard-content')) {
        // This will run on both dashboard and report pages if they share this class
        initControllerPage(); 
    }
    if (document.getElementById('attendance-table')) {
        initEditAttendancePage();
    }
    if(document.querySelector('.report-table-container')){
        initReportPage();
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
    const manualEditBtn = document.getElementById('manual-edit-btn');
    const manualEditModal = document.getElementById('manual-edit-modal');
    
    if (window.activeSessionData?.id) {
        const timerElement = document.getElementById(`timer-${window.activeSessionData.id}`);
        if(timerElement) startRobustTimer(window.activeSessionData.end_time, timerElement);
    }

    if (startButton) {
        startButton.addEventListener('click', async () => {
            startButton.disabled = true;
            startButton.textContent = 'Getting Location...';
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

    if(manualEditBtn && manualEditModal) {
        const closeButton = manualEditModal.querySelector('.close-button');
        const studentListContainer = manualEditModal.querySelector('.manual-student-list');

        manualEditBtn.addEventListener('click', async () => {
            const sessionId = manualEditBtn.dataset.sessionId;
            studentListContainer.innerHTML = '<p>Loading students...</p>';
            manualEditModal.style.display = 'block';
            // FIX: Add class to body to prevent background scrolling
            document.body.classList.add('modal-open');

            const response = await fetch(`/api/get_students_for_manual_edit/${sessionId}`);
            const data = await response.json();

            if(data.success) {
                studentListContainer.innerHTML = '';
                data.students.forEach(student => {
                    const studentDiv = document.createElement('div');
                    studentDiv.className = 'manual-student-item';
                    studentDiv.innerHTML = `
                        <span>${student.name} (${student.enrollment_no})</span>
                        <button class="button mark-manual-btn ${student.is_present ? 'button-secondary' : ''}" data-student-id="${student.id}" ${student.is_present ? 'disabled' : ''}>
                            ${student.is_present ? 'Present' : 'Mark Present'}
                        </button>
                    `;
                    studentListContainer.appendChild(studentDiv);
                });

                studentListContainer.querySelectorAll('.mark-manual-btn').forEach(btn => {
                    btn.addEventListener('click', async (e) => {
                        const studentId = e.target.dataset.studentId;
                        e.target.disabled = true;
                        e.target.textContent = 'Marking...';

                        const markResponse = await fetch('/api/manual_mark_attendance', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/json' },
                            body: JSON.stringify({
                                session_id: sessionId,
                                student_id: studentId
                            })
                        });
                        const markResult = await markResponse.json();
                        if(markResult.success) {
                             e.target.textContent = 'Present';
                             e.target.classList.add('button-secondary');
                        } else {
                            e.target.textContent = 'Error';
                            e.target.disabled = false;
                        }
                    });
                });
            } else {
                studentListContainer.innerHTML = `<p class="error">${data.message}</p>`;
            }
        });

        const closeModal = () => {
            manualEditModal.style.display = 'none';
            // FIX: Remove class from body to re-enable scrolling
            document.body.classList.remove('modal-open');
        };

        closeButton.addEventListener('click', closeModal);
        window.addEventListener('click', (event) => {
            if (event.target == manualEditModal) {
                closeModal();
            }
        });
    }
}

function initReportPage() {
    const deleteModal = document.getElementById('delete-confirmation-modal');
    if(!deleteModal) return;

    const closeButton = deleteModal.querySelector('.close-button');
    const confirmDeleteBtn = document.getElementById('confirm-delete-btn');
    const cancelDeleteBtn = document.getElementById('cancel-delete-btn');
    let dateToDelete = null;

    document.querySelectorAll('.delete-day-btn').forEach(button => {
        button.addEventListener('click', (e) => {
            dateToDelete = e.target.dataset.date;
            deleteModal.style.display = 'block';
            document.body.classList.add('modal-open');
        });
    });

    const closeModal = () => {
        deleteModal.style.display = 'none';
        document.body.classList.remove('modal-open');
    };
    
    closeButton.addEventListener('click', closeModal);
    cancelDeleteBtn.addEventListener('click', closeModal);
    window.addEventListener('click', (e) => {
        if(e.target == deleteModal) closeModal();
    });

    confirmDeleteBtn.addEventListener('click', async () => {
        confirmDeleteBtn.disabled = true;
        confirmDeleteBtn.textContent = 'Deleting...';

        const response = await fetch('/api/delete_day_records', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ date: dateToDelete })
        });
        const result = await response.json();
        showStatusMessage(result.message, result.success ? 'success' : 'error');
        if(result.success){
            setTimeout(() => window.location.reload(), 2000);
        } else {
            confirmDeleteBtn.disabled = false;
            confirmDeleteBtn.textContent = 'Confirm Delete';
        }
    });
}

function initEditAttendancePage() {
    const table = document.getElementById('attendance-table');
    if (!table) return;

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

