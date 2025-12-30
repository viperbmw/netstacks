/**
 * NetStacks API Client
 *
 * Handles JWT token management and authenticated API calls.
 * All API requests to microservices should use this client.
 */

const NetStacksAPI = (function() {
    const TOKEN_KEY = 'netstacks_jwt_token';
    const REFRESH_TOKEN_KEY = 'netstacks_jwt_refresh';
    const TOKEN_EXPIRY_KEY = 'netstacks_jwt_expiry';

    // Track if we're currently refreshing to prevent concurrent refreshes
    let refreshPromise = null;

    /**
     * Store JWT tokens in localStorage
     */
    function storeTokens(accessToken, refreshToken, expiresIn) {
        localStorage.setItem(TOKEN_KEY, accessToken);
        if (refreshToken) {
            localStorage.setItem(REFRESH_TOKEN_KEY, refreshToken);
        }
        // Store expiry time (subtract 60 seconds for buffer)
        const expiryTime = Date.now() + ((expiresIn - 60) * 1000);
        localStorage.setItem(TOKEN_EXPIRY_KEY, expiryTime.toString());
    }

    /**
     * Get the current access token
     */
    function getToken() {
        return localStorage.getItem(TOKEN_KEY);
    }

    /**
     * Get the refresh token
     */
    function getRefreshToken() {
        return localStorage.getItem(REFRESH_TOKEN_KEY);
    }

    /**
     * Check if the current token is expired
     */
    function isTokenExpired() {
        const expiry = localStorage.getItem(TOKEN_EXPIRY_KEY);
        if (!expiry) return true;
        return Date.now() >= parseInt(expiry);
    }

    /**
     * Clear all tokens (logout)
     */
    function clearTokens() {
        localStorage.removeItem(TOKEN_KEY);
        localStorage.removeItem(REFRESH_TOKEN_KEY);
        localStorage.removeItem(TOKEN_EXPIRY_KEY);
    }

    /**
     * Refresh the access token using the refresh token
     */
    async function refreshAccessToken() {
        // If already refreshing, wait for that to complete
        if (refreshPromise) {
            return refreshPromise;
        }

        const refreshToken = getRefreshToken();
        if (!refreshToken) {
            console.warn('No refresh token available');
            return false;
        }

        refreshPromise = fetch('/api/auth/refresh', {
            method: 'POST',
            headers: {
                'Content-Type': 'application/json'
            },
            body: JSON.stringify({ refresh_token: refreshToken })
        })
        .then(response => {
            if (response.ok) {
                return response.json();
            }
            throw new Error('Token refresh failed');
        })
        .then(data => {
            storeTokens(
                data.access_token,
                data.refresh_token || refreshToken,
                data.expires_in || 1800
            );
            console.log('JWT token refreshed successfully');
            return true;
        })
        .catch(error => {
            console.error('Error refreshing token:', error);
            clearTokens();
            return false;
        })
        .finally(() => {
            refreshPromise = null;
        });

        return refreshPromise;
    }

    /**
     * Ensure we have a valid token, refreshing if necessary
     */
    async function ensureValidToken() {
        if (!getToken()) {
            return false;
        }

        if (isTokenExpired()) {
            return await refreshAccessToken();
        }

        return true;
    }

    /**
     * Login and get JWT tokens
     */
    async function login(username, password) {
        try {
            const response = await fetch('/api/auth/login', {
                method: 'POST',
                headers: {
                    'Content-Type': 'application/json'
                },
                body: JSON.stringify({ username, password })
            });

            if (response.ok) {
                const data = await response.json();
                storeTokens(
                    data.access_token,
                    data.refresh_token,
                    data.expires_in || 1800
                );
                return { success: true, user: data.user };
            } else {
                const error = await response.json();
                return { success: false, error: error.detail || 'Login failed' };
            }
        } catch (error) {
            console.error('Login error:', error);
            return { success: false, error: 'Connection error' };
        }
    }

    /**
     * Make an authenticated API request
     *
     * @param {string} url - The API endpoint URL
     * @param {object} options - Fetch options (method, body, etc.)
     * @returns {Promise<Response>} - The fetch response
     */
    async function request(url, options = {}) {
        // Ensure we have a valid token
        const hasValidToken = await ensureValidToken();

        // Set up headers
        const headers = {
            'Content-Type': 'application/json',
            'Accept': 'application/json',
            ...options.headers
        };

        // Add authorization header if we have a token
        const token = getToken();
        if (token) {
            headers['Authorization'] = `Bearer ${token}`;
        }

        // Make the request
        let response = await fetch(url, {
            ...options,
            headers
        });

        // If 401, try to refresh token and retry once
        if (response.status === 401 && hasValidToken) {
            const refreshed = await refreshAccessToken();
            if (refreshed) {
                headers['Authorization'] = `Bearer ${getToken()}`;
                response = await fetch(url, {
                    ...options,
                    headers
                });
            }
        }

        return response;
    }

    /**
     * GET request helper
     */
    async function get(url) {
        const response = await request(url, { method: 'GET' });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || error.error || `HTTP ${response.status}`);
        }
        return response.json();
    }

    /**
     * POST request helper
     */
    async function post(url, data) {
        const response = await request(url, {
            method: 'POST',
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || error.error || `HTTP ${response.status}`);
        }
        return response.json();
    }

    /**
     * PUT request helper
     */
    async function put(url, data) {
        const response = await request(url, {
            method: 'PUT',
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || error.error || `HTTP ${response.status}`);
        }
        return response.json();
    }

    /**
     * PATCH request helper
     */
    async function patch(url, data) {
        const response = await request(url, {
            method: 'PATCH',
            body: JSON.stringify(data)
        });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || error.error || `HTTP ${response.status}`);
        }
        return response.json();
    }

    /**
     * DELETE request helper
     */
    async function del(url) {
        const response = await request(url, { method: 'DELETE' });
        if (!response.ok) {
            const error = await response.json().catch(() => ({ detail: 'Request failed' }));
            throw new Error(error.detail || error.error || `HTTP ${response.status}`);
        }
        return response.json();
    }

    /**
     * jQuery AJAX wrapper for backward compatibility
     * Use this to replace $.ajax calls with authenticated requests
     */
    function ajax(options) {
        return new Promise(async (resolve, reject) => {
            try {
                await ensureValidToken();

                const token = getToken();
                const headers = {
                    'Content-Type': 'application/json',
                    'Accept': 'application/json',
                    ...options.headers
                };

                if (token) {
                    headers['Authorization'] = `Bearer ${token}`;
                }

                $.ajax({
                    ...options,
                    headers,
                    success: function(data) {
                        if (options.success) options.success(data);
                        resolve(data);
                    },
                    error: async function(xhr, status, error) {
                        // Try refresh on 401
                        if (xhr.status === 401) {
                            const refreshed = await refreshAccessToken();
                            if (refreshed) {
                                headers['Authorization'] = `Bearer ${getToken()}`;
                                $.ajax({
                                    ...options,
                                    headers,
                                    success: function(data) {
                                        if (options.success) options.success(data);
                                        resolve(data);
                                    },
                                    error: function(xhr, status, error) {
                                        if (options.error) options.error(xhr, status, error);
                                        reject(new Error(xhr.responseJSON?.error || error));
                                    }
                                });
                                return;
                            }
                        }
                        if (options.error) options.error(xhr, status, error);
                        reject(new Error(xhr.responseJSON?.error || error));
                    }
                });
            } catch (err) {
                if (options.error) options.error(null, 'error', err.message);
                reject(err);
            }
        });
    }

    /**
     * Check if user is authenticated
     */
    function isAuthenticated() {
        return !!getToken() && !isTokenExpired();
    }

    /**
     * Logout - clear tokens and redirect to login
     */
    function logout() {
        clearTokens();
        window.location.href = '/logout';
    }

    // Public API
    return {
        login,
        logout,
        isAuthenticated,
        getToken,
        clearTokens,
        ensureValidToken,
        request,
        get,
        post,
        put,
        patch,
        delete: del,
        ajax
    };
})();

