/**
 * Auth Guard - Client-side authentication check
 *
 * Include this script on pages that require authentication.
 * It checks for a valid JWT and redirects to login if missing.
 */

(function() {
    'use strict';

    // Check if we're on the login page - don't redirect
    if (window.location.pathname === '/login' || window.location.pathname === '/logout') {
        return;
    }

    // Check for JWT token
    const token = localStorage.getItem('netstacks_jwt_token');
    const tokenExpiry = localStorage.getItem('netstacks_jwt_expiry');

    if (!token) {
        // No token - redirect to login
        console.log('No JWT token found, redirecting to login');
        window.location.href = '/login';
        return;
    }

    // Check if token is expired
    if (tokenExpiry && Date.now() >= parseInt(tokenExpiry)) {
        // Token expired - try refresh or redirect
        const refreshToken = localStorage.getItem('netstacks_jwt_refresh');
        if (refreshToken) {
            // Will be handled by api-client.js on first API call
            console.log('JWT token expired, will attempt refresh on first API call');
        } else {
            console.log('JWT token expired and no refresh token, redirecting to login');
            localStorage.removeItem('netstacks_jwt_token');
            localStorage.removeItem('netstacks_jwt_expiry');
            window.location.href = '/login';
            return;
        }
    }

    // Parse JWT to get username
    function parseJwt(token) {
        try {
            const base64Url = token.split('.')[1];
            const base64 = base64Url.replace(/-/g, '+').replace(/_/g, '/');
            const jsonPayload = decodeURIComponent(atob(base64).split('').map(function(c) {
                return '%' + ('00' + c.charCodeAt(0).toString(16)).slice(-2);
            }).join(''));
            return JSON.parse(jsonPayload);
        } catch (e) {
            console.error('Error parsing JWT:', e);
            return null;
        }
    }

    // Set username in navbar when DOM is ready
    document.addEventListener('DOMContentLoaded', function() {
        const payload = parseJwt(token);
        if (payload && payload.sub) {
            const usernameElement = document.getElementById('current-username');
            if (usernameElement) {
                usernameElement.textContent = payload.sub;
            }
        }
    });
})();
