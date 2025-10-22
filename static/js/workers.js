// Workers page JavaScript

$(document).ready(function() {
    loadWorkers();

    // Refresh button
    $('#refresh-workers').click(function() {
        loadWorkers();
    });

    // Auto-refresh every 10 seconds
    setInterval(loadWorkers, 10000);
});

function loadWorkers() {
    $('#workers-loading').show();
    $('#workers-container').hide();

    // Fetch both workers and tasks to determine which workers are busy
    $.when(
        $.get('/api/workers'),
        $.get('/api/tasks')
    ).done(function(workersResponse, tasksResponse) {
        const workers = workersResponse[0];
        const tasks = tasksResponse[0];

        const tbody = $('#workers-body');
        tbody.empty();

        if (!workers || workers.length === 0) {
            tbody.append('<tr><td colspan="4" class="text-center text-muted">No active workers</td></tr>');
            $('#worker-count-display').text('0');
            $('#workers-loading').hide();
            $('#workers-container').show();
            return;
        }

        // Get list of running task IDs
        const taskIds = tasks?.data?.task_id || [];

        // Build a map of worker -> current task by checking running tasks
        const workerTasks = {};
        let tasksChecked = 0;

        if (taskIds.length === 0) {
            // No tasks - all workers are idle
            displayWorkers(workers, {});
        } else {
            // Check each task to see which worker is handling it
            taskIds.slice(0, 20).forEach(function(taskId) {
                $.get('/api/task/' + taskId)
                    .done(function(taskResponse) {
                        const task = taskResponse.data || taskResponse;
                        const status = task.task_status || task.status || 'unknown';

                        // If task is running/started, try to find which worker has it
                        if (status === 'started' || status === 'running') {
                            // Netstacker doesn't expose worker assignment, so we'll show task ID
                            // We can't directly map task to worker, so mark as "active"
                            if (task.worker_name) {
                                workerTasks[task.worker_name] = taskId;
                            }
                        }
                    })
                    .always(function() {
                        tasksChecked++;
                        if (tasksChecked === Math.min(taskIds.length, 20)) {
                            displayWorkers(workers, workerTasks);
                        }
                    });
            });

            // If no tasks to check, display immediately
            if (taskIds.length === 0) {
                displayWorkers(workers, workerTasks);
            }
        }
    }).fail(function() {
        $('#workers-body').html('<tr><td colspan="4" class="text-center text-danger">Failed to load workers</td></tr>');
        $('#workers-loading').hide();
        $('#workers-container').show();
    });
}

function displayWorkers(data, workerTasks) {
    const tbody = $('#workers-body');
    tbody.empty();

    if (!data || data.length === 0) {
        tbody.append('<tr><td colspan="4" class="text-center text-muted">No active workers</td></tr>');
        $('#worker-count-display').text('0');
    } else {
        $('#worker-count-display').text(data.length);

        data.forEach(function(worker) {
            const workerType = worker.name.includes('pinned') ? 'Pinned' : 'FIFO';

            // Determine state based on worker data and assigned tasks
            let state = 'idle';
            let stateBadge = 'bg-success';
            let currentJob = 'None';

            // Check if this worker has a task assigned (from workerTasks map)
            if (workerTasks[worker.name]) {
                state = 'busy';
                stateBadge = 'bg-primary';
                currentJob = workerTasks[worker.name];
            } else if (worker.state) {
                // If worker has explicit state field (some Netstacker versions)
                state = worker.state;
                if (state === 'busy') stateBadge = 'bg-primary';
                else if (state === 'failed') stateBadge = 'bg-danger';
            } else if (worker.current_job || worker.current_job_id) {
                // Worker has a current job - it's busy
                state = 'busy';
                stateBadge = 'bg-primary';
                currentJob = worker.current_job || worker.current_job_id;
            } else {
                // Check if worker has recent activity (heartbeat within last 60 seconds)
                const lastHeartbeat = new Date(worker.last_heartbeat);
                const now = new Date();
                const secondsSinceHeartbeat = (now - lastHeartbeat) / 1000;

                if (secondsSinceHeartbeat > 90) {
                    state = 'stale';
                    stateBadge = 'bg-warning text-dark';
                } else {
                    state = 'idle';
                    stateBadge = 'bg-success';
                }
            }

            // Worker stats
            const successCount = worker.successful_job_count || 0;
            const failedCount = worker.failed_job_count || 0;
            const totalJobs = successCount + failedCount;
            const workingTime = worker.total_working_time ? worker.total_working_time.toFixed(2) + 's' : '0s';

            const row = `
                <tr>
                    <td>
                        <strong>${worker.name || 'Unknown'}</strong><br>
                        <small class="text-muted">PID: ${worker.pid || 'N/A'} | Host: ${worker.hostname || 'N/A'}</small>
                    </td>
                    <td><span class="badge bg-info">${workerType}</span></td>
                    <td>
                        <span class="badge ${stateBadge}">${state.toUpperCase()}</span><br>
                        <small class="text-muted">Jobs: ${totalJobs} (✓${successCount} ✗${failedCount})</small><br>
                        <small class="text-muted">Time: ${workingTime}</small>
                    </td>
                    <td><small class="font-monospace text-muted">${currentJob}</small></td>
                </tr>
            `;
            tbody.append(row);
        });
    }

    $('#workers-loading').hide();
    $('#workers-container').show();
}
