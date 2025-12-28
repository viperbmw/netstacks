/**
 * MOPs Management UI
 * YAML-based mop engine interface
 */

let currentMOPId = null;
let mops = [];

// Example mop templates
const WORKFLOW_EXAMPLES = {
    maintenance: `name: "Maintenance Window - Deploy Customer VPN"
description: "Check prerequisites, deploy stack, send notifications"
devices:
  - router1.example.com
  - router2.example.com

steps:
  - name: "Verify BGP Neighbors"
    id: check_bgp
    type: check_bgp
    command: "show ip bgp summary"
    on_success: deploy_stack
    on_failure: send_failure_webhook

  - name: "Deploy Customer VPN Stack"
    id: deploy_stack
    type: deploy_stack
    stack_name: "customer-vpn-stack"
    on_success: verify_deployment
    on_failure: rollback

  - name: "Verify Deployment"
    id: verify_deployment
    type: check_interfaces
    command: "show ip interface brief"
    on_success: send_success_webhook
    on_failure: send_failure_webhook

  - name: "Rollback Stack"
    id: rollback
    type: deploy_stack
    stack_name: "rollback-stack"
    on_success: send_failure_webhook
    on_failure: send_failure_webhook

  - name: "Send Success Webhook"
    id: send_success_webhook
    type: webhook
    url: "https://hooks.slack.com/services/xxx"
    message: "Maintenance Complete - {{ mop_name }}"

  - name: "Send Failure Webhook"
    id: send_failure_webhook
    type: webhook
    url: "https://hooks.slack.com/services/xxx"
    message: "Maintenance Failed - {{ mop_name }}"`,

    simple: `name: "Simple BGP Check and Alert"
description: "Check BGP neighbors and send webhook if there's an issue"
devices:
  - router1.example.com
  - router2.example.com

steps:
  - name: "Check BGP Status"
    id: check_bgp
    type: check_bgp
    command: "show ip bgp summary"
    on_success: send_success
    on_failure: send_alert

  - name: "Send Success"
    id: send_success
    type: webhook
    url: "https://hooks.slack.com/services/xxx"
    message: "BGP Check Passed - All neighbors up"

  - name: "Send Alert"
    id: send_alert
    type: webhook
    url: "https://hooks.slack.com/services/xxx"
    message: "BGP Check FAILED - Neighbor count mismatch"`,

    custom: `name: "Interface Validation with Manual Approval"
description: "Check interfaces, wait for approval, then push config"
devices:
  - device1.example.com

steps:
  - name: "Get Interface Status"
    id: get_interfaces
    type: get_config
    command: "show ip interface brief"
    use_textfsm: true
    on_success: validate_interfaces
    on_failure: send_alert

  - name: "Validate Interface Output"
    id: validate_interfaces
    type: validate_config
    command: "show ip interface brief"
    on_success: manual_review
    on_failure: send_alert

  - name: "Manual Review Required"
    id: manual_review
    type: manual_approval
    prompt: "Please review interface status and approve to continue"
    instructions: "Verify all expected interfaces are up before proceeding with configuration changes"
    on_success: push_config
    on_failure: send_alert

  - name: "Push Configuration"
    id: push_config
    type: set_config
    config_lines:
      - "interface GigabitEthernet0/1"
      - "description Updated by MOP"
    on_success: send_success
    on_failure: send_alert

  - name: "Send Success"
    id: send_success
    type: webhook
    url: "https://hooks.slack.com/services/xxx"
    message: "Validation and Config Push Complete"

  - name: "Send Alert"
    id: send_alert
    type: webhook
    url: "https://hooks.slack.com/services/xxx"
    message: "MOP Failed - Check logs"`
};

