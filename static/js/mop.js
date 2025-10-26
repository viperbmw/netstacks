// MOP (Method of Procedures) JavaScript

let currentMopId = null;
let currentSteps = [];
let allDevices = [];
let allTemplates = [];
let allApiResources = [];
let allServiceStacks = [];
let currentMopDevices = []; // Track current MOP's devices
let newMopDevices = []; // Track new MOP's devices during creation

// Initialize on page load
document.addEventListener('DOMContentLoaded', function() {
    loadMops();
    loadDevices();
    loadTemplates();
    loadApiResources();
    loadServiceStacks();

    // Event listeners
    document.getElementById('create-mop-btn').addEventListener('click', showCreateMopModal);
    document.getElementById('confirm-create-mop-btn').addEventListener('click', createMop);
    document.getElementById('save-mop-btn').addEventListener('click', saveMop);
    document.getElementById('delete-mop-btn').addEventListener('click', deleteMop);
    document.getElementById('execute-mop-btn').addEventListener('click', executeMop);
    document.getElementById('add-step-btn').addEventListener('click', showAddStepModal);
    document.getElementById('confirm-add-step-btn').addEventListener('click', saveStep);
    document.getElementById('step-type').addEventListener('change', handleStepTypeChange);
    document.getElementById('copy-result-btn').addEventListener('click', copyResultToClipboard);
    document.getElementById('api-resource').addEventListener('change', handleApiResourceChange);
    document.getElementById('api-method').addEventListener('change', handleApiMethodChange);
    document.getElementById('mop-test-api-btn').addEventListener('click', testMopApiConfig);
    document.getElementById('confirm-execute-mop-btn').addEventListener('click', confirmExecuteMop);
    document.getElementById('device-mode-select').addEventListener('change', handleDeviceModeChange);
    document.getElementById('device-mode-variable').addEventListener('change', handleDeviceModeChange);
    document.getElementById('add-mop-device-btn').addEventListener('click', addMopDevice);
    document.getElementById('add-new-mop-device-btn').addEventListener('click', addNewMopDevice);
    document.getElementById('template-select').addEventListener('change', handleTemplateSelect);
});

// Load all MOPs
async function loadMops() {
    try {
        const response = await fetch('/api/mop');
        const data = await response.json();

        if (data.success) {
            displayMopsList(data.mops);
        } else {
            showError('Failed to load procedures: ' + data.error);
        }
    } catch (error) {
        showError('Error loading procedures: ' + error.message);
    }
}

// Display MOPs list
function displayMopsList(mops) {
    const container = document.getElementById('mops-list');

    if (mops.length === 0) {
        container.innerHTML = '<div class="p-3 text-center text-muted">No procedures created yet</div>';
        return;
    }

    container.innerHTML = mops.map(mop => `
        <a href="#" class="list-group-item list-group-item-action ${mop.mop_id === currentMopId ? 'active' : ''}"
           data-mop-id="${mop.mop_id}">
            <div class="d-flex justify-content-between align-items-center">
                <div>
                    <h6 class="mb-0">${escapeHtml(mop.name)}</h6>
                    ${mop.description ? `<small class="text-muted">${escapeHtml(mop.description)}</small>` : ''}
                </div>
                <i class="fas fa-chevron-right"></i>
            </div>
        </a>
    `).join('');

    // Add click handlers
    container.querySelectorAll('.list-group-item').forEach(item => {
        item.addEventListener('click', (e) => {
            e.preventDefault();
            const mopId = item.getAttribute('data-mop-id');
            loadMop(mopId);
        });
    });
}

// Load a specific MOP
async function loadMop(mopId) {
    try {
        const response = await fetch(`/api/mop/${mopId}`);
        const data = await response.json();

        if (data.success) {
            currentMopId = mopId;
            currentSteps = data.mop.steps || [];
            displayMop(data.mop);

            // Check if there's a running execution for this MOP
            checkForRunningExecution(mopId);
        } else {
            showError('Failed to load procedure: ' + data.error);
        }
    } catch (error) {
        showError('Error loading procedure: ' + error.message);
    }
}

// Display MOP in editor
function displayMop(mop) {
    document.getElementById('no-mop-selected').style.display = 'none';
    document.getElementById('mop-editor').style.display = 'block';

    document.getElementById('current-mop-id').value = mop.mop_id;
    document.getElementById('mop-name').value = mop.name;
    document.getElementById('mop-description').value = mop.description || '';
    document.getElementById('mop-title').textContent = mop.name;

    // Load MOP devices
    currentMopDevices = mop.devices || [];
    updateMopDevicesList();

    // Update step device options to only show MOP devices
    updateStepDeviceOptions(currentMopDevices);

    displaySteps(mop.steps || []);

    // Clear any previous execution status (will be restored if there's a running execution)
    clearExecutionStatus();

    // Show detected variables
    updateVariablesDisplay();

    // Update active state in list
    document.querySelectorAll('#mops-list .list-group-item').forEach(item => {
        item.classList.toggle('active', item.getAttribute('data-mop-id') === mop.mop_id);
    });
}

// Clear execution status from UI
function clearExecutionStatus() {
    // Hide execution status div
    const statusDiv = document.getElementById('execution-status');
    statusDiv.style.display = 'none';
    statusDiv.innerHTML = '';

    // Clear all step status badges and borders
    const stepCards = document.querySelectorAll('.step-card');
    stepCards.forEach(card => {
        const statusSpan = card.querySelector('.step-execution-status');
        const actionButtons = card.querySelector('.step-action-buttons');

        // Clear status badge
        if (statusSpan) {
            statusSpan.innerHTML = '';
        }

        // Show action buttons
        if (actionButtons) {
            actionButtons.style.display = '';
        }

        // Remove borders
        card.classList.remove('border-success', 'border-danger', 'border-info', 'border-2');

        // Remove any device results
        const deviceResults = card.querySelector('.device-results');
        if (deviceResults) {
            deviceResults.remove();
        }
    });
}

// Update the variables display for the current MOP
function updateVariablesDisplay() {
    const variables = detectMopVariables();
    const infoDiv = document.getElementById('mop-variables-info');
    const listSpan = document.getElementById('mop-variables-list');

    if (variables.size > 0) {
        listSpan.innerHTML = Array.from(variables).map(varName =>
            `<code class="bg-white px-2 py-1 me-1 rounded">{{${escapeHtml(varName)}}}</code>`
        ).join('');
        infoDiv.style.display = 'block';
    } else {
        infoDiv.style.display = 'none';
    }
}

