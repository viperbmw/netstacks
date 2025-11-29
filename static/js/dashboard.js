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

            if (data.success && data.devices && data.devices.length > 0) {
                // Show first 30 devices
                data.devices.slice(0, 30).forEach(function(device) {
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
                        $.get('/api/task/' + taskId)
                            .done(function(taskResponse) {
                                const task = taskResponse.data || taskResponse;
                                const status = task.task_status || task.status || 'unknown';

                                fetchedCount++;

                                // Count by status
                                if (status === 'queued') queuedCount++;
                                else if (status === 'started' || status === 'running') runningCount++;

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
                        $.get('/api/task/' + taskId)
                            .done(function(taskResponse) {
                                const task = taskResponse.data || taskResponse;
                                const status = task.task_status || task.status || 'unknown';

                                if (status === 'queued') {
                                    queuedCount++;
                                    $('#queued-count').text(queuedCount);
                                } else if (status === 'started' || status === 'running') {
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
            let statusBadge = 'secondary';
            if (status === 'queued') statusBadge = 'badge-queued';
            else if (status === 'started' || status === 'running') statusBadge = 'badge-running';
            else if (status === 'finished' || status === 'completed') statusBadge = 'badge-completed';
            else if (status === 'failed') statusBadge = 'badge-failed';

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
            const deviceCount = data.devices ? data.devices.length : 0;
            $('#device-count').text(deviceCount);
        })
        .fail(function() {
            $('#device-count').text('?');
        });
}

function loadScheduledTasks() {
    $.get('/api/scheduled-operations')
        .done(function(data) {
            $('#scheduled-tasks-loading').hide();
            
            if (data.success && data.schedules && data.schedules.length > 0) {
                const schedules = data.schedules.filter(s => s.enabled);
                
                if (schedules.length === 0) {
                    $('#no-scheduled-tasks').show();
                    $('#scheduled-tasks-container').hide();
                    return;
                }
                
                const tbody = $('#scheduled-tasks-body');
                tbody.empty();
                
                // Sort by next_run
                schedules.sort((a, b) => {
                    if (!a.next_run) return 1;
                    if (!b.next_run) return -1;
                    return new Date(a.next_run) - new Date(b.next_run);
                });
                
                // Show only next 10 schedules
                schedules.slice(0, 10).forEach(schedule => {
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

                    const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

                    let scheduleDetails = '';
                    if (schedule.schedule_type === 'once') {
                        scheduleDetails = formatDateInUserTimezone(schedule.scheduled_time);
                    } else if (schedule.schedule_type === 'daily') {
                        scheduleDetails = `Daily at ${schedule.scheduled_time}`;
                    } else if (schedule.schedule_type === 'weekly') {
                        scheduleDetails = `${dayNames[schedule.day_of_week]} at ${schedule.scheduled_time}`;
                    } else if (schedule.schedule_type === 'monthly') {
                        scheduleDetails = `Day ${schedule.day_of_month} at ${schedule.scheduled_time}`;
                    }

                    const nextRun = schedule.next_run ? formatDateInUserTimezone(schedule.next_run) : 'Not scheduled';
                    const statusBadge = schedule.enabled ? '<span class="badge bg-success">Enabled</span>' : '<span class="badge bg-secondary">Disabled</span>';

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
                                <br><small class="text-muted">${scheduleTypeLabels[schedule.schedule_type]}</small>
                            </td>
                            <td><small>${nextRun}</small></td>
                            <td><small>${targetInfo}</small></td>
                            <td>
                                <div class="btn-group btn-group-sm" role="group">
                                    <button class="btn btn-outline-primary edit-schedule-btn" data-schedule-id="${schedule.schedule_id}" title="Edit">
                                        <i class="fas fa-edit"></i>
                                    </button>
                                    <button class="btn btn-outline-danger delete-schedule-btn" data-schedule-id="${schedule.schedule_id}" title="Delete">
                                        <i class="fas fa-trash"></i>
                                    </button>
                                </div>
                            </td>
                        </tr>
                    `;
                    tbody.append(row);
                });
                
                $('#scheduled-tasks-container').show();
                $('#no-scheduled-tasks').hide();
            } else {
                $('#no-scheduled-tasks').show();
                $('#scheduled-tasks-container').hide();
            }
        })
        .fail(function() {
            $('#scheduled-tasks-loading').hide();
            $('#no-scheduled-tasks').show();
            $('#scheduled-tasks-container').hide();
        });
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
            $.get('/api/task/' + taskId)
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
            $.get('/api/task/' + taskId)
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
