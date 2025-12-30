# Troubleshooting

This guide covers common issues and their solutions.

## Quick Diagnostics

### Check Container Status

```bash
docker-compose ps
```

All containers should show `Up` status.

### Check Logs

```bash
# All logs
docker-compose logs

# Specific service
docker-compose logs -f netstacks
docker-compose logs -f netstacks-workers
```

### Check Resource Usage

```bash
docker stats
```

## Common Issues

### Connection Issues

#### Cannot Access Web UI

**Symptoms:**
- Browser shows connection refused
- Page doesn't load

**Solutions:**

1. Check container is running:
```bash
docker-compose ps netstacks
```

2. Check port mapping:
```bash
docker-compose port netstacks 8088
```

3. Check firewall rules:
```bash
sudo ufw status
```

4. Check container logs:
```bash
docker-compose logs netstacks | tail -50
```

#### Database Connection Failed

**Symptoms:**
```
sqlalchemy.exc.OperationalError: could not connect to server
```

**Solutions:**

1. Check PostgreSQL is running:
```bash
docker-compose ps netstacks-postgres
```

2. Verify connection string:
```bash
docker-compose exec netstacks printenv DATABASE_URL
```

3. Check PostgreSQL logs:
```bash
docker-compose logs netstacks-postgres
```

4. Restart PostgreSQL:
```bash
docker-compose restart netstacks-postgres
```

#### Redis Connection Failed

**Symptoms:**
```
redis.exceptions.ConnectionError: Error connecting to redis
```

**Solutions:**

1. Check Redis is running:
```bash
docker-compose ps netstacks-redis
```

2. Test Redis connection:
```bash
docker-compose exec netstacks-redis redis-cli ping
```

3. Restart Redis:
```bash
docker-compose restart netstacks-redis
```

### Authentication Issues

#### Login Failed

**Symptoms:**
- "Invalid credentials" error
- Cannot login with correct password

**Solutions:**

1. Verify username is correct (case-sensitive)

2. Reset admin password via database:
```bash
docker-compose exec netstacks-postgres psql -U netstacks -c \
  "UPDATE users SET password_hash = '\$2b\$12\$...' WHERE username = 'admin';"
```

3. Check authentication order if using LDAP/OIDC

4. Check logs for auth errors:
```bash
docker-compose logs netstacks | grep -i auth
```

#### LDAP Connection Failed

**Symptoms:**
- "LDAP connection failed" error
- LDAP test button fails

**Solutions:**

1. Verify server hostname and port
2. Check SSL/TLS settings
3. Test with ldapsearch:
```bash
ldapsearch -H ldap://server:389 -D "bind-dn" -W -b "base-dn" "(uid=testuser)"
```

4. Check firewall allows LDAP port

#### OIDC Callback Error

**Symptoms:**
- Error after IdP redirect
- "State mismatch" error

**Solutions:**

1. Verify redirect URI matches exactly
2. Check client ID and secret
3. Verify issuer URL is correct
4. Clear browser cookies and retry

### Device Issues

#### SSH Connection Timeout

**Symptoms:**
```
Error: Connection to device timed out
```

**Solutions:**

1. Verify device is reachable:
```bash
docker-compose exec netstacks ping -c 3 device-ip
```

2. Check SSH port:
```bash
docker-compose exec netstacks nc -zv device-ip 22
```

3. Verify credentials manually:
```bash
docker-compose exec netstacks ssh user@device-ip
```

4. Check device type is correct

#### Authentication Failed on Device

**Symptoms:**
```
Error: Authentication failed
```

**Solutions:**

1. Verify username and password
2. Check SSH is enabled on device
3. Verify user has privilege level for commands
4. Check for account lockout

#### Wrong Output from Device

**Symptoms:**
- Commands execute but output is wrong
- Missing output

**Solutions:**

1. Check device type matches actual device
2. Try alternative device type (e.g., `cisco_xe` vs `cisco_ios`)
3. Check command syntax for device platform
4. Increase command timeout

### Task/Worker Issues

#### Tasks Stuck in Queue

**Symptoms:**
- Tasks show "pending" indefinitely
- No task progress

**Solutions:**

1. Check worker is running:
```bash
docker-compose ps netstacks-workers
```

2. Check worker logs:
```bash
docker-compose logs netstacks-workers | tail -50
```

3. Check Redis has tasks:
```bash
docker-compose exec netstacks-redis redis-cli llen celery
```

4. Restart workers:
```bash
docker-compose restart netstacks-workers
```

#### Scheduled Tasks Not Running

**Symptoms:**
- Scheduled backups don't run
- Beat tasks not executing

**Solutions:**

1. Check beat is running:
```bash
docker-compose ps netstacks-workers-beat
```

2. Check beat logs:
```bash
docker-compose logs netstacks-workers-beat
```

3. Verify schedule is enabled in settings