// Display steps
function displaySteps(steps) {
    const container = document.getElementById('steps-container');

    if (steps.length === 0) {
        container.innerHTML = '<div class="text-center text-muted py-3">No steps added yet. Click "Add Step" to begin.</div>';
        return;
    }

    container.innerHTML = steps.map((step, index) => {
        const icon = getStepIcon(step.step_type);
        const badge = step.enabled ? '<span class="badge bg-success">Enabled</span>' : '<span class="badge bg-secondary">Disabled</span>';

        return `
            <div class="card mb-2 step-card" data-step-id="${step.step_id}" data-step-order="${step.step_order}" data-step-index="${index}">
                <div class="card-body">
                    <div class="d-flex justify-content-between align-items-start">
                        <div class="flex-grow-1">
                            <h6 class="mb-1">
                                <span class="badge bg-primary me-2">${index + 1}</span>
                                <i class="fas ${icon} me-1 step-icon"></i>
                                ${escapeHtml(step.step_name)}
                                ${badge}
                                <span class="step-execution-status"></span>
                            </h6>
                            <small class="text-muted">
                                Type: ${step.step_type}
                                ${step.devices && step.devices.length > 0 ? `| Devices: ${step.devices.join(', ')}` : ''}
                            </small>
                        </div>
                        <div class="btn-group btn-group-sm step-action-buttons">
                            <button class="btn btn-outline-secondary" onclick="moveStepUp(${index})" ${index === 0 ? 'disabled' : ''}>
                                <i class="fas fa-arrow-up"></i>
                            </button>
                            <button class="btn btn-outline-secondary" onclick="moveStepDown(${index})" ${index === steps.length - 1 ? 'disabled' : ''}>
                                <i class="fas fa-arrow-down"></i>
                            </button>
                            <button class="btn btn-outline-primary" onclick="editStep('${step.step_id}')">
                                <i class="fas fa-edit"></i>
                            </button>
                            <button class="btn btn-outline-danger" onclick="deleteStep('${step.step_id}')">
                                <i class="fas fa-trash"></i>
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }).join('');
}

// Get icon for step type
function getStepIcon(stepType) {
    const icons = {
        'getconfig': 'fa-download',
        'setconfig': 'fa-upload',
        'template': 'fa-file-code',
        'deploy_stack': 'fa-layer-group',
        'api': 'fa-plug',
        'code': 'fa-code'
    };
    return icons[stepType] || 'fa-question';
}

// Show create MOP modal
function showCreateMopModal() {
    document.getElementById('new-mop-name').value = '';
    document.getElementById('new-mop-description').value = '';
    newMopDevices = []; // Reset devices
    updateNewMopDevicesList();
    const modal = new bootstrap.Modal(document.getElementById('createMopModal'));
    modal.show();
}

// Create new MOP
async function createMop() {
    const name = document.getElementById('new-mop-name').value;
    const description = document.getElementById('new-mop-description').value;

    if (!name) {
        showError('Procedure name is required');
        return;
    }

    try {
        const response = await fetch('/api/mop', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, description, devices: newMopDevices})
        });

        const data = await response.json();

        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('createMopModal')).hide();
            await loadMops();
            await loadMop(data.mop_id);
            showSuccess('Procedure created successfully');
        } else {
            showError('Failed to create procedure: ' + data.error);
        }
    } catch (error) {
        showError('Error creating procedure: ' + error.message);
    }
}

// Save MOP
async function saveMop() {
    const mopId = document.getElementById('current-mop-id').value;
    const name = document.getElementById('mop-name').value;
    const description = document.getElementById('mop-description').value;

    if (!name) {
        showError('Procedure name is required');
        return;
    }

    // Show saving indicator
    const saveBtn = document.getElementById('save-mop-btn');
    const originalBtnHtml = saveBtn.innerHTML;
    saveBtn.disabled = true;
    saveBtn.innerHTML = '<span class="spinner-border spinner-border-sm me-1"></span> Saving...';

    try {
        const response = await fetch(`/api/mop/${mopId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({name, description, devices: currentMopDevices})
        });

        const data = await response.json();

        if (data.success) {
            await loadMops();
            document.getElementById('mop-title').textContent = name;
            // Update step device selects to reflect new MOP devices
            updateStepDeviceOptions(currentMopDevices);

            // Show success feedback
            saveBtn.innerHTML = '<i class="fas fa-check"></i> Saved!';
            saveBtn.classList.remove('btn-warning');
            saveBtn.classList.add('btn-success');

            setTimeout(() => {
                saveBtn.innerHTML = originalBtnHtml;
                saveBtn.classList.remove('btn-success');
                saveBtn.classList.add('btn-warning');
                saveBtn.disabled = false;
            }, 2000);
        } else {
            saveBtn.innerHTML = originalBtnHtml;
            saveBtn.disabled = false;
            showError('Failed to save procedure: ' + data.error);
        }
    } catch (error) {
        saveBtn.innerHTML = originalBtnHtml;
        saveBtn.disabled = false;
        showError('Error saving procedure: ' + error.message);
    }
}

// Delete MOP
async function deleteMop() {
    if (!confirm('Are you sure you want to delete this procedure? This action cannot be undone.')) {
        return;
    }

    const mopId = document.getElementById('current-mop-id').value;

    try {
        const response = await fetch(`/api/mop/${mopId}`, {method: 'DELETE'});
        const data = await response.json();

        if (data.success) {
            currentMopId = null;
            currentSteps = [];
            document.getElementById('mop-editor').style.display = 'none';
            document.getElementById('no-mop-selected').style.display = 'block';
            await loadMops();
            showSuccess('Procedure deleted successfully');
        } else {
            showError('Failed to delete procedure: ' + data.error);
        }
    } catch (error) {
        showError('Error deleting procedure: ' + error.message);
    }
}

