// main.js
document.addEventListener('DOMContentLoaded', function() {
    console.log('DOMContentLoaded fired: main.js loaded');

    const attendanceForm = document.getElementById('attendance-form');
    const enrollmentNoInput = document.getElementById('enrollment_no');
    const studentNameDisplay = document.getElementById('student-name-display');
    const markBtn = document.getElementById('mark-btn');
    // Use a more general status message div that can be present on all pages
    const statusMessageDiv = document.getElementById('status-message') || document.createElement('div');
    if (!document.getElementById('status-message')) {
        statusMessageDiv.id = 'status-message';
        document.body.appendChild(statusMessageDiv); // Append to body if not found (e.g., student attendance page)
        statusMessageDiv.style.position = 'fixed';
        statusMessageDiv.style.top = '20px';
        statusMessageDiv.style.left = '50%';
        statusMessageDiv.style.transform = 'translateX(-50%)';
        statusMessageDiv.style.zIndex = '1001';
        statusMessageDiv.style.minWidth = '300px';
        statusMessageDiv.style.textAlign = 'center';
        statusMessageDiv.style.display = 'none'; // Hide by default
    }

    // Custom Confirmation Modal Elements (should be present in admin_dashboard.html)
    const confirmationModal = document.getElementById('confirmation-modal');
    const confirmMessage = document.getElementById('confirm-message');
    const confirmYesBtn = document.getElementById('confirm-yes');
    const confirmNoBtn = document.getElementById('confirm-no');
    const modalCloseBtn = document.querySelector('#confirmation-modal .close-button'); // More specific selector

    let activeSessionId = null; // Store the active session ID
    let pendingDeleteDate = null; // Store the date to be deleted for confirmation modal

    // Function to display a temporary status message
    function showStatus(message, type) {
        if (statusMessageDiv) {
            statusMessageDiv.textContent = message;
            statusMessageDiv.className = `status-message ${type}`; // Use CSS classes for styling
            statusMessageDiv.style.display = 'block';
            setTimeout(() => {
                statusMessageDiv.style.display = 'none';
            }, 5000); // Hide after 5 seconds
        }
    }

    // Function to show the custom confirmation modal
    function showConfirmationModal(message, dateToDelete) {
        if (confirmationModal && confirmMessage) {
            confirmMessage.textContent = message;
            pendingDeleteDate = dateToDelete; // Store the date for deletion
            confirmationModal.style.display = 'block';
            console.log('Confirmation modal shown for date:', dateToDelete); // Debug log
        } else {
            console.error('Confirmation modal elements not found!');
        }
    }

    // Function to hide the custom confirmation modal
    function hideConfirmationModal() {
        if (confirmationModal) {
            confirmationModal.style.display = 'none';
            pendingDeleteDate = null; // Clear pending date
            console.log('Confirmation modal hidden.'); // Debug log
        }
    }

    // Modal close button
    if (modalCloseBtn) {
        modalCloseBtn.onclick = hideConfirmationModal;
    }

    // Click outside modal to close
    window.onclick = function(event) {
        if (event.target == confirmationModal) {
            hideConfirmationModal();
        }
    };

    // Confirm Yes button handler
    if (confirmYesBtn) {
        confirmYesBtn.onclick = async function() {
            hideConfirmationModal();
            if (pendingDeleteDate) {
                console.log('Confirming delete for date:', pendingDeleteDate); // Debug log
                await deleteDailyAttendance(pendingDeleteDate);
            }
        };
    }

    // Confirm No button handler
    if (confirmNoBtn) {
        confirmNoBtn.onclick = hideConfirmationModal;
    }

    // Function to delete daily attendance
    async function deleteDailyAttendance(date) {
        showStatus('Deleting attendance for ' + date + '...', 'info');
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
                // Reload the page or update the table to reflect the deletion
                setTimeout(() => window.location.reload(), 1000); 
            } else {
                showStatus(data.message, 'error');
            }
        } catch (error) {
            console.error('Error deleting daily attendance:', error);
            showStatus('An error occurred during deletion. Please try again.', 'error');
        }
    }

    // Event listener for delete buttons in the attendance report table
    // This listener needs to be on document.body because the buttons are dynamically loaded
    document.body.addEventListener('click', function(event) {
        if (event.target && event.target.classList.contains('delete-day-btn')) {
            const dateToDelete = event.target.dataset.date;
            console.log('Delete Day button clicked for date:', dateToDelete); // Debug log
            showConfirmationModal(`Are you sure you want to delete all attendance records for ${dateToDelete}? This action cannot be undone.`, dateToDelete);
        }
    });

    // Function to handle ending an attendance session (for controller dashboard)
    // This is now directly called by the button in admin_dashboard.html
    document.querySelectorAll('.end-session-btn').forEach(button => {
        button.addEventListener('click', async function(e) {
            e.preventDefault(); // Prevent default form submission
            const sessionId = this.dataset.sessionId; // Get session ID from data attribute
            
            console.log('End Session button clicked for session:', sessionId); // Debug log
            showStatus('Ending session...', 'info');
            try {
                const response = await fetch(`/end_session/${sessionId}`, {
                    method: 'POST'
                });
                const data = await response.json();
                if (data.success) {
                    showStatus(data.message, 'success');
                    window.location.reload(); // Reload to show updated session status
                } else {
                    showStatus(data.message, 'error');
                }
            } catch (error) {
                console.error('Error ending session:', error);
                showStatus('An error occurred while ending the session.', 'error');
            }
        });
    });


    // Function to fetch active BA session ID (for student attendance page)
    async function fetchActiveBASession() {
        // Only run this on the student attendance page
        if (!attendanceForm) return; 
        console.log('Fetching active BA session for student page...'); // Debug log

        try {
            const response = await fetch('/api/get_active_ba_session');
            const data = await response.json();
            if (data.success && data.session_id) {
                activeSessionId = data.session_id;
                if (markBtn) markBtn.disabled = false; // Enable button if session is active
                showStatus('', 'info'); // Clear any previous status
                console.log('Active session found:', activeSessionId); // Debug log
            } else {
                if (markBtn) markBtn.disabled = true;
                showStatus(data.message || 'No active BA attendance session found.', 'error');
                console.log('No active session found:', data.message); // Debug log
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
    }

    // Event listener for enrollment number input to display student name (for student attendance page)
    if (enrollmentNoInput) {
        enrollmentNoInput.addEventListener('input', async function() {
            const enrollmentNo = this.value.trim();
            if (enrollmentNo.length >= 5) { // Fetch name after a few characters
                console.log('Fetching student name for enrollment:', enrollmentNo); // Debug log
                try {
                    const response = await fetch(`/api/get_student_name/${enrollmentNo}`);
                    const data = await response.json();
                    if (data.success && data.name) {
                        studentNameDisplay.textContent = `Name: ${data.name}`;
                        studentNameDisplay.style.color = '#0056b3';
                        console.log('Student name found:', data.name); // Debug log
                    } else {
                        studentNameDisplay.textContent = data.message || 'Student not found.';
                        studentNameDisplay.style.color = '#dc3545';
                        console.log('Student name not found:', data.message); // Debug log
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

    // Event listener for attendance form submission (for student attendance page)
    if (attendanceForm) {
        attendanceForm.addEventListener('submit', async function(e) {
            e.preventDefault();
            console.log('Attendance form submitted.'); // Debug log

            const enrollmentNo = enrollmentNoInput.value.trim();
            
            if (!enrollmentNo || !activeSessionId) {
                showStatus('Please enter your enrollment number and ensure a session is active.', 'error');
                return;
            }

            // Step 1: Get user's geolocation
            showStatus('Fetching your location...', 'info');
            console.log('Requesting geolocation...'); // Debug log

            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    async position => {
                        const { latitude, longitude } = position.coords;
                        console.log(`Geolocation obtained: Lat ${latitude}, Lon ${longitude}`); // Debug log
                        
                        // Step 2: Submit attendance to the server
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
                            const data = await response.json(); // Expect JSON response
                            console.log('Attendance submission response:', data); // Debug log

                            if (data.success) {
                                showStatus(data.message, data.category); // e.g., "Attendance marked successfully!", "success"
                                enrollmentNoInput.value = ''; // Clear input on success
                                studentNameDisplay.textContent = ''; // Clear name display
                            } else {
                                showStatus(data.message, data.category); // e.g., "Not on location!", "error"
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
    // Correctly target the table by its ID 'attendance-table' as defined in edit_attendance.html
    const editAttendanceTable = document.getElementById('attendance-table'); 
    if (editAttendanceTable) {
        console.log('Edit Attendance page detected. Initializing...'); // Debug log
        const sessionId = editAttendanceTable.dataset.sessionId; // This data-sessionId is set in the HTML
        fetchStudentsForEdit(sessionId);
    }

    async function fetchStudentsForEdit(sessionId) {
        const loadingMessage = document.getElementById('loading-message');
        const errorMessage = document.getElementById('error-message');
        const tbody = editAttendanceTable.querySelector('tbody');

        if (loadingMessage) loadingMessage.style.display = 'block';
        if (errorMessage) errorMessage.style.display = 'none';
        tbody.innerHTML = ''; // Clear existing rows
        console.log('Fetching students for session:', sessionId); // Debug log

        try {
            console.log('Attempting fetch to /api/get_session_students_for_edit/' + sessionId); // New debug log
            const response = await fetch(`/api/get_session_students_for_edit/${sessionId}`);
            console.log('Fetch response received:', response); // New debug log

            if (!response.ok) { // Check if response status is 2xx
                const errorText = await response.text();
                console.error('HTTP error! Status:', response.status, 'Response text:', errorText);
                if (loadingMessage) loadingMessage.style.display = 'none';
                if (errorMessage) {
                    errorMessage.textContent = `Error fetching data: ${response.status} - ${errorText.substring(0, 100)}`;
                    errorMessage.style.display = 'block';
                }
                return;
            }

            const data = await response.json();
            console.log('Students for edit fetched (parsed JSON):', data); // Debug log

            if (loadingMessage) loadingMessage.style.display = 'none';

            // Check if the API returned a success: false structure for errors from the backend
            if (data.success === false) {
                if (errorMessage) {
                    errorMessage.textContent = data.message || "Could not load students for editing.";
                    errorMessage.style.display = 'block';
                }
                return;
            }

            if (data.length === 0) {
                tbody.innerHTML = '<tr><td colspan="3">No BA students found or session data is unavailable.</td></tr>';
                return;
            }

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
                    console.log(`Checkbox changed for student ${studentId}: isPresent = ${isPresent}`); // Debug log
                    await updateAttendanceRecord(sessionId, studentId, isPresent, this); // Pass checkbox for revert
                });
            });

        } catch (error) {
            console.error('Error fetching students for edit (catch block):', error); // Debug log
            if (loadingMessage) loadingMessage.style.display = 'none';
            if (errorMessage) {
                errorMessage.textContent = 'Failed to load student data: ' + error.message;
                errorMessage.style.display = 'block';
            }
        }
    }

    async function updateAttendanceRecord(sessionId, studentId, isPresent, checkboxElement) {
        const updateStatus = document.getElementById('status-message'); // Use the global status message div
        if (updateStatus) showStatus('Updating attendance...', 'info');
        console.log(`Updating attendance record for session ${sessionId}, student ${studentId}, present: ${isPresent}`); // Debug log

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
            console.log('Update attendance response:', data); // Debug log

            if (data.success) {
                if (updateStatus) showStatus(data.message, 'success');
            } else {
                if (updateStatus) showStatus(data.message, 'error');
                if (checkboxElement) {
                    checkboxElement.checked = !isPresent; // Revert checkbox state on failure
                }
            }
        } catch (error) {
            console.error('Error updating attendance record:', error);
            if (updateStatus) showStatus('An error occurred while updating the record.', 'error');
            if (checkboxElement) {
                checkboxElement.checked = !isPresent; // Revert checkbox state on error
            }
        }
    }

    // --- Controller Dashboard Timer Logic ---
    // This runs only if window.activeSessionData is available (from admin_dashboard.html)
    if (window.activeSessionData && window.activeSessionData.id) {
        console.log('Active session data found for dashboard timer.'); // Debug log
        let remainingTimeController = window.activeSessionData.remaining_time;
        let timerDisplayController = document.getElementById(`timer-${window.activeSessionData.id}`);

        if (timerDisplayController && remainingTimeController > 0) {
            let controllerTimer = setInterval(function() {
                let minutes = Math.floor(remainingTimeController / 60);
                let seconds = remainingTimeController % 60;
                timerDisplayController.innerHTML = minutes + "m " + seconds + "s";

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
});
