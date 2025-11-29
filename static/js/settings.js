// Settings page JavaScript

// Utility function to show alerts
function showAlert(type, message) {
    const alertHtml = `
        <div class="alert alert-${type} alert-dismissible fade show" role="alert">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert" aria-label="Close"></button>
        </div>
    `;

    // Insert at the top of the content area
    $('.container-fluid').prepend(alertHtml);

    // Auto-dismiss after 5 seconds
    setTimeout(() => {
        $('.alert').fadeOut(() => {
            $(this).remove();
        });
    }, 5000);
}

// Default settings
const DEFAULT_SETTINGS = {
    netbox_url: 'https://netbox.example.com',
    netbox_token: '',
    netbox_verify_ssl: false,
    netbox_filters: [],
    default_username: '',
    default_password: '',
    cache_ttl: 300,
    timezone: 'auto'
};

$(document).ready(function() {
    loadSettings();
    loadTheme();
    updateTimezoneDisplay();

    // Theme change handler
    $('#theme-select').change(function() {
        saveTheme($(this).val());
    });

    // Timezone change handler
    $('#timezone-select').change(function() {
        updateTimezoneDisplay();
    });

    // Save settings form submit
    $('#settings-form').submit(function(e) {
        e.preventDefault();
        saveSettings();
    });

    // Reset to defaults
    $('#reset-btn').click(function() {
        if (confirm('Are you sure you want to reset all settings to defaults?')) {
            resetToDefaults();
        }
    });

    // Clear all data
    $('#clear-all-btn').click(function() {
        if (confirm('This will clear all settings and cached data. Are you sure?')) {
            clearAllData();
        }
    });

    // Add filter button
    $('#add-filter-btn').click(function() {
        addFilterRow();
    });

    // Test Netbox connection button
    $('#test-netbox-btn').click(function() {
        testNetboxConnection();
    });

});

function loadSettings() {
    // Load backend settings first, then merge with localStorage
    $.ajax({
        url: '/api/settings',
        method: 'GET'
    })
    .done(function(data) {
        if (data.success) {
            // Get user preferences from localStorage
            const localSettings = getSettings();

            // Merge backend settings with local preferences
            const settings = {
                ...localSettings,
                netbox_url: data.settings.netbox_url || localSettings.netbox_url,
                netbox_verify_ssl: data.settings.verify_ssl !== undefined ? data.settings.verify_ssl : localSettings.netbox_verify_ssl
            };

            // Note: tokens are masked in API response, so we keep them from localStorage
            // unless localStorage is empty (first time)
            if (!localSettings.netbox_token && data.settings.netbox_token !== '****') {
                settings.netbox_token = data.settings.netbox_token;
            }

            populateForm(settings);
        }
    })
    .fail(function() {
        // Fall back to localStorage only
        console.warn('Could not load backend settings, using localStorage');
        const settings = getSettings();
        populateForm(settings);
    });
}

function populateForm(settings) {
    // Populate form fields
    $('#netbox-url').val(settings.netbox_url);
    $('#netbox-token').val(settings.netbox_token);
    $('#netbox-verify-ssl').prop('checked', settings.netbox_verify_ssl);
    $('#default-username').val(settings.default_username);
    $('#default-password').val(settings.default_password);
    $('#cache-ttl').val(settings.cache_ttl);
    $('#timezone-select').val(settings.timezone || 'auto');
    $('#system-timezone').val(settings.system_timezone || 'UTC');

    // Load filters
    loadFilters(settings.netbox_filters || []);

    updateStatus(settings);
    updateTimezoneDisplay();
}

