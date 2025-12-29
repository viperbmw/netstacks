# Security & Production Hardening

This project can be run safely on a developer workstation with the provided defaults.
If you deploy NetStacks anywhere reachable by other users/systems, treat it like any other
network-facing automation platform: **harden it first**.

## Required changes for production

### 1) Change default credentials

- The default UI user is `admin/admin`.
- Change this immediately after the first login.

### 2) Set strong secrets (do not use defaults)

Set these via `.env` (or your secrets manager) **before** deploying:

- `POSTGRES_PASSWORD`
- `JWT_SECRET_KEY`
- `SECRET_KEY` (Flask session signing)

Generate secrets with e.g.:

```bash
python -c "import secrets; print(secrets.token_hex(32))"
```

### 3) Traefik dashboard must not be exposed

The default compose currently exposes the Traefik dashboard port `8080` and enables
Traefik's insecure API mode.

In production:

- Disable the Traefik dashboard entirely, or bind it to localhost only.
- Use authentication (and ideally a private admin network) if you must expose it.

### 4) TLS everywhere

- Terminate TLS at your reverse proxy / ingress.
- Enforce HTTPS for any authentication flows (especially OIDC).

### 5) Restrict outbound HTTP proxying

The endpoint `/api/proxy-api-call` can make outbound HTTP requests on behalf of an
authenticated user.

In production, you should:

- Add an allowlist of permitted hostnames / base URLs
- Block link-local / RFC1918 / loopback ranges (SSRF protection)
- Ensure all proxy requests are audited (user, target, time)

### 6) Network device credential handling

- Prefer per-device credentials and least-privilege accounts.
- Avoid storing cleartext credentials.
- Rotate credentials regularly.

## Recommended operational controls

- Put the app on a private network/VPN.
- Enable audit logging for config changes.
- Add rate limiting on login and sensitive endpoints.
- Run vulnerability scanning for dependencies (e.g. `pip-audit`).

## Reporting security issues

If you discover a vulnerability, please report it privately to the maintainers.