4. Restart beat:
```bash
docker-compose restart netstacks-workers-beat
```

### Template Issues

#### Template Syntax Error

**Symptoms:**
```
jinja2.exceptions.TemplateSyntaxError
```

**Solutions:**

1. Check for matching braces: `{{ }}` and `{% %}`
2. Verify filter syntax: `{{ value | filter }}`
3. Check for missing `endif` or `endfor`
4. Preview template before saving

#### Variables Not Rendering

**Symptoms:**
- Variables show as `{{ variable }}` in output
- Empty values in output

**Solutions:**

1. Check variable names match exactly (case-sensitive)
2. Verify all required variables are provided
3. Check for typos in variable names
4. Use `| default('')` for optional variables

### Backup Issues

#### Backup Failed

**Symptoms:**
- Backup task shows failed
- No backup created

**Solutions:**

1. Check device connectivity
2. Verify credentials work
3. Check device supports show running-config
4. Check worker logs:
```bash
docker-compose logs netstacks-workers | grep backup
```

#### Backups Using Too Much Storage

**Solutions:**

1. Reduce retention period:
```bash
curl -X PUT http://localhost:8089/api/backup-schedule \
  -H "Content-Type: application/json" \
  -d '{"retention_days": 14}'
```

2. Manually cleanup:
```bash
curl -X POST http://localhost:8089/api/config-backups/cleanup \
  -H "Content-Type: application/json" \
  -d '{"retention_days": 7}'
```

3. Check database size:
```bash
docker-compose exec netstacks-postgres psql -U netstacks -c \
  "SELECT pg_size_pretty(pg_database_size('netstacks'));"
```

### AI/Agent Issues

#### LLM Connection Failed

**Symptoms:**
- "API connection failed" error
- Agent won't start

**Solutions:**

1. Verify API key is correct
2. Test connection via UI
3. Check network access to API endpoints
4. Verify provider is enabled

#### Agent Not Responding

**Symptoms:**
- Agent shows "active" but no responses
- High latency

**Solutions:**

1. Check agent logs
2. Verify LLM provider is configured
3. Reduce context size
4. Try different model

## Log Analysis

### Log Locations

| Service | Log Command |
|---------|-------------|
| Flask | `docker-compose logs netstacks` |
| Workers | `docker-compose logs netstacks-workers` |
| Beat | `docker-compose logs netstacks-workers-beat` |
| PostgreSQL | `docker-compose logs netstacks-postgres` |
| Redis | `docker-compose logs netstacks-redis` |

### Common Log Patterns

**Database Errors:**
```
sqlalchemy.exc.OperationalError
```

**Authentication Errors:**
```
Invalid credentials for user
Authentication failed
```

**Task Errors:**
```
Task raised unexpected
celery.exceptions
```

**Device Errors:**
```
Connection timed out
Authentication failed
NetmikoTimeoutException
```

## Performance Issues

### Slow Page Loads

**Solutions:**

1. Check database performance:
```bash
docker-compose exec netstacks-postgres pg_stat_activity
```

2. Add indexes if needed

3. Check Redis memory:
```bash
docker-compose exec netstacks-redis redis-cli info memory
```

4. Increase container resources

### High Memory Usage

**Solutions:**

1. Check memory limits:
```bash
docker stats
```

2. Add limits in docker-compose:
```yaml
deploy:
  resources:
    limits:
      memory: 2G
```

3. Reduce worker concurrency

### Slow Task Execution

**Solutions:**

1. Increase worker count
2. Check device response times
3. Optimize task code
4. Use task prioritization

## Recovery Procedures

### Reset Admin Password

```bash
# Generate new password hash
docker-compose exec netstacks python -c "
from werkzeug.security import generate_password_hash
print(generate_password_hash('newpassword'))
"

# Update in database
docker-compose exec netstacks-postgres psql -U netstacks -c \
  "UPDATE users SET password_hash = 'hash-from-above' WHERE username = 'admin';"
```

### Database Backup

```bash
docker-compose exec netstacks-postgres pg_dump -U netstacks netstacks > backup.sql
```

### Database Restore

```bash
cat backup.sql | docker-compose exec -T netstacks-postgres psql -U netstacks netstacks
```

### Full System Reset

```bash
# Stop and remove everything
docker-compose down -v

# Rebuild and start fresh
docker-compose up -d
```

## Getting Help

### Before Asking for Help

1. Check this troubleshooting guide
2. Search existing issues
3. Gather relevant logs
4. Note exact error messages
5. Document steps to reproduce

### Reporting Issues

Create an issue at https://github.com/viperbmw/netstacks/issues with:

- NetStacks version
- Docker/Docker Compose version
- Error messages and logs
- Steps to reproduce
- Expected vs actual behavior

## Next Steps

- [[Installation]] - Fresh installation
- [[Configuration]] - Configuration options
- [[Architecture]] - System design
