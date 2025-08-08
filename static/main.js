// static/main.js

// Fixed radius for GPS location check (in meters).
// This value will be sent to the backend for server-side validation.
const FIXED_RADIUS_METERS = 80; // The fixed radius for attendance marking

// DOM elements
const enrollmentNoInput = document.getElementById('enrollment_no');
const studentNameDisplay = document.getElementById('student-name-display');
const markAttendanceButton = document.getElementById('mark-btn');
const attendanceForm = document.getElementById('attendance-form');
const timerStudentSpan = document.getElementById('timer-student');

// Global status message div
const statusMessageDiv = document.getElementById('status-message');

// Custom Confirmation Modal Elements (present on admin_dashboard.html and attendance_report.html)
const confirmationModal = document.getElementById('confirmation-modal');
const confirmMessage = document.getElementById('confirm-message');
const confirmYesBtn = document.getElementById('confirm-yes');
const confirmNoBtn = document.getElementById('confirm-no');
const modalCloseBtn = confirmationModal ? confirmationModal.querySelector('.close-button') : null;

let pendingDeleteDate = null; // Stores the date to be deleted for confirmation modal

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
        statusMessageDiv.style.display = 'block'; // Ensure it's visible
        console.log(`Status (${type}): ${message}`);
        // Hide after 5 seconds for transient messages
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
        pendingDeleteDate = dataToConfirm; // Store the data
        confirmationModal.style.display = 'block';
        console.log('Confirmation modal shown for:', dataToConfirm);
    } else {
        console.error('Confirmation modal elements not found!');
    }
}

/**
 * Hides the custom confirmation modal.
 */
function hideConfirmationModal() {
    if (confirmationModal) {
        confirmationModal.style.display = 'none';
        console.log('Confirmation modal hidden.');
    }
}

