// Dashboard JavaScript for NetStacks

// Global variable to store all tasks for search
let allTasks = [];

$(document).ready(function() {
    loadDashboard();

    // Refresh every 10 seconds
    setInterval(loadDashboard, 10000);

    // Task search functionality
    $('#task-search').on('keyup', function() {
        const searchTerm = $(this).val().toLowerCase();
        filterTasks(searchTerm);
    });

    // Clear search button
    $('#task-search-clear').on('click', function() {
        $('#task-search').val('');
        filterTasks('');
    });

    // Task row click handler
    $(document).on('click', '.task-row', function() {
        const taskId = $(this).data('task-id');
        showTaskResults(taskId);
    });

    // View deployed stack button handler
    $(document).on('click', '.view-deployed-stack-btn', function() {
        const stackId = $(this).data('stack-id');
        window.location.href = `/service-stacks?view=${stackId}`;
    });
});

function loadDashboard() {
    loadWorkerCount();
    loadDevicesList();
    loadTasks();
    loadDeviceCount();
    loadScheduledTasks();
    loadCompletedSchedules();
    loadServiceStacksSummary();
    loadBackupSchedule();
    loadAgentsSummary();
    loadAlertsSummary();
}

function loadWorkerCount() {
    $.get('/api/workers')
        .done(function(data) {
            // Filter out offline placeholder workers
            let onlineWorkers = 0;
            if (Array.isArray(data)) {
                onlineWorkers = data.filter(w => w.status === 'online').length;
            }
            $('#worker-count').text(onlineWorkers);
        })
        .fail(function() {
            $('#worker-count').text('?');
        });
}

function loadDevicesList() {
    // Get filters from settings
    let filters = [];
    try {
        const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
        filters = settings.netbox_filters || [];
    } catch (e) {
        console.error('Error reading filters from settings:', e);
    }

    // Make POST request with filters
    $.ajax({
        url: '/api/devices',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ filters: filters })
    })
        .done(function(data) {
            const devicesListBody = $('#devices-list-body');
            devicesListBody.empty();

            // Handle both response formats: data.devices (legacy) or data.data.devices (microservice)
            const devices = data.devices || (data.data && data.data.devices) || [];

            if (data.success && devices.length > 0) {
                // Show first 30 devices
                devices.slice(0, 30).forEach(function(device) {
                    devicesListBody.append(`
                        <a href="/deploy" class="list-group-item list-group-item-action py-2">
                            <i class="fas fa-server text-primary"></i> ${device.name}
                        </a>
                    `);
                });

                $('#devices-list-loading').hide();
                $('#devices-list-container').show();
            } else {
                devicesListBody.html('<p class="text-center text-muted mb-0">No devices found</p>');
                $('#devices-list-loading').hide();
                $('#devices-list-container').show();
            }
        })
        .fail(function() {
            $('#devices-list-body').html('<p class="text-center text-danger mb-0">Error loading devices</p>');
            $('#devices-list-loading').hide();
            $('#devices-list-container').show();
        });
}

function loadTasks() {
    // Fetch task metadata first
    $.get('/api/tasks/metadata')
        .done(function(metadataResponse) {
            const metadata = metadataResponse.metadata || {};

            $.get('/api/tasks')
                .done(function(data) {
                    // API returns: {status: 'success', data: {task_id: ['id1', 'id2']}}
                    let taskIds = [];
                    if (data.data && data.data.task_id && Array.isArray(data.data.task_id)) {
                        taskIds = data.data.task_id;
                    }

                    if (taskIds.length === 0) {
                        $('#queued-count').text(0);
                        $('#running-count').text(0);
                        $('#recent-tasks-body').html('<tr><td colspan="3" class="text-center text-muted">No recent tasks</td></tr>');
                        $('#recent-tasks-loading').hide();
                        $('#recent-tasks-container').show();
                        return;
                    }

                    let queuedCount = 0;
                    let runningCount = 0;
                    const recentTasks = [];
                    let fetchedCount = 0;

                    // Fetch details for first 50 tasks (for search)
                    taskIds.slice(0, 50).forEach(function(taskId) {
                        $.get('/api/tasks/' + taskId)
                            .done(function(taskResponse) {
                                const task = taskResponse.data || taskResponse;
                                const status = task.task_status || task.status || 'unknown';

                                fetchedCount++;

                                // Count by status (handle both Celery and custom status names)
                                const statusLower = status.toLowerCase();
                                if (statusLower === 'queued' || statusLower === 'pending') queuedCount++;
                                else if (statusLower === 'started' || statusLower === 'running') runningCount++;

                                // Get device name from metadata
                                const deviceName = metadata[taskId]?.device_name || 'Unknown Device';

                                recentTasks.push({
                                    taskId: taskId,
                                    deviceName: deviceName,
                                    status: status,
                                    created: task.created_on
                                });

                                if (fetchedCount === Math.min(taskIds.length, 50)) {
                                    // Store all tasks globally for search
                                    allTasks = recentTasks;
                                    displayRecentTasks(recentTasks.slice(0, 10), queuedCount, runningCount);
                                }
                            })
                            .fail(function() {
                                fetchedCount++;
                                if (fetchedCount === Math.min(taskIds.length, 50)) {
                                    allTasks = recentTasks;
                                    displayRecentTasks(recentTasks.slice(0, 10), queuedCount, runningCount);
                                }
                            });
                    });

                    // Also count all tasks for accurate queue/running counts
                    taskIds.forEach(function(taskId) {
                        $.get('/api/tasks/' + taskId)
                            .done(function(taskResponse) {
                                if (!taskResponse) return;
                                const task = taskResponse.data || taskResponse;
                                if (!task) return;
                                const status = task.task_status || task.status || 'unknown';

                                const statusLower2 = status.toLowerCase();
                                if (statusLower2 === 'queued' || statusLower2 === 'pending') {
                                    queuedCount++;
                                    $('#queued-count').text(queuedCount);
                                } else if (statusLower2 === 'started' || statusLower2 === 'running') {
                                    runningCount++;
                                    $('#running-count').text(runningCount);
                                }
                            });
                    });
                })
                .fail(function() {
                    $('#queued-count').text('?');
                    $('#running-count').text('?');
                    $('#recent-tasks-loading').hide();
                    $('#recent-tasks-container').show();
                });
        })
        .fail(function() {
            $('#queued-count').text('?');
            $('#running-count').text('?');
            $('#recent-tasks-loading').hide();
            $('#recent-tasks-container').show();
        });
}

