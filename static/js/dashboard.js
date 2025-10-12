// Dashboard JavaScript for NetStacks

$(document).ready(function() {
    loadDashboard();

    // Refresh every 10 seconds
    setInterval(loadDashboard, 10000);
});

function loadDashboard() {
    loadWorkerCount();
    loadDevicesList();
    loadTasks();
    loadDeviceCount();
}

function loadWorkerCount() {
    $.get('/api/workers')
        .done(function(data) {
            const workerCount = data.length || 0;
            $('#worker-count').text(workerCount);
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
                    // Netpalm returns: {status: 'success', data: {task_id: ['id1', 'id2']}}
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

                    // Fetch details for first 5 tasks
                    taskIds.slice(0, 5).forEach(function(taskId) {
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

                                if (fetchedCount === Math.min(taskIds.length, 5)) {
                                    displayRecentTasks(recentTasks, queuedCount, runningCount);
                                }
                            })
                            .fail(function() {
                                fetchedCount++;
                                if (fetchedCount === Math.min(taskIds.length, 5)) {
                                    displayRecentTasks(recentTasks, queuedCount, runningCount);
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
            const createdDate = task.created ? new Date(task.created).toLocaleString() : 'N/A';

            tbody.append(`
                <tr style="cursor: pointer;" onclick="window.location.href='/monitor'">
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
