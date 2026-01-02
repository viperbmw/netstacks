// Monitor page JavaScript for NetStacks
// All task data comes from database - no Celery queries

let autoRefreshInterval = null;
let showCompleted = true;

$(document).ready(function() {
    loadMonitor();

    // Refresh button
    $('#refresh-btn').click(function() {
        loadMonitor();
    });

    // Auto-refresh toggle
    $('#auto-refresh-btn').click(function() {
        const btn = $(this);
        const isAuto = btn.attr('data-auto') === 'true';

        if (isAuto) {
            clearInterval(autoRefreshInterval);
            btn.attr('data-auto', 'false');
            btn.removeClass('active');
            btn.html('<i class="fas fa-play"></i> Auto-Refresh (5s)');
        } else {
            autoRefreshInterval = setInterval(loadMonitor, 5000);
            btn.attr('data-auto', 'true');
            btn.addClass('active');
            btn.html('<i class="fas fa-pause"></i> Stop Auto-Refresh');
        }
    });

    // Show completed toggle
    $('#show-completed').change(function() {
        showCompleted = $(this).is(':checked');
        loadTasks();
    });

    // Event delegation for view buttons
    $(document).on('click', '.view-task-btn, .view-history-btn', function(e) {
        e.preventDefault();
        e.stopPropagation();
        const taskId = $(this).data('task-id');
        viewTaskDetails(taskId);
    });
});

function loadMonitor() {
    loadTasks();
    loadWorkers();
    loadMopExecutions();
    loadTaskHistory();
}

function loadTasks() {
    $('#tasks-loading').show();
    $('#tasks-container').hide();

    // Single API call - all data from DB
    $.get('/api/tasks/metadata')
        .done(function(response) {
            const metadata = response.metadata || {};
            const tbody = $('#tasks-body');
            tbody.empty();

            const taskIds = Object.keys(metadata);

            if (taskIds.length === 0) {
                $('#no-tasks').show();
                $('#tasks-table').hide();
                $('#tasks-loading').hide();
                $('#tasks-container').show();
                return;
            }

            $('#no-tasks').hide();
            $('#tasks-table').show();

            // Render all tasks from DB metadata - instant, no additional calls
            taskIds.forEach(function(taskId) {
                const task = metadata[taskId] || {};
                const deviceName = task.device_name || 'Unknown Device';
                const status = task.status || 'pending';
                const created = task.created_at || null;
                const createdDate = created ? formatDate(created) : 'N/A';

                // Skip completed tasks if filter is off
                if (!showCompleted && (status === 'success' || status === 'completed')) {
                    return;
                }

                // Determine badge class
                let statusBadge = 'badge-secondary';
                const statusLower = status.toLowerCase();
                if (statusLower === 'pending') statusBadge = 'badge-queued';
                else if (statusLower === 'started') statusBadge = 'badge-running';
                else if (statusLower === 'success') statusBadge = 'badge-completed';
                else if (statusLower === 'failure') statusBadge = 'badge-failed';

                tbody.append(`
                    <tr data-task-id="${taskId}">
                        <td><small>${deviceName}</small></td>
                        <td><span class="badge ${statusBadge}">${status}</span></td>
                        <td><small>${createdDate}</small></td>
                        <td>
                            <button class="btn btn-sm btn-primary view-task-btn" data-task-id="${taskId}">
                                <i class="fas fa-eye"></i> View
                            </button>
                        </td>
                    </tr>
                `);
            });

            $('#tasks-loading').hide();
            $('#tasks-container').show();
        })
        .fail(function(xhr, status, error) {
            $('#tasks-loading').hide();
            $('#tasks-container').show();
            $('#no-tasks').html('<i class="fas fa-exclamation-triangle"></i> Error loading tasks: ' + error).show();
            $('#tasks-table').hide();
        });
}