function displayRecentTasks(tasks, queuedCount, runningCount) {
    $('#queued-count').text(queuedCount);
    $('#running-count').text(runningCount);

    const tbody = $('#recent-tasks-body');
    tbody.empty();

    if (tasks.length === 0) {
        tbody.append('<tr><td colspan="3" class="text-center text-muted">No recent tasks</td></tr>');
    } else {
        tasks.forEach(function(task) {
            const status = task.status;
            const statusLower = (status || '').toLowerCase();
            let statusBadge = 'secondary';
            if (statusLower === 'queued' || statusLower === 'pending') statusBadge = 'badge-queued';
            else if (statusLower === 'started' || statusLower === 'running') statusBadge = 'badge-running';
            else if (statusLower === 'finished' || statusLower === 'completed' || statusLower === 'success') statusBadge = 'badge-completed';
            else if (statusLower === 'failed' || statusLower === 'failure') statusBadge = 'badge-failed';

            const deviceName = task.deviceName || 'Unknown Device';
            const createdDate = task.created ? formatDate(task.created) : 'N/A';

            tbody.append(`
                <tr class="task-row" data-task-id="${task.taskId}" style="cursor: pointer;">
                    <td><small>${deviceName}</small></td>
                    <td><span class="badge ${statusBadge}">${status}</span></td>
                    <td><small>${createdDate}</small></td>
                </tr>
            `);
        });
    }

    $('#recent-tasks-loading').hide();
    $('#recent-tasks-container').show();
}

function loadDeviceCount() {
    // Get filters from settings
    let filters = [];
    try {
        const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
        filters = settings.netbox_filters || [];
    } catch (e) {
        console.error('Error reading filters from settings:', e);
    }

    // Make POST request with filters
    $.ajax({
        url: '/api/devices',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ filters: filters })
    })
        .done(function(data) {
            // Handle both response formats: data.devices (legacy) or data.data.devices (microservice)
            const devices = data.devices || (data.data && data.data.devices) || [];
            const deviceCount = data.data?.count || devices.length || 0;
            $('#device-count').text(deviceCount);

            // Count devices by source
            let netboxCount = 0;
            let manualCount = 0;
            devices.forEach(function(device) {
                if (device.source === 'netbox') {
                    netboxCount++;
                } else {
                    manualCount++;
                }
            });

            // Update source text
            if (netboxCount > 0 && manualCount > 0) {
                $('#device-sources-text').text(`${netboxCount} NetBox, ${manualCount} Manual`);
            } else if (netboxCount > 0) {
                $('#device-sources-text').text(`${netboxCount} from NetBox`);
            } else if (manualCount > 0) {
                $('#device-sources-text').text(`${manualCount} Manual`);
            } else {
                $('#device-sources-text').text('No devices');
            }
        })
        .fail(function() {
            $('#device-count').text('?');
            $('#device-sources-text').text('Error loading');
        });
}

