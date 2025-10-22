// Service Stacks Management
let allDevices = [];
let allTemplates = [];
let serviceCounter = 0;
let autoSyncInterval = null;

$(document).ready(function() {
    // Load initial data
    loadDevices();
    loadTemplates();
    loadServiceStacks();
    loadStackTemplates();

    // Check for URL parameter to auto-open stack details modal
    const urlParams = new URLSearchParams(window.location.search);
    const viewStackId = urlParams.get('view');
    if (viewStackId) {
        // Wait a bit for data to load, then open the modal
        setTimeout(function() {
            viewStackDetails(viewStackId);
            // Clear the URL parameter
            window.history.replaceState({}, document.title, window.location.pathname);
        }, 500);
    }

    // Start auto-sync for deploying services (every 5 seconds)
    startAutoSync();

    // Update server time display every second
    updateServerTime();
    setInterval(updateServerTime, 1000);

    // Update timezone labels when modal opens
    $('#scheduleStackModal').on('show.bs.modal', function() {
        updateTimezoneLabels();
    });

    // Set current time button
    $('#set-current-time-btn').click(function() {
        setCurrentServerTime();
    });

    // Event handlers
    // Custom stack creation removed - only template-based creation allowed
    // $('#create-stack-btn').click(function() {
    //     openStackModal();
    // });

    // $('#save-stack-btn').click(function() {
    //     saveServiceStack();
    // });

    // $('#add-service-btn').click(function() {
    //     addServiceToStack();
    // });

    $('#add-shared-var-btn').click(function() {
        addSharedVariable();
    });

    // Search handlers
    $('#search-templates').on('input', function() {
        filterStackTemplates($(this).val());
    });

    $('#search-stacks').on('input', function() {
        filterDeployedStacks($(this).val());
    });

    // Stack Template handlers
    $('#create-template-btn').click(function() {
        openStackTemplateModal();
    });

    // Use event delegation for save button to ensure it always works
    $(document).on('click', '#save-stack-template-btn', function(e) {
        e.preventDefault();
        console.log('Save stack template button clicked');
        saveStackTemplate();
    });

    $('#add-template-service-btn').click(function() {
        addServiceToTemplate();
    });

    // Sync states button handler (manual sync)
    $('#sync-states-btn').click(function() {
        syncServiceStates(true); // true = show UI feedback
    });
});

/**
 * Start automatic state syncing in background
 */
function startAutoSync() {
    // Sync every 5 seconds
    autoSyncInterval = setInterval(function() {
        syncServiceStates(false); // false = silent, no UI feedback
    }, 5000);
}

/**
 * Stop automatic state syncing
 */
function stopAutoSync() {
    if (autoSyncInterval) {
        clearInterval(autoSyncInterval);
        autoSyncInterval = null;
    }
}

/**
 * Sync service instance states from Netstacker
 * @param {boolean} showUI - Whether to show UI feedback (button state, status messages)
 */
function syncServiceStates(showUI) {
    showUI = showUI !== false; // Default to true if not specified

    const btn = $('#sync-states-btn');
    if (showUI) {
        btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> Syncing...');
    }

    $.ajax({
        url: '/api/services/instances/sync-states',
        method: 'POST',
        contentType: 'application/json'
    })
    .done(function(data) {
        if (data.success) {
            // Only reload if something changed
            if (data.updated > 0 || data.failed > 0 || data.stacks_updated > 0) {
                loadServiceStacks();

                // Show status message only for manual sync
                if (showUI) {
                    let message = 'States synced: ';
                    if (data.updated > 0) {
                        message += `${data.updated} deployed`;
                    }
                    if (data.failed > 0) {
                        message += `, ${data.failed} failed`;
                    }
                    if (data.stacks_updated > 0) {
                        message += `, ${data.stacks_updated} stacks updated`;
                    }
                    if (data.updated === 0 && data.failed === 0) {
                        message += 'no changes';
                    }

                    showStatus('success', {
                        message: message
                    });
                }
            }
        } else if (showUI) {
            showStatus('error', {
                message: 'Failed to sync states: ' + (data.error || 'Unknown error')
            });
        }
    })
    .fail(function(xhr) {
        if (showUI) {
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'Unknown error';
            showStatus('error', {
                message: 'Failed to sync states: ' + error
            });
        }
    })
    .always(function() {
        if (showUI) {
            btn.prop('disabled', false).html('<i class="fas fa-sync"></i> Refresh Status');
        }
    });
}

/**
 * Load devices from API
 */
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
        if (data.success && data.devices) {
            allDevices = data.devices;
            console.log('Loaded ' + allDevices.length + ' devices');
        }
    })
    .fail(function() {
        console.error('Failed to load devices');
    });
}

/**
 * Load templates from API
 */
function loadTemplates() {
    $.get('/api/templates')
        .done(function(data) {
            if (data.success && data.templates) {
                allTemplates = data.templates;
            }
        })
        .fail(function() {
            console.error('Failed to load templates');
        });
}

/**
 * Load and display all service stacks
 */
function loadServiceStacks() {
    const container = $('#stacks-container');
    container.html('<div class="text-center"><div class="spinner-border"></div></div>');

    $.get('/api/service-stacks')
        .done(function(data) {
            if (data.success && data.stacks) {
                renderServiceStacks(data.stacks);
            } else {
                container.html('<div class="alert alert-warning">No service stacks found</div>');
            }
        })
        .fail(function() {
            container.html('<div class="alert alert-danger">Failed to load service stacks</div>');
        });
}

/**
 * Render service stacks as cards
 */
function renderServiceStacks(stacks) {
    const container = $('#stacks-container');

    if (stacks.length === 0) {
        container.html('<div class="alert alert-info">No service stacks created yet. Click "Create Stack" to get started.</div>');
        return;
    }

    let html = '<div class="row">';

    stacks.forEach(function(stack) {
        const stateColors = {
            'pending': 'secondary',
            'deploying': 'warning',
            'deployed': 'success',
            'partial': 'warning',
            'failed': 'danger'
        };

        const stateColor = stateColors[stack.state] || 'secondary';

        // Calculate unique device count from all services
        const allDevicesInStack = new Set();
        if (stack.services && Array.isArray(stack.services)) {
            stack.services.forEach(service => {
                if (service.devices && Array.isArray(service.devices)) {
                    service.devices.forEach(device => allDevicesInStack.add(device));
                } else if (service.device) {
                    allDevicesInStack.add(service.device);
                }
            });
        }
        const deviceCount = allDevicesInStack.size;
        const deviceList = Array.from(allDevicesInStack);
        const serviceCount = stack.services ? stack.services.length : 0;

        html += `
            <div class="col-md-6 col-lg-4 mb-3">
                <div class="card h-100 stack-card" data-stack-id="${stack.stack_id}" style="cursor: pointer;">
                    <div class="card-header d-flex justify-content-between align-items-center">
                        <h6 class="mb-0">${stack.name}</h6>
                        <div>
                            <span class="badge bg-${stateColor}">${stack.state}</span>
                            ${stack.has_pending_changes ? '<span class="badge bg-info ms-1"><i class="fas fa-exclamation-circle"></i> Pending Updates</span>' : ''}
                        </div>
                    </div>
                    <div class="card-body">
                        ${stack.description ? `<p class="text-muted small">${stack.description}</p>` : ''}

                        <div class="mb-2">
                            <small>
                                <i class="fas fa-cogs text-primary"></i> <strong>${serviceCount}</strong> service${serviceCount !== 1 ? 's' : ''}
                            </small>
                        </div>

                        <div class="mb-2">
                            <small>
                                <i class="fas fa-server text-info"></i> <strong>${deviceCount}</strong> device${deviceCount !== 1 ? 's' : ''}
                            </small>
                        </div>

                        ${deviceList.length > 0 ? `
                            <div class="mb-2">
                                <small class="text-muted">
                                    ${deviceList.slice(0, 3).join(', ')}${deviceList.length > 3 ? '...' : ''}
                                </small>
                            </div>
                        ` : ''}

                        <div class="mt-3">
                            <small class="text-muted">
                                Created: ${formatDate(stack.created_at)}
                            </small>
                        </div>
                    </div>
                    <div class="card-footer bg-transparent">
                        <div class="btn-group w-100" role="group">
                            <button class="btn btn-sm btn-outline-primary view-stack-btn" data-stack-id="${stack.stack_id}">
                                <i class="fas fa-eye"></i> View
                            </button>
                            <button class="btn btn-sm btn-outline-secondary edit-stack-btn" data-stack-id="${stack.stack_id}">
                                <i class="fas fa-edit"></i> Edit
                            </button>
                            ${stack.state === 'deployed' || stack.state === 'partial' ? `
                                <button class="btn btn-sm btn-outline-info validate-stack-btn" data-stack-id="${stack.stack_id}">
                                    <i class="fas fa-check-circle"></i> Validate
                                </button>
                            ` : ''}
                            ${stack.state === 'pending' || stack.state === 'deploying' ? `
                                <button class="btn btn-sm btn-outline-success deploy-stack-btn" data-stack-id="${stack.stack_id}" ${stack.state === 'deploying' ? 'disabled' : ''}>
                                    <i class="fas fa-rocket"></i> ${stack.state === 'deploying' ? 'Deploying...' : 'Deploy'}
                                </button>
                            ` : `
                                <button class="btn btn-sm ${stack.has_pending_changes ? 'btn-warning' : 'btn-outline-warning'} redeploy-stack-btn" data-stack-id="${stack.stack_id}">
                                    <i class="fas fa-${stack.has_pending_changes ? 'exclamation-triangle' : 'redo'}"></i> ${stack.has_pending_changes ? 'Deploy Updates' : 'Redeploy'}
                                </button>
                            `}
                            <button class="btn btn-sm btn-outline-danger delete-stack-btn" data-stack-id="${stack.stack_id}">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    });

    html += '</div>';
    container.html(html);

    // Attach event handlers
    // Make entire card clickable to view details
    $('.stack-card').click(function(e) {
        // Don't trigger if clicking on action buttons
        if ($(e.target).closest('.btn').length === 0) {
            const stackId = $(this).data('stack-id');
            viewStackDetails(stackId);
        }
    });

    $('.view-stack-btn').click(function(e) {
        e.stopPropagation();
        const stackId = $(this).data('stack-id');
        viewStackDetails(stackId);
    });

    $('.edit-stack-btn').click(function(e) {
        e.stopPropagation();
        const stackId = $(this).data('stack-id');
        editStack(stackId);
    });

    $('.deploy-stack-btn').click(function(e) {
        e.stopPropagation();
        const stackId = $(this).data('stack-id');
        deployStack(stackId);
    });

    $('.validate-stack-btn').click(function(e) {
        e.stopPropagation();
        const stackId = $(this).data('stack-id');
        validateStack(stackId);
    });

    $('.redeploy-stack-btn').click(function(e) {
        e.stopPropagation();
        const stackId = $(this).data('stack-id');
        redeployStack(stackId);
    });

    $('.delete-stack-btn').click(function(e) {
        e.stopPropagation();
        const stackId = $(this).data('stack-id');
        deleteStack(stackId);
    });
}

/**
 * Redeploy an existing stack
 */
function redeployStack(stackId) {
    // Reset stack state to pending before deploying
    $.ajax({
        url: '/api/service-stacks/' + encodeURIComponent(stackId),
        method: 'PUT',
        contentType: 'application/json',
        data: JSON.stringify({ state: 'pending' })
    })
    .done(function() {
        // Now deploy
        deployStack(stackId);
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON ? xhr.responseJSON.error : 'Unknown error';
        alert('Failed to reset stack state: ' + error);
    });
}

/**
 * Validate a service stack - validates all deployed services
 */
function validateStack(stackId) {
    showStatus('info', {
        message: 'Validating service stack...',
        details: 'Checking all deployed services against device configurations.'
    });

    // Get credentials from settings
    let username, password;
    try {
        const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
        username = settings.default_username;
        password = settings.default_password;
        console.log('Validate stack - Credentials from settings:', { username, hasPassword: !!password });
    } catch (e) {
        console.error('Error reading credentials from settings:', e);
    }

    $.ajax({
        url: '/api/service-stacks/' + encodeURIComponent(stackId) + '/validate',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            username: username,
            password: password
        }),
        timeout: 300000 // 5 minute timeout
    })
    .done(function(data) {
        if (data.success) {
            const allValid = data.all_valid;
            const results = data.results || [];

            let detailsHtml = '<strong>Validation Results:</strong><ul class="mb-0">';
            results.forEach(function(result) {
                const icon = result.valid ? '<i class="fas fa-check-circle text-success"></i>' : '<i class="fas fa-times-circle text-danger"></i>';
                detailsHtml += `<li>${icon} ${result.service_name}: ${result.message}`;
                if (result.missing_lines && result.missing_lines.length > 0) {
                    detailsHtml += '<br><small class="text-muted">Missing: ' + result.missing_lines.join(', ') + '</small>';
                }
                detailsHtml += '</li>';
            });
            detailsHtml += '</ul>';

            showStatus(allValid ? 'success' : 'warning', {
                message: allValid ? '✓ All services validated successfully!' : '⚠ Some services have configuration drift',
                details: detailsHtml
            });
        } else {
            showStatus('error', {
                message: '✗ Stack validation failed',
                details: data.error || 'Unknown error'
            });
        }
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON ? xhr.responseJSON.error : 'Request failed';
        showStatus('error', {
            message: '✗ Failed to validate stack',
            details: error
        });
    });
}

/**
 * Edit an existing stack
 */
function editStack(stackId) {
    $.get('/api/service-stacks/' + encodeURIComponent(stackId))
        .done(function(data) {
            if (data.success && data.stack) {
                openStackModal(data.stack);
            } else {
                alert('Failed to load stack: ' + (data.error || 'Unknown error'));
            }
        })
        .fail(function(xhr) {
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'Unknown error';
            alert('Failed to load stack: ' + error);
        });
}

/**
 * Add a shared variable key-value pair
 */
function addSharedVariable(key, value) {
    $('#no-shared-vars-msg').remove();

    const varHtml = `
        <div class="shared-var-item mb-2 d-flex gap-2">
            <input type="text" class="form-control form-control-sm shared-var-key" placeholder="Variable name" value="${key || ''}" style="flex: 1;">
            <input type="text" class="form-control form-control-sm shared-var-value" placeholder="Variable value" value="${value || ''}" style="flex: 2;">
            <button type="button" class="btn btn-sm btn-danger remove-shared-var-btn">
                <i class="fas fa-times"></i>
            </button>
        </div>
    `;

    $('#shared-vars-list').append(varHtml);

    // Attach remove handler
    $('#shared-vars-list').find('.shared-var-item').last().find('.remove-shared-var-btn').click(function() {
        $(this).closest('.shared-var-item').remove();

        if ($('#shared-vars-list .shared-var-item').length === 0) {
            $('#shared-vars-list').html('<p class="text-muted text-center mb-0" id="no-shared-vars-msg"><small>No shared variables. Click "Add Variable" to add one.</small></p>');
        }
    });
}

/**
 * Open modal to create new stack
 */
function openStackModal(stackData) {
    serviceCounter = 0;

    $('#stackModalTitle').text(stackData ? 'Edit Service Stack' : 'Create Service Stack');
    $('#stack-form')[0].reset();
    $('#services-list').html('<p class="text-muted text-center mb-0" id="no-services-msg">No services added yet. Click "Add Service" to begin.</p>');
    $('#shared-vars-list').html('<p class="text-muted text-center mb-0" id="no-shared-vars-msg"><small>No shared variables. Click "Add Variable" to add one.</small></p>');

    if (stackData) {
        $('#stack-id').val(stackData.stack_id);
        $('#stack-name').val(stackData.name);
        $('#stack-description').val(stackData.description || '');

        // Load shared variables
        if (stackData.shared_variables && Object.keys(stackData.shared_variables).length > 0) {
            Object.entries(stackData.shared_variables).forEach(([key, value]) => {
                addSharedVariable(key, value);
            });
        }

        // Load services
        if (stackData.services && stackData.services.length > 0) {
            stackData.services.forEach(function(service) {
                addServiceToStack(service);
            });
        }
    }

    const modal = new bootstrap.Modal(document.getElementById('stackModal'));
    modal.show();
}

/**
 * Add a service to the stack
 */
function addServiceToStack(serviceData) {
    serviceCounter++;
    const serviceId = serviceData ? serviceData.order : serviceCounter;

    $('#no-services-msg').remove();

    const serviceHtml = `
        <div class="service-item border rounded p-3 mb-3" data-service-id="${serviceId}">
            <div class="d-flex justify-content-between align-items-start mb-2">
                <h6>Service #${serviceId}</h6>
                <button type="button" class="btn btn-sm btn-danger remove-service-btn">
                    <i class="fas fa-times"></i>
                </button>
            </div>

            <div class="row">
                <div class="col-md-6 mb-2">
                    <label class="form-label">Service Name *</label>
                    <input type="text" class="form-control service-name" placeholder="e.g., PE Router Config" value="${serviceData ? serviceData.name : ''}" required>
                </div>

                <div class="col-md-6 mb-2">
                    <label class="form-label">Order</label>
                    <input type="number" class="form-control service-order" value="${serviceId}" min="1" required>
                </div>
            </div>

            <div class="row">
                <div class="col-md-6 mb-2">
                    <label class="form-label">Template Stack *</label>
                    <select class="form-select service-template" required>
                        <option value="">Select template stack...</option>
                        ${allTemplates.filter(t => {
                            // Only show complete template stacks (those with delete templates)
                            return t.delete_template;
                        }).map(t => {
                            const templateName = typeof t === 'string' ? t : t.name;
                            const templateDisplay = templateName.replace('.j2', '');
                            const isSelected = serviceData && serviceData.template === templateName;
                            const hasValidation = t.validation_template ? ' (Full Stack)' : ' (Manual Validation)';
                            return `<option value="${templateName}" ${isSelected ? 'selected' : ''}>${templateDisplay}${hasValidation}</option>`;
                        }).join('')}
                    </select>
                </div>

                <div class="col-md-6 mb-2">
                    <div class="d-flex justify-content-between align-items-center mb-1">
                        <label class="form-label mb-0">Devices *</label>
                        <button type="button" class="btn btn-sm btn-outline-primary add-device-btn">
                            <i class="fas fa-plus"></i>
                        </button>
                    </div>
                    <div class="devices-list">
                        <!-- Device dropdowns will be added here -->
                    </div>
                </div>
            </div>

            <div class="row">
                <div class="col-12 mb-2">
                    <label class="form-label">Service Variables</label>
                    <div class="service-variables-container p-2 border rounded">
                        <div class="text-center text-muted">
                            <small>Select a template to load variables...</small>
                        </div>
                    </div>
                </div>
            </div>

            <div class="row">
                <div class="col-12 mb-2">
                    <label class="form-label">Dependencies (comma-separated service names)</label>
                    <input type="text" class="form-control service-dependencies" placeholder="e.g., CE Router Config, VLAN Setup" value="${serviceData && serviceData.depends_on ? serviceData.depends_on.join(', ') : ''}">
                    <small class="form-text text-muted">This service will wait for these services to complete first</small>
                </div>
            </div>

            <div class="row">
                <div class="col-12 mb-2">
                    <div class="form-check">
                        <input class="form-check-input" type="checkbox" id="enable-checks-${serviceId}" ${serviceData && (serviceData.pre_checks || serviceData.post_checks) ? 'checked' : ''}>
                        <label class="form-check-label" for="enable-checks-${serviceId}">
                            Enable Pre/Post Deployment Checks
                        </label>
                    </div>
                </div>
            </div>

            <div class="row checks-container" style="display: ${serviceData && (serviceData.pre_checks || serviceData.post_checks) ? 'flex' : 'none'};">
                <div class="col-md-6 mb-2">
                    <label class="form-label">Pre-Check Command</label>
                    <input type="text" class="form-control pre-check-command" placeholder="show run | i hostname" value="${serviceData && serviceData.pre_checks && serviceData.pre_checks[0] ? serviceData.pre_checks[0].get_config_args.command : ''}">
                    <small class="form-text text-muted">Command to run before deployment</small>
                </div>
                <div class="col-md-6 mb-2">
                    <label class="form-label">Pre-Check Expected Output</label>
                    <input type="text" class="form-control pre-check-match" placeholder="hostname cat" value="${serviceData && serviceData.pre_checks && serviceData.pre_checks[0] ? serviceData.pre_checks[0].match_str.join(', ') : ''}">
                    <small class="form-text text-muted">Text that must be in output</small>
                </div>
            </div>

            <div class="row checks-container" style="display: ${serviceData && (serviceData.pre_checks || serviceData.post_checks) ? 'flex' : 'none'};">
                <div class="col-md-6 mb-2">
                    <label class="form-label">Post-Check Command</label>
                    <input type="text" class="form-control post-check-command" placeholder="show run | i hostname" value="${serviceData && serviceData.post_checks && serviceData.post_checks[0] ? serviceData.post_checks[0].get_config_args.command : ''}">
                    <small class="form-text text-muted">Command to run after deployment</small>
                </div>
                <div class="col-md-6 mb-2">
                    <label class="form-label">Post-Check Expected Output</label>
                    <input type="text" class="form-control post-check-match" placeholder="hostname dog" value="${serviceData && serviceData.post_checks && serviceData.post_checks[0] ? serviceData.post_checks[0].match_str.join(', ') : ''}">
                    <small class="form-text text-muted">Text that must be in output</small>
                </div>
            </div>
        </div>
    `;

    $('#services-list').append(serviceHtml);

    const $serviceItem = $('#services-list').find('.service-item').last();

    // Initialize with at least one device dropdown
    if (serviceData && serviceData.devices) {
        // Load existing devices
        serviceData.devices.forEach(device => {
            addDeviceDropdown($serviceItem, device);
        });
    } else {
        // Add first empty device dropdown
        addDeviceDropdown($serviceItem, null);
    }

    // If we have service data with variables, populate them
    if (serviceData && serviceData.template) {
        loadTemplateVariablesForService($serviceItem, serviceData.template, serviceData.variables);
    }

    // Attach add device button handler
    $serviceItem.find('.add-device-btn').click(function() {
        addDeviceDropdown($serviceItem, null);
    });

    // Attach template change handler
    $serviceItem.find('.service-template').change(function() {
        const template = $(this).val();
        if (template) {
            loadTemplateVariablesForService($serviceItem, template);
        }
    });

    // Attach remove handler
    $serviceItem.find('.remove-service-btn').click(function() {
        $(this).closest('.service-item').remove();

        if ($('#services-list .service-item').length === 0) {
            $('#services-list').html('<p class="text-muted text-center mb-0" id="no-services-msg">No services added yet. Click "Add Service" to begin.</p>');
        }
    });

    // Attach enable checks toggle handler
    $serviceItem.find(`#enable-checks-${serviceId}`).change(function() {
        const $checks = $(this).closest('.service-item').find('.checks-container');
        if ($(this).is(':checked')) {
            $checks.show();
        } else {
            $checks.hide();
        }
    });
}

