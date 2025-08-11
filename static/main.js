// static/main.js

// Fixed radius for GPS location check (in meters).
const FIXED_RADIUS_METERS = 80;

// DOM elements
const enrollmentNoInput = document.getElementById('enrollment_no');
const studentNameDisplay = document.getElementById('student-name-display');
const markAttendanceButton = document.getElementById('mark-btn');
const attendanceForm = document.getElementById('attendance-form');
const timerStudentSpan = document.getElementById('timer-student');

// Global status message div
const statusMessageDiv = document.getElementById('status-message');

// Custom Confirmation Modal Elements
const confirmationModal = document.getElementById('confirmation-modal');
const confirmMessage = document.getElementById('confirm-message');
const confirmYesBtn = document.getElementById('confirm-yes');
const confirmNoBtn = document.getElementById('confirm-no');
const modalCloseBtn = confirmationModal ? confirmationModal.querySelector('.close-button') : null;

let pendingDeleteDate = null;

/**
 * Displays a status message to the user.
 * @param {string} message - The message to display.
 * @param {string} type - 'success', 'error', 'info', or 'warning' for styling.
 */
function showStatusMessage(message, type) {
    if (statusMessageDiv) {
        statusMessageDiv.textContent = message;
        statusMessageDiv.className = 'status-message'; // Reset classes
        if (type) {
            statusMessageDiv.classList.add(type);
        }
        statusMessageDiv.style.display = 'block';
        setTimeout(() => {
            clearStatusMessage();
        }, 5000);
    }
}

/**
 * Clears the status message.
 */
function clearStatusMessage() {
    if (statusMessageDiv) {
        statusMessageDiv.textContent = '';
        statusMessageDiv.className = 'status-message';
        statusMessageDiv.style.display = 'none';
    }
}

/**
 * Shows the custom confirmation modal.
 * @param {string} message - The message to display in the modal.
 * @param {string} dataToConfirm - Data associated with the confirmation (e.g., date for deletion).
 */
function showConfirmationModal(message, dataToConfirm) {
    if (confirmationModal && confirmMessage) {
        confirmMessage.textContent = message;
        pendingDeleteDate = dataToConfirm;
        confirmationModal.style.display = 'block';
    }
}

/**
 * Hides the custom confirmation modal.
 */
function hideConfirmationModal() {
    if (confirmationModal) {
        confirmationModal.style.display = 'none';
    }
}

