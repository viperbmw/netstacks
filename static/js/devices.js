// Devices page JavaScript

let allDevices = [];
let selectedDevices = [];
let deviceBackups = {};  // Map of device_name -> latest backup info
let runningTasks = [];
let taskPollInterval = null;
let backupsPage = 0;
const backupsPageSize = 50;

$(document).ready(function() {
    loadDevices();
    loadBackupSummary();
    loadBackupSchedule();
    loadDeviceOverrides();
    loadRecentSnapshots();

    // Restore running tasks from TaskManager on page load
    restoreRunningTasks();

    // Show/hide add device form
    $('#show-add-device-form-btn').click(function() {
        $('#add-device-form-container').slideDown();
        $('#device-name').focus();
    });

    $('#cancel-add-device-btn').click(function() {
        $('#add-device-form-container').slideUp();
        $('#add-device-form')[0].reset();
    });

    // Add manual device form submission
    $('#add-device-form').submit(function(e) {
        e.preventDefault();
        addManualDevice();
    });

    // Clear cache button
    $('#clear-cache-btn').click(function() {
        clearCacheAndReload();
    });

    // Search filter
    $('#device-search').on('input', function() {
        const searchTerm = $(this).val().toLowerCase();
        filterDevices(searchTerm);
    });

    // Select all checkbox in header
    $('#select-all-checkbox').change(function() {
        const isChecked = $(this).is(':checked');
        $('.device-checkbox').prop('checked', isChecked);
        updateSelectedDevices();
    });

    // Select all button
    $('#select-all-btn').click(function() {
        $('.device-checkbox').prop('checked', true);
        $('#select-all-checkbox').prop('checked', true);
        updateSelectedDevices();
    });

    // Select none button
    $('#select-none-btn').click(function() {
        $('.device-checkbox').prop('checked', false);
        $('#select-all-checkbox').prop('checked', false);
        updateSelectedDevices();
    });

    // Clear selection button
    $('#clear-selection-btn').click(function() {
        $('.device-checkbox').prop('checked', false);
        $('#select-all-checkbox').prop('checked', false);
        updateSelectedDevices();
    });

    // Bulk action buttons
    $('#bulk-getconfig-btn').click(function() {
        if (selectedDevices.length === 0) {
            alert('Please select at least one device');
            return;
        }
        showBulkGetConfigModal();
    });

    $('#bulk-setconfig-btn').click(function() {
        if (selectedDevices.length === 0) {
            alert('Please select at least one device');
            return;
        }
        showBulkSetConfigModal();
    });

    // Execute bulk getconfig
    $('#execute-bulk-getconfig-btn').click(function() {
        executeBulkGetConfig();
    });

    // Execute bulk setconfig
    $('#execute-bulk-setconfig-btn').click(function() {
        executeBulkSetConfig();
    });

    // Bulk test connectivity
    $('#bulk-test-btn').click(function() {
        if (selectedDevices.length === 0) {
            alert('Please select at least one device');
            return;
        }
        executeBulkTestConnectivity();
    });

    // Bulk backup
    $('#bulk-backup-btn').click(function() {
        if (selectedDevices.length === 0) {
            alert('Please select at least one device');
            return;
        }
        executeBulkBackup();
    });

    // Bulk delete (only manual devices)
    $('#bulk-delete-btn').click(function() {
        if (selectedDevices.length === 0) {
            alert('Please select at least one device');
            return;
        }
        executeBulkDelete();
    });

    // Template source toggle
    $('input[name="bulk-set-config-source"]').change(function() {
        if ($(this).val() === 'manual') {
            $('#bulk-set-manual-container').show();
            $('#bulk-set-template-container').hide();
        } else {
            $('#bulk-set-manual-container').hide();
            $('#bulk-set-template-container').show();
            loadBulkTemplates();
        }
    });

    // Template selection
    $('#bulk-set-template-select').change(function() {
        if ($(this).val()) {
            $('#bulk-set-template-vars-container').show();
        } else {
            $('#bulk-set-template-vars-container').hide();
        }
    });
});

function loadDevices() {
    $('#devices-loading').show();
    $('#devices-container').hide();

    // Get filters from settings
    let filters = [];
    try {
        const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
        filters = settings.netbox_filters || [];
    } catch (e) {
        console.error('Error reading filters from settings:', e);
    }

    // Show active filters in UI
    showActiveFilters();

    // Make POST request with filters
    $.ajax({
        url: '/api/devices/list',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ filters: filters })
    })
        .done(function(data) {
            if (data.success && data.data && data.data.devices) {
                allDevices = data.data.devices;
                displayDevices(allDevices);
                $('#device-count-display').text(allDevices.length);
            } else if (data.success && data.devices) {
                // Legacy format support
                allDevices = data.devices;
                displayDevices(allDevices);
                $('#device-count-display').text(allDevices.length);
            } else {
                $('#devices-body').html('<tr><td colspan="3" class="text-center text-danger">Error loading devices</td></tr>');
            }
            $('#devices-loading').hide();
            $('#devices-container').show();
        })
        .fail(function() {
            $('#devices-body').html('<tr><td colspan="3" class="text-center text-danger">Failed to load devices</td></tr>');
            $('#devices-loading').hide();
            $('#devices-container').show();
        });
}

function displayDevices(devices) {
    const tbody = $('#devices-body');
    tbody.empty();

    if (devices.length === 0) {
        tbody.append('<tr><td colspan="7" class="text-center text-muted">No devices found</td></tr>');
        return;
    }

    devices.forEach(function(device) {
        const deviceType = device.device_type || 'N/A';
        const source = device.source || 'netbox';
        const sourceBadge = source === 'manual' ?
            '<span class="badge bg-primary">Manual</span>' :
            '<span class="badge bg-info">Netbox</span>';

        // Get management IP from device data
        const managementIp = device.primary_ip || device.host || device.ip_address || '-';

        // Get backup info for this device
        const backup = deviceBackups[device.name];
        let backupInfo = '<span class="text-muted">Never</span>';
        let backupBadge = '';
        if (backup) {
            const backupDate = new Date(backup.created_at);
            const now = new Date();
            const daysSince = Math.floor((now - backupDate) / (1000 * 60 * 60 * 24));

            if (daysSince === 0) {
                backupInfo = '<span class="text-success">Today</span>';
            } else if (daysSince === 1) {
                backupInfo = '<span class="text-success">Yesterday</span>';
            } else if (daysSince < 7) {
                backupInfo = `<span class="text-warning">${daysSince}d ago</span>`;
            } else {
                backupInfo = `<span class="text-danger">${daysSince}d ago</span>`;
            }

            // Add view button if backup exists
            backupBadge = `<button class="btn btn-sm btn-link p-0 ms-1 view-device-backup-btn" data-id="${backup.backup_id}" data-device="${device.name}" title="View backup">
                <i class="fas fa-eye"></i>
            </button>`;
        }

        const deleteBtn = source === 'manual' ?
            `<button class="btn btn-sm btn-outline-danger delete-manual-device-btn" data-device="${device.name}" title="Delete device">
                <i class="fas fa-trash"></i>
             </button>` : '';

        const backupBtn = `<button class="btn btn-sm btn-outline-primary backup-device-btn me-1" data-device="${device.name}" title="Backup now">
            <i class="fas fa-download"></i>
        </button>`;

        // Check if device has overrides
        const hasOverride = deviceOverrides[device.name];
        const overrideIndicator = hasOverride ? '<i class="fas fa-cog text-warning ms-1" title="Has custom settings"></i>' : '';

        const editBtn = `<button class="btn btn-sm btn-outline-secondary edit-device-btn me-1" data-device="${device.name}" title="Edit device settings">
            <i class="fas fa-edit"></i>
        </button>`;

        const testBtn = `<button class="btn btn-sm btn-outline-info test-connectivity-btn me-1" data-device="${device.name}" title="Test connectivity">
            <i class="fas fa-plug"></i>
        </button>`;

        const row = `
            <tr>
                <td>
                    <input type="checkbox" class="form-check-input device-checkbox" data-device="${device.name}">
                </td>
                <td><strong>${device.name}</strong>${overrideIndicator}</td>
                <td><code class="text-muted">${escapeHtml(managementIp)}</code></td>
                <td>${deviceType}</td>
                <td>${sourceBadge}</td>
                <td>${backupInfo}${backupBadge}</td>
                <td>${editBtn}${testBtn}${backupBtn}${deleteBtn}</td>
            </tr>
        `;
        tbody.append(row);
    });

    // Attach change handler to checkboxes
    $('.device-checkbox').change(function() {
        updateSelectedDevices();
    });

    // Attach click handler to delete buttons
    $('.delete-manual-device-btn').click(function() {
        const deviceName = $(this).data('device');
        deleteManualDevice(deviceName);
    });

    // Attach click handler to backup buttons
    $('.backup-device-btn').click(function() {
        const deviceName = $(this).data('device');
        backupSingleDevice(deviceName);
    });

    // Attach click handler to view backup buttons
    $('.view-device-backup-btn').click(function() {
        const backupId = $(this).data('id');
        const deviceName = $(this).data('device');
        viewBackup(backupId, deviceName);
    });

    // Attach click handler to edit device buttons
    $('.edit-device-btn').click(function() {
        const deviceName = $(this).data('device');
        openEditDeviceModal(deviceName);
    });

    // Attach click handler to test connectivity buttons
    $('.test-connectivity-btn').click(function() {
        const deviceName = $(this).data('device');
        testDeviceConnectivity(deviceName, $(this));
    });
}

