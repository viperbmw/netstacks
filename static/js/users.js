$(document).ready(function() {
    // Load users on page load
    loadUsers();

    // Change password form submission
    $('#change-password-form').on('submit', function(e) {
        e.preventDefault();
        changePassword();
    });

    // Create user form submission
    $('#create-user-form').on('submit', function(e) {
        e.preventDefault();
        createUser();
    });
});

// Show status message
function showStatus(type, message) {
    const alertClass = type === 'success' ? 'alert-success' : 'alert-danger';
    const icon = type === 'success' ? 'fa-check-circle' : 'fa-exclamation-triangle';

    const alert = $(`
        <div class="alert ${alertClass} alert-dismissible fade show" role="alert">
            <i class="fas ${icon}"></i> ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `);

    $('#status-container').html(alert);

    // Auto-dismiss after 5 seconds
    setTimeout(function() {
        alert.alert('close');
    }, 5000);
}

// Load users list
function loadUsers() {
    $.get('/api/users')
        .done(function(response) {
            if (response.success) {
                // API returns users in response.data array
                renderUsers(response.data || []);
            } else {
                showStatus('error', 'Failed to load users: ' + (response.error || 'Unknown error'));
            }
        })
        .fail(function() {
            showStatus('error', 'Failed to load users');
        });
}

// Render users table
function renderUsers(users) {
    const tbody = $('#users-table-body');
    tbody.empty();

    if (users.length === 0) {
        tbody.html('<tr><td colspan="4" class="text-center">No users found</td></tr>');
        return;
    }

    users.forEach(function(user) {
        const createdAt = user.created_at ? new Date(user.created_at).toLocaleString() : 'Unknown';
        const isAdmin = user.username === 'admin';
        const authSource = user.auth_source || 'local';

        // Auth source badge
        let authBadge = '';
        if (authSource === 'local') {
            authBadge = '<span class="badge bg-success"><i class="fas fa-key"></i> Local</span>';
        } else if (authSource === 'ldap') {
            authBadge = '<span class="badge bg-info"><i class="fas fa-building"></i> LDAP</span>';
        } else if (authSource === 'oidc') {
            authBadge = '<span class="badge bg-warning text-dark"><i class="fas fa-shield-alt"></i> SSO</span>';
        }

        const row = $(`
            <tr>
                <td>
                    <i class="fas fa-user"></i> ${user.username}
                    ${isAdmin ? '<span class="badge bg-primary ms-2">Admin</span>' : ''}
                </td>
                <td>${authBadge}</td>
                <td>${createdAt}</td>
                <td>
                    ${!isAdmin ? `
                        <button class="btn btn-sm btn-danger" onclick="deleteUser('${user.username}')">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    ` : '<span class="text-muted">Cannot delete admin</span>'}
                </td>
            </tr>
        `);

        tbody.append(row);
    });
}

// Change password
function changePassword() {
    const currentPassword = $('#current-password').val();
    const newPassword = $('#new-password').val();
    const confirmPassword = $('#confirm-password').val();

    // Validate passwords match
    if (newPassword !== confirmPassword) {
        showStatus('error', 'New passwords do not match');
        return;
    }

    // Get current username from session (we'll need to pass it from the backend)
    // For now, we'll get it from the navbar
    const username = $('.nav-link.text-light').text().trim();

    $.ajax({
        url: '/api/users/' + encodeURIComponent(username) + '/password',
        method: 'PUT',
        contentType: 'application/json',
        data: JSON.stringify({
            current_password: currentPassword,
            new_password: newPassword
        })
    })
    .done(function(data) {
        if (data.success) {
            showStatus('success', data.message || 'Password changed successfully');
            $('#change-password-form')[0].reset();
        } else {
            showStatus('error', data.error || 'Failed to change password');
        }
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON?.error || 'Failed to change password';
        showStatus('error', error);
    });
}

// Create user
function createUser() {
    const username = $('#new-username').val().trim();
    const password = $('#new-user-password').val();
    const confirmPassword = $('#confirm-user-password').val();

    // Validate
    if (!username) {
        showStatus('error', 'Username is required');
        return;
    }

    if (password !== confirmPassword) {
        showStatus('error', 'Passwords do not match');
        return;
    }

    $.ajax({
        url: '/api/users',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            username: username,
            password: password
        })
    })
    .done(function(data) {
        if (data.success) {
            showStatus('success', data.message || 'User created successfully');
            $('#create-user-form')[0].reset();
            loadUsers(); // Reload users list
        } else {
            showStatus('error', data.error || 'Failed to create user');
        }
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON?.error || 'Failed to create user';
        showStatus('error', error);
    });
}

// Delete user
function deleteUser(username) {
    if (!confirm(`Are you sure you want to delete user "${username}"?`)) {
        return;
    }

    $.ajax({
        url: '/api/users/' + encodeURIComponent(username),
        method: 'DELETE'
    })
    .done(function(data) {
        if (data.success) {
            showStatus('success', data.message || 'User deleted successfully');
            loadUsers(); // Reload users list
        } else {
            showStatus('error', data.error || 'Failed to delete user');
        }
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON?.error || 'Failed to delete user';
        showStatus('error', error);
    });
}