/**
 * Add a device dropdown to a service
 */
function addDeviceDropdown($serviceItem, selectedDevice) {
    const $devicesList = $serviceItem.find('.devices-list');
    const deviceCount = $devicesList.find('.device-dropdown-item').length;

    const deviceHtml = `
        <div class="device-dropdown-item mb-2 d-flex gap-2">
            <select class="form-select form-select-sm service-device-select" required>
                <option value="">Select device...</option>
                ${allDevices.map(d => `<option value="${d.name}" ${selectedDevice === d.name ? 'selected' : ''}>${d.display || d.name}</option>`).join('')}
            </select>
            ${deviceCount > 0 ? '<button type="button" class="btn btn-sm btn-danger remove-device-btn"><i class="fas fa-times"></i></button>' : ''}
        </div>
    `;

    $devicesList.append(deviceHtml);

    // Attach remove handler (only for additional devices, not the first one)
    if (deviceCount > 0) {
        $devicesList.find('.device-dropdown-item').last().find('.remove-device-btn').click(function() {
            $(this).closest('.device-dropdown-item').remove();
        });
    }
}

/**
 * Load template variables for a service
 */
function loadTemplateVariablesForService($serviceItem, templateName, existingVariables) {
    const $container = $serviceItem.find('.service-variables-container');
    $container.html('<div class="text-center"><small class="text-muted">Loading variables...</small></div>');

    $.get('/api/templates/' + encodeURIComponent(templateName) + '/variables')
        .done(function(data) {
            if (data.success && data.variables) {
                renderTemplateVariablesForm($container, data.variables, existingVariables);
            } else {
                $container.html('<div class="alert alert-warning alert-sm mb-0"><small>No variables found in template</small></div>');
            }
        })
        .fail(function() {
            $container.html('<div class="alert alert-danger alert-sm mb-0"><small>Failed to load template variables</small></div>');
        });
}

/**
 * Render template variables as form inputs
 */
function renderTemplateVariablesForm($container, variables, existingValues) {
    existingValues = existingValues || {};

    if (variables.length === 0) {
        $container.html('<div class="text-muted text-center"><small>No variables required for this template</small></div>');
        return;
    }

    let html = '<div class="row g-2">';

    variables.forEach(function(field) {
        // Handle both string array format and object format
        let fieldName, fieldLabel, fieldValue, fieldType, fieldDescription, fieldOptions, isRequired;

        if (typeof field === 'string') {
            // Simple string format from current API
            fieldName = field;
            fieldLabel = field.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            fieldValue = existingValues[fieldName] || '';
            fieldType = 'text';
            fieldDescription = '';
            fieldOptions = null;
            isRequired = false;
        } else {
            // Object format with metadata
            fieldName = field.name;
            fieldLabel = field.name.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());
            fieldValue = existingValues[fieldName] || field.default || '';
            fieldType = field.type || 'text';
            fieldDescription = field.description || '';
            fieldOptions = field.options || null;
            isRequired = field.required || false;
        }

        html += `<div class="col-md-6">`;
        html += `<label class="form-label small mb-1">${fieldLabel} ${isRequired ? '*' : ''}</label>`;

        if (fieldType === 'select' || fieldType === 'device') {
            html += `<select class="form-select form-select-sm var-input" data-var-name="${fieldName}" ${isRequired ? 'required' : ''}>`;
            html += `<option value="">Select ${fieldLabel}...</option>`;

            if (fieldType === 'device') {
                allDevices.forEach(function(device) {
                    const selected = fieldValue === device.name ? 'selected' : '';
                    html += `<option value="${device.name}" ${selected}>${device.display || device.name}</option>`;
                });
            } else if (fieldOptions) {
                fieldOptions.forEach(function(opt) {
                    const selected = fieldValue === opt ? 'selected' : '';
                    html += `<option value="${opt}" ${selected}>${opt}</option>`;
                });
            }

            html += '</select>';
        } else if (fieldType === 'boolean') {
            html += `<select class="form-select form-select-sm var-input" data-var-name="${fieldName}" ${isRequired ? 'required' : ''}>`;
            html += `<option value="true" ${fieldValue === 'true' || fieldValue === true ? 'selected' : ''}>True</option>`;
            html += `<option value="false" ${fieldValue === 'false' || fieldValue === false ? 'selected' : ''}>False</option>`;
            html += '</select>';
        } else if (fieldType === 'integer' || fieldType === 'number') {
            html += `<input type="number" class="form-control form-control-sm var-input" data-var-name="${fieldName}"
                     value="${fieldValue}" placeholder="${fieldDescription}" ${isRequired ? 'required' : ''}>`;
        } else {
            // Default to text input
            html += `<input type="text" class="form-control form-control-sm var-input" data-var-name="${fieldName}"
                     value="${fieldValue}" placeholder="${fieldDescription}" ${isRequired ? 'required' : ''}>`;
        }

        if (fieldDescription) {
            html += `<small class="form-text text-muted d-block">${fieldDescription}</small>`;
        }

        html += '</div>';
    });

    html += '</div>';
    $container.html(html);
}

/**
 * Save service stack
 */
function saveServiceStack() {
    // Validate form
    const name = $('#stack-name').val().trim();
    if (!name) {
        alert('Stack name is required');
        return;
    }

    const services = [];
    let valid = true;

    $('#services-list .service-item').each(function() {
        const serviceName = $(this).find('.service-name').val().trim();
        const template = $(this).find('.service-template').val();
        const order = parseInt($(this).find('.service-order').val());
        const dependenciesText = $(this).find('.service-dependencies').val().trim();

        // Collect all selected devices
        const devices = [];
        $(this).find('.service-device-select').each(function() {
            const deviceValue = $(this).val();
            if (deviceValue) {
                devices.push(deviceValue);
            }
        });

        if (!serviceName || !template || devices.length === 0) {
            alert('All services must have name, template, and at least one device');
            valid = false;
            return false;
        }

        // Collect variables from GUI inputs
        const variables = {};
        $(this).find('.var-input').each(function() {
            const varName = $(this).data('var-name');
            const varValue = $(this).val();
            if (varValue) {
                variables[varName] = varValue;
            }
        });

        const dependencies = dependenciesText ?
            dependenciesText.split(',').map(d => d.trim()).filter(d => d) : [];

        // Extract pre/post checks if enabled
        const serviceData = {
            name: serviceName,
            template: template,
            devices: devices,
            order: order,
            variables: variables,
            depends_on: dependencies
        };

        const checksEnabled = $(this).find('input[type="checkbox"][id^="enable-checks-"]').is(':checked');
        if (checksEnabled) {
            const preCheckCommand = $(this).find('.pre-check-command').val().trim();
            const preCheckMatch = $(this).find('.pre-check-match').val().trim();
            const postCheckCommand = $(this).find('.post-check-command').val().trim();
            const postCheckMatch = $(this).find('.post-check-match').val().trim();

            if (preCheckCommand && preCheckMatch) {
                serviceData.pre_checks = [{
                    match_type: 'include',
                    get_config_args: {
                        command: preCheckCommand
                    },
                    match_str: preCheckMatch.split(',').map(s => s.trim())
                }];
            }

            if (postCheckCommand && postCheckMatch) {
                serviceData.post_checks = [{
                    match_type: 'include',
                    get_config_args: {
                        command: postCheckCommand
                    },
                    match_str: postCheckMatch.split(',').map(s => s.trim())
                }];
            }
        }

        services.push(serviceData);
    });

    if (!valid || services.length === 0) {
        if (services.length === 0) {
            alert('At least one service is required');
        }
        return;
    }

    // Collect shared variables from key-value inputs
    const sharedVariables = {};
    $('#shared-vars-list .shared-var-item').each(function() {
        const key = $(this).find('.shared-var-key').val().trim();
        const value = $(this).find('.shared-var-value').val().trim();
        if (key && value) {
            sharedVariables[key] = value;
        }
    });

    const stackData = {
        name: name,
        description: $('#stack-description').val().trim(),
        services: services,
        shared_variables: sharedVariables
    };

    const stackId = $('#stack-id').val();
    const url = stackId ? `/api/service-stacks/${stackId}` : '/api/service-stacks';
    const method = stackId ? 'PUT' : 'POST';

    $('#save-stack-btn').prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> Saving...');

    $.ajax({
        url: url,
        method: method,
        contentType: 'application/json',
        data: JSON.stringify(stackData)
    })
    .done(function(data) {
        if (data.success) {
            showStatus('success', {
                message: data.message
            });
            bootstrap.Modal.getInstance(document.getElementById('stackModal')).hide();
            loadServiceStacks();
        } else {
            showStatus('error', {
                message: data.error || 'Failed to save service stack'
            });
        }
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON ? xhr.responseJSON.error : 'Unknown error';
        showStatus('error', {
            message: 'Failed to save service stack: ' + error
        });
    })
    .always(function() {
        $('#save-stack-btn').prop('disabled', false).html('<i class="fas fa-save"></i> Save Stack');
    });
}

/**
 * View stack details
 */
function viewStackDetails(stackId) {
    const modal = new bootstrap.Modal(document.getElementById('stackDetailsModal'));
    const body = $('#stackDetailsBody');
    body.html('<div class="text-center"><div class="spinner-border"></div></div>');

    // Store current stack ID for refresh after service operations
    $('#stackDetailsModal').data('current-stack-id', stackId);

    modal.show();

    $.get('/api/service-stacks/' + encodeURIComponent(stackId))
        .done(function(data) {
            if (data.success && data.stack) {
                renderStackDetails(data.stack);
            } else {
                body.html('<div class="alert alert-danger">Failed to load stack details</div>');
            }
        })
        .fail(function(xhr, status, error) {
            console.error('Failed to load stack details:', status, error);
            body.html('<div class="alert alert-danger">Failed to load stack details</div>');
        });

    // Set up deploy and validate buttons
    $('#deploy-stack-details-btn').off('click').on('click', function() {
        deployStack(stackId);
    });

    $('#validate-stack-details-btn').off('click').on('click', function() {
        validateStack(stackId);
    });
}

/**
 * Render stack details in modal
 */
