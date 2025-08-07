// main.js
document.addEventListener('DOMContentLoaded', function() {
    const attendanceForm = document.getElementById('attendance-form');
    const enrollmentNoInput = document.getElementById('enrollment_no');
    const studentNameDisplay = document.getElementById('student-name-display');
    const markBtn = document.getElementById('mark-btn');
    const statusMessageDiv = document.getElementById('status-message'); // This div will display feedback

    // Custom Confirmation Modal Elements
    const confirmationModal = document.getElementById('confirmation-modal');
    const confirmMessage = document.getElementById('confirm-message');
    const confirmYesBtn = document.getElementById('confirm-yes');
    const confirmNoBtn = document.getElementById('confirm-no');
    const modalCloseBtn = document.querySelector('.close-button');

    let activeSessionId = null; // Store the active session ID
    let pendingDeleteDate = null; // Store the date to be deleted

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
        confirmMessage.textContent = message;
        pendingDeleteDate = dateToDelete; // Store the date for deletion
        confirmationModal.style.display = 'block';
    }

    // Function to hide the custom confirmation modal
    function hideConfirmationModal() {
        confirmationModal.style.display = 'none';
        pendingDeleteDate = null; // Clear pending date
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
    document.body.addEventListener('click', function(event) {
        if (event.target && event.target.classList.contains('delete-day-btn')) {
            const dateToDelete = event.target.dataset.date;
            showConfirmationModal(`Are you sure you want to delete all attendance records for ${dateToDelete}? This action cannot be undone.`, dateToDelete);
        }
    });


    // Function to fetch active BA session ID
    async function fetchActiveBASession() {
        try {
            const response = await fetch('/api/get_active_ba_session');
            const data = await response.json();
            if (data.success && data.session_id) {
                activeSessionId = data.session_id;
                if (markBtn) markBtn.disabled = false; // Enable button if session is active
                if (statusMessageDiv) {
                    statusMessageDiv.textContent = ''; // Clear any previous status
                    statusMessageDiv.style.display = 'none';
                }
            } else {
                if (markBtn) markBtn.disabled = true;
                showStatus(data.message || 'No active BA attendance session found.', 'error');
            }
        } catch (error) {
            console.error('Error fetching active BA session:', error);
            if (markBtn) markBtn.disabled = true;
            showStatus('Failed to load attendance session. Please try again later.', 'error');
        }
    }

    // Call this on page load to check for active sessions
    fetchActiveBASession();

    // Event listener for enrollment number input to display student name
    if (enrollmentNoInput) {
        enrollmentNoInput.addEventListener('input', async function() {
            const enrollmentNo = this.value.trim();
            if (enrollmentNo.length >= 5) { // Fetch name after a few characters
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
                    console.error('Error fetching student name:', error);
                    studentNameDisplay.textContent = 'Error fetching name.';
                    studentNameDisplay.style.color = '#dc3545';
                }
            } else {
                studentNameDisplay.textContent = '';
            }
        });
    }

    // Event listener for attendance form submission
    if (attendanceForm) {
        attendanceForm.addEventListener('submit', async function(e) {
            e.preventDefault();

            const enrollmentNo = enrollmentNoInput.value.trim();
            
            if (!enrollmentNo || !activeSessionId) {
                showStatus('Please enter your enrollment number and ensure a session is active.', 'error');
                return;
            }

            // Step 1: Get user's geolocation
            showStatus('Fetching your location...', 'info');

            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    async position => {
                        const { latitude, longitude } = position.coords;
                        
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
});
