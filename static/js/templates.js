// Templates page JavaScript

let allTemplatesWithMetadata = [];
let currentTemplate = null;
let isNewTemplate = false;
let editor = null;
let editorModal = null;

$(document).ready(function() {
    // Initialize CodeMirror editor
    editor = CodeMirror.fromTextArea(document.getElementById('template-content'), {
        mode: 'jinja2',
        theme: 'monokai',
        lineNumbers: true,
        lineWrapping: true,
        indentUnit: 4,
        tabSize: 4,
        indentWithTabs: false
    });

    // Initialize Bootstrap modal
    editorModal = new bootstrap.Modal(document.getElementById('templateEditorModal'));

    // Refresh CodeMirror when modal is shown
    $('#templateEditorModal').on('shown.bs.modal', function() {
        editor.refresh();
    });

    loadTemplates();

    // Create new template button
    $('#create-template-btn').click(function() {
        createNewTemplate();
    });

    // Save template button
    $('#save-template-btn').click(function() {
        saveTemplate();
    });

    // Delete template button
    $('#delete-template-btn').click(function() {
        if (confirm(`Are you sure you want to delete ${currentTemplate}?`)) {
            deleteTemplate(currentTemplate);
        }
    });

    // Push to Netstacker button
    $('#push-template-btn').click(function() {
        pushTemplateToNetstacker(currentTemplate);
    });

    // Template type change handler - show/hide validation and delete options
    $('#template-type').change(function() {
        const type = $(this).val();
        if (type === 'deploy') {
            $('#deploy-template-options').show();
        } else {
            $('#deploy-template-options').hide();
        }
    });

    // Create delete template button
    $(document).on('click', '#create-delete-template-btn', function() {
        const deployTemplateName = $('#template-name').val().trim();
        const suggestedName = deployTemplateName ? `${deployTemplateName}_delete` : '';

        // Create new template
        createNewTemplate(suggestedName, deployTemplateName, 'delete');
    });

    // Create validation template button
    $(document).on('click', '#create-validation-template-btn', function() {
        const deployTemplateName = $('#template-name').val().trim();
        const suggestedName = deployTemplateName ? `${deployTemplateName}_validate` : '';

        // Create new template
        createNewTemplate(suggestedName, deployTemplateName, 'validation');
    });
});

function loadTemplates() {
    $('#template-groups-loading').show();
    $('#template-groups-container').hide();

    $.get('/api/templates')
        .done(function(data) {
            if (data.success && data.templates && data.templates.length > 0) {
                allTemplatesWithMetadata = data.templates;
                displayTemplateGroups(data.templates);
            } else {
                $('#template-groups-container').html('<div class="alert alert-info">No templates found. Create your first template to get started.</div>');
                $('#template-groups-container').show();
            }
            $('#template-groups-loading').hide();
        })
        .fail(function() {
            $('#template-groups-container').html('<div class="alert alert-danger">Failed to load templates</div>');
            $('#template-groups-loading').hide();
            $('#template-groups-container').show();
        });
}