function loadScheduledTasks() {
    // Load both scheduled operations AND backup schedule
    Promise.all([
        $.get('/api/scheduled-operations'),
        $.get('/api/backup-schedule')
    ])
    .then(function([scheduleData, backupData]) {
        $('#scheduled-tasks-loading').hide();

        const allSchedules = [];

        // Add scheduled operations
        if (scheduleData.success && scheduleData.schedules) {
            scheduleData.schedules.filter(s => s.enabled).forEach(s => {
                allSchedules.push({
                    ...s,
                    source: 'operations'
                });
            });
        }

        // Add backup schedule if enabled
        if (backupData.success && backupData.schedule && backupData.schedule.enabled) {
            allSchedules.push({
                schedule_id: 'backup-schedule',
                operation_type: 'config_backup',
                schedule_type: 'interval',
                next_run: backupData.schedule.next_run,
                last_run: backupData.schedule.last_run,
                interval_hours: backupData.schedule.interval_hours,
                enabled: true,
                source: 'backup'
            });
        }

        if (allSchedules.length === 0) {
            $('#no-scheduled-tasks').show();
            $('#scheduled-tasks-container').hide();
            return;
        }

        const tbody = $('#scheduled-tasks-body');
        tbody.empty();

        // Sort by next_run
        allSchedules.sort((a, b) => {
            if (!a.next_run) return 1;
            if (!b.next_run) return -1;
            return new Date(a.next_run) - new Date(b.next_run);
        });

        // Operation icons and labels
        const operationIcons = {
            'deploy': '<i class="fas fa-rocket text-primary"></i>',
            'validate': '<i class="fas fa-check-circle text-info"></i>',
            'delete': '<i class="fas fa-trash text-danger"></i>',
            'config_deploy': '<i class="fas fa-cog text-warning"></i>',
            'config_backup': '<i class="fas fa-download text-success"></i>'
        };

        const operationLabels = {
            'deploy': 'Deploy Stack',
            'validate': 'Validate Stack',
            'delete': 'Delete Stack',
            'config_deploy': 'Deploy Config',
            'config_backup': 'Device Backup'
        };

        const scheduleTypeLabels = {
            'once': 'One-time',
            'daily': 'Daily',
            'weekly': 'Weekly',
            'monthly': 'Monthly',
            'interval': 'Recurring'
        };

        const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

        // Show only next 10 schedules
        allSchedules.slice(0, 10).forEach(schedule => {
            let scheduleDetails = '';
            if (schedule.schedule_type === 'once') {
                scheduleDetails = formatDateInUserTimezone(schedule.scheduled_time);
            } else if (schedule.schedule_type === 'daily') {
                scheduleDetails = `Daily at ${schedule.scheduled_time}`;
            } else if (schedule.schedule_type === 'weekly') {
                scheduleDetails = `${dayNames[schedule.day_of_week]} at ${schedule.scheduled_time}`;
            } else if (schedule.schedule_type === 'monthly') {
                scheduleDetails = `Day ${schedule.day_of_month} at ${schedule.scheduled_time}`;
            } else if (schedule.schedule_type === 'interval') {
                scheduleDetails = `Every ${schedule.interval_hours}h`;
            }

            const nextRun = schedule.next_run ? formatDateInUserTimezone(schedule.next_run) : 'Not scheduled';

            // Determine target/stack info
            let targetInfo = 'N/A';
            if (schedule.operation_type === 'config_backup') {
                targetInfo = 'All devices';
            } else if (schedule.operation_type === 'config_deploy' && schedule.config_data) {
                try {
                    const configData = JSON.parse(schedule.config_data);
                    const devices = configData.devices || [];
                    targetInfo = devices.length > 0 ? `${devices.length} device(s)` : 'N/A';
                } catch (e) {
                    targetInfo = 'Config Deploy';
                }
            } else if (schedule.stack_id) {
                targetInfo = schedule.stack_id;
            }

            // Different action buttons for backup vs other schedules
            let actionButtons = '';
            if (schedule.source === 'backup') {
                actionButtons = `
                    <a href="/devices" class="btn btn-outline-primary btn-sm" title="Manage">
                        <i class="fas fa-cog"></i>
                    </a>
                `;
            } else {
                actionButtons = `
                    <div class="btn-group btn-group-sm" role="group">
                        <button class="btn btn-outline-primary edit-schedule-btn" data-schedule-id="${schedule.schedule_id}" title="Edit">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-outline-danger delete-schedule-btn" data-schedule-id="${schedule.schedule_id}" title="Delete">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                `;
            }

            const row = `
                <tr>
                    <td>
                        ${operationIcons[schedule.operation_type] || '<i class="fas fa-question"></i>'}
                        <strong>${operationLabels[schedule.operation_type] || 'Unknown'}</strong>
                        <br><small class="text-muted">${scheduleTypeLabels[schedule.schedule_type] || schedule.schedule_type}</small>
                    </td>
                    <td><small>${nextRun}</small></td>
                    <td><small>${targetInfo}</small></td>
                    <td>${actionButtons}</td>
                </tr>
            `;
            tbody.append(row);
        });

        $('#scheduled-tasks-container').show();
        $('#no-scheduled-tasks').hide();
    })
    .catch(function() {
        $('#scheduled-tasks-loading').hide();
        $('#no-scheduled-tasks').show();
        $('#scheduled-tasks-container').hide();
    });
}

// Load backup schedule (for completed schedules panel)
function loadBackupSchedule() {
    // This is already included in loadScheduledTasks, but we can use it for additional UI updates
    $.get('/api/backup-schedule')
        .done(function(data) {
            if (data.success && data.schedule) {
                // Update completed schedules if backup has run
                if (data.schedule.last_run) {
                    addBackupToCompletedSchedules(data.schedule);
                }
            }
        });
}

