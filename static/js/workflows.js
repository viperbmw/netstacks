/**
 * Workflows Management UI
 * YAML-based workflow engine interface
 */

let currentWorkflowId = null;
let workflows = [];

// Example workflow templates
const WORKFLOW_EXAMPLES = {
    maintenance: `name: "Maintenance Window - Deploy Customer VPN"
description: "Check prerequisites, deploy stack, send notifications"
devices:
  - bms01-bidev.nae05.gi-nw.viasat.io
  - dmsp01-cidev.nae05.gi-nw.viasat.io

steps:
  - name: "Verify Devices Reachable"
    type: check_ping
    on_success: check_bgp
    on_failure: send_failure_email

  - name: "Verify BGP Neighbors"
    id: check_bgp
    type: check_bgp
    expect_neighbor_count: 4
    compare_to_netbox: true
    on_success: deploy_stack
    on_failure: send_failure_email

  - name: "Deploy Customer VPN Stack"
    id: deploy_stack
    type: deploy_stack
    stack_id: "customer-vpn-stack"
    on_success: verify_deployment
    on_failure: rollback

  - name: "Verify Deployment"
    id: verify_deployment
    type: check_interfaces
    expect_up_count: 3
    on_success: send_success_email
    on_failure: send_failure_email

  - name: "Rollback Stack"
    id: rollback
    type: deploy_stack
    stack_id: "rollback-stack"
    on_success: send_failure_email
    on_failure: send_failure_email

  - name: "Send Success Email"
    id: send_success_email
    type: email
    to: "ops@company.com"
    subject: "Maintenance Complete - {workflow_name}"
    body: "Deployment successful at {timestamp}"

  - name: "Send Failure Email"
    id: send_failure_email
    type: email
    to: "oncall@company.com"
    subject: "Maintenance Failed - {workflow_name}"
    body: "Workflow failed. Check logs for details."`,

    simple: `name: "Simple BGP Check and Alert"
description: "Check BGP neighbors and send email if there's an issue"
devices:
  - router1.example.com
  - router2.example.com

steps:
  - name: "Check BGP Status"
    type: check_bgp
    expect_neighbor_count: 4
    on_success: send_success
    on_failure: send_alert

  - name: "Send Success"
    id: send_success
    type: email
    to: "ops@company.com"
    subject: "BGP Check Passed"
    body: "All BGP neighbors are up"

  - name: "Send Alert"
    id: send_alert
    type: email
    to: "oncall@company.com"
    subject: "BGP Check FAILED"
    body: "BGP neighbor count mismatch detected"`,

    custom: `name: "Custom Python Validation"
description: "Use custom Python code for complex validation logic"
devices:
  - device1.example.com

steps:
  - name: "Get Interface Status"
    type: run_command
    command: "show ip interface brief"
    use_textfsm: true

  - name: "Custom Validation"
    type: custom_python
    script: |
      # Access previous step results from context
      interfaces = context['step_results'].get('Get Interface Status', {}).get('data', [])

      # Custom validation logic
      up_count = sum(1 for intf in interfaces if intf.get('status') == 'up')

      if up_count >= 3:
          result = {'status': 'success', 'message': f'{up_count} interfaces up'}
      else:
          result = {'status': 'failed', 'error': f'Only {up_count} interfaces up'}
    on_success: send_success
    on_failure: send_alert

  - name: "Send Success"
    id: send_success
    type: email
    to: "ops@company.com"
    subject: "Validation Passed"

  - name: "Send Alert"
    id: send_alert
    type: email
    to: "oncall@company.com"
    subject: "Validation Failed"`
};