$(document).ready(function() {
    loadMOPs();

    // Create new mop
    $('#create-mop-btn').click(function() {
        currentMOPId = null;
        $('#current-mop-id').val('');
        $('#mop-name').val('');
        $('#mop-description').val('');
        $('#mop-yaml').val('');
        $('#mop-executions-body').html('<tr><td colspan="4" class="text-center text-muted">No executions yet</td></tr>');

        // Clear Visual Builder
        if (typeof clearVisualBuilder === 'function') {
            clearVisualBuilder();
        }

        $('#no-mop-selected').hide();
        $('#mop-editor').show();
        $('#mop-title').text('New MOP');
        $('#delete-mop-btn').hide();
    });

    // Load example templates
    $('.load-example').click(function(e) {
        e.preventDefault();
        const exampleType = $(this).data('example');
        const yamlContent = WORKFLOW_EXAMPLES[exampleType];

        if (yamlContent) {
            currentMOPId = null;
            $('#current-mop-id').val('');

            // Parse YAML to get name
            const nameMatch = yamlContent.match(/name:\s*"([^"]+)"/);
            const descMatch = yamlContent.match(/description:\s*"([^"]+)"/);

            $('#mop-name').val(nameMatch ? nameMatch[1] : 'Example MOP');
            $('#mop-description').val(descMatch ? descMatch[1] : '');
            $('#mop-yaml').val(yamlContent);
            $('#mop-executions-body').html('<tr><td colspan="4" class="text-center text-muted">No executions yet</td></tr>');

            $('#no-mop-selected').hide();
            $('#mop-editor').show();
            $('#mop-title').text('Example: ' + (nameMatch ? nameMatch[1] : 'MOP'));
            $('#delete-mop-btn').hide();
        }
    });

    // Save mop
    $('#save-mop-btn').click(function() {
        saveMOP();
    });

    // Delete mop
    $('#delete-mop-btn').click(function() {
        if (confirm('Are you sure you want to delete this mop?')) {
            deleteMOP(currentMOPId);
        }
    });

    // Execute mop
    $('#execute-mop-btn').click(function() {
        if (!currentMOPId) {
            alert('Please save the mop first before executing');
            return;
        }
        executeMOP(currentMOPId);
    });

    // Validate YAML
    $('#validate-yaml-btn').click(function() {
        validateYAML();
    });
});

function loadMOPs() {
    $.get('/api/mops')
        .done(function(data) {
            if (data.success) {
                mops = data.mops;
                renderMOPsList();
            }
        })
        .fail(function() {
            $('#mops-list').html('<div class="p-3 text-danger">Error loading mops</div>');
        });
}

function renderMOPsList() {
    const container = $('#mops-list');
    container.empty();

    if (mops.length === 0) {
        container.html('<div class="p-3 text-muted text-center">No mops yet</div>');
        return;
    }

    mops.forEach(mop => {
        const item = $('<a>')
            .addClass('list-group-item list-group-item-action')
            .attr('href', '#')
            .data('mop-id', mop.mop_id)
            .html(`
                <div class="d-flex w-100 justify-content-between">
                    <h6 class="mb-1">${escapeHtml(mop.name)}</h6>
                    <small class="text-muted">${formatDate(mop.created_at)}</small>
                </div>
                ${mop.description ? `<p class="mb-1 small text-muted">${escapeHtml(mop.description)}</p>` : ''}
            `)
            .click(function(e) {
                e.preventDefault();
                loadMOP(mop.mop_id);
            });

        if (currentMOPId === mop.mop_id) {
            item.addClass('active');
        }

        container.append(item);
    });
}

function loadMOP(mopId) {
    $.get(`/api/mops/${mopId}`)
        .done(function(data) {
            if (data.success) {
                const mop = data.mop;
                currentMOPId = mopId;

                $('#current-mop-id').val(mopId);
                $('#mop-name').val(mop.name);
                $('#mop-description').val(mop.description || '');
                $('#mop-yaml').val(mop.yaml_content);

                $('#no-mop-selected').hide();
                $('#mop-editor').show();
                $('#mop-title').text(mop.name);
                $('#delete-mop-btn').show();

                // Load YAML into Visual Builder
                if (typeof loadYAMLIntoVisualBuilder === 'function') {
                    loadYAMLIntoVisualBuilder(mop.yaml_content);
                }

                // Load execution history
                loadMOPExecutions(mopId);

                // Update list highlighting
                renderMOPsList();
            }
        });
}

function saveMOP() {
    const name = $('#mop-name').val().trim();
    const description = $('#mop-description').val().trim();
    const yamlContent = $('#mop-yaml').val().trim();

    if (!name) {
        alert('Please enter a mop name');
        return;
    }

    if (!yamlContent) {
        alert('Please enter YAML mop definition');
        return;
    }

    const data = {
        name: name,
        description: description,
        yaml_content: yamlContent,
        devices: []  // Extracted from YAML
    };

    if (currentMOPId) {
        // Update existing
        $.ajax({
            url: `/api/mops/${currentMOPId}`,
            method: 'PUT',
            contentType: 'application/json',
            data: JSON.stringify(data)
        })
        .done(function() {
            showSuccess('MOP updated successfully');
            loadMOPs();
        })
        .fail(function(xhr) {
            showError('Error updating mop: ' + (xhr.responseJSON?.error || 'Unknown error'));
        });
    } else {
        // Create new
        $.ajax({
            url: '/api/mops',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(data)
        })
        .done(function(data) {
            if (data.success) {
                currentMOPId = data.mop_id;
                $('#current-mop-id').val(currentMOPId);
                $('#delete-mop-btn').show();
                showSuccess('MOP created successfully');
                loadMOPs();
            }
        })
        .fail(function(xhr) {
            showError('Error creating mop: ' + (xhr.responseJSON?.error || 'Unknown error'));
        });
    }
}