function filterDevices(searchTerm) {
    if (!searchTerm) {
        displayDevices(allDevices);
        $('#device-count-display').text(allDevices.length);
        return;
    }

    const filtered = allDevices.filter(function(device) {
        return device.name.toLowerCase().includes(searchTerm);
    });

    displayDevices(filtered);
    $('#device-count-display').text(filtered.length);
}

function updateSelectedDevices() {
    selectedDevices = [];
    $('.device-checkbox:checked').each(function() {
        selectedDevices.push($(this).data('device'));
    });

    // Update selected count display
    $('#selected-count').text(selectedDevices.length);

    // Show/hide bulk actions bar
    if (selectedDevices.length > 0) {
        $('#bulk-actions-bar').css('display', 'flex');
    } else {
        $('#bulk-actions-bar').hide();
    }
}

function showBulkGetConfigModal() {
    // Pre-fill with settings if available
    if (window.getAppSettings) {
        const settings = window.getAppSettings();
        $('#bulk-get-username').val(settings.default_username || '');
        $('#bulk-get-password').val(settings.default_password || '');
    }

    const modal = new bootstrap.Modal(document.getElementById('bulkGetConfigModal'));
    modal.show();
}

function showBulkSetConfigModal() {
    // Pre-fill with settings if available
    if (window.getAppSettings) {
        const settings = window.getAppSettings();
        $('#bulk-set-username').val(settings.default_username || '');
        $('#bulk-set-password').val(settings.default_password || '');
    }

    const modal = new bootstrap.Modal(document.getElementById('bulkSetConfigModal'));
    modal.show();
}

function loadBulkTemplates() {
    const select = $('#bulk-set-template-select');
    select.html('<option value="">Loading templates...</option>');

    $.get('/api/templates')
        .done(function(data) {
            select.empty();
            select.append('<option value="">Select a template...</option>');

            if (data.success && data.templates && data.templates.length > 0) {
                data.templates.forEach(function(template) {
                    const templateName = template.name || template;
                    select.append(`<option value="${templateName}">${templateName}</option>`);
                });
            } else {
                select.append('<option value="">No templates found</option>');
            }
        })
        .fail(function() {
            select.html('<option value="">Error loading templates</option>');
        });
}

function executeBulkGetConfig() {
    const library = $('#bulk-get-library').val();
    const command = $('#bulk-get-command').val();
    const username = $('#bulk-get-username').val();
    const password = $('#bulk-get-password').val();
    const useTextFsm = $('#bulk-get-use-textfsm').is(':checked');

    if (!command) {
        alert('Please enter a command');
        return;
    }

    // Use default credentials if not provided
    const creds = loadDefaultCredentials();
    const finalUsername = username || creds.username;
    const finalPassword = password || creds.password;

    if (!finalUsername || !finalPassword) {
        alert('Please provide credentials or set defaults in Settings');
        return;
    }

    // Close the form modal
    bootstrap.Modal.getInstance(document.getElementById('bulkGetConfigModal')).hide();

    // Show status modal
    const statusModal = new bootstrap.Modal(document.getElementById('bulkStatusModal'));
    statusModal.show();

    let completed = 0;
    let successful = 0;
    let failed = 0;

    selectedDevices.forEach(function(device) {
        $.get('/api/device/' + encodeURIComponent(device) + '/connection-info')
            .done(function(deviceInfo) {
                const payload = {
                    connection_args: {
                        device_type: deviceInfo.device_type || "cisco_ios",
                        host: deviceInfo.ip_address || device,
                        username: finalUsername,
                        password: finalPassword,
                        timeout: 10
                    },
                    command: command,
                    queue_strategy: "pinned"
                };

                if (useTextFsm) {
                    payload.args = { use_textfsm: true };
                }

                $.ajax({
                    url: '/api/deploy/getconfig',
                    method: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({
                        library: library,
                        payload: payload,
                        device_name: device
                    }),
                    timeout: 30000
                })
                .done(function() {
                    successful++;
                })
                .fail(function() {
                    failed++;
                })
                .always(function() {
                    completed++;
                    updateBulkStatus(completed, successful, failed, selectedDevices.length);
                });
            })
            .fail(function() {
                failed++;
                completed++;
                updateBulkStatus(completed, successful, failed, selectedDevices.length);
            });
    });
}

function executeBulkSetConfig() {
    const library = $('#bulk-set-library').val();
    const username = $('#bulk-set-username').val();
    const password = $('#bulk-set-password').val();
    const dryRun = $('#bulk-set-dry-run').is(':checked');
    const configSource = $('input[name="bulk-set-config-source"]:checked').val();

    // Use default credentials if not provided
    const creds = loadDefaultCredentials();
    const finalUsername = username || creds.username;
    const finalPassword = password || creds.password;

    if (!finalUsername || !finalPassword) {
        alert('Please provide credentials or set defaults in Settings');
        return;
    }

    if (configSource === 'manual') {
        const config = $('#bulk-set-config').val();
        if (!config.trim()) {
            alert('Please enter configuration commands');
            return;
        }

        const commands = config.split('\n').filter(cmd => cmd.trim() !== '');
        executeBulkSetConfigWithCommands(library, commands, finalUsername, finalPassword, dryRun);
    } else {
        // Template mode
        const templateName = $('#bulk-set-template-select').val();
        if (!templateName) {
            alert('Please select a template');
            return;
        }

        const templateVarsText = $('#bulk-set-template-vars').val().trim();
        let templateVars = {};

        if (templateVarsText) {
            try {
                templateVars = JSON.parse(templateVarsText);
            } catch (e) {
                alert('Invalid JSON in template variables: ' + e.message);
                return;
            }
        }

        // Render template first
        $.ajax({
            url: '/api/templates/render',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify({
                template_name: templateName,
                variables: templateVars
            }),
            timeout: 10000
        })
        .done(function(data) {
            if (data.success && data.rendered_config) {
                const commands = data.rendered_config.split('\n').filter(cmd => cmd.trim() !== '');
                executeBulkSetConfigWithCommands(library, commands, finalUsername, finalPassword, dryRun);
            } else {
                alert('Failed to render template');
            }
        })
        .fail(function(xhr) {
            const error = xhr.responseJSON?.error || 'Failed to render template';
            alert('Error: ' + error);
        });
    }
}

function executeBulkSetConfigWithCommands(library, commands, username, password, dryRun) {
    // Close the form modal
    bootstrap.Modal.getInstance(document.getElementById('bulkSetConfigModal')).hide();

    // Show status modal
    const statusModal = new bootstrap.Modal(document.getElementById('bulkStatusModal'));
    statusModal.show();

    let completed = 0;
    let successful = 0;
    let failed = 0;

    const endpoint = dryRun ? '/api/deploy/setconfig/dry-run' : '/api/deploy/setconfig';

    selectedDevices.forEach(function(device) {
        $.get('/api/device/' + encodeURIComponent(device) + '/connection-info')
            .done(function(deviceInfo) {
                const payload = {
                    connection_args: {
                        device_type: deviceInfo.device_type || "cisco_ios",
                        host: deviceInfo.ip_address || device,
                        username: username,
                        password: password,
                        timeout: 10
                    },
                    config: commands,
                    queue_strategy: "pinned"
                };

                $.ajax({
                    url: endpoint,
                    method: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({
                        library: library,
                        payload: payload,
                        device_name: device
                    }),
                    timeout: 30000
                })
                .done(function() {
                    successful++;
                })
                .fail(function() {
                    failed++;
                })
                .always(function() {
                    completed++;
                    updateBulkStatus(completed, successful, failed, selectedDevices.length);
                });
            })
            .fail(function() {
                failed++;
                completed++;
                updateBulkStatus(completed, successful, failed, selectedDevices.length);
            });
    });
}