// Add backup schedule to completed schedules panel
function addBackupToCompletedSchedules(schedule) {
    const tbody = $('#completed-schedules-body');

    // Check if backup row already exists
    if ($('#backup-schedule-completed-row').length > 0) {
        // Update existing row
        $('#backup-schedule-completed-row .last-run-time').text(formatDateInUserTimezone(schedule.last_run));
        return;
    }

    const lastRun = schedule.last_run ? formatDateInUserTimezone(schedule.last_run) : 'Never';

    const row = `
        <tr id="backup-schedule-completed-row">
            <td>
                <i class="fas fa-download text-success"></i>
                <strong>Device Backup</strong>
                <br><small class="text-muted">All devices</small>
            </td>
            <td><small class="last-run-time">${lastRun}</small></td>
            <td><span class="badge bg-info">Recurring</span></td>
            <td>
                <a href="/devices" class="btn btn-sm btn-outline-info" title="View Backups">
                    <i class="fas fa-eye"></i>
                </a>
            </td>
        </tr>
    `;

    // Prepend to top of list
    tbody.prepend(row);

    // Show container if it was hidden
    $('#completed-schedules-container').show();
    $('#no-completed-schedules').hide();
}

// Edit schedule button
$(document).on('click', '.edit-schedule-btn', function() {
    const scheduleId = $(this).data('schedule-id');

    // Fetch schedule details
    $.get('/api/scheduled-operations/' + scheduleId)
        .done(function(data) {
            if (data.success && data.schedule) {
                openEditScheduleModal(data.schedule);
            } else {
                alert('Failed to load schedule details');
            }
        })
        .fail(function() {
            alert('Failed to load schedule details');
        });
});

function openEditScheduleModal(schedule) {
    // Set schedule ID
    $('#edit-schedule-id').val(schedule.schedule_id);

    // Set schedule type
    $('#edit-schedule-type-select').val(schedule.schedule_type);

    // Set enabled status
    $('#edit-schedule-enabled').val(schedule.enabled ? '1' : '0');

    // Hide all sections first
    $('#edit-schedule-datetime-section').hide();
    $('#edit-schedule-time-section').hide();
    $('#edit-schedule-day-week-section').hide();
    $('#edit-schedule-day-month-section').hide();

    // Show and populate relevant sections based on schedule type
    if (schedule.schedule_type === 'once') {
        $('#edit-schedule-datetime-section').show();
        // Time is already in system timezone, no conversion needed
        if (schedule.scheduled_time) {
            // scheduled_time format: "2025-10-15T14:28:00"
            // datetime-local input expects: "2025-10-15T14:28"
            const timeValue = schedule.scheduled_time.slice(0, 16);
            $('#edit-schedule-datetime').val(timeValue);
        }
    } else {
        $('#edit-schedule-time-section').show();
        $('#edit-schedule-time').val(schedule.scheduled_time);

        if (schedule.schedule_type === 'weekly') {
            $('#edit-schedule-day-week-section').show();
            $('#edit-schedule-day-week').val(schedule.day_of_week);
        } else if (schedule.schedule_type === 'monthly') {
            $('#edit-schedule-day-month-section').show();
            $('#edit-schedule-day-month').val(schedule.day_of_month);
        }
    }

    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('editScheduleModal'));
    modal.show();
}

// Handle schedule type changes in edit modal
$(document).on('change', '#edit-schedule-type-select', function() {
    const scheduleType = $(this).val();

    // Hide all sections
    $('#edit-schedule-datetime-section').hide();
    $('#edit-schedule-time-section').hide();
    $('#edit-schedule-day-week-section').hide();
    $('#edit-schedule-day-month-section').hide();

    // Show relevant sections
    if (scheduleType === 'once') {
        $('#edit-schedule-datetime-section').show();
    } else if (scheduleType === 'daily') {
        $('#edit-schedule-time-section').show();
    } else if (scheduleType === 'weekly') {
        $('#edit-schedule-time-section').show();
        $('#edit-schedule-day-week-section').show();
    } else if (scheduleType === 'monthly') {
        $('#edit-schedule-time-section').show();
        $('#edit-schedule-day-month-section').show();
    }
});

// Save schedule changes
$(document).on('click', '#save-schedule-btn', function() {
    const scheduleId = $('#edit-schedule-id').val();
    const scheduleType = $('#edit-schedule-type-select').val();
    const enabled = parseInt($('#edit-schedule-enabled').val());

    let scheduledTime, dayOfWeek = null, dayOfMonth = null;

    // Collect schedule time based on type
    if (scheduleType === 'once') {
        const localTime = $('#edit-schedule-datetime').val();
        if (!localTime) {
            alert('Please select a date and time');
            return;
        }
        // Keep the time as-is in the system timezone (no UTC conversion)
        // The backend expects times in the container's local timezone
        scheduledTime = localTime;
    } else {
        scheduledTime = $('#edit-schedule-time').val();
        if (!scheduledTime) {
            alert('Please select a time');
            return;
        }

        if (scheduleType === 'weekly') {
            dayOfWeek = parseInt($('#edit-schedule-day-week').val());
        } else if (scheduleType === 'monthly') {
            dayOfMonth = parseInt($('#edit-schedule-day-month').val());
            if (!dayOfMonth || dayOfMonth < 1 || dayOfMonth > 31) {
                alert('Please enter a valid day of month (1-31)');
                return;
            }
        }
    }

    const updateData = {
        schedule_type: scheduleType,
        scheduled_time: scheduledTime,
        day_of_week: dayOfWeek,
        day_of_month: dayOfMonth,
        enabled: enabled
    };

    $.ajax({
        url: '/api/scheduled-operations/' + scheduleId,
        method: 'PUT',
        contentType: 'application/json',
        data: JSON.stringify(updateData)
    })
    .done(function(data) {
        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('editScheduleModal')).hide();
            loadScheduledTasks(); // Reload the list
        } else {
            alert('Failed to update schedule: ' + (data.error || 'Unknown error'));
        }
    })
    .fail(function(xhr) {
        alert('Failed to update schedule: ' + (xhr.responseJSON?.error || 'Network error'));
    });
});

