// Timezone utilities for NetStacks Pro

/**
 * Get user's preferred timezone from settings
 * @returns {string} IANA timezone string (e.g., 'America/New_York')
 */
function getUserTimezone() {
    try {
        const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
        const tzSetting = settings.timezone || 'auto';

        if (tzSetting === 'auto') {
            // Return browser timezone
            return Intl.DateTimeFormat().resolvedOptions().timeZone;
        }

        return tzSetting;
    } catch (e) {
        console.error('Error getting timezone:', e);
        // Fallback to browser timezone
        return Intl.DateTimeFormat().resolvedOptions().timeZone;
    }
}

/**
 * Format a UTC datetime string to user's local timezone
 * @param {string} utcDateString - ISO 8601 UTC datetime string
 * @param {object} options - Intl.DateTimeFormat options
 * @returns {string} Formatted datetime string in user's timezone
 */
function formatDateInUserTimezone(utcDateString, options = {}) {
    if (!utcDateString) return 'N/A';

    try {
        const date = new Date(utcDateString);
        const userTz = getUserTimezone();

        const defaultOptions = {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true,
            timeZone: userTz
        };

        const formatOptions = { ...defaultOptions, ...options };

        return new Intl.DateTimeFormat('en-US', formatOptions).format(date);
    } catch (e) {
        console.error('Error formatting date:', e);
        return utcDateString;
    }
}

/**
 * Format a UTC datetime string to user's local timezone (short format)
 * @param {string} utcDateString - ISO 8601 UTC datetime string
 * @returns {string} Formatted datetime string
 */
function formatDateShort(utcDateString) {
    return formatDateInUserTimezone(utcDateString, {
        year: 'numeric',
        month: 'numeric',
        day: 'numeric',
        hour: 'numeric',
        minute: '2-digit',
        hour12: true
    });
}

/**
 * Convert local datetime-local input value to UTC ISO string
 * @param {string} localDateTimeString - Local datetime string from datetime-local input
 * @returns {string} UTC ISO string
 */
function localToUTC(localDateTimeString) {
    if (!localDateTimeString) return null;

    try {
        const localDate = new Date(localDateTimeString);
        return localDate.toISOString();
    } catch (e) {
        console.error('Error converting to UTC:', e);
        return null;
    }
}

/**
 * Convert UTC ISO string to local datetime-local input value
 * @param {string} utcISOString - UTC ISO 8601 string
 * @returns {string} Local datetime string for datetime-local input
 */
function utcToLocal(utcISOString) {
    if (!utcISOString) return '';

    try {
        const utcDate = new Date(utcISOString);
        // Get local datetime in YYYY-MM-DDTHH:mm format for datetime-local input
        const localDateTime = new Date(utcDate.getTime() - utcDate.getTimezoneOffset() * 60000)
            .toISOString().slice(0, 16);
        return localDateTime;
    } catch (e) {
        console.error('Error converting to local:', e);
        return '';
    }
}

/**
 * Get current time in user's timezone
 * @returns {string} Formatted current time
 */
function getCurrentTimeInUserTimezone() {
    const now = new Date();
    return formatDateInUserTimezone(now.toISOString());
}

/**
 * Get timezone abbreviation (e.g., 'EST', 'PST')
 * @returns {string} Timezone abbreviation
 */
function getTimezoneAbbreviation() {
    try {
        const userTz = getUserTimezone();
        const now = new Date();
        const formatter = new Intl.DateTimeFormat('en-US', {
            timeZone: userTz,
            timeZoneName: 'short'
        });

        const parts = formatter.formatToParts(now);
        const tzPart = parts.find(part => part.type === 'timeZoneName');

        return tzPart ? tzPart.value : '';
    } catch (e) {
        console.error('Error getting timezone abbreviation:', e);
        return '';
    }
}

// Export to window for global access
if (typeof window !== 'undefined') {
    window.getUserTimezone = getUserTimezone;
    window.formatDateInUserTimezone = formatDateInUserTimezone;
    window.formatDateShort = formatDateShort;
    window.localToUTC = localToUTC;
    window.utcToLocal = utcToLocal;
    window.getCurrentTimeInUserTimezone = getCurrentTimeInUserTimezone;
    window.getTimezoneAbbreviation = getTimezoneAbbreviation;
}
