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

            if (overallStatus === 'healthy' || healthyCount === totalCount) {
                healthIcon.classList.add('text-success');
                if (healthIndicator) {
                    healthIndicator.setAttribute('data-bs-original-title', 'All services healthy');
                    healthIndicator.setAttribute('title', 'All services healthy');
                }
            } else if (healthyCount >= totalCount / 2) {
                healthIcon.classList.add('text-warning');
                if (healthIndicator) {
                    healthIndicator.setAttribute('data-bs-original-title', `${healthyCount}/${totalCount} services healthy`);
                    healthIndicator.setAttribute('title', `${healthyCount}/${totalCount} services healthy`);
                }
            } else {
                healthIcon.classList.add('text-danger');
                if (healthIndicator) {
                    healthIndicator.setAttribute('data-bs-original-title', `${healthyCount}/${totalCount} services healthy - Click for details`);
                    healthIndicator.setAttribute('title', `${healthyCount}/${totalCount} services healthy - Click for details`);
                }
            }
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
    // Check platform health immediately and every 30 seconds
    checkPlatformHealth();
    setInterval(checkPlatformHealth, 30000);
});