// Delete schedule button
$(document).on('click', '.delete-schedule-btn', function() {
    const scheduleId = $(this).data('schedule-id');

    $.ajax({
        url: '/api/scheduled-operations/' + scheduleId,
        method: 'DELETE'
    })
    .done(function(data) {
        if (data.success) {
            loadScheduledTasks(); // Reload the list
        } else {
            alert('Failed to delete schedule: ' + (data.error || 'Unknown error'));
        }
    })
    .fail(function(xhr) {
        alert('Failed to delete schedule: ' + (xhr.responseJSON?.error || 'Network error'));
    });
});

// Filter tasks by device name
function filterTasks(searchTerm) {
    if (!searchTerm) {
        // Show all tasks (up to 10)
        displayRecentTasks(allTasks.slice(0, 10));
        $('#no-tasks-found').hide();
        $('#recent-tasks-container').show();
        return;
    }

    // Filter tasks by device name
    const filtered = allTasks.filter(task =>
        task.deviceName.toLowerCase().includes(searchTerm)
    );

    if (filtered.length === 0) {
        $('#recent-tasks-container').hide();
        $('#no-tasks-found').show();
    } else {
        $('#no-tasks-found').hide();
        displayRecentTasks(filtered.slice(0, 20));
        $('#recent-tasks-container').show();
    }
}

// Load completed scheduled operations
function loadCompletedSchedules() {
    $.get('/api/scheduled-operations')
        .done(function(data) {
            $('#completed-schedules-loading').hide();

            if (data.success && data.schedules && data.schedules.length > 0) {
                // Filter for completed schedules (run_count > 0 or last_run exists)
                const completed = data.schedules.filter(s => s.run_count > 0 || s.last_run);

                if (completed.length === 0) {
                    $('#no-completed-schedules').show();
                    $('#completed-schedules-container').hide();
                    return;
                }

                const tbody = $('#completed-schedules-body');
                tbody.empty();

                // Sort by last_run descending
                completed.sort((a, b) => {
                    if (!a.last_run) return 1;
                    if (!b.last_run) return -1;
                    return new Date(b.last_run) - new Date(a.last_run);
                });

                // Show only last 10 completed
                completed.slice(0, 10).forEach(schedule => {
                    const operationIcons = {
                        'deploy': '<i class="fas fa-rocket text-primary"></i>',
                        'validate': '<i class="fas fa-check-circle text-info"></i>',
                        'delete': '<i class="fas fa-trash text-danger"></i>',
                        'config_deploy': '<i class="fas fa-cog text-warning"></i>'
                    };

                    const operationLabels = {
                        'deploy': 'Deploy Stack',
                        'validate': 'Validate Stack',
                        'delete': 'Delete Stack',
                        'config_deploy': 'Deploy Config'
                    };

                    const scheduleTypeLabels = {
                        'once': 'One-time',
                        'daily': 'Daily',
                        'weekly': 'Weekly',
                        'monthly': 'Monthly'
                    };

                    const lastRun = schedule.last_run ? formatDateInUserTimezone(schedule.last_run) : 'Never';
                    const statusBadge = schedule.enabled ?
                        '<span class="badge bg-success">Active</span>' :
                        '<span class="badge bg-secondary">Completed</span>';

                    // Determine target/stack info
                    let targetInfo = 'N/A';
                    if (schedule.operation_type === 'config_deploy' && schedule.config_data) {
                        try {
                            const configData = JSON.parse(schedule.config_data);
                            const devices = configData.devices || [];
                            targetInfo = devices.length > 0 ? `${devices.length} device(s)` : 'N/A';
                        } catch (e) {
                            targetInfo = 'Config Deploy';
                        }
                    } else if (schedule.stack_id) {
                        targetInfo = schedule.stack_id;
                    }

                    const row = `
                        <tr>
                            <td>
                                ${operationIcons[schedule.operation_type] || '<i class="fas fa-question"></i>'}
                                <strong>${operationLabels[schedule.operation_type] || 'Unknown'}</strong>
                                <br><small class="text-muted">${targetInfo}</small>
                            </td>
                            <td><small>${lastRun}</small></td>
                            <td><span class="badge bg-info">${schedule.run_count || 0}</span></td>
                            <td>
                                <button class="btn btn-sm btn-outline-info view-outcome-btn"
                                        data-schedule-id="${schedule.schedule_id}"
                                        data-operation-type="${schedule.operation_type}"
                                        title="View Outcome">
                                    <i class="fas fa-eye"></i>
                                </button>
                            </td>
                        </tr>
                    `;
                    tbody.append(row);
                });

                $('#completed-schedules-container').show();
                $('#no-completed-schedules').hide();
            } else {
                $('#no-completed-schedules').show();
                $('#completed-schedules-container').hide();
            }
        })
        .fail(function() {
            $('#completed-schedules-loading').hide();
            $('#no-completed-schedules').show();
            $('#completed-schedules-container').hide();
        });
}

