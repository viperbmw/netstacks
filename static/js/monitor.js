// Monitor page JavaScript for NetStacks

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
            // Stop auto-refresh
            clearInterval(autoRefreshInterval);
            btn.attr('data-auto', 'false');
            btn.removeClass('active');
            btn.html('<i class="fas fa-play"></i> Auto-Refresh (5s)');
        } else {
            // Start auto-refresh
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

    // Event delegation for dynamically created view buttons
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

    // Fetch task metadata first
    $.get('/api/tasks/metadata')
        .done(function(metadataResponse) {
            const metadata = metadataResponse.metadata || {};

            $.get('/api/tasks')
                .done(function(data) {
                    const tbody = $('#tasks-body');
                    tbody.empty();

                    // Netstacker returns: {status: 'success', data: {task_id: ['id1', 'id2', ...]}}
                    let taskIds = [];
                    if (data.data && data.data.task_id && Array.isArray(data.data.task_id)) {
                        taskIds = data.data.task_id;
                    } else if (data.task_id && Array.isArray(data.task_id)) {
                        taskIds = data.task_id;
                    }

                    if (taskIds.length === 0) {
                        $('#no-tasks').show();
                        $('#tasks-table').hide();
                        $('#tasks-loading').hide();
                        $('#tasks-container').show();
                        return;
                    }

                    $('#no-tasks').hide();
                    $('#tasks-table').show();

                    // Fetch details for each task
                    let tasksLoaded = 0;
                    taskIds.forEach(function(taskId) {
                        $.get('/api/task/' + taskId)
                            .done(function(taskResponse) {
                                const task = taskResponse.data || taskResponse;
                                const status = task.task_status || task.status || 'unknown';

                                // Filter based on showCompleted
                                if (!showCompleted && (status === 'finished' || status === 'completed')) {
                                    tasksLoaded++;
                                    if (tasksLoaded === taskIds.length) {
                                        $('#tasks-loading').hide();
                                        $('#tasks-container').show();
                                        if (tbody.children().length === 0) {
                                            $('#no-tasks').show();
                                            $('#tasks-table').hide();
                                        }
                                    }
                                    return;
                                }

                                // Get device name from metadata
                                const deviceName = metadata[taskId]?.device_name || 'Unknown Device';

                                const created = task.created_on || task.enqueued_at || 'N/A';

                                let statusBadge = 'secondary';
                                if (status === 'queued') statusBadge = 'badge-queued';
                                else if (status === 'started' || status === 'running') statusBadge = 'badge-running';
                                else if (status === 'finished' || status === 'completed') statusBadge = 'badge-completed';
                                else if (status === 'failed') statusBadge = 'badge-failed';

                                const createdDate = created !== 'N/A' ? formatDate(created) : 'N/A';

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

                        tasksLoaded++;
                        if (tasksLoaded === taskIds.length) {
                            $('#tasks-loading').hide();
                            $('#tasks-container').show();
                        }
                    })
                    .fail(function() {
                        tasksLoaded++;
                        if (tasksLoaded === taskIds.length) {
                            $('#tasks-loading').hide();
                            $('#tasks-container').show();
                        }
                    });
                });
            })
            .fail(function(xhr, status, error) {
                $('#tasks-loading').hide();
                $('#tasks-container').show();
                $('#no-tasks').html('<i class="fas fa-exclamation-triangle"></i> Error loading tasks: ' + error).show();
                $('#tasks-table').hide();
            });
        })
        .fail(function() {
            $('#tasks-loading').hide();
            $('#tasks-container').show();
            $('#no-tasks').html('<i class="fas fa-exclamation-triangle"></i> Error loading task metadata').show();
            $('#tasks-table').hide();
        });
}

