#!/usr/bin/env python3
"""
Convert Jinja2 templates to static HTML for the frontend microservice.

This script reads Jinja2 templates and converts them to static HTML files
that use JavaScript for authentication and dynamic content.
"""

import os
import re
from pathlib import Path

# Paths
TEMPLATES_DIR = Path(__file__).parent.parent / "templates"
PAGES_DIR = Path(__file__).parent.parent / "services" / "frontend" / "pages"

# Base template HTML (the navbar and common structure)
BASE_HEADER = '''<!DOCTYPE html>
<html lang="en" data-bs-theme="dark">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>{title}</title>
    <link rel="icon" type="image/svg+xml" href="/static/favicon.svg">
    <link href="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/css/bootstrap.min.css" rel="stylesheet">
    <link href="https://cdnjs.cloudflare.com/ajax/libs/font-awesome/6.4.0/css/all.min.css" rel="stylesheet">
    <link href="/static/css/style.css?v=4" rel="stylesheet">
    <link href="/static/css/assistant.css?v=2" rel="stylesheet">
</head>
<body>
    <nav class="navbar navbar-expand-lg navbar-dark bg-dark py-1">
        <div class="container-fluid py-0">
            <a class="navbar-brand brand-logo" href="/">
                <span class="brand-icon">
                    <i class="fas fa-layer-group"></i>
                </span>
                <span class="brand-text">NetStacks</span>
            </a>
            <button class="navbar-toggler" type="button" data-bs-toggle="collapse" data-bs-target="#navbarNav">
                <span class="navbar-toggler-icon"></span>
            </button>
            <div class="collapse navbar-collapse" id="navbarNav">
                <ul class="navbar-nav">
                    <!-- Operations Menu -->
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                            <i class="fas fa-play-circle"></i> Operations
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="/deploy"><i class="fas fa-rocket"></i> Deploy Config</a></li>
                            <li><a class="dropdown-item" href="/monitor"><i class="fas fa-chart-line"></i> Monitor Jobs</a></li>
                            <li><a class="dropdown-item" href="/mop"><i class="fas fa-list-check"></i> Procedures (MOP)</a></li>
                        </ul>
                    </li>
                    <!-- Configuration Menu -->
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                            <i class="fas fa-cogs"></i> Configuration
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="/devices"><i class="fas fa-server"></i> Devices & Snapshots</a></li>
                            <li><a class="dropdown-item" href="/templates"><i class="fas fa-file-code"></i> Templates</a></li>
                            <li><a class="dropdown-item" href="/service-stacks"><i class="fas fa-layer-group"></i> Service Stacks</a></li>
                        </ul>
                    </li>
                    <!-- AI Menu -->
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                            <i class="fas fa-brain"></i> AI
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="/agents"><i class="fas fa-robot"></i> Agents</a></li>
                            <li><a class="dropdown-item" href="/agents/chat"><i class="fas fa-comments"></i> Agent Chat</a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item" href="/alerts"><i class="fas fa-bell"></i> Alerts</a></li>
                            <li><a class="dropdown-item" href="/incidents"><i class="fas fa-exclamation-triangle"></i> Incidents</a></li>
                            <li><a class="dropdown-item" href="/approvals"><i class="fas fa-shield-alt"></i> Approvals</a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item" href="/knowledge"><i class="fas fa-book-open"></i> Knowledge</a></li>
                            <li><a class="dropdown-item" href="/tools"><i class="fas fa-wrench"></i> Tools</a></li>
                        </ul>
                    </li>
                    <!-- Settings Menu -->
                    <li class="nav-item dropdown">
                        <a class="nav-link dropdown-toggle" href="#" role="button" data-bs-toggle="dropdown" aria-expanded="false">
                            <i class="fas fa-cog"></i> Settings
                        </a>
                        <ul class="dropdown-menu">
                            <li><a class="dropdown-item" href="/admin"><i class="fas fa-users-cog"></i> Users & Auth</a></li>
                            <li><a class="dropdown-item" href="/settings"><i class="fas fa-sliders-h"></i> System Settings</a></li>
                            <li><a class="dropdown-item" href="/settings/ai"><i class="fas fa-brain"></i> AI Settings</a></li>
                            <li><a class="dropdown-item" href="/platform"><i class="fas fa-heartbeat"></i> Platform Health</a></li>
                            <li><a class="dropdown-item" href="/step-types"><i class="fas fa-puzzle-piece"></i> MOP Step Types</a></li>
                            <li><hr class="dropdown-divider"></li>
                            <li><a class="dropdown-item" href="/docs" target="_blank"><i class="fas fa-book"></i> NetStacks API</a></li>
                        </ul>
                    </li>
                </ul>
                <ul class="navbar-nav ms-auto">
                    <li class="nav-item">
                        <span class="nav-link text-light">
                            <i class="fas fa-user"></i> <span id="current-username">Loading...</span>
                        </span>
                    </li>
                    <li class="nav-item">
                        <span class="nav-link text-light" id="system-time-container" data-bs-toggle="tooltip" data-bs-placement="bottom" title="Loading...">
                            <i class="fas fa-clock"></i>
                        </span>
                    </li>
                    <li class="nav-item">
                        <a class="nav-link" href="#" onclick="handleLogout(event)">
                            <i class="fas fa-sign-out-alt"></i> Logout
                        </a>
                    </li>
                </ul>
            </div>
        </div>
    </nav>

    <div class="container-fluid mt-4">
        <!-- Page Content -->
'''