function deleteMOP(mopId) {
    $.ajax({
        url: `/api/mops/${mopId}`,
        method: 'DELETE'
    })
    .done(function() {
        showSuccess('MOP deleted');
        currentMOPId = null;
        $('#mop-editor').hide();
        $('#no-mop-selected').show();
        loadMOPs();
    })
    .fail(function(xhr) {
        showError('Error deleting mop: ' + (xhr.responseJSON?.error || 'Unknown error'));
    });
}

function executeMOP(mopId) {
    $('#execute-mop-btn').prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Executing...');

    $.ajax({
        url: `/api/mops/${mopId}/execute`,
        method: 'POST'
    })
    .done(function(data) {
        if (data.success) {
            showSuccess('MOP execution started');

            // Reload execution history after a short delay
            setTimeout(function() {
                loadMOPExecutions(mopId);
            }, 1000);
        }
    })
    .fail(function(xhr) {
        showError('Error executing mop: ' + (xhr.responseJSON?.error || 'Unknown error'));
    })
    .always(function() {
        $('#execute-mop-btn').prop('disabled', false).html('<i class="fas fa-play"></i> Execute');
    });
}

function loadMOPExecutions(mopId) {
    $.get(`/api/mops/${mopId}/executions`)
        .done(function(data) {
            if (data.success) {
                renderExecutionHistory(data.executions);
            }
        });
}

function renderExecutionHistory(executions) {
    const tbody = $('#mop-executions-body');
    tbody.empty();

    if (executions.length === 0) {
        tbody.html('<tr><td colspan="4" class="text-center text-muted">No executions yet</td></tr>');
        return;
    }

    executions.forEach(execution => {
        const startTime = new Date(execution.started_at);
        const endTime = execution.completed_at ? new Date(execution.completed_at) : null;
        const duration = endTime ? ((endTime - startTime) / 1000).toFixed(1) + 's' : 'Running...';

        let statusBadge;
        if (execution.status === 'completed') {
            statusBadge = '<span class="badge bg-success">Success</span>';
        } else if (execution.status === 'failed') {
            statusBadge = '<span class="badge bg-danger">Failed</span>';
        } else {
            statusBadge = '<span class="badge bg-warning">Running</span>';
        }

        const row = $('<tr>')
            .html(`
                <td><small>${formatDateTime(execution.started_at)}</small></td>
                <td>${statusBadge}</td>
                <td><small>${duration}</small></td>
                <td>
                    <button class="btn btn-sm btn-outline-primary view-execution-btn" data-execution-id="${execution.execution_id}">
                        <i class="fas fa-eye"></i> View
                    </button>
                </td>
            `);

        tbody.append(row);
    });

    // Add click handlers
    $('.view-execution-btn').click(function() {
        const executionId = $(this).data('execution-id');
        viewExecutionDetails(executionId);
    });
}

function viewExecutionDetails(executionId) {
    $('#executionModal').modal('show');
    $('#execution-details-content').html('<div class="text-center"><i class="fas fa-spinner fa-spin"></i> Loading...</div>');

    $.get(`/api/mop-executions/${executionId}`)
        .done(function(data) {
            if (data.success) {
                renderExecutionDetails(data.execution);
            }
        })
        .fail(function() {
            $('#execution-details-content').html('<div class="alert alert-danger">Error loading execution details</div>');
        });
}