function updateBulkStatus(completed, successful, failed, total) {
    const statusContent = $('#bulk-status-content');

    const successRate = Math.round((successful / total) * 100);
    const progress = Math.round((completed / total) * 100);

    statusContent.html(`
        <div class="mb-3">
            <h6>Progress: ${completed} / ${total}</h6>
            <div class="progress">
                <div class="progress-bar" role="progressbar" style="width: ${progress}%" aria-valuenow="${progress}" aria-valuemin="0" aria-valuemax="100">${progress}%</div>
            </div>
        </div>
        <div class="row text-center">
            <div class="col-4">
                <div class="text-success">
                    <i class="fas fa-check-circle fa-2x"></i>
                    <p class="mb-0"><strong>${successful}</strong></p>
                    <small class="text-muted">Successful</small>
                </div>
            </div>
            <div class="col-4">
                <div class="text-danger">
                    <i class="fas fa-times-circle fa-2x"></i>
                    <p class="mb-0"><strong>${failed}</strong></p>
                    <small class="text-muted">Failed</small>
                </div>
            </div>
            <div class="col-4">
                <div class="text-info">
                    <i class="fas fa-clock fa-2x"></i>
                    <p class="mb-0"><strong>${total - completed}</strong></p>
                    <small class="text-muted">Pending</small>
                </div>
            </div>
        </div>
        ${completed === total ? '<div class="alert alert-success mt-3"><i class="fas fa-check"></i> Bulk operation completed!</div>' : ''}
    `);
}

function clearCacheAndReload() {
    const btn = $('#clear-cache-btn');
    btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> Clearing...');

    $.ajax({
        url: '/api/devices/clear-cache',
        method: 'POST'
    })
    .done(function(data) {
        if (data.success) {
            console.log('Cache cleared successfully');
            loadDevices();
        } else {
            alert('Failed to clear cache: ' + (data.error || 'Unknown error'));
        }
    })
    .fail(function() {
        alert('Failed to clear cache');
    })
    .always(function() {
        btn.prop('disabled', false).html('<i class="fas fa-sync-alt"></i> Clear Cache & Reload');
    });
}

// Manual device management functions
function addManualDevice() {
    const deviceData = {
        device_name: $('#device-name').val().trim(),
        device_type: $('#device-type').val(),
        host: $('#device-host').val().trim(),
        port: parseInt($('#device-port').val()) || 22,
        username: $('#device-username').val().trim(),
        password: $('#device-password').val()
    };

    // Validate required fields
    if (!deviceData.device_name || !deviceData.device_type || !deviceData.host) {
        alert('Please fill in all required fields');
        return;
    }

    $.ajax({
        url: '/api/manual-devices',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(deviceData)
    })
    .done(function(data) {
        if (data.success) {
            $('#add-device-form')[0].reset();
            $('#add-device-form-container').slideUp();
            clearCacheAndReload();
        } else {
            alert('Error adding device: ' + (data.error || 'Unknown error'));
        }
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON && xhr.responseJSON.error ? xhr.responseJSON.error : 'Failed to add device';
        alert('Error: ' + error);
    });
}

function deleteManualDevice(deviceName) {
    if (!confirm(`Are you sure you want to delete device "${deviceName}"?`)) {
        return;
    }

    $.ajax({
        url: `/api/manual-devices/${encodeURIComponent(deviceName)}`,
        method: 'DELETE'
    })
    .done(function(data) {
        if (data.success) {
            clearCacheAndReload();
        } else {
            alert('Error deleting device: ' + (data.error || 'Unknown error'));
        }
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON && xhr.responseJSON.error ? xhr.responseJSON.error : 'Failed to delete device';
        alert('Error: ' + error);
    });
}

function showActiveFilters() {
    try {
        const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
        const filters = settings.netbox_filters || [];

        if (filters.length > 0) {
            const filterText = filters.map(f => `${f.key}=${f.value}`).join(', ');
            $('#filter-info').html(`(Filters: ${filterText})`);
        } else {
            $('#filter-info').html('(No filters)');
        }
    } catch (e) {
        console.error('Error showing filters:', e);
    }
}

// ============================================================================
// Config Backup Functions
// ============================================================================

function loadBackupSummary() {
    $.get('/api/config-backups?limit=1')
        .done(function(response) {
            // Handle wrapped response (data.summary) or direct response (summary)
            const data = response.data || response;
            if (response.success && data.summary) {
                const s = data.summary;
                $('#total-backups').text(s.total_backups || 0);
                $('#devices-with-backups').text(s.unique_devices || 0);
                $('#latest-backup').text(s.latest_backup ? formatDate(s.latest_backup) : 'Never');

                // Store device backup info for display in table
                if (s.devices_with_backups) {
                    // Populate filter dropdown
                    const $filter = $('#filter-backup-device');
                    $filter.find('option:not(:first)').remove();
                    s.devices_with_backups.forEach(function(device) {
                        $filter.append(`<option value="${device}">${device}</option>`);
                    });
                }
            }
        });

    // Also load latest backup per device for the table
    loadDeviceBackupStatus();
}

function loadDeviceBackupStatus() {
    // Get latest backup for each device
    $.get('/api/config-backups?limit=500')
        .done(function(response) {
            // Handle wrapped response (data.backups) or direct response (backups)
            const data = response.data || response;
            if (response.success && data.backups) {
                deviceBackups = {};
                data.backups.forEach(function(backup) {
                    // Only keep the first (latest) backup per device
                    if (!deviceBackups[backup.device_name]) {
                        deviceBackups[backup.device_name] = backup;
                    }
                });
                // Re-render devices table to show backup status
                if (allDevices.length > 0) {
                    displayDevices(allDevices);
                }
            }
        });
}

function loadBackupSchedule() {
    $.get('/api/backup-schedule')
        .done(function(response) {
            if (response.success && response.schedule) {
                const s = response.schedule;
                $('#schedule-enabled').prop('checked', s.enabled);
                $('#schedule-interval').val(s.interval_hours || 24);
                $('#schedule-retention').val(s.retention_days || 30);
                $('#schedule-juniper-set').prop('checked', s.juniper_set_format !== false);
                $('#schedule-exclude').val((s.exclude_patterns || []).join(', '));
                $('#last-run').text(s.last_run ? formatDate(s.last_run) : 'Never');
                $('#next-run').text(s.next_run ? formatDate(s.next_run) : 'Not scheduled');
            }
        });
}

// Create Snapshot button handler
$('#create-snapshot-btn').click(function() {
    const deviceCount = allDevices.length || 0;
    if (deviceCount === 0) {
        alert('No devices loaded. Please ensure devices are loaded first.');
        return;
    }
    if (!confirm(`Create a snapshot of ${deviceCount} devices? This will backup the running config of all devices.`)) return;

    const $btn = $(this);
    $btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Creating...');

    $.ajax({
        url: '/api/config-backups/run-all',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            snapshot_type: 'manual'
        }),
        timeout: 300000  // 5 minute timeout for large device counts
    })
    .done(function(response) {
        if (response.success) {
            showToast('success', `Snapshot started: ${response.submitted} devices`);
            if (response.tasks && response.tasks.length > 0) {
                runningTasks = response.tasks;
                // Register with global TaskManager for persistence across page navigation
                if (typeof TaskManager !== 'undefined') {
                    TaskManager.addTasks(response.tasks.map(t => ({
                        task_id: t.task_id,
                        device: t.device,
                        type: 'snapshot',
                        snapshot_id: t.snapshot_id || response.snapshot_id
                    })));
                }
                // Store snapshot_id for polling
                currentSnapshotId = response.snapshot_id;
                showRunningTasks();
                startSnapshotTaskPolling();
            }
            // Reload snapshots list
            setTimeout(loadRecentSnapshots, 1000);
        } else {
            alert('Error: ' + response.error);
        }
    })
    .fail(function(xhr, textStatus, errorThrown) {
        // Don't show error if user navigated away (request aborted)
        if (textStatus === 'abort' || xhr.status === 0) {
            console.log('Snapshot request aborted (user navigated away) - snapshot continues on server');
            return;
        }
        const error = xhr.responseJSON?.error || 'Failed to create snapshot';
        alert('Error: ' + error);
    })
    .always(function() {
        $btn.prop('disabled', false).html('<i class="fas fa-plus"></i> Create Snapshot');
    });
});

let currentSnapshotId = null;

// Save schedule button
$('#save-schedule-btn').click(function() {
    const excludeText = $('#schedule-exclude').val().trim();
    const excludePatterns = excludeText ? excludeText.split(',').map(p => p.trim()).filter(p => p) : [];

    const scheduleData = {
        enabled: $('#schedule-enabled').is(':checked'),
        interval_hours: parseInt($('#schedule-interval').val()) || 24,
        retention_days: parseInt($('#schedule-retention').val()) || 30,
        juniper_set_format: $('#schedule-juniper-set').is(':checked'),
        exclude_patterns: excludePatterns
    };

    $.ajax({
        url: '/api/backup-schedule',
        method: 'PUT',
        contentType: 'application/json',
        data: JSON.stringify(scheduleData)
    })
    .done(function(response) {
        if (response.success) {
            loadBackupSchedule();
        } else {
            alert('Error: ' + response.error);
        }
    });
});