function renderStackDetails(stack) {
    const stateColors = {
        'pending': 'secondary',
        'deploying': 'warning',
        'deployed': 'success',
        'partial': 'warning',
        'failed': 'danger'
    };

    const stateColor = stateColors[stack.state] || 'secondary';

    // Count deployed service instances (not service definitions)
    const deployedServiceCount = stack.deployed_services ? stack.deployed_services.length : 0;
    const serviceDefinitionCount = stack.services ? stack.services.length : 0;

    let html = `
        <div class="mb-3">
            <h5>
                ${stack.name}
                <span class="badge bg-${stateColor}">${stack.state}</span>
                ${stack.has_pending_changes ? '<span class="badge bg-info ms-1"><i class="fas fa-exclamation-circle"></i> Pending Updates</span>' : ''}
            </h5>
            ${stack.description ? `<p class="text-muted">${stack.description}</p>` : ''}
            ${stack.has_pending_changes ? `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle"></i> This stack has pending changes that require redeployment.
                    ${stack.pending_since ? `<br><small>Changes made: ${formatDate(stack.pending_since)}</small>` : ''}
                </div>
            ` : ''}
        </div>

        <div class="row mb-3">
            <div class="col-md-4">
                <strong>Service Types:</strong> ${serviceDefinitionCount}
            </div>
            <div class="col-md-4">
                <strong>Deployed Instances:</strong> ${deployedServiceCount}
            </div>
            <div class="col-md-4">
                <strong>Created:</strong> ${formatDate(stack.created_at)}
            </div>
        </div>

        ${stack.shared_variables && Object.keys(stack.shared_variables).length > 0 ? `
            <div class="mb-3">
                <h6>Shared Variables</h6>
                <pre class="p-2 rounded border"><code>${JSON.stringify(stack.shared_variables, null, 2)}</code></pre>
            </div>
        ` : ''}
    `;

    // Show validation history
    if (stack.last_validated || stack.validation_status) {
        const validationStatusColors = {
            'success': 'success',
            'passed': 'success',
            'failed': 'danger',
            'partial': 'warning',
            'pending': 'secondary'
        };
        const statusColor = validationStatusColors[stack.validation_status] || 'secondary';

        html += `
            <div class="mb-3">
                <h6><i class="fas fa-check-circle"></i> Validation Status</h6>
                <div class="p-2 border rounded">
                    <div class="row">
                        ${stack.validation_status ? `
                            <div class="col-md-6">
                                <strong>Status:</strong> <span class="badge bg-${statusColor}">${stack.validation_status}</span>
                            </div>
                        ` : ''}
                        ${stack.last_validated ? `
                            <div class="col-md-6">
                                <strong>Last Validated:</strong> ${formatDate(stack.last_validated)}
                            </div>
                        ` : ''}
                    </div>
                </div>
            </div>
        `;
    }

    // Show deployed service instances if available
    if (stack.deployed_services && stack.deployed_services.length > 0) {
        html += `
            <div class="mb-3">
                <h6><i class="fas fa-cogs"></i> Deployed Service Instances</h6>
                <div id="deployed-services-list">
                    <div class="text-center"><div class="spinner-border spinner-border-sm"></div> Loading...</div>
                </div>
            </div>
        `;
    } else {
        html += `
            <div class="mb-3">
                <h6><i class="fas fa-info-circle"></i> No Deployed Services</h6>
                <p class="text-muted">This stack has not been deployed yet. Click "Deploy Stack" to deploy all services.</p>
            </div>
        `;
    }

    // Show deployment errors for failed or partial states
    if ((stack.state === 'failed' || stack.state === 'partial') && stack.deployment_errors && stack.deployment_errors.length > 0) {
        const alertClass = stack.state === 'partial' ? 'alert-warning' : 'alert-danger';
        html += `
            <div class="alert ${alertClass}">
                <h6><i class="fas fa-exclamation-triangle"></i> ${stack.state === 'partial' ? 'Partial Deployment Issues' : 'Deployment Errors'}</h6>
                <ul class="mb-0">
                    ${stack.deployment_errors.map(e => {
                        let errorHtml = `<li><strong>${e.name || 'Unknown'}</strong>: ${e.error}`;

                        // Show device-level details if available
                        if (e.failed_devices && e.failed_devices.length > 0) {
                            errorHtml += '<ul class="mt-1">';
                            e.failed_devices.forEach(fd => {
                                errorHtml += `<li><i class="fas fa-server text-danger"></i> ${fd.device}: ${fd.error}</li>`;
                            });
                            errorHtml += '</ul>';
                        }

                        // Show succeeded devices for partial failures
                        if (e.succeeded_devices && e.succeeded_devices.length > 0) {
                            errorHtml += `<div class="text-muted small mt-1">✓ Succeeded on: ${e.succeeded_devices.join(', ')}</div>`;
                        }

                        // Show skipped devices (no changes)
                        if (e.skipped_devices && e.skipped_devices.length > 0) {
                            errorHtml += `<div class="text-info small mt-1"><i class="fas fa-forward"></i> Skipped (no changes): ${e.skipped_devices.join(', ')}</div>`;
                        }

                        errorHtml += '</li>';
                        return errorHtml;
                    }).join('')}
                </ul>
            </div>
        `;
    }

    $('#stackDetailsBody').html(html);
    $('#stackDetailsTitle').text('Stack: ' + stack.name);

    // Load deployed service instances
    if (stack.deployed_services && stack.deployed_services.length > 0) {
        loadDeployedServices(stack.deployed_services);
    }
}

/**
 * Load and display deployed service instances
 */
function loadDeployedServices(serviceIds) {
    const container = $('#deployed-services-list');

    // Fetch all service instances (with error handling for deleted services)
    Promise.all(serviceIds.map(id =>
        $.get('/api/services/instances/' + encodeURIComponent(id))
            .catch(function(xhr) {
                // Service might have been deleted, return null instead of failing
                console.warn('Service instance not found or error loading:', id);
                return null;
            })
    )).then(function(responses) {
        let html = '<div class="list-group">';
        let serviceCount = 0;

        responses.forEach(function(response) {
            // Skip null responses (deleted or errored services)
            // API returns service in 'instance' field, not 'service' field
            if (response && response.success && response.instance) {
                const service = response.instance;
                serviceCount++;
                const stateColors = {
                    'pending': 'secondary',
                    'deployed': 'success',
                    'failed': 'danger',
                    'validated': 'info'
                };
                const stateColor = stateColors[service.state] || 'secondary';

                const validationBadge = service.validation_status ?
                    (service.validation_status === 'passed' || service.validation_status === 'success' ?
                        `<span class="badge bg-success ms-1" title="Validation Status"><i class="fas fa-check-circle"></i> Validated</span>` :
                     service.validation_status === 'failed' ?
                        `<span class="badge bg-danger ms-1" title="Validation Status"><i class="fas fa-times-circle"></i> Validation Failed</span>` :
                        `<span class="badge bg-warning ms-1" title="Validation Status">${service.validation_status}</span>`
                    ) : '';

                html += `
                    <div class="list-group-item">
                        <div class="d-flex justify-content-between align-items-start">
                            <div class="flex-grow-1">
                                <h6 class="mb-1">
                                    ${service.name}
                                    <span class="badge bg-${stateColor} ms-2">${service.state}</span>
                                    ${validationBadge}
                                </h6>
                                <small class="text-muted">
                                    <i class="fas fa-server"></i> ${service.device} |
                                    <i class="fas fa-file-code"></i> ${service.template}
                                </small>
                                ${service.deployed_at ? `<br><small class="text-muted"><i class="fas fa-rocket"></i> Deployed: ${formatDate(service.deployed_at)}</small>` : ''}
                                ${service.last_validated ? `<br><small class="text-muted"><i class="fas fa-check"></i> Last Validated: ${formatDate(service.last_validated)}</small>` : ''}
                                ${service.state === 'failed' && service.error ? `<br><small class="text-danger"><i class="fas fa-exclamation-triangle"></i> ${service.error}</small>` : ''}
                                ${(() => {
                                    try {
                                        const errors = typeof service.validation_errors === 'string' ? JSON.parse(service.validation_errors) : service.validation_errors;
                                        return errors && Array.isArray(errors) && errors.length > 0 ? `<br><small class="text-danger"><i class="fas fa-exclamation-triangle"></i> Validation Errors: ${errors.length} issue(s)</small>` : '';
                                    } catch (e) {
                                        return service.validation_errors ? `<br><small class="text-danger"><i class="fas fa-exclamation-triangle"></i> Validation Errors</small>` : '';
                                    }
                                })()}
                            </div>
                            <div class="btn-group btn-group-sm">
                                <button class="btn btn-outline-info view-service-btn" data-service-id="${service.service_id}">
                                    <i class="fas fa-eye"></i> Details
                                </button>
                                ${service.state === 'deployed' || service.state === 'validated' ? `
                                    <button class="btn btn-outline-success validate-service-btn" data-service-id="${service.service_id}">
                                        <i class="fas fa-check-circle"></i> Validate
                                    </button>
                                ` : ''}
                                ${service.state === 'failed' ? `
                                    <button class="btn btn-warning redeploy-service-btn" data-service-id="${service.service_id}">
                                        <i class="fas fa-redo"></i> Redeploy
                                    </button>
                                ` : `
                                    <button class="btn btn-outline-warning redeploy-service-btn" data-service-id="${service.service_id}">
                                        <i class="fas fa-redo"></i> Redeploy
                                    </button>
                                `}
                                <button class="btn btn-outline-danger delete-service-btn" data-service-id="${service.service_id}">
                                    <i class="fas fa-trash"></i> Delete
                                </button>
                            </div>
                        </div>
                    </div>
                `;
            }
        });

        html += '</div>';

        if (serviceCount === 0) {
            container.html('<div class="alert alert-info">No service instances found</div>');
        } else {
            container.html(html);
        }

        // Attach event handlers for service actions
        attachServiceActionHandlers();

    }).catch(function(error) {
        console.error('Error loading services:', error);
        const errorMsg = error && error.message ? error.message : 'Unknown error';
        container.html('<div class="alert alert-danger">Failed to load service instances: ' + errorMsg + '</div>');
    });
}

/**
 * Attach event handlers for service instance actions
 */
function attachServiceActionHandlers() {
    $('.view-service-btn').off('click').on('click', function() {
        const serviceId = $(this).data('service-id');
        viewServiceDetails(serviceId);
    });

    $('.validate-service-btn').off('click').on('click', function() {
        const serviceId = $(this).data('service-id');
        validateService(serviceId);
    });

    $('.delete-service-btn').off('click').on('click', function() {
        const serviceId = $(this).data('service-id');
        deleteService(serviceId);
    });

    $('.redeploy-service-btn').off('click').on('click', function() {
        const serviceId = $(this).data('service-id');
        redeployService(serviceId);
    });
}

/**
 * View service instance details
 */
function viewServiceDetails(serviceId) {
    const modal = new bootstrap.Modal(document.getElementById('serviceInstanceModal'));
    const body = $('#serviceInstanceBody');
    body.html('<div class="text-center"><div class="spinner-border"></div></div>');

    modal.show();

    // Fetch service instance details
    $.get('/api/services/instances/' + encodeURIComponent(serviceId))
        .done(function(data) {
            if (data.success && data.instance) {
                renderServiceInstanceDetails(data.instance);

                // Setup action buttons
                $('#validate-service-instance-btn').off('click').on('click', function() {
                    modal.hide();
                    validateService(serviceId);
                });

                $('#delete-service-instance-btn').off('click').on('click', function() {
                    modal.hide();
                    deleteService(serviceId);
                });
            } else {
                body.html('<div class="alert alert-danger">Failed to load service instance details</div>');
            }
        })
        .fail(function(xhr, status, error) {
            console.error('Failed to load service instance:', status, error);
            body.html('<div class="alert alert-danger">Failed to load service instance details</div>');
        });
}

/**
 * Render service instance details in modal
 */
function renderServiceInstanceDetails(service) {
    const stateColors = {
        'pending': 'secondary',
        'deployed': 'success',
        'failed': 'danger',
        'validated': 'info'
    };
    const stateColor = stateColors[service.state] || 'secondary';

    let html = `
        <div class="row mb-4">
            <div class="col-md-12">
                <h5>${service.name} <span class="badge bg-${stateColor}">${service.state}</span></h5>
            </div>
        </div>

        <div class="row mb-3">
            <div class="col-md-6">
                <h6><i class="fas fa-info-circle"></i> Service Information</h6>
                <table class="table table-sm">
                    <tr>
                        <th style="width: 40%;">Service ID:</th>
                        <td><code>${service.service_id}</code></td>
                    </tr>
                    <tr>
                        <th>Device:</th>
                        <td>${service.device}</td>
                    </tr>
                    <tr>
                        <th>Template:</th>
                        <td><code>${service.template}</code></td>
                    </tr>
                    ${service.validation_template ? `
                    <tr>
                        <th>Validation Template:</th>
                        <td><code>${service.validation_template}</code></td>
                    </tr>
                    ` : ''}
                    ${service.delete_template ? `
                    <tr>
                        <th>Delete Template:</th>
                        <td><code>${service.delete_template}</code></td>
                    </tr>
                    ` : ''}
                    <tr>
                        <th>State:</th>
                        <td><span class="badge bg-${stateColor}">${service.state}</span></td>
                    </tr>
                    ${service.state === 'failed' && service.error ? `
                    <tr>
                        <th>Error:</th>
                        <td><span class="text-danger"><i class="fas fa-exclamation-triangle"></i> ${service.error}</span></td>
                    </tr>
                    ` : ''}
                    ${service.validation_status ? `
                    <tr>
                        <th>Validation Status:</th>
                        <td>${service.validation_status === 'valid' ? '<span class="badge bg-success">Valid</span>' : '<span class="badge bg-warning">Invalid</span>'}</td>
                    </tr>
                    ` : ''}
                </table>
            </div>

            <div class="col-md-6">
                <h6><i class="fas fa-clock"></i> Timestamps</h6>
                <table class="table table-sm">
                    <tr>
                        <th style="width: 40%;">Created:</th>
                        <td>${formatDate(service.created_at)}</td>
                    </tr>
                    ${service.deployed_at ? `
                    <tr>
                        <th>Deployed:</th>
                        <td>${formatDate(service.deployed_at)}</td>
                    </tr>
                    ` : ''}
                    ${service.last_validated ? `
                    <tr>
                        <th>Last Validated:</th>
                        <td>${formatDate(service.last_validated)}</td>
                    </tr>
                    ` : ''}
                    ${service.updated_at ? `
                    <tr>
                        <th>Updated:</th>
                        <td>${formatDate(service.updated_at)}</td>
                    </tr>
                    ` : ''}
                </table>

                ${service.task_id ? `
                <h6 class="mt-3"><i class="fas fa-tasks"></i> Task Information</h6>
                <table class="table table-sm">
                    <tr>
                        <th style="width: 40%;">Task ID:</th>
                        <td><code>${service.task_id}</code></td>
                    </tr>
                </table>
                ` : ''}
            </div>
        </div>

        ${service.variables && Object.keys(service.variables).length > 0 ? `
        <div class="mb-3">
            <h6><i class="fas fa-code"></i> Template Variables</h6>
            <pre class="p-3 rounded border"><code>${JSON.stringify(service.variables, null, 2)}</code></pre>
        </div>
        ` : ''}

        ${service.rendered_config ? `
        <div class="mb-3">
            <h6><i class="fas fa-file-code"></i> Rendered Configuration</h6>
            <pre class="p-3 rounded border" style="max-height: 300px; overflow-y: auto;"><code>${service.rendered_config}</code></pre>
        </div>
        ` : ''}

        ${service.stack_id ? `
        <div class="mb-3">
            <h6><i class="fas fa-layer-group"></i> Stack Information</h6>
            <p class="mb-1"><strong>Stack ID:</strong> <code>${service.stack_id}</code></p>
            ${service.stack_order ? `<p class="mb-1"><strong>Order in Stack:</strong> ${service.stack_order}</p>` : ''}
        </div>
        ` : ''}
    `;

    $('#serviceInstanceBody').html(html);
    $('#serviceInstanceTitle').text('Service: ' + service.name);
}

/**
 * Validate a service instance
 */
function validateService(serviceId) {
    showStatus('info', { message: 'Validating service...' });

    // Get credentials from settings
    let username, password;
    try {
        const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
        username = settings.default_username;
        password = settings.default_password;
    } catch (e) {
        console.error('Error reading credentials:', e);
    }

    $.ajax({
        url: '/api/services/instances/' + encodeURIComponent(serviceId) + '/validate',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ username, password }),
        timeout: 60000
    })
    .done(function(data) {
        if (data.success) {
            if (data.valid) {
                showStatus('success', {
                    message: '✓ Service validation passed',
                    details: data.message
                });
            } else {
                showStatus('warning', {
                    message: '⚠ Service validation failed - configuration drift detected',
                    details: data.message + (data.missing_lines ? '<br>Missing: ' + data.missing_lines.join(', ') : '')
                });
            }
        } else {
            showStatus('error', {
                message: 'Validation failed: ' + (data.error || 'Unknown error')
            });
        }
    })
    .fail(function(xhr) {
        showStatus('error', {
            message: 'Validation failed: ' + (xhr.responseJSON ? xhr.responseJSON.error : 'Unknown error')
        });
    });
}

