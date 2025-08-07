// main.js
document.addEventListener('DOMContentLoaded', function() {
    const attendanceForm = document.getElementById('attendance-form');
    const enrollmentNoInput = document.getElementById('enrollment_no');
    const studentNameDisplay = document.getElementById('student-name-display');
    const markBtn = document.getElementById('mark-btn');
    const statusMessage = document.getElementById('status-message'); // For general messages if needed

    let activeSessionId = null; // Store the active session ID

    // Function to fetch active BA session ID
    async function fetchActiveBASession() {
        try {
            const response = await fetch('/api/get_active_ba_session');
            const data = await response.json();
            if (data.success && data.session_id) {
                activeSessionId = data.session_id;
                markBtn.disabled = false; // Enable button if session is active
                // Optionally update a visible session ID if you want to show it to students
                // For now, we'll just enable the button.
            } else {
                // No active session, keep button disabled and show message
                markBtn.disabled = true;
                if (statusMessage) {
                    statusMessage.textContent = data.message || 'No active BA attendance session found.';
                    statusMessage.className = 'error-message';
                }
            }
        } catch (error) {
            console.error('Error fetching active BA session:', error);
            markBtn.disabled = true;
            if (statusMessage) {
                statusMessage.textContent = 'Failed to load attendance session. Please try again later.';
                statusMessage.className = 'error-message';
            }
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
        attendanceForm.addEventListener('submit', function(e) {
            e.preventDefault();

            const enrollmentNo = enrollmentNoInput.value.trim();
            
            if (!enrollmentNo || !activeSessionId) {
                // Flash messages are handled by Flask after redirect, but for immediate feedback
                if (statusMessage) {
                    statusMessage.textContent = 'Please enter your enrollment number and ensure a session is active.';
                    statusMessage.className = 'error-message';
                }
                return;
            }

            // Step 1: Get user's geolocation
            if (statusMessage) {
                statusMessage.textContent = 'Fetching your location...';
                statusMessage.className = 'info-message';
            }

            if (navigator.geolocation) {
                navigator.geolocation.getCurrentPosition(
                    position => {
                        const { latitude, longitude } = position.coords;
                        
                        // Step 2: Submit attendance to the server
                        if (statusMessage) {
                            statusMessage.textContent = 'Location fetched. Submitting attendance...';
                            statusMessage.className = 'info-message';
                        }
                        
                        fetch('/mark_attendance', {
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
                        })
                        .then(response => {
                            // Flask redirects, so we just reload the page to see flash messages
                            window.location.reload(); 
                        })
                        .catch(error => {
                            console.error('Error submitting attendance:', error);
                            if (statusMessage) {
                                statusMessage.textContent = 'An error occurred during submission. Please try again.';
                                statusMessage.className = 'error-message';
                            }
                        });
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
                        if (statusMessage) {
                            statusMessage.textContent = errorMessage;
                            statusMessage.className = 'error-message';
                        }
                    },
                    { enableHighAccuracy: true, timeout: 10000, maximumAge: 0 } // Geolocation options
                );
            } else {
                if (statusMessage) {
                    statusMessage.textContent = 'Geolocation is not supported by your browser.';
                    statusMessage.className = 'error-message';
                }
            }
        });
    }
});