// Cleanup old backups button
$('#cleanup-backups-btn').click(function() {
    const retentionDays = parseInt($('#schedule-retention').val()) || 30;
    if (!confirm(`Delete all backups older than ${retentionDays} days?`)) return;

    $.ajax({
        url: '/api/config-backups/cleanup',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ retention_days: retentionDays })
    })
    .done(function(response) {
        if (response.success) {
            loadBackupSummary();
        } else {
            alert('Error: ' + response.error);
        }
    });
});

// View all backups button
$('#view-all-backups-btn').click(function() {
    loadAllBackups();
    const modal = new bootstrap.Modal(document.getElementById('allBackupsModal'));
    modal.show();
});

// Refresh backups button
$('#refresh-backups-btn').click(function() {
    loadAllBackups($('#filter-backup-device').val());
});

// Filter backup device
$('#filter-backup-device').change(function() {
    backupsPage = 0;
    loadAllBackups($(this).val());
});

// Pagination
$('#prev-page').click(function(e) {
    e.preventDefault();
    if (backupsPage > 0) {
        backupsPage--;
        loadAllBackups($('#filter-backup-device').val());
    }
});

$('#next-page').click(function(e) {
    e.preventDefault();
    backupsPage++;
    loadAllBackups($('#filter-backup-device').val());
});

function loadAllBackups(deviceFilter = '') {
    const offset = backupsPage * backupsPageSize;
    let url = `/api/config-backups?limit=${backupsPageSize}&offset=${offset}`;
    if (deviceFilter) {
        url += `&device=${encodeURIComponent(deviceFilter)}`;
    }

    $.get(url)
        .done(function(response) {
            if (response.success) {
                renderBackupsTable(response.backups);
                $('#backup-count').text(response.backups.length);
                $('#prev-page').toggleClass('disabled', backupsPage === 0);
                $('#next-page').toggleClass('disabled', response.backups.length < backupsPageSize);
            }
        });
}

function renderBackupsTable(backups) {
    const $tbody = $('#all-backups-table-body');
    $tbody.empty();

    if (!backups || backups.length === 0) {
        $tbody.html('<tr><td colspan="6" class="text-center text-muted">No backups found</td></tr>');
        return;
    }

    backups.forEach(function(backup) {
        const statusBadge = backup.status === 'success'
            ? '<span class="badge bg-success">Success</span>'
            : '<span class="badge bg-danger">Failed</span>';

        const formatBadge = backup.config_format === 'set'
            ? '<span class="badge bg-info">Set</span>'
            : '<span class="badge bg-secondary">Native</span>';

        $tbody.append(`
            <tr>
                <td><i class="fas fa-server text-muted"></i> ${escapeHtml(backup.device_name)}</td>
                <td><small>${formatDate(backup.created_at)}</small></td>
                <td>${formatBadge}</td>
                <td><small>${formatFileSize(backup.file_size || 0)}</small></td>
                <td>${statusBadge}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary view-backup-btn" data-id="${backup.backup_id}">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger delete-backup-btn" data-id="${backup.backup_id}">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>
        `);
    });

    // Bind handlers
    $('.view-backup-btn').click(function() {
        viewBackup($(this).data('id'));
    });

    $('.delete-backup-btn').click(function() {
        deleteBackup($(this).data('id'));
    });
}

function viewBackup(backupId, deviceName) {
    // Show the backup modal
    const modal = new bootstrap.Modal(document.getElementById('viewBackupModal'));

    // Reset and show loading state
    $('#view-backup-device-name').text(deviceName || 'Device');
    $('#view-backup-loading').show();
    $('#view-backup-content-container').hide();
    $('#view-backup-created').text('-');
    $('#view-backup-format').text('-');
    $('#view-backup-size').text('-');

    modal.show();

    // Fetch backup content
    $.get(`/api/config-backups/${backupId}`)
        .done(function(response) {
            $('#view-backup-loading').hide();

            // Handle wrapped response (data.backup) or direct response (backup)
            const data = response.data || response;
            if (response.success && data.backup) {
                const backup = data.backup;
                $('#viewBackupModal').data('backup', backup);

                // Display metadata
                $('#view-backup-device-name').text(backup.device_name);
                $('#view-backup-created').text(formatDate(backup.created_at));
                $('#view-backup-format').html(backup.config_format === 'set' ?
                    '<span class="badge bg-info">Set Format</span>' :
                    '<span class="badge bg-secondary">Native</span>');
                $('#view-backup-size').text(formatFileSize(backup.file_size || 0));

                // Display config content
                $('#view-backup-config').val(backup.config_content || '');
                $('#view-backup-content-container').show();
            } else {
                $('#view-backup-config').val('Error: Could not load backup content');
                $('#view-backup-content-container').show();
            }
        })
        .fail(function() {
            $('#view-backup-loading').hide();
            $('#view-backup-config').val('Error: Failed to fetch backup');
            $('#view-backup-content-container').show();
        });
}

// Copy backup button handler
$('#copy-backup-btn').click(function() {
    const content = $('#view-backup-config').val();
    const btn = $(this);
    const originalHtml = btn.html();

    navigator.clipboard.writeText(content).then(function() {
        btn.html('<i class="fas fa-check"></i> Copied!');
        setTimeout(function() {
            btn.html(originalHtml);
        }, 2000);
    }).catch(function(err) {
        console.error('Failed to copy:', err);
        alert('Failed to copy to clipboard');
    });
});