function loadWorkers() {
    $('#workers-loading').show();
    $('#workers-container').hide();

    // Get active tasks from DB metadata (tasks with status 'started')
    $.get('/api/tasks/metadata')
        .done(function(response) {
            const metadata = response.metadata || {};
            const tbody = $('#workers-body');
            tbody.empty();

            // Find tasks that are currently running (status = 'started')
            const activeTasks = [];
            Object.entries(metadata).forEach(function([taskId, task]) {
                if (task.status === 'started') {
                    activeTasks.push({
                        taskId: taskId,
                        deviceName: task.device_name,
                        taskName: task.task_name,
                        startedAt: task.started_at
                    });
                }
            });

            if (activeTasks.length === 0) {
                tbody.append('<tr><td colspan="4" class="text-center text-muted">No active tasks</td></tr>');
            } else {
                activeTasks.forEach(function(task) {
                    const shortTaskName = task.taskName ? task.taskName.split('.').pop() : 'unknown';
                    const startedAt = task.startedAt ? formatDate(task.startedAt) : 'N/A';

                    tbody.append(`
                        <tr>
                            <td>${task.deviceName || 'Unknown'}</td>
                            <td><span class="badge bg-info">${shortTaskName}</span></td>
                            <td><span class="worker-busy"><i class="fas fa-spinner fa-spin"></i> running</span></td>
                            <td><small>${startedAt}</small></td>
                        </tr>
                    `);
                });
            }

            $('#workers-loading').hide();
            $('#workers-container').show();
        })
        .fail(function() {
            $('#workers-loading').hide();
            $('#workers-container').show();
        });
}

function viewTaskDetails(taskId) {
    const modal = new bootstrap.Modal(document.getElementById('taskDetailModal'));
    modal.show();

    $('#task-detail-loading').show();
    $('#task-detail-content').hide();
    $('#detail-errors-section').hide();

    // Fetch task details from DB
    $.get('/api/tasks/' + taskId)
        .done(function(task) {
            const status = task.status || 'unknown';
            const result = task.result;

            // Status badge
            let statusClass = 'bg-secondary';
            if (status === 'pending') statusClass = 'bg-warning text-dark';
            else if (status === 'started') statusClass = 'bg-info';
            else if (status === 'success') statusClass = 'bg-success';
            else if (status === 'failure') statusClass = 'bg-danger';

            $('#detail-status').removeClass().addClass('badge ' + statusClass).text(status.toUpperCase());
            $('#detail-task-id').text(taskId);

            // Queue and worker info (from task_name)
            const taskName = task.task_name || 'N/A';
            $('#detail-queue').text(taskName.split('.').pop() || 'N/A');
            $('#detail-worker').text(task.device_name || 'N/A');

            // Timing info
            $('#detail-created').text(task.created_at ? formatDate(task.created_at) : 'N/A');
            $('#detail-started').text(task.started_at ? formatDate(task.started_at) : 'Not started');
            $('#detail-ended').text(task.completed_at ? formatDate(task.completed_at) : 'Not finished');

            // Calculate duration
            if (task.started_at && task.completed_at) {
                const start = new Date(task.started_at);
                const end = new Date(task.completed_at);
                const duration = (end - start) / 1000;
                $('#detail-duration').text(duration.toFixed(1) + ' seconds');
            } else {
                $('#detail-duration').text('N/A');
            }

            // Errors section
            if (task.error) {
                $('#detail-errors').html(`<strong>Error:</strong> ${task.error}`);
                $('#detail-errors-section').show();
            }

            // Format result
            let formattedResult = 'No result data';
            if (result !== null && result !== undefined) {
                if (typeof result === 'object') {
                    formattedResult = JSON.stringify(result, null, 2);
                } else {
                    formattedResult = String(result);
                }
            }
            $('#detail-result').text(formattedResult);

            // Copy button handler
            $('#copy-task-details').off('click').on('click', function() {
                const fullDetails = JSON.stringify(task, null, 2);
                navigator.clipboard.writeText(fullDetails).then(function() {
                    const btn = $('#copy-task-details');
                    const originalHtml = btn.html();
                    btn.html('<i class="fas fa-check"></i> Copied!');
                    setTimeout(function() {
                        btn.html(originalHtml);
                    }, 2000);
                });
            });

            $('#task-detail-loading').hide();
            $('#task-detail-content').show();
        })
        .fail(function(xhr, status, error) {
            $('#task-detail-loading').hide();
            $('#task-detail-content').show();
            $('#detail-status').removeClass().addClass('badge bg-danger').text('ERROR');
            $('#detail-task-id').text(taskId);
            $('#detail-queue').text('N/A');
            $('#detail-worker').text('N/A');
            $('#detail-created').text('N/A');
            $('#detail-started').text('N/A');
            $('#detail-ended').text('N/A');
            $('#detail-duration').text('N/A');
            $('#detail-result').text('Error loading task details: ' + error);
        });
}