function displayTemplateGroups(templates) {
    const container = $('#template-groups-container');
    container.empty();

    // Organize templates into complete and incomplete stacks
    const completeStacks = [];
    const incompleteStacks = [];

    templates.forEach(template => {
        const name = template.name || template;
        const templateType = template.type || 'deploy';
        const hasValidation = template.validation_template;
        const hasDelete = template.delete_template;

        // Only process deploy templates (validation and delete templates are shown as linked components)
        if (templateType === 'deploy') {
            const stack = {
                deploy: template,
                validation: hasValidation ? templates.find(t => t.name === hasValidation) : null,
                delete: hasDelete ? templates.find(t => t.name === hasDelete) : null
            };

            // Check if stack is complete (has at least deploy + delete)
            // Validation is optional, but delete is required for a complete stack
            if (stack.delete) {
                completeStacks.push(stack);
            } else {
                incompleteStacks.push(stack);
            }
        }
    });

    // Display complete template stacks first
    if (completeStacks.length > 0) {
        container.append('<h6 class="text-muted mb-3"><i class="fas fa-layer-group"></i> Complete Template Stacks</h6>');
        container.append('<div class="row" id="complete-stacks-grid"></div>');

        completeStacks.forEach(stack => {
            $('#complete-stacks-grid').append(createTemplateStackCard(stack));
        });
    }

    // Display incomplete stacks (standalone deploy templates)
    if (incompleteStacks.length > 0) {
        container.append('<h6 class="text-muted mt-4 mb-3"><i class="fas fa-file"></i> Standalone Deploy Templates</h6>');
        container.append('<p class="text-muted small">Deploy templates without a delete template linked.</p>');
        container.append('<div class="row" id="standalone-stacks-grid"></div>');

        incompleteStacks.forEach(stack => {
            $('#standalone-stacks-grid').append(createTemplateStackCard(stack));
        });
    }

    // Collect all linked template names (validation and delete templates that are already in use)
    const linkedTemplateNames = new Set();
    templates.forEach(template => {
        if (template.type === 'deploy') {
            if (template.validation_template) {
                linkedTemplateNames.add(template.validation_template);
            }
            if (template.delete_template) {
                linkedTemplateNames.add(template.delete_template);
            }
        }
    });

    // Display standalone delete and validation templates (not linked to any deploy template)
    const standaloneTemplates = templates.filter(t =>
        (t.type === 'delete' || t.type === 'validation') && !linkedTemplateNames.has(t.name)
    );
    if (standaloneTemplates.length > 0) {
        container.append('<h6 class="text-muted mt-4 mb-3"><i class="fas fa-puzzle-piece"></i> Standalone Delete & Validation Templates</h6>');
        container.append('<p class="text-muted small">Delete and validation templates not yet linked to deploy templates.</p>');
        container.append('<div class="row" id="standalone-helpers-grid"></div>');

        standaloneTemplates.forEach(template => {
            const badge = template.type === 'delete' ?
                '<span class="badge bg-danger">Delete</span>' :
                '<span class="badge bg-success">Validation</span>';

            const cardHtml = `
                <div class="col-md-4 col-lg-2 mb-2">
                    <div class="card template-card template-card-mini h-100">
                        <div class="card-body d-flex flex-column">
                            <div class="mb-2">
                                ${badge}
                            </div>
                            <h6 class="card-title mb-2" style="font-size: 0.85rem; word-break: break-word;">
                                ${template.name}
                            </h6>
                            ${template.description ? `<p class="text-muted mb-2" style="font-size: 0.7rem;">${template.description}</p>` : ''}
                            <div class="mt-auto">
                                <button class="btn btn-sm btn-outline-primary w-100" onclick="loadTemplate('${template.name}')">
                                    <i class="fas fa-edit"></i> Edit
                                </button>
                            </div>
                        </div>
                    </div>
                </div>
            `;
            $('#standalone-helpers-grid').append(cardHtml);
        });
    }

    container.show();
}

