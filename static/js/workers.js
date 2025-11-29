// Workers page JavaScript - Celery Workers

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

    $.get('/api/workers')
        .done(function(workers) {
            displayWorkers(workers);
        })
        .fail(function(xhr) {
            const errorMsg = xhr.responseJSON?.error || 'Failed to connect to workers API';
            $('#workers-body').html(`<tr><td colspan="5" class="text-center text-danger"><i class="fas fa-exclamation-triangle"></i> ${errorMsg}</td></tr>`);
            $('#workers-loading').hide();
            $('#workers-container').show();

            // Update stats to show error state
            $('#total-workers-count').text('0');
            $('#active-workers-count').text('0');
            $('#active-tasks-count').text('0');
            $('#broker-status').text('Error');
        });
}

function displayWorkers(data) {
    const tbody = $('#workers-body');
    tbody.empty();

    // Handle case where data is an error response
    if (data && data.error) {
        tbody.append(`<tr><td colspan="5" class="text-center text-danger"><i class="fas fa-exclamation-triangle"></i> ${data.error}</td></tr>`);
        $('#workers-loading').hide();
        $('#workers-container').show();
        return;
    }

    // Handle no workers or single "offline" placeholder
    if (!data || data.length === 0 || (data.length === 1 && data[0].status === 'offline')) {
        tbody.append(`
            <tr>
                <td colspan="5" class="text-center">
                    <div class="py-4">
                        <i class="fas fa-server fa-3x text-muted mb-3 d-block"></i>
                        <p class="text-muted mb-2">No Celery workers are currently connected</p>
                        <small class="text-muted">Workers should automatically connect when the celery-worker container starts</small>
                    </div>
                </td>
            </tr>
        `);

        $('#total-workers-count').text('0');
        $('#active-workers-count').text('0');
        $('#active-tasks-count').text('0');
        $('#broker-status').html('<span class="text-warning">Waiting</span>');

        $('#workers-loading').hide();
        $('#workers-container').show();
        $('#tasks-loading').hide();
        $('#registered-tasks-container').html('<p class="text-muted text-center">No workers available to query tasks</p>').show();
        return;
    }

    // Calculate stats
    let totalWorkers = data.length;
    let onlineWorkers = data.filter(w => w.status === 'online').length;
    let totalActiveTasks = data.reduce((sum, w) => sum + (w.active_tasks || 0), 0);
    let brokerConnected = data.some(w => w.broker);

    // Update stats cards
    $('#total-workers-count').text(totalWorkers);
    $('#active-workers-count').text(onlineWorkers);
    $('#active-tasks-count').text(totalActiveTasks);
    $('#broker-status').html(brokerConnected ?
        '<span class="text-success"><i class="fas fa-check-circle"></i> Redis</span>' :
        '<span class="text-warning">Unknown</span>'
    );

    // Display workers
    data.forEach(function(worker) {
        // Determine status badge
        let statusBadge = 'bg-secondary';
        let statusText = worker.status || 'unknown';

        if (worker.status === 'online') {
            statusBadge = worker.active_tasks > 0 ? 'bg-primary' : 'bg-success';
            statusText = worker.active_tasks > 0 ? 'Busy' : 'Ready';
        } else if (worker.status === 'offline') {
            statusBadge = 'bg-danger';
            statusText = 'Offline';
        }

        // Format worker name
        const workerName = worker.name || 'Unknown Worker';
        const workerShortName = workerName.split('@')[0] || workerName;
        const workerHost = workerName.split('@')[1] || 'localhost';

        // Pool info
        const poolInfo = worker.pool || 'N/A';

        // Active tasks
        const activeTasks = worker.active_tasks || 0;

        // Broker
        const broker = worker.broker || 'redis';

        const row = `
            <tr>
                <td>
                    <strong><i class="fas fa-microchip text-primary"></i> ${escapeHtml(workerShortName)}</strong>
                    <br><small class="text-muted">${escapeHtml(workerHost)}</small>
                </td>
                <td><span class="badge ${statusBadge}">${statusText}</span></td>
                <td><span class="badge bg-secondary">${poolInfo}</span></td>
                <td>
                    ${activeTasks > 0 ?
                        `<span class="badge bg-info">${activeTasks} running</span>` :
                        '<span class="text-muted">Idle</span>'
                    }
                </td>
                <td><small class="text-muted"><i class="fas fa-database"></i> ${escapeHtml(broker)}</small></td>
            </tr>
        `;
        tbody.append(row);
    });

    $('#workers-loading').hide();
    $('#workers-container').show();

    // Load registered tasks from first online worker
    loadRegisteredTasks();
}

function loadRegisteredTasks() {
    $.get('/api/workers/tasks')
        .done(function(data) {
            $('#tasks-loading').hide();

            if (data && data.tasks && data.tasks.length > 0) {
                const container = $('#registered-tasks-list');
                container.empty();

                // Group tasks by prefix
                const taskGroups = {};
                data.tasks.forEach(task => {
                    const prefix = task.split('.')[0] || 'other';
                    if (!taskGroups[prefix]) taskGroups[prefix] = [];
                    taskGroups[prefix].push(task);
                });

                // Display task groups
                Object.keys(taskGroups).sort().forEach(group => {
                    const tasks = taskGroups[group];
                    const groupHtml = `
                        <div class="col-md-4 mb-3">
                            <div class="card h-100">
                                <div class="card-header py-2">
                                    <strong><i class="fas fa-folder text-warning"></i> ${escapeHtml(group)}</strong>
                                    <span class="badge bg-secondary float-end">${tasks.length}</span>
                                </div>
                                <div class="card-body py-2">
                                    <ul class="list-unstyled mb-0" style="font-size: 0.85rem;">
                                        ${tasks.map(t => `<li><i class="fas fa-code text-muted"></i> ${escapeHtml(t.split('.').slice(1).join('.') || t)}</li>`).join('')}
                                    </ul>
                                </div>
                            </div>
                        </div>
                    `;
                    container.append(groupHtml);
                });

                $('#registered-tasks-container').show();
            } else {
                $('#registered-tasks-container').html('<p class="text-muted text-center">No registered tasks found</p>').show();
            }
        })
        .fail(function() {
            $('#tasks-loading').hide();
            $('#registered-tasks-container').html('<p class="text-muted text-center">Could not load registered tasks</p>').show();
        });
}

function escapeHtml(text) {
    if (!text) return '';
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}