// Attach event listeners for the confirmation modal
document.addEventListener('DOMContentLoaded', () => {
    if (modalCloseBtn) {
        modalCloseBtn.addEventListener('click', () => {
            pendingDeleteDate = null;
            hideConfirmationModal();
        });
    }
    if (confirmNoBtn) {
        confirmNoBtn.addEventListener('click', () => {
            pendingDeleteDate = null;
            hideConfirmationModal();
        });
    }
    if (confirmYesBtn) {
        confirmYesBtn.addEventListener('click', async function() {
            const dateToProcess = pendingDeleteDate;
            hideConfirmationModal();
            if (dateToProcess) {
                await deleteDailyAttendance(dateToProcess);
            }
            pendingDeleteDate = null;
        });
    }

    window.addEventListener('click', function(event) {
        if (event.target == confirmationModal) {
            pendingDeleteDate = null;
            hideConfirmationModal();
        }
    });

    // --- Controller Dashboard Logic ---
    document.querySelectorAll('.end-session-btn').forEach(button => {
        button.addEventListener('click', async function(e) {
            e.preventDefault();
            const sessionId = this.dataset.sessionId;
            showStatusMessage('Ending session...', 'info');
            try {
                const response = await fetch(`/end_session/${sessionId}`, { method: 'POST' });
                const data = await response.json();
                showStatusMessage(data.message, data.category);
                if (data.success) {
                    setTimeout(() => window.location.reload(), 1000);
                }
            } catch (error) {
                showStatusMessage('An error occurred while ending the session.', 'error');
            }
        });
    });

    if (typeof window.activeSessionData !== 'undefined' && window.activeSessionData && window.activeSessionData.id) {
        let remainingTimeController = window.activeSessionData.remaining_time;
        let timerDisplayController = document.getElementById(`timer-${window.activeSessionData.id}`);
        if (timerDisplayController && remainingTimeController > 0) {
            let controllerTimer = setInterval(function() {
                remainingTimeController--;
                if (remainingTimeController <= 0) {
                    clearInterval(controllerTimer);
                    timerDisplayController.innerHTML = "Session ended.";
                    window.location.reload();
                }
                let minutes = Math.floor(remainingTimeController / 60);
                let seconds = remainingTimeController % 60;
                timerDisplayController.innerHTML = `${minutes}m ${seconds}s`;
            }, 1000);
        } else if (timerDisplayController) {
            timerDisplayController.innerHTML = "Session ended.";
        }
    }

    // --- Attendance Report Page Logic ---
    document.body.addEventListener('click', function(event) {
        if (event.target && event.target.classList.contains('delete-day-btn')) {
            const dateToDelete = event.target.dataset.date;
            showConfirmationModal(`Are you sure you want to delete all attendance records for ${dateToDelete}? This action cannot be undone.`, dateToDelete);
        }
    });

    async function deleteDailyAttendance(date) {
        showStatusMessage(`Deleting attendance for ${date}...`, 'info');
        try {
            const response = await fetch('/delete_daily_attendance', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ date: date })
            });
            if (!response.ok) {
                const errorData = await response.json();
                throw new Error(errorData.message || 'Failed to delete');
            }
            const data = await response.json();
            showStatusMessage(data.message, data.category);
            if (data.success) {
                setTimeout(() => window.location.reload(), 1000);
            }
        } catch (error) {
            showStatusMessage('An unexpected network error occurred during deletion.', 'error');
        }
    }

    // ==============================================================================
    // === THIS ENTIRE BLOCK FOR THE STUDENT PAGE HAS BEEN REPLACED AND UPGRADED ===
    // ==============================================================================
    if (attendanceForm) {
        const locationStatusDiv = document.getElementById('location-status');

        if (!window.activeSessionDataStudent || !window.activeSessionDataStudent.id) {
            if (markAttendanceButton) {
                markAttendanceButton.disabled = true;
                markAttendanceButton.textContent = "No Active Session";
            }
            return;
        }

        // --- Student Timer ---
        let remainingTimeStudent = window.activeSessionDataStudent.remaining_time;
        if (timerStudentSpan && remainingTimeStudent > 0) {
            let studentTimer = setInterval(function() {
                remainingTimeStudent--;
                if (remainingTimeStudent <= 0) {
                    clearInterval(studentTimer);
                    timerStudentSpan.innerHTML = "Session ended.";
                    if (markAttendanceButton) {
                        markAttendanceButton.disabled = true;
                        markAttendanceButton.textContent = "Session Expired";
                    }
                    if (enrollmentNoInput) enrollmentNoInput.disabled = true;
                    showStatusMessage('The attendance session has ended.', 'warning');
                }
                let minutes = Math.floor(remainingTimeStudent / 60);
                let seconds = remainingTimeStudent % 60;
                timerStudentSpan.innerHTML = `${minutes}m ${seconds}s`;
            }, 1000);
        }

        // --- NEW: On-load location check ---
        function checkLocationOnLoad() {
            if (!navigator.geolocation) {
                updateLocationStatus('Geolocation is not supported by your browser.', 'error');
                return;
            }
            navigator.geolocation.getCurrentPosition(
                (position) => {
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
                    updateLocationStatus('Could not get your location. Please grant permission and refresh.', 'error');
                },
                { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
            );
        }

        function updateLocationStatus(message, type) {
            locationStatusDiv.textContent = message;
            locationStatusDiv.className = `status-message ${type}`;
            locationStatusDiv.style.display = 'block';
        }

        checkLocationOnLoad();

        // --- Enrollment number name lookup ---
        enrollmentNoInput.addEventListener('input', async function() {
            const enrollmentNo = this.value.trim();
            if (enrollmentNo.length >= 5) {
                try {
                    const response = await fetch(`/api/get_student_name/${enrollmentNo}`);
                    const data = await response.json();
                    if (data.success && data.name) {
                        studentNameDisplay.textContent = `Name: ${data.name}`;
                        studentNameDisplay.style.color = '#0056b3';
                    } else {
                        studentNameDisplay.textContent = data.message || 'Student not found.';
                        studentNameDisplay.style.color = '#dc3545';
                    }
                } catch (error) {
                    studentNameDisplay.textContent = 'Error fetching name.';
                    studentNameDisplay.style.color = '#dc3545';
                }
            } else {
                studentNameDisplay.textContent = '';
            }
        });

        // --- NEW: Form submission with fingerprinting ---
        attendanceForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            const enrollmentNo = enrollmentNoInput.value.trim();
            const sessionId = window.activeSessionDataStudent.id;
            
            if (!enrollmentNo) {
                showStatusMessage('Please enter your enrollment number.', 'error');
                return;
            }

            markAttendanceButton.disabled = true;
            markAttendanceButton.textContent = "Processing...";
            showStatusMessage('Verifying device and location...', 'info');

            try {
                const fp = await FingerprintJS.load();
                const result = await fp.get();
                const visitorId = result.visitorId;

                navigator.geolocation.getCurrentPosition(
                    async (position) => {
                        const { latitude, longitude } = position.coords;
                        
                        const response = await fetch('/mark_attendance', {
                            method: 'POST',
                            headers: { 'Content-Type': 'application/x-www-form-urlencoded' },
                            body: new URLSearchParams({
                                enrollment_no: enrollmentNo,
                                session_id: sessionId,
                                latitude: latitude,
                                longitude: longitude,
                                device_fingerprint: visitorId
                            })
                        });
                        const data = await response.json();
                        showStatusMessage(data.message, data.category);

                        if (data.success) {
                            enrollmentNoInput.value = '';
                            studentNameDisplay.textContent = '';
                        }
                    },
                    (error) => {
                        showStatusMessage('Geolocation error: ' + error.message, 'error');
                    },
                    { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 }
                );
            } catch (error) {
                showStatusMessage('An unexpected error occurred.', 'error');
            } finally {
                markAttendanceButton.disabled = false;
                markAttendanceButton.textContent = "Mark Attendance";
            }
        });
    }

    // --- Edit Attendance Page Logic ---
    const editAttendanceTable = document.getElementById('attendance-table'); 
    if (editAttendanceTable) {
        const sessionId = editAttendanceTable.dataset.sessionId;
        fetchStudentsForEdit(sessionId);
    }

    async function fetchStudentsForEdit(sessionId) {
        const tbody = editAttendanceTable.querySelector('tbody');
        tbody.innerHTML = '<tr><td colspan="3">Loading students...</td></tr>';
        try {
            const response = await fetch(`/api/get_session_students_for_edit/${sessionId}`);
            const data = await response.json();

            if (!data.success || !data.students) {
                tbody.innerHTML = `<tr><td colspan="3">${data.message || 'Failed to load students.'}</td></tr>`;
                return;
            }

            tbody.innerHTML = '';
            data.students.forEach(student => {
                const row = tbody.insertRow();
                row.innerHTML = `
                    <td>${student.enrollment_no}</td>
                    <td>${student.name}</td>
                    <td>
                        <input type="checkbox" data-student-id="${student.id}" class="attendance-checkbox" ${student.is_present ? 'checked' : ''}>
                    </td>
                `;
            });

            tbody.querySelectorAll('.attendance-checkbox').forEach(checkbox => {
                checkbox.addEventListener('change', async function() {
                    const studentId = this.dataset.studentId;
                    const isPresent = this.checked;
                    await updateAttendanceRecord(sessionId, studentId, isPresent, this);
                });
            });

        } catch (error) {
            tbody.innerHTML = '<tr><td colspan="3">An unexpected error occurred.</td></tr>';
        }
    }

    async function updateAttendanceRecord(sessionId, studentId, isPresent, checkboxElement) {
        showStatusMessage('Updating attendance...', 'info');
        try {
            const response = await fetch('/api/update_attendance_record', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({
                    session_id: sessionId,
                    student_id: studentId,
                    is_present: isPresent
                })
            });
            const data = await response.json();
            showStatusMessage(data.message, data.success ? 'success' : 'error');
            if (!data.success) {
                checkboxElement.checked = !isPresent; // Revert on failure
            }
        } catch (error) {
            showStatusMessage('An error occurred while updating the record.', 'error');
            checkboxElement.checked = !isPresent;
        }
    }
});

// Utility function to calculate distance
function haversineDistance(lat1, lon1, lat2, lon2) {
    const R = 6371e3; // metres
    const φ1 = lat1 * Math.PI / 180;
    const φ2 = lat2 * Math.PI / 180;
    const Δφ = (lat2 - lat1) * Math.PI / 180;
    const Δλ = (lon2 - lon1) * Math.PI / 180;
    const a = Math.sin(Δφ / 2) * Math.sin(Δφ / 2) + Math.cos(φ1) * Math.cos(φ2) * Math.sin(Δλ / 2) * Math.sin(Δλ / 2);
    const c = 2 * Math.atan2(Math.sqrt(a), Math.sqrt(1 - a));
    return R * c;
}