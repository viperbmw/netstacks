// Deploy page JavaScript for NetStacks

// Store all devices and templates globally for filtering
let allDevices = [];
let allTemplates = [];

$(document).ready(function() {
    loadDevices();

    // Get Config form submit
    $('#getconfig-form').submit(function(e) {
        e.preventDefault();
        executeGetConfig();
    });

    // Set Config form submit
    $('#setconfig-form').submit(function(e) {
        e.preventDefault();
        executeSetConfig();
    });

    // Copy result button
    $('#copy-result').click(function() {
        const resultText = $('#result-content').text();
        navigator.clipboard.writeText(resultText).then(function() {
            const btn = $('#copy-result');
            const originalText = btn.html();
            btn.html('<i class="fas fa-check"></i> Copied!');
            setTimeout(function() {
                btn.html(originalText);
            }, 2000);
        });
    });

    // View task link
    $('#view-task-link').click(function(e) {
        e.preventDefault();
        window.location.href = '/monitor';
    });

    // Toggle TTP template input visibility
    $('#get-use-ttp').change(function() {
        if ($(this).is(':checked')) {
            $('#get-ttp-template-container').show();
        } else {
            $('#get-ttp-template-container').hide();
        }
    });

    // Mutual exclusivity between TextFSM and TTP
    $('#get-use-textfsm').change(function() {
        if ($(this).is(':checked')) {
            $('#get-use-ttp').prop('checked', false);
            $('#get-ttp-template-container').hide();
        }
    });

    $('#get-use-ttp').change(function() {
        if ($(this).is(':checked')) {
            $('#get-use-textfsm').prop('checked', false);
        }
    });


    // Setup template variable form/JSON toggle for new template tab
    setupTemplateVariableToggle('#template-select', '#template-vars-container', '#template-vars-toggle');

    // Pre-fill credentials if defaults exist
    prefillCredentials('#get-username', '#get-password');
    prefillCredentials('#set-username', '#set-password');
    prefillCredentials('#template-username', '#template-password');

    // Handle template form submission
    $('#template-form').submit(function(e) {
        e.preventDefault();
        deployTemplate();
    });

    // Toggle pre/post check fields for Set Config
    $('#set-enable-checks').change(function() {
        if ($(this).is(':checked')) {
            $('#set-checks-container').show();
        } else {
            $('#set-checks-container').hide();
        }
    });

    // Toggle pre/post check fields for Template
    $('#template-enable-checks').change(function() {
        if ($(this).is(':checked')) {
            $('#template-checks-container').show();
        } else {
            $('#template-checks-container').hide();
        }
    });
});

function loadDevices() {
    // Get filters from settings
    let filters = [];
    try {
        const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
        filters = settings.netbox_filters || [];
    } catch (e) {
        console.error('Error reading filters from settings:', e);
    }

    // Make POST request with filters
    $.ajax({
        url: '/api/devices',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ filters: filters })
    })
        .done(function(data) {
            // Handle both legacy format (data.devices) and microservice format (data.data.devices)
            const devices = data.devices || (data.data && data.data.devices) || [];
            if (data.success && devices.length > 0) {
                populateDeviceDropdowns(devices);
            } else if (data.success && devices.length === 0) {
                $('#get-device, #set-device, #template-device').html('<option value="">No devices found</option>');
            } else {
                $('#get-device, #set-device, #template-device').html('<option value="">Error loading devices</option>');
            }
        })
        .fail(function() {
            $('#get-device, #set-device, #template-device').html('<option value="">Error loading devices</option>');
        });
}

function populateDeviceDropdowns(devices) {
    // Store devices globally for filtering
    allDevices = devices;

    const getSelect = $('#get-device');
    const setSelect = $('#set-device');
    const templateSelect = $('#template-device');

    getSelect.empty();
    setSelect.empty();
    templateSelect.empty();

    if (devices.length === 0) {
        getSelect.append('<option value="">No devices found</option>');
        setSelect.append('<option value="">No devices found</option>');
        templateSelect.append('<option value="">No devices found</option>');
        return;
    }

    getSelect.append('<option value="">Select a device...</option>');
    setSelect.append('<option value="">Select a device...</option>');
    templateSelect.append('<option value="">Select a device...</option>');

    devices.forEach(function(device) {
        const displayName = device.display || device.name;
        const deviceValue = device.name;
        const platform = device.platform || '';

        // Include platform in data attribute for filtering
        const option = `<option value="${deviceValue}" data-name="${device.name}" data-platform="${platform}">${displayName}</option>`;
        getSelect.append(option);
        setSelect.append(option);
        templateSelect.append(option);
    });
}

/**
 * Filter template device dropdown based on selected template's vendor_types
 * @param {Array} vendorTypes - Array of allowed vendor types
 */
function filterTemplateDevices(vendorTypes) {
    const templateSelect = $('#template-device');
    const currentValue = templateSelect.val();

    templateSelect.empty();
    templateSelect.append('<option value="">Select a device...</option>');

    if (allDevices.length === 0) {
        templateSelect.append('<option value="">No devices found</option>');
        return;
    }

    let matchingDevices = allDevices;

    // If vendor_types is set (non-empty array), filter devices by platform
    if (vendorTypes && vendorTypes.length > 0) {
        matchingDevices = allDevices.filter(device => {
            const platform = device.platform || '';
            // Match if platform matches any of the vendor types
            return vendorTypes.some(vt => platform === vt || platform.startsWith(vt));
        });

        if (matchingDevices.length === 0) {
            templateSelect.append(`<option value="" disabled>No matching devices found</option>`);
            return;
        }
    }

    matchingDevices.forEach(function(device) {
        const displayName = device.display || device.name;
        const deviceValue = device.name;
        const platform = device.platform || '';

        const option = `<option value="${deviceValue}" data-name="${device.name}" data-platform="${platform}">${displayName}</option>`;
        templateSelect.append(option);
    });

    // Restore previous value if still valid
    if (currentValue && templateSelect.find(`option[value="${currentValue}"]`).length > 0) {
        templateSelect.val(currentValue);
    }
}

function loadTemplates() {
    const select = $('#template-select');
    select.html('<option value="">Loading templates...</option>');

    $.get('/api/templates')
        .done(function(data) {
            select.empty();
            select.append('<option value="">Select a template...</option>');

            // Handle both legacy format (data.templates) and microservice format (data.data.templates)
            const templates = data.templates || (data.data && data.data.templates) || [];
            if (data.success && templates.length > 0) {
                // Store templates globally
                allTemplates = templates;

                templates.forEach(function(template) {
                    const templateName = template.name || template;
                    const vendorTypes = template.vendor_types || [];
                    // Store vendor_types as JSON in data attribute
                    select.append(`<option value="${templateName}" data-vendor-types='${JSON.stringify(vendorTypes)}'>${templateName}</option>`);
                });
            } else {
                select.append('<option value="">No templates found</option>');
            }
        })
        .fail(function() {
            select.html('<option value="">Error loading templates</option>');
        });
}

// Load templates when the template tab is shown
$('#template-tab').on('shown.bs.tab', function() {
    loadTemplates();
});

// Filter devices when template is selected
$('#template-select').on('change', function() {
    const selectedOption = $(this).find('option:selected');
    const vendorTypesStr = selectedOption.data('vendor-types') || '';
    // Parse vendor types - could be JSON array or empty string
    let vendorTypes = [];
    if (vendorTypesStr) {
        try {
            vendorTypes = typeof vendorTypesStr === 'string' ? JSON.parse(vendorTypesStr) : vendorTypesStr;
        } catch (e) {
            vendorTypes = [];
        }
    }
    filterTemplateDevices(vendorTypes);
});

function resetStatus() {
    $('#status-idle, #status-loading, #status-success, #status-error').hide();
}

function showStatus(status, data = {}) {
    resetStatus();

    switch(status) {
        case 'idle':
            $('#status-idle').show();
            break;
        case 'loading':
            $('#status-loading').show();
            break;
        case 'success':
            $('#success-task-id').text(data.taskId || 'Unknown');
            $('#status-success').show();
            break;
        case 'error':
            $('#error-message').text(data.message || 'Unknown error');
            $('#status-error').show();
            break;
    }
}

function executeGetConfig() {
    const devices = $('#get-device').val(); // Now returns array
    const library = $('#get-library').val();
    const command = $('#get-command').val();
    const username = $('#get-username').val();
    const password = $('#get-password').val();
    const enableCache = $('#get-cache').is(':checked');
    const useTextFsm = $('#get-use-textfsm').is(':checked');
    const useTtp = $('#get-use-ttp').is(':checked');
    const ttpTemplate = $('#get-ttp-template').val();

    if (!devices || devices.length === 0) {
        showStatus('error', { message: 'Please select at least one device' });
        return;
    }

    // Use default credentials if not provided
    const creds = loadDefaultCredentials();
    const finalUsername = username || creds.username;
    const finalPassword = password || creds.password;

    if (!finalUsername || !finalPassword) {
        showStatus('error', { message: 'Please provide credentials or set defaults in Settings' });
        return;
    }

    showStatus('loading');

    const taskIds = [];
    let completed = 0;

    // Send command to each device
    devices.forEach(function(device) {
        // Fetch device connection info first
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

                if (enableCache) {
                    payload.cache = {
                        enabled: true,
                        ttl: 300
                    };
                }

                // Add args for parsing options
                if (useTextFsm || useTtp) {
                    payload.args = {};
                    if (useTextFsm) {
                        payload.args.use_textfsm = true;
                    }
                    if (useTtp) {
                        payload.args.use_ttp = true;
                        if (ttpTemplate && ttpTemplate.trim() !== '') {
                            payload.args.ttp_template = ttpTemplate;
                        }
                    }
                }

                $.ajax({
                    url: '/api/deploy/getconfig',
                    method: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({
                        library: library,
                        payload: payload,
                        device_name: device  // Include device name for tracking
                    }),
                    timeout: 30000
                })
                .done(function(data) {
                    // API returns: {status: 'success', data: {task_id: '...', ...}}
                    const taskId = data.data?.task_id || data.task_id || data.id;
                    if (taskId) {
                        taskIds.push(taskId);
                    }
                    completed++;

                    if (completed === devices.length) {
                        const taskIdList = taskIds.join(', ');
                        showStatus('success', { taskId: `${taskIds.length} tasks created` });

                        // Redirect to job monitor after 3 seconds
                        setTimeout(function() {
                            window.location.href = '/monitor';
                        }, 3000);
                    }
                })
                .fail(function(xhr, status, error) {
                    completed++;
                    let errorMsg = 'Failed to execute command on ' + device;
                    if (xhr.responseJSON && xhr.responseJSON.error) {
                        errorMsg += ': ' + xhr.responseJSON.error;
                    }
                    console.error(errorMsg);

                    if (completed === devices.length) {
                        showStatus('error', { message: `Completed with errors. ${taskIds.length} of ${devices.length} successful` });
                    }
                });
            })
            .fail(function() {
                completed++;
                console.error('Failed to fetch device info for ' + device);
                if (completed === devices.length) {
                    showStatus('error', { message: `Failed to fetch device info` });
                }
            });
    });
}

function executeSetConfig() {
    const devices = $('#set-device').val(); // Now returns array
    const library = $('#set-library').val();
    const username = $('#set-username').val();
    const password = $('#set-password').val();
    const dryRun = $('#set-dry-run').is(':checked');

    if (!devices || devices.length === 0) {
        showStatus('error', { message: 'Please select at least one device' });
        return;
    }

    // Set Config tab only supports manual configuration
    const config = $('#set-config').val();
    if (!config.trim()) {
        showStatus('error', { message: 'Please enter configuration commands' });
        return;
    }

    // Collect pre/post check options
    const enableChecks = $('#set-enable-checks').is(':checked');
    const preCheckCommand = $('#set-pre-check-command').val().trim();
    const preCheckMatch = $('#set-pre-check-match').val().trim();
    const postCheckCommand = $('#set-post-check-command').val().trim();
    const postCheckMatch = $('#set-post-check-match').val().trim();

    if (enableChecks && !preCheckCommand && !postCheckCommand) {
        showStatus('error', { message: 'Please enter at least one pre or post-check command' });
        return;
    }

    const commands = config.split('\n').filter(cmd => cmd.trim() !== '');
    const checkOptions = {
        enabled: enableChecks,
        preCheckCommand: preCheckCommand,
        preCheckMatch: preCheckMatch,
        postCheckCommand: postCheckCommand,
        postCheckMatch: postCheckMatch
    };
    deployToDevices(devices, library, commands, username, password, dryRun, checkOptions);
}

function deployToDevices(devices, library, commands, username, password, dryRun, checkOptions) {
    showStatus('loading');

    // Use default credentials if not provided
    const creds = loadDefaultCredentials();
    const finalUsername = username || creds.username;
    const finalPassword = password || creds.password;

    if (!finalUsername || !finalPassword) {
        showStatus('error', { message: 'Please provide credentials or set defaults in Settings' });
        return;
    }

    // Default check options
    checkOptions = checkOptions || {
        enabled: false,
        preCheckCommand: '',
        preCheckMatch: '',
        postCheckCommand: '',
        postCheckMatch: ''
    };

    const taskIds = [];
    const dryRunResults = [];  // Collect dry run results
    let completed = 0;
    const endpoint = dryRun ? '/api/deploy/setconfig/dry-run' : '/api/deploy/setconfig';

    // Send config to each device
    devices.forEach(function(device) {
        // Fetch device connection info first
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
                    config: commands,
                    queue_strategy: "pinned"
                };

                // Add pre_checks if enabled and command is provided
                if (checkOptions.enabled && checkOptions.preCheckCommand) {
                    const matchArray = checkOptions.preCheckMatch ?
                        checkOptions.preCheckMatch.split(',').map(s => s.trim()).filter(s => s) :
                        [];

                    payload.pre_checks = [{
                        get_config_args: {
                            command: checkOptions.preCheckCommand
                        },
                        match_type: "include",
                        match_str: matchArray  // Array of strings that must be in output (empty = just capture)
                    }];
                }

                // Add post_checks if enabled and command is provided
                if (checkOptions.enabled && checkOptions.postCheckCommand) {
                    const matchArray = checkOptions.postCheckMatch ?
                        checkOptions.postCheckMatch.split(',').map(s => s.trim()).filter(s => s) :
                        [];

                    payload.post_checks = [{
                        get_config_args: {
                            command: checkOptions.postCheckCommand
                        },
                        match_type: "include",
                        match_str: matchArray
                    }];
                }

                $.ajax({
                    url: endpoint,
                    method: 'POST',
                    contentType: 'application/json',
                    data: JSON.stringify({
                        library: library,
                        payload: payload,
                        device_name: device  // Include device name for tracking
                    }),
                    timeout: 30000
                })
                .done(function(data) {
                    completed++;

                    if (dryRun) {
                        // For dry run, collect rendered config
                        const renderedConfig = data.data?.rendered_config || data.rendered_config || '';
                        dryRunResults.push({
                            device: device,
                            config: Array.isArray(renderedConfig) ? renderedConfig.join('\n') : renderedConfig
                        });

                        if (completed === devices.length) {
                            // Show dry run results in modal
                            showDryRunResults(dryRunResults);
                        }
                    } else {
                        // API returns: {status: 'success', data: {task_id: '...', ...}}
                        const taskId = data.data?.task_id || data.task_id || data.id;
                        if (taskId) {
                            taskIds.push(taskId);
                        }

                        if (completed === devices.length) {
                            showStatus('success', { taskId: `${taskIds.length} tasks created` });

                            // Redirect to job monitor after 3 seconds
                            setTimeout(function() {
                                window.location.href = '/monitor';
                            }, 3000);
                        }
                    }
                })
                .fail(function(xhr, status, error) {
                    completed++;
                    let errorMsg = 'Failed to deploy to ' + device;
                    if (xhr.responseJSON && xhr.responseJSON.error) {
                        errorMsg += ': ' + xhr.responseJSON.error;
                    }
                    console.error(errorMsg);

                    if (completed === devices.length) {
                        showStatus('error', { message: `Completed with errors. ${taskIds.length} of ${devices.length} successful` });
                    }
                });
            })
            .fail(function() {
                completed++;
                console.error('Failed to fetch device info for ' + device);
                if (completed === devices.length) {
                    showStatus('error', { message: `Failed to fetch device info` });
                }
            });
    });
}

function oldExecuteSetConfigSingle() {
    const device = $('#set-device').val();
    const library = $('#set-library').val();
    const config = $('#set-config').val();
    const username = $('#set-username').val();
    const password = $('#set-password').val();
    const dryRun = $('#set-dry-run').is(':checked');

    if (!device) {
        showStatus('error', { message: 'Please select a device' });
        return;
    }

    if (!config.trim()) {
        showStatus('error', { message: 'Please enter configuration commands' });
        return;
    }

    showStatus('loading');

    // Split config into array of commands
    const commands = config.split('\n').filter(cmd => cmd.trim() !== '');

    const payload = {
        connection_args: {
            device_type: "cisco_ios",  // Default, can be made configurable
            host: device,
            username: username,
            password: password
        },
        config: commands
    };

    const endpoint = dryRun ? '/api/deploy/setconfig/dry-run' : '/api/deploy/setconfig';

    $.ajax({
        url: endpoint,
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            library: library,
            payload: payload
        }),
        timeout: 30000
    })
    .done(function(data) {
        // API returns: {status: 'success', data: {task_id: '...', ...}}
        const taskId = data.data?.task_id || data.task_id || data.id;
        showStatus('success', { taskId: taskId });

        // Redirect to job monitor after 3 seconds
        setTimeout(function() {
            window.location.href = '/monitor';
        }, 3000);

        // Poll for result
        if (taskId) {
            pollTaskResult(taskId);
        }
    })
    .fail(function(xhr, status, error) {
        let errorMsg = 'Failed to deploy configuration';
        if (xhr.responseJSON && xhr.responseJSON.error) {
            errorMsg = xhr.responseJSON.error;
        } else if (error) {
            errorMsg = error;
        }
        showStatus('error', { message: errorMsg });
    });
}

function pollTaskResult(taskId, attempts = 0) {
    if (attempts > 20) {  // Stop after 20 attempts (40 seconds)
        return;
    }

    setTimeout(function() {
        $.get('/api/task/' + taskId)
            .done(function(data) {
                // API returns: {status: 'success', data: {task_status: '...', task_result: ...}}
                const taskData = data.data || data;
                const status = taskData.task_status || taskData.status;

                if (status === 'finished' || status === 'completed') {
                    // Show result in modal
                    showResultModal(taskData);
                } else if (status === 'failed') {
                    showStatus('error', {
                        message: 'Task failed: ' + (taskData.task_errors || 'Unknown error')
                    });
                } else if (status === 'queued' || status === 'started') {
                    // Continue polling
                    pollTaskResult(taskId, attempts + 1);
                }
            })
            .fail(function() {
                // Continue polling on error (task might not be created yet)
                if (attempts < 5) {
                    pollTaskResult(taskId, attempts + 1);
                }
            });
    }, 2000);  // Poll every 2 seconds
}

function showResultModal(taskData) {
    const result = taskData.task_result || taskData.data || 'No result available';

    let formattedResult = result;
    if (typeof result === 'object') {
        formattedResult = JSON.stringify(result, null, 2);
    }

    $('#result-content').text(formattedResult);

    const modal = new bootstrap.Modal(document.getElementById('resultModal'));
    modal.show();
}