// Execute MOP - Show variables modal first
function executeMop() {
    const mopName = document.getElementById('mop-name').value;

    // Detect variables in all steps
    const variables = detectMopVariables();

    const modal = new bootstrap.Modal(document.getElementById('executeMopModal'));
    const container = document.getElementById('execution-variables-container');
    const noVarsMessage = document.getElementById('no-variables-message');

    if (variables.size > 0) {
        // Show input fields for each variable
        container.style.display = 'block';
        noVarsMessage.style.display = 'none';

        // Find where each variable is used
        const variableUsage = {};
        currentSteps.forEach(step => {
            const stepInfo = `${step.step_name} (${step.step_type})`;

            // Check devices
            if (step.devices) {
                step.devices.forEach(device => {
                    const matches = device.match(/\{\{(\w+)\}\}/g);
                    if (matches) {
                        matches.forEach(match => {
                            const varName = match.replace(/\{\{|\}\}/g, '');
                            if (!variableUsage[varName]) variableUsage[varName] = [];
                            variableUsage[varName].push(`${stepInfo} - devices`);
                        });
                    }
                });
            }

            // Check config
            const configStr = JSON.stringify(step.config || {});
            const matches = configStr.match(/\{\{(\w+)\}\}/g);
            if (matches) {
                matches.forEach(match => {
                    const varName = match.replace(/\{\{|\}\}/g, '');
                    if (!variableUsage[varName]) variableUsage[varName] = [];
                    if (!variableUsage[varName].includes(`${stepInfo}`)) {
                        variableUsage[varName].push(`${stepInfo} - config`);
                    }
                });
            }
        });

        container.innerHTML = Array.from(variables).map(varName => {
            const usage = variableUsage[varName] || [];
            const usageText = usage.length > 0 ? `Used in: ${usage.slice(0, 2).join(', ')}${usage.length > 2 ? '...' : ''}` : '';

            return `
                <div class="mb-3">
                    <label class="form-label">
                        <strong>${escapeHtml(varName)}</strong>
                        ${varName.toLowerCase().includes('device') ? '<span class="badge bg-info ms-1">Devices</span>' : ''}
                    </label>
                    ${varName.toLowerCase().includes('device') ? `
                        <select class="form-select" multiple size="6" id="exec-var-${escapeHtml(varName)}" data-var-name="${escapeHtml(varName)}">
                            ${allDevices.map(device => `<option value="${device.name}">${device.name}</option>`).join('')}
                        </select>
                        <small class="form-text text-muted">Hold Ctrl/Cmd to select multiple devices</small>
                    ` : `
                        <input type="text" class="form-control" id="exec-var-${escapeHtml(varName)}"
                               data-var-name="${escapeHtml(varName)}"
                               placeholder="Enter value for ${escapeHtml(varName)}">
                    `}
                    ${usageText ? `<small class="form-text text-muted d-block mt-1"><i class="fas fa-info-circle"></i> ${usageText}</small>` : ''}
                </div>
            `;
        }).join('');
    } else {
        // No variables, show message
        container.style.display = 'none';
        noVarsMessage.style.display = 'block';
    }

    modal.show();
}

// Detect variables in MOP steps (looking for {{variable}})
function detectMopVariables() {
    const variables = new Set();
    const varPattern = /\{\{(\w+)\}\}/g;

    currentSteps.forEach(step => {
        // Check devices array
        if (step.devices && Array.isArray(step.devices)) {
            step.devices.forEach(device => {
                let match;
                while ((match = varPattern.exec(device)) !== null) {
                    variables.add(match[1]);
                }
                varPattern.lastIndex = 0;
            });
        }

        // Check config fields
        if (step.config) {
            const configStr = JSON.stringify(step.config);
            let match;
            while ((match = varPattern.exec(configStr)) !== null) {
                variables.add(match[1]);
            }
        }
    });

    return variables;
}

// Confirm and execute MOP with variables
async function confirmExecuteMop() {
    const mopId = document.getElementById('current-mop-id').value;
    const mopName = document.getElementById('mop-name').value;

    // Collect variable values
    const variables = {};
    document.querySelectorAll('[data-var-name]').forEach(input => {
        const varName = input.getAttribute('data-var-name');
        if (input.tagName === 'SELECT' && input.multiple) {
            // Multiple select for devices
            const selected = Array.from(input.selectedOptions).map(opt => opt.value);
            variables[varName] = selected;
        } else {
            // Text input
            variables[varName] = input.value.trim();
        }
    });

    // Close modal
    bootstrap.Modal.getInstance(document.getElementById('executeMopModal')).hide();

    // Show execution status
    const statusDiv = document.getElementById('execution-status');
    statusDiv.style.display = 'block';
    statusDiv.innerHTML = `
        <div class="alert alert-info">
            <i class="fas fa-spinner fa-spin"></i> Starting procedure execution...
        </div>
    `;
    document.getElementById('execution-steps-results').innerHTML = '';

    try {
        // Start execution (returns immediately with execution_id)
        const response = await fetch(`/api/mop/${mopId}/execute`, {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ variables: variables })
        });

        const data = await response.json();

        if (data.success && data.execution_id) {
            // Start polling for progress
            pollExecutionProgress(data.execution_id);
        } else {
            document.getElementById('execution-status').innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle"></i> Failed to start execution: ${data.error}
                </div>
            `;
        }
    } catch (error) {
        document.getElementById('execution-status').innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-exclamation-triangle"></i> Error starting execution: ${error.message}
            </div>
        `;
    }
}

// Check for running execution when MOP is loaded
async function checkForRunningExecution(mopId) {
    try {
        const response = await fetch(`/api/mop/${mopId}/current-execution`);
        const data = await response.json();

        if (data.success && data.has_running) {
            const execution = data.execution;
            console.log('Found running execution:', execution.execution_id);

            // Show alert to user
            const statusDiv = document.getElementById('execution-status');
            statusDiv.style.display = 'block';
            statusDiv.innerHTML = `
                <div class="alert alert-info">
                    <i class="fas fa-info-circle"></i> <strong>Execution In Progress</strong><br>
                    This MOP is currently executing. Resuming progress tracking...
                </div>
            `;

            // Resume polling for this execution
            pollExecutionProgress(execution.execution_id);
        }
    } catch (error) {
        console.error('Error checking for running execution:', error);
    }
}

// Poll execution progress
async function pollExecutionProgress(executionId) {
    const pollInterval = 1000; // Poll every second
    let currentStep = -1;

    const poll = async () => {
        try {
            const response = await fetch(`/api/mop/executions/${executionId}`);
            const data = await response.json();

            if (!data.success) {
                throw new Error(data.error);
            }

            const execution = data.execution;

            // Update status message
            if (execution.status === 'running' && execution.current_step !== undefined) {
                if (execution.current_step !== currentStep) {
                    currentStep = execution.current_step;
                    document.getElementById('execution-status').innerHTML = `
                        <div class="alert alert-info">
                            <i class="fas fa-spinner fa-spin"></i> Executing step ${currentStep + 1}...
                        </div>
                    `;

                    // Update step display to show progress
                    updateStepProgress(execution.results || [], currentStep);
                }
            } else if (execution.status === 'completed') {
                // Execution completed - show final results
                displayExecutionResults(execution.results || [], execution.context || {});
                return; // Stop polling
            } else if (execution.status === 'failed') {
                document.getElementById('execution-status').innerHTML = `
                    <div class="alert alert-danger">
                        <i class="fas fa-exclamation-triangle"></i> Execution failed: ${execution.error || 'Unknown error'}
                    </div>
                `;
                return; // Stop polling
            }

            // Continue polling
            setTimeout(poll, pollInterval);

        } catch (error) {
            console.error('Error polling execution:', error);
            document.getElementById('execution-status').innerHTML = `
                <div class="alert alert-danger">
                    <i class="fas fa-exclamation-triangle"></i> Error checking execution status: ${error.message}
                </div>
            `;
        }
    };

    // Start polling
    poll();
}