// Export for use in modules if needed
if (typeof module !== 'undefined' && module.exports) {
    module.exports = NetStacksAPI;
}

/**
 * jQuery AJAX Prefilter
 *
 * Automatically adds JWT token to all jQuery AJAX requests.
 * This makes all existing $.ajax, $.get, $.post calls work with JWT auth
 * without requiring code changes.
 */
(function() {
    // Wait for jQuery to be available
    if (typeof $ === 'undefined' && typeof jQuery === 'undefined') {
        console.warn('jQuery not available, skipping AJAX prefilter setup');
        return;
    }

    const jq = $ || jQuery;

    // Set up the prefilter to add JWT token to all requests
    jq.ajaxPrefilter(function(options, originalOptions, jqXHR) {
        // Only add token for same-origin requests (not cross-domain)
        if (options.crossDomain) {
            return;
        }

        // Get the current token
        const token = NetStacksAPI.getToken();

        if (token) {
            // Add Authorization header
            jqXHR.setRequestHeader('Authorization', 'Bearer ' + token);
        }
    });

    // Set up a global error handler for 401 responses
    jq(document).ajaxError(function(event, jqXHR, settings, thrownError) {
        if (jqXHR.status === 401) {
            // Don't redirect if already on login page or if it's a settings/non-critical API
            if (window.location.pathname === '/login') {
                return;
            }

            // For settings API, just log and continue - session auth will handle it
            if (settings.url && settings.url.includes('/api/settings')) {
                console.log('Settings API returned 401, session auth in use');
                return;
            }

            // Token might be expired, try to refresh
            console.log('Got 401, attempting token refresh...');

            // If we have a refresh token, try to refresh
            const refreshToken = localStorage.getItem('netstacks_jwt_refresh');
            if (refreshToken) {
                // Attempt to refresh the token
                fetch('/api/auth/refresh', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ refresh_token: refreshToken })
                })
                .then(response => {
                    if (response.ok) {
                        return response.json();
                    }
                    throw new Error('Refresh failed');
                })
                .then(data => {
                    // Store new tokens
                    localStorage.setItem('netstacks_jwt_token', data.access_token);
                    if (data.refresh_token) {
                        localStorage.setItem('netstacks_jwt_refresh', data.refresh_token);
                    }
                    const expiryTime = Date.now() + ((data.expires_in - 60) * 1000);
                    localStorage.setItem('netstacks_jwt_expiry', expiryTime.toString());
                    console.log('Token refreshed successfully');
                    // Note: The original request will still fail, but subsequent requests will work
                })
                .catch(err => {
                    console.warn('Token refresh failed');
                    // Clear tokens but don't redirect - session auth may still be valid
                    NetStacksAPI.clearTokens();
                });
            } else {
                // No refresh token - don't redirect, session auth may still work
                console.log('No JWT refresh token, using session auth');
            }
        }
    });

    console.log('NetStacksAPI: jQuery AJAX prefilter configured for JWT authentication');
})();
