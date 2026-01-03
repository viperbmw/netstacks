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

    // Result view toggle (Formatted vs Raw JSON) - use event delegation for dynamic content
    $(document).on('change', 'input[name="result-view"]', function() {
        if ($('#view-raw').is(':checked')) {
            $('#detail-result').hide();
            $('#detail-result-raw').show();
        } else {
            $('#detail-result').show();
            $('#detail-result-raw').hide();
        }
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
                const taskName = task.task_name || '';
                const actionType = task.action_type || null;

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

                // Format task ID like snapshots do (show first 8 chars of UUID)
                const shortId = taskId.length > 8 ? taskId.substring(0, 8) : taskId;

                // Format task type from action_type (preferred) or task_name (fallback)
                const taskType = formatTaskType(taskName, actionType);

                tbody.append(`
                    <tr data-task-id="${taskId}">
                        <td><small class="font-monospace text-muted" title="${taskId}">${shortId}</small></td>
                        <td>${taskType}</td>
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

// Store the current task result for view toggling
let currentTaskResult = null;

function viewTaskDetails(taskId) {
    const modal = new bootstrap.Modal(document.getElementById('taskDetailModal'));
    modal.show();

    $('#task-detail-loading').show();
    $('#task-detail-content').hide();
    $('#detail-errors-section').hide();

    // Reset view to formatted
    $('#view-formatted').prop('checked', true);
    $('#detail-result').show();
    $('#detail-result-raw').hide();

    // Fetch task details from DB
    $.get('/api/tasks/' + taskId)
        .done(function(task) {
            const status = task.status || 'unknown';
            const result = task.result;

            // Store the full result for raw view
            currentTaskResult = result;

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

            // Format result - make it more readable
            let formattedResult = 'No result data';
            if (result !== null && result !== undefined) {
                if (typeof result === 'object') {
                    formattedResult = formatTaskResult(result);
                } else {
                    formattedResult = String(result);
                }
            }
            $('#detail-result').html(formattedResult);

            // Set raw JSON view
            if (result !== null && result !== undefined) {
                $('#detail-result-json').text(JSON.stringify(result, null, 2));
            } else {
                $('#detail-result-json').text('No result data');
            }

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

/**
 * Format task result for better readability
 * Handles device config output, parsed data, etc.
 */
function formatTaskResult(result) {
    let html = '';
    
    // Show status prominently if present
    if (result.status) {
        const statusClass = result.status === 'success' ? 'text-success' : 
                           result.status === 'failed' ? 'text-danger' : 'text-warning';
        html += `<div class="mb-2"><strong>Status:</strong> <span class="${statusClass} fw-bold">${result.status.toUpperCase()}</span></div>`;
    }
    
    // Show host/device if present
    if (result.host) {
        html += `<div class="mb-2"><strong>Host:</strong> ${escapeHtml(result.host)}</div>`;
    }
    
    // Show command if present
    if (result.command) {
        html += `<div class="mb-2"><strong>Command:</strong> <code>${escapeHtml(result.command)}</code></div>`;
    }
    
    // Show error if present
    if (result.error) {
        html += `<div class="mb-3 p-2 bg-danger bg-opacity-10 border border-danger rounded">
            <strong class="text-danger"><i class="fas fa-exclamation-triangle"></i> Error:</strong>
            <pre class="mb-0 mt-1 text-danger" style="white-space: pre-wrap;">${escapeHtml(result.error)}</pre>
        </div>`;
    }
    
    // Show config lines if present (for set_config tasks)
    if (result.config_lines && Array.isArray(result.config_lines)) {
        html += `<div class="mb-3">
            <strong>Config Lines (${result.config_lines.length}):</strong>
            <pre class="bg-secondary bg-opacity-10 p-2 rounded mt-1 small" style="max-height: 200px; overflow-y: auto;">${escapeHtml(result.config_lines.join('\n'))}</pre>
        </div>`;
    }
    
    // Show rendered config if present
    if (result.rendered_config) {
        html += `<div class="mb-3">
            <strong>Rendered Config:</strong>
            <pre class="bg-secondary bg-opacity-10 p-2 rounded mt-1 small" style="max-height: 200px; overflow-y: auto;">${escapeHtml(result.rendered_config)}</pre>
        </div>`;
    }
    
    // Show CLI output (most important for readability)
    if (result.output) {
        html += `<div class="mb-3">
            <strong>Device Output:</strong>
            <pre class="bg-dark text-light p-3 rounded mt-1" style="max-height: 400px; overflow-y: auto; font-size: 12px; line-height: 1.4;">${escapeHtml(result.output)}</pre>
        </div>`;
    }
    
    // Show save output if present
    if (result.save_output) {
        html += `<div class="mb-3">
            <strong>Save Config Output:</strong>
            <pre class="bg-secondary bg-opacity-10 p-2 rounded mt-1 small" style="max-height: 150px; overflow-y: auto;">${escapeHtml(result.save_output)}</pre>
        </div>`;
    }
    
    // Show parsed output if present (for TextFSM/TTP parsed data)
    if (result.parsed_output) {
        let parsedHtml = '';
        if (Array.isArray(result.parsed_output)) {
            // Format as table if array of objects
            if (result.parsed_output.length > 0 && typeof result.parsed_output[0] === 'object') {
                const headers = Object.keys(result.parsed_output[0]);
                parsedHtml = `<table class="table table-sm table-bordered table-striped mb-0">
                    <thead class="table-dark"><tr>${headers.map(h => `<th>${escapeHtml(h)}</th>`).join('')}</tr></thead>
                    <tbody>${result.parsed_output.map(row => 
                        `<tr>${headers.map(h => `<td>${escapeHtml(String(row[h] || ''))}</td>`).join('')}</tr>`
                    ).join('')}</tbody>
                </table>`;
            } else {
                parsedHtml = `<pre class="mb-0">${escapeHtml(JSON.stringify(result.parsed_output, null, 2))}</pre>`;
            }
        } else {
            parsedHtml = `<pre class="mb-0">${escapeHtml(JSON.stringify(result.parsed_output, null, 2))}</pre>`;
        }
        
        html += `<div class="mb-3">
            <strong>Parsed Output${result.parser ? ' (' + result.parser + ')' : ''}:</strong>
            <div class="bg-secondary bg-opacity-10 p-2 rounded mt-1" style="max-height: 300px; overflow: auto;">${parsedHtml}</div>
        </div>`;
    }
    
    // Show validations if present
    if (result.validations && Array.isArray(result.validations)) {
        html += `<div class="mb-3">
            <strong>Validations:</strong>
            <div class="mt-1">`;
        result.validations.forEach(v => {
            const icon = v.found ? '<i class="fas fa-check text-success"></i>' : '<i class="fas fa-times text-danger"></i>';
            html += `<div class="small">${icon} <code>${escapeHtml(v.pattern)}</code></div>`;
        });
        html += `</div></div>`;
    }
    
    // If none of the above matched, show raw JSON
    if (html === '' || (!result.output && !result.error && !result.config_lines && !result.parsed_output)) {
        // Remove known processed fields and show any remaining data
        const remaining = {...result};
        delete remaining.status;
        delete remaining.host;
        delete remaining.command;
        delete remaining.error;
        delete remaining.output;
        delete remaining.save_output;
        delete remaining.config_lines;
        delete remaining.rendered_config;
        delete remaining.parsed_output;
        delete remaining.parser;
        delete remaining.validations;
        
        if (Object.keys(remaining).length > 0) {
            html += `<div class="mb-3">
                <strong>Additional Data:</strong>
                <pre class="bg-secondary bg-opacity-10 p-2 rounded mt-1 small">${escapeHtml(JSON.stringify(remaining, null, 2))}</pre>
            </div>`;
        }
    }
    
    // Fallback if still empty
    if (html === '') {
        html = `<pre class="mb-0">${escapeHtml(JSON.stringify(result, null, 2))}</pre>`;
    }
    
    return html;
}

/**
 * Format task type into a human-readable badge
 * @param {string} taskName - Full task name (e.g., "tasks.device_tasks.set_config")
 * @param {string|null} actionType - Explicit action type (deploy, delete, validate, etc.)
 * @returns {string} HTML badge for the task type
 */
function formatTaskType(taskName, actionType) {
    // Map action types to display labels and colors
    const actionTypeMap = {
        'deploy': { label: 'Deploy', icon: 'fa-rocket', color: 'primary' },
        'delete': { label: 'Delete', icon: 'fa-trash', color: 'danger' },
        'validate': { label: 'Validate', icon: 'fa-check-circle', color: 'success' },
        'healthcheck': { label: 'Health Check', icon: 'fa-heartbeat', color: 'success' },
        'backup': { label: 'Backup', icon: 'fa-save', color: 'info' },
        'command': { label: 'Command', icon: 'fa-terminal', color: 'secondary' },
        'restore': { label: 'Restore', icon: 'fa-undo', color: 'warning' },
        'test': { label: 'Test', icon: 'fa-plug', color: 'warning' }
    };

    // Prefer action_type if available (more accurate)
    if (actionType && actionTypeMap[actionType]) {
        const typeInfo = actionTypeMap[actionType];
        return `<span class="badge bg-${typeInfo.color}"><i class="fas ${typeInfo.icon}"></i> ${typeInfo.label}</span>`;
    }

    // Fallback: parse task_name for backwards compatibility
    if (!taskName) return '<span class="badge bg-secondary">Unknown</span>';

    // Extract the last part of the task name
    const parts = taskName.split('.');
    const action = parts[parts.length - 1] || '';

    // Map task names to display labels and colors
    const taskNameMap = {
        'set_config': { label: 'Config', icon: 'fa-cog', color: 'primary' },
        'get_config': { label: 'Get Config', icon: 'fa-download', color: 'info' },
        'validate_config': { label: 'Validate', icon: 'fa-check-circle', color: 'success' },
        'backup_device_config': { label: 'Backup', icon: 'fa-save', color: 'info' },
        'test_connectivity': { label: 'Test', icon: 'fa-plug', color: 'warning' }
    };

    const typeInfo = taskNameMap[action] || { label: action, icon: 'fa-cog', color: 'secondary' };

    return `<span class="badge bg-${typeInfo.color}"><i class="fas ${typeInfo.icon}"></i> ${typeInfo.label}</span>`;
}

/**
 * Escape HTML special characters
 */
function escapeHtml(text) {
    if (text === null || text === undefined) return '';
    return String(text)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}