// View outcome button handler
$(document).on('click', '.view-outcome-btn', function() {
    const scheduleId = $(this).data('schedule-id');
    const operationType = $(this).data('operation-type');

    if (operationType === 'config_deploy') {
        // For config deployments, try to find and show the most recent task
        showScheduleOutcome(scheduleId);
    } else {
        // For stack operations, go to service stacks page
        window.location.href = '/service-stacks';
    }
});

// Show outcome of completed schedule
function showScheduleOutcome(scheduleId) {
    // Get schedule details first
    $.get('/api/scheduled-operations/' + scheduleId)
        .done(function(data) {
            if (data.success && data.schedule) {
                const schedule = data.schedule;

                // Parse config data to get device info
                if (schedule.config_data) {
                    try {
                        const configData = JSON.parse(schedule.config_data);
                        const devices = configData.devices || [];

                        if (devices.length > 0) {
                            // Get tasks and find the most recent one for these devices
                            $.get('/api/tasks')
                                .done(function(tasksResponse) {
                                    const taskIds = tasksResponse.task_ids || [];

                                    // Get task metadata to filter by device
                                    $.get('/api/tasks/metadata')
                                        .done(function(metadataResponse) {
                                            const metadata = metadataResponse.metadata || {};

                                            // Find tasks for target devices around the schedule's last run time
                                            const lastRunTime = new Date(schedule.last_run);
                                            let matchedTaskId = null;

                                            // Look through recent tasks
                                            for (const taskId of taskIds.slice(0, 20)) {
                                                const taskMeta = metadata[taskId];
                                                if (taskMeta && devices.includes(taskMeta.device_name)) {
                                                    // Found a task for one of the target devices
                                                    matchedTaskId = taskId;
                                                    break;
                                                }
                                            }

                                            if (matchedTaskId) {
                                                // Show the task results
                                                showTaskResults(matchedTaskId);
                                            } else {
                                                // No task found, show message
                                                alert('No task results found for this schedule.\n\nThe scheduled deployment may have failed to create tasks, or the tasks may have been purged.\n\nRedirecting to Job Monitor...');
                                                window.location.href = '/monitor';
                                            }
                                        })
                                        .fail(function() {
                                            alert('Could not load task metadata.\n\nRedirecting to Job Monitor...');
                                            window.location.href = '/monitor';
                                        });
                                })
                                .fail(function() {
                                    alert('Could not load tasks.\n\nRedirecting to Job Monitor...');
                                    window.location.href = '/monitor';
                                });
                        } else {
                            alert('No device information found for this schedule.');
                        }
                    } catch (e) {
                        alert('Could not parse schedule configuration.');
                    }
                } else {
                    alert('No configuration data found for this schedule.');
                }
            }
        })
        .fail(function() {
            alert('Failed to load schedule details.\n\nRedirecting to Job Monitor...');
            window.location.href = '/monitor';
        });
}

