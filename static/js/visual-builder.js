/**
 * Visual MOP Builder with intelligent step type loading
 */

let visualSteps = [];
let stepTypesMetadata = [];
let selectedDevices = [];

// Load step types and devices on page load
$(document).ready(function() {
    loadStepTypes();
    loadDevices();
});

// Load step types from introspection API
function loadStepTypes() {
    $.get('/api/step-types-introspect')
        .done(function(data) {
            if (data.success) {
                stepTypesMetadata = data.step_types;
                populateStepTypeDropdown();
            } else {
                console.error('Failed to load step types:', data.error);
            }
        })
        .fail(function() {
            console.error('Failed to load step types from API');
        });
}

// Load devices from Netstacker API
function loadDevices() {
    console.log('Loading devices from API...');
    const $select = $('#mop-device-dropdown');

    // Get filters from settings (like deploy.js does)
    let filters = [];
    try {
        const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
        filters = settings.netbox_filters || [];
    } catch (e) {
        console.error('Error reading filters from settings:', e);
    }

    // Use POST with filters to get cached/filtered devices
    $.ajax({
        url: '/api/devices',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify({ filters: filters }),
        timeout: 30000 // 30 second timeout
    })
    .done(function(response) {
        console.log('Devices API response:', response);
        $select.empty();
        $select.append('<option value="">-- Select Device --</option>');

        if (response.success && response.devices && response.devices.length > 0) {
            console.log('Found ' + response.devices.length + ' devices');
            response.devices.forEach(function(device) {
                const deviceName = device.name || device.display || device.hostname || 'Unknown';
                $select.append(`<option value="${deviceName}">${deviceName}</option>`);
            });
        } else {
            console.warn('No devices found in response');
            $select.append('<option value="">No devices available</option>');
        }
    })
    .fail(function(xhr, status, error) {
        console.error('Failed to load devices from API:', status, error);
        console.error('Response:', xhr.responseText);
        $select.empty();
        $select.append('<option value="">Error loading devices</option>');
    });
}

// Add device to selected list
$('#add-device-btn').click(function() {
    const device = $('#mop-device-dropdown').val();

    if (!device) {
        alert('Please select a device first.');
        return;
    }

    if (selectedDevices.includes(device)) {
        alert('This device has already been added.');
        return;
    }

    selectedDevices.push(device);
    renderSelectedDevices();

    // Reset dropdown
    $('#mop-device-dropdown').val('');
});

// Render selected devices list
function renderSelectedDevices() {
    const $list = $('#selected-devices-list');
    $list.empty();

    if (selectedDevices.length === 0) {
        $list.html(`
            <div class="text-muted text-center p-2">
                <small>No devices added yet</small>
            </div>
        `);
        return;
    }

    selectedDevices.forEach(function(device, index) {
        $list.append(`
            <div class="list-group-item d-flex justify-content-between align-items-center">
                <span><i class="fas fa-server text-success"></i> ${device}</span>
                <button class="btn btn-sm btn-danger remove-device-btn" data-index="${index}">
                    <i class="fas fa-times"></i>
                </button>
            </div>
        `);
    });

    // Bind remove button click handlers
    $('.remove-device-btn').click(function() {
        const index = $(this).data('index');
        selectedDevices.splice(index, 1);
        renderSelectedDevices();
    });
}

// Populate step type dropdown
function populateStepTypeDropdown() {
    const $select = $('#step-type');
    $select.empty();
    $select.append('<option value="">-- Select Type --</option>');

    stepTypesMetadata.forEach(function(stepType) {
        $select.append(`<option value="${stepType.id}">${stepType.name}</option>`);
    });
}

// When step type changes, show relevant parameter fields
$('#step-type').change(function() {
    const selectedType = $(this).val();
    renderParameterFields(selectedType);
});

// Render parameter fields based on selected step type
function renderParameterFields(stepTypeId) {
    const $container = $('#dynamic-params-container');
    $container.empty();

    if (!stepTypeId) {
        return;
    }

    const stepType = stepTypesMetadata.find(st => st.id === stepTypeId);
    if (!stepType || !stepType.parameters || stepType.parameters.length === 0) {
        $container.html('<p class="text-muted"><small>No additional parameters required</small></p>');
        return;
    }

    stepType.parameters.forEach(function(param) {
        const fieldHtml = renderParameterField(param);
        $container.append(fieldHtml);
    });
}