$(document).ready(function() {
    loadWorkflows();

    // Create new workflow
    $('#create-workflow-btn').click(function() {
        currentWorkflowId = null;
        $('#current-workflow-id').val('');
        $('#workflow-name').val('');
        $('#workflow-description').val('');
        $('#workflow-yaml').val('');
        $('#workflow-executions-body').html('<tr><td colspan="4" class="text-center text-muted">No executions yet</td></tr>');

        $('#no-workflow-selected').hide();
        $('#workflow-editor').show();
        $('#workflow-title').text('New Workflow');
        $('#delete-workflow-btn').hide();
    });

    // Load example templates
    $('.load-example').click(function(e) {
        e.preventDefault();
        const exampleType = $(this).data('example');
        const yamlContent = WORKFLOW_EXAMPLES[exampleType];

        if (yamlContent) {
            currentWorkflowId = null;
            $('#current-workflow-id').val('');

            // Parse YAML to get name
            const nameMatch = yamlContent.match(/name:\s*"([^"]+)"/);
            const descMatch = yamlContent.match(/description:\s*"([^"]+)"/);

            $('#workflow-name').val(nameMatch ? nameMatch[1] : 'Example Workflow');
            $('#workflow-description').val(descMatch ? descMatch[1] : '');
            $('#workflow-yaml').val(yamlContent);
            $('#workflow-executions-body').html('<tr><td colspan="4" class="text-center text-muted">No executions yet</td></tr>');

            $('#no-workflow-selected').hide();
            $('#workflow-editor').show();
            $('#workflow-title').text('Example: ' + (nameMatch ? nameMatch[1] : 'Workflow'));
            $('#delete-workflow-btn').hide();
        }
    });

    // Save workflow
    $('#save-workflow-btn').click(function() {
        saveWorkflow();
    });

    // Delete workflow
    $('#delete-workflow-btn').click(function() {
        if (confirm('Are you sure you want to delete this workflow?')) {
            deleteWorkflow(currentWorkflowId);
        }
    });

    // Execute workflow
    $('#execute-workflow-btn').click(function() {
        if (!currentWorkflowId) {
            alert('Please save the workflow first before executing');
            return;
        }
        executeWorkflow(currentWorkflowId);
    });

    // Validate YAML
    $('#validate-yaml-btn').click(function() {
        validateYAML();
    });
});

function loadWorkflows() {
    $.get('/api/workflows')
        .done(function(data) {
            if (data.success) {
                workflows = data.workflows;
                renderWorkflowsList();
            }
        })
        .fail(function() {
            $('#workflows-list').html('<div class="p-3 text-danger">Error loading workflows</div>');
        });
}

function renderWorkflowsList() {
    const container = $('#workflows-list');
    container.empty();

    if (workflows.length === 0) {
        container.html('<div class="p-3 text-muted text-center">No workflows yet</div>');
        return;
    }

    workflows.forEach(workflow => {
        const item = $('<a>')
            .addClass('list-group-item list-group-item-action')
            .attr('href', '#')
            .data('workflow-id', workflow.workflow_id)
            .html(`
                <div class="d-flex w-100 justify-content-between">
                    <h6 class="mb-1">${escapeHtml(workflow.name)}</h6>
                    <small class="text-muted">${formatDate(workflow.created_at)}</small>
                </div>
                ${workflow.description ? `<p class="mb-1 small text-muted">${escapeHtml(workflow.description)}</p>` : ''}
            `)
            .click(function(e) {
                e.preventDefault();
                loadWorkflow(workflow.workflow_id);
            });

        if (currentWorkflowId === workflow.workflow_id) {
            item.addClass('active');
        }

        container.append(item);
    });
}

function loadWorkflow(workflowId) {
    $.get(`/api/workflows/${workflowId}`)
        .done(function(data) {
            if (data.success) {
                const workflow = data.workflow;
                currentWorkflowId = workflowId;

                $('#current-workflow-id').val(workflowId);
                $('#workflow-name').val(workflow.name);
                $('#workflow-description').val(workflow.description || '');
                $('#workflow-yaml').val(workflow.yaml_content);

                $('#no-workflow-selected').hide();
                $('#workflow-editor').show();
                $('#workflow-title').text(workflow.name);
                $('#delete-workflow-btn').show();

                // Load execution history
                loadWorkflowExecutions(workflowId);

                // Update list highlighting
                renderWorkflowsList();
            }
        });
}

