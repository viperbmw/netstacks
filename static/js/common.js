// NetStacks Common JavaScript Functions
// Shared utilities across all pages

/**
 * Check platform health status and update the indicator icon
 * Uses the same /api/platform/health endpoint as the Platform Health page
 */
async function checkPlatformHealth() {
    const healthIcon = document.getElementById('health-status-icon');
    const healthIndicator = document.getElementById('platform-health-indicator');
    if (!healthIcon) return;

    try {
        const controller = new AbortController();
        const timeoutId = setTimeout(() => controller.abort(), 5000);
        const response = await fetch('/api/platform/health', {
            method: 'GET',
            signal: controller.signal
        });
        clearTimeout(timeoutId);

        if (!response.ok) {
            throw new Error('Health endpoint returned error');
        }

        const data = await response.json();

        if (data.success && data.data) {
            const services = data.data.services || {};
            const overallStatus = data.data.overall_status;

            let healthyCount = 0;
            let totalCount = 0;

            Object.values(services).forEach(s => {
                totalCount++;
                if (s.status === 'healthy') healthyCount++;
            });

            // Update icon color based on overall health
            healthIcon.classList.remove('text-secondary', 'text-success', 'text-warning', 'text-danger');

            let statusClass, titleText;
            if (overallStatus === 'healthy' || healthyCount === totalCount) {
                statusClass = 'text-success';
                titleText = 'All services healthy';
            } else if (healthyCount >= totalCount / 2) {
                statusClass = 'text-warning';
                titleText = `${healthyCount}/${totalCount} services healthy`;
            } else {
                statusClass = 'text-danger';
                titleText = `${healthyCount}/${totalCount} services healthy - Click for details`;
            }

            healthIcon.classList.add(statusClass);
            if (healthIndicator) {
                healthIndicator.setAttribute('data-bs-original-title', titleText);
                healthIndicator.setAttribute('title', titleText);
            }

            // Cache the status for page navigation
            sessionStorage.setItem('netstacks_health_status', statusClass);
            sessionStorage.setItem('netstacks_health_title', titleText);
        }
    } catch (e) {
        // API error or timeout - show unknown/gray state
        healthIcon.classList.remove('text-secondary', 'text-success', 'text-warning', 'text-danger');
        healthIcon.classList.add('text-secondary');
        if (healthIndicator) {
            healthIndicator.setAttribute('data-bs-original-title', 'Unable to check health');
            healthIndicator.setAttribute('title', 'Unable to check health');
        }
    }
}

/**
 * Handle logout - clear JWT tokens and redirect
 */
function handleLogout(event) {
    if (event) event.preventDefault();
    // Clear JWT tokens from localStorage
    if (typeof NetStacksAPI !== 'undefined') {
        NetStacksAPI.clearTokens();
    } else {
        localStorage.removeItem('netstacks_jwt_token');
        localStorage.removeItem('netstacks_jwt_refresh');
        localStorage.removeItem('netstacks_jwt_expiry');
    }
    // Redirect to logout endpoint
    window.location.href = '/logout';
}

// Initialize common functionality on page load
document.addEventListener('DOMContentLoaded', function() {
    // Only run health check if we haven't checked recently (within 30 seconds)
    // This prevents redundant API calls when navigating between pages
    const lastCheck = sessionStorage.getItem('netstacks_health_last_check');
    const now = Date.now();
    const HEALTH_CHECK_INTERVAL = 30000; // 30 seconds

    if (!lastCheck || (now - parseInt(lastCheck)) > HEALTH_CHECK_INTERVAL) {
        checkPlatformHealth();
        sessionStorage.setItem('netstacks_health_last_check', now.toString());
    } else {
        // Restore the last known health state from session storage
        const lastStatus = sessionStorage.getItem('netstacks_health_status');
        if (lastStatus) {
            const healthIcon = document.getElementById('health-status-icon');
            const healthIndicator = document.getElementById('platform-health-indicator');
            if (healthIcon) {
                healthIcon.classList.remove('text-secondary', 'text-success', 'text-warning', 'text-danger');
                healthIcon.classList.add(lastStatus);
            }
            const lastTitle = sessionStorage.getItem('netstacks_health_title');
            if (healthIndicator && lastTitle) {
                healthIndicator.setAttribute('title', lastTitle);
            }
        }
    }

    // Set up interval for periodic health checks (every 30 seconds)
    setInterval(function() {
        checkPlatformHealth();
        sessionStorage.setItem('netstacks_health_last_check', Date.now().toString());
    }, HEALTH_CHECK_INTERVAL);
});