function loadWorkers() {
    $('#workers-loading').show();
    $('#workers-container').hide();

    $.get('/api/workers')
        .done(function(data) {
            const tbody = $('#workers-body');
            tbody.empty();

            if (data.length === 0) {
                tbody.append('<tr><td colspan="4" class="text-center text-muted">No active workers</td></tr>');
            } else {
                data.forEach(function(worker) {
                    const workerName = worker.name || 'Unknown';
                    const workerType = workerName.includes('pinned') ? 'Pinned' : 'FIFO';
                    const state = worker.state || 'idle';
                    const currentJob = worker.current_job || 'None';

                    let stateClass = 'worker-idle';
                    let stateIcon = '<i class="fas fa-pause-circle"></i>';
                    if (state === 'busy' || state === 'started') {
                        stateClass = 'worker-busy';
                        stateIcon = '<i class="fas fa-spinner fa-spin"></i>';
                    } else if (state === 'failed') {
                        stateClass = 'worker-failed';
                        stateIcon = '<i class="fas fa-exclamation-circle"></i>';
                    }

                    tbody.append(`
                        <tr>
                            <td>${workerName}</td>
                            <td><span class="badge bg-secondary">${workerType}</span></td>
                            <td><span class="${stateClass}">${stateIcon} ${state}</span></td>
                            <td><small class="font-monospace">${currentJob}</small></td>
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
    // Show modal
    const modal = new bootstrap.Modal(document.getElementById('taskDetailModal'));
    modal.show();

    // Reset modal content
    $('#task-detail-loading').show();
    $('#task-detail-content').hide();
    $('#detail-errors-section').hide();

    // Fetch task details
    $.get('/api/task/' + taskId)
        .done(function(data) {
            // Netstacker returns: {status: 'success', data: {task_status: '...', task_result: ...}}
            const task = data.data || data;
            const status = task.task_status || task.status || 'unknown';
            const result = task.task_result || task.data || 'No result available';
            const meta = task.task_meta || {};
            const errors = task.task_errors || [];

            // Status badge
            let statusClass = 'bg-secondary';
            if (status === 'queued') statusClass = 'bg-warning text-dark';
            else if (status === 'started' || status === 'running') statusClass = 'bg-info';
            else if (status === 'finished' || status === 'completed') statusClass = 'bg-success';
            else if (status === 'failed') statusClass = 'bg-danger';

            $('#detail-status').removeClass().addClass('badge ' + statusClass).text(status.toUpperCase());
            $('#detail-task-id').text(taskId);

            // Queue and worker info
            $('#detail-queue').text(task.task_queue || 'N/A');
            $('#detail-worker').text(meta.assigned_worker || 'Not assigned');

            // Timing info
            $('#detail-created').text(task.created_on ? formatDate(task.created_on) : 'N/A');
            $('#detail-started').text(meta.started_at ? formatDate(meta.started_at) : 'Not started');
            $('#detail-ended').text(meta.ended_at ? formatDate(meta.ended_at) : 'Not finished');

            const duration = meta.total_elapsed_seconds || '0';
            $('#detail-duration').text(duration + ' seconds');

            // Errors section
            if (errors && errors.length > 0) {
                let errorHtml = '<ul class="mb-0">';
                errors.forEach(function(err) {
                    const exClass = err.exception_class || 'Unknown Error';
                    const exArgs = err.exception_args || [];
                    const exMsg = Array.isArray(exArgs) ? exArgs.join(' ') : String(exArgs);
                    errorHtml += `<li><strong>${exClass}:</strong> ${exMsg}</li>`;
                });
                errorHtml += '</ul>';
                $('#detail-errors').html(errorHtml);
                $('#detail-errors-section').show();
            }

            // Format result
            let formattedResult = result;
            if (result === null || result === undefined) {
                formattedResult = 'No result data';
            } else if (typeof result === 'object') {
                formattedResult = JSON.stringify(result, null, 2);
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

    $.get('/api/mop-executions/running')
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

                    // Show cancel button only for running executions, view button for completed/failed
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
    $.post('/api/mop-executions/' + executionId + '/cancel')
        .done(function(data) {
            if (data.success) {
                // Show success message
                alert('MOP execution cancelled successfully');
                // Reload MOP executions to reflect the change
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
    // Show modal and loading state
    const modal = new bootstrap.Modal(document.getElementById('mopExecutionDetailModal'));
    modal.show();

    $('#mop-detail-loading').show();
    $('#mop-detail-content').hide();

    // Fetch execution details
    $.get('/api/mop-executions/' + executionId)
        .done(function(data) {
            if (data.success && data.execution) {
                const exec = data.execution;

                // Set status badge
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

                // Calculate duration
                if (exec.started_at && exec.completed_at) {
                    const start = new Date(exec.started_at);
                    const end = new Date(exec.completed_at);
                    const duration = (end - start) / 1000;
                    $('#mop-detail-duration').text(duration.toFixed(1) + 's');
                } else {
                    $('#mop-detail-duration').text('N/A');
                }

                // Show errors if any
                if (exec.error) {
                    $('#mop-detail-errors').text(exec.error);
                    $('#mop-detail-errors-section').show();
                } else {
                    $('#mop-detail-errors-section').hide();
                }

                // Show execution log - format if it's an array of step objects
                let logText = '';
                if (exec.execution_log) {
                    if (Array.isArray(exec.execution_log)) {
                        // Format as readable step-by-step log
                        exec.execution_log.forEach(function(step) {
                            const timestamp = step.timestamp ? formatDate(step.timestamp) : '';
                            const status = step.status ? step.status.toUpperCase() : 'UNKNOWN';
                            const statusIcon = step.status === 'success' ? '✓' : step.status === 'failed' ? '✗' : '•';

                            logText += `${statusIcon} ${step.step}\n`;
                            logText += `  Status: ${status}\n`;
                            if (step.message) {
                                logText += `  Message: ${step.message}\n`;
                            }
                            // Show error details if step failed
                            if (step.error) {
                                logText += `  Error: ${step.error}\n`;
                            }
                            // Show additional details if available
                            if (step.details) {
                                logText += `  Details: ${JSON.stringify(step.details)}\n`;
                            }
                            if (timestamp) {
                                logText += `  Time: ${timestamp}\n`;
                            }
                            logText += '\n';
                        });
                    } else if (typeof exec.execution_log === 'string') {
                        logText = exec.execution_log;
                    } else {
                        // Fallback: JSON stringify
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
    navigator.clipboard.writeText(log).then(function() {
        alert('Log copied to clipboard!');
    }, function(err) {
        alert('Failed to copy log: ' + err);
    });
});