function renderExecutionDetails(execution) {
    // Build detailed execution info similar to monitor.js
    let html = `
        <div class="row mb-3">
            <div class="col-md-6">
                <p class="mb-1"><strong>Status:</strong> ${getStatusBadge(execution.status)}</p>
                <p class="mb-1"><strong>MOP Name:</strong> ${escapeHtml(execution.mop_name || 'Unknown')}</p>
                <p class="mb-1"><strong>Execution ID:</strong> <small class="font-monospace">${escapeHtml(execution.execution_id)}</small></p>
                <p class="mb-1"><strong>Current Step:</strong> ${execution.current_step !== null ? 'Step ' + (parseInt(execution.current_step) + 1) : 'N/A'}</p>
            </div>
            <div class="col-md-6">
                <p class="mb-1"><strong>Started:</strong> ${formatDateTime(execution.started_at)}</p>
                <p class="mb-1"><strong>Completed:</strong> ${execution.completed_at ? formatDateTime(execution.completed_at) : 'In Progress'}</p>
                <p class="mb-1"><strong>Duration:</strong> ${calculateDuration(execution.started_at, execution.completed_at)}</p>
                <p class="mb-1"><strong>Started By:</strong> ${escapeHtml(execution.started_by || 'N/A')}</p>
            </div>
        </div>
    `;

    if (execution.error) {
        html += `<div class="alert alert-danger"><strong><i class="fas fa-exclamation-triangle"></i> Error:</strong> ${escapeHtml(execution.error)}</div>`;
    }

    // Format execution log with same style as monitor.js
    html += '<h6 class="mt-3">Execution Log:</h6>';

    if (execution.execution_log && execution.execution_log.length > 0) {
        html += '<pre class="p-3 border rounded bg-dark text-light" style="max-height: 500px; overflow-y: auto; font-size: 0.9rem; white-space: pre-wrap; font-family: \'Courier New\', monospace;">';

        execution.execution_log.forEach(log => {
            const statusIcon = log.status === 'success' ? '✓' : log.status === 'failed' ? '✗' : '•';
            const status = log.status ? log.status.toUpperCase() : 'UNKNOWN';
            const timestamp = log.timestamp ? formatDateTime(log.timestamp) : '';

            html += `${statusIcon} ${escapeHtml(log.step)}\n`;
            html += `  Status: ${status}\n`;
            if (log.message) {
                html += `  Message: ${escapeHtml(log.message)}\n`;
            }
            // Show error details if step failed
            if (log.error) {
                html += `  Error: ${escapeHtml(log.error)}\n`;
            }
            // Show additional details if available
            if (log.details) {
                html += `  Details: ${escapeHtml(JSON.stringify(log.details))}\n`;
            }
            if (timestamp) {
                html += `  Time: ${timestamp}\n`;
            }
            html += '\n';
        });

        html += '</pre>';
    } else {
        html += '<pre class="p-3 border rounded bg-dark text-light" style="font-family: \'Courier New\', monospace;">No log available</pre>';
    }

    $('#execution-details-content').html(html);
}

function validateYAML() {
    const yamlContent = $('#mop-yaml').val();
    const resultSpan = $('#yaml-validation-result');

    try {
        // Basic YAML validation (browser-side)
        // Check for common issues
        const lines = yamlContent.split('\n');
        let hasName = false;
        let hasSteps = false;

        for (const line of lines) {
            if (line.trim().startsWith('name:')) hasName = true;
            if (line.trim().startsWith('steps:')) hasSteps = true;
        }

        if (!hasName) {
            resultSpan.html('<span class="text-danger"><i class="fas fa-times"></i> Missing "name" field</span>');
            return;
        }

        if (!hasSteps) {
            resultSpan.html('<span class="text-danger"><i class="fas fa-times"></i> Missing "steps" section</span>');
            return;
        }

        resultSpan.html('<span class="text-success"><i class="fas fa-check"></i> YAML looks valid</span>');

    } catch (e) {
        resultSpan.html('<span class="text-danger"><i class="fas fa-times"></i> Invalid YAML syntax</span>');
    }
}

function getStatusBadge(status) {
    if (status === 'completed') return '<span class="badge bg-success">Success</span>';
    if (status === 'failed') return '<span class="badge bg-danger">Failed</span>';
    if (status === 'running') return '<span class="badge bg-warning">Running</span>';
    return '<span class="badge bg-secondary">' + status + '</span>';
}

function calculateDuration(start, end) {
    if (!end) return 'Running...';
    const startTime = new Date(start);
    const endTime = new Date(end);
    return ((endTime - startTime) / 1000).toFixed(1) + 's';
}

function formatDate(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleDateString();
}

function formatDateTime(dateStr) {
    if (!dateStr) return '';
    const date = new Date(dateStr);
    return date.toLocaleString();
}

// Copy execution log to clipboard
$('#copy-execution-log').on('click', function() {
    const logElement = $('#execution-details-content pre');
    if (logElement.length > 0) {
        const logText = logElement.text();
        const btn = $(this);
        const originalText = btn.html();
        navigator.clipboard.writeText(logText).then(function() {
            btn.html('<i class="fas fa-check"></i> Copied');
            setTimeout(() => btn.html(originalText), 1500);
        }, function(err) {
            alert('Failed to copy log: ' + err);
        });
    } else {
        alert('No log available to copy');
    }
});

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showSuccess(message) {
    // Silent success - no popup needed for simple saves
    console.log('Success:', message);
}

function showError(message) {
    alert(message);
}
