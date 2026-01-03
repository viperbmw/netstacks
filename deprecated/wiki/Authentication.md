# Authentication

NetStacks supports multiple authentication methods that can be used individually or in combination.

## Authentication Methods

| Method | Description |
|--------|-------------|
| **Local** | Database-backed username/password |
| **LDAP** | Active Directory / LDAP integration |
| **OIDC** | OAuth2 / OpenID Connect (SSO) |

## Priority-Based Authentication

When multiple methods are enabled, NetStacks tries them in priority order:

1. Check credentials against each method in priority order
2. First successful authentication wins
3. User is logged in with that method's context

### Setting Priority

1. Navigate to **Settings → Authentication**
2. Set priority number for each method (lower = higher priority)
3. Example: Local (10), LDAP (20), OIDC (30)

## Local Authentication

Default database-backed authentication.

### Configuration

1. Navigate to **Settings → Authentication**
2. Local auth is enabled by default
3. Set priority (default: 10)

### User Management

1. Go to **Settings → Users**
2. Add users with username/password
3. Users can change password via profile

### Password Requirements

- Minimum 8 characters
- Stored with bcrypt hashing
- No password history enforced

## LDAP / Active Directory

Integrate with enterprise directory services.

### Configuration

1. Navigate to **Settings → Authentication**
2. Click **LDAP** tab
3. Configure settings:

| Setting | Example | Description |
|---------|---------|-------------|
| Server | `ldap.example.com` | LDAP server hostname |
| Port | `389` (LDAP) or `636` (LDAPS) | Server port |
| Use SSL | `true` | Enable SSL/TLS |
| Use StartTLS | `true` | Use STARTTLS upgrade |
| Base DN | `dc=example,dc=com` | Search base |
| User Filter | `(uid={username})` | User lookup filter |
| Bind DN | `cn=admin,dc=example,dc=com` | Admin bind DN (optional) |
| Bind Password | `****` | Admin bind password |

4. Click **Test Connection**
5. Toggle **Enabled**
6. Click **Save**

### User Filter Examples

**Active Directory:**
```
(sAMAccountName={username})
```

**OpenLDAP:**
```
(uid={username})
```

**Email-based:**
```
(mail={username})
```

### Auto-Provisioning

When enabled, LDAP users are automatically created on first login:

- Username from LDAP
- No local password (LDAP auth only)
- Default role assigned

### Troubleshooting LDAP

**Connection Failed:**
- Verify server hostname and port
- Check firewall rules
- Test with `ldapsearch` CLI

**Authentication Failed:**
- Verify user filter is correct
- Check user exists in LDAP
- Verify password is correct

**SSL/TLS Issues:**
- Verify certificate is valid
- Try disabling certificate verification (not recommended for production)

## OAuth2 / OpenID Connect (OIDC)

Single Sign-On with identity providers.

### Supported Providers

- Google
- Microsoft Azure AD
- Okta
- Auth0
- Keycloak
- Any OIDC-compliant provider

### Configuration

1. Create OAuth2 application in your IdP
2. Note Client ID and Client Secret
3. Navigate to **Settings → Authentication → OIDC**
4. Configure settings:

| Setting | Description |
|---------|-------------|
| Issuer URL | Your IdP's issuer URL |
| Client ID | OAuth2 client ID |
| Client Secret | OAuth2 client secret |
| Redirect URI | `http://your-server:8089/login/oidc/callback` |

5. Click **Test Configuration**
6. Toggle **Enabled**
7. Click **Save**

### Provider-Specific Setup

#### Google

1. Go to [Google Cloud Console](https://console.cloud.google.com)
2. Create OAuth 2.0 Client ID
3. Add authorized redirect URI
4. Use issuer: `https://accounts.google.com`

#### Azure AD

1. Go to [Azure Portal](https://portal.azure.com)
2. Register application in Azure AD
3. Create client secret
4. Use issuer: `https://login.microsoftonline.com/{tenant-id}/v2.0`

#### Okta

1. Create OIDC Web Application in Okta
2. Note client credentials
3. Use issuer: `https://{your-domain}.okta.com`

### Login Flow

1. User clicks "Sign in with SSO"
2. Redirected to identity provider
3. User authenticates with IdP
4. Redirected back to NetStacks
5. Session created automatically

### Auto-Provisioning

OIDC users are automatically provisioned:
- Username from OIDC claim (usually email)
- No local password
- Linked to OIDC provider

## Session Management

### Session Settings

| Setting | Default | Description |
|---------|---------|-------------|
| Session timeout | 24 hours | Time until session expires |
| Remember me | 7 days | Extended session duration |

### JWT Tokens

NetStacks uses JWT for API authentication:

```bash
# Get token
curl -X POST http://localhost:8089/login \
  -d "username=admin&password=admin"

# Use token
curl http://localhost:8089/api/devices \
  -H "Authorization: Bearer {token}"
```

### Logout

Logging out:
- Invalidates session
- Clears cookies
- For OIDC, may redirect to IdP logout

## User Badges

Users show their authentication source:

| Badge | Meaning |
|-------|---------|
| 🔑 Local | Database authentication |
| 📁 LDAP | LDAP/AD authentication |
| 🔐 SSO | OIDC authentication |

## Security Best Practices

### General

- Use HTTPS in production
- Set strong secret keys
- Enable session timeout
- Audit login attempts

### Local Auth

- Require strong passwords
- Change default admin password
- Limit admin accounts

### LDAP

- Use LDAPS or StartTLS
- Use service account for binds
- Restrict search base
- Monitor failed attempts

### OIDC

- Use authorization code flow
- Validate tokens properly
- Implement logout correctly
- Rotate client secrets

## API Authentication

### Session-Based

Web UI uses session cookies automatically.

### Token-Based

For API access:

```bash
# Login and get token
TOKEN=$(curl -s -X POST http://localhost:8089/api/auth/login \
  -H "Content-Type: application/json" \
  -d '{"username":"admin","password":"admin"}' | jq -r '.token')

# Use token
curl http://localhost:8089/api/devices \
  -H "Authorization: Bearer $TOKEN"
```

## Troubleshooting

### "Invalid credentials"

1. Verify username is correct
2. Check password (case-sensitive)
3. For LDAP: verify user exists in directory
4. Check authentication priority order

### "OIDC callback error"

1. Verify redirect URI matches exactly
2. Check client ID and secret
3. Verify issuer URL is correct
4. Check browser console for errors

### "Session expired"

1. Login again
2. Check session timeout settings
3. Verify system clock is synchronized

### "Account locked"

1. Contact administrator
2. Check for failed login attempts
3. Verify account status in LDAP/IdP

## Next Steps

- [[User Management]] - Managing user accounts
- [[Settings]] - Platform configuration
- [[API Reference]] - Authentication API details
