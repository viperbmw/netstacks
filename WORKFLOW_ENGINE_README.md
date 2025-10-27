# YAML Workflow Engine

A simple, intuitive workflow engine for network automation. Network engineers can create workflows using plain YAML - no Python coding required.

## Quick Start

### 1. Create a Workflow (YAML file)

```yaml
name: "Check BGP and Deploy"
description: "Simple maintenance workflow"

devices:
  - router1
  - router2

steps:
  - name: "Check BGP Neighbors"
    type: check_bgp
    expect_neighbor_count: 4
    on_failure: send_alert

  - name: "Deploy Service Stack"
    type: deploy_stack
    stack_id: "customer-vpn"
    on_failure: send_alert

  - name: "Send Success Email"
    type: email
    to: "ops@company.com"
    subject: "Deployment Complete"
    body: "Service deployed successfully!"

  - name: "Send Alert"
    id: send_alert
    type: email
    to: "oncall@company.com"
    subject: "Deployment Failed"
    body: "Check the logs for details"
```

### 2. Test Your Workflow

```bash
# Test from command line
python test_workflow.py workflows/my_workflow.yaml

# With verbose output
python test_workflow.py workflows/my_workflow.yaml --verbose
```

### 3. Execute via Web UI (Coming Soon)

Navigate to `/workflows` page and click "Execute"

## Workflow Structure

### Basic Format

```yaml
name: "Workflow Name"              # Required
description: "What this does"      # Optional
devices:                           # Optional - can be set per step
  - device1
  - device2

steps:                             # Required
  - name: "Step Name"
    type: step_type
    # ... step-specific parameters
    on_success: next_step_id       # Optional - jump to step
    on_failure: error_step_id      # Optional - jump on error
```

### Conditional Flow

```yaml
steps:
  - name: "Check Something"
    id: check_step
    type: check_bgp
    on_success: do_deployment      # Jump to deployment if success
    on_failure: send_alert         # Jump to alert if failed

  - name: "Deploy Stack"
    id: do_deployment
    type: deploy_stack
    # ... continues here if check passed

  - name: "Send Alert"
    id: send_alert
    type: email
    # ... jumps here if check failed
```

## Available Step Types

### 1. Check Steps (Validation)

#### `check_bgp` - Verify BGP Neighbors

```yaml
- name: "Verify BGP"
  type: check_bgp
  expect_neighbor_count: 4         # Expected neighbor count
  compare_to_netbox: true          # Get expected from Netbox
  on_success: next_step
  on_failure: send_alert
```

#### `check_ping` - Verify Device Reachability

```yaml
- name: "Ping Devices"
  type: check_ping
  devices:                         # Override workflow devices
    - router1
    - router2
```

#### `check_interfaces` - Verify Interface Status

```yaml
- name: "Check Interfaces"
  type: check_interfaces
  expect_up_count: 3               # Expect 3 interfaces up
```

### 2. Action Steps (Make Changes)

#### `deploy_stack` - Deploy Service Stack

```yaml
- name: "Deploy VPN Service"
  type: deploy_stack
  stack_id: "customer-vpn-stack"   # Stack ID to deploy
  devices:
    - router1
    - router2
```

#### `run_command` - Execute CLI Commands

```yaml
- name: "Get Interface Status"
  type: run_command
  command: "show ip interface brief"
  use_textfsm: true                # Parse output with TextFSM
```

### 3. Notification Steps

#### `email` - Send Email

```yaml
- name: "Send Notification"
  type: email
  to: "ops@company.com"
  subject: "Workflow Complete"
  body: |
    Workflow finished at {timestamp}

    Status: Success
    Devices: {devices}
```

**Available variables in email:**
- `{timestamp}` - Current timestamp
- `{workflow_name}` - Name of workflow
- `{step_results.STEP_ID.data.FIELD}` - Result from previous step

#### `webhook` - Call HTTP Endpoint

```yaml
- name: "Notify Slack"
  type: webhook
  url: "https://hooks.slack.com/services/YOUR/WEBHOOK/URL"
  method: POST
  body:
    text: "Deployment complete!"
    channel: "#network-ops"
```

### 4. Custom Steps

#### `custom_python` - Run Python Code

```yaml
- name: "Custom Validation"
  type: custom_python
  script: |
    # Your Python code here
    # Access previous results via 'context' variable

    results = context['step_results']

    # Do custom logic
    if some_condition:
        result = {'status': 'success', 'message': 'OK'}
    else:
        result = {'status': 'failed', 'error': 'Not OK'}
```

**Available in Python scripts:**
- `context` - Full workflow context with all results
- `log` - Logger instance
- `datetime` - Python datetime module
- `json` - Python json module

#### `wait` - Pause Execution

```yaml
- name: "Wait for Convergence"
  type: wait
  seconds: 30                      # Wait 30 seconds
```

## Example Workflows

### Example 1: Simple Pre-flight Check

