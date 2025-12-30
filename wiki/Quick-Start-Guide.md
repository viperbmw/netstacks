# Quick Start Guide

Get NetStacks up and running in 10 minutes.

## Step 1: Deploy NetStacks

```bash
git clone https://github.com/viperbmw/netstacks.git
cd netstacks
docker-compose up -d
```

## Step 2: Login

1. Open `http://localhost:8089`
2. Login with `admin` / `admin`
3. **Change the password** via Settings → Profile

## Step 3: Add a Device

1. Navigate to **Devices**
2. Click **Add Device**
3. Enter device details:
   - **Name**: `router1`
   - **IP Address**: `192.168.1.1`
   - **Device Type**: `cisco_ios`
   - **Username**: SSH username
   - **Password**: SSH password
4. Click **Save**
5. Click **Test** to verify connectivity

## Step 4: Create a Template

1. Navigate to **Templates**
2. Click **New Template**
3. Enter template details:
   - **Name**: `snmp_config`
   - **Description**: `Configure SNMP settings`
   - **Content**:
   ```jinja2
   snmp-server community {{ community }} RO
   snmp-server location {{ location }}
   snmp-server contact {{ contact }}
   ```
4. Click **Save**

## Step 5: Deploy Configuration

1. Navigate to **Deploy**
2. Select your template (`snmp_config`)
3. Select target device (`router1`)
4. Fill in variables:
   - `community`: `public`
   - `location`: `DataCenter1`
   - `contact`: `noc@example.com`
5. Click **Deploy**
6. Monitor progress in real-time

## Step 6: Verify Deployment

1. Check the job status in **Monitor**
2. View the deployed configuration
3. (Optional) Create a backup to save the current config

## What's Next?

### Expand Your Inventory

- **Netbox Integration**: Sync devices automatically from Netbox
- **Bulk Import**: Add multiple devices via CSV

### Create More Templates

- **Validation Templates**: Verify configurations exist on devices
- **Delete Templates**: Cleanly remove configurations
- **Service Stacks**: Group related templates

### Automate with MOPs

- **Visual Builder**: Create procedures without YAML
- **Conditional Logic**: Handle success/failure paths
- **Scheduling**: Run procedures at specific times

### Enable AI Features

- **Configure LLM**: Add Anthropic, OpenAI, or OpenRouter
- **Create Agents**: Automate network operations
- **Knowledge Base**: Upload documentation for context

## Example Workflows

### SNMP Configuration Rollout

1. Create SNMP template with variables
2. Select all devices needing SNMP
3. Deploy with same variables
4. Validate deployment succeeded

### Maintenance Window

1. Create MOP with steps:
   - Disable BGP on router
   - Wait for traffic to drain
   - Perform maintenance
   - Re-enable BGP
   - Verify traffic restored
2. Schedule for maintenance window
3. Monitor execution

### Configuration Backup

1. Go to **Backups**
2. Configure schedule (daily at midnight)
3. Set retention (30 days)
4. Enable backups
5. View diffs when configs change

## Troubleshooting

### Device Connection Failed

1. Verify SSH connectivity: `ssh user@device-ip`
2. Check device type matches actual device
3. Verify credentials are correct
4. Check firewall rules

### Template Variables Not Rendering

1. Use `{{ variable }}` syntax (double braces)
2. Check variable names match exactly
3. Provide all required variables

### Jobs Stuck in Queue

1. Check worker status: `docker-compose logs netstacks-workers`
2. Verify Redis is running: `docker-compose ps`
3. Restart workers: `docker-compose restart netstacks-workers`

## Next Steps

- [[Device Management]] - Detailed device configuration
- [[Templates]] - Advanced template techniques
- [[MOPs]] - Building automated procedures
- [[AI Agents]] - AI-powered automation