// Render individual parameter field
function renderParameterField(param) {
    const required = param.required ? 'required' : '';
    const label = param.description || param.name.replace('_', ' ').replace(/\b\w/g, l => l.toUpperCase());

    let inputHtml = '';

    switch (param.type) {
        case 'boolean':
            inputHtml = `
                <div class="form-check form-switch">
                    <input class="form-check-input step-param-field" type="checkbox"
                           id="param-${param.name}" data-param="${param.name}">
                    <label class="form-check-label" for="param-${param.name}">${label}</label>
                </div>
            `;
            break;

        case 'number':
            inputHtml = `
                <div class="mb-3">
                    <label for="param-${param.name}" class="form-label">${label}</label>
                    <input type="number" class="form-control step-param-field"
                           id="param-${param.name}" data-param="${param.name}" ${required}>
                </div>
            `;
            break;

        case 'array':
        case 'object':
            inputHtml = `
                <div class="mb-3">
                    <label for="param-${param.name}" class="form-label">${label}</label>
                    <textarea class="form-control font-monospace step-param-field"
                              id="param-${param.name}" data-param="${param.name}"
                              rows="3" ${required}></textarea>
                    <small class="text-muted">JSON format</small>
                </div>
            `;
            break;

        default: // string
            inputHtml = `
                <div class="mb-3">
                    <label for="param-${param.name}" class="form-label">${label}</label>
                    <input type="text" class="form-control step-param-field"
                           id="param-${param.name}" data-param="${param.name}" ${required}>
                </div>
            `;
    }

    return inputHtml;
}

// Auto-generate step ID from step name
$(document).on('input', '#step-name', function() {
    const stepName = $(this).val();
    // Convert to snake_case: lowercase, replace spaces/special chars with underscores
    const stepId = stepName
        .toLowerCase()
        .replace(/[^a-z0-9]+/g, '_')
        .replace(/^_+|_+$/g, ''); // Remove leading/trailing underscores
    $('#step-id').val(stepId);
});

// Add Step Button
$('#add-step-btn').click(function() {
    $('#step-form')[0].reset();
    $('#step-index').val('');
    $('#dynamic-params-container').empty();
    $('.modal-title').text('Add Step');
    $('#stepModal').modal('show');
});

// Save Step
$('#save-step-btn').click(function() {
    const stepIndex = $('#step-index').val();
    const stepType = $('#step-type').val();
    const stepName = $('#step-name').val();
    const stepId = $('#step-id').val();

    if (!stepName || !stepType) {
        alert('Please fill in required fields (Name, Type)');
        return;
    }

    if (!stepId) {
        alert('Invalid step name - could not generate ID');
        return;
    }

    // Collect dynamic parameters
    const params = {};
    $('.step-param-field').each(function() {
        const $field = $(this);
        const paramName = $field.data('param');
        let value;

        if ($field.attr('type') === 'checkbox') {
            value = $field.is(':checked');
        } else if ($field.attr('type') === 'number') {
            value = parseFloat($field.val()) || null;
        } else {
            value = $field.val();
        }

        if (value !== null && value !== '') {
            params[paramName] = value;
        }
    });

    const step = {
        name: $('#step-name').val(),
        id: $('#step-id').val(),
        type: stepType,
        params: params,
        on_success: $('#step-on-success').val(),
        on_failure: $('#step-on-failure').val()
    };

    if (stepIndex === '') {
        visualSteps.push(step);
    } else {
        visualSteps[parseInt(stepIndex)] = step;
    }

    renderVisualSteps();
    $('#stepModal').modal('hide');
});

// Render Visual Steps
function renderVisualSteps() {
    const $list = $('#visual-steps-list');
    $list.empty();

    if (visualSteps.length === 0) {
        $list.append('<div class="text-center text-muted p-3">No steps added yet. Click "Add Step" to begin.</div>');
        return;
    }

    visualSteps.forEach((step, index) => {
        const stepTypeMeta = stepTypesMetadata.find(st => st.id === step.type);
        const icon = stepTypeMeta ? stepTypeMeta.icon : 'cog';

        const $item = $(`
            <div class="list-group-item">
                <div class="d-flex justify-content-between align-items-center">
                    <div>
                        <i class="fas fa-${icon}"></i>
                        <strong>${escapeHtml(step.name)}</strong>
                        <span class="badge bg-secondary ms-2">${escapeHtml(step.type)}</span>
                        <br>
                        <small class="text-muted">ID: ${escapeHtml(step.id)}</small>
                    </div>
                    <div>
                        <button class="btn btn-sm btn-outline-primary edit-visual-step" data-index="${index}">
                            <i class="fas fa-edit"></i>
                        </button>
                        <button class="btn btn-sm btn-outline-danger delete-visual-step" data-index="${index}">
                            <i class="fas fa-trash"></i>
                        </button>
                    </div>
                </div>
            </div>
        `);
        $list.append($item);
    });

    // Edit step
    $('.edit-visual-step').click(function() {
        const index = $(this).data('index');
        const step = visualSteps[index];

        $('#step-index').val(index);
        $('#step-name').val(step.name);
        $('#step-id').val(step.id);
        $('#step-type').val(step.type);
        $('#step-on-success').val(step.on_success);
        $('#step-on-failure').val(step.on_failure);

        // Render parameter fields and populate them
        renderParameterFields(step.type);
        setTimeout(function() {
            // Populate parameter values
            Object.keys(step.params).forEach(function(key) {
                const $field = $(`#param-${key}`);
                if ($field.attr('type') === 'checkbox') {
                    $field.prop('checked', step.params[key]);
                } else {
                    $field.val(step.params[key]);
                }
            });
        }, 100);

        $('.modal-title').text('Edit Step');
        $('#stepModal').modal('show');
    });

    // Delete step
    $('.delete-visual-step').click(function() {
        const index = $(this).data('index');
        if (confirm('Delete this step?')) {
            visualSteps.splice(index, 1);
            renderVisualSteps();
        }
    });
}

