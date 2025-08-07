// main.js
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded fired: main.js loaded');

    // Get common elements
    const attendanceForm = document.getElementById('attendance-form');
    const enrollmentNoInput = document.getElementById('enrollment_no');
    const studentNameDisplay = document.getElementById('student-name-display');
    const markBtn = document.getElementById('mark-btn');
    
    // Global status message div (present on admin_dashboard, attendance_report, edit_attendance, student_attendance)
    const statusMessageDiv = document.getElementById('status-message');

    // Custom Confirmation Modal Elements (present in admin_dashboard.html)
    const confirmationModal = document.getElementById('confirmation-modal');
    const confirmMessage = document.getElementById('confirm-message');
    const confirmYesBtn = document.getElementById('confirm-yes');
    const confirmNoBtn = document.getElementById('confirm-no');
    const modalCloseBtn = confirmationModal ? confirmationModal.querySelector('.close-button') : null;

    let activeSessionId = null; // Stores the active session ID for student attendance
    let pendingDeleteDate = null; // Stores the date to be deleted for confirmation modal

    /**
     * Displays a temporary status message to the user.
     * @param {string} message - The message to display.
     * @param {string} type - The type of message (e.g., 'info', 'success', 'warning', 'error').
     */
    function showStatus(message, type) {
        if (statusMessageDiv) {
            statusMessageDiv.textContent = message;
            statusMessageDiv.className = `status-message ${type}`; // Apply CSS class for styling
            statusMessageDiv.style.display = 'block';
            console.log(`Status (${type}): ${message}`); // Log status messages for debugging
            setTimeout(() => {
                statusMessageDiv.style.display = 'none';
                statusMessageDiv.textContent = ''; // Clear message after hiding
            }, 5000); // Hide after 5 seconds
        } else {
            console.warn('Status message div not found.');
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
            pendingDeleteDate = null; // Clear pending data
            console.log('Confirmation modal hidden.');
        }
    }

    // Attach event listeners for the confirmation modal
    if (modalCloseBtn) {
        modalCloseBtn.onclick = hideConfirmationModal;
    }
    if (confirmNoBtn) {
        confirmNoBtn.onclick = hideConfirmationModal;
    }
    if (confirmYesBtn) {
        confirmYesBtn.onclick = async function() {
            hideConfirmationModal();
            if (pendingDeleteDate) {
                console.log('Confirming action for:', pendingDeleteDate);
                // This is specifically for daily attendance deletion
                await deleteDailyAttendance(pendingDeleteDate);
            }
        };
    }

    // Click outside modal to close
    window.onclick = function(event) {
        if (event.target == confirmationModal) {
            hideConfirmationModal();
        }
    };

    // --- Controller Dashboard Logic ---

    // Event listener for "End Session" button
    document.querySelectorAll('.end-session-btn').forEach(button => {
        button.addEventListener('click', async function(e) {
            e.preventDefault(); // Prevent default form submission
            const sessionId = this.dataset.sessionId;
            
            console.log('End Session button clicked for session:', sessionId);
            showStatus('Ending session...', 'info');
            try {
                const response = await fetch(`/end_session/${sessionId}`, {
                    method: 'POST'
                });
                const data = await response.json();
                if (data.success) {
                    showStatus(data.message, 'success');
                    // Reload to update dashboard status after a short delay
                    setTimeout(() => window.location.reload(), 1000); 
                } else {
                    showStatus(data.message, 'error');
                }
            } catch (error) {
                console.error('Error ending session:', error);
                showStatus('An error occurred while ending the session.', 'error');
            }
        });
    });

    // Controller Dashboard Timer Logic
    // This runs only if window.activeSessionData is available (from admin_dashboard.html)
    if (typeof window.activeSessionData !== 'undefined' && window.activeSessionData && window.activeSessionData.id) {
        console.log('Active session data found for dashboard timer.');
        let remainingTimeController = window.activeSessionData.remaining_time;
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
        showStatus(`Deleting attendance for ${date}...`, 'info');
        try {
            const response = await fetch('/delete_daily_attendance', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json',
                },
                body: JSON.stringify({ date: date })
            });
            const data = await response.json();

            if (data.success) {
                showStatus(data.message, 'success');
                // Reload the page to reflect the deletion
                setTimeout(() => window.location.reload(), 1000); 
            } else {
                showStatus(data.message, 'error');
            }
        } catch (error) {
            console.error('Error deleting daily attendance:', error);
            showStatus('An error occurred during deletion. Please try again.', 'error');
        }
    }

    // --- Student Attendance Page Logic ---

    // Function to fetch active BA session ID for the student attendance page
    async function fetchActiveBASession() {
        // Only run this on the student attendance page if the form exists
        if (!attendanceForm) return; 
        console.log('Fetching active BA session for student page...');

        try {
            const response = await fetch('/api/get_active_ba_session');
            const data = await response.json();
            if (data.success && data.session_id) {
                activeSessionId = data.session_id;
                if (markBtn) markBtn.disabled = false; // Enable button if session is active
                showStatus('', 'info'); // Clear any previous status
                console.log('Active session found:', activeSessionId);
            } else {
                if (markBtn) markBtn.disabled = true;
                showStatus(data.message || 'No active BA attendance session found.', 'error');
                console.log('No active session found:', data.message);
            }
        } catch (error) {
            console.error('Error fetching active BA session:', error);
            if (markBtn) markBtn.disabled = true;
            showStatus('Failed to load attendance session. Please try again later.', 'error');
        }
    }

    // Call this on page load to check for active sessions (only for student page)
    if (attendanceForm) {
        fetchActiveBASession();

        // Student page timer logic
        if (typeof window.activeSessionDataStudent !== 'undefined' && window.activeSessionDataStudent && window.activeSessionDataStudent.id) {
            console.log('Active session data found for student page timer.');
            let remainingTimeStudent = window.activeSessionDataStudent.remaining_time;
            let timerDisplayStudent = document.getElementById('timer-student');

            if (timerDisplayStudent && remainingTimeStudent > 0) {
                let studentTimer = setInterval(function() {
                    let minutes = Math.floor(remainingTimeStudent / 60);
                    let seconds = remainingTimeStudent % 60;
                    timerDisplayStudent.innerHTML = `${minutes}m ${seconds}s`;

                    if (remainingTimeStudent <= 0) {
                        clearInterval(studentTimer);
                        timerDisplayStudent.innerHTML = "Session ended.";
                        // Optionally disable mark button if session ends
                        if (markBtn) markBtn.disabled = true;
                        showStatus('The attendance session has ended.', 'warning');
                    }
                    remainingTimeStudent--;
                }, 1000);
            } else if (timerDisplayStudent) {
                timerDisplayStudent.innerHTML = "No active session.";
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
            
            if (!enrollmentNo || !activeSessionId) {
                showStatus('Please enter your enrollment number and ensure a session is active.', 'error');
                return;
            }

            showStatus('Fetching your location...', 'info');
            console.log('Requesting geolocation...');

            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    async position => {
                        const { latitude, longitude } = position.coords;
                        console.log(`Geolocation obtained: Lat ${latitude}, Lon ${longitude}`);
                        
                        showStatus('Location fetched. Submitting attendance...', 'info');
                        
                        try {
                            const response = await fetch('/mark_attendance', {
                                method: 'POST',
                                headers: {
                                    'Content-Type': 'application/x-www-form-urlencoded',
                                },
                                body: new URLSearchParams({
                                    enrollment_no: enrollmentNo,
                                    session_id: activeSessionId,
                                    latitude: latitude,
                                    longitude: longitude
                                })
                            });
                            const data = await response.json();
                            console.log('Attendance submission response:', data);

                            if (data.success) {
                                showStatus(data.message, data.category);
                                enrollmentNoInput.value = ''; // Clear input on success
                                studentNameDisplay.textContent = ''; // Clear name display
                            } else {
                                showStatus(data.message, data.category);
                            }
                        } catch (error) {
                            console.error('Error submitting attendance:', error);
                            showStatus('An unexpected error occurred during submission. Please try again.', 'error');
                        }
                    },
                    error => {
                        console.error('Geolocation Error:', error);
                        let errorMessage = 'Unable to fetch your location. Please enable location services.';
                        if (error.code === error.PERMISSION_DENIED) {
                            errorMessage = 'Location permission denied. Please allow location access to mark attendance.';
                        } else if (error.code === error.POSITION_UNAVAILABLE) {
                            errorMessage = 'Your location is currently unavailable. Please try again.';
                        } else if (error.code === error.TIMEOUT) {
                            errorMessage = 'Fetching location timed out. Please try again.';
                        }
                        showStatus(errorMessage, 'error');
                    },
                    { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 } // Geolocation options
                );
            } else {
                showStatus('Geolocation is not supported by your browser.', 'error');
            }
        });
    }

    // --- Edit Attendance Page Logic (for controller) ---
    // Target the table by its ID 'attendance-table' as defined in edit_attendance.html
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
            console.log('Attempting fetch to /api/get_session_students_for_edit/' + sessionId);
            const response = await fetch(`/api/get_session_students_for_edit/${sessionId}`);
            console.log('Fetch response received:', response);

            if (!response.ok) { // Check if response status is 2xx
                const errorText = await response.text();
                console.error('HTTP error! Status:', response.status, 'Response text:', errorText);
                if (loadingMessage) loadingMessage.style.display = 'none';
                if (errorMessage) {
                    errorMessage.textContent = `Error fetching data: ${response.status} - ${errorText.substring(0, 100)}`;
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

            if (data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3">No BA students found or session data is unavailable.</td></tr>';
                return;
            }

            tbody.innerHTML = ''; // Clear loading message before populating
            data.forEach(student => {
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
        showStatus('Updating attendance...', 'info');
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
                showStatus(data.message, 'success');
            } else {
                showStatus(data.message, 'error');
                if (checkboxElement) {
                    checkboxElement.checked = !isPresent; // Revert checkbox state on failure
                }
            }
        } catch (error) {
            console.error('Error updating attendance record:', error);
            showStatus('An error occurred while updating the record.', 'error');
            if (checkboxElement) {
                checkboxElement.checked = !isPresent; // Revert checkbox state on error
            }
        }
    }
});
