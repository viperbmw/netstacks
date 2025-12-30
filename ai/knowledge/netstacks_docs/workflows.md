# NetStacks Workflows

## Template to Stack Deployment Flow

1. **Create Template**: Define Jinja2 template with variables
2. **Create Stack**: Group templates with deployment order
3. **Add Stack Templates**: Link templates to stack with variable values
4. **Deploy Stack**: Render templates and push to devices
5. **Validate**: Run post-deployment validation checks

## Incident Lifecycle

1. **Alert Received**: Webhook from monitoring system
2. **Triage**: AI agent correlates with existing incidents
3. **Incident Created**: If new issue, create incident
4. **Investigation**: Agent gathers context, runs diagnostics
5. **Remediation**: Execute automated fixes or escalate
6. **Resolution**: Verify fix, close incident

## MOP Execution

1. **Create MOP**: Define steps, approvals, rollback
2. **Schedule**: Set execution time or trigger
3. **Pre-checks**: Validate device state
4. **Approval**: Get required approvals
5. **Execute**: Run configuration steps
6. **Validation**: Verify changes applied
7. **Rollback**: If validation fails, revert changes