function loadMopExecutions() {
    $('#mop-executions-loading').show();
    $('#mop-executions-container').hide();

    $.get('/api/mops/executions/running/list')
        .done(function(data) {
            const tbody = $('#mop-executions-body');
            tbody.empty();

            if (!data.success || !data.executions || data.executions.length === 0) {
                $('#no-mop-executions').show();
                $('#mop-executions-container').find('table').hide();
            } else {
                $('#no-mop-executions').hide();
                $('#mop-executions-container').find('table').show();

                data.executions.forEach(function(exec) {
                    const executionId = exec.execution_id;
                    const mopName = exec.mop_name || 'Unknown MOP';
                    const currentStep = exec.current_step !== null ? exec.current_step : 'N/A';
                    const status = exec.status || 'running';
                    const startedAt = exec.started_at ? formatDate(exec.started_at) : 'N/A';

                    let statusBadge = 'bg-info';
                    if (status === 'running') statusBadge = 'badge-running';
                    else if (status === 'completed') statusBadge = 'badge-completed';
                    else if (status === 'failed') statusBadge = 'badge-failed';

                    let actionButton = '';
                    if (status === 'running') {
                        actionButton = `<button class="btn btn-sm btn-danger cancel-mop-btn" data-execution-id="${executionId}">
                                            <i class="fas fa-stop"></i> Cancel
                                        </button>`;
                    } else {
                        actionButton = `<button class="btn btn-sm btn-primary view-mop-execution-btn" data-execution-id="${executionId}">
                                            <i class="fas fa-eye"></i> View
                                        </button>`;
                    }

                    tbody.append(`
                        <tr data-execution-id="${executionId}">
                            <td><small>${mopName}</small></td>
                            <td><span class="badge bg-secondary">Step ${currentStep !== 'N/A' ? parseInt(currentStep) + 1 : 'N/A'}</span></td>
                            <td><span class="badge ${statusBadge}">${status}</span></td>
                            <td><small>${startedAt}</small></td>
                            <td>${actionButton}</td>
                        </tr>
                    `);
                });
            }

            $('#mop-executions-loading').hide();
            $('#mop-executions-container').show();
        })
        .fail(function(xhr, status, error) {
            $('#mop-executions-loading').hide();
            $('#mop-executions-container').show();
            $('#no-mop-executions').html('<i class="fas fa-exclamation-triangle"></i> Error loading MOP executions: ' + error).show();
            $('#mop-executions-container').find('table').hide();
        });
}

// Event delegation for cancel MOP button
$(document).on('click', '.cancel-mop-btn', function(e) {
    e.preventDefault();
    e.stopPropagation();
    const executionId = $(this).data('execution-id');

    if (confirm('Are you sure you want to cancel this MOP execution?')) {
        cancelMopExecution(executionId);
    }
});

// Event delegation for view MOP execution button
$(document).on('click', '.view-mop-execution-btn', function(e) {
    e.preventDefault();
    e.stopPropagation();
    const executionId = $(this).data('execution-id');
    showMopExecutionDetails(executionId);
});