function saveSettings() {
    // Collect filters
    const filters = [];
    $('.netbox-filter-row').each(function() {
        const key = $(this).find('.filter-key').val().trim();
        const value = $(this).find('.filter-value').val().trim();
        if (key && value) {
            filters.push({ key: key, value: value });
        }
    });

    const settings = {
        netbox_url: $('#netbox-url').val().trim(),
        netbox_token: $('#netbox-token').val().trim(),
        netbox_verify_ssl: $('#netbox-verify-ssl').is(':checked'),
        netbox_filters: filters,
        default_username: $('#default-username').val().trim(),
        default_password: $('#default-password').val().trim(),
        cache_ttl: parseInt($('#cache-ttl').val()),
        timezone: $('#timezone-select').val(),
        system_timezone: $('#system-timezone').val()
    };

    // Validate
    if (settings.cache_ttl < 60 || settings.cache_ttl > 3600) {
        alert('Cache TTL must be between 60 and 3600 seconds');
        return;
    }

    // Save to localStorage (for user preferences like filters, credentials)
    localStorage.setItem('netstacks_settings', JSON.stringify(settings));

    // Save backend settings (Netbox URLs) to database via API
    const backendSettings = {
        netbox_url: settings.netbox_url,
        netbox_token: settings.netbox_token,
        verify_ssl: settings.netbox_verify_ssl,
        default_username: settings.default_username,
        default_password: settings.default_password,
        system_timezone: settings.system_timezone
    };

    $.ajax({
        url: '/api/settings',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(backendSettings)
    })
    .done(function(data) {
        if (data.success) {
            showNotification('Settings saved successfully!', 'success');
            updateStatus(settings);
        } else {
            showNotification('Error saving backend settings: ' + (data.error || 'Unknown error'), 'error');
        }
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON ? xhr.responseJSON.error : 'Request failed';
        showNotification('Failed to save backend settings: ' + error, 'error');
    });
}

function getSettings() {
    const stored = localStorage.getItem('netstacks_settings');
    if (stored) {
        try {
            return JSON.parse(stored);
        } catch (e) {
            console.error('Error parsing stored settings:', e);
            return DEFAULT_SETTINGS;
        }
    }
    return DEFAULT_SETTINGS;
}

function resetToDefaults() {
    // Set form to defaults
    $('#netbox-url').val(DEFAULT_SETTINGS.netbox_url);
    $('#netbox-token').val(DEFAULT_SETTINGS.netbox_token);
    $('#netbox-verify-ssl').prop('checked', DEFAULT_SETTINGS.netbox_verify_ssl);
    $('#default-username').val(DEFAULT_SETTINGS.default_username);
    $('#default-password').val(DEFAULT_SETTINGS.default_password);
    $('#cache-ttl').val(DEFAULT_SETTINGS.cache_ttl);

    // Clear filters
    loadFilters([]);

    // Save defaults
    localStorage.setItem('netstacks_settings', JSON.stringify(DEFAULT_SETTINGS));

    showNotification('Settings reset to defaults', 'info');
    updateStatus(DEFAULT_SETTINGS);
}

function clearAllData() {
    // Clear all localStorage
    localStorage.clear();

    // Reset form
    resetToDefaults();

    showNotification('All data cleared successfully', 'warning');
}

function updateStatus(settings) {
    const statusEl = $('#settings-status');
    statusEl.empty();

    let configured = true;
    let issues = [];

    if (!settings.netbox_token) {
        issues.push('Netbox token not set');
        configured = false;
    }

    if (!settings.default_username) {
        issues.push('Default credentials not set');
    }

    if (configured && issues.length === 0) {
        statusEl.html('<span class="badge bg-success">Fully Configured</span>');
    } else if (configured) {
        statusEl.html('<span class="badge bg-warning">Partially Configured</span>');
        issues.forEach(function(issue) {
            statusEl.append(`<br><small class="text-muted">- ${issue}</small>`);
        });
    } else {
        statusEl.html('<span class="badge bg-danger">Not Configured</span>');
        issues.forEach(function(issue) {
            statusEl.append(`<br><small class="text-muted">- ${issue}</small>`);
        });
    }
}

function showNotification(message, type) {
    // Create Bootstrap alert
    const alertClass = type === 'success' ? 'alert-success' :
                      type === 'warning' ? 'alert-warning' :
                      type === 'info' ? 'alert-info' : 'alert-danger';

    const alert = $(`
        <div class="alert ${alertClass} alert-dismissible fade show position-fixed top-0 start-50 translate-middle-x mt-3" role="alert" style="z-index: 9999; min-width: 300px;">
            ${message}
            <button type="button" class="btn-close" data-bs-dismiss="alert"></button>
        </div>
    `);

    $('body').append(alert);

    // Auto-dismiss after 3 seconds
    setTimeout(function() {
        alert.alert('close');
    }, 3000);
}

// Filter management functions
function loadFilters(filters) {
    const container = $('#netbox-filters-container');
    container.empty();

    if (filters.length === 0) {
        // Add one empty filter by default
        addFilterRow();
    } else {
        filters.forEach(function(filter) {
            addFilterRow(filter.key, filter.value);
        });
    }
}

