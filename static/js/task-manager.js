/**
 * Global Task Manager
 * Persists running task state across page navigation and provides
 * a global indicator in the navbar for long-running tasks.
 */

const TaskManager = {
    // Storage key for persisting tasks
    STORAGE_KEY: 'netstacks_running_tasks',

    // Poll interval in ms
    POLL_INTERVAL: 2000,

    // Internal state
    _tasks: [],
    _pollInterval: null,
    _initialized: false,

    /**
     * Initialize the task manager
     */
    init: function() {
        if (this._initialized) return;
        this._initialized = true;

        // Load persisted tasks
        this._loadFromStorage();

        // Create navbar indicator if it doesn't exist
        this._createNavbarIndicator();

        // Start polling if there are active tasks
        if (this._tasks.length > 0) {
            this._startPolling();
            this._updateNavbarIndicator();
        }

        // Listen for storage changes from other tabs
        window.addEventListener('storage', (e) => {
            if (e.key === this.STORAGE_KEY) {
                this._loadFromStorage();
                this._updateNavbarIndicator();
            }
        });

        console.log('TaskManager initialized with', this._tasks.length, 'tasks');
    },

    /**
     * Add tasks to be tracked
     * @param {Array} tasks - Array of task objects with {task_id, device, type, started_at}
     */
    addTasks: function(tasks) {
        const now = new Date().toISOString();
        tasks.forEach(task => {
            // Add metadata
            task.started_at = task.started_at || now;
            task.type = task.type || 'backup';
            task.status = 'running';

            // Avoid duplicates
            const existing = this._tasks.find(t => t.task_id === task.task_id);
            if (!existing) {
                this._tasks.push(task);
            }
        });

        this._saveToStorage();
        this._updateNavbarIndicator();
        this._startPolling();

        // Dispatch event for page-specific handlers
        window.dispatchEvent(new CustomEvent('tasksAdded', { detail: { tasks } }));
    },

    /**
     * Get all running tasks
     */
    getTasks: function() {
        return this._tasks.filter(t => t.status === 'running');
    },

    /**
     * Get all tasks (including completed)
     */
    getAllTasks: function() {
        return [...this._tasks];
    },

    /**
     * Check if there are any running tasks
     */
    hasRunningTasks: function() {
        return this._tasks.some(t => t.status === 'running');
    },

    /**
     * Clear completed tasks from storage
     */
    clearCompleted: function() {
        this._tasks = this._tasks.filter(t => t.status === 'running');
        this._saveToStorage();
    },

    /**
     * Clear all tasks
     */
    clearAll: function() {
        this._tasks = [];
        this._saveToStorage();
        this._stopPolling();
        this._updateNavbarIndicator();
    },

    // Private methods

    _loadFromStorage: function() {
        try {
            const stored = localStorage.getItem(this.STORAGE_KEY);
            if (stored) {
                this._tasks = JSON.parse(stored);
                // Filter out very old tasks (older than 1 hour)
                const oneHourAgo = new Date(Date.now() - 60 * 60 * 1000).toISOString();
                this._tasks = this._tasks.filter(t => t.started_at > oneHourAgo || t.status === 'running');
            }
        } catch (e) {
            console.error('Failed to load tasks from storage:', e);
            this._tasks = [];
        }
    },

    _saveToStorage: function() {
        try {
            localStorage.setItem(this.STORAGE_KEY, JSON.stringify(this._tasks));
        } catch (e) {
            console.error('Failed to save tasks to storage:', e);
        }
    },

    _createNavbarIndicator: function() {
        // Check if indicator already exists
        if ($('#task-indicator').length > 0) return;

        // Add indicator to navbar (before logout)
        const indicator = `
            <li class="nav-item" id="task-indicator" style="display: none;">
                <a class="nav-link" href="/devices" title="View running tasks">
                    <span class="position-relative">
                        <i class="fas fa-tasks"></i>
                        <span class="position-absolute top-0 start-100 translate-middle badge rounded-pill bg-warning" id="task-count">
                            0
                        </span>
                    </span>
                    <span class="ms-1" id="task-indicator-text">Tasks</span>
                </a>
            </li>
        `;

        // Insert before the logout link
        const $logoutItem = $('a.nav-link[href="/logout"]').parent();
        if ($logoutItem.length > 0) {
            $(indicator).insertBefore($logoutItem);
        }
    },

    _updateNavbarIndicator: function() {
        const runningCount = this._tasks.filter(t => t.status === 'running').length;
        const $indicator = $('#task-indicator');
        const $count = $('#task-count');
        const $text = $('#task-indicator-text');

        if (runningCount > 0) {
            $indicator.show();
            $count.text(runningCount);
            $text.html('<i class="fas fa-spinner fa-spin"></i> Running');
        } else {
            // Keep showing briefly after completion
            const recentCompleted = this._tasks.filter(t =>
                t.status === 'success' || t.status === 'failed'
            ).length;

            if (recentCompleted > 0) {
                $indicator.show();
                $count.text(recentCompleted).removeClass('bg-warning').addClass('bg-success');
                $text.text('Complete');

                // Hide after 5 seconds
                setTimeout(() => {
                    if (!this.hasRunningTasks()) {
                        $indicator.fadeOut();
                        this.clearCompleted();
                    }
                }, 5000);
            } else {
                $indicator.hide();
            }
        }

        // Dispatch event for page-specific UI updates
        window.dispatchEvent(new CustomEvent('taskStatusUpdate', {
            detail: {
                running: runningCount,
                tasks: this._tasks
            }
        }));
    },

    _startPolling: function() {
        if (this._pollInterval) return;

        this._pollInterval = setInterval(() => this._pollTasks(), this.POLL_INTERVAL);
        // Poll immediately
        this._pollTasks();
    },

    _stopPolling: function() {
        if (this._pollInterval) {
            clearInterval(this._pollInterval);
            this._pollInterval = null;
        }
    },

    _pollTasks: function() {
        const runningTasks = this._tasks.filter(t => t.status === 'running');

        if (runningTasks.length === 0) {
            this._stopPolling();
            return;
        }

        runningTasks.forEach(task => {
            // Include snapshot_id in the polling request if available
            let pollUrl = `/api/config-backups/task/${task.task_id}`;
            if (task.snapshot_id) {
                pollUrl += `?snapshot_id=${task.snapshot_id}`;
            }

            $.get(pollUrl)
                .done(response => {
                    let newStatus = null;

                    if (response.status === 'success' || response.saved) {
                        newStatus = 'success';
                    } else if (response.status === 'failed' ||
                               (response.result && response.result.status === 'failed')) {
                        newStatus = 'failed';
                    } else if (response.status === 'PENDING' || response.status === 'STARTED') {
                        // Still running
                        newStatus = 'running';
                    }

                    if (newStatus && newStatus !== task.status) {
                        task.status = newStatus;
                        task.completed_at = new Date().toISOString();
                        this._saveToStorage();
                        this._updateNavbarIndicator();

                        // Dispatch completion event
                        window.dispatchEvent(new CustomEvent('taskCompleted', {
                            detail: { task, status: newStatus }
                        }));
                    }
                })
                .fail(() => {
                    // If API fails, might be complete or error
                    console.warn('Failed to poll task:', task.task_id);
                });
        });
    }
};

// Auto-initialize when DOM is ready
$(document).ready(function() {
    TaskManager.init();
});