// Update step progress display during execution
function updateStepProgress(results, currentStep) {
    // Update existing step cards with execution status
    const stepCards = document.querySelectorAll('.step-card');

    stepCards.forEach((card, index) => {
        const statusSpan = card.querySelector('.step-execution-status');
        const actionButtons = card.querySelector('.step-action-buttons');

        // Hide action buttons during execution
        if (actionButtons) {
            actionButtons.style.display = 'none';
        }

        // Reset card styling
        card.classList.remove('border-success', 'border-info', 'border-2');

        if (index < currentStep) {
            // Completed step - green border and checkmark
            card.classList.add('border-success', 'border-2');
            statusSpan.innerHTML = '<span class="badge bg-success ms-2"><i class="fas fa-check"></i> Completed</span>';
        } else if (index === currentStep) {
            // Currently executing - blue border and spinner
            card.classList.add('border-info', 'border-2');
            statusSpan.innerHTML = '<span class="badge bg-info ms-2"><i class="fas fa-spinner fa-spin"></i> Executing</span>';
        } else {
            // Not started yet - gray badge
            statusSpan.innerHTML = '<span class="badge bg-secondary ms-2"><i class="fas fa-clock"></i> Pending</span>';
        }
    });
}

// Display execution results
function displayExecutionResults(results, context) {
    const statusDiv = document.getElementById('execution-status');

    const hasErrors = results.some(r => r.status === 'error');
    const allSuccess = results.every(r => r.status === 'success' || r.status === 'skipped');

    // Show completion status in the status div
    statusDiv.style.display = 'block';
    if (allSuccess) {
        statusDiv.innerHTML = `
            <div class="alert alert-success">
                <i class="fas fa-check-circle"></i> Procedure completed successfully
            </div>
        `;
    } else if (hasErrors) {
        statusDiv.innerHTML = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i> Procedure completed with errors
            </div>
        `;
    }

    // Auto-hide the status message after 5 seconds
    setTimeout(() => {
        statusDiv.style.display = 'none';
        statusDiv.innerHTML = '';
    }, 5000);

    // Update existing step cards with final results
    const stepCards = document.querySelectorAll('.step-card');
    stepCards.forEach((card, index) => {
        const statusSpan = card.querySelector('.step-execution-status');
        const actionButtons = card.querySelector('.step-action-buttons');
        const cardBody = card.querySelector('.card-body');

        // Show action buttons again
        if (actionButtons) {
            actionButtons.style.display = '';
        }

        // Reset styling
        card.classList.remove('border-success', 'border-danger', 'border-info', 'border-2');
        cardBody.classList.remove('bg-light');

        // Get result for this step
        const result = results[index];
        if (result) {
            if (result.status === 'success') {
                card.classList.add('border-success', 'border-2');
                statusSpan.innerHTML = '<span class="badge bg-success ms-2"><i class="fas fa-check"></i> Completed</span>';
            } else if (result.status === 'error') {
                card.classList.add('border-danger', 'border-2');
                statusSpan.innerHTML = '<span class="badge bg-danger ms-2"><i class="fas fa-exclamation-circle"></i> Error</span>';
            } else if (result.status === 'skipped') {
                statusSpan.innerHTML = '<span class="badge bg-secondary ms-2"><i class="fas fa-minus-circle"></i> Skipped</span>';
            }

            // Add device results display if available
            if (result.data && Array.isArray(result.data) && result.data.length > 0) {
                let deviceResultsHtml = '<div class="mt-2 pt-2 border-top"><small>';
                result.data.forEach(deviceResult => {
                    deviceResultsHtml += `
                        <div class="mb-1">
                            <strong>${deviceResult.device || 'Unknown'}:</strong>
                            <span class="badge bg-${deviceResult.status === 'success' ? 'success' : 'danger'}">${deviceResult.status || 'pending'}</span>
                            ${deviceResult.task_id ? `
                                <button class="btn btn-xs btn-outline-primary ms-1" onclick="viewStepResult('${deviceResult.task_id}', '${escapeHtml(result.step_name)}', '${deviceResult.device || 'Unknown'}')">
                                    <i class="fas fa-eye"></i> View
                                </button>
                            ` : ''}
                        </div>
                    `;
                });
                deviceResultsHtml += '</small></div>';

                // Insert after the h6
                const h6 = cardBody.querySelector('h6');
                if (h6 && !cardBody.querySelector('.device-results')) {
                    const div = document.createElement('div');
                    div.className = 'device-results';
                    div.innerHTML = deviceResultsHtml;
                    h6.insertAdjacentElement('afterend', div);
                }
            }
        }
    });

    // Hide the separate execution-steps-results section since we're using the main step cards
    const stepsDiv = document.getElementById('execution-steps-results');
    stepsDiv.innerHTML = '';
}

// View step result in modal
async function viewStepResult(taskId, stepName, deviceName) {
    try {
        const response = await fetch(`/api/task/${taskId}/result`);
        const data = await response.json();

        if (data.success || data.status === 'success') {
            const taskData = data.data || data;
            const taskResult = taskData.task_result || taskData.result || 'No output available';

            document.getElementById('execution-detail-content').textContent =
                `Step: ${stepName}\nDevice: ${deviceName}\nTask ID: ${taskId}\n\n${JSON.stringify(taskResult, null, 2)}`;

            const modal = new bootstrap.Modal(document.getElementById('executionDetailsModal'));
            modal.show();
        } else {
            showError('Failed to fetch task result');
        }
    } catch (error) {
        showError('Error fetching task result: ' + error.message);
    }
}

// View task results (legacy - redirects to monitor)
function viewTaskResults(taskId) {
    window.location.href = `/monitor?task=${taskId}`;
}

// Load devices
async function loadDevices() {
    try {
        // Get filters from settings if available
        let filters = [];
        try {
            const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
            filters = settings.netbox_filters || [];
        } catch (e) {
            console.error('Error reading filters from settings:', e);
        }

        const response = await fetch('/api/devices', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({ filters: filters })
        });
        const data = await response.json();

        if (data.success) {
            allDevices = data.devices || [];
            // Update device select in add step modal
            updateDeviceSelect();
        } else {
            console.error('Error loading devices:', data.error);
        }
    } catch (error) {
        console.error('Error loading devices:', error);
    }
}

// Update device select
function updateDeviceSelect() {
    const select = document.getElementById('step-devices');
    select.innerHTML = allDevices.map(device =>
        `<option value="${device.name}">${device.name} (${device.device_type || 'Unknown'})</option>`
    ).join('');

    // Also update MOP-level device dropdowns
    const mopDeviceDropdown = document.getElementById('mop-device-dropdown');
    const newMopDeviceDropdown = document.getElementById('new-mop-device-dropdown');

    const deviceOptions = allDevices.map(device =>
        `<option value="${device.name}">${device.name} (${device.device_type || 'Unknown'})</option>`
    ).join('');

    if (mopDeviceDropdown) {
        mopDeviceDropdown.innerHTML = '<option value="">Select a device...</option>' + deviceOptions;
    }
    if (newMopDeviceDropdown) {
        newMopDeviceDropdown.innerHTML = '<option value="">Select a device...</option>' + deviceOptions;
    }
}

// Add device to current MOP
function addMopDevice() {
    const dropdown = document.getElementById('mop-device-dropdown');
    const selectedDevice = dropdown.value;

    if (!selectedDevice) {
        return;
    }

    if (currentMopDevices.includes(selectedDevice)) {
        showError('Device already added');
        return;
    }

    currentMopDevices.push(selectedDevice);
    updateMopDevicesList();
    dropdown.value = ''; // Reset dropdown
}

// Add device to new MOP during creation
function addNewMopDevice() {
    const dropdown = document.getElementById('new-mop-device-dropdown');
    const selectedDevice = dropdown.value;

    if (!selectedDevice) {
        return;
    }

    if (newMopDevices.includes(selectedDevice)) {
        showError('Device already added');
        return;
    }

    newMopDevices.push(selectedDevice);
    updateNewMopDevicesList();
    dropdown.value = ''; // Reset dropdown
}

// Remove device from current MOP
function removeMopDevice(deviceName) {
    currentMopDevices = currentMopDevices.filter(d => d !== deviceName);
    updateMopDevicesList();
}

// Remove device from new MOP
function removeNewMopDevice(deviceName) {
    newMopDevices = newMopDevices.filter(d => d !== deviceName);
    updateNewMopDevicesList();
}

// Update the MOP devices list display
function updateMopDevicesList() {
    const listDiv = document.getElementById('mop-devices-list');

    if (currentMopDevices.length === 0) {
        listDiv.innerHTML = '<small class="text-muted">No devices added yet</small>';
    } else {
        listDiv.innerHTML = currentMopDevices.map(device => `
            <span class="badge bg-primary me-1 mb-1">
                ${escapeHtml(device)}
                <button type="button" class="btn-close btn-close-white ms-1" style="font-size: 0.65rem;" onclick="removeMopDevice('${escapeHtml(device)}')" aria-label="Remove"></button>
            </span>
        `).join('');
    }

    // Update step device options
    updateStepDeviceOptions(currentMopDevices);
}

// Update the new MOP devices list display
function updateNewMopDevicesList() {
    const listDiv = document.getElementById('new-mop-devices-list');

    if (newMopDevices.length === 0) {
        listDiv.innerHTML = '<small class="text-muted">No devices added yet</small>';
    } else {
        listDiv.innerHTML = newMopDevices.map(device => `
            <span class="badge bg-primary me-1 mb-1">
                ${escapeHtml(device)}
                <button type="button" class="btn-close btn-close-white ms-1" style="font-size: 0.65rem;" onclick="removeNewMopDevice('${escapeHtml(device)}')" aria-label="Remove"></button>
            </span>
        `).join('');
    }
}

// Update step device options to filter by MOP devices
function updateStepDeviceOptions(mopDevices) {
    const stepDevicesSelect = document.getElementById('step-devices');

    if (!mopDevices || mopDevices.length === 0) {
        // No MOP devices selected, show all devices
        stepDevicesSelect.innerHTML = allDevices.map(device =>
            `<option value="${device.name}">${device.name} (${device.device_type || 'Unknown'})</option>`
        ).join('');
    } else {
        // Filter to only show MOP devices
        const filteredDevices = allDevices.filter(device => mopDevices.includes(device.name));
        stepDevicesSelect.innerHTML = filteredDevices.map(device =>
            `<option value="${device.name}">${device.name} (${device.device_type || 'Unknown'})</option>`
        ).join('');
    }
}

// Load templates
async function loadTemplates() {
    try {
        const response = await fetch('/api/templates');
        const data = await response.json();
        allTemplates = data.templates || [];

        // Update template select
        const select = document.getElementById('template-select');
        select.innerHTML = '<option value="">Select template...</option>' +
            allTemplates.map(template =>
                `<option value="${template.name}">${template.name}</option>`
            ).join('');
    } catch (error) {
        console.error('Error loading templates:', error);
    }
}

// Load API resources
async function loadApiResources() {
    try {
        const response = await fetch('/api/api-resources');
        const data = await response.json();
        allApiResources = data.resources || [];

        // Update API resource select
        const select = document.getElementById('api-resource');
        select.innerHTML = '<option value="">Select API resource...</option>' +
            allApiResources.map(resource =>
                `<option value="${resource.resource_id}">${resource.name}</option>`
            ).join('');
    } catch (error) {
        console.error('Error loading API resources:', error);
    }
}

// Load service stacks
async function loadServiceStacks() {
    try {
        const response = await fetch('/api/service-stacks');
        const data = await response.json();
        allServiceStacks = data.stacks || [];

        // Update stack select
        const select = document.getElementById('stack-select');
        select.innerHTML = '<option value="">Select service stack...</option>' +
            allServiceStacks.map(stack => {
                // Build the display text with state
                let displayText = stack.name;
                if (stack.description) {
                    displayText += ' - ' + stack.description;
                }

                // Add state annotation
                if (stack.state) {
                    displayText += ` (${stack.state})`;
                } else if (stack.has_pending_changes) {
                    displayText += ' (pending)';
                }

                return `<option value="${stack.stack_id}">${displayText}</option>`;
            }).join('');
    } catch (error) {
        console.error('Error loading service stacks:', error);
    }
}

// Show add step modal
function showAddStepModal() {
    if (!currentMopId) {
        showError('Please save the procedure first');
        return;
    }

    // Reset form
    document.getElementById('edit-step-id').value = '';
    document.getElementById('edit-step-order').value = '';
    document.getElementById('step-name').value = '';
    document.getElementById('step-type').value = '';
    document.getElementById('step-devices').selectedIndex = -1;
    document.getElementById('step-devices-variable').value = '';

    // Reset to select mode
    document.getElementById('device-mode-select').checked = true;
    handleDeviceModeChange();

    // Hide all config sections
    document.getElementById('getconfig-config').style.display = 'none';
    document.getElementById('setconfig-config').style.display = 'none';
    document.getElementById('template-config').style.display = 'none';
    document.getElementById('api-config').style.display = 'none';
    document.getElementById('code-config').style.display = 'none';

    // Reset API fields
    document.getElementById('api-resource').value = '';
    document.getElementById('api-endpoint').value = '';
    document.getElementById('api-method').value = 'GET';
    document.getElementById('api-body').value = '';
    document.getElementById('api-jsonpath').value = '';
    document.getElementById('api-resource-info').style.display = 'none';

    // Reset Code fields
    document.getElementById('code-script').value = '';

    document.getElementById('step-modal-title').textContent = 'Add Step';
    document.getElementById('step-confirm-text').textContent = 'Add Step';

    const modal = new bootstrap.Modal(document.getElementById('addStepModal'));
    modal.show();
}

// Edit step
async function editStep(stepId) {
    const step = currentSteps.find(s => s.step_id === stepId);
    if (!step) return;

    document.getElementById('edit-step-id').value = step.step_id;
    document.getElementById('edit-step-order').value = step.step_order;
    document.getElementById('step-name').value = step.step_name;
    document.getElementById('step-type').value = step.step_type;

    // Select devices or set variable
    if (step.devices && step.devices.length === 1 && step.devices[0].includes('{{')) {
        // Variable mode
        document.getElementById('device-mode-variable').checked = true;
        document.getElementById('step-devices-variable').value = step.devices[0];
        handleDeviceModeChange();
    } else {
        // Select mode
        document.getElementById('device-mode-select').checked = true;
        const deviceSelect = document.getElementById('step-devices');
        Array.from(deviceSelect.options).forEach(option => {
            option.selected = step.devices.includes(option.value);
        });
        handleDeviceModeChange();
    }

    // Load step-specific config
    handleStepTypeChange();

    if (step.step_type === 'getconfig') {
        document.getElementById('getconfig-command').value = step.config.command || '';
        document.getElementById('getconfig-cache').checked = step.config.enable_cache || false;
        document.getElementById('getconfig-textfsm').checked = step.config.use_textfsm || false;
    } else if (step.step_type === 'setconfig') {
        document.getElementById('setconfig-commands').value = step.config.commands || '';
        document.getElementById('setconfig-dryrun').checked = step.config.dry_run || false;
    } else if (step.step_type === 'template') {
        document.getElementById('template-select').value = step.config.template || '';
        document.getElementById('template-dryrun').checked = step.config.dry_run || false;
        handleTemplateSelect(step.config.variables || {}); // Load template variables with saved values
    } else if (step.step_type === 'deploy_stack') {
        document.getElementById('stack-select').value = step.config.stack_id || '';
    } else if (step.step_type === 'api') {
        document.getElementById('api-resource').value = step.config.resource_id || '';
        document.getElementById('api-endpoint').value = step.config.endpoint || '';
        document.getElementById('api-method').value = step.config.method || 'GET';
        document.getElementById('api-body').value = step.config.body || '';
        document.getElementById('api-jsonpath').value = step.config.jsonpath || '';
        handleApiResourceChange();
        handleApiMethodChange();
    } else if (step.step_type === 'code') {
        document.getElementById('code-script').value = step.config.script || '';
    }

    document.getElementById('step-modal-title').textContent = 'Edit Step';
    document.getElementById('step-confirm-text').textContent = 'Save Changes';

    const modal = new bootstrap.Modal(document.getElementById('addStepModal'));
    modal.show();
}

// Handle step type change
function handleStepTypeChange() {
    const stepType = document.getElementById('step-type').value;

    document.getElementById('getconfig-config').style.display = stepType === 'getconfig' ? 'block' : 'none';
    document.getElementById('setconfig-config').style.display = stepType === 'setconfig' ? 'block' : 'none';
    document.getElementById('template-config').style.display = stepType === 'template' ? 'block' : 'none';
    document.getElementById('deploy-stack-config').style.display = stepType === 'deploy_stack' ? 'block' : 'none';
    document.getElementById('api-config').style.display = stepType === 'api' ? 'block' : 'none';
    document.getElementById('code-config').style.display = stepType === 'code' ? 'block' : 'none';

    const deviceSelect = document.getElementById('step-devices').closest('.mb-3');

    // API, Code, and Deploy Stack steps don't need devices (deploy_stack has devices defined in the stack itself)
    if (stepType === 'api' || stepType === 'code' || stepType === 'deploy_stack') {
        deviceSelect.style.display = 'none';
        document.getElementById('step-devices').removeAttribute('required');
    } else {
        deviceSelect.style.display = 'block';
        document.getElementById('step-devices').setAttribute('required', 'required');
    }
}

// Handle API resource change
function handleApiResourceChange() {
    const resourceId = document.getElementById('api-resource').value;
    const infoDiv = document.getElementById('api-resource-info');

    if (!resourceId) {
        infoDiv.style.display = 'none';
        return;
    }

    // Find the selected resource
    const resource = allApiResources.find(r => r.resource_id === resourceId);
    if (resource) {
        document.getElementById('resource-base-url').textContent = resource.base_url || 'N/A';
        document.getElementById('resource-auth-type').textContent = resource.auth_type || 'None';
        infoDiv.style.display = 'block';
    } else {
        infoDiv.style.display = 'none';
    }
}

// Handle API method change
function handleApiMethodChange() {
    const method = document.getElementById('api-method').value;
    const bodyGroup = document.getElementById('api-body-group');

    // Show body field for POST, PUT, PATCH
    if (method === 'POST' || method === 'PUT' || method === 'PATCH') {
        bodyGroup.style.display = 'block';
    } else {
        bodyGroup.style.display = 'none';
    }
}

// Handle template selection and extract variables
async function handleTemplateSelect(savedVariables = {}) {
    const templateName = document.getElementById('template-select').value;
    const container = document.getElementById('template-vars-container');

    if (!templateName) {
        container.innerHTML = '';
        return;
    }

    try {
        // Remove .j2 extension if present
        const cleanName = templateName.endsWith('.j2') ? templateName.slice(0, -3) : templateName;

        // Fetch template variables
        const response = await fetch(`/api/templates/${cleanName}/variables`);
        const data = await response.json();

        if (data.success && data.variables && data.variables.length > 0) {
            // Display variables with input fields
            let html = '<div class="alert alert-info small mb-3">';
            html += '<i class="fas fa-info-circle"></i> <strong>Template Variables Detected:</strong>';
            html += '<p class="mb-2 mt-2">Provide values for these variables. You can use MOP variable syntax like <code>{{mop.devices.DEVICE_NAME.step0.output}}</code></p>';
            html += '</div>';

            html += '<div class="mb-3">';
            html += '<label class="form-label"><strong>Template Variables:</strong></label>';
            data.variables.forEach(varName => {
                const savedValue = savedVariables[varName] || '';
                html += `
                    <div class="mb-2">
                        <label for="template-var-${varName}" class="form-label small">{{${varName}}}</label>
                        <input type="text" class="form-control form-control-sm template-variable-input"
                               id="template-var-${varName}"
                               data-var-name="${varName}"
                               value="${savedValue}"
                               placeholder="Enter value or use {{mop.devices.DEVICE_NAME.attribute}}">
                    </div>
                `;
            });
            html += '</div>';

            container.innerHTML = html;
        } else {
            container.innerHTML = '<div class="alert alert-secondary small">No variables detected in this template.</div>';
        }
    } catch (error) {
        console.error('Error fetching template variables:', error);
        container.innerHTML = '<div class="alert alert-warning small">Failed to load template variables.</div>';
    }
}

// Handle device mode change
function handleDeviceModeChange() {
    const isVariableMode = document.getElementById('device-mode-variable').checked;
    const deviceSelect = document.getElementById('step-devices');
    const deviceVariable = document.getElementById('step-devices-variable');
    const selectHelp = document.getElementById('device-select-help');
    const variableHelp = document.getElementById('device-variable-help');

    if (isVariableMode) {
        deviceSelect.style.display = 'none';
        deviceVariable.style.display = 'block';
        selectHelp.style.display = 'none';
        variableHelp.style.display = 'block';
        deviceSelect.removeAttribute('required');
        deviceVariable.setAttribute('required', 'required');
    } else {
        deviceSelect.style.display = 'block';
        deviceVariable.style.display = 'none';
        selectHelp.style.display = 'block';
        variableHelp.style.display = 'none';
        deviceSelect.setAttribute('required', 'required');
        deviceVariable.removeAttribute('required');
    }
}

// Save step
async function saveStep() {
    const stepId = document.getElementById('edit-step-id').value;
    const stepName = document.getElementById('step-name').value;
    const stepType = document.getElementById('step-type').value;

    // Get devices based on mode (select or variable)
    let devices = [];
    if (stepType !== 'api' && stepType !== 'code' && stepType !== 'deploy_stack') {
        const isVariableMode = document.getElementById('device-mode-variable').checked;
        if (isVariableMode) {
            // Variable mode - get the variable string
            const variableInput = document.getElementById('step-devices-variable').value.trim();
            devices = [variableInput]; // Store as single-item array
        } else {
            // Select mode - get selected devices
            const deviceSelect = document.getElementById('step-devices');
            devices = Array.from(deviceSelect.selectedOptions).map(opt => opt.value);
        }
    }

    // Validate required fields based on step type
    if (!stepName || !stepType) {
        showError('Please fill in all required fields');
        return;
    }
    if (stepType !== 'api' && stepType !== 'code' && stepType !== 'deploy_stack' && devices.length === 0) {
        showError('Please select at least one device');
        return;
    }

    // Build config based on step type
    let config = {};
    if (stepType === 'getconfig') {
        config = {
            command: document.getElementById('getconfig-command').value,
            enable_cache: document.getElementById('getconfig-cache').checked,
            use_textfsm: document.getElementById('getconfig-textfsm').checked
        };
    } else if (stepType === 'setconfig') {
        config = {
            commands: document.getElementById('setconfig-commands').value,
            dry_run: document.getElementById('setconfig-dryrun').checked
        };
    } else if (stepType === 'template') {
        // Collect template variable values
        const variables = {};
        document.querySelectorAll('.template-variable-input').forEach(input => {
            const varName = input.getAttribute('data-var-name');
            const value = input.value.trim();
            if (value) {
                variables[varName] = value;
            }
        });

        config = {
            template: document.getElementById('template-select').value,
            dry_run: document.getElementById('template-dryrun').checked,
            variables: variables
        };
    } else if (stepType === 'deploy_stack') {
        config = {
            stack_id: document.getElementById('stack-select').value
        };
        if (!config.stack_id) {
            showError('Service stack selection is required');
            return;
        }
    } else if (stepType === 'api') {
        config = {
            resource_id: document.getElementById('api-resource').value,
            endpoint: document.getElementById('api-endpoint').value,
            method: document.getElementById('api-method').value,
            body: document.getElementById('api-body').value,
            jsonpath: document.getElementById('api-jsonpath').value
        };
        if (!config.resource_id || !config.endpoint) {
            showError('API resource and endpoint are required');
            return;
        }
    } else if (stepType === 'code') {
        config = {
            script: document.getElementById('code-script').value
        };
        if (!config.script) {
            showError('Python code is required');
            return;
        }
    }

    try {
        let response;
        if (stepId) {
            // Update existing step
            response = await fetch(`/api/mop/${currentMopId}/steps/${stepId}`, {
                method: 'PUT',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({step_name: stepName, step_type: stepType, devices, config})
            });
        } else {
            // Create new step
            const stepOrder = currentSteps.length;
            response = await fetch(`/api/mop/${currentMopId}/steps`, {
                method: 'POST',
                headers: {'Content-Type': 'application/json'},
                body: JSON.stringify({step_order: stepOrder, step_type: stepType, step_name: stepName, devices, config})
            });
        }

        const data = await response.json();

        if (data.success) {
            bootstrap.Modal.getInstance(document.getElementById('addStepModal')).hide();
            await loadMop(currentMopId);
            updateVariablesDisplay(); // Update variables display after step change
            showSuccess('Step saved successfully');
        } else {
            showError('Failed to save step: ' + data.error);
        }
    } catch (error) {
        showError('Error saving step: ' + error.message);
    }
}

// Delete step
async function deleteStep(stepId) {
    if (!confirm('Are you sure you want to delete this step?')) {
        return;
    }

    try {
        const response = await fetch(`/api/mop/${currentMopId}/steps/${stepId}`, {method: 'DELETE'});
        const data = await response.json();

        if (data.success) {
            await loadMop(currentMopId);
            updateVariablesDisplay(); // Update variables display after step change
            showSuccess('Step deleted successfully');
        } else {
            showError('Failed to delete step: ' + data.error);
        }
    } catch (error) {
        showError('Error deleting step: ' + error.message);
    }
}

// Move step up
async function moveStepUp(index) {
    if (index === 0) return;

    const step = currentSteps[index];
    const prevStep = currentSteps[index - 1];

    // Swap orders
    await updateStepOrder(step.step_id, prevStep.step_order);
    await updateStepOrder(prevStep.step_id, step.step_order);

    await loadMop(currentMopId);
}

// Move step down
async function moveStepDown(index) {
    if (index === currentSteps.length - 1) return;

    const step = currentSteps[index];
    const nextStep = currentSteps[index + 1];

    // Swap orders
    await updateStepOrder(step.step_id, nextStep.step_order);
    await updateStepOrder(nextStep.step_id, step.step_order);

    await loadMop(currentMopId);
}

// Update step order
async function updateStepOrder(stepId, newOrder) {
    try {
        await fetch(`/api/mop/${currentMopId}/steps/${stepId}`, {
            method: 'PUT',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({step_order: newOrder})
        });
    } catch (error) {
        console.error('Error updating step order:', error);
    }
}

// Test API Configuration
async function testMopApiConfig() {
    const resourceId = document.getElementById('api-resource').value;
    const endpoint = document.getElementById('api-endpoint').value.trim();
    const method = document.getElementById('api-method').value;
    const body = document.getElementById('api-body').value.trim();
    const jsonPath = document.getElementById('api-jsonpath').value.trim();

    const resultDiv = document.getElementById('mop-api-test-result');

    // Validate
    if (!resourceId) {
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i> Please select an API resource first
            </div>
        `;
        return;
    }

    const resource = allApiResources.find(r => r.resource_id === resourceId);
    if (!resource) {
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = `
            <div class="alert alert-danger">
                <i class="fas fa-times-circle"></i> Selected resource not found. Please refresh the page.
            </div>
        `;
        return;
    }

    if (!endpoint) {
        resultDiv.style.display = 'block';
        resultDiv.innerHTML = `
            <div class="alert alert-warning">
                <i class="fas fa-exclamation-triangle"></i> Please enter an endpoint path
            </div>
        `;
        return;
    }

    // Detect variables in endpoint and body (looking for {{variable}})
    const varPattern = /\{\{(\w+)\}\}/g;
    const variables = new Set();

    let match;
    while ((match = varPattern.exec(endpoint)) !== null) {
        variables.add(match[1]);
    }
    if (body) {
        varPattern.lastIndex = 0; // Reset regex
        while ((match = varPattern.exec(body)) !== null) {
            variables.add(match[1]);
        }
    }

    // If variables detected, show input fields
    const testVarsContainer = document.getElementById('mop-test-variables-container');
    const testVarsInputs = document.getElementById('mop-test-variables-inputs');

    if (variables.size > 0) {
        testVarsContainer.style.display = 'block';
        testVarsInputs.innerHTML = Array.from(variables).map(varName => `
            <div class="mb-2">
                <label class="form-label small mb-1">${escapeHtml(varName)}</label>
                <input type="text" class="form-control form-control-sm mop-test-var-input"
                       data-var-name="${escapeHtml(varName)}"
                       placeholder="Enter test value for ${escapeHtml(varName)}">
            </div>
        `).join('');
    } else {
        testVarsContainer.style.display = 'none';
    }

    // Collect test variable values
    const testVariables = {};
    document.querySelectorAll('.mop-test-var-input').forEach(input => {
        const varName = input.getAttribute('data-var-name');
        const varValue = input.value.trim();
        if (varValue) {
            testVariables[varName] = varValue;
        }
    });

    // Show loading state
    const btn = document.getElementById('mop-test-api-btn');
    const originalBtnHtml = btn.innerHTML;
    btn.disabled = true;
    btn.innerHTML = '<span class="spinner-border spinner-border-sm"></span> Testing...';

    // Build display URL and body with test values
    let displayUrl = resource.base_url.replace(/\/$/, '') + (endpoint.startsWith('/') ? endpoint : '/' + endpoint);
    let displayBody = body;

    Object.keys(testVariables).forEach(varName => {
        const regex = new RegExp(`\\{\\{${varName}\\}\\}`, 'g');
        displayUrl = displayUrl.replace(regex, testVariables[varName]);
        if (displayBody) {
            displayBody = displayBody.replace(regex, testVariables[varName]);
        }
    });

    // Show debug info
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
    resultDiv.style.display = 'block';
    resultDiv.innerHTML = debugInfo;

    try {
        // Make the request via backend proxy
        const response = await fetch('/api/proxy-api-call', {
            method: 'POST',
            headers: {'Content-Type': 'application/json'},
            body: JSON.stringify({
                resource_id: resourceId,
                endpoint: endpoint,
                method: method,
                body: displayBody || undefined,
                variables: testVariables
            })
        });

        const data = await response.json();

        if (!data.success) {
            throw new Error(data.error || 'Unknown error');
        }

        const responseData = data.data;
        const status = data.status;
        const statusText = data.statusText;

        // Extract value using JSONPath if provided
        let extractedValue = null;
        let extractError = null;

        if (jsonPath) {
            try {
                extractedValue = extractJsonPath(responseData, jsonPath);
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
                        <div class="mt-1">
                            <small>${extractError || 'Path not found in response'}</small>
                        </div>
                    </div>
                `;
            }
        }

        // Show full response
        html += `
            <div class="card">
                <div class="card-header py-2">
                    <small><strong>Full Response</strong></small>
                </div>
                <div class="card-body py-2">
                    <pre class="mb-0" style="max-height: 300px; overflow-y: auto; font-size: 0.8rem;">${escapeHtml(JSON.stringify(responseData, null, 2))}</pre>
                </div>
            </div>
        `;

        resultDiv.innerHTML = html;

    } catch (error) {
        resultDiv.innerHTML = `
            <div class="alert alert-danger">
                <strong><i class="fas fa-times-circle"></i> API Call Failed</strong>
                <div class="mt-2">
                    <small>${escapeHtml(error.message)}</small>
                </div>
            </div>
        `;
    } finally {
        btn.disabled = false;
        btn.innerHTML = originalBtnHtml;
    }
}

// Extract value from JSON using JSONPath
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

// Utility functions
function escapeHtml(text) {
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showError(message) {
    // You can implement a toast notification here
    alert('Error: ' + message);
}

function showSuccess(message) {
    // You can implement a toast notification here
    console.log('Success:', message);
}

function copyResultToClipboard() {
    const content = document.getElementById('execution-detail-content').textContent;
    navigator.clipboard.writeText(content).then(function() {
        const btn = document.getElementById('copy-result-btn');
        const originalText = btn.innerHTML;
        btn.innerHTML = '<i class="fas fa-check"></i> Copied!';
        setTimeout(function() {
            btn.innerHTML = originalText;
        }, 2000);
    }).catch(function(err) {
        showError('Failed to copy to clipboard: ' + err);
    });
}