function addFilterRow(key = '', value = '') {
    const container = $('#netbox-filters-container');
    const rowId = 'filter-row-' + Date.now();

    const row = $(`
        <div class="row mb-2 netbox-filter-row" id="${rowId}">
            <div class="col-md-5">
                <input type="text" class="form-control form-control-sm filter-key" placeholder="Filter key (e.g., tag)" value="${key}">
            </div>
            <div class="col-md-5">
                <input type="text" class="form-control form-control-sm filter-value" placeholder="Filter value (e.g., production)" value="${value}">
            </div>
            <div class="col-md-2">
                <button type="button" class="btn btn-sm btn-outline-danger remove-filter-btn w-100" data-row-id="${rowId}">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        </div>
    `);

    container.append(row);

    // Attach remove handler
    row.find('.remove-filter-btn').on('click', function() {
        const rowIdToRemove = $(this).data('row-id');
        $('#' + rowIdToRemove).remove();

        // If no filters left, add one empty
        if ($('.netbox-filter-row').length === 0) {
            addFilterRow();
        }
    });
}

function testNetboxConnection() {
    const btn = $('#test-netbox-btn');
    const resultDiv = $('#netbox-test-result');

    // Get current values from form
    const netboxUrl = $('#netbox-url').val().trim();
    const netboxToken = $('#netbox-token').val().trim();
    const verifySSL = $('#netbox-verify-ssl').is(':checked');

    // Collect current filters from the form
    const filters = [];
    $('.netbox-filter-row').each(function() {
        const key = $(this).find('.filter-key').val().trim();
        const value = $(this).find('.filter-value').val().trim();
        if (key && value) {
            filters.push({ key: key, value: value });
        }
    });

    if (!netboxUrl) {
        resultDiv.html('<div class="alert alert-warning"><i class="fas fa-exclamation-triangle"></i> Please enter a Netbox URL first</div>').show();
        return;
    }

    // Disable button and show loading
    btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> Testing...');

    let loadingMsg = '<div class="alert alert-info"><i class="fas fa-spinner fa-spin"></i> Connecting to Netbox...';
    if (filters.length > 0) {
        loadingMsg += '<br><small class="text-muted">Testing with ' + filters.length + ' filter(s)</small>';
    }
    loadingMsg += '</div>';
    resultDiv.html(loadingMsg).show();

    // Send test request
    $.ajax({
        url: '/api/test-netbox',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            netbox_url: netboxUrl,
            netbox_token: netboxToken,
            verify_ssl: verifySSL,
            filters: filters
        }),
        timeout: 35000  // Increased to 35 seconds
    })
    .done(function(data) {
        if (data.success) {
            let successMsg = `
                <div class="alert alert-success">
                    <i class="fas fa-check-circle"></i> <strong>Connection Successful!</strong><br>
                    <small>Found ${data.device_count} devices in Netbox</small><br>`;

            if (data.connection_count !== undefined) {
                successMsg += `<small>Found ${data.connection_count} connections</small><br>`;
            }

            if (data.cached) {
                successMsg += `<small><i class="fas fa-database"></i> Cached for fast network map loading</small><br>`;
            }

            successMsg += `<small class="text-muted">Response time: ${data.response_time || 'N/A'}</small>
                </div>
                <details class="mt-2">
                    <summary class="text-muted small" style="cursor: pointer;">
                        <i class="fas fa-info-circle"></i> Show API Details
                    </summary>
                    <div class="card card-body bg-light mt-2">
                        <p class="mb-1"><strong>API URL:</strong></p>
                        <code class="small">${data.api_url || 'N/A'}</code>
                        <p class="mb-1 mt-2"><strong>SSL Verification:</strong> ${data.verify_ssl ? 'Enabled' : 'Disabled'}</p>
                        <p class="mb-0"><strong>Using Token:</strong> ${data.has_token ? 'Yes' : 'No (Public access)'}</p>
                    </div>
                </details>
            `;
            resultDiv.html(successMsg);
        } else {
            resultDiv.html(`
                <div class="alert alert-danger">
                    <i class="fas fa-times-circle"></i> <strong>Connection Failed</strong><br>
                    <small>${data.error || 'Unknown error'}</small>
                </div>
                <details class="mt-2">
                    <summary class="text-muted small" style="cursor: pointer;">
                        <i class="fas fa-info-circle"></i> Show Debug Details
                    </summary>
                    <div class="card card-body bg-light mt-2">
                        <p class="mb-1"><strong>API URL:</strong></p>
                        <code class="small">${data.api_url || 'N/A'}</code>
                        ${data.status_code ? '<p class="mb-1 mt-2"><strong>HTTP Status:</strong> ' + data.status_code + '</p>' : ''}
                        ${data.details ? '<p class="mb-0 mt-2"><strong>Technical Details:</strong><br><small>' + data.details + '</small></p>' : ''}
                    </div>
                </details>
            `);
        }
    })
    .fail(function(xhr) {
        let errorMsg = 'Connection failed';
        let apiUrl = netboxUrl + '/api/dcim/devices/?brief=true&limit=10';
        let details = '';

        if (xhr.responseJSON) {
            errorMsg = xhr.responseJSON.error || errorMsg;
            apiUrl = xhr.responseJSON.api_url || apiUrl;
            details = xhr.responseJSON.details || '';
        } else if (xhr.statusText) {
            errorMsg = xhr.statusText;
        }

        resultDiv.html(`
            <div class="alert alert-danger">
                <i class="fas fa-times-circle"></i> <strong>Connection Failed</strong><br>
                <small>${errorMsg}</small>
            </div>
            <details class="mt-2">
                <summary class="text-muted small" style="cursor: pointer;">
                    <i class="fas fa-info-circle"></i> Show Debug Details
                </summary>
                <div class="card card-body bg-light mt-2">
                    <p class="mb-1"><strong>API URL:</strong></p>
                    <code class="small">${apiUrl}</code>
                    ${details ? '<p class="mb-0 mt-2"><strong>Technical Details:</strong><br><small>' + details + '</small></p>' : ''}
                </div>
            </details>
        `);
    })
    .always(function() {
        btn.prop('disabled', false).html('<i class="fas fa-plug"></i> Test Netbox Connection');
    });
}