// Show task results modal
function showTaskResults(taskId) {
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('taskResultsModal'));
    modal.show();

    // Show loading state
    $('#task-results-loading').show();
    $('#task-results-content').hide();
    $('#task-results-error').hide();

    // Fetch task metadata first
    $.get('/api/tasks/metadata')
        .done(function(metadataResponse) {
            const metadata = metadataResponse.metadata || {};
            const deviceName = metadata[taskId]?.device_name || 'Unknown Device';

            // Fetch task details
            $.get('/api/tasks/' + taskId)
                .done(function(taskResponse) {
                    const task = taskResponse.data || taskResponse;

                    // Populate task info
                    $('#task-result-id').text(taskId);
                    $('#task-result-device').text(deviceName);

                    const status = task.task_status || task.status || 'unknown';
                    let statusBadge = 'secondary';
                    let statusText = status;

                    if (status === 'queued') {
                        statusBadge = 'warning';
                        statusText = 'Queued';
                    } else if (status === 'started' || status === 'running') {
                        statusBadge = 'info';
                        statusText = 'Running';
                    } else if (status === 'finished' || status === 'completed') {
                        statusBadge = 'success';
                        statusText = 'Completed';
                    } else if (status === 'failed') {
                        statusBadge = 'danger';
                        statusText = 'Failed';
                    }

                    $('#task-result-status').html(`<span class="badge bg-${statusBadge}">${statusText}</span>`);

                    const createdDate = task.created_on ? formatDateInUserTimezone(task.created_on) : 'N/A';
                    $('#task-result-created').text(createdDate);

                    // Get task result
                    let resultOutput = 'No output available';

                    if (task.task_result) {
                        if (typeof task.task_result === 'string') {
                            resultOutput = task.task_result;
                        } else {
                            resultOutput = JSON.stringify(task.task_result, null, 2);
                        }
                    } else if (task.task_errors) {
                        resultOutput = `Error: ${JSON.stringify(task.task_errors, null, 2)}`;
                    }

                    $('#task-result-output').text(resultOutput);

                    // Hide loading, show content
                    $('#task-results-loading').hide();
                    $('#task-results-content').show();
                })
                .fail(function(xhr) {
                    $('#task-results-loading').hide();
                    $('#task-error-message').text('Failed to load task details: ' + (xhr.responseJSON?.error || 'Unknown error'));
                    $('#task-results-error').show();
                });
        })
        .fail(function() {
            // If metadata fails, still try to show task
            $.get('/api/tasks/' + taskId)
                .done(function(taskResponse) {
                    const task = taskResponse.data || taskResponse;

                    $('#task-result-id').text(taskId);
                    $('#task-result-device').text('Unknown Device');

                    const status = task.task_status || task.status || 'unknown';
                    $('#task-result-status').html(`<span class="badge bg-secondary">${status}</span>`);

                    const createdDate = task.created_on ? formatDateInUserTimezone(task.created_on) : 'N/A';
                    $('#task-result-created').text(createdDate);

                    let resultOutput = 'No output available';
                    if (task.task_result) {
                        resultOutput = typeof task.task_result === 'string' ?
                            task.task_result :
                            JSON.stringify(task.task_result, null, 2);
                    }

                    $('#task-result-output').text(resultOutput);

                    $('#task-results-loading').hide();
                    $('#task-results-content').show();
                })
                .fail(function(xhr) {
                    $('#task-results-loading').hide();
                    $('#task-error-message').text('Failed to load task: ' + (xhr.responseJSON?.error || 'Unknown error'));
                    $('#task-results-error').show();
                });
        });
}

function loadServiceStacksSummary() {
    $.get('/api/service-stacks')
        .done(function(data) {
            if (data.success && data.stacks && data.stacks.length > 0) {
                const stacks = data.stacks;

                // Update counts
                $('#total-stacks-count').text(stacks.length);

                // Count deployed instances
                let deployedCount = 0;
                let totalServices = 0;
                stacks.forEach(stack => {
                    if (stack.state === 'deployed' || stack.state === 'partial') {
                        deployedCount++;
                    }
                    if (stack.deployed_services && Array.isArray(stack.deployed_services)) {
                        totalServices += stack.deployed_services.length;
                    }
                });
                $('#active-deployments-count').text(deployedCount);
                $('#total-services-count').text(totalServices);

                // Count scheduled stacks
                let scheduledCount = stacks.filter(stack => stack.scheduled).length;
                $('#scheduled-stacks-count').text(scheduledCount);

                // Populate table
                const tbody = $('#service-stacks-body');
                tbody.empty();

                // Show first 5 stacks
                stacks.slice(0, 5).forEach(stack => {
                    const servicesCount = stack.deployed_services ? stack.deployed_services.length : 0;
                    const stateClass = stack.state === 'deployed' ? 'success' :
                                      stack.state === 'partial' ? 'warning' :
                                      stack.state === 'deploying' ? 'info' : 'secondary';
                    const stateText = stack.state || 'unknown';

                    const created = stack.created_at
                        ? new Date(stack.created_at).toLocaleString()
                        : '<span class="text-muted">Unknown</span>';

                    tbody.append(`
                        <tr>
                            <td><strong>${escapeHtml(stack.name)}</strong></td>
                            <td><span class="badge bg-info">${servicesCount} service${servicesCount !== 1 ? 's' : ''}</span></td>
                            <td><span class="badge bg-${stateClass}">${escapeHtml(stateText)}</span></td>
                            <td>${created}</td>
                            <td>
                                <button class="btn btn-sm btn-outline-primary view-deployed-stack-btn" data-stack-id="${escapeHtml(stack.stack_id)}" title="View Stack Details">
                                    <i class="fas fa-eye"></i>
                                </button>
                            </td>
                        </tr>
                    `);
                });

                $('#service-stacks-loading').hide();
                $('#service-stacks-container').show();
            } else {
                $('#service-stacks-loading').hide();
                $('#no-service-stacks').show();
            }
        })
        .fail(function() {
            $('#service-stacks-loading').hide();
            $('#no-service-stacks').show();
        });
}

function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// ============================================================================
// AI Agents Summary
// ============================================================================