function saveWorkflow() {
    const name = $('#workflow-name').val().trim();
    const description = $('#workflow-description').val().trim();
    const yamlContent = $('#workflow-yaml').val().trim();

    if (!name) {
        alert('Please enter a workflow name');
        return;
    }

    if (!yamlContent) {
        alert('Please enter YAML workflow definition');
        return;
    }

    const data = {
        name: name,
        description: description,
        yaml_content: yamlContent,
        devices: []  // Extracted from YAML
    };

    if (currentWorkflowId) {
        // Update existing
        $.ajax({
            url: `/api/workflows/${currentWorkflowId}`,
            method: 'PUT',
            contentType: 'application/json',
            data: JSON.stringify(data)
        })
        .done(function() {
            showSuccess('Workflow updated successfully');
            loadWorkflows();
        })
        .fail(function(xhr) {
            showError('Error updating workflow: ' + (xhr.responseJSON?.error || 'Unknown error'));
        });
    } else {
        // Create new
        $.ajax({
            url: '/api/workflows',
            method: 'POST',
            contentType: 'application/json',
            data: JSON.stringify(data)
        })
        .done(function(data) {
            if (data.success) {
                currentWorkflowId = data.workflow_id;
                $('#current-workflow-id').val(currentWorkflowId);
                $('#delete-workflow-btn').show();
                showSuccess('Workflow created successfully');
                loadWorkflows();
            }
        })
        .fail(function(xhr) {
            showError('Error creating workflow: ' + (xhr.responseJSON?.error || 'Unknown error'));
        });
    }
}

function deleteWorkflow(workflowId) {
    $.ajax({
        url: `/api/workflows/${workflowId}`,
        method: 'DELETE'
    })
    .done(function() {
        showSuccess('Workflow deleted');
        currentWorkflowId = null;
        $('#workflow-editor').hide();
        $('#no-workflow-selected').show();
        loadWorkflows();
    })
    .fail(function(xhr) {
        showError('Error deleting workflow: ' + (xhr.responseJSON?.error || 'Unknown error'));
    });
}

function executeWorkflow(workflowId) {
    $('#execute-workflow-btn').prop('disabled', true).html('<i class="fas fa-spinner fa-spin"></i> Executing...');

    $.ajax({
        url: `/api/workflows/${workflowId}/execute`,
        method: 'POST'
    })
    .done(function(data) {
        if (data.success) {
            showSuccess('Workflow execution started');

            // Reload execution history after a short delay
            setTimeout(function() {
                loadWorkflowExecutions(workflowId);
            }, 1000);
        }
    })
    .fail(function(xhr) {
        showError('Error executing workflow: ' + (xhr.responseJSON?.error || 'Unknown error'));
    })
    .always(function() {
        $('#execute-workflow-btn').prop('disabled', false).html('<i class="fas fa-play"></i> Execute');
    });
}

function loadWorkflowExecutions(workflowId) {
    $.get(`/api/workflows/${workflowId}/executions`)
        .done(function(data) {
            if (data.success) {
                renderExecutionHistory(data.executions);
            }
        });
}

function renderExecutionHistory(executions) {
    const tbody = $('#workflow-executions-body');
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

    $.get(`/api/workflow-executions/${executionId}`)
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
    let html = `
        <div class="row mb-3">
            <div class="col-md-4">
                <strong>Status:</strong> ${getStatusBadge(execution.status)}
            </div>
            <div class="col-md-4">
                <strong>Started:</strong> ${formatDateTime(execution.started_at)}
            </div>
            <div class="col-md-4">
                <strong>Duration:</strong> ${calculateDuration(execution.started_at, execution.completed_at)}
            </div>
        </div>
    `;

    if (execution.error) {
        html += `<div class="alert alert-danger"><strong>Error:</strong> ${escapeHtml(execution.error)}</div>`;
    }

    if (execution.execution_log && execution.execution_log.length > 0) {
        html += '<h6 class="mt-3">Execution Log:</h6><div class="list-group">';

        execution.execution_log.forEach(log => {
            const icon = log.status === 'success' ? 'check-circle text-success' : 'times-circle text-danger';
            html += `
                <div class="list-group-item">
                    <div class="d-flex w-100 justify-content-between">
                        <h6 class="mb-1">
                            <i class="fas fa-${icon}"></i> ${escapeHtml(log.step)}
                        </h6>
                        <small class="text-muted">${formatDateTime(log.timestamp)}</small>
                    </div>
                    ${log.message ? `<p class="mb-0 small">${escapeHtml(log.message)}</p>` : ''}
                </div>
            `;
        });

        html += '</div>';
    }

    $('#execution-details-content').html(html);
}

function validateYAML() {
    const yamlContent = $('#workflow-yaml').val();
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

function escapeHtml(text) {
    if (!text) return '';
    const div = document.createElement('div');
    div.textContent = text;
    return div.innerHTML;
}

function showSuccess(message) {
    // TODO: Implement toast notification
    alert(message);
}

function showError(message) {
    // TODO: Implement toast notification
    alert(message);
}
