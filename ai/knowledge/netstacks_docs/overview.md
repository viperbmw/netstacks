# NetStacks Platform Overview

NetStacks is a NOC (Network Operations Center) automation platform that manages network devices, configurations, and automated operations.

## Core Components

### Devices
Network devices (routers, switches, firewalls) managed by NetStacks. Each device has connection credentials and a device type (cisco_ios, juniper_junos, etc.).

### Templates
Jinja2-based configuration templates. Templates have variables that get populated when rendering configuration for a specific device or service.

### Service Stacks
Groups of templates deployed together as a coordinated service. Stacks define deployment order and variable mappings.

### MOPs (Method of Procedure)
Step-by-step automation workflows with approval gates. MOPs can include pre-checks, configuration changes, validation, and rollback procedures.

### Agents
AI agents that handle automated tasks:
- Alert Triage: Correlates and prioritizes incoming alerts
- Incident Response: Investigates and remediates incidents
- Config Validation: Validates configurations against policies

### Incidents & Alerts
Alerts are individual events from monitoring systems. Incidents group related alerts and track remediation progress.

### Backups & Snapshots
Device configuration backups stored for compliance and rollback. Snapshots are point-in-time backups across multiple devices.