function createTemplateStackCard(stack) {
    const deploy = stack.deploy;
    const validation = stack.validation;
    const deleteTemplate = stack.delete;

    const hasValidation = !!validation;
    const hasDelete = !!deleteTemplate;
    const isComplete = hasDelete; // Complete if it has delete template

    let cardClass = 'template-stack-card';
    if (isComplete) cardClass += ' complete';

    // For standalone templates (no delete), show simplified card
    if (!hasDelete) {
        const deployType = deploy.type || 'deploy';
        const typeBadge = deployType === 'deploy' ?
            '<span class="badge bg-info ms-1">Deploy</span>' :
            deployType === 'delete' ?
            '<span class="badge bg-danger ms-1">Delete</span>' :
            '<span class="badge bg-success ms-1">Validation</span>';

        return `
            <div class="col-md-4 col-lg-2 mb-2">
                <div class="card template-card template-card-mini ${cardClass} h-100">
                    <div class="card-body d-flex flex-column">
                        <div class="mb-2">
                            ${typeBadge}
                            <span class="badge bg-secondary ms-1">Standalone</span>
                        </div>
                        <h6 class="card-title mb-2" style="font-size: 0.85rem; word-break: break-word;">
                            ${deploy.name || deploy}
                        </h6>
                        ${deploy.description ? `<p class="text-muted mb-2" style="font-size: 0.7rem;">${deploy.description}</p>` : ''}
                        <div class="mt-auto">
                            <button class="btn btn-sm btn-outline-primary w-100 edit-template-btn" data-template="${deploy.name || deploy}">
                                <i class="fas fa-edit"></i> Edit
                            </button>
                        </div>
                    </div>
                </div>
            </div>
        `;
    }

    // For complete stacks, show full flow
    // If no explicit validation template, it uses itself (our new default behavior)
    const deployType = deploy.type || 'deploy';
    const typeBadge = '<span class="badge bg-info ms-1">Deploy</span>';
    const completeBadge = hasDelete
        ? '<span class="badge bg-success ms-1">Complete</span>'
        : '<span class="badge bg-warning text-dark ms-1">Manual Validation</span>';

    return `
        <div class="col-md-6 col-lg-3 mb-2">
            <div class="card template-card ${cardClass} h-100">
                <div class="card-body">
                    <h6 class="card-title">
                        ${deploy.name || deploy}
                        ${typeBadge}
                        ${completeBadge}
                    </h6>
                    ${deploy.description ? `<p class="text-muted mb-2">${deploy.description}</p>` : ''}

                    <div class="template-flow">
                        <!-- Deploy Template -->
                        <span class="badge bg-primary template-flow-badge" data-template="${deploy.name || deploy}" title="Click to edit">
                            <i class="fas fa-play-circle"></i> Deploy
                        </span>

                        <span class="template-flow-arrow">→</span>
                        <span class="badge bg-success template-flow-badge" data-template="${hasValidation ? validation.name : (deploy.name || deploy)}" title="Click to edit - ${hasValidation ? 'Custom validation' : 'Uses deploy template for validation'}">
                            <i class="fas fa-check-circle"></i> Validate${hasValidation ? '' : ' (Self)'}
                        </span>

                        <span class="template-flow-arrow">→</span>
                        <span class="badge bg-danger template-flow-badge" data-template="${deleteTemplate.name}" title="Click to edit">
                            <i class="fas fa-trash-alt"></i> Delete
                        </span>
                    </div>

                    <div class="action-buttons mt-2">
                        <button class="btn btn-sm btn-outline-primary edit-template-btn" data-template="${deploy.name || deploy}">
                            <i class="fas fa-edit"></i> Edit
                        </button>
                        ${!hasValidation ? `
                            <button class="btn btn-sm btn-outline-success add-validation-btn" data-template="${deploy.name || deploy}">
                                <i class="fas fa-plus"></i> Custom Validation
                            </button>
                        ` : ''}
                    </div>
                </div>
            </div>
        </div>
    `;
}


// Event delegation for dynamically created buttons
$(document).on('click', '.template-flow-badge, .edit-template-btn', function(e) {
    e.stopPropagation();
    const templateName = $(this).data('template');
    if (templateName) {
        loadTemplate(templateName);
    }
});

$(document).on('click', '.template-card', function(e) {
    e.stopPropagation();
    const templateName = $(this).data('template');
    if (templateName) {
        loadTemplate(templateName);
    }
});

$(document).on('click', '.add-validation-btn', function(e) {
    e.stopPropagation();
    const deployTemplate = $(this).data('template');
    createRelatedTemplate(deployTemplate, 'validation');
});

function createRelatedTemplate(deployTemplate, type) {
    // Create a new template and suggest a name based on the deploy template
    const baseName = deployTemplate.replace('.j2', '').replace('_add_', '_').replace('_create_', '_');
    const suggestedName = type === 'validation'
        ? `${baseName}_validate.j2`
        : `${baseName}_remove.j2`;

    createNewTemplate(suggestedName, deployTemplate, type);
}