function cancelMopExecution(executionId) {
    $.post('/api/mops/executions/' + executionId + '/cancel')
        .done(function(data) {
            if (data.success) {
                loadMopExecutions();
            } else {
                alert('Error cancelling MOP execution: ' + (data.error || 'Unknown error'));
            }
        })
        .fail(function(xhr, status, error) {
            alert('Error cancelling MOP execution: ' + error);
        });
}

function showMopExecutionDetails(executionId) {
    const modal = new bootstrap.Modal(document.getElementById('mopExecutionDetailModal'));
    modal.show();

    $('#mop-detail-loading').show();
    $('#mop-detail-content').hide();

    $.get('/api/mops/executions/' + executionId)
        .done(function(data) {
            if (data.success && data.execution) {
                const exec = data.execution;

                let statusClass = 'bg-info';
                if (exec.status === 'running') statusClass = 'badge-running';
                else if (exec.status === 'completed') statusClass = 'badge-completed';
                else if (exec.status === 'failed') statusClass = 'badge-failed';

                $('#mop-detail-status').removeClass().addClass('badge ' + statusClass).text(exec.status || 'unknown');
                $('#mop-detail-name').text(exec.mop_name || 'Unknown MOP');
                $('#mop-detail-execution-id').text(executionId);
                $('#mop-detail-current-step').text(exec.current_step !== null ? 'Step ' + (parseInt(exec.current_step) + 1) : 'N/A');
                $('#mop-detail-started').text(exec.started_at ? formatDate(exec.started_at) : 'N/A');
                $('#mop-detail-completed').text(exec.completed_at ? formatDate(exec.completed_at) : 'In Progress');
                $('#mop-detail-started-by').text(exec.started_by || 'N/A');

                if (exec.started_at && exec.completed_at) {
                    const start = new Date(exec.started_at);
                    const end = new Date(exec.completed_at);
                    const duration = (end - start) / 1000;
                    $('#mop-detail-duration').text(duration.toFixed(1) + 's');
                } else {
                    $('#mop-detail-duration').text('N/A');
                }

                if (exec.error) {
                    $('#mop-detail-errors').text(exec.error);
                    $('#mop-detail-errors-section').show();
                } else {
                    $('#mop-detail-errors-section').hide();
                }

                let logText = '';
                if (exec.execution_log) {
                    if (Array.isArray(exec.execution_log)) {
                        exec.execution_log.forEach(function(step) {
                            const timestamp = step.timestamp ? formatDate(step.timestamp) : '';
                            const statusIcon = step.status === 'success' ? '✓' : step.status === 'failed' ? '✗' : '•';

                            logText += `${statusIcon} ${step.step}\n`;
                            logText += `  Status: ${(step.status || 'UNKNOWN').toUpperCase()}\n`;
                            if (step.message) logText += `  Message: ${step.message}\n`;
                            if (step.error) logText += `  Error: ${step.error}\n`;
                            if (step.details) logText += `  Details: ${JSON.stringify(step.details)}\n`;
                            if (timestamp) logText += `  Time: ${timestamp}\n`;
                            logText += '\n';
                        });
                    } else if (typeof exec.execution_log === 'string') {
                        logText = exec.execution_log;
                    } else {
                        logText = JSON.stringify(exec.execution_log, null, 2);
                    }
                } else {
                    logText = 'No log available';
                }
                $('#mop-detail-log').text(logText);

                $('#mop-detail-loading').hide();
                $('#mop-detail-content').show();
            } else {
                alert('Error loading MOP execution details: ' + (data.error || 'Unknown error'));
                modal.hide();
            }
        })
        .fail(function(xhr, status, error) {
            alert('Error loading MOP execution details: ' + error);
            modal.hide();
        });
}

// Copy MOP execution log to clipboard
$('#copy-mop-details').on('click', function() {
    const log = $('#mop-detail-log').text();
    const btn = $(this);
    const originalText = btn.html();
    navigator.clipboard.writeText(log).then(function() {
        btn.html('<i class="fas fa-check"></i> Copied');
        setTimeout(() => btn.html(originalText), 1500);
    }, function(err) {
        alert('Failed to copy log: ' + err);
    });
});