// Deploy template from the new Push Standalone Template tab
function deployTemplate() {
    const devices = $('#template-device').val();
    const library = $('#template-library').val();
    const templateName = $('#template-select').val();
    const username = $('#template-username').val();
    const password = $('#template-password').val();
    const dryRun = $('#template-dry-run').is(':checked');

    if (!devices || devices.length === 0) {
        showStatus('error', { message: 'Please select at least one device' });
        return;
    }

    if (!templateName) {
        showStatus('error', { message: 'Please select a template' });
        return;
    }

    // Collect pre/post check options
    const enableChecks = $('#template-enable-checks').is(':checked');
    const preCheckCommand = $('#template-pre-check-command').val().trim();
    const preCheckMatch = $('#template-pre-check-match').val().trim();
    const postCheckCommand = $('#template-post-check-command').val().trim();
    const postCheckMatch = $('#template-post-check-match').val().trim();

    if (enableChecks && !preCheckCommand && !postCheckCommand) {
        showStatus('error', { message: 'Please enter at least one pre or post-check command' });
        return;
    }

    let templateVars = {};

    // Collect variables from form or JSON
    try {
        templateVars = collectTemplateVariables('#template-vars-container');
    } catch (e) {
        showStatus('error', { message: e.message });
        return;
    }

    showStatus('loading');

    const checkOptions = {
        enabled: enableChecks,
        preCheckCommand: preCheckCommand,
        preCheckMatch: preCheckMatch,
        postCheckCommand: postCheckCommand,
        postCheckMatch: postCheckMatch
    };

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
            // Split rendered config into commands
            const commands = data.rendered_config.split('\n').filter(cmd => cmd.trim() !== '');
            deployToDevices(devices, library, commands, username, password, dryRun, checkOptions);
        } else {
            showStatus('error', { message: 'Failed to render template' });
        }
    })
    .fail(function(xhr, status, error) {
        showStatus('error', { message: 'Template rendering failed: ' + (xhr.responseJSON?.error || error) });
    });
}

// ==================== Scheduled Deployments ====================

let currentScheduleType = null;

// Schedule SetConfig button
$(document).on('click', '#schedule-setconfig-btn', function() {
    currentScheduleType = 'setconfig';
    openScheduleModal();
});

// Schedule Template button
$(document).on('click', '#schedule-template-btn', function() {
    currentScheduleType = 'template';
    openScheduleModal();
});

function openScheduleModal() {
    $('#schedule-deploy-type').val(currentScheduleType);
    $('#schedule-deploy-form')[0].reset();
    
    // Show datetime picker by default
    $('#schedule-deploy-datetime-section').show();
    $('#schedule-deploy-time-section').hide();
    $('#schedule-deploy-day-week-section').hide();
    $('#schedule-deploy-day-month-section').hide();
    
    const modal = new bootstrap.Modal(document.getElementById('scheduleDeployModal'));
    modal.show();
}

// Handle schedule type changes
$(document).on('change', '#schedule-deploy-type-select', function() {
    const scheduleType = $(this).val();
    
    // Hide all sections
    $('#schedule-deploy-datetime-section').hide();
    $('#schedule-deploy-time-section').hide();
    $('#schedule-deploy-day-week-section').hide();
    $('#schedule-deploy-day-month-section').hide();
    
    // Show relevant sections
    if (scheduleType === 'once') {
        $('#schedule-deploy-datetime-section').show();
        $('#schedule-deploy-datetime').prop('required', true);
        $('#schedule-deploy-time').prop('required', false);
    } else if (scheduleType === 'daily') {
        $('#schedule-deploy-time-section').show();
        $('#schedule-deploy-datetime').prop('required', false);
        $('#schedule-deploy-time').prop('required', true);
    } else if (scheduleType === 'weekly') {
        $('#schedule-deploy-time-section').show();
        $('#schedule-deploy-day-week-section').show();
        $('#schedule-deploy-datetime').prop('required', false);
        $('#schedule-deploy-time').prop('required', true);
    } else if (scheduleType === 'monthly') {
        $('#schedule-deploy-time-section').show();
        $('#schedule-deploy-day-month-section').show();
        $('#schedule-deploy-datetime').prop('required', false);
        $('#schedule-deploy-time').prop('required', true);
    }
});

