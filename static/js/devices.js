// Devices page JavaScript

let allDevices = [];
let selectedDevices = [];

$(document).ready(function() {
    loadDevices();

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
        url: '/api/devices',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ filters: filters })
    })
        .done(function(data) {
            if (data.success && data.devices) {
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
        tbody.append('<tr><td colspan="5" class="text-center text-muted">No devices found</td></tr>');
        return;
    }

    devices.forEach(function(device) {
        const deviceType = device.device_type || 'N/A';
        const source = device.source || 'netbox';
        const sourceBadge = source === 'manual' ?
            '<span class="badge bg-primary">Manual</span>' :
            '<span class="badge bg-info">Netbox</span>';

        const deleteBtn = source === 'manual' ?
            `<button class="btn btn-sm btn-danger delete-manual-device-btn" data-device="${device.name}">
                <i class="fas fa-trash"></i>
             </button>` : '';

        const row = `
            <tr>
                <td>
                    <input type="checkbox" class="form-check-input device-checkbox" data-device="${device.name}">
                </td>
                <td><strong>${device.name}</strong></td>
                <td>${deviceType}</td>
                <td>${sourceBadge}</td>
                <td>${deleteBtn}</td>
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
            alert('Device added successfully!');
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
            alert('Device deleted successfully!');
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