function createNewTemplate(suggestedName = '', relatedTo = null, relationType = null) {
    currentTemplate = null;
    isNewTemplate = true;

    $('#editor-mode-title').text('Create New Template');
    $('#template-name').val(suggestedName).prop('disabled', false);
    $('#template-description').val('');
    $('#validation-template').val('');
    $('#delete-template-select').val('');
    editor.setValue('');
    $('#delete-template-btn').hide();
    $('#push-template-btn').hide();

    // Set template type based on relation type
    if (relationType === 'validation') {
        $('#template-type').val('validation');
        $('#deploy-template-options').hide();
    } else if (relationType === 'delete') {
        $('#template-type').val('delete');
        $('#deploy-template-options').hide();
    } else {
        $('#template-type').val('deploy');
        $('#deploy-template-options').show();
    }

    // Populate metadata dropdowns
    populateMetadataDropdowns();

    // If creating a related template, pre-fill some info
    if (relatedTo && relationType) {
        const deployTemplateObj = allTemplatesWithMetadata.find(t => t.name === relatedTo);
        if (deployTemplateObj && relationType === 'validation') {
            $('#template-description').val(`Validation template for ${relatedTo}`);
        } else if (deployTemplateObj && relationType === 'delete') {
            $('#template-description').val(`Delete template for ${relatedTo}`);
        }
    } else {
        // For new deploy templates, set validation to self by default
        // User can change it to a custom validation template if needed
        if (suggestedName) {
            setTimeout(function() {
                $('#validation-template').val(suggestedName);
            }, 50);
        }
    }

    editorModal.show();

    // Refresh editor after modal is shown to ensure proper rendering
    setTimeout(function() {
        editor.refresh();
    }, 100);
}

function loadTemplate(templateName) {
    $.get('/api/templates/' + encodeURIComponent(templateName))
        .done(function(data) {
            if (data.success && data.content) {
                currentTemplate = templateName;
                isNewTemplate = false;

                $('#editor-mode-title').text('Edit Template');
                $('#template-name').val(templateName).prop('disabled', true);
                editor.setValue(data.content);
                $('#delete-template-btn').show();
                $('#push-template-btn').show();

                // Load metadata
                const templateObj = allTemplatesWithMetadata.find(t => {
                    const name = typeof t === 'string' ? t : t.name;
                    return name === templateName;
                });

                if (templateObj) {
                    const templateType = templateObj.type || 'deploy'; // Default to deploy if no type set
                    $('#template-description').val(templateObj.description || '');
                    $('#template-type').val(templateType);

                    // Show/hide deploy options based on type
                    // Templates without a type should be treated as deploy templates
                    if (templateType === 'deploy') {
                        $('#deploy-template-options').show();
                        // Default validation template to itself if not set
                        $('#validation-template').val(templateObj.validation_template || templateName);
                        $('#delete-template-select').val(templateObj.delete_template || '');
                    } else {
                        $('#deploy-template-options').hide();
                    }
                }

                // Populate metadata dropdowns
                populateMetadataDropdowns();

                editorModal.show();

                // Refresh editor after modal is shown to ensure proper rendering
                setTimeout(function() {
                    editor.refresh();
                }, 100);
            }
        })
        .fail(function() {
            alert('Failed to load template');
        });
}

function populateMetadataDropdowns() {
    const validationSelect = $('#validation-template');
    const deleteSelect = $('#delete-template-select');

    const currentValidation = validationSelect.val();
    const currentDelete = deleteSelect.val();

    validationSelect.html('<option value="">None - use deployed config</option>');
    deleteSelect.html('<option value="">None - manual cleanup</option>');

    allTemplatesWithMetadata.forEach(function(template) {
        const templateName = typeof template === 'string' ? template : template.name;
        const templateType = template.type || 'deploy';

        // Only show validation templates (or deploy templates) in validation dropdown
        if (templateType === 'validation' || templateType === 'deploy') {
            validationSelect.append(`<option value="${templateName}">${templateName} (${templateType})</option>`);
        }

        // Only show delete templates in delete dropdown
        if (templateType === 'delete') {
            deleteSelect.append(`<option value="${templateName}">${templateName}</option>`);
        }
    });

    // Restore selections
    if (currentValidation) validationSelect.val(currentValidation);
    if (currentDelete) deleteSelect.val(currentDelete);
}

