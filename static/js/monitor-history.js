// Task History functionality for Monitor page

function loadTaskHistory() {
    $('#history-loading').show();
    $('#history-container').hide();

    // Get all tasks and filter for completed ones
    $.get('/api/tasks')
        .done(function(data) {
            const tbody = $('#history-body');
            tbody.empty();

            // API returns: {status: 'success', data: {task_id: ['id1', 'id2', ...]}}
            let taskIds = [];
            if (data.data && data.data.task_id && Array.isArray(data.data.task_id)) {
                taskIds = data.data.task_id;
            }

            if (taskIds.length === 0) {
                $('#no-history').show();
                $('#history-loading').hide();
                $('#history-container').show();
                return;
            }

            const completedTasks = [];
            let fetchedCount = 0;

            // Fetch all tasks and filter for completed
            taskIds.forEach(function(taskId) {
                $.get('/api/task/' + taskId)
                    .done(function(taskResponse) {
                        const task = taskResponse.data || taskResponse;
                        const status = task.task_status || task.status || 'unknown';

                        fetchedCount++;

                        // Only include finished or failed tasks
                        const statusLower = status.toLowerCase();
                        if (statusLower === 'finished' || statusLower === 'completed' || statusLower === 'success' ||
                            statusLower === 'failed' || statusLower === 'failure' || statusLower === 'error') {
                            completedTasks.push({
                                taskId: taskId,
                                status: status,
                                ended: task.task_meta?.ended_at || task.ended_at,
                                task: task
                            });
                        }

                        if (fetchedCount === taskIds.length) {
                            displayTaskHistory(completedTasks);
                        }
                    })
                    .fail(function() {
                        fetchedCount++;
                        if (fetchedCount === taskIds.length) {
                            displayTaskHistory(completedTasks);
                        }
                    });
            });
        })
        .fail(function() {
            $('#history-loading').hide();
            $('#history-container').show();
            $('#no-history').html('<i class="fas fa-exclamation-triangle"></i> Error loading task history').show();
        });
}

function displayTaskHistory(tasks) {
    const tbody = $('#history-body');
    tbody.empty();

    if (tasks.length === 0) {
        $('#no-history').show();
        $('table', '#history-container').hide();
    } else {
        $('#no-history').hide();
        $('table', '#history-container').show();

        // Sort by ended time, most recent first
        tasks.sort((a, b) => {
            if (!a.ended) return 1;
            if (!b.ended) return -1;
            return new Date(b.ended) - new Date(a.ended);
        });

        // Show only last 20
        tasks.slice(0, 20).forEach(function(item) {
            const status = item.status;
            const taskId = item.taskId;
            const endedDate = item.ended ? formatDate(item.ended) : 'N/A';

            let statusBadge = 'secondary';
            const statusLower = status.toLowerCase();
            if (statusLower === 'finished' || statusLower === 'completed' || statusLower === 'success') statusBadge = 'badge-completed';
            else if (statusLower === 'failed' || statusLower === 'failure' || statusLower === 'error') statusBadge = 'badge-failed';

            const shortId = taskId.length > 16 ? taskId.substring(0, 16) + '...' : taskId;

            tbody.append(`
                <tr>
                    <td><small class="font-monospace">${shortId}</small></td>
                    <td><span class="badge ${statusBadge}">${status}</span></td>
                    <td><small>${endedDate}</small></td>
                    <td>
                        <button class="btn btn-sm btn-primary view-history-btn" data-task-id="${taskId}">
                            <i class="fas fa-eye"></i> View
                        </button>
                    </td>
                </tr>
            `);
        });
    }

    $('#history-loading').hide();
    $('#history-container').show();
}