// Download backup button handler
$('#download-backup-btn').click(function() {
    const backup = $('#viewBackupModal').data('backup');
    if (!backup) return;

    const content = backup.config_content || '';
    const filename = `${backup.device_name}_backup_${backup.created_at.replace(/[: ]/g, '_')}.txt`;

    const blob = new Blob([content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = filename;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
});

// Reset diff view to initial state
function resetDiffView() {
    $('#diff-compare-backup').html('<option value="">Select backup to compare...</option>');
    $('#diff-loading').hide();
    $('#diff-no-previous').hide();
    $('#diff-no-changes').hide();
    $('#diff-content-container').hide();
    $('#diff-content').html('');
    $('#diff-added-count').text('0');
    $('#diff-removed-count').text('0');
    $('#diff-unchanged-count').text('0');
}

// Load other backups for comparison dropdown
function loadBackupsForComparison(deviceName, currentBackupId) {
    $.get(`/api/config-backups?device=${encodeURIComponent(deviceName)}&limit=20`)
        .done(function(response) {
            if (response.success && response.backups) {
                const $select = $('#diff-compare-backup');
                $select.html('<option value="">Select backup to compare...</option>');

                // Filter out current backup and add others
                const otherBackups = response.backups.filter(b => b.backup_id !== currentBackupId);

                if (otherBackups.length === 0) {
                    $select.append('<option value="" disabled>No other backups available</option>');
                    return;
                }

                otherBackups.forEach(backup => {
                    const date = formatDate(backup.created_at);
                    const formatLabel = backup.config_format === 'set' ? ' (set)' : '';
                    $select.append(`<option value="${backup.backup_id}">${date}${formatLabel}</option>`);
                });

                // Auto-select previous backup (first in list after current)
                if (otherBackups.length > 0) {
                    $select.val(otherBackups[0].backup_id);
                }
            }
        });
}

// When diff tab is shown, load the diff
$('#diff-tab').on('shown.bs.tab', function() {
    const compareBackupId = $('#diff-compare-backup').val();
    if (compareBackupId) {
        loadDiff(compareBackupId);
    } else {
        // Try to auto-select and load
        const $select = $('#diff-compare-backup');
        const firstOption = $select.find('option[value!=""]:not(:disabled)').first().val();
        if (firstOption) {
            $select.val(firstOption);
            loadDiff(firstOption);
        } else {
            $('#diff-no-previous').show();
        }
    }
});

// When comparison backup changes
$('#diff-compare-backup').change(function() {
    const compareBackupId = $(this).val();
    if (compareBackupId) {
        loadDiff(compareBackupId);
    }
});

// Load and display diff between current and selected backup
function loadDiff(compareBackupId) {
    const currentBackup = $('#viewBackupModal').data('backup');
    if (!currentBackup) return;

    // Show loading
    $('#diff-loading').show();
    $('#diff-no-previous').hide();
    $('#diff-no-changes').hide();
    $('#diff-content-container').hide();

    // Fetch the comparison backup
    $.get(`/api/config-backups/${compareBackupId}`)
        .done(function(response) {
            $('#diff-loading').hide();

            if (response.success && response.backup) {
                const compareBackup = response.backup;
                const currentContent = currentBackup.config_content || '';
                const compareContent = compareBackup.config_content || '';

                // Compute and display diff
                displayDiff(currentContent, compareContent);
            } else {
                $('#diff-no-previous').show();
            }
        })
        .fail(function() {
            $('#diff-loading').hide();
            $('#diff-no-previous').show();
        });
}

// Compute and display the diff between two configs
function displayDiff(currentContent, previousContent) {
    const currentLines = currentContent.split('\n');
    const previousLines = previousContent.split('\n');

    // Simple line-by-line diff (LCS-based would be better but this is simpler)
    const diff = computeLineDiff(previousLines, currentLines);

    if (diff.added === 0 && diff.removed === 0) {
        $('#diff-no-changes').show();
        $('#diff-content-container').hide();
        $('#diff-added-count').text('0');
        $('#diff-removed-count').text('0');
        $('#diff-unchanged-count').text(currentLines.length);
        return;
    }

    // Update counts
    $('#diff-added-count').text(diff.added);
    $('#diff-removed-count').text(diff.removed);
    $('#diff-unchanged-count').text(diff.unchanged);

    // Display diff content
    $('#diff-content').html(diff.html);
    $('#diff-content-container').show();
    $('#diff-no-changes').hide();
}

// Compute line-by-line diff using a simple algorithm
function computeLineDiff(oldLines, newLines) {
    const oldSet = new Set(oldLines);
    const newSet = new Set(newLines);

    let html = '';
    let added = 0;
    let removed = 0;
    let unchanged = 0;

    // Track which lines from old are in new (for unchanged detection)
    const oldLinesCounted = new Set();
    const newLinesCounted = new Set();

    // First pass: identify removed lines (in old but not in new)
    oldLines.forEach((line, idx) => {
        if (!newSet.has(line)) {
            removed++;
        }
    });

    // Second pass: identify added lines (in new but not in old)
    newLines.forEach((line, idx) => {
        if (!oldSet.has(line)) {
            added++;
        }
    });

    // Build unified diff output
    // Use a simple approach: show context with additions and removals
    const CONTEXT_LINES = 3;
    let i = 0, j = 0;
    let lastOutputLine = -CONTEXT_LINES - 1;

    while (i < oldLines.length || j < newLines.length) {
        const oldLine = i < oldLines.length ? oldLines[i] : null;
        const newLine = j < newLines.length ? newLines[j] : null;

        if (oldLine === newLine) {
            // Unchanged line
            unchanged++;
            html += `<div class="diff-line diff-unchanged"><span class="diff-line-num">${j + 1}</span><span class="diff-line-content">${escapeHtml(newLine)}</span></div>`;
            i++;
            j++;
        } else if (oldLine !== null && !newSet.has(oldLine)) {
            // Removed line
            html += `<div class="diff-line diff-removed"><span class="diff-line-num">-</span><span class="diff-line-content">${escapeHtml(oldLine)}</span></div>`;
            i++;
        } else if (newLine !== null && !oldSet.has(newLine)) {
            // Added line
            html += `<div class="diff-line diff-added"><span class="diff-line-num">+</span><span class="diff-line-content">${escapeHtml(newLine)}</span></div>`;
            j++;
        } else {
            // Line exists in both but in different positions - treat as unchanged for display
            unchanged++;
            html += `<div class="diff-line diff-unchanged"><span class="diff-line-num">${j + 1}</span><span class="diff-line-content">${escapeHtml(newLine)}</span></div>`;
            i++;
            j++;
        }
    }

    return { html, added, removed, unchanged };
}

// ============================================================================
// Test Connectivity Functions
// ============================================================================

function testDeviceConnectivity(deviceName, $btn) {
    const originalHtml = $btn.html();
    $btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i>');

    $.ajax({
        url: `/api/devices/${encodeURIComponent(deviceName)}/test`,
        method: 'POST',
        contentType: 'application/json',
        timeout: 60000
    })
    .done(function(response) {
        if (response.success && response.data && response.data.task_id) {
            // Poll for task result
            pollConnectivityTest(response.data.task_id, deviceName, $btn, originalHtml);
        } else {
            $btn.prop('disabled', false).html(originalHtml);
            showToast('error', 'Failed to start connectivity test: ' + (response.error || 'Unknown error'));
        }
    })
    .fail(function(xhr) {
        $btn.prop('disabled', false).html(originalHtml);
        const error = xhr.responseJSON?.error || 'Failed to test connectivity';
        showToast('error', error);
    });
}

function pollConnectivityTest(taskId, deviceName, $btn, originalHtml) {
    let pollCount = 0;
    const maxPolls = 30;  // 30 seconds max

    const pollInterval = setInterval(function() {
        pollCount++;

        $.get(`/api/task/${taskId}`)
            .done(function(response) {
                const status = response.data?.task_status || response.status;

                if (status === 'success' || status === 'SUCCESS') {
                    clearInterval(pollInterval);
                    $btn.prop('disabled', false).html('<i class="fas fa-check text-success"></i>');
                    showToast('success', `${deviceName}: Connection successful!`);
                    setTimeout(() => $btn.html(originalHtml), 3000);
                } else if (status === 'failed' || status === 'FAILURE') {
                    clearInterval(pollInterval);
                    $btn.prop('disabled', false).html('<i class="fas fa-times text-danger"></i>');
                    const error = response.data?.task_result?.error || 'Connection failed';
                    showToast('error', `${deviceName}: ${error}`);
                    setTimeout(() => $btn.html(originalHtml), 3000);
                } else if (pollCount >= maxPolls) {
                    clearInterval(pollInterval);
                    $btn.prop('disabled', false).html(originalHtml);
                    showToast('warning', `${deviceName}: Test timed out`);
                }
            })
            .fail(function() {
                if (pollCount >= maxPolls) {
                    clearInterval(pollInterval);
                    $btn.prop('disabled', false).html(originalHtml);
                    showToast('error', `${deviceName}: Failed to get test result`);
                }
            });
    }, 1000);
}

// ============================================================================
// Bulk Operations
// ============================================================================

function executeBulkTestConnectivity() {
    if (!confirm(`Test connectivity for ${selectedDevices.length} devices?`)) return;

    // Show status modal
    const statusModal = new bootstrap.Modal(document.getElementById('bulkStatusModal'));
    statusModal.show();

    let completed = 0;
    let successful = 0;
    let failed = 0;

    selectedDevices.forEach(function(device) {
        $.ajax({
            url: `/api/devices/${encodeURIComponent(device)}/test`,
            method: 'POST',
            contentType: 'application/json',
            timeout: 60000
        })
        .done(function(response) {
            if (response.success && response.data && response.data.task_id) {
                // Start polling for this device
                pollBulkConnectivityTest(response.data.task_id, device, function(success) {
                    if (success) successful++;
                    else failed++;
                    completed++;
                    updateBulkStatus(completed, successful, failed, selectedDevices.length);
                });
            } else {
                failed++;
                completed++;
                updateBulkStatus(completed, successful, failed, selectedDevices.length);
            }
        })
        .fail(function() {
            failed++;
            completed++;
            updateBulkStatus(completed, successful, failed, selectedDevices.length);
        });
    });
}

function pollBulkConnectivityTest(taskId, deviceName, callback) {
    let pollCount = 0;
    const maxPolls = 30;

    const pollInterval = setInterval(function() {
        pollCount++;

        $.get(`/api/task/${taskId}`)
            .done(function(response) {
                const status = response.data?.task_status || response.status;

                if (status === 'success' || status === 'SUCCESS') {
                    clearInterval(pollInterval);
                    callback(true);
                } else if (status === 'failed' || status === 'FAILURE') {
                    clearInterval(pollInterval);
                    callback(false);
                } else if (pollCount >= maxPolls) {
                    clearInterval(pollInterval);
                    callback(false);
                }
            })
            .fail(function() {
                if (pollCount >= maxPolls) {
                    clearInterval(pollInterval);
                    callback(false);
                }
            });
    }, 1000);
}

function executeBulkBackup() {
    if (!confirm(`Backup ${selectedDevices.length} devices?`)) return;

    const $btn = $('#bulk-backup-btn');
    $btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Backing up...');

    $.ajax({
        url: '/api/config-backups/run-selected',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            device_names: selectedDevices,
            juniper_set_format: true
        }),
        timeout: 300000
    })
    .done(function(response) {
        if (response.success) {
            showToast('success', `Backup started for ${response.submitted || selectedDevices.length} devices`);
            if (response.tasks && response.tasks.length > 0) {
                runningTasks = response.tasks;
                showRunningTasks();
                startTaskPolling();
            }
        } else {
            showToast('error', 'Failed to start backup: ' + (response.error || 'Unknown error'));
        }
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON?.error || 'Failed to start backup';
        showToast('error', error);
    })
    .always(function() {
        $btn.prop('disabled', false).html('<i class="fas fa-save"></i> Backup');
    });
}

