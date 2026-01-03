# Configuration Backups

NetStacks provides automated and on-demand configuration backup with diff comparison and retention management.

## Overview

Configuration backups capture device running configurations for:
- Change tracking
- Compliance auditing
- Disaster recovery
- Troubleshooting

## Backup Methods

### On-Demand Backup

1. Navigate to **Backups**
2. Select device(s)
3. Click **Backup Now**
4. View progress
5. Backup stored when complete

### Scheduled Backups

Configure automated backups:

1. Navigate to **Backups → Schedule**
2. Configure schedule:
   - **Enabled**: Turn on scheduled backups
   - **Interval**: Hours between backups (e.g., 24)
   - **Retention**: Days to keep backups (e.g., 30)
3. Click **Save**

### Backup Triggers

Backups can also be triggered by:
- MOP steps
- API calls
- Post-deployment hooks

## Viewing Backups

### Backup List

Navigate to **Backups** to see:
- Device name
- Backup timestamp
- Size
- Status

### Filter Options

- By device
- By date range
- By status

### Backup Details

Click a backup to view:
- Full configuration content
- Metadata (timestamp, size, format)
- Related backups for comparison

## Configuration Diff

Compare configurations to see changes.

### Compare Two Backups

1. Select first backup
2. Click **Compare**
3. Select second backup
4. View diff

### Diff Display

```diff
- no ip http server
+ ip http server
+ ip http secure-server
```

- Red lines: Removed
- Green lines: Added
- Yellow lines: Changed

### Compare with Running Config

1. Select a backup
2. Click **Compare with Current**
3. View differences from device's current config

## Backup Formats

### Standard Format

Full configuration as retrieved from device:

```
! Cisco IOS Configuration
hostname router1
!
interface GigabitEthernet0/0
  ip address 10.0.0.1 255.255.255.0
!
```

### Juniper Set Format

For Junos devices, optional set format:

```
set system host-name router1
set interfaces ge-0/0/0 unit 0 family inet address 10.0.0.1/24
```

Configure in schedule settings:
- **Juniper Set Format**: Enable for set-style output

## Retention Management

### Automatic Cleanup

Old backups are automatically deleted based on retention settings:
- Runs daily at 3 AM
- Deletes backups older than retention period
- Logs cleanup actions

### Manual Cleanup

1. Navigate to **Backups**
2. Select old backups
3. Click **Delete**
4. Confirm deletion

### Storage Considerations

Backups are stored in PostgreSQL. Monitor database size for large deployments.

## Backup Schedule Settings

| Setting | Default | Description |
|---------|---------|-------------|
| `enabled` | false | Enable scheduled backups |
| `interval_hours` | 24 | Hours between backup runs |
| `retention_days` | 30 | Days to keep backups |
| `juniper_set_format` | true | Use set format for Junos |
| `include_filters` | [] | Devices to include (empty = all) |
| `exclude_patterns` | [] | Device patterns to exclude |

### Include/Exclude Filters

Include specific devices:
```json
{
  "include_filters": [
    {"tag": "production"},
    {"name_pattern": "core-*"}
  ]
}
```

Exclude patterns:
```json
{
  "exclude_patterns": [
    "lab-*",
    "test-*"
  ]
}
```

## Backup Tasks

### Task Status

Check backup task progress:

1. Navigate to **Monitor**
2. Find backup tasks
3. View status and output

### Task States

| State | Description |
|-------|-------------|
| `pending` | Waiting to run |
| `running` | Backup in progress |
| `success` | Backup completed |
| `failed` | Backup failed |

### Failed Backups

When backups fail:
1. Check device connectivity
2. Verify credentials
3. Review error message
4. Retry backup

## Integration

### MOP Integration

Trigger backups from MOPs:

```yaml
steps:
  - name: "Pre-change backup"
    id: backup
    type: http_request
    url: "http://localhost:8089/api/config-backups/run-single"
    method: POST
    body: '{"device_name": "router1"}'
    on_success: make_change
```

### Alert Integration

Configure backup alerts:
- Backup failure notifications
- Compliance alerts for changes
- Storage warnings

## API Reference

### List Backups

```bash
GET /api/config-backups
GET /api/config-backups?device=router1
GET /api/config-backups?limit=50&offset=0
```

### Get Backup

```bash
GET /api/config-backups/{id}
```

### Trigger Single Backup

```bash
POST /api/config-backups/run-single
Content-Type: application/json

{
  "device_name": "router1"
}
```

### Trigger All Device Backup

```bash
POST /api/config-backups/run-all
```

### Delete Backup

```bash
DELETE /api/config-backups/{id}
```

### Get Schedule

```bash
GET /api/backup-schedule
```

### Update Schedule

```bash
PUT /api/backup-schedule
Content-Type: application/json

{
  "enabled": true,
  "interval_hours": 24,
  "retention_days": 30
}
```

### Cleanup Old Backups

```bash
POST /api/config-backups/cleanup
Content-Type: application/json

{
  "retention_days": 30
}
```

## Best Practices

### Scheduling

- Run backups during low-traffic periods
- Stagger large deployments
- Consider timezone for scheduling

### Retention

- Balance storage vs history needs
- Keep longer retention for compliance
- Archive critical backups externally

### Monitoring

- Alert on backup failures
- Monitor storage usage
- Audit backup coverage

### Security

- Backups may contain sensitive data
- Restrict access to backup content
- Consider encryption for exports

## Troubleshooting

### Backup Timeout

```
Error: Connection timed out
```

- Increase backup timeout
- Check device load
- Verify network connectivity

### Authentication Failed

```
Error: Authentication failed
```

- Verify device credentials
- Check account permissions
- Verify SSH access

### Storage Full

```
Error: Database storage limit exceeded
```

- Reduce retention period
- Delete old backups
- Increase database storage

### Missing Backups

If scheduled backups aren't running:
1. Check Celery Beat is running
2. Verify schedule is enabled
3. Check for errors in logs

## Next Steps

- [[Device Management]] - Add devices for backup
- [[MOPs]] - Automate backup workflows
- [[Troubleshooting]] - Common issues