/**
 * Redeploy a service instance
 */
function redeployService(serviceId) {
    showStatus('info', { message: 'Redeploying service...' });

    // Get credentials from settings
    let username, password;
    try {
        const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
        username = settings.default_username;
        password = settings.default_password;
    } catch (e) {
        console.error('Error reading credentials:', e);
    }

    $.ajax({
        url: '/api/services/instances/' + encodeURIComponent(serviceId) + '/redeploy',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ username, password }),
        timeout: 120000  // 2 minutes for redeploy
    })
    .done(function(data) {
        if (data.success) {
            showStatus('success', {
                message: '✓ Service redeployed successfully',
                details: data.message
            });
            // Refresh the current stack view
            const stackId = $('#stackDetailsModal').data('current-stack-id');
            if (stackId) {
                setTimeout(() => viewStackDetails(stackId), 1500);
            }
        } else {
            showStatus('error', {
                message: 'Redeploy failed: ' + (data.error || 'Unknown error')
            });
        }
    })
    .fail(function(xhr) {
        showStatus('error', {
            message: 'Redeploy failed: ' + (xhr.responseJSON ? xhr.responseJSON.error : 'Unknown error')
        });
    });
}

/**
 * Delete a service instance
 */
function deleteService(serviceId) {
    if (!confirm('Delete this service instance? This will remove the configuration from the device.')) {
        return;
    }

    showStatus('info', { message: 'Deleting service...' });

    // Get credentials from settings
    let username, password;
    try {
        const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
        username = settings.default_username;
        password = settings.default_password;
    } catch (e) {
        console.error('Error reading credentials:', e);
    }

    $.ajax({
        url: '/api/services/instances/' + encodeURIComponent(serviceId) + '/delete',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ username, password }),
        timeout: 60000
    })
    .done(function(data) {
        if (data.success) {
            showStatus('success', {
                message: '✓ Service deleted successfully',
                details: data.message
            });
            // Refresh the current stack view and the stacks list
            const stackId = $('#stackDetailsModal').data('current-stack-id');
            if (stackId) {
                setTimeout(() => {
                    viewStackDetails(stackId);
                    loadServiceStacks(); // Refresh the main stacks list
                }, 1500);
            }
        } else {
            showStatus('error', {
                message: 'Delete failed: ' + (data.error || 'Unknown error')
            });
        }
    })
    .fail(function(xhr) {
        showStatus('error', {
            message: 'Delete failed: ' + (xhr.responseJSON ? xhr.responseJSON.error : 'Unknown error')
        });
    });
}

/**
 * Deploy a service stack
 */
function deployStack(stackId) {
    // Get credentials from settings
    let username, password;
    try {
        const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
        username = settings.default_username;
        password = settings.default_password;
        console.log('Credentials from settings:', { username, hasPassword: !!password });
    } catch (e) {
        console.error('Error reading credentials from settings:', e);
    }

    showStatus('info', {
        message: 'Deploying service stack...',
        details: 'This may take several minutes depending on the number of services.'
    });

    $.ajax({
        url: '/api/service-stacks/' + encodeURIComponent(stackId) + '/deploy',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            username: username,
            password: password
        }),
        timeout: 300000 // 5 minute timeout
    })
    .done(function(data) {
        if (data.success) {
            showStatus('success', {
                message: `✓ Stack deployed successfully - ${data.deployed_count} service(s) deployed`,
                details: data.deployed_services.length > 0 ?
                    '<strong>Deployed services:</strong><br><ul class="mb-0">' +
                    data.deployed_services.map(id => '<li><code>' + id + '</code></li>').join('') +
                    '</ul>' : ''
            });

            // Redirect to job monitor after 3 seconds
            setTimeout(function() {
                window.location.href = '/monitor';
            }, 3000);
        } else {
            const failedDetails = data.failed_services && data.failed_services.length > 0 ?
                '<strong>Failed services:</strong><br><ul class="mb-0">' +
                data.failed_services.map(f => '<li>' + f.name + ': ' + f.error + '</li>').join('') +
                '</ul>' : '';

            showStatus('error', {
                message: `⚠ Stack deployment failed - ${data.deployed_count} deployed, ${data.failed_count} failed`,
                details: failedDetails
            });
        }

        loadServiceStacks();
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON ? xhr.responseJSON.error : 'Unknown error';
        showStatus('error', {
            message: 'Stack deployment failed: ' + error
        });
    });
}

/**
 * Validate a service stack
 */
/**
 * Delete a service stack
 */
function deleteStack(stackId) {
    // Show the delete confirmation modal
    const modal = new bootstrap.Modal(document.getElementById('deleteStackModal'));
    modal.show();

    // Store the stack ID for the confirm button
    $('#confirm-delete-stack-btn').data('stack-id', stackId);

    // Remove any existing click handlers and add new one
    $('#confirm-delete-stack-btn').off('click').on('click', function() {
        const runDeleteTemplates = $('input[name="deleteOption"]:checked').val() === 'cleanup';

        // Hide the modal
        modal.hide();

        // Show status
        showStatus('info', {
            message: runDeleteTemplates ?
                'Deleting stack and running delete templates...' :
                'Deleting stack (keeping device configurations)...'
        });

        // Get credentials from settings if running delete templates
        let username, password;
        if (runDeleteTemplates) {
            try {
                const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
                username = settings.default_username;
                password = settings.default_password;
                console.log('Delete stack - using credentials from settings:', { username, hasPassword: !!password });
            } catch (e) {
                console.error('Error reading credentials from settings:', e);
            }
        }

        // Execute the deletion
        $.ajax({
            url: '/api/service-stacks/' + encodeURIComponent(stackId) +
                 (runDeleteTemplates ? '?delete_services=true' : ''),
            method: 'DELETE',
            contentType: 'application/json',
            data: runDeleteTemplates ? JSON.stringify({
                username: username,
                password: password
            }) : undefined,
            timeout: runDeleteTemplates ? 180000 : 30000  // 3 min if running delete templates, 30 sec otherwise
        })
        .done(function(data) {
            if (data.success) {
                showStatus('success', {
                    message: data.message + (runDeleteTemplates ? ' Device configurations have been removed.' : ' Device configurations remain.')
                });
                loadServiceStacks();
            } else {
                showStatus('error', {
                    message: data.error || 'Failed to delete service stack'
                });
            }
        })
        .fail(function(xhr) {
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'Unknown error';
            showStatus('error', {
                message: 'Failed to delete service stack: ' + error
            });
        });
    });
}

/**
 * Show status modal (reused from services.js)
 */
function showStatus(type, data) {
    const modal = new bootstrap.Modal(document.getElementById('statusModal'));

    const titles = {
        'success': 'Success',
        'error': 'Error',
        'warning': 'Warning',
        'info': 'Information'
    };
    $('#statusModalTitle').text(titles[type] || 'Status');

    const alertClasses = {
        'success': 'alert-success',
        'error': 'alert-danger',
        'warning': 'alert-warning',
        'info': 'alert-info'
    };

    const icons = {
        'success': 'fa-check-circle',
        'error': 'fa-exclamation-triangle',
        'warning': 'fa-exclamation-circle',
        'info': 'fa-info-circle'
    };

    let html = `
        <div class="alert ${alertClasses[type] || 'alert-info'}">
            <h5><i class="fas ${icons[type] || 'fa-info-circle'}"></i> ${data.message || 'Status'}</h5>
            ${data.details ? `<hr><div>${data.details}</div>` : ''}
            ${data.task_id ? `<hr><small><strong>Task ID:</strong> <code>${data.task_id}</code></small>` : ''}
        </div>
    `;

    $('#statusModalBody').html(html);
    modal.show();

    // Cleanup backdrop on close
    const modalElement = document.getElementById('statusModal');
    modalElement.addEventListener('hidden.bs.modal', function () {
        const backdrops = document.querySelectorAll('.modal-backdrop');
        backdrops.forEach(backdrop => backdrop.remove());
        document.body.classList.remove('modal-open');
        document.body.style.overflow = '';
        document.body.style.paddingRight = '';
    });
}

/**
 * Load stack templates from API
 */
function loadStackTemplates() {
    $.get('/api/stack-templates')
        .done(function(data) {
            if (data.success) {
                displayStackTemplates(data.templates);
            }
        })
        .fail(function(xhr) {
            $('#stack-templates-container').html(`
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle"></i> Failed to load stack templates: ${xhr.responseJSON?.error || 'Unknown error'}
                </div>
            `);
        });
}

/**
 * Display stack templates
 */
function displayStackTemplates(templates) {
    const container = $('#stack-templates-container');

    if (!templates || templates.length === 0) {
        container.html(`
            <div class="text-center text-muted">
                <i class="fas fa-folder-open fa-2x mb-2"></i>
                <p>No stack templates created yet. Click "New Template" to create one.</p>
            </div>
        `);
        return;
    }

    let html = '<div class="row">';
    templates.forEach(template => {
        const serviceCount = template.services?.length || 0;
        const variableCount = template.required_variables?.length || 0;

        html += `
            <div class="col-md-3 mb-2">
                <div class="card shadow-sm" style="max-height: 180px;">
                    <div class="card-body p-2">
                        <h6 class="card-title mb-1 small">
                            <i class="fas fa-file-alt text-success"></i> ${escapeHtml(template.name)}
                        </h6>
                        <p class="card-text" style="font-size: 0.75rem; color: #6c757d; margin-bottom: 0.5rem; max-height: 2.4em; overflow: hidden;">${escapeHtml(template.description || 'No description')}</p>
                        <div style="font-size: 0.7rem;">
                            <span class="badge bg-info" style="font-size: 0.65rem;">${serviceCount} Svc</span>
                            <span class="badge bg-secondary" style="font-size: 0.65rem;">${variableCount} Var</span>
                        </div>
                    </div>
                    <div class="card-footer bg-transparent p-1">
                        <div class="btn-group w-100">
                            <button class="btn btn-sm btn-primary deploy-from-template-btn" data-template-id="${template.template_id}" style="font-size: 0.7rem; padding: 0.2rem 0.3rem;">
                                <i class="fas fa-plus-circle"></i> Create
                            </button>
                            <button class="btn btn-sm btn-outline-secondary edit-template-btn" data-template-id="${template.template_id}" style="font-size: 0.7rem; padding: 0.2rem 0.3rem;">
                                <i class="fas fa-edit"></i> Edit
                            </button>
                            <button class="btn btn-sm btn-outline-danger delete-template-btn" data-template-id="${template.template_id}" style="font-size: 0.7rem; padding: 0.2rem 0.3rem;">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    });
    html += '</div>';

    container.html(html);

    // Attach event handlers
    $('.deploy-from-template-btn').click(function() {
        const templateId = $(this).data('template-id');
        openDeployFromTemplateModal(templateId);
    });

    $('.edit-template-btn').click(function() {
        const templateId = $(this).data('template-id');
        editStackTemplate(templateId);
    });

    $('.delete-template-btn').click(function() {
        const templateId = $(this).data('template-id');
        deleteStackTemplate(templateId);
    });
}

/**
 * Open stack template modal
 */
function openStackTemplateModal(templateId = null) {
    $('#stack-template-id').val(templateId || '');
    $('#stack-template-name').val('');
    $('#stack-template-description').val('');
    $('#template-services-container').html('<p class="text-muted">No services added yet. Click "Add Service" to define services for this template.</p>');

    // Clear API variable configs, per-device variables, and hide detected variables card
    apiVariableConfigs = {};
    perDeviceVariables = [];
    $('#detected-variables-card').hide();
    $('#detected-variables-container').empty();

    $('#stackTemplateModalTitle').text(templateId ? 'Edit Stack Template' : 'Create Stack Template');

    const modal = new bootstrap.Modal(document.getElementById('stackTemplateModal'));
    modal.show();
}

/**
 * Add service to template
 */
function addServiceToTemplate() {
    serviceCounter++;
    const serviceId = `template-service-${serviceCounter}`;

    const container = $('#template-services-container');

    // Remove "no services" message if present
    if (container.find('p.text-muted').length) {
        container.empty();
    }

    const serviceHtml = `
        <div class="card mb-2" id="${serviceId}">
            <div class="card-body">
                <div class="row">
                    <div class="col-md-4">
                        <label class="form-label small">Service Name *</label>
                        <input type="text" class="form-control form-control-sm service-name" placeholder="e.g., PE Router Config" required>
                    </div>
                    <div class="col-md-4">
                        <label class="form-label small">Config Template *</label>
                        <select class="form-select form-control-sm service-template" required>
                            <option value="">Select template...</option>
                            ${allTemplates.filter(t => t.delete_template).map(t => `<option value="${t.name}">${t.name}</option>`).join('')}
                        </select>
                    </div>
                    <div class="col-md-3">
                        <label class="form-label small">Order</label>
                        <input type="number" class="form-control form-control-sm service-order" value="${serviceCounter}" min="1">
                    </div>
                    <div class="col-md-1">
                        <label class="form-label small">&nbsp;</label>
                        <button type="button" class="btn btn-sm btn-danger w-100 remove-service-btn">
                            <i class="fas fa-times"></i>
                        </button>
                    </div>
                </div>

                <div class="row mt-2">
                    <div class="col-12">
                        <div class="form-check">
                            <input class="form-check-input enable-checks-checkbox" type="checkbox" id="enable-checks-${serviceId}">
                            <label class="form-check-label small" for="enable-checks-${serviceId}">
                                Enable Pre/Post Deployment Checks
                            </label>
                        </div>
                    </div>
                </div>

                <div class="checks-container" style="display: none;">
                    <div class="row mt-2">
                        <div class="col-md-6">
                            <label class="form-label small">Pre-Check Command</label>
                            <input type="text" class="form-control form-control-sm pre-check-command" placeholder="show run | i hostname">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label small">Pre-Check Expected Output</label>
                            <input type="text" class="form-control form-control-sm pre-check-match" placeholder="hostname cat">
                        </div>
                    </div>
                    <div class="row mt-2">
                        <div class="col-md-6">
                            <label class="form-label small">Post-Check Command</label>
                            <input type="text" class="form-control form-control-sm post-check-command" placeholder="show run | i hostname">
                        </div>
                        <div class="col-md-6">
                            <label class="form-label small">Post-Check Expected Output</label>
                            <input type="text" class="form-control form-control-sm post-check-match" placeholder="hostname dog">
                        </div>
                    </div>
                </div>
            </div>
        </div>
    `;

    container.append(serviceHtml);

    // Attach remove handler
    $(`#${serviceId} .remove-service-btn`).click(function() {
        $(`#${serviceId}`).remove();
        if ($('#template-services-container .card').length === 0) {
            $('#template-services-container').html('<p class="text-muted">No services added yet. Click "Add Service" to define services for this template.</p>');
        }
    });

    // Attach enable checks toggle handler
    $(`#${serviceId} .enable-checks-checkbox`).change(function() {
        const $checks = $(this).closest('.card-body').find('.checks-container');
        if ($(this).is(':checked')) {
            $checks.show();
        } else {
            $checks.hide();
        }
    });
}

/**
 * Save stack template
 */