function updateBulkStatus(completed, successful, failed, total) {
    const percent = Math.round((completed / total) * 100);
    $('#bulk-progress-bar').css('width', percent + '%').text(percent + '%');
    $('#bulk-completed-count').text(completed);
    $('#bulk-success-count').text(successful);
    $('#bulk-failed-count').text(failed);

    if (completed === total) {
        $('#bulk-progress-bar').removeClass('progress-bar-animated');
        if (failed === 0) {
            $('#bulk-progress-bar').removeClass('bg-primary').addClass('bg-success');
        } else if (successful === 0) {
            $('#bulk-progress-bar').removeClass('bg-primary').addClass('bg-danger');
        } else {
            $('#bulk-progress-bar').removeClass('bg-primary').addClass('bg-warning');
        }
    }
}

function executeBulkDelete() {
    // Filter to only manual devices
    const manualDevices = selectedDevices.filter(function(deviceName) {
        const device = allDevices.find(d => d.name === deviceName);
        return device && device.source === 'manual';
    });

    if (manualDevices.length === 0) {
        alert('No manual devices selected. Only manual devices can be deleted.');
        return;
    }

    const netboxCount = selectedDevices.length - manualDevices.length;
    let confirmMsg = `Delete ${manualDevices.length} manual device(s)?`;
    if (netboxCount > 0) {
        confirmMsg += `\n\n(${netboxCount} NetBox device(s) will be skipped - they cannot be deleted here)`;
    }

    if (!confirm(confirmMsg)) return;

    const $btn = $('#bulk-delete-btn');
    $btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Deleting...');

    let deleted = 0;
    let errors = 0;
    let completed = 0;

    manualDevices.forEach(function(deviceName) {
        $.ajax({
            url: `/api/manual-devices/${encodeURIComponent(deviceName)}`,
            method: 'DELETE'
        })
        .done(function(response) {
            if (response.success) {
                deleted++;
            } else {
                errors++;
            }
        })
        .fail(function() {
            errors++;
        })
        .always(function() {
            completed++;
            if (completed === manualDevices.length) {
                $btn.prop('disabled', false).html('<i class="fas fa-trash"></i> Delete');
                if (deleted > 0) {
                    showToast('success', `Deleted ${deleted} device(s)`);
                    clearCacheAndReload();
                }
                if (errors > 0) {
                    showToast('error', `Failed to delete ${errors} device(s)`);
                }
            }
        });
    });
}

function deleteBackup(backupId) {
    if (!confirm('Are you sure you want to delete this backup?')) return;

    $.ajax({
        url: `/api/config-backups/${backupId}`,
        method: 'DELETE'
    })
    .done(function(response) {
        if (response.success) {
            loadAllBackups($('#filter-backup-device').val());
            loadBackupSummary();
        } else {
            alert('Error: ' + response.error);
        }
    });
}

// Backup single device (from device row)
function backupSingleDevice(deviceName) {
    const $btn = $(`.backup-device-btn[data-device="${deviceName}"]`);
    $btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i>');

    $.ajax({
        url: '/api/config-backups/run-single',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            device_name: deviceName,
            juniper_set_format: true  // Default to set format for Juniper devices
        })
    })
    .done(function(response) {
        if (response.success) {
            const task = { device: deviceName, task_id: response.task_id };
            runningTasks = [task];
            // Register with global TaskManager for persistence
            if (typeof TaskManager !== 'undefined') {
                TaskManager.addTasks([{
                    task_id: response.task_id,
                    device: deviceName,
                    type: 'backup-single'
                }]);
            }
            showRunningTasks();
            startTaskPolling();
        } else {
            alert('Error: ' + response.error);
            $btn.prop('disabled', false).html('<i class="fas fa-download"></i>');
        }
    })
    .fail(function() {
        alert('Failed to start backup');
        $btn.prop('disabled', false).html('<i class="fas fa-download"></i>');
    });
}

// Running tasks display
function showRunningTasks() {
    $('#running-tasks-card').show();
    const $list = $('#running-tasks-list');
    $list.empty();

    runningTasks.forEach(function(task) {
        $list.append(`
            <div class="d-flex justify-content-between align-items-center mb-2" id="task-${task.task_id}">
                <span><i class="fas fa-spinner fa-spin text-primary"></i> ${escapeHtml(task.device)}</span>
                <span class="badge bg-warning">Running</span>
            </div>
        `);
    });
}

function startTaskPolling() {
    if (taskPollInterval) clearInterval(taskPollInterval);

    taskPollInterval = setInterval(function() {
        runningTasks.forEach(function(task) {
            $.get(`/api/config-backups/task/${task.task_id}`)
                .done(function(response) {
                    const $taskEl = $(`#task-${task.task_id}`);
                    if (response.status === 'success' || response.saved) {
                        $taskEl.find('.fa-spinner').removeClass('fa-spinner fa-spin text-primary').addClass('fa-check text-success');
                        $taskEl.find('.badge').removeClass('bg-warning').addClass('bg-success').text('Complete');
                    } else if (response.status === 'failed' || (response.result && response.result.status === 'failed')) {
                        $taskEl.find('.fa-spinner').removeClass('fa-spinner fa-spin text-primary').addClass('fa-times text-danger');
                        $taskEl.find('.badge').removeClass('bg-warning').addClass('bg-danger').text('Failed');
                    }
                });
        });

        // Check if all done
        setTimeout(function() {
            const remaining = runningTasks.filter(function(task) {
                const $el = $(`#task-${task.task_id}`);
                return $el.find('.fa-spinner').length > 0;
            });

            if (remaining.length === 0) {
                clearInterval(taskPollInterval);
                taskPollInterval = null;
                loadBackupSummary();
                setTimeout(function() {
                    $('#running-tasks-card').fadeOut();
                }, 3000);
            }
        }, 500);
    }, 2000);
}

// Close tasks card
$('#close-tasks-card').click(function() {
    $('#running-tasks-card').hide();
});

// Copy and download handlers
$('#copy-config-btn').click(function() {
    const content = $('#view-config-content').val();
    const btn = $(this);
    const originalText = btn.html();
    navigator.clipboard.writeText(content).then(function() {
        btn.html('<i class="fas fa-check"></i> Copied');
        setTimeout(() => btn.html(originalText), 1500);
    });
});

$('#download-config-btn').click(function() {
    const backup = $('#viewBackupModal').data('backup');
    if (!backup) return;

    const blob = new Blob([backup.config_content], { type: 'text/plain' });
    const url = URL.createObjectURL(blob);
    const a = document.createElement('a');
    a.href = url;
    a.download = `${backup.device_name}_${backup.created_at.replace(/[: ]/g, '_')}.txt`;
    document.body.appendChild(a);
    a.click();
    document.body.removeChild(a);
    URL.revokeObjectURL(url);
});

