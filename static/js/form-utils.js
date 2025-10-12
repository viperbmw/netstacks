// Form utility functions for dynamic template variables and credentials

/**
 * Load default credentials from settings
 */
function loadDefaultCredentials() {
    try {
        const stored = localStorage.getItem('netstacks_settings');
        if (stored) {
            const settings = JSON.parse(stored);
            return {
                username: settings.default_username || '',
                password: settings.default_password || ''
            };
        }
    } catch (e) {
        console.error('Error loading credentials from settings:', e);
    }
    return { username: '', password: '' };
}

/**
 * Pre-fill credentials in form if defaults exist
 */
function prefillCredentials(usernameId, passwordId) {
    const creds = loadDefaultCredentials();
    if (creds.username) {
        $(usernameId).val(creds.username);
    }
    if (creds.password) {
        $(passwordId).val(creds.password);
    }
}

/**
 * Load template variables and create dynamic form fields
 */
function loadTemplateVariables(templateName, containerId, inputMode) {
    const container = $(containerId);
    container.show();
    container.html('<div class="text-center"><div class="spinner-border spinner-border-sm"></div> Loading variables...</div>');

    $.get('/api/templates/' + encodeURIComponent(templateName) + '/variables')
        .done(function(data) {
            if (data.success && data.variables) {
                if (inputMode === 'form') {
                    renderVariableForm(data.variables, container);
                } else {
                    renderVariableJSON(data.variables, container);
                }
                container.show();
            } else {
                container.html('<div class="alert alert-warning">No variables found in template</div>');
                container.show();
            }
        })
        .fail(function() {
            container.html('<div class="alert alert-danger">Failed to load template variables</div>');
            container.show();
        });
}

/**
 * Render dynamic form fields for template variables
 */
function renderVariableForm(variables, container) {
    if (variables.length === 0) {
        container.html('<div class="alert alert-info">This template has no variables</div>');
        return;
    }

    let html = '<div class="template-variables-form">';

    variables.forEach(function(variable) {
        const fieldId = 'template-var-' + variable;
        const label = variable.replace(/_/g, ' ').replace(/\b\w/g, l => l.toUpperCase());

        html += `
            <div class="mb-3">
                <label for="${fieldId}" class="form-label">${label}</label>
                <input type="text" class="form-control template-var-input"
                       id="${fieldId}"
                       data-var-name="${variable}"
                       placeholder="Enter ${label.toLowerCase()}">
            </div>
        `;
    });

    html += '</div>';
    container.html(html);
}

/**
 * Render JSON textarea for template variables
 */
function renderVariableJSON(variables, container) {
    if (variables.length === 0) {
        container.html('<div class="alert alert-info">This template has no variables</div>');
        return;
    }

    // Create example JSON object
    const exampleObj = {};
    variables.forEach(function(variable) {
        exampleObj[variable] = '';
    });

    const exampleJSON = JSON.stringify(exampleObj, null, 2);

    const html = `
        <div class="mb-3">
            <label class="form-label">Template Variables (JSON)</label>
            <textarea class="form-control font-monospace template-vars-json" rows="8" placeholder='${exampleJSON}'></textarea>
            <small class="form-text text-muted">Enter variables as JSON object</small>
        </div>
    `;

    container.html(html);
}

/**
 * Collect template variables from form fields
 */
function collectTemplateVariables(containerId) {
    const container = $(containerId);
    const variables = {};

    // Check if using form mode
    const formInputs = container.find('.template-var-input');
    if (formInputs.length > 0) {
        formInputs.each(function() {
            const varName = $(this).data('var-name');
            const value = $(this).val().trim();
            if (value) {
                variables[varName] = value;
            }
        });
        return variables;
    }

    // Check if using JSON mode
    const jsonTextarea = container.find('.template-vars-json');
    if (jsonTextarea.length > 0) {
        const jsonText = jsonTextarea.val().trim();
        if (jsonText) {
            try {
                return JSON.parse(jsonText);
            } catch (e) {
                throw new Error('Invalid JSON: ' + e.message);
            }
        }
    }

    return variables;
}

/**
 * Toggle between Form and JSON input modes for template variables
 */
function setupTemplateVariableToggle(templateSelectId, containerId, toggleContainerId) {
    const container = $(containerId);
    const toggleContainer = $(toggleContainerId);
    let currentMode = 'form';
    let currentTemplate = null;

    // Create toggle buttons
    const toggleHTML = `
        <div class="btn-group mb-2" role="group">
            <input type="radio" class="btn-check" name="var-input-mode" id="var-mode-form" value="form" checked autocomplete="off">
            <label class="btn btn-outline-primary btn-sm" for="var-mode-form">
                <i class="fas fa-list"></i> Form
            </label>

            <input type="radio" class="btn-check" name="var-input-mode" id="var-mode-json" value="json" autocomplete="off">
            <label class="btn btn-outline-primary btn-sm" for="var-mode-json">
                <i class="fas fa-code"></i> JSON
            </label>
        </div>
    `;

    toggleContainer.html(toggleHTML);
    toggleContainer.hide();

    // Template selection handler
    $(templateSelectId).change(function() {
        const templateName = $(this).val();
        currentTemplate = templateName;

        if (templateName) {
            toggleContainer.show();
            container.show();
            loadTemplateVariables(templateName, containerId, currentMode);
        } else {
            toggleContainer.hide();
            container.hide();
            container.html('');
        }
    });

    // Mode toggle handler
    $('input[name="var-input-mode"]').change(function() {
        currentMode = $(this).val();
        if (currentTemplate) {
            loadTemplateVariables(currentTemplate, containerId, currentMode);
        }
    });
}