// Theme management functions
function loadTheme() {
    $.get('/api/user/theme')
        .done(function(data) {
            if (data.success) {
                $('#theme-select').val(data.theme);
            }
        })
        .fail(function() {
            // Default to dark if API fails
            $('#theme-select').val('dark');
        });
}

function saveTheme(theme) {
    $.ajax({
        url: '/api/user/theme',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ theme: theme })
    })
    .done(function(data) {
        if (data.success) {
            // Update the theme immediately without page reload
            $('html').attr('data-bs-theme', theme);
            showNotification(`Theme changed to ${theme}`, 'success');
        }
    })
    .fail(function(xhr) {
        showNotification('Failed to save theme: ' + (xhr.responseJSON?.error || 'Unknown error'), 'danger');
    });
}

// Timezone display update
function updateTimezoneDisplay() {
    const selectedTz = $('#timezone-select').val();
    let displayText = '';

    if (selectedTz === 'auto') {
        // Get browser timezone
        const browserTz = Intl.DateTimeFormat().resolvedOptions().timeZone;
        displayText = `Auto-detect (${browserTz})`;
    } else {
        displayText = selectedTz;
    }

    $('#current-timezone-display').text(displayText);
}

// Get user's timezone preference
function getUserTimezone() {
    const settings = getSettings();
    const tzSetting = settings.timezone || 'auto';

    if (tzSetting === 'auto') {
        // Return browser timezone
        return Intl.DateTimeFormat().resolvedOptions().timeZone;
    }

    return tzSetting;
}

// Export functions for use in other pages
window.getAppSettings = getSettings;
window.getUserTimezone = getUserTimezone;

// ============================================================================
// API Resources Management
// ============================================================================

let apiResourcesData = [];