function saveTemplate() {
    let templateName = $('#template-name').val().trim();
    const description = $('#template-description').val().trim();
    const templateType = $('#template-type').val();
    const validationTemplate = $('#validation-template').val();
    const deleteTemplate = $('#delete-template-select').val();

    // Force CodeMirror to save to textarea first
    editor.save();
    const content = editor.getValue();

    console.log('Saving template:', templateName);
    console.log('Content length:', content.length);
    console.log('Content preview:', content.substring(0, 100));

    if (!templateName) {
        alert('Please enter a template name');
        return;
    }

    if (!content.trim()) {
        alert('Template content cannot be empty. Content length: ' + content.length);
        console.error('Empty content!', content);
        return;
    }

    // Strip .j2 extension if user added it - Netstacker stores without extension
    if (templateName.endsWith('.j2')) {
        templateName = templateName.slice(0, -3);
        $('#template-name').val(templateName);
    }

    // Base64 encode the content for Netstacker API
    const base64Content = btoa(content);

    const templateData = {
        name: templateName,
        base64_payload: base64Content,
        description: description || null,
        validation_template: validationTemplate || null,
        delete_template: deleteTemplate || null
    };

    // First, save the template content to Netstacker
    $.ajax({
        url: '/api/templates',
        method: 'POST',
        contentType: 'application/json',
        data: JSON.stringify(templateData)
    })
    .done(function(data) {
        if (data.success) {
            // Template saved successfully, now save metadata
            const metadataData = {
                type: templateType || 'deploy',
                description: description || null,
                validation_template: validationTemplate || null,
                delete_template: deleteTemplate || null
            };

            const templateNameNoExt = templateName.replace('.j2', '');

            $.ajax({
                url: '/api/templates/' + encodeURIComponent(templateNameNoExt) + '/metadata',
                method: 'PUT',
                contentType: 'application/json',
                data: JSON.stringify(metadataData)
            })
            .done(function(metadataResult) {
                alert(`Template ${templateName} saved successfully`);
                editorModal.hide();
                loadTemplates(); // Reload the template list
            })
            .fail(function(xhr) {
                console.warn('Metadata save failed:', xhr);
                alert(`Template content saved, but metadata save failed. Template: ${templateName}`);
                editorModal.hide();
                loadTemplates();
            });
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
            console.error('Save error:', data);
        }
    })
    .fail(function(xhr, status, error) {
        let errorMsg = 'Failed to save template';
        if (xhr.responseJSON && xhr.responseJSON.error) {
            errorMsg += ': ' + xhr.responseJSON.error;
        } else if (xhr.responseText) {
            errorMsg += ': ' + xhr.responseText;
        }
        alert(errorMsg);
        console.error('Save failed:', xhr, status, error);
    });
}

function deleteTemplate(templateName) {
    if (!templateName) return;

    const templateNameNoExt = templateName.replace('.j2', '');

    $.ajax({
        url: '/api/templates',
        method: 'DELETE',
        contentType: 'application/json',
        data: JSON.stringify({ name: templateNameNoExt })
    })
    .done(function(data) {
        if (data.success) {
            alert(`Template ${templateName} deleted successfully`);
            editorModal.hide();
            loadTemplates();
        } else {
            alert('Error: ' + (data.error || 'Unknown error'));
        }
    })
    .fail(function(xhr) {
        const errorMsg = xhr.responseJSON?.error || 'Failed to delete template';
        alert('Error: ' + errorMsg);
    });
}

/**
 * Push template to Netstacker for persistent storage
 */
function pushTemplateToNetstacker(templateName) {
    if (!templateName) {
        alert('No template selected');
        return;
    }

    const templateNameNoExt = templateName.endsWith('.j2') ? templateName.slice(0, -3) : templateName;

    // Show loading state
    const $btn = $('#push-template-btn');
    const originalHtml = $btn.html();
    $btn.prop('disabled', true).html('<span class="spinner-border spinner-border-sm"></span> Pushing...');

    $.ajax({
        url: '/api/templates/' + encodeURIComponent(templateNameNoExt) + '/push',
        method: 'POST',
        timeout: 30000
    })
    .done(function(data) {
        if (data.success) {
            alert(`✓ Template "${templateName}" successfully pushed to Netstacker!\n\n${data.message}`);
        } else {
            alert('Error pushing to Netstacker: ' + (data.error || 'Unknown error'));
        }
    })
    .fail(function(xhr) {
        const error = xhr.responseJSON && xhr.responseJSON.error ? xhr.responseJSON.error : 'Failed to push template';
        alert('Error: ' + error);
    })
    .always(function() {
        $btn.prop('disabled', false).html(originalHtml);
    });
}