// Confirm schedule button
$(document).on('click', '#confirm-schedule-deploy-btn', function() {
    const deployType = $('#schedule-deploy-type').val();
    const scheduleType = $('#schedule-deploy-type-select').val();
    
    let scheduledTime, dayOfWeek, dayOfMonth;
    
    if (scheduleType === 'once') {
        const localTime = $('#schedule-deploy-datetime').val();
        if (!localTime) {
            alert('Please select a date and time');
            return;
        }
        // Keep the time as-is in the system timezone (no UTC conversion)
        // The backend expects times in the container's local timezone
        scheduledTime = localTime;
    } else {
        scheduledTime = $('#schedule-deploy-time').val();
        if (!scheduledTime) {
            alert('Please select a time');
            return;
        }
        
        if (scheduleType === 'weekly') {
            dayOfWeek = parseInt($('#schedule-deploy-day-week').val());
        } else if (scheduleType === 'monthly') {
            dayOfMonth = parseInt($('#schedule-deploy-day-month').val());
            if (!dayOfMonth || dayOfMonth < 1 || dayOfMonth > 31) {
                alert('Please enter a valid day of month (1-31)');
                return;
            }
        }
    }
    
    // Collect deployment configuration
    let deployConfig = {};
    
    if (deployType === 'setconfig') {
        const devices = $('#set-device').val();
        const config = $('#set-config').val();
        const username = $('#set-username').val();
        const password = $('#set-password').val();
        const dryRun = $('#set-dry-run').is(':checked');
        
        if (!devices || devices.length === 0) {
            alert('Please select at least one device');
            return;
        }
        
        if (!config.trim()) {
            alert('Please enter configuration commands');
            return;
        }
        
        deployConfig = {
            type: 'setconfig',
            devices: devices,
            config: config,
            username: username,
            password: password,
            dry_run: dryRun
        };
    } else if (deployType === 'template') {
        const devices = $('#template-device').val();
        const templateName = $('#template-select').val();
        const username = $('#template-username').val();
        const password = $('#template-password').val();
        const dryRun = $('#template-dry-run').is(':checked');
        
        if (!devices || devices.length === 0) {
            alert('Please select at least one device');
            return;
        }
        
        if (!templateName) {
            alert('Please select a template');
            return;
        }
        
        // Collect template variables
        const templateVars = {};
        $('.template-var-input').each(function() {
            const varName = $(this).data('var-name');
            const varValue = $(this).val();
            if (varValue) {
                templateVars[varName] = varValue;
            }
        });
        
        deployConfig = {
            type: 'template',
            devices: devices,
            template_name: templateName,
            variables: templateVars,
            username: username,
            password: password,
            dry_run: dryRun
        };
    }
    
    const scheduleData = {
        operation_type: 'config_deploy',
        schedule_type: scheduleType,
        scheduled_time: scheduledTime,
        day_of_week: dayOfWeek,
        day_of_month: dayOfMonth,
        config: deployConfig
    };
    
    $.ajax({
        url: '/api/scheduled-config-operations',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(scheduleData)
    })
    .done(function(data) {
        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('scheduleDeployModal')).hide();
        } else {
            alert('Error: ' + (data.error || 'Failed to schedule deployment'));
        }
    })
    .fail(function(xhr) {
        alert('Failed to schedule deployment: ' + (xhr.responseJSON?.error || 'Unknown error'));
    });
});

/**
 * Show dry run results in a modal
 */
function showDryRunResults(results) {
    // Build the content for the modal
    let content = '';
    results.forEach(function(result) {
        content += `<div class="mb-3">
            <h6 class="text-primary"><i class="fas fa-server"></i> ${result.device}</h6>
            <pre class="bg-dark text-light p-3 rounded" style="max-height: 300px; overflow-y: auto; white-space: pre-wrap;">${escapeHtml(result.config)}</pre>
        </div>`;
    });

    // Set the modal content and show it
    $('#result-content').html(content);
    showStatus('success', { taskId: `Dry run completed for ${results.length} device(s)` });

    const modal = new bootstrap.Modal(document.getElementById('resultModal'));
    modal.show();
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}