function saveStackTemplate() {
    console.log('saveStackTemplate function called');

    const templateId = $('#stack-template-id').val();
    const name = $('#stack-template-name').val().trim();
    const description = $('#stack-template-description').val().trim();

    console.log('Template data:', { templateId, name, description });

    if (!name) {
        alert('Please enter a template name');
        return;
    }

    // Collect services
    const services = [];
    $('#template-services-container .card').each(function() {
        const serviceName = $(this).find('.service-name').val().trim();
        const template = $(this).find('.service-template').val();
        const order = parseInt($(this).find('.service-order').val()) || 0;

        if (serviceName && template) {
            const serviceData = {
                name: serviceName,
                template: template,
                order: order
            };

            // Extract pre/post checks if enabled
            const checksEnabled = $(this).find('.enable-checks-checkbox').is(':checked');
            if (checksEnabled) {
                const preCheckCommand = $(this).find('.pre-check-command').val().trim();
                const preCheckMatch = $(this).find('.pre-check-match').val().trim();
                const postCheckCommand = $(this).find('.post-check-command').val().trim();
                const postCheckMatch = $(this).find('.post-check-match').val().trim();

                if (preCheckCommand && preCheckMatch) {
                    serviceData.pre_checks = [{
                        match_type: 'include',
                        get_config_args: {
                            command: preCheckCommand
                        },
                        match_str: preCheckMatch.split(',').map(s => s.trim())
                    }];
                }

                if (postCheckCommand && postCheckMatch) {
                    serviceData.post_checks = [{
                        match_type: 'include',
                        get_config_args: {
                            command: postCheckCommand
                        },
                        match_str: postCheckMatch.split(',').map(s => s.trim())
                    }];
                }
            }

            services.push(serviceData);
        }
    });

    console.log('Collected services:', services);

    if (services.length === 0) {
        alert('Please add at least one service to the template');
        return;
    }

    // Use the API variables configured via the popup modals
    console.log('API variables:', apiVariableConfigs);
    console.log('Per-device variables:', perDeviceVariables);

    const payload = {
        name: name,
        description: description,
        services: services,
        api_variables: apiVariableConfigs,
        per_device_variables: perDeviceVariables
    };

    // Include template_id if editing existing template
    if (templateId) {
        payload.template_id = templateId;
    }

    console.log('Sending payload to API:', payload);

    $.ajax({
        url: '/api/stack-templates',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(payload)
    })
    .done(function(data) {
        console.log('API response:', data);
        if (data.success) {
            // Show success message (using alert for now since showToast doesn't exist)
            const message = templateId ? 'Stack template updated successfully' : 'Stack template created successfully';
            console.log(message);

            // Close modal with proper cleanup
            const modalElement = document.getElementById('stackTemplateModal');
            const modalInstance = bootstrap.Modal.getInstance(modalElement);

            // Add one-time event listener for cleanup
            modalElement.addEventListener('hidden.bs.modal', function cleanupBackdrop() {
                // Remove any lingering backdrops
                const backdrops = document.querySelectorAll('.modal-backdrop');
                backdrops.forEach(backdrop => backdrop.remove());
                document.body.classList.remove('modal-open');
                document.body.style.overflow = '';
                document.body.style.paddingRight = '';

                // Refresh templates list
                loadStackTemplates();

                // Remove this event listener
                modalElement.removeEventListener('hidden.bs.modal', cleanupBackdrop);
            }, { once: true });

            // Hide the modal
            if (modalInstance) {
                modalInstance.hide();
            } else {
                $(modalElement).modal('hide');
            }
        }
    })
    .fail(function(xhr) {
        console.error('API error:', xhr);
        alert('Failed to save stack template: ' + (xhr.responseJSON?.error || 'Unknown error'));
    });
}

/**
 * Open deploy from template modal
 */
function openDeployFromTemplateModal(templateId) {
    $.get(`/api/stack-templates/${templateId}`)
        .done(function(data) {
            if (data.success) {
                const template = data.template;

                $('#deploy-template-id').val(templateId);
                $('#deploy-stack-name').val('');
                $('#deploy-stack-description').val('');

                // Display required variables with API variable support
                const varsContainer = $('#deploy-variables-container');
                const apiVariables = template.api_variables || {};
                const hasApiVars = Object.keys(apiVariables).length > 0;

                // Separate variables into shared and per-device based on template configuration
                const sharedVars = [];
                const perDeviceVars = [];
                const perDeviceVarList = template.per_device_variables || [];

                if (template.required_variables && template.required_variables.length > 0) {
                    template.required_variables.forEach(varName => {
                        // Check if variable is marked as per-device in template
                        if (perDeviceVarList.includes(varName)) {
                            perDeviceVars.push(varName);
                        } else {
                            sharedVars.push(varName);
                        }
                    });
                }

                // Display shared variables with API fetch support
                if (sharedVars.length > 0) {
                    let varsHtml = '<div class="row">';
                    sharedVars.forEach(varName => {
                        const hasApi = apiVariables.hasOwnProperty(varName);
                        varsHtml += `
                            <div class="col-md-6 mb-3">
                                <label class="form-label small d-flex justify-content-between align-items-center">
                                    <span>${varName}</span>
                                    ${hasApi ? '<i class="fas fa-cloud-download-alt text-success ms-1" title="API fetch available"></i>' : ''}
                                </label>
                                <div class="input-group input-group-sm">
                                    <input type="text" class="form-control template-variable-shared"
                                           data-var-name="${varName}"
                                           placeholder="Enter ${varName}"
                                           ${hasApi ? 'data-api-var="true"' : ''}>
                                    ${hasApi ? `<button class="btn btn-outline-primary fetch-shared-api-var-btn" type="button"
                                                       data-var-name="${varName}"
                                                       title="Fetch from API">
                                                   <i class="fas fa-sync-alt"></i>
                                               </button>` : ''}
                                </div>
                                <div class="api-fetch-status-shared" data-var-name="${varName}" style="display:none; font-size: 0.75rem; margin-top: 0.25rem;"></div>
                            </div>
                        `;
                    });
                    varsHtml += '</div>';
                    varsContainer.html(varsHtml);

                    // Attach event handlers for API fetch buttons on shared variables
                    $('.fetch-shared-api-var-btn').off('click').on('click', function() {
                        const varName = $(this).data('var-name');
                        const apiConfig = apiVariables[varName];
                        fetchApiVariableShared(varName, apiConfig);
                    });
                } else if (perDeviceVars.length > 0) {
                    varsContainer.html('<p class="text-muted small"><i class="fas fa-info-circle"></i> All variables are device-specific and will appear next to each device below.</p>');
                } else {
                    varsContainer.html('<p class="text-muted small">No variables required</p>');
                }

                // Display services with device selection (compact layout)
                const servicesContainer = $('#deploy-services-preview');
                let servicesHtml = '';
                template.services.forEach((service, index) => {
                    servicesHtml += `
                        <div class="border rounded p-2 mb-2" data-service-index="${index}">
                            <div class="d-flex justify-content-between align-items-center mb-2">
                                <div>
                                    <strong class="text-primary">${escapeHtml(service.name)}</strong>
                                    <small class="text-muted ms-2"><i class="fas fa-file-code"></i> ${escapeHtml(service.template)}</small>
                                </div>
                                <button type="button" class="btn btn-sm btn-outline-primary add-deploy-device-btn" data-service-index="${index}">
                                    <i class="fas fa-plus"></i> Add Device
                                </button>
                            </div>
                            <div class="deploy-devices-list" data-service-index="${index}">
                                <!-- Device dropdowns will be added here -->
                            </div>
                        </div>
                    `;
                });
                servicesContainer.html(servicesHtml);

                // Store template data for per-device variable handling
                $('#deployFromTemplateModal').data('template-api-vars', template.api_variables || {});
                $('#deployFromTemplateModal').data('template-per-device-vars', perDeviceVars);
                $('#deployFromTemplateModal').data('template-required-vars', template.required_variables || []);

                // Initialize each service with one device dropdown
                template.services.forEach((service, index) => {
                    addDeployDeviceDropdown(index, null);
                });

                // Attach add device button handlers
                $('.add-deploy-device-btn').click(function() {
                    const serviceIndex = $(this).data('service-index');
                    addDeployDeviceDropdown(serviceIndex, null);
                });

                const modal = new bootstrap.Modal(document.getElementById('deployFromTemplateModal'));
                modal.show();

                // Attach deploy handler
                $('#confirm-deploy-from-template-btn').off('click').on('click', function() {
                    deployFromTemplate(template);
                });
            }
        })
        .fail(function(xhr) {
            alert('Failed to load template: ' + (xhr.responseJSON?.error || 'Unknown error'));
        });
}

/**
 * Add device dropdown to deploy from template service
 */
function addDeployDeviceDropdown(serviceIndex, selectedDevice) {
    const $devicesList = $(`.deploy-devices-list[data-service-index="${serviceIndex}"]`);
    const deviceCount = $devicesList.find('.deploy-device-dropdown-item').length;
    const deviceInstanceId = `device-${serviceIndex}-${deviceCount}-${Date.now()}`;

    // Get per-device variables and API configs
    const perDeviceVars = $('#deployFromTemplateModal').data('template-per-device-vars') || [];
    const apiVariables = $('#deployFromTemplateModal').data('template-api-vars') || {};

    // Build per-device variable inputs as inline columns
    let variablesColumnsHtml = '';
    if (perDeviceVars.length > 0) {
        perDeviceVars.forEach(varName => {
            const hasApi = apiVariables.hasOwnProperty(varName);
            const apiConfig = apiVariables[varName];
            const description = hasApi && apiConfig.description ? apiConfig.description : '';

            variablesColumnsHtml += `
                <div class="flex-fill" style="min-width: 150px;">
                    <label class="form-label small mb-1">
                        ${varName}
                        ${hasApi ? '<i class="fas fa-cloud-download-alt text-success ms-1" title="API fetch available"></i>' : ''}
                    </label>
                    <div class="input-group input-group-sm">
                        <input type="text" class="form-control template-variable-per-device"
                               data-var-name="${varName}"
                               data-device-instance="${deviceInstanceId}"
                               placeholder="${varName}"
                               ${hasApi ? 'data-api-var="true"' : ''}>
                        ${hasApi ? `<button class="btn btn-outline-primary fetch-api-var-btn" type="button"
                                           data-var-name="${varName}"
                                           data-device-instance="${deviceInstanceId}"
                                           title="Fetch from API">
                                       <i class="fas fa-sync-alt"></i>
                                   </button>` : ''}
                    </div>
                    <div class="api-fetch-status" data-var-name="${varName}" data-device-instance="${deviceInstanceId}" style="display:none; font-size: 0.65rem; margin-top: 0.25rem;"></div>
                </div>
            `;
        });
    }

    const deviceHtml = `
        <div class="deploy-device-dropdown-item mb-2 p-2 border rounded" data-device-instance="${deviceInstanceId}">
            <div class="d-flex gap-2 align-items-start flex-wrap">
                <div style="min-width: 200px; flex: 1 1 200px;">
                    <label class="form-label small mb-1">Device</label>
                    <select class="form-select form-select-sm deploy-service-device-select"
                            data-service-index="${serviceIndex}"
                            data-device-instance="${deviceInstanceId}" required>
                        <option value="">Select device...</option>
                        ${allDevices.map(d => `<option value="${d.name}" ${selectedDevice === d.name ? 'selected' : ''}>${d.display || d.name}</option>`).join('')}
                    </select>
                </div>
                ${variablesColumnsHtml}
                ${deviceCount > 0 ? '<div class="d-flex align-items-end"><button type="button" class="btn btn-sm btn-danger remove-deploy-device-btn" style="height: 31px;"><i class="fas fa-times"></i></button></div>' : ''}
            </div>
        </div>
    `;

    $devicesList.append(deviceHtml);

    // Attach change handler to auto-fetch API variables when device is selected
    $devicesList.find('.deploy-service-device-select').last().change(function() {
        const selectedDevice = $(this).val();
        const instanceId = $(this).data('device-instance');

        if (selectedDevice) {
            console.log('Device selected:', selectedDevice, '- Auto-fetching API variables for instance:', instanceId);

            // Get stored API variable configs
            const apiVariables = $('#deployFromTemplateModal').data('template-api-vars') || {};

            // Find all API variables for this specific device instance and fetch them
            $(`.fetch-api-var-btn[data-device-instance="${instanceId}"]`).each(function() {
                const $btn = $(this);
                const varName = $btn.data('var-name');
                const apiConfig = apiVariables[varName];

                if (apiConfig) {
                    // Trigger the fetch for this specific device instance
                    fetchApiVariablePerDevice(varName, apiConfig, instanceId, selectedDevice);
                }
            });
        }
    });

    // Attach manual fetch button handlers for per-device variables
    $devicesList.find('.fetch-api-var-btn').last().off('click').on('click', function() {
        const $btn = $(this);
        const varName = $btn.data('var-name');
        const instanceId = $btn.data('device-instance');
        const apiVariables = $('#deployFromTemplateModal').data('template-api-vars') || {};
        const apiConfig = apiVariables[varName];

        // Get the device name from the select for this instance
        const $deviceSelect = $(`.deploy-service-device-select[data-device-instance="${instanceId}"]`);
        const deviceName = $deviceSelect.val();

        if (!deviceName) {
            alert('Please select a device first before fetching API variables');
            return;
        }

        if (apiConfig) {
            fetchApiVariablePerDevice(varName, apiConfig, instanceId, deviceName);
        }
    });

    // Attach remove handler (only for additional devices, not the first one)
    if (deviceCount > 0) {
        $devicesList.find('.deploy-device-dropdown-item').last().find('.remove-deploy-device-btn').click(function() {
            $(this).closest('.deploy-device-dropdown-item').remove();
        });
    }
}

/**
 * Deploy stack from template
 */
function deployFromTemplate(template) {
    const stackName = $('#deploy-stack-name').val().trim();
    const description = $('#deploy-stack-description').val().trim();

    if (!stackName) {
        alert('Please enter a stack name');
        return;
    }

    // Collect shared variable values (non-API variables from top section)
    const sharedVariables = {};
    $('.template-variable-shared').each(function() {
        const varName = $(this).data('var-name');
        const value = $(this).val().trim();
        if (value) {
            sharedVariables[varName] = value;
        }
    });

    // Collect device selections and per-device variables for each service
    const services = [];
    const deviceInstances = {};

    // Build a map of device instances with their variables
    $('.deploy-device-dropdown-item').each(function() {
        const $item = $(this);
        const deviceInstanceId = $item.data('device-instance');
        const $select = $item.find('.deploy-service-device-select');
        const serviceIndex = $select.data('service-index');
        const deviceName = $select.val();

        if (!deviceName) {
            return; // Skip empty selections
        }

        // Collect per-device variables for this device instance
        const deviceVariables = {};
        $item.find('.template-variable-per-device').each(function() {
            const varName = $(this).data('var-name');
            const value = $(this).val().trim();
            if (value) {
                deviceVariables[varName] = value;
            }
        });

        console.log(`Device ${deviceName} variables:`, deviceVariables);

        if (!deviceInstances[serviceIndex]) {
            deviceInstances[serviceIndex] = [];
        }

        deviceInstances[serviceIndex].push({
            deviceName: deviceName,
            variables: deviceVariables
        });
    });

    // Validate and create service instances with per-device variables
    for (let i = 0; i < template.services.length; i++) {
        const templateService = template.services[i];
        const instances = deviceInstances[i] || [];

        if (instances.length === 0) {
            alert(`Please select at least one device for service: ${templateService.name}`);
            return;
        }

        // Create one service instance per device with its specific variables
        instances.forEach(instance => {
            services.push({
                name: templateService.name,
                template: templateService.template,
                device: instance.deviceName,
                order: templateService.order || 0,
                variables: instance.variables  // Per-device variables stored here!
            });
        });
    }

    if (services.length === 0) {
        alert('Please select at least one device for each service');
        return;
    }

    // Create stack with expanded services
    const stackData = {
        name: stackName,
        description: description,
        services: services,
        shared_variables: sharedVariables
    };

    console.log('=== Deploying Stack from Template ===');
    console.log('Shared variables:', sharedVariables);
    console.log('Services with per-device variables:', services);

    $.ajax({
        url: '/api/service-stacks',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(stackData)
    })
    .done(function(data) {
        if (data.success) {
            console.log('Stack created from template successfully');
            const modalElement = document.getElementById('deployFromTemplateModal');
            const modalInstance = bootstrap.Modal.getInstance(modalElement);
            if (modalInstance) {
                modalInstance.hide();
            }
            setTimeout(function() {
                loadServiceStacks();
            }, 300);
        }
    })
    .fail(function(xhr) {
        alert('Failed to create stack: ' + (xhr.responseJSON?.error || 'Unknown error'));
    });
}

/**
 * Edit stack template
 */