// Utility functions
function formatDate(dateStr) {
    if (!dateStr) return 'N/A';
    const d = new Date(dateStr);
    return d.toLocaleString();
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 B';
    const k = 1024;
    const sizes = ['B', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return parseFloat((bytes / Math.pow(k, i)).toFixed(1)) + ' ' + sizes[i];
}

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// ============================================================================
// Task Restoration Functions (for page navigation persistence)
// ============================================================================

/**
 * Restore running tasks from TaskManager when page loads
 * This ensures the tasks panel and spinning buttons are shown even after navigation
 */
function restoreRunningTasks() {
    if (typeof TaskManager === 'undefined') return;

    const tasks = TaskManager.getTasks();
    if (tasks.length === 0) return;

    console.log('Restoring', tasks.length, 'running tasks from TaskManager');

    // Restore to local runningTasks array
    runningTasks = tasks.map(t => ({
        task_id: t.task_id,
        device: t.device
    }));

    // Show the tasks card and start polling
    showRunningTasks();
    startTaskPolling();

    // Update the "Backup All" button if we have bulk tasks running
    const hasBulkTasks = tasks.some(t => t.type === 'backup-all');
    if (hasBulkTasks) {
        const $btn = $('#run-all-backups-btn');
        $btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Running...');
    }
}

/**
 * Listen for task completion events from TaskManager
 */
window.addEventListener('taskCompleted', function(e) {
    const { task, status } = e.detail;
    console.log('Task completed:', task.device, status);

    // Update backup button for the specific device
    const $btn = $(`.backup-device-btn[data-device="${task.device}"]`);
    if ($btn.length > 0) {
        $btn.prop('disabled', false).html('<i class="fas fa-download"></i>');
    }

    // Reload backup summary when tasks complete
    loadBackupSummary();
    loadDeviceBackupStatus();
});

/**
 * Listen for task status updates
 */
window.addEventListener('taskStatusUpdate', function(e) {
    const { running, tasks } = e.detail;

    // Update Backup All button based on running status
    const hasBulkRunning = tasks.some(t => t.type === 'backup-all' && t.status === 'running');
    const $backupAllBtn = $('#run-all-backups-btn');

    if (hasBulkRunning) {
        $backupAllBtn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Running...');
    } else {
        $backupAllBtn.prop('disabled', false).html('<i class="fas fa-sync"></i> Backup All Devices');
    }
});

// ============================================================================
// Device Override/Edit Functions
// ============================================================================

let deviceOverrides = {};  // Map of device_name -> override settings

function loadDeviceOverrides() {
    $.get('/api/device-overrides')
        .done(function(response) {
            if (response.success && response.overrides) {
                deviceOverrides = {};
                response.overrides.forEach(function(override) {
                    deviceOverrides[override.device_name] = override;
                });
                // Re-render devices table to show override indicators
                if (allDevices.length > 0) {
                    displayDevices(allDevices);
                }
            }
        });
}

function openEditDeviceModal(deviceName) {
    // Reset form
    $('#edit-device-form')[0].reset();
    $('#edit-device-name').val(deviceName);
    $('#edit-device-display-name').text(deviceName);

    // For manual devices, load full device details first, then apply overrides
    $.get(`/api/manual-devices/${encodeURIComponent(deviceName)}`)
        .done(function(response) {
            if (response.success && response.device) {
                const d = response.device;
                // Fill in device base settings
                if (d.device_type) $('#edit-device-type').val(d.device_type);
                if (d.host) $('#edit-device-host').val(d.host);
                if (d.port) $('#edit-device-port').val(d.port);
                if (d.username) $('#edit-device-username').val(d.username);
                if (d.password) $('#edit-device-password').val(d.password);
                if (d.enable_password) $('#edit-device-secret').val(d.enable_password);
            }
            // After loading manual device, load overrides to apply on top
            loadDeviceOverridesForModal(deviceName);
        })
        .fail(function() {
            // Not a manual device, try cache then load overrides
            const device = allDevices.find(d => d.name === deviceName);
            if (device) {
                $('#edit-device-type').val(device.device_type || '');
                $('#edit-device-host').val(device.primary_ip || device.host || '');
                if (device.port) $('#edit-device-port').val(device.port);
            }
            loadDeviceOverridesForModal(deviceName);
        });

    const modal = new bootstrap.Modal(document.getElementById('editDeviceModal'));
    modal.show();
}

function loadDeviceOverridesForModal(deviceName) {
    $.get(`/api/device-overrides/${encodeURIComponent(deviceName)}`)
        .done(function(response) {
            if (response.success && response.override) {
                const o = response.override;
                // Apply override values on top of device settings
                if (o.device_type) $('#edit-device-type').val(o.device_type);
                if (o.host) $('#edit-device-host').val(o.host);
                if (o.port) $('#edit-device-port').val(o.port);
                if (o.username) $('#edit-device-username').val(o.username);
                if (o.password) $('#edit-device-password').val(o.password);
                if (o.secret) $('#edit-device-secret').val(o.secret);
                if (o.timeout) $('#edit-device-timeout').val(o.timeout);
                if (o.conn_timeout) $('#edit-device-conn-timeout').val(o.conn_timeout);
                if (o.auth_timeout) $('#edit-device-auth-timeout').val(o.auth_timeout);
                if (o.banner_timeout) $('#edit-device-banner-timeout').val(o.banner_timeout);
                if (o.notes) $('#edit-device-notes').val(o.notes);
                $('#edit-device-disabled').prop('checked', o.disabled || false);
            }
        });
}

// Save device override button handler
$('#save-device-override-btn').click(function() {
    const deviceName = $('#edit-device-name').val();

    const overrideData = {
        device_type: $('#edit-device-type').val() || null,
        host: $('#edit-device-host').val() || null,
        port: $('#edit-device-port').val() || null,
        username: $('#edit-device-username').val() || null,
        password: $('#edit-device-password').val() || null,
        secret: $('#edit-device-secret').val() || null,
        timeout: $('#edit-device-timeout').val() || null,
        conn_timeout: $('#edit-device-conn-timeout').val() || null,
        auth_timeout: $('#edit-device-auth-timeout').val() || null,
        banner_timeout: $('#edit-device-banner-timeout').val() || null,
        notes: $('#edit-device-notes').val() || null,
        disabled: $('#edit-device-disabled').is(':checked')
    };

    const $btn = $(this);
    $btn.prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Saving...');

    $.ajax({
        url: `/api/device-overrides/${encodeURIComponent(deviceName)}`,
        method: 'PUT',
        contentType: 'application/json',
        data: JSON.stringify(overrideData)
    })
    .done(function(response) {
        if (response.success) {
            bootstrap.Modal.getInstance(document.getElementById('editDeviceModal')).hide();
            // Update local cache and refresh display
            deviceOverrides[deviceName] = overrideData;
            if (allDevices.length > 0) {
                displayDevices(allDevices);
            }
            // Show success message
            showToast('success', `Settings saved for ${deviceName}`);
        } else {
            alert('Error: ' + (response.error || 'Failed to save settings'));
        }
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON?.error || 'Failed to save settings';
        alert('Error: ' + error);
    })
    .always(function() {
        $btn.prop('disabled', false).html('<i class="fas fa-save"></i> Save Settings');
    });
});

// Delete device override button handler
$('#delete-device-override-btn').click(function() {
    const deviceName = $('#edit-device-name').val();

    if (!confirm(`Clear all overrides for "${deviceName}"? This will revert to default settings.`)) {
        return;
    }

    const $btn = $(this);
    $btn.prop('disabled', true);

    $.ajax({
        url: `/api/device-overrides/${encodeURIComponent(deviceName)}`,
        method: 'DELETE'
    })
    .done(function(response) {
        if (response.success) {
            bootstrap.Modal.getInstance(document.getElementById('editDeviceModal')).hide();
            // Remove from local cache and refresh display
            delete deviceOverrides[deviceName];
            if (allDevices.length > 0) {
                displayDevices(allDevices);
            }
            showToast('info', `Overrides cleared for ${deviceName}`);
        } else {
            alert('Error: ' + (response.error || 'Failed to delete overrides'));
        }
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON?.error || 'Failed to delete overrides';
        alert('Error: ' + error);
    })
    .always(function() {
        $btn.prop('disabled', false);
    });
});

// Simple toast notification function
function showToast(type, message) {
    // Create toast container if it doesn't exist
    let $toastContainer = $('#toast-container');
    if ($toastContainer.length === 0) {
        $toastContainer = $('<div id="toast-container" class="position-fixed bottom-0 end-0 p-3" style="z-index: 9999;"></div>');
        $('body').append($toastContainer);
    }

    const toastId = 'toast-' + Date.now();
    const bgClass = type === 'success' ? 'bg-success' : type === 'error' ? 'bg-danger' : 'bg-info';
    const iconClass = type === 'success' ? 'fa-check-circle' : type === 'error' ? 'fa-times-circle' : 'fa-info-circle';

    const toastHtml = `
        <div id="${toastId}" class="toast align-items-center text-white ${bgClass} border-0" role="alert" aria-live="assertive" aria-atomic="true">
            <div class="d-flex">
                <div class="toast-body">
                    <i class="fas ${iconClass}"></i> ${escapeHtml(message)}
                </div>
                <button type="button" class="btn-close btn-close-white me-2 m-auto" data-bs-dismiss="toast" aria-label="Close"></button>
            </div>
        </div>
    `;

    $toastContainer.append(toastHtml);
    const toastEl = document.getElementById(toastId);
    const toast = new bootstrap.Toast(toastEl, { delay: 3000 });
    toast.show();

    // Remove from DOM after hidden
    toastEl.addEventListener('hidden.bs.toast', function() {
        $(this).remove();
    });
}

// ============================================================================
// Snapshot Functions
// ============================================================================

/**
 * Load recent snapshots for the right panel display
 */
function loadRecentSnapshots() {
    $.get('/api/config-snapshots?limit=5')
        .done(function(response) {
            if (response.success && response.snapshots) {
                renderRecentSnapshots(response.snapshots);
            }
        })
        .fail(function() {
            $('#recent-snapshots-list').html('<div class="text-muted small text-center py-2">Failed to load snapshots</div>');
        });
}

function renderRecentSnapshots(snapshots) {
    const $list = $('#recent-snapshots-list');
    $list.empty();

    if (!snapshots || snapshots.length === 0) {
        $list.html('<div class="text-muted small text-center py-2">No snapshots yet</div>');
        return;
    }

    snapshots.forEach(function(snapshot) {
        const statusBadge = getSnapshotStatusBadge(snapshot.status);
        const date = formatDate(snapshot.created_at);
        const deviceInfo = `${snapshot.success_count}/${snapshot.total_devices}`;

        $list.append(`
            <div class="d-flex justify-content-between align-items-center py-1 border-bottom snapshot-item" data-id="${snapshot.snapshot_id}" style="cursor: pointer;">
                <div>
                    <small class="d-block">${escapeHtml(snapshot.name || 'Snapshot')}</small>
                    <small class="text-muted">${date}</small>
                </div>
                <div class="text-end">
                    <small class="d-block">${deviceInfo}</small>
                    ${statusBadge}
                </div>
            </div>
        `);
    });

    // Click handler for snapshot items
    $('.snapshot-item').click(function() {
        const snapshotId = $(this).data('id');
        viewSnapshot(snapshotId);
    });
}

function getSnapshotStatusBadge(status) {
    switch (status) {
        case 'complete':
            return '<span class="badge bg-success">Complete</span>';
        case 'partial':
            return '<span class="badge bg-warning">Partial</span>';
        case 'failed':
            return '<span class="badge bg-danger">Failed</span>';
        case 'in_progress':
            return '<span class="badge bg-info"><i class="fas fa-spinner fa-spin"></i> Running</span>';
        default:
            return '<span class="badge bg-secondary">' + escapeHtml(status) + '</span>';
    }
}

/**
 * View all snapshots modal
 */
$('#view-all-snapshots-btn').click(function() {
    loadAllSnapshots();
    const modal = new bootstrap.Modal(document.getElementById('allSnapshotsModal'));
    modal.show();
});

function loadAllSnapshots() {
    $.get('/api/config-snapshots?limit=50')
        .done(function(response) {
            if (response.success) {
                renderAllSnapshotsTable(response.snapshots);
            }
        });
}

function renderAllSnapshotsTable(snapshots) {
    const $tbody = $('#all-snapshots-table-body');
    $tbody.empty();

    if (!snapshots || snapshots.length === 0) {
        $tbody.html('<tr><td colspan="5" class="text-center text-muted">No snapshots found</td></tr>');
        return;
    }

    snapshots.forEach(function(snapshot) {
        const statusBadge = getSnapshotStatusBadge(snapshot.status);
        const date = formatDate(snapshot.created_at);

        $tbody.append(`
            <tr>
                <td>${escapeHtml(snapshot.name || 'Snapshot')}</td>
                <td><small>${date}</small></td>
                <td>${statusBadge}</td>
                <td>${snapshot.success_count}/${snapshot.total_devices}</td>
                <td>
                    <button class="btn btn-sm btn-outline-primary view-snapshot-btn" data-id="${snapshot.snapshot_id}">
                        <i class="fas fa-eye"></i>
                    </button>
                    <button class="btn btn-sm btn-outline-danger delete-snapshot-btn" data-id="${snapshot.snapshot_id}">
                        <i class="fas fa-trash"></i>
                    </button>
                </td>
            </tr>
        `);
    });

    // Bind handlers
    $('.view-snapshot-btn').click(function() {
        const snapshotId = $(this).data('id');
        bootstrap.Modal.getInstance(document.getElementById('allSnapshotsModal')).hide();
        viewSnapshot(snapshotId);
    });

    $('.delete-snapshot-btn').click(function() {
        const snapshotId = $(this).data('id');
        deleteSnapshot(snapshotId);
    });
}

/**
 * View a single snapshot and its backups
 */
function viewSnapshot(snapshotId) {
    $.get(`/api/config-snapshots/${snapshotId}`)
        .done(function(response) {
            if (response.success && response.snapshot) {
                const s = response.snapshot;
                $('#view-snapshot-title').text(s.name || 'Snapshot');
                $('#view-snapshot-status').html(getSnapshotStatusBadge(s.status));
                $('#view-snapshot-devices').text(s.total_devices);
                $('#view-snapshot-success').text(s.success_count);
                $('#view-snapshot-failed').text(s.failed_count);
                $('#viewSnapshotModal').data('snapshot-id', snapshotId);

                // Render backups table
                renderSnapshotBackupsTable(s.backups || []);

                const modal = new bootstrap.Modal(document.getElementById('viewSnapshotModal'));
                modal.show();
            }
        });
}

function renderSnapshotBackupsTable(backups) {
    const $tbody = $('#snapshot-backups-table-body');
    $tbody.empty();

    if (!backups || backups.length === 0) {
        $tbody.html('<tr><td colspan="5" class="text-center text-muted">No backups in this snapshot</td></tr>');
        return;
    }

    backups.forEach(function(backup) {
        const statusBadge = backup.status === 'success'
            ? '<span class="badge bg-success">Success</span>'
            : '<span class="badge bg-danger">Failed</span>';

        const formatBadge = backup.config_format === 'set'
            ? '<span class="badge bg-info">Set</span>'
            : '<span class="badge bg-secondary">Native</span>';

        $tbody.append(`
            <tr>
                <td>${escapeHtml(backup.device_name)}</td>
                <td>${statusBadge}</td>
                <td>${formatBadge}</td>
                <td><small>${formatFileSize(backup.file_size || 0)}</small></td>
                <td>
                    <button class="btn btn-sm btn-outline-primary view-snapshot-backup-btn" data-id="${backup.backup_id}">
                        <i class="fas fa-eye"></i>
                    </button>
                </td>
            </tr>
        `);
    });

    // Bind handlers
    $('.view-snapshot-backup-btn').click(function() {
        const backupId = $(this).data('id');
        viewBackup(backupId);
    });
}

/**
 * Delete a snapshot
 */
function deleteSnapshot(snapshotId) {
    if (!confirm('Delete this snapshot and all its backups? This cannot be undone.')) return;

    $.ajax({
        url: `/api/config-snapshots/${snapshotId}`,
        method: 'DELETE'
    })
    .done(function(response) {
        if (response.success) {
            showToast('success', 'Snapshot deleted');
            loadRecentSnapshots();
            loadAllSnapshots();
            loadBackupSummary();
        } else {
            alert('Error: ' + response.error);
        }
    });
}

// Delete snapshot button in view modal
$('#delete-snapshot-btn').click(function() {
    const snapshotId = $('#viewSnapshotModal').data('snapshot-id');
    if (snapshotId) {
        bootstrap.Modal.getInstance(document.getElementById('viewSnapshotModal')).hide();
        deleteSnapshot(snapshotId);
    }
});

/**
 * Start polling for snapshot tasks with snapshot_id in the request
 */
function startSnapshotTaskPolling() {
    if (taskPollInterval) clearInterval(taskPollInterval);

    taskPollInterval = setInterval(function() {
        runningTasks.forEach(function(task) {
            // Include snapshot_id in the polling request
            const snapshotId = task.snapshot_id || currentSnapshotId;
            let pollUrl = `/api/config-backups/task/${task.task_id}`;
            if (snapshotId) {
                pollUrl += `?snapshot_id=${snapshotId}`;
            }

            $.get(pollUrl)
                .done(function(response) {
                    const $taskEl = $(`#task-${task.task_id}`);
                    if (response.status === 'success' || response.saved) {
                        $taskEl.find('.fa-spinner').removeClass('fa-spinner fa-spin text-primary').addClass('fa-check text-success');
                        $taskEl.find('.badge').removeClass('bg-warning').addClass('bg-success').text('Complete');
                    } else if (response.status === 'failed' || (response.result && response.result.status === 'failed')) {
                        $taskEl.find('.fa-spinner').removeClass('fa-spinner fa-spin text-primary').addClass('fa-times text-danger');
                        $taskEl.find('.badge').removeClass('bg-warning').addClass('bg-danger').text('Failed');
                    }
                });
        });

        // Check if all done
        setTimeout(function() {
            const remaining = runningTasks.filter(function(task) {
                const $el = $(`#task-${task.task_id}`);
                return $el.find('.fa-spinner').length > 0;
            });

            if (remaining.length === 0) {
                clearInterval(taskPollInterval);
                taskPollInterval = null;
                currentSnapshotId = null;
                loadBackupSummary();
                loadRecentSnapshots();
                setTimeout(function() {
                    $('#running-tasks-card').fadeOut();
                }, 3000);
            }
        }, 500);
    }, 2000);
}