BASE_FOOTER = '''        <!-- End Page Content -->
    </div>

    <script src="https://cdn.jsdelivr.net/npm/bootstrap@5.3.0/dist/js/bootstrap.bundle.min.js"></script>
    <script src="https://code.jquery.com/jquery-3.7.0.min.js"></script>
    <script src="/static/js/api-client.js"></script>
    <script src="/static/js/auth-guard.js"></script>
    <script src="/static/js/timezone-utils.js"></script>
    <script src="/static/js/task-manager.js"></script>
    <script>
        let systemTimezone = 'UTC';
        let timezoneLoaded = false;

        // Load system timezone asynchronously
        async function loadSystemTimezone() {
            try {
                const response = await $.ajax({
                    url: '/api/settings',
                    method: 'GET'
                });
                if (response.success && response.settings.system_timezone) {
                    systemTimezone = response.settings.system_timezone;
                    console.log('System timezone loaded:', systemTimezone);
                }
            } catch (error) {
                systemTimezone = 'UTC';
                console.log('Failed to load system timezone, using UTC');
            }
            timezoneLoaded = true;
        }

        // Update system time tooltip every second
        function updateSystemTime() {
            const now = new Date();
            let timeString;

            try {
                const options = {
                    timeZone: systemTimezone,
                    year: 'numeric',
                    month: '2-digit',
                    day: '2-digit',
                    hour: '2-digit',
                    minute: '2-digit',
                    second: '2-digit',
                    hour12: false
                };
                const formatter = new Intl.DateTimeFormat('en-CA', options);
                const parts = formatter.formatToParts(now);
                const dateMap = {};
                parts.forEach(part => {
                    dateMap[part.type] = part.value;
                });
                timeString = `${dateMap.year}-${dateMap.month}-${dateMap.day} ${dateMap.hour}:${dateMap.minute}:${dateMap.second}`;

                if (systemTimezone === 'UTC') {
                    timeString += ' UTC';
                } else {
                    timeString += ` (${systemTimezone})`;
                }
            } catch (e) {
                timeString = now.toISOString().slice(0, 19).replace('T', ' ') + ' UTC';
            }

            const $container = $('#system-time-container');
            $container.attr('data-bs-original-title', 'Server Time: ' + timeString);
            $container.attr('title', 'Server Time: ' + timeString);
        }

        // Handle logout - clear JWT tokens and redirect
        function handleLogout(event) {
            event.preventDefault();
            if (typeof NetStacksAPI !== 'undefined') {
                NetStacksAPI.clearTokens();
            } else {
                localStorage.removeItem('netstacks_jwt_token');
                localStorage.removeItem('netstacks_jwt_refresh');
                localStorage.removeItem('netstacks_jwt_expiry');
            }
            window.location.href = '/logout';
        }

        // Initialize on page load
        $(document).ready(async function() {
            await loadSystemTimezone();
            const tooltipTriggerList = [].slice.call(document.querySelectorAll('[data-bs-toggle="tooltip"]'));
            tooltipTriggerList.map(function (tooltipTriggerEl) {
                return new bootstrap.Tooltip(tooltipTriggerEl);
            });
            updateSystemTime();
            setInterval(updateSystemTime, 1000);
        });
    </script>
{scripts}
    <!-- NetStacks AI Assistant -->
    <script src="/static/js/assistant.js?v=2"></script>
</body>
</html>
'''