// Attach event listeners for the confirmation modal
document.addEventListener('DOMContentLoaded', () => {
    if (modalCloseBtn) {
        modalCloseBtn.addEventListener('click', () => {
            pendingDeleteDate = null; // Clear if user closes via X
            hideConfirmationModal();
        });
        console.log('Modal close button listener attached.');
    }
    if (confirmNoBtn) {
        confirmNoBtn.addEventListener('click', () => {
            pendingDeleteDate = null; // Clear if user clicks No
            hideConfirmationModal();
        });
        console.log('Confirm No button listener attached.');
    }
    if (confirmYesBtn) {
        confirmYesBtn.addEventListener('click', async function() {
            console.log('--- CONFIRM YES BUTTON CLICKED ---');
            const dateToProcess = pendingDeleteDate; // Capture the date BEFORE hiding the modal
            hideConfirmationModal(); // This will log 'Confirmation modal hidden.'

            if (dateToProcess) { // Use the captured date
                console.log('Proceeding with deletion for date:', dateToProcess);
                await deleteDailyAttendance(dateToProcess);
            } else {
                console.warn('pendingDeleteDate was null at time of confirmation. Cannot proceed with deletion.');
            }
            pendingDeleteDate = null; // Clear after processing
        });
        console.log('Confirm Yes button listener attached.');
    } else {
        console.error('Confirm Yes button element not found on DOMContentLoaded!');
    }

    // Click outside modal to close
    window.addEventListener('click', function(event) {
        if (event.target == confirmationModal) {
            pendingDeleteDate = null; // Clear if user clicks outside
            hideConfirmationModal();
        }
    });

    // --- Controller Dashboard Logic ---

    // Event listener for "End Session" button
    document.querySelectorAll('.end-session-btn').forEach(button => {
        button.addEventListener('click', async function(e) {
            e.preventDefault(); // Prevent default form submission
            const sessionId = this.dataset.sessionId;
            
            console.log('End Session button clicked for session:', sessionId);
            showStatusMessage('Ending session...', 'info');
            try {
                const response = await fetch(`/end_session/${sessionId}`, {
                    method: 'POST'
                });
                const data = await response.json();
                if (data.success) {
                    showStatusMessage(data.message, data.category);
                    // Reload to update dashboard status after a short delay
                    setTimeout(() => window.location.reload(), 1000); 
                } else {
                    showStatusMessage(data.message, data.category);
                }
            } catch (error) {
                console.error('Error ending session:', error);
                showStatusMessage('An error occurred while ending the session.', 'error');
            }
        });
    });

    // Controller Dashboard Timer Logic
    // This runs only if window.activeSessionData is available (from admin_dashboard.html)
    if (typeof window.activeSessionData !== 'undefined' && window.activeSessionData && window.activeSessionData.id) {
        console.log('Active session data found for dashboard timer.');
        let remainingTimeController = window.activeSessionData.remaining_time;
        // Find the specific timer element for the active session ID
        let timerDisplayController = document.getElementById(`timer-${window.activeSessionData.id}`);

        if (timerDisplayController && remainingTimeController > 0) {
            let controllerTimer = setInterval(function() {
                let minutes = Math.floor(remainingTimeController / 60);
                let seconds = remainingTimeController % 60;
                timerDisplayController.innerHTML = `${minutes}m ${seconds}s`;

                if (remainingTimeController <= 0) {
                    clearInterval(controllerTimer);
                    timerDisplayController.innerHTML = "Session ended.";
                    window.location.reload(); // Reload to update dashboard status
                }
                remainingTimeController--;
            }, 1000);
        } else if (timerDisplayController) {
            timerDisplayController.innerHTML = "Session ended.";
        }
    }

    // --- Attendance Report Page Logic ---

    // Event listener for "Delete Day" buttons in the attendance report table
    // This listener is on document.body because buttons are dynamically loaded
    document.body.addEventListener('click', function(event) {
        if (event.target && event.target.classList.contains('delete-day-btn')) {
            const dateToDelete = event.target.dataset.date;
            console.log('Delete Day button clicked for date:', dateToDelete);
            showConfirmationModal(`Are you sure you want to delete all attendance records for ${dateToDelete}? This action cannot be undone.`, dateToDelete);
        }
    });

    /**
     * Sends an AJAX request to delete all attendance records for a specific date.
     * @param {string} date - The date (YYYY-MM-DD) for which to delete attendance.
     */
    async function deleteDailyAttendance(date) {
        showStatusMessage(`Deleting attendance for ${date}...`, 'info');
        console.log(`Attempting to delete attendance for date: ${date}`);
        try {
            const response = await fetch('/delete_daily_attendance', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ date: date })
            });
            
            console.log('Fetch response received:', response);
            
            if (!response.ok) {
                const errorData = await response.json(); // Assuming JSON error response
                console.error('HTTP error! Status:', response.status, 'Response data:', errorData);
                showStatusMessage(errorData.message || `Error: ${response.status} - Failed to delete.`, errorData.category || 'error');
                return;
            }

            const data = await response.json();
            console.log('Delete attendance API response data:', data);

            if (data.success) {
                showStatusMessage(data.message, data.category);
                // Reload the page to reflect the deletion
                setTimeout(() => window.location.reload(), 1000); 
            } else {
                showStatusMessage(data.message, data.category);
            }
        } catch (error) {
            console.error('Error during deleteDailyAttendance fetch:', error);
            showStatusMessage('An unexpected network error occurred during deletion. Please check your connection.', 'error');
        }
    }

    // --- Student Attendance Page Logic ---

    // Function to fetch active BA session ID for the student attendance page
    // This is now primarily handled by the server-side rendering in student_attendance.html
    // and `window.activeSessionDataStudent`. This API call is less critical now.
    async function fetchActiveBASession() {
        // Only run this if the activeSessionDataStudent was NOT provided by the server
        if (typeof window.activeSessionDataStudent === 'undefined' || !window.activeSessionDataStudent || !window.activeSessionDataStudent.id) {
            console.log('No active session data from server. Fetching active BA session for student page via API...');
            try {
                const response = await fetch('/api/get_active_ba_session');
                const data = await response.json();
                if (data.success && data.session_id) {
                    // Update window.activeSessionDataStudent if fetched via API
                    window.activeSessionDataStudent = { id: data.session_id, class_name: 'BA - Anthropology', remaining_time: 0 }; // Remaining time will be updated by timer
                    if (markAttendanceButton) markAttendanceButton.disabled = false; // Enable button if session is active
                    showStatusMessage('', 'info'); // Clear any previous status
                    console.log('Active session found via API:', data.session_id);
                } else {
                    if (markAttendanceButton) markAttendanceButton.disabled = true;
                    showStatusMessage(data.message || 'No active BA attendance session found.', 'error');
                    console.log('No active session found via API:', data.message);
                }
            } catch (error) {
                console.error('Error fetching active BA session:', error);
                if (markAttendanceButton) markAttendanceButton.disabled = true;
                showStatusMessage('Failed to load attendance session. Please try again later.', 'error');
            }
        }
    }

    // Call this on page load to check for active sessions (only for student page)
    if (attendanceForm) {
        // Initial check for active session data from server-side render
        // If not present, try fetching via API (fallback)
        if (typeof window.activeSessionDataStudent === 'undefined' || !window.activeSessionDataStudent || !window.activeSessionDataStudent.id) {
            fetchActiveBASession();
        }

        // Student page timer logic
        if (typeof window.activeSessionDataStudent !== 'undefined' && window.activeSessionDataStudent && window.activeSessionDataStudent.id) {
            console.log('Active session data found for student page timer.');
            let remainingTimeStudent = window.activeSessionDataStudent.remaining_time;
            
            if (timerStudentSpan && remainingTimeStudent > 0) {
                let studentTimer = setInterval(function() {
                    let minutes = Math.floor(remainingTimeStudent / 60);
                    let seconds = remainingTimeStudent % 60;
                    timerStudentSpan.innerHTML = `${minutes}m ${seconds}s`;

                    if (remainingTimeStudent <= 0) {
                        clearInterval(studentTimer);
                        timerStudentSpan.innerHTML = "Session ended.";
                        // Optionally disable mark button if session ends
                        if (markAttendanceButton) {
                            markAttendanceButton.disabled = true;
                            markAttendanceButton.textContent = "Session Expired";
                        }
                        if (enrollmentNoInput) {
                            enrollmentNoInput.disabled = true;
                        }
                        showStatusMessage('The attendance session has ended.', 'warning');
                    }
                    remainingTimeStudent--;
                }, 1000);
            } else if (timerStudentSpan) {
                timerStudentSpan.innerHTML = "No active session.";
            }
        } else {
             // If no active session from server, ensure button is disabled
            if (markAttendanceButton) {
                markAttendanceButton.disabled = true;
                markAttendanceButton.textContent = "No Active Session";
            }
        }
    }

    // Event listener for enrollment number input to display student name (student page)
    if (enrollmentNoInput) {
        enrollmentNoInput.addEventListener('input', async function() {
            const enrollmentNo = this.value.trim();
            if (enrollmentNo.length >= 5) { // Fetch name after a few characters
                console.log('Fetching student name for enrollment:', enrollmentNo);
                try {
                    const response = await fetch(`/api/get_student_name/${enrollmentNo}`);
                    const data = await response.json();
                    if (data.success && data.name) {
                        studentNameDisplay.textContent = `Name: ${data.name}`;
                        studentNameDisplay.style.color = '#0056b3';
                        console.log('Student name found:', data.name);
                    } else {
                        studentNameDisplay.textContent = data.message || 'Student not found.';
                        studentNameDisplay.style.color = '#dc3545';
                        console.log('Student name not found:', data.message);
                    }
                } catch (error) {
                    console.error('Error fetching student name:', error);
                    studentNameDisplay.textContent = 'Error fetching name.';
                    studentNameDisplay.style.color = '#dc3545';
                }
            } else {
                studentNameDisplay.textContent = '';
            }
        });
    }

    // Event listener for attendance form submission (student page)
    if (attendanceForm) {
        attendanceForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            console.log('Attendance form submitted.');

            const enrollmentNo = enrollmentNoInput.value.trim();
            const sessionId = window.activeSessionDataStudent ? window.activeSessionDataStudent.id : null;
            
            if (!enrollmentNo || !sessionId) {
                showStatusMessage('Please enter your enrollment number and ensure a session is active.', 'error');
                return;
            }

            // Disable button to prevent multiple submissions
            markAttendanceButton.disabled = true;
            markAttendanceButton.textContent = "Marking...";
            showStatusMessage('Getting your location...', 'info');
            console.log('Requesting geolocation...');

            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    async position => {
                        const { latitude, longitude } = position.coords;
                        console.log(`Geolocation obtained: Lat ${latitude}, Lon ${longitude}`);
                        
                        // Always use the FIXED_RADIUS_METERS for allowed_radius
                        const allowedRadius = FIXED_RADIUS_METERS;
                        console.log(`Using fixed allowed radius: ${allowedRadius}m`);

                        showStatusMessage('Location fetched. Submitting attendance...', 'info');
                        
                        try {
                            const response = await fetch('/mark_attendance', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/x-www-form-urlencoded',
                                },
                                body: new URLSearchParams({
                                    enrollment_no: enrollmentNo,
                                    session_id: sessionId,
                                    latitude: latitude,
                                    longitude: longitude,
                                    allowed_radius: allowedRadius // Send the fixed radius to the backend
                                })
                            });
                            const data = await response.json();
                            console.log('Attendance submission response:', data);

                            if (data.success) {
                                showStatusMessage(data.message, data.category);
                                enrollmentNoInput.value = ''; // Clear input on success
                                studentNameDisplay.textContent = ''; // Clear name display
                            } else {
                                showStatusMessage(data.message, data.category);
                            }
                        } catch (error) {
                            console.error('Error submitting attendance:', error);
                            showStatusMessage('An unexpected error occurred during submission. Please try again.', 'error');
                        } finally {
                            markAttendanceButton.disabled = false; // Re-enable button
                            markAttendanceButton.textContent = "Mark Attendance";
                        }
                    },
                    error => {
                        console.error('Geolocation Error:', error);
                        markAttendanceButton.disabled = false; // Re-enable button
                        markAttendanceButton.textContent = "Mark Attendance";
                        let errorMessage = 'Unable to fetch your location. Please enable location services.';
                        if (error.code === error.PERMISSION_DENIED) {
                            errorMessage = 'Location permission denied. Please allow location access to mark attendance.';
                        } else if (error.code === error.POSITION_UNAVAILABLE) {
                            errorMessage = 'Your location is currently unavailable. Please try again.';
                        } else if (error.code === error.TIMEOUT) {
                            errorMessage = 'Fetching location timed out. Please try again.';
                        }
                        showStatusMessage(errorMessage, 'error');
                    },
                    { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 } // Geolocation options
                );
            } else {
                showStatusMessage('Geolocation is not supported by your browser.', 'error');
                markAttendanceButton.disabled = false; // Re-enable button
                markAttendanceButton.textContent = "Mark Attendance";
            }
        });
    }

    // --- Edit Attendance Page Logic (for controller) ---
    const editAttendanceTable = document.getElementById('attendance-table'); 
    if (editAttendanceTable) {
        console.log('Edit Attendance page detected. Initializing...');
        const sessionId = editAttendanceTable.dataset.sessionId; // Get session ID from data attribute
        fetchStudentsForEdit(sessionId);
    }

    /**
     * Fetches student data for a specific session and populates the edit attendance table.
     * @param {string} sessionId - The ID of the session to fetch students for.
     */
    async function fetchStudentsForEdit(sessionId) {
        const loadingMessage = document.getElementById('loading-message');
        const errorMessage = document.getElementById('error-message');
        const tbody = editAttendanceTable.querySelector('tbody');

        if (loadingMessage) loadingMessage.style.display = 'block';
        if (errorMessage) errorMessage.style.display = 'none';
        tbody.innerHTML = '<tr><td colspan="3">Loading students...</td></tr>'; // Show loading in table
        console.log('Fetching students for session:', sessionId);

        try {
            const response = await fetch(`/api/get_session_students_for_edit/${sessionId}`);
            
            if (!response.ok) { // Check if response status is 2xx
                const errorData = await response.json(); // Assuming JSON error response
                console.error('HTTP error! Status:', response.status, 'Response data:', errorData);
                if (loadingMessage) loadingMessage.style.display = 'none';
                if (errorMessage) {
                    errorMessage.textContent = errorData.message || `Error: ${response.status} - Failed to load students.`;
                    errorMessage.style.display = 'block';
                }
                tbody.innerHTML = '<tr><td colspan="3">Failed to load students.</td></tr>'; // Update table on fetch error
                return;
            }

            const data = await response.json();
            console.log('Students for edit fetched (parsed JSON):', data);

            if (loadingMessage) loadingMessage.style.display = 'none';

            // Check if the API returned a success: false structure for errors from the backend
            if (data.success === false) {
                if (errorMessage) {
                    errorMessage.textContent = data.message || "Could not load students for editing.";
                    errorMessage.style.display = 'block';
                }
                tbody.innerHTML = '<tr><td colspan="3">Error: ' + (data.message || 'Could not load students.') + '</td></tr>'; // Update table on backend error
                return;
            }

            const students = data.students; // Access the 'students' array
            if (!students || students.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3">No BA students found or session data is unavailable.</td></tr>';
                return;
            }

            tbody.innerHTML = ''; // Clear loading message before populating
            students.forEach(student => {
                const row = tbody.insertRow();
                row.innerHTML = `
                    <td>${student.enrollment_no}</td>
                    <td>${student.name}</td>
                    <td>
                        <input type="checkbox" data-student-id="${student.id}" class="attendance-checkbox" ${student.is_present ? 'checked' : ''}>
                    </td>
                `;
            });

            // Add event listeners to checkboxes
            tbody.querySelectorAll('.attendance-checkbox').forEach(checkbox => {
                checkbox.addEventListener('change', async function() {
                    const studentId = this.dataset.studentId;
                    const isPresent = this.checked;
                    console.log(`Checkbox changed for student ${studentId}: isPresent = ${isPresent}`);
                    await updateAttendanceRecord(sessionId, studentId, isPresent, this); // Pass checkbox for revert
                });
            });

        } catch (error) {
            console.error('Error fetching students for edit (catch block):', error);
            if (loadingMessage) loadingMessage.style.display = 'none';
            if (errorMessage) {
                errorMessage.textContent = 'Failed to load student data: ' + error.message;
                errorMessage.style.display = 'block';
            }
            tbody.innerHTML = '<tr><td colspan="3">An unexpected error occurred.</td></tr>'; // Update table on JS error
        }
    }

    /**
     * Sends an AJAX request to update a single attendance record.
     * @param {string} sessionId - The ID of the session.
     * @param {string} studentId - The ID of the student.
     * @param {boolean} isPresent - True if marking present, false if marking absent.
     * @param {HTMLElement} checkboxElement - The checkbox element to revert its state on failure.
     */
    async function updateAttendanceRecord(sessionId, studentId, isPresent, checkboxElement) {
        showStatusMessage('Updating attendance...', 'info');
        console.log(`Updating attendance record for session ${sessionId}, student ${studentId}, present: ${isPresent}`);

        try {
            const response = await fetch('/api/update_attendance_record', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({
                    session_id: sessionId,
                    student_id: studentId,
                    is_present: isPresent
                })
            });
            const data = await response.json();
            console.log('Update attendance response:', data);

            if (data.success) {
                showStatusMessage(data.message, data.category);
            } else {
                showStatusMessage(data.message, data.category);
                if (checkboxElement) {
                    checkboxElement.checked = !isPresent; // Revert checkbox state on failure
                }
            }
        } catch (error) {
            console.error('Error updating attendance record:', error);
            showStatusMessage('An error occurred while updating the record.', 'error');
            if (checkboxElement) {
                checkboxElement.checked = !isPresent; // Revert checkbox state on error
            }
        }
    }
});
