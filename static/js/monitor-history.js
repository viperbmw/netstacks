// Task History functionality for Monitor page
// Uses DB-only API - no Celery queries

function loadTaskHistory() {
    $('#history-loading').show();
    $('#history-container').hide();

    // Single API call - gets all task data from DB
    $.get('/api/tasks/metadata')
        .done(function(response) {
            const metadata = response.metadata || {};
            const tbody = $('#history-body');
            tbody.empty();

            // Filter for completed/failed tasks only
            const completedTasks = [];
            Object.entries(metadata).forEach(function([taskId, task]) {
                const status = task.status || 'pending';
                const statusLower = status.toLowerCase();

                if (statusLower === 'success' || statusLower === 'failure') {
                    completedTasks.push({
                        taskId: taskId,
                        status: status,
                        deviceName: task.device_name,
                        completedAt: task.completed_at,
                        createdAt: task.created_at
                    });
                }
            });

            if (completedTasks.length === 0) {
                $('#no-history').show();
                $('table', '#history-container').hide();
                $('#history-loading').hide();
                $('#history-container').show();
                return;
            }

            $('#no-history').hide();
            $('table', '#history-container').show();

            // Sort by completed time, most recent first
            completedTasks.sort((a, b) => {
                if (!a.completedAt) return 1;
                if (!b.completedAt) return -1;
                return new Date(b.completedAt) - new Date(a.completedAt);
            });

            // Show only last 20
            completedTasks.slice(0, 20).forEach(function(item) {
                const status = item.status;
                const taskId = item.taskId;
                const endedDate = item.completedAt ? formatDate(item.completedAt) : 'N/A';

                let statusBadge = 'badge-secondary';
                if (status === 'success') statusBadge = 'badge-completed';
                else if (status === 'failure') statusBadge = 'badge-failed';

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

            $('#history-loading').hide();
            $('#history-container').show();
        })
        .fail(function() {
            $('#history-loading').hide();
            $('#history-container').show();
            $('#no-history').html('<i class="fas fa-exclamation-triangle"></i> Error loading task history').show();
        });
}