function editStackTemplate(templateId) {
    $.get(`/api/stack-templates/${templateId}`)
        .done(function(data) {
            if (data.success) {
                const template = data.template;

                // Populate the template modal for editing
                $('#stack-template-id').val(template.template_id);
                $('#stack-template-name').val(template.name);
                $('#stack-template-description').val(template.description || '');

                // Load API variable configurations and per-device variables
                apiVariableConfigs = template.api_variables || {};
                perDeviceVariables = template.per_device_variables || [];
                console.log('Loaded API variable configs:', apiVariableConfigs);
                console.log('Loaded per-device variables:', perDeviceVariables);

                // Clear and populate services
                $('#template-services-container').empty();

                if (template.services && template.services.length > 0) {
                    template.services.forEach(service => {
                        serviceCounter++;
                        const serviceId = `template-service-${serviceCounter}`;

                        const serviceHtml = `
                            <div class="card mb-2" id="${serviceId}">
                                <div class="card-body">
                                    <div class="row">
                                        <div class="col-md-4">
                                            <label class="form-label small">Service Name *</label>
                                            <input type="text" class="form-control form-control-sm service-name" placeholder="e.g., PE Router Config" value="${escapeHtml(service.name)}" required>
                                        </div>
                                        <div class="col-md-4">
                                            <label class="form-label small">Config Template *</label>
                                            <select class="form-select form-control-sm service-template" required>
                                                <option value="">Select template...</option>
                                                ${allTemplates.filter(t => t.delete_template).map(t => `<option value="${t.name}" ${service.template === t.name ? 'selected' : ''}>${t.name}</option>`).join('')}
                                            </select>
                                        </div>
                                        <div class="col-md-3">
                                            <label class="form-label small">Order</label>
                                            <input type="number" class="form-control form-control-sm service-order" value="${service.order || 0}" min="1">
                                        </div>
                                        <div class="col-md-1">
                                            <label class="form-label small">&nbsp;</label>
                                            <button type="button" class="btn btn-sm btn-danger w-100 remove-service-btn">
                                                <i class="fas fa-times"></i>
                                            </button>
                                        </div>
                                    </div>
                                </div>
                            </div>
                        `;

                        $('#template-services-container').append(serviceHtml);

                        // Attach remove handler
                        $(`#${serviceId} .remove-service-btn`).click(function() {
                            $(`#${serviceId}`).remove();
                            if ($('#template-services-container .card').length === 0) {
                                $('#template-services-container').html('<p class="text-muted">No services added yet. Click "Add Service" to define services for this template.</p>');
                            }
                        });
                    });
                } else {
                    $('#template-services-container').html('<p class="text-muted">No services added yet. Click "Add Service" to define services for this template.</p>');
                }

                $('#stackTemplateModalTitle').text('Edit Stack Template');
                const modal = new bootstrap.Modal(document.getElementById('stackTemplateModal'));
                modal.show();

                // Extract variables from templates to show detected variables with API configs
                setTimeout(() => {
                    extractTemplateVariables();
                }, 100);
            }
        })
        .fail(function(xhr) {
            alert('Failed to load template: ' + (xhr.responseJSON?.error || 'Unknown error'));
        });
}

/**
 * Delete stack template
 */
function deleteStackTemplate(templateId) {
    if (!confirm('Are you sure you want to delete this stack template?')) {
        return;
    }

    $.ajax({
        url: `/api/stack-templates/${templateId}`,
        method: 'DELETE'
    })
    .done(function(data) {
        if (data.success) {
            console.log('Stack template deleted successfully');
            loadStackTemplates();
        }
    })
    .fail(function(xhr) {
        alert('Failed to delete template: ' + (xhr.responseJSON?.error || 'Unknown error'));
    });
}

/**
 * Escape HTML to prevent XSS
 */
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return String(text).replace(/[&<>"']/g, m => map[m]);
}

// ==================== Scheduled Operations ====================

/**
 * Open schedule modal for a stack
 */
$(document).on('click', '#schedule-stack-btn', function() {
    const stackId = $('#stackDetailsModal').data('current-stack-id');
    if (!stackId) {
        alert('No stack selected');
        return;
    }

    $('#schedule-stack-id').val(stackId);
    $('#schedule-form')[0].reset();

    // Show datetime picker by default
    $('#schedule-datetime-section').show();
    $('#schedule-time-section').hide();
    $('#schedule-day-week-section').hide();
    $('#schedule-day-month-section').hide();

    // Load existing schedules
    loadScheduledOperations(stackId);

    const modal = new bootstrap.Modal(document.getElementById('scheduleStackModal'));
    modal.show();
});

/**
 * Handle schedule type changes
 */
$(document).on('change', '#schedule-type', function() {
    const scheduleType = $(this).val();

    // Hide all sections
    $('#schedule-datetime-section').hide();
    $('#schedule-time-section').hide();
    $('#schedule-day-week-section').hide();
    $('#schedule-day-month-section').hide();

    // Show relevant sections
    if (scheduleType === 'once') {
        $('#schedule-datetime-section').show();
        $('#schedule-datetime').prop('required', true);
        $('#schedule-time').prop('required', false);
    } else if (scheduleType === 'daily') {
        $('#schedule-time-section').show();
        $('#schedule-datetime').prop('required', false);
        $('#schedule-time').prop('required', true);
    } else if (scheduleType === 'weekly') {
        $('#schedule-time-section').show();
        $('#schedule-day-week-section').show();
        $('#schedule-datetime').prop('required', false);
        $('#schedule-time').prop('required', true);
    } else if (scheduleType === 'monthly') {
        $('#schedule-time-section').show();
        $('#schedule-day-month-section').show();
        $('#schedule-datetime').prop('required', false);
        $('#schedule-time').prop('required', true);
    }
});

/**
 * Create new schedule
 */
$(document).on('click', '#create-schedule-btn', function() {
    const stackId = $('#schedule-stack-id').val();
    const operationType = $('#schedule-operation-type').val();
    const scheduleType = $('#schedule-type').val();

    let scheduledTime, dayOfWeek, dayOfMonth;

    if (scheduleType === 'once') {
        scheduledTime = $('#schedule-datetime').val();
        if (!scheduledTime) {
            alert('Please select a date and time');
            return;
        }
        // Keep the time as-is in the system timezone (no UTC conversion)
        // The backend expects times in the container's local timezone
    } else {
        scheduledTime = $('#schedule-time').val();
        if (!scheduledTime) {
            alert('Please select a time');
            return;
        }

        if (scheduleType === 'weekly') {
            dayOfWeek = parseInt($('#schedule-day-week').val());
        } else if (scheduleType === 'monthly') {
            dayOfMonth = parseInt($('#schedule-day-month').val());
            if (!dayOfMonth || dayOfMonth < 1 || dayOfMonth > 31) {
                alert('Please enter a valid day of month (1-31)');
                return;
            }
        }
    }

    const scheduleData = {
        stack_id: stackId,
        operation_type: operationType,
        schedule_type: scheduleType,
        scheduled_time: scheduledTime,
        day_of_week: dayOfWeek,
        day_of_month: dayOfMonth
    };

    $.ajax({
        url: '/api/scheduled-operations',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(scheduleData)
    })
    .done(function(data) {
        if (data.success) {
            $('#schedule-form')[0].reset();
            loadScheduledOperations(stackId);
        } else {
            alert('Error: ' + (data.error || 'Failed to create schedule'));
        }
    })
    .fail(function(xhr) {
        alert('Failed to create schedule: ' + (xhr.responseJSON?.error || 'Unknown error'));
    });
});

/**
 * Load scheduled operations for a stack
 */
function loadScheduledOperations(stackId) {
    $('#existing-schedules-list').html('<div class="text-center"><small class="text-muted">Loading...</small></div>');

    $.get('/api/scheduled-operations?stack_id=' + encodeURIComponent(stackId))
        .done(function(data) {
            if (data.success && data.schedules && data.schedules.length > 0) {
                renderSchedulesList(data.schedules);
            } else {
                $('#existing-schedules-list').html('<div class="text-center text-muted"><small>No schedules yet</small></div>');
            }
        })
        .fail(function() {
            $('#existing-schedules-list').html('<div class="alert alert-danger">Failed to load schedules</div>');
        });
}

/**
 * Render schedules list
 */
function renderSchedulesList(schedules) {
    const operationIcons = {
        'deploy': '<i class="fas fa-rocket text-primary"></i>',
        'validate': '<i class="fas fa-check-circle text-info"></i>',
        'delete': '<i class="fas fa-trash text-danger"></i>'
    };

    const operationLabels = {
        'deploy': 'Deploy',
        'validate': 'Validate',
        'delete': 'Delete'
    };

    const scheduleTypeLabels = {
        'once': 'One-time',
        'daily': 'Daily',
        'weekly': 'Weekly',
        'monthly': 'Monthly'
    };

    const dayNames = ['Monday', 'Tuesday', 'Wednesday', 'Thursday', 'Friday', 'Saturday', 'Sunday'];

    let html = '<div class="list-group">';

    schedules.forEach(schedule => {
        const enabled = schedule.enabled ? true : false;
        const badge = enabled ? '<span class="badge bg-success">Enabled</span>' : '<span class="badge bg-secondary">Disabled</span>';

        let scheduleDetails = '';
        if (schedule.schedule_type === 'once') {
            console.log('DEBUG: schedule.scheduled_time =', schedule.scheduled_time);
            scheduleDetails = formatDate(schedule.scheduled_time);
            console.log('DEBUG: scheduleDetails after formatDate =', scheduleDetails);
        } else if (schedule.schedule_type === 'daily') {
            scheduleDetails = `Every day at ${schedule.scheduled_time}`;
        } else if (schedule.schedule_type === 'weekly') {
            scheduleDetails = `Every ${dayNames[schedule.day_of_week]} at ${schedule.scheduled_time}`;
        } else if (schedule.schedule_type === 'monthly') {
            scheduleDetails = `Day ${schedule.day_of_month} of each month at ${schedule.scheduled_time}`;
        }

        console.log('DEBUG: schedule.next_run =', schedule.next_run);
        const nextRun = schedule.next_run ? formatDate(schedule.next_run) : 'Not scheduled';
        console.log('DEBUG: nextRun after formatDate =', nextRun);

        html += `
            <div class="list-group-item">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <h6 class="mb-1">
                            ${operationIcons[schedule.operation_type]}
                            ${operationLabels[schedule.operation_type]} - ${scheduleTypeLabels[schedule.schedule_type]}
                            ${badge}
                        </h6>
                        <p class="mb-1"><small>${scheduleDetails}</small></p>
                        <p class="mb-1"><small class="text-muted">Next run: ${nextRun}</small></p>
                        ${schedule.last_run ? `<p class="mb-0"><small class="text-muted">Last run: ${formatDate(schedule.last_run)} (${schedule.run_count} times)</small></p>` : ''}
                    </div>
                    <div class="btn-group-vertical btn-group-sm">
                        <button class="btn btn-sm btn-outline-${enabled ? 'warning' : 'success'} toggle-schedule-btn"
                                data-schedule-id="${schedule.schedule_id}"
                                data-enabled="${enabled}">
                            <i class="fas fa-${enabled ? 'pause' : 'play'}"></i> ${enabled ? 'Disable' : 'Enable'}
                        </button>
                        <button class="btn btn-sm btn-outline-danger delete-schedule-btn"
                                data-schedule-id="${schedule.schedule_id}">
                            <i class="fas fa-trash"></i> Delete
                        </button>
                    </div>
                </div>
            </div>
        `;
    });

    html += '</div>';
    $('#existing-schedules-list').html(html);
}

/**
 * Toggle schedule enabled/disabled
 */
$(document).on('click', '.toggle-schedule-btn', function() {
    const scheduleId = $(this).data('schedule-id');
    const enabled = $(this).data('enabled');
    const newState = !enabled;

    $.ajax({
        url: `/api/scheduled-operations/${scheduleId}`,
        method: 'PATCH',
        contentType: 'application/json',
        data: JSON.stringify({ enabled: newState })
    })
    .done(function(data) {
        if (data.success) {
            const stackId = $('#schedule-stack-id').val();
            loadScheduledOperations(stackId);
        } else {
            alert('Error: ' + (data.error || 'Failed to update schedule'));
        }
    })
    .fail(function(xhr) {
        alert('Failed to update schedule: ' + (xhr.responseJSON?.error || 'Unknown error'));
    });
});

/**
 * Delete schedule
 */
$(document).on('click', '.delete-schedule-btn', function() {
    const scheduleId = $(this).data('schedule-id');

    $.ajax({
        url: `/api/scheduled-operations/${scheduleId}`,
        method: 'DELETE'
    })
    .done(function(data) {
        if (data.success) {
            const stackId = $('#schedule-stack-id').val();
            loadScheduledOperations(stackId);
        } else {
            alert('Error: ' + (data.error || 'Failed to delete schedule'));
        }
    })
    .fail(function(xhr) {
        alert('Failed to delete schedule: ' + (xhr.responseJSON?.error || 'Unknown error'));
    });
});


// ============================================================================
// API Variable Fetching for Stack Templates
// ============================================================================

/**
 * Fetch all API variables for a template
 */
function fetchAllApiVariables(template) {
    const apiVariables = template.api_variables || {};

    Object.keys(apiVariables).forEach(varName => {
        fetchApiVariable(varName, apiVariables[varName]);
    });

    // Attach manual fetch button handlers
    $('.fetch-api-var-btn').off('click').on('click', function() {
        const varName = $(this).data('var-name');
        const apiConfig = apiVariables[varName];
        if (apiConfig) {
            fetchApiVariable(varName, apiConfig);
        }
    });
}

/**
 * Fetch a single API variable from external API
 */
function fetchApiVariable(varName, apiConfig) {
    const $input = $(`.template-variable[data-var-name="${varName}"]`);
    const $status = $(`.api-fetch-status[data-var-name="${varName}"]`);
    const $button = $(`.fetch-api-var-btn[data-var-name="${varName}"]`);

    // Show loading state
    $button.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span>');
    $status.show().html('<span class="text-info"><i class="fas fa-spinner fa-spin"></i> Fetching from API...</span>');

    // Load resources if not cached
    if (apiResourcesCache.length === 0) {
        // Fetch resources synchronously
        $.ajax({
            url: '/api/api-resources',
            method: 'GET',
            async: false,
            success: function(response) {
                if (response.success) {
                    apiResourcesCache = response.resources;
                }
            }
        });
    }

    // Get the resource
    const resource = apiResourcesCache.find(r => r.resource_id === apiConfig.resource_id);
    if (!resource) {
        $status.html(`<span class="text-danger"><i class="fas fa-exclamation-triangle"></i> API resource not found</span>`);
        $button.prop('disabled', false).html('<i class="fas fa-sync-alt"></i>');
        return;
    }

    // Collect all available variables for substitution
    const variables = {};

    // Get device name from the deploy service device select (if in deployment modal)
    const $deviceSelect = $('.deploy-service-device-select').first();
    if ($deviceSelect.length && $deviceSelect.val()) {
        variables.device = $deviceSelect.val();
    }

    // Collect all other template variables
    $('.template-variable').each(function() {
        const vName = $(this).data('var-name');
        const vValue = $(this).val();
        if (vValue && vName !== varName) {  // Don't include the variable we're currently fetching
            variables[vName] = vValue;
        }
    });

    // Check if endpoint requires variables that aren't available
    const endpointVars = (apiConfig.endpoint.match(/\{\{(\w+)\}\}/g) || []).map(v => v.slice(2, -2));
    const bodyVars = apiConfig.body ? (apiConfig.body.match(/\{\{(\w+)\}\}/g) || []).map(v => v.slice(2, -2)) : [];
    const requiredVars = [...new Set([...endpointVars, ...bodyVars])];
    const missingVars = requiredVars.filter(v => !variables.hasOwnProperty(v));

    if (missingVars.length > 0) {
        $status.html(`<span class="text-warning"><i class="fas fa-exclamation-triangle"></i> Missing required variable(s): ${missingVars.join(', ')}. ${missingVars.includes('device') ? 'Please select a device first.' : 'Please fill in required fields.'}</span>`);
        $button.prop('disabled', false).html('<i class="fas fa-sync-alt"></i>');
        return;
    }

    // Build full URL for display (with unsubstituted variables)
    const baseUrl = resource.base_url.replace(/\/$/, '');
    const cleanEndpoint = apiConfig.endpoint.startsWith('/') ? apiConfig.endpoint : '/' + apiConfig.endpoint;
    const url = baseUrl + cleanEndpoint;

    // Make the request via backend proxy (bypasses CORS)
    console.log('Fetching API variable:', varName);
    console.log('API config:', apiConfig);
    console.log('Variables for substitution:', variables);

    $.ajax({
        url: '/api/proxy-api-call',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            resource_id: apiConfig.resource_id,
            endpoint: apiConfig.endpoint,
            method: apiConfig.method || 'GET',
            body: apiConfig.body,
            variables: variables  // Pass variables for substitution
        })
    })
    .done(function(response) {
        console.log('API response:', response);
        if (!response.success) {
            throw new Error(response.error || 'API call failed');
        }

        const data = response.data;
        console.log('Response data structure:', data);

        // Extract value using JSONPath
        let value;
        if (apiConfig.json_path) {
            console.log('Extracting with JSONPath:', apiConfig.json_path);
            value = extractJsonPath(data, apiConfig.json_path);
            console.log('Extracted value:', value);
        } else {
            // If no JSONPath, assume the response is the value
            value = data;
        }

        if (value !== null && value !== undefined) {
            $input.val(value);
            $status.html('<span class="text-success"><i class="fas fa-check-circle"></i> Fetched successfully</span>');

            // Hide status after 3 seconds
            setTimeout(() => {
                $status.fadeOut();
            }, 3000);
        } else {
            console.error('Failed to extract value. Data structure:', JSON.stringify(data, null, 2));
            throw new Error('Could not extract value from API response using JSONPath: ' + apiConfig.json_path);
        }
    })
    .fail(function(xhr) {
        const errorMsg = xhr.responseJSON ? xhr.responseJSON.error : 'API call failed';
        console.error('API fetch error:', errorMsg);
        $status.html(`<span class="text-danger"><i class="fas fa-exclamation-triangle"></i> Error: ${errorMsg}</span>`);
    })
    .always(function() {
        $button.prop('disabled', false).html('<i class="fas fa-sync-alt"></i>');
    });
}