// Generate YAML from Visual Steps
$('#generate-yaml-btn').click(function() {
    if (visualSteps.length === 0) {
        alert('No steps to generate. Add some steps first.');
        return;
    }

    const mopName = $('#mop-name').val() || 'Untitled MOP';
    const mopDesc = $('#mop-description').val() || 'No description';

    if (selectedDevices.length === 0) {
        alert('Please add at least one target device.');
        return;
    }

    let yaml = `name: "${mopName}"\n`;
    yaml += `description: "${mopDesc}"\n`;
    yaml += `devices:\n`;

    // Add selected devices
    selectedDevices.forEach(device => {
        yaml += `  - ${device}\n`;
    });
    yaml += `\n`;
    yaml += `steps:\n`;

    visualSteps.forEach(step => {
        yaml += `  - name: "${step.name}"\n`;
        yaml += `    id: ${step.id}\n`;
        yaml += `    type: ${step.type}\n`;

        // Add parameters
        Object.keys(step.params).forEach(key => {
            const value = step.params[key];
            if (typeof value === 'string') {
                yaml += `    ${key}: "${value}"\n`;
            } else if (typeof value === 'boolean') {
                yaml += `    ${key}: ${value}\n`;
            } else {
                yaml += `    ${key}: ${value}\n`;
            }
        });

        if (step.on_success) {
            yaml += `    on_success: ${step.on_success}\n`;
        }
        if (step.on_failure) {
            yaml += `    on_failure: ${step.on_failure}\n`;
        }
        yaml += '\n';
    });

    $('#mop-yaml').val(yaml);

    // Switch to YAML tab
    $('#yaml-tab').tab('show');

    alert('YAML generated! Review and edit if needed, then save.');
});

// Helper function
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

// Function to clear Visual Builder
function clearVisualBuilder() {
    visualSteps = [];
    selectedDevices = [];
    renderVisualSteps();
    renderSelectedDevices();
}

// Function to load YAML into Visual Builder
function loadYAMLIntoVisualBuilder(yamlText) {
    if (!yamlText || yamlText.trim() === '') {
        console.warn('No YAML to load');
        return false;
    }

    try {
        // Parse YAML
        const mopData = jsyaml.load(yamlText);
        
        if (!mopData || !mopData.steps) {
            alert('Invalid MOP YAML. Must contain a "steps" section.');
            return;
        }
        
        // Clear existing visual steps and devices
        visualSteps = [];
        selectedDevices = [];

        // Load devices if present in YAML
        if (mopData.devices && Array.isArray(mopData.devices)) {
            selectedDevices = mopData.devices.slice(); // Copy array
            renderSelectedDevices();
        }

        // Convert each step
        mopData.steps.forEach(function(step) {
            const visualStep = {
                name: step.name || 'Unnamed Step',
                id: step.id || step.name.toLowerCase().replace(/[^a-z0-9]+/g, '_').replace(/^_+|_+$/g, ''),
                type: step.type,
                params: {},
                on_success: step.on_success || '',
                on_failure: step.on_failure || ''
            };

            // Extract parameters (everything except known MOP fields)
            const knownFields = ['name', 'id', 'type', 'on_success', 'on_failure', 'devices'];
            Object.keys(step).forEach(function(key) {
                if (!knownFields.includes(key)) {
                    visualStep.params[key] = step[key];
                }
            });

            visualSteps.push(visualStep);
        });

        // Render the visual steps
        renderVisualSteps();
        return true;

    } catch (e) {
        console.error('Failed to parse YAML: ' + e.message);
        return false;
    }
}

// Load from YAML button handler
$('#load-from-yaml-btn').click(function() {
    const yamlText = $('#mop-yaml').val();

    if (!yamlText || yamlText.trim() === '') {
        alert('No YAML to load. Please enter YAML in the editor first.');
        return;
    }

    if (loadYAMLIntoVisualBuilder(yamlText)) {
        $('#visual-tab').tab('show');
        alert(`Loaded ${visualSteps.length} step(s) from YAML!`);
    } else {
        alert('Failed to parse YAML. Check console for details.');
    }
});