// Helper function to escape HTML
function escapeHtml(text) {
    const map = {
        '&': '&amp;',
        '<': '&lt;',
        '>': '&gt;',
        '"': '&quot;',
        "'": '&#039;'
    };
    return text.replace(/[&<>"']/g, m => map[m]);
}

// Load API resources
function loadApiResources() {
    $.get('/api/api-resources')
        .done(function(response) {
            if (response.success) {
                apiResourcesData = response.resources;
                displayApiResources();
            }
        })
        .fail(function() {
            $('#api-resources-list').html('<div class="alert alert-danger">Failed to load API resources</div>');
        });
}

// Display API resources
function displayApiResources() {
    const container = $('#api-resources-list');

    if (apiResourcesData.length === 0) {
        container.html('<p class="text-muted text-center">No API resources configured. Click "Add Resource" to create one.</p>');
        return;
    }

    let html = '<div class="list-group">';
    apiResourcesData.forEach(resource => {
        const authType = resource.auth_type || 'none';
        const authBadge = {
            'none': '<span class="badge bg-secondary">No Auth</span>',
            'bearer': '<span class="badge bg-primary">Bearer Token</span>',
            'api_key': '<span class="badge bg-primary">API Key</span>',
            'basic': '<span class="badge bg-info">Basic Auth</span>',
            'custom': '<span class="badge bg-warning text-dark">Custom Headers</span>'
        }[authType];

        html += `
            <div class="list-group-item">
                <div class="d-flex justify-content-between align-items-start">
                    <div class="flex-grow-1">
                        <h6 class="mb-1">${escapeHtml(resource.name)} ${authBadge}</h6>
                        <p class="mb-1 small text-muted">${escapeHtml(resource.description || '')}</p>
                        <small class="text-muted"><i class="fas fa-link"></i> ${escapeHtml(resource.base_url)}</small>
                    </div>
                    <div class="btn-group">
                        <button class="btn btn-sm btn-outline-primary edit-api-resource-btn" data-resource-id="${resource.resource_id}">
                            <i class="fas fa-edit"></i> Edit
                        </button>
                        <button class="btn btn-sm btn-outline-danger delete-api-resource-btn" data-resource-id="${resource.resource_id}">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        `;
    });
    html += '</div>';

    container.html(html);

    // Attach event handlers
    $('.edit-api-resource-btn').click(function() {
        const resourceId = $(this).data('resource-id');
        editApiResource(resourceId);
    });

    $('.delete-api-resource-btn').click(function() {
        const resourceId = $(this).data('resource-id');
        deleteApiResource(resourceId);
    });
}

// Open add API resource modal
function openAddApiResourceModal() {
    $('#apiResourceModalTitle').text('Add API Resource');
    $('#api-resource-id').val('');
    $('#api-resource-name').val('');
    $('#api-resource-description').val('');
    $('#api-resource-base-url').val('');
    $('#api-resource-auth-type').val('none').trigger('change');
    $('#api-resource-token').val('');
    $('#api-resource-username').val('');
    $('#api-resource-password').val('');
    $('#api-resource-custom-headers').val('');

    const modal = new bootstrap.Modal(document.getElementById('apiResourceModal'));
    modal.show();
}

// Edit API resource
function editApiResource(resourceId) {
    const resource = apiResourcesData.find(r => r.resource_id === resourceId);
    if (!resource) return;

    $('#apiResourceModalTitle').text('Edit API Resource');
    $('#api-resource-id').val(resource.resource_id);
    $('#api-resource-name').val(resource.name);
    $('#api-resource-description').val(resource.description || '');
    $('#api-resource-base-url').val(resource.base_url);
    $('#api-resource-auth-type').val(resource.auth_type || 'none').trigger('change');
    $('#api-resource-token').val(resource.auth_token || '');
    $('#api-resource-username').val(resource.auth_username || '');
    $('#api-resource-password').val(resource.auth_password || '');

    if (resource.custom_headers) {
        $('#api-resource-custom-headers').val(JSON.stringify(resource.custom_headers, null, 2));
    }

    const modal = new bootstrap.Modal(document.getElementById('apiResourceModal'));
    modal.show();
}

// Save API resource
function saveApiResource() {
    const resourceId = $('#api-resource-id').val();
    const name = $('#api-resource-name').val().trim();
    const description = $('#api-resource-description').val().trim();
    const baseUrl = $('#api-resource-base-url').val().trim();
    const authType = $('#api-resource-auth-type').val();
    const token = $('#api-resource-token').val().trim();
    const username = $('#api-resource-username').val().trim();
    const password = $('#api-resource-password').val().trim();
    const customHeadersStr = $('#api-resource-custom-headers').val().trim();

    if (!name || !baseUrl) {
        alert('Name and Base URL are required');
        return;
    }

    let customHeaders = null;
    if (authType === 'custom' && customHeadersStr) {
        try {
            customHeaders = JSON.parse(customHeadersStr);
        } catch (e) {
            alert('Invalid JSON in Custom Headers field');
            return;
        }
    }

    const data = {
        name,
        description,
        base_url: baseUrl,
        auth_type: authType,
        auth_token: token,
        auth_username: username,
        auth_password: password,
        custom_headers: customHeaders
    };

    const isEdit = resourceId !== '';
    const url = isEdit ? `/api/api-resources/${resourceId}` : '/api/api-resources';
    const method = isEdit ? 'PUT' : 'POST';

    $.ajax({
        url,
        method,
        contentType: 'application/json',
        data: JSON.stringify(data)
    })
    .done(function(response) {
        if (response.success) {
            bootstrap.Modal.getInstance(document.getElementById('apiResourceModal')).hide();
            loadApiResources();
            showNotification(`API Resource ${isEdit ? 'updated' : 'created'} successfully`, 'success');
        } else {
            alert('Error: ' + response.error);
        }
    })
    .fail(function(xhr) {
        alert('Failed to save API resource: ' + (xhr.responseJSON?.error || 'Unknown error'));
    });
}

// Delete API resource
function deleteApiResource(resourceId) {
    const resource = apiResourcesData.find(r => r.resource_id === resourceId);
    if (!resource) return;

    if (!confirm(`Delete API Resource "${resource.name}"?`)) {
        return;
    }

    $.ajax({
        url: `/api/api-resources/${resourceId}`,
        method: 'DELETE'
    })
    .done(function(response) {
        if (response.success) {
            loadApiResources();
            showNotification('API Resource deleted successfully', 'success');
        } else {
            alert('Error: ' + response.error);
        }
    })
    .fail(function(xhr) {
        alert('Failed to delete API resource: ' + (xhr.responseJSON?.error || 'Unknown error'));
    });
}

// Handle auth type change to show/hide relevant fields
function handleAuthTypeChange() {
    const authType = $('#api-resource-auth-type').val();

    // Hide all auth fields
    $('.auth-field').hide();

    // Show relevant fields based on auth type
    if (authType === 'bearer' || authType === 'api_key') {
        $('.auth-bearer').show();
    } else if (authType === 'basic') {
        $('.auth-basic').show();
    } else if (authType === 'custom') {
        $('.auth-custom').show();
    }
}

// Initialize API resources when settings page loads
$(document).ready(function() {
    // Check if we're on the settings page
    if ($('#api-resources-list').length > 0) {
        // Load API resources
        loadApiResources();

        // Event handlers
        $('#add-api-resource-btn').click(openAddApiResourceModal);
        $('#save-api-resource-btn').click(saveApiResource);
        $('#api-resource-auth-type').change(handleAuthTypeChange);
    }

    // Load menu items for reordering
    if ($('#menu-items-list').length > 0) {
        loadMenuItems();
        $('#save-menu-order-btn').click(saveMenuOrder);
    }

    // Load custom step types
    if ($('#custom-step-types-list').length > 0) {
        loadCustomStepTypes();
    }
});


// ============================================================================
// Menu Items Management
// ============================================================================

let menuItemsData = [];

function loadMenuItems() {
    $.ajax({
        url: '/api/menu-items',
        method: 'GET',
        success: function(response) {
            if (response.success) {
                menuItemsData = response.menu_items;
                renderMenuItems();
                initializeSortable();
            } else {
                showAlert('danger', 'Failed to load menu items: ' + (response.error || 'Unknown error'));
            }
        },
        error: function(xhr, status, error) {
            showAlert('danger', 'Error loading menu items: ' + error);
        }
    });
}

function renderMenuItems() {
    const $list = $('#menu-items-list');
    $list.empty();

    menuItemsData.forEach((item, index) => {
        const isVisible = item.visible === 1 || item.visible === true;
        const visibilityIcon = isVisible ? 'eye' : 'eye-slash';
        const visibilityClass = isVisible ? 'text-primary' : 'text-muted';

        const $item = $(`
            <div class="list-group-item d-flex align-items-center" data-item-id="${item.item_id}" data-order="${index}">
                <span class="drag-handle me-2" style="cursor: move;">
                    <i class="fas fa-grip-vertical text-muted"></i>
                </span>
                <i class="fas fa-${item.icon} me-2"></i>
                <span class="flex-grow-1">${item.label}</span>
                <button class="btn btn-sm btn-link toggle-visibility ${visibilityClass}" data-item-id="${item.item_id}">
                    <i class="fas fa-${visibilityIcon}"></i>
                </button>
            </div>
        `);

        $list.append($item);
    });

    // Attach visibility toggle handlers
    $('.toggle-visibility').click(function() {
        const itemId = $(this).data('item-id');
        toggleMenuItemVisibility(itemId);
    });
}

function initializeSortable() {
    const el = document.getElementById('menu-items-list');
    if (el && typeof Sortable !== 'undefined') {
        new Sortable(el, {
            animation: 150,
            handle: '.drag-handle',
            onEnd: function(evt) {
                // Update order in memory
                updateMenuItemsOrder();
            }
        });
    } else {
        // Fallback: manual drag if Sortable.js not available
        console.warn('Sortable.js not loaded, drag-and-drop disabled');
    }
}

function updateMenuItemsOrder() {
    const $items = $('#menu-items-list .list-group-item');
    $items.each(function(index) {
        const itemId = $(this).data('item-id');
        const item = menuItemsData.find(i => i.item_id === itemId);
        if (item) {
            item.order_index = index;
        }
    });
}

function toggleMenuItemVisibility(itemId) {
    const item = menuItemsData.find(i => i.item_id === itemId);
    if (item) {
        item.visible = item.visible === 1 ? 0 : 1;
        renderMenuItems();
        // Re-initialize sortable after re-render
        initializeSortable();
    }
}

function saveMenuOrder() {
    // Update order based on current DOM order
    updateMenuItemsOrder();

    console.log('Saving menu order:', menuItemsData);

    $.ajax({
        url: '/api/menu-items',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({
            menu_items: menuItemsData
        }),
        success: function(response) {
            console.log('Save response:', response);
            if (response.success) {
                showAlert('success', 'Menu order saved successfully! Refresh the page to see changes.');
            } else {
                showAlert('danger', 'Failed to save menu order: ' + (response.error || 'Unknown error'));
            }
        },
        error: function(xhr, status, error) {
            console.error('Save error:', xhr.responseText);
            let errorMsg = 'Error saving menu order: ';
            try {
                const response = JSON.parse(xhr.responseText);
                errorMsg += response.error || error;
            } catch (e) {
                errorMsg += error || 'Unknown error';
            }
            showAlert('danger', errorMsg);
        }
    });
}

// ============================================================
// Custom Step Types Management
// ============================================================

function loadCustomStepTypes() {
    $.get('/api/custom-step-types', function(data) {
        const $list = $('#custom-step-types-list');
        $list.empty();

        if (data.success && data.step_types && data.step_types.length > 0) {
            data.step_types.forEach(function(stepType) {
                const $item = $(`
                    <div class="d-flex justify-content-between align-items-center border-bottom py-2">
                        <div class="flex-grow-1">
                            <strong><i class="fas fa-${stepType.icon}"></i> ${stepType.name}</strong>
                            <br>
                            <small class="text-muted">${stepType.description || 'No description'}</small>
                            <br>
                            <span class="badge bg-secondary">${stepType.category || 'Custom'}</span>
                            <span class="badge ${stepType.custom_type === 'python' ? 'bg-info' : 'bg-success'}">${stepType.custom_type === 'python' ? 'Python' : 'Webhook'}</span>
                        </div>
                        <div>
                            <button class="btn btn-sm btn-outline-primary edit-custom-step-type" data-id="${stepType.step_type_id}">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-sm btn-outline-danger delete-custom-step-type" data-id="${stepType.step_type_id}">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                `);
                $list.append($item);
            });
        } else {
            $list.html('<div class="text-center text-muted py-3">No custom step types yet. Click "Create Step Type" to add one.</div>');
        }
    }).fail(function() {
        $('#custom-step-types-list').html('<div class="alert alert-danger">Error loading custom step types</div>');
    });
}

// Add custom step type button
$('#add-custom-step-type-btn').click(function() {
    $('#customStepTypeModalTitle').text('Create Custom Step Type');
    $('#custom-step-type-form')[0].reset();
    $('#custom-step-type-id-input').val('');
    $('#step-type-id').prop('disabled', false);
    $('.implementation-section').hide();
    $('#customStepTypeModal').modal('show');
});

// Implementation type selector
$('#step-type-implementation').change(function() {
    const implType = $(this).val();
    $('.implementation-section').hide();

    if (implType === 'python') {
        $('#python-implementation').show();
    } else if (implType === 'webhook') {
        $('#webhook-implementation').show();
    }
});

// Save custom step type
$('#save-custom-step-type-btn').click(function() {
    const isEdit = $('#custom-step-type-id-input').val().length > 0;
    const stepTypeId = isEdit ? $('#custom-step-type-id-input').val() : $('#step-type-id').val();
    const implType = $('#step-type-implementation').val();

    // Validation
    if (!stepTypeId || !$('#step-type-name').val() || !implType) {
        showAlert('danger', 'Please fill in all required fields');
        return;
    }

    // Validate step type ID format (only for new step types)
    if (!isEdit && !/^[a-z_]+$/.test(stepTypeId)) {
        showAlert('danger', 'Step Type ID must contain only lowercase letters and underscores');
        return;
    }

    // Build request data
    const data = {
        step_type_id: stepTypeId,
        name: $('#step-type-name').val(),
        description: $('#step-type-description').val(),
        category: $('#step-type-category').val(),
        icon: $('#step-type-icon').val() || 'cog',
        custom_type: implType
    };

    // Add implementation-specific fields
    if (implType === 'python') {
        data.custom_code = $('#step-type-python-code').val();
        if (!data.custom_code) {
            showAlert('danger', 'Python code is required');
            return;
        }
    } else if (implType === 'webhook') {
        data.custom_webhook_url = $('#step-type-webhook-url').val();
        data.custom_webhook_method = $('#step-type-webhook-method').val();

        if (!data.custom_webhook_url) {
            showAlert('danger', 'Webhook URL is required');
            return;
        }

        const headers = $('#step-type-webhook-headers').val();
        if (headers) {
            try {
                data.custom_webhook_headers = JSON.parse(headers);
            } catch (e) {
                showAlert('danger', 'Invalid JSON in webhook headers');
                return;
            }
        }
    }

    // Parse parameters schema
    const paramsText = $('#step-type-parameters').val();
    if (paramsText) {
        try {
            data.parameters_schema = JSON.parse(paramsText);
        } catch (e) {
            showAlert('danger', 'Invalid JSON in parameters schema');
            return;
        }
    }

    // Send request
    const url = isEdit ? `/api/custom-step-types/${stepTypeId}` : '/api/custom-step-types';
    const method = isEdit ? 'PUT' : 'POST';

    $.ajax({
        url: url,
        method: method,
        contentType: 'application/json',
        data: JSON.stringify(data),
        success: function(response) {
            if (response.success) {
                showAlert('success', `Custom step type ${isEdit ? 'updated' : 'created'} successfully`);
                $('#customStepTypeModal').modal('hide');
                loadCustomStepTypes();
            } else {
                showAlert('danger', response.error || 'Failed to save step type');
            }
        },
        error: function(xhr) {
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'Unknown error';
            showAlert('danger', 'Error: ' + error);
        }
    });
});

// Edit custom step type
$(document).on('click', '.edit-custom-step-type', function() {
    const stepTypeId = $(this).data('id');

    $.get(`/api/custom-step-types/${stepTypeId}`, function(data) {
        if (data.success) {
            const stepType = data.step_type;

            $('#customStepTypeModalTitle').text('Edit Custom Step Type');
            $('#custom-step-type-id-input').val(stepType.step_type_id);
            $('#step-type-id').val(stepType.step_type_id).prop('disabled', true);
            $('#step-type-name').val(stepType.name);
            $('#step-type-description').val(stepType.description || '');
            $('#step-type-category').val(stepType.category || 'Custom');
            $('#step-type-icon').val(stepType.icon || 'cog');
            $('#step-type-implementation').val(stepType.custom_type).trigger('change');

            if (stepType.custom_type === 'python') {
                $('#step-type-python-code').val(stepType.custom_code || '');
            } else if (stepType.custom_type === 'webhook') {
                $('#step-type-webhook-url').val(stepType.custom_webhook_url || '');
                $('#step-type-webhook-method').val(stepType.custom_webhook_method || 'POST');
                if (stepType.custom_webhook_headers) {
                    $('#step-type-webhook-headers').val(JSON.stringify(stepType.custom_webhook_headers, null, 2));
                }
            }

            if (stepType.parameters_schema) {
                $('#step-type-parameters').val(JSON.stringify(stepType.parameters_schema, null, 2));
            }

            $('#customStepTypeModal').modal('show');
        }
    }).fail(function() {
        showAlert('danger', 'Error loading step type');
    });
});

// Delete custom step type
$(document).on('click', '.delete-custom-step-type', function() {
    const stepTypeId = $(this).data('id');

    if (!confirm('Are you sure you want to delete this custom step type? This cannot be undone.')) {
        return;
    }

    $.ajax({
        url: `/api/custom-step-types/${stepTypeId}`,
        method: 'DELETE',
        success: function(response) {
            if (response.success) {
                showAlert('success', 'Custom step type deleted successfully');
                loadCustomStepTypes();
            } else {
                showAlert('danger', response.error || 'Failed to delete step type');
            }
        },
        error: function(xhr) {
            const error = xhr.responseJSON ? xhr.responseJSON.error : 'Unknown error';
            showAlert('danger', 'Error: ' + error);
        }
    });
});