/**
 * Fetch a single API variable for a specific device instance (per-device fetching)
 */
function fetchApiVariablePerDevice(varName, apiConfig, deviceInstanceId, deviceName) {
    const $input = $(`.template-variable-per-device[data-var-name="${varName}"][data-device-instance="${deviceInstanceId}"]`);
    const $status = $(`.api-fetch-status[data-var-name="${varName}"][data-device-instance="${deviceInstanceId}"]`);
    const $button = $(`.fetch-api-var-btn[data-var-name="${varName}"][data-device-instance="${deviceInstanceId}"]`);

    // Show loading state
    $button.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span>');
    $status.show().html('<span class="text-info"><i class="fas fa-spinner fa-spin"></i> Fetching from API...</span>');

    // Load resources if not cached
    if (apiResourcesCache.length === 0) {
        // Fetch resources synchronously
        $.ajax({
            url: '/api/api-resources',
            method: 'GET',
            async: false,
            success: function(response) {
                if (response.success) {
                    apiResourcesCache = response.resources;
                }
            }
        });
    }

    // Get the resource
    const resource = apiResourcesCache.find(r => r.resource_id === apiConfig.resource_id);
    if (!resource) {
        $status.html(`<span class="text-danger"><i class="fas fa-exclamation-triangle"></i> API resource not found</span>`);
        $button.prop('disabled', false).html('<i class="fas fa-sync-alt"></i>');
        return;
    }

    // Collect all available variables for substitution
    const variables = {};

    // Always include the device name for this specific device instance
    variables.device = deviceName;

    // Collect all shared variables (non-API variables from top section)
    $('.template-variable-shared').each(function() {
        const vName = $(this).data('var-name');
        const vValue = $(this).val();
        if (vValue) {
            variables[vName] = vValue;
        }
    });

    // Collect other per-device variables from THIS device instance
    $(`.template-variable-per-device[data-device-instance="${deviceInstanceId}"]`).each(function() {
        const vName = $(this).data('var-name');
        const vValue = $(this).val();
        if (vValue && vName !== varName) {  // Don't include the variable we're currently fetching
            variables[vName] = vValue;
        }
    });

    // Check if endpoint requires variables that aren't available
    const endpointVars = (apiConfig.endpoint.match(/\{\{(\w+)\}\}/g) || []).map(v => v.slice(2, -2));
    const bodyVars = apiConfig.body ? (apiConfig.body.match(/\{\{(\w+)\}\}/g) || []).map(v => v.slice(2, -2)) : [];
    const requiredVars = [...new Set([...endpointVars, ...bodyVars])];
    const missingVars = requiredVars.filter(v => !variables.hasOwnProperty(v));

    if (missingVars.length > 0) {
        $status.html(`<span class="text-warning"><i class="fas fa-exclamation-triangle"></i> Missing: ${missingVars.join(', ')}</span>`);
        $button.prop('disabled', false).html('<i class="fas fa-sync-alt"></i>');
        return;
    }

    // Make the request via backend proxy (bypasses CORS)
    console.log(`Fetching API variable '${varName}' for device '${deviceName}' (instance: ${deviceInstanceId})`);
    console.log('API config:', apiConfig);
    console.log('Variables for substitution:', variables);

    $.ajax({
        url: '/api/proxy-api-call',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            resource_id: apiConfig.resource_id,
            endpoint: apiConfig.endpoint,
            method: apiConfig.method || 'GET',
            body: apiConfig.body,
            variables: variables  // Pass variables for substitution (includes device name)
        })
    })
    .done(function(response) {
        console.log('API response:', response);
        if (!response.success) {
            throw new Error(response.error || 'API call failed');
        }

        const data = response.data;
        console.log('Response data structure:', data);

        // Extract value using JSONPath
        let value;
        if (apiConfig.json_path) {
            console.log('Extracting with JSONPath:', apiConfig.json_path);
            value = extractJsonPath(data, apiConfig.json_path);
            console.log('Extracted value:', value);
        } else {
            // If no JSONPath, assume the response is the value
            value = data;
        }

        if (value !== null && value !== undefined) {
            $input.val(value);
            $status.html('<span class="text-success"><i class="fas fa-check-circle"></i> Fetched</span>');

            // Hide status after 3 seconds
            setTimeout(() => {
                $status.fadeOut();
            }, 3000);
        } else {
            console.error('Failed to extract value. Data structure:', JSON.stringify(data, null, 2));
            throw new Error('Could not extract value from API response using JSONPath: ' + apiConfig.json_path);
        }
    })
    .fail(function(xhr) {
        const errorMsg = xhr.responseJSON ? xhr.responseJSON.error : 'API call failed';
        console.error('API fetch error:', errorMsg);
        $status.html(`<span class="text-danger"><i class="fas fa-exclamation-triangle"></i> Error: ${errorMsg}</span>`);
    })
    .always(function() {
        $button.prop('disabled', false).html('<i class="fas fa-sync-alt"></i>');
    });
}

/**
 * Simple JSONPath extractor (supports basic paths like $.data.ip_address)
 */
function extractJsonPath(data, path) {
    // Remove leading $. if present
    if (path.startsWith('$.')) {
        path = path.substring(2);
    } else if (path.startsWith('$')) {
        path = path.substring(1);
    }

    // Handle empty path
    if (!path || path === '') {
        return data;
    }

    // Split path and traverse
    const parts = path.split('.');
    let current = data;

    for (const part of parts) {
        // Handle array indices like [0] or results[0]
        if (part.includes('[') && part.includes(']')) {
            const arrayMatch = part.match(/^(\w+)?\[(\d+)\]$/);
            if (arrayMatch) {
                const key = arrayMatch[1];
                const index = parseInt(arrayMatch[2]);

                // If there's a key, navigate to it first
                if (key) {
                    current = current[key];
                }

                // Then access the array index
                if (Array.isArray(current)) {
                    current = current[index];
                } else {
                    return null;
                }
            }
        } else {
            if (current && current.hasOwnProperty(part)) {
                current = current[part];
            } else {
                return null;
            }
        }
    }

    return current;
}

/**
 * Fetch API variable for shared variables (stack-level, no device)
 * Uses the same logic as fetchApiVariablePerDevice but without device context
 */
function fetchApiVariableShared(varName, apiConfig) {
    const $input = $(`.template-variable-shared[data-var-name="${varName}"]`);
    const $status = $(`.api-fetch-status-shared[data-var-name="${varName}"]`);
    const $button = $(`.fetch-shared-api-var-btn[data-var-name="${varName}"]`);

    // Show loading state
    $button.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span>');
    $status.show().html('<span class="text-info"><i class="fas fa-spinner fa-spin"></i> Fetching from API...</span>');

    // Load resources if not cached
    if (apiResourcesCache.length === 0) {
        // Fetch resources synchronously
        $.ajax({
            url: '/api/api-resources',
            method: 'GET',
            async: false,
            success: function(response) {
                if (response.success) {
                    apiResourcesCache = response.resources;
                }
            }
        });
    }

    // Get the resource
    const resource = apiResourcesCache.find(r => r.resource_id === apiConfig.resource_id);
    if (!resource) {
        $status.html(`<span class="text-danger"><i class="fas fa-exclamation-triangle"></i> API resource not found</span>`);
        $button.prop('disabled', false).html('<i class="fas fa-sync-alt"></i>');
        return;
    }

    // Collect all available variables for substitution (no device for shared variables)
    const variables = {};

    // Collect other shared variables that might be needed for substitution
    $('.template-variable-shared').each(function() {
        const vName = $(this).data('var-name');
        const vValue = $(this).val();
        if (vValue && vName !== varName) {  // Don't include the variable we're currently fetching
            variables[vName] = vValue;
        }
    });

    // Check if endpoint requires variables that aren't available
    const endpointVars = (apiConfig.endpoint.match(/\{\{(\w+)\}\}/g) || []).map(v => v.slice(2, -2));
    const bodyVars = apiConfig.body ? (apiConfig.body.match(/\{\{(\w+)\}\}/g) || []).map(v => v.slice(2, -2)) : [];
    const requiredVars = [...new Set([...endpointVars, ...bodyVars])];
    const missingVars = requiredVars.filter(v => !variables.hasOwnProperty(v));

    if (missingVars.length > 0) {
        $status.html(`<span class="text-warning"><i class="fas fa-exclamation-triangle"></i> Missing: ${missingVars.join(', ')}</span>`);
        $button.prop('disabled', false).html('<i class="fas fa-sync-alt"></i>');
        return;
    }

    // Make the request via backend proxy (bypasses CORS)
    console.log(`Fetching shared API variable '${varName}'`);
    console.log('API config:', apiConfig);
    console.log('Variables for substitution:', variables);

    $.ajax({
        url: '/api/proxy-api-call',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            resource_id: apiConfig.resource_id,
            endpoint: apiConfig.endpoint,
            method: apiConfig.method || 'GET',
            body: apiConfig.body,
            variables: variables
        })
    })
    .done(function(response) {
        console.log('API response:', response);
        if (!response.success) {
            throw new Error(response.error || 'API call failed');
        }

        const data = response.data;
        console.log('Response data structure:', data);

        // Extract value using JSONPath (same logic as per-device)
        let value;
        if (apiConfig.json_path) {
            console.log('Extracting with JSONPath:', apiConfig.json_path);
            value = extractJsonPath(data, apiConfig.json_path);
            console.log('Extracted value:', value);
        } else {
            // If no JSONPath, assume the response is the value
            value = data;
        }

        if (value !== null && value !== undefined) {
            $input.val(value);
            $status.html('<span class="text-success"><i class="fas fa-check-circle"></i> Fetched</span>');

            // Hide status after 3 seconds
            setTimeout(() => {
                $status.fadeOut();
            }, 3000);
        } else {
            console.error('Failed to extract value. Data structure:', JSON.stringify(data, null, 2));
            throw new Error('Could not extract value from API response using JSONPath: ' + apiConfig.json_path);
        }
    })
    .fail(function(xhr) {
        const errorMsg = xhr.responseJSON ? xhr.responseJSON.error : 'API call failed';
        console.error('API fetch error:', errorMsg);
        $status.html(`<span class="text-danger"><i class="fas fa-exclamation-triangle"></i> Error: ${errorMsg}</span>`);
    })
    .always(function() {
        $button.prop('disabled', false).html('<i class="fas fa-sync-alt"></i>');
    });
}


// ============================================================================
// API Variable Configuration for Template Editor
// ============================================================================

// Store API configurations for variables
let apiVariableConfigs = {};
let apiResourcesCache = []; // Cache of available API resources
let perDeviceVariables = []; // List of variables that should be collected per-device

/**
 * Load API resources from backend
 */
function loadApiResources() {
    $.get('/api/api-resources')
        .done(function(response) {
            if (response.success) {
                apiResourcesCache = response.resources;
                populateApiResourceSelector();
            }
        })
        .fail(function() {
            console.error('Failed to load API resources');
        });
}

/**
 * Populate the API resource selector dropdown
 */
function populateApiResourceSelector() {
    const select = $('#api-config-resource');
    const currentValue = select.val();

    // Clear and re-add options
    select.html('<option value="">-- Select an API Resource --</option>');

    apiResourcesCache.forEach(resource => {
        select.append(`<option value="${resource.resource_id}">${resource.name}</option>`);
    });

    // Restore previous selection if it still exists
    if (currentValue) {
        select.val(currentValue);
    }
}

/**
 * Handle API resource selection change
 */
function handleApiResourceChange() {
    const resourceId = $('#api-config-resource').val();

    if (resourceId) {
        // Resource selected - show resource info
        const resource = apiResourcesCache.find(r => r.resource_id === resourceId);
        if (resource) {
            // Show resource info
            const authType = resource.auth_type || 'none';
            const authLabel = {
                'none': 'No Auth',
                'bearer': 'Bearer Token',
                'api_key': 'API Key',
                'basic': 'Basic Auth',
                'custom': 'Custom Headers'
            }[authType] || authType;

            $('#resource-base-url').text(resource.base_url);
            $('#resource-auth-type').text(authLabel);
            $('#api-config-resource-info').show();
        }
    } else {
        // No resource selected - hide info
        $('#api-config-resource-info').hide();
    }
}

/**
 * Handle API method change - show/hide request body for POST/PUT
 */
function handleApiMethodChange() {
    const method = $('#api-config-method').val();

    if (method === 'POST' || method === 'PUT') {
        $('#api-config-body-group').show();
    } else {
        $('#api-config-body-group').hide();
    }

    // Re-detect variables since body might have been shown
    detectAndShowTestVariables();
}

/**
 * Detect variables in endpoint and body, show test inputs
 */
function detectAndShowTestVariables() {
    const endpoint = $('#api-config-endpoint').val() || '';
    const body = $('#api-config-body').val() || '';
    const combined = endpoint + ' ' + body;

    // Find all {{variable}} patterns (double braces)
    const varMatches = combined.match(/\{\{(\w+)\}\}/g);

    if (varMatches && varMatches.length > 0) {
        // Get unique variable names (remove {{ and }})
        const varNames = [...new Set(varMatches.map(m => m.slice(2, -2)))];

        let html = '';
        varNames.forEach(varName => {
            html += `
                <div class="input-group input-group-sm mb-1">
                    <span class="input-group-text" style="min-width: 120px;">{{${varName}}}</span>
                    <input type="text" class="form-control test-var-input" data-var-name="${varName}"
                           placeholder="test_${varName}" value="test_${varName}">
                </div>
            `;
        });

        $('#test-variables-inputs').html(html);
        $('#test-variables-container').show();
    } else {
        $('#test-variables-container').hide();
    }
}

/**
 * Extract variables from all selected service templates
 */
function extractTemplateVariables() {
    const templates = [];

    // Collect all selected templates
    $('#template-services-container .service-template').each(function() {
        const templateName = $(this).val();
        if (templateName) {
            templates.push(templateName);
        }
    });

    if (templates.length === 0) {
        $('#detected-variables-card').hide();
        return;
    }

    // Fetch variables for each template
    const variablePromises = templates.map(templateName => {
        const cleanName = templateName.endsWith('.j2') ? templateName.slice(0, -3) : templateName;
        return $.get(`/api/templates/${cleanName}/variables`);
    });

    Promise.all(variablePromises)
        .then(responses => {
            // Collect all unique variables
            const allVariables = new Set();
            responses.forEach(response => {
                if (response.success && response.variables) {
                    response.variables.forEach(v => allVariables.add(v));
                }
            });

            if (allVariables.size > 0) {
                displayDetectedVariables(Array.from(allVariables).sort());
                $('#detected-variables-card').show();
            } else {
                $('#detected-variables-card').hide();
            }
        })
        .catch(error => {
            console.error('Error fetching template variables:', error);
        });
}

/**
 * Display detected variables with API config buttons
 */
function displayDetectedVariables(variables) {
    const container = $('#detected-variables-container');
    container.empty();

    console.log('displayDetectedVariables called with:', variables);
    console.log('Current perDeviceVariables:', perDeviceVariables);

    const html = variables.map(varName => {
        const hasApiConfig = apiVariableConfigs.hasOwnProperty(varName);
        const isPerDevice = perDeviceVariables.includes(varName);
        console.log(`Variable ${varName}: isPerDevice=${isPerDevice}`);

        // Determine display badge and type
        let variableType = 'Shared';
        let badgeClass = 'bg-secondary';
        let badgeIcon = 'fa-layer-group';

        if (isPerDevice && hasApiConfig) {
            variableType = 'Per-Device (API)';
            badgeClass = 'bg-success';
            badgeIcon = 'fa-cloud-download-alt';
        } else if (isPerDevice) {
            variableType = 'Per-Device';
            badgeClass = 'bg-primary';
            badgeIcon = 'fa-network-wired';
        }

        return `
            <div class="d-flex align-items-center justify-content-between mb-2 p-2 border rounded variable-row" data-var-name="${varName}">
                <div class="flex-grow-1">
                    <strong>${escapeHtml(varName)}</strong>
                    <span class="badge ${badgeClass} ms-2"><i class="fas ${badgeIcon}"></i> ${variableType}</span>
                </div>
                <div class="d-flex align-items-center gap-2">
                    <select class="form-select form-select-sm variable-type-select" data-var-name="${varName}" style="width: auto;">
                        <option value="shared" ${!isPerDevice ? 'selected' : ''}>Shared</option>
                        <option value="per-device" ${isPerDevice ? 'selected' : ''}>Per-Device</option>
                    </select>
                    <button type="button" class="btn btn-sm btn-outline-success config-api-btn" data-var-name="${varName}">
                        <i class="fas fa-cog"></i> ${hasApiConfig ? 'Edit' : 'Configure'} API
                    </button>
                </div>
            </div>
        `;
    }).join('');

    container.html(html);

    // Attach click handlers for API config buttons
    $('.config-api-btn').click(function() {
        const varName = $(this).data('var-name');
        openApiConfigModal(varName);
    });

    // Attach change handlers for variable type dropdown
    $('.variable-type-select').change(function() {
        const varName = $(this).data('var-name');
        const selectedType = $(this).val();

        if (selectedType === 'per-device') {
            // Add to per-device list if not already there
            if (!perDeviceVariables.includes(varName)) {
                perDeviceVariables.push(varName);
            }
        } else {
            // Remove from per-device list (making it shared)
            const index = perDeviceVariables.indexOf(varName);
            if (index > -1) {
                perDeviceVariables.splice(index, 1);
            }
        }

        // Update the badge display
        displayDetectedVariables(variables);
    });
}