```yaml
name: "Pre-flight Check"

devices:
  - router1
  - router2

steps:
  - name: "Check Devices Online"
    type: check_ping
    on_failure: send_alert

  - name: "Check BGP"
    type: check_bgp
    expect_neighbor_count: 4
    on_failure: send_alert

  - name: "Send Success"
    type: email
    to: "ops@company.com"
    subject: "Pre-flight Passed"
    body: "All checks passed, ready for maintenance"

  - name: "Send Alert"
    id: send_alert
    type: email
    to: "oncall@company.com"
    subject: "Pre-flight Failed"
    body: "Cannot proceed with maintenance"
```

### Example 2: Deploy with Rollback

```yaml
name: "Deploy with Rollback"

devices:
  - router1
  - router2

steps:
  - name: "Deploy New Config"
    type: deploy_stack
    stack_id: "new-config-v2"
    on_failure: rollback

  - name: "Verify Deployment"
    type: check_interfaces
    expect_up_count: 3
    on_failure: rollback
    on_success: send_success

  - name: "Rollback"
    id: rollback
    type: deploy_stack
    stack_id: "previous-config"
    on_success: send_rollback_notice

  - name: "Send Success"
    id: send_success
    type: email
    to: "ops@company.com"
    subject: "Deployment Successful"

  - name: "Send Rollback Notice"
    id: send_rollback_notice
    type: email
    to: "ops@company.com"
    subject: "Deployment Failed - Rolled Back"
```

### Example 3: Your Exact Use Case

```yaml
name: "Maintenance Window - BGP Check and Deploy"
description: "Check BGP matches Netbox, deploy stack, send email"

devices:
  - bms01-bidev.nae05.gi-nw.viasat.io
  - dmsp01-cidev.nae05.gi-nw.viasat.io

steps:
  # Step 1: Check devices are online
  - name: "Verify Devices Online"
    type: check_ping
    on_failure: send_preflight_fail

  # Step 2: Check BGP neighbor count matches Netbox
  - name: "Verify BGP Neighbors"
    type: check_bgp
    compare_to_netbox: true          # Get expected count from Netbox
    on_success: deploy_stack
    on_failure: send_preflight_fail

  # Step 3: Deploy service stack
  - name: "Deploy Service Stack"
    id: deploy_stack
    type: deploy_stack
    stack_id: "customer-service-stack"
    on_success: send_success_email
    on_failure: send_deploy_fail

  # Success path
  - name: "Send Success Email"
    id: send_success_email
    type: email
    to: "ops@company.com"
    subject: "Maintenance Complete - Service Deployed"
    body: |
      Maintenance window completed successfully!

      Time: {timestamp}
      Devices: bms01-bidev, dmsp01-cidev
      Stack: customer-service-stack

      All checks passed and service is deployed.

  # Failure paths
  - name: "Send Pre-flight Failure"
    id: send_preflight_fail
    type: email
    to: "ops@company.com"
    subject: "ALERT: Pre-flight Checks Failed"
    body: |
      Pre-flight checks failed - no changes made.

      Please verify device status before proceeding.

  - name: "Send Deploy Failure"
    id: send_deploy_fail
    type: email
    to: "ops@company.com,oncall@company.com"
    subject: "CRITICAL: Service Deployment Failed"
    body: |
      Service deployment failed!

      Manual intervention may be required.
```

## Best Practices

### 1. Always Include Failure Handling

```yaml
# Good
- name: "Critical Step"
  type: deploy_stack
  on_failure: rollback_and_notify

# Bad (failure will stop workflow without notification)
- name: "Critical Step"
  type: deploy_stack
```

### 2. Use Descriptive Names

```yaml
# Good
- name: "Verify BGP Neighbors Match Expected Count"

# Bad
- name: "Check 1"
```

### 3. Add Comments

```yaml
steps:
  # Pre-flight checks
  - name: "Check Devices Online"
    type: check_ping

  # Deployment steps
  - name: "Deploy Stack"
    type: deploy_stack
```

### 4. Test Before Production

```bash
# Always test with dry run first
python test_workflow.py workflows/my_workflow.yaml

# Check the logs
python test_workflow.py workflows/my_workflow.yaml --verbose
```

## Troubleshooting

### Workflow Won't Execute

1. Check YAML syntax: `python -m yaml workflows/my_workflow.yaml`
2. Verify all step IDs referenced in `on_success`/`on_failure` exist
3. Check logs for detailed error messages

### Steps Not Running as Expected

1. Use `--verbose` flag to see full execution context
2. Check `on_success` and `on_failure` paths
3. Verify step types are spelled correctly

### Variables Not Substituting

1. Check variable syntax: `{variable}` not `{{variable}}`
2. Verify variable exists in context
3. Use verbose mode to see available context

## Next Steps

1. **Try the examples**: Run the example workflows
2. **Create your first workflow**: Start with `example_simple.yaml` as a template
3. **Test it**: Use `test_workflow.py` to verify it works
4. **Deploy it**: Use the web UI to execute in production

## Support

For help or questions:
- Check the examples in `workflows/` directory
- Review this README
- Contact the network automation team