function loadAgentsSummary() {
    $.get('/api/agents/')
        .done(function(data) {
            $('#agents-loading').hide();

            if (data.agents && data.agents.length > 0) {
                const agents = data.agents;
                const activeAgents = agents.filter(a => a.is_active);

                // Update top card
                $('#agent-count').text(agents.length);
                $('#active-agents-text').text(`${activeAgents.length} active`);

                // Also update stack count card if not already set
                if ($('#stack-count').text() === '-') {
                    $('#stack-count').text('0');
                    $('#deployed-services-text').text('0 services');
                }

                // Populate agents table
                const tbody = $('#agents-body');
                tbody.empty();

                agents.slice(0, 5).forEach(agent => {
                    const statusBadge = agent.is_active
                        ? '<span class="badge bg-success">Active</span>'
                        : '<span class="badge bg-secondary">Inactive</span>';

                    const agentType = agent.agent_type || 'custom';
                    const typeBadge = getAgentTypeBadge(agentType);

                    tbody.append(`
                        <tr>
                            <td>
                                <strong>${escapeHtml(agent.agent_name || 'Unnamed')}</strong>
                            </td>
                            <td>${typeBadge}</td>
                            <td>${statusBadge}</td>
                            <td>
                                <a href="/agents/${agent.agent_id}/chat" class="btn btn-sm btn-outline-primary" title="Chat">
                                    <i class="fas fa-comments"></i>
                                </a>
                            </td>
                        </tr>
                    `);
                });

                $('#agents-container').show();
            } else {
                // Update counts
                $('#agent-count').text('0');
                $('#active-agents-text').text('No agents');
                $('#no-agents').show();
            }
        })
        .fail(function() {
            $('#agents-loading').hide();
            $('#agent-count').text('0');
            $('#active-agents-text').text('Error loading');
            $('#no-agents').show();
        });
}

function getAgentTypeBadge(type) {
    const badges = {
        'triage': '<span class="badge bg-warning text-dark">Triage</span>',
        'diagnostic': '<span class="badge bg-info">Diagnostic</span>',
        'remediation': '<span class="badge bg-danger">Remediation</span>',
        'automation': '<span class="badge bg-primary">Automation</span>',
        'monitoring': '<span class="badge bg-success">Monitoring</span>',
        'custom': '<span class="badge bg-secondary">Custom</span>'
    };
    return badges[type] || badges['custom'];
}

// ============================================================================
// Alerts Summary
// ============================================================================

function loadAlertsSummary() {
    // Load both alerts and incidents
    Promise.all([
        $.get('/api/alerts/?status=new&limit=10'),
        $.get('/api/incidents/?status=open&limit=10')
    ])
    .then(function([alertsData, incidentsData]) {
        $('#alerts-loading').hide();

        const alerts = alertsData.alerts || [];
        const incidents = incidentsData.incidents || [];

        // Update top card
        const openIncidents = incidents.length;
        const criticalAlerts = alerts.filter(a => a.severity === 'critical').length;

        $('#incident-count').text(openIncidents);
        if (criticalAlerts > 0) {
            $('#critical-alerts-text').text(`${criticalAlerts} critical alerts`);
            $('#incidents-card').css('animation', 'pulse 2s infinite');
        } else if (alerts.length > 0) {
            $('#critical-alerts-text').text(`${alerts.length} new alerts`);
        } else {
            $('#critical-alerts-text').text('No active alerts');
            // Change card to green if no incidents/alerts
            if (openIncidents === 0) {
                $('#incidents-card').css('background', 'linear-gradient(135deg, #22c55e 0%, #16a34a 100%)');
            }
        }

        // Populate alerts table
        if (alerts.length > 0) {
            const tbody = $('#alerts-body');
            tbody.empty();

            alerts.slice(0, 5).forEach(alert => {
                const severityBadge = getSeverityBadge(alert.severity);
                const device = alert.device || 'N/A';
                const time = alert.created_at ? formatRelativeTime(alert.created_at) : 'N/A';

                tbody.append(`
                    <tr class="alert-row" data-alert-id="${alert.alert_id}" style="cursor: pointer;">
                        <td>
                            <small>${escapeHtml(alert.title || 'Unknown')}</small>
                        </td>
                        <td>${severityBadge}</td>
                        <td><small>${escapeHtml(device)}</small></td>
                        <td><small>${time}</small></td>
                    </tr>
                `);
            });

            $('#alerts-container').show();
        } else {
            $('#no-alerts').show();
        }
    })
    .catch(function() {
        $('#alerts-loading').hide();
        $('#incident-count').text('?');
        $('#critical-alerts-text').text('Error loading');
        $('#no-alerts').show();
    });
}

function getSeverityBadge(severity) {
    const badges = {
        'critical': '<span class="badge bg-danger">Critical</span>',
        'error': '<span class="badge bg-danger">Error</span>',
        'warning': '<span class="badge bg-warning text-dark">Warning</span>',
        'info': '<span class="badge bg-info">Info</span>'
    };
    return badges[severity] || badges['info'];
}

function formatRelativeTime(dateString) {
    const date = new Date(dateString);
    const now = new Date();
    const diffMs = now - date;
    const diffSecs = Math.floor(diffMs / 1000);
    const diffMins = Math.floor(diffSecs / 60);
    const diffHours = Math.floor(diffMins / 60);
    const diffDays = Math.floor(diffHours / 24);

    if (diffDays > 0) return `${diffDays}d ago`;
    if (diffHours > 0) return `${diffHours}h ago`;
    if (diffMins > 0) return `${diffMins}m ago`;
    return 'just now';
}

// Alert row click handler
$(document).on('click', '.alert-row', function() {
    const alertId = $(this).data('alert-id');
    window.location.href = `/alerts?alert=${alertId}`;
});