def extract_title(content: str) -> str:
    """Extract title from {% block title %}...{% endblock %}"""
    match = re.search(r'{%\s*block\s+title\s*%}(.+?){%\s*endblock\s*%}', content)
    if match:
        return match.group(1).strip()
    return "NetStacks"


def extract_content(content: str) -> str:
    """Extract content from {% block content %}...{% endblock %}"""
    match = re.search(r'{%\s*block\s+content\s*%}(.+?){%\s*endblock\s*%}', content, re.DOTALL)
    if match:
        return match.group(1).strip()
    return ""


def extract_scripts(content: str) -> str:
    """Extract scripts from {% block scripts %}...{% endblock %}"""
    match = re.search(r'{%\s*block\s+scripts\s*%}(.+?){%\s*endblock\s*%}', content, re.DOTALL)
    if match:
        scripts = match.group(1).strip()
        # Convert Jinja2 url_for to static paths
        scripts = re.sub(
            r'{{\s*url_for\([\'"]static[\'"]\s*,\s*filename=[\'"]([^"\']+)[\'"]\)\s*}}',
            r'/static/\1',
            scripts
        )
        return scripts
    return ""


def convert_jinja_to_static(content: str) -> str:
    """Convert Jinja2 syntax to static HTML"""
    # Convert url_for to static paths
    content = re.sub(
        r'{{\s*url_for\([\'"]static[\'"]\s*,\s*filename=[\'"]([^"\']+)[\'"]\)\s*}}',
        r'/static/\1',
        content
    )

    # Remove {{ session.username }} - will be filled by JS
    content = re.sub(r'{{\s*session\.username\s*}}', '', content)

    # Remove other common Jinja2 constructs that should be handled by JS
    content = re.sub(r'{{\s*[^}]+\s*}}', '', content)

    # Remove Jinja2 conditionals - keep the content inside
    content = re.sub(r'{%\s*if\s+[^%]+\s*%}', '', content)
    content = re.sub(r'{%\s*else\s*%}', '', content)
    content = re.sub(r'{%\s*elif\s+[^%]+\s*%}', '', content)
    content = re.sub(r'{%\s*endif\s*%}', '', content)

    # Remove for loops - keep only static content
    content = re.sub(r'{%\s*for\s+[^%]+\s*%}', '', content)
    content = re.sub(r'{%\s*endfor\s*%}', '', content)

    # Remove any remaining Jinja2 tags
    content = re.sub(r'{%[^%]*%}', '', content)

    return content


def convert_template(template_name: str) -> bool:
    """Convert a single template to static HTML"""
    template_path = TEMPLATES_DIR / template_name

    if not template_path.exists():
        print(f"  Skipping {template_name} - not found")
        return False

    with open(template_path, 'r') as f:
        content = f.read()

    # Check if this extends base.html
    if '{% extends "base.html" %}' not in content:
        print(f"  Skipping {template_name} - doesn't extend base.html")
        return False

    # Extract parts
    title = extract_title(content)
    page_content = extract_content(content)
    scripts = extract_scripts(content)

    # Convert Jinja2 to static
    page_content = convert_jinja_to_static(page_content)

    # Build final HTML - use replace instead of format to avoid issues with curly braces in scripts
    header = BASE_HEADER.replace('{title}', title)
    footer = BASE_FOOTER.replace('{scripts}', scripts)
    final_html = header + page_content + footer

    # Write to pages directory
    output_name = template_name.replace('.html', '') + '.html'
    output_path = PAGES_DIR / output_name

    with open(output_path, 'w') as f:
        f.write(final_html)

    print(f"  Converted {template_name} -> {output_name}")
    return True


def main():
    """Convert all templates to static HTML"""
    print("Converting Jinja2 templates to static HTML...")
    print(f"Source: {TEMPLATES_DIR}")
    print(f"Destination: {PAGES_DIR}")
    print()

    # Ensure pages directory exists
    PAGES_DIR.mkdir(parents=True, exist_ok=True)

    # Skip login.html as it has a different structure
    skip_templates = ['base.html', 'login.html', 'login_redirect.html', 'index.html']

    converted = 0
    for template_file in sorted(TEMPLATES_DIR.glob('*.html')):
        if template_file.name in skip_templates:
            print(f"  Skipping {template_file.name} - in skip list")
            continue

        if convert_template(template_file.name):
            converted += 1

    print()
    print(f"Converted {converted} templates")


if __name__ == '__main__':
    main()