/**
 * Open API configuration modal for a variable
 */
function openApiConfigModal(varName) {
    $('#api-config-var-name').val(varName);
    $('#api-config-var-display').text(varName);

    // Load resources if not already loaded
    if (apiResourcesCache.length === 0) {
        loadApiResources();
    } else {
        // Resources already loaded, populate selector immediately
        populateApiResourceSelector();
    }

    // Clear test results
    $('#api-test-result').hide().html('');

    // Load existing config if any
    const existingConfig = apiVariableConfigs[varName];
    if (existingConfig) {
        $('#api-config-resource').val(existingConfig.resource_id || '');
        $('#api-config-endpoint').val(existingConfig.endpoint || '');
        $('#api-config-method').val(existingConfig.method || 'GET');
        $('#api-config-body').val(existingConfig.body || '');
        $('#api-config-jsonpath').val(existingConfig.json_path || '');
        $('#api-config-description').val(existingConfig.description || '');
    } else {
        // Clear form
        $('#api-config-resource').val('');
        $('#api-config-endpoint').val('');
        $('#api-config-method').val('GET');
        $('#api-config-body').val('');
        $('#api-config-jsonpath').val('');
        $('#api-config-description').val('');
    }

    // Update UI to show resource info and handle method change
    setTimeout(() => {
        handleApiResourceChange();
        handleApiMethodChange();
        detectAndShowTestVariables();
    }, 10);

    const modal = new bootstrap.Modal(document.getElementById('apiVariableConfigModal'));
    modal.show();
}

/**
 * Save API configuration for a variable
 */
function saveApiConfig() {
    const varName = $('#api-config-var-name').val();
    const resourceId = $('#api-config-resource').val();
    const endpoint = $('#api-config-endpoint').val().trim();
    const method = $('#api-config-method').val();
    const body = $('#api-config-body').val().trim();
    const jsonPath = $('#api-config-jsonpath').val().trim();
    const description = $('#api-config-description').val().trim();

    // Validate
    if (!resourceId) {
        alert('Please select an API resource');
        return;
    }

    if (!endpoint) {
        alert('Endpoint path is required');
        return;
    }

    // Validate JSON body if provided
    if (body) {
        try {
            JSON.parse(body);
        } catch (e) {
            alert('Invalid JSON in request body: ' + e.message);
            return;
        }
    }

    // Save configuration
    apiVariableConfigs[varName] = {
        resource_id: resourceId,
        endpoint: endpoint,
        method: method,
        body: body || undefined,  // Only save if not empty
        json_path: jsonPath,
        description: description
    };

    // Close modal
    bootstrap.Modal.getInstance(document.getElementById('apiVariableConfigModal')).hide();

    // Refresh variables display to show API badge
    const variables = Array.from($('.variable-row')).map(row => $(row).data('var-name'));
    displayDetectedVariables(variables);
}

/**
 * Clear API configuration for a variable
 */
function clearApiConfig() {
    const varName = $('#api-config-var-name').val();
    delete apiVariableConfigs[varName];

    // Close modal
    bootstrap.Modal.getInstance(document.getElementById('apiVariableConfigModal')).hide();

    // Refresh variables display to remove API badge
    const variables = Array.from($('.variable-row')).map(row => $(row).data('var-name'));
    displayDetectedVariables(variables);
}

/**
 * Test API configuration
 */
function testApiConfig() {
    const resourceId = $('#api-config-resource').val();
    const endpoint = $('#api-config-endpoint').val().trim();
    const method = $('#api-config-method').val();
    const jsonPath = $('#api-config-jsonpath').val().trim();

    const resultDiv = $('#api-test-result');

    // Validate
    if (!resourceId) {
        resultDiv.show().html(`
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i> Please select an API resource first
            </div>
        `);
        return;
    }

    const resource = apiResourcesCache.find(r => r.resource_id === resourceId);
    if (!resource) {
        resultDiv.show().html(`
            <div class="alert alert-danger">
                <i class="fas fa-times-circle"></i> Selected resource not found. Please refresh the page.
            </div>
        `);
        return;
    }

    if (!endpoint) {
        resultDiv.show().html(`
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i> Please enter an endpoint path
            </div>
        `);
        return;
    }

    // Build full URL from resource base_url + endpoint
    const baseUrl = resource.base_url.replace(/\/$/, ''); // Remove trailing slash
    const cleanEndpoint = endpoint.startsWith('/') ? endpoint : '/' + endpoint;
    const url = baseUrl + cleanEndpoint;

    // Build headers based on auth type
    let headers = {};
    const authType = resource.auth_type || 'none';
    if (authType === 'bearer') {
        headers['Authorization'] = `Bearer ${resource.auth_token}`;
    } else if (authType === 'api_key') {
        headers['X-API-Key'] = resource.auth_token;
    } else if (authType === 'basic') {
        const credentials = btoa(`${resource.auth_username}:${resource.auth_password}`);
        headers['Authorization'] = `Basic ${credentials}`;
    } else if (authType === 'custom' && resource.custom_headers) {
        headers = resource.custom_headers;
    }

    // Show loading state with debug info
    $('#test-api-btn').prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> Testing...');

    // Collect test variable values from inputs
    const testVariables = {};
    $('.test-var-input').each(function() {
        const varName = $(this).data('var-name');
        const varValue = $(this).val().trim();
        if (varValue) {
            testVariables[varName] = varValue;
        }
    });

    // Build display URL with test values (double braces)
    let displayUrl = url;
    Object.keys(testVariables).forEach(varName => {
        displayUrl = displayUrl.replace(new RegExp(`\\{\\{${varName}\\}\\}`, 'g'), testVariables[varName]);
    });

    // Get and substitute variables in request body (double braces)
    const body = $('#api-config-body').val().trim();
    let displayBody = body;
    if (body) {
        Object.keys(testVariables).forEach(varName => {
            displayBody = displayBody.replace(new RegExp(`\\{\\{${varName}\\}\\}`, 'g'), testVariables[varName]);
        });
    }

    // Show what we're about to call
    let debugInfo = `
        <div class="alert alert-info mb-2">
            <i class="fas fa-spinner fa-spin"></i> Making API request via backend proxy...
        </div>
        <div class="card mb-2">
            <div class="card-body py-2">
                <small><strong>URL:</strong> <code>${escapeHtml(displayUrl)}</code></small><br>
                <small><strong>Method:</strong> ${method}</small><br>
                <small><strong>Auth:</strong> ${escapeHtml(resource.auth_type || 'none')}</small>
    `;

    if (displayBody) {
        debugInfo += `<br><small><strong>Body:</strong> <code>${escapeHtml(displayBody.substring(0, 100))}${displayBody.length > 100 ? '...' : ''}</code></small>`;
    }

    if (Object.keys(testVariables).length > 0) {
        debugInfo += `<br><small class="text-warning"><strong>Variables:</strong> ${escapeHtml(JSON.stringify(testVariables))}</small>`;
    }

    debugInfo += `
            </div>
        </div>
    `;
    resultDiv.show().html(debugInfo);

    // Make the request via backend proxy (bypasses CORS)
    $.ajax({
        url: '/api/proxy-api-call',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            resource_id: resourceId,
            endpoint: endpoint,
            method: method,
            body: displayBody || undefined,  // Send substituted body
            variables: testVariables  // Pass test variables for substitution
        })
    })
    .done(function(response) {
        if (!response.success) {
            throw new Error(response.error || 'Unknown error');
        }

        const data = response.data;
        const status = response.status;
        const statusText = response.statusText;


        // Extract value using JSONPath if provided
        let extractedValue = null;
        let extractError = null;

        if (jsonPath) {
            try {
                extractedValue = extractJsonPath(data, jsonPath);
            } catch (e) {
                extractError = e.message;
            }
        }

        // Display results
        let html = `
            <div class="alert alert-success">
                <strong><i class="fas fa-check-circle"></i> API Call Successful</strong>
                <div class="mt-2">
                    <strong>Status:</strong> ${status} ${statusText}
                </div>
            </div>
        `;

        if (jsonPath) {
            if (extractedValue !== null && extractedValue !== undefined) {
                html += `
                    <div class="alert alert-success">
                        <strong><i class="fas fa-bullseye"></i> Extracted Value:</strong>
                        <div class="mt-2">
                            <code class="bg-white p-2 d-block border rounded">${escapeHtml(String(extractedValue))}</code>
                        </div>
                        <small class="text-muted">From JSONPath: ${escapeHtml(jsonPath)}</small>
                    </div>
                `;
            } else {
                html += `
                    <div class="alert alert-warning">
                        <strong><i class="fas fa-exclamation-triangle"></i> JSONPath Extraction Failed</strong>
                        <div class="mt-2">
                            <small>JSONPath: <code>${escapeHtml(jsonPath)}</code></small><br>
                            <small>${extractError || 'No value found at the specified path'}</small>
                        </div>
                    </div>
                `;
            }
        }

        html += `
            <div class="card">
                <div class="card-header">
                    <strong>Full API Response:</strong>
                </div>
                <div class="card-body">
                    <pre class="mb-0" style="max-height: 300px; overflow-y: auto; font-size: 0.85rem;"><code>${escapeHtml(JSON.stringify(data, null, 2))}</code></pre>
                </div>
            </div>
        `;

        resultDiv.html(html);
    })
    .fail(function(xhr) {
        const errorMsg = xhr.responseJSON ? xhr.responseJSON.error : 'Unknown error';
        console.error('API test error:', errorMsg);
        console.error('Failed URL:', url);

        resultDiv.html(`
            <div class="alert alert-danger">
                <strong><i class="fas fa-times-circle"></i> API Call Failed</strong>
                <div class="mt-2">
                    <strong>Error:</strong> ${escapeHtml(errorMsg)}
                </div>
                <div class="mt-2">
                    <small><strong>URL:</strong> <code>${escapeHtml(url)}</code></small><br>
                    <small><strong>Method:</strong> ${method}</small><br>
                    <small><strong>Resource:</strong> ${escapeHtml(resource.name)}</small>
                </div>
            </div>
            <div class="alert alert-secondary mt-2">
                <small class="text-muted">
                    <strong>Common issues:</strong>
                    <ul class="mb-0">
                        <li><strong>Invalid URL</strong> - Check base URL + endpoint path combination</li>
                        <li><strong>Invalid auth</strong> - Check authentication credentials in resource</li>
                        <li><strong>Network issue</strong> - API server unreachable from NetStacks backend</li>
                        <li><strong>Timeout</strong> - API took longer than 30 seconds to respond</li>
                    </ul>
                </small>
            </div>
        `);
    })
    .always(function() {
        $('#test-api-btn').prop('disabled', false).html('<i class="fas fa-flask"></i> Test API Call');
    });
}

// Initialize API config modal handlers
// Using direct binding when modal opens to ensure handlers work with Bootstrap modals
$(document).on('shown.bs.modal', '#apiVariableConfigModal', function() {
    // Attach handlers directly to ensure they work properly
    $('#save-api-config-btn').off('click').on('click', function(e) {
        e.preventDefault();
        saveApiConfig();
    });

    $('#clear-api-config-btn').off('click').on('click', function(e) {
        e.preventDefault();
        clearApiConfig();
    });

    $('#test-api-btn').off('click').on('click', function(e) {
        e.preventDefault();
        testApiConfig();
    });
});

$(document).on('change', '#api-config-resource', handleApiResourceChange);
$(document).on('change', '#api-config-method', handleApiMethodChange);

// Watch for endpoint and body changes to detect variables
$(document).on('input', '#api-config-endpoint, #api-config-body', detectAndShowTestVariables);

// Watch for template selection changes
$(document).on('change', '.service-template', function() {
    extractTemplateVariables();
});

// Update timezone labels in schedule modal
function updateTimezoneLabels() {
    const systemTz = (typeof systemTimezone !== 'undefined') ? systemTimezone : 'UTC';
    const tzLabel = systemTz === 'UTC' ? 'UTC' : systemTz;

    $('#schedule-datetime-label').text(`Date and Time (${tzLabel}) *`);
    $('#schedule-time-label').text(`Time (${tzLabel}) *`);
}

// Set datetime-local input to current server time
function setCurrentServerTime() {
    const systemTz = (typeof systemTimezone !== 'undefined') ? systemTimezone : 'UTC';
    const now = new Date();

    try {
        // Format current time in system timezone as datetime-local format
        const options = {
            timeZone: systemTz,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            hour12: false
        };

        const formatter = new Intl.DateTimeFormat('en-CA', options);
        const parts = formatter.formatToParts(now);
        const dateMap = {};
        parts.forEach(part => {
            dateMap[part.type] = part.value;
        });

        // Create datetime-local format: YYYY-MM-DDTHH:MM
        const datetimeLocal = `${dateMap.year}-${dateMap.month}-${dateMap.day}T${dateMap.hour}:${dateMap.minute}`;
        $('#schedule-datetime').val(datetimeLocal);
    } catch (e) {
        console.error('Error setting current time:', e);
        // Fallback to browser local time
        const localString = now.toISOString().slice(0, 16);
        $('#schedule-datetime').val(localString);
    }
}

// Update server time display using system timezone
function updateServerTime() {
    const now = new Date();
    let timeString;

    // Get system timezone from global variable set in base.html
    const systemTz = (typeof systemTimezone !== 'undefined') ? systemTimezone : 'UTC';

    try {
        // Format time in the configured timezone
        const options = {
            timeZone: systemTz,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: false
        };
        const formatter = new Intl.DateTimeFormat('en-CA', options);
        const parts = formatter.formatToParts(now);
        const dateMap = {};
        parts.forEach(part => {
            dateMap[part.type] = part.value;
        });
        timeString = `${dateMap.year}-${dateMap.month}-${dateMap.day} ${dateMap.hour}:${dateMap.minute}:${dateMap.second}`;

        // Add timezone abbreviation
        if (systemTz === 'UTC') {
            timeString += ' UTC';
        } else {
            timeString += ` (${systemTz})`;
        }
    } catch (e) {
        // Fallback to UTC if timezone is invalid
        timeString = now.toISOString().slice(0, 19).replace('T', ' ') + ' UTC';
    }

    $('#server-time-display').text(timeString);
    $('#server-time-display-daily').text(timeString);
}

/**
 * Filter stack templates based on search query
 */
function filterStackTemplates(query) {
    const searchTerm = query.toLowerCase().trim();
    const templates = $('#stack-templates-container .card');

    if (!searchTerm) {
        // Show all templates if search is empty
        templates.show();
        return;
    }

    templates.each(function() {
        const $template = $(this);
        const name = $template.find('.card-title').text().toLowerCase();
        const description = $template.find('.text-muted').text().toLowerCase();

        // Check if name or description contains the search term
        if (name.includes(searchTerm) || description.includes(searchTerm)) {
            $template.show();
        } else {
            $template.hide();
        }
    });
}

/**
 * Filter deployed stacks based on search query
 */
function filterDeployedStacks(query) {
    const searchTerm = query.toLowerCase().trim();
    const stacks = $('#stacks-container .card');

    if (!searchTerm) {
        // Show all stacks if search is empty
        stacks.show();
        return;
    }

    stacks.each(function() {
        const $stack = $(this);
        // Stack name is in <h6> inside card-header, not using card-title class
        const name = $stack.find('.card-header h6').text().toLowerCase();
        const description = $stack.find('.card-body .text-muted').text().toLowerCase();

        // Check if name or description contains the search term
        if (name.includes(searchTerm) || description.includes(searchTerm)) {
            $stack.show();
        } else {
            $stack.hide();
        }
    });
}
