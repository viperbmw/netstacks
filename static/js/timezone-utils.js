// Timezone utilities for NetStacks

/**
 * Get system timezone from global variable (set in base.html)
 * @returns {string} IANA timezone string (e.g., 'America/New_York')
 */
function getUserTimezone() {
    try {
        // Use global systemTimezone variable if available (set in base.html)
        if (typeof systemTimezone !== 'undefined' && systemTimezone) {
            return systemTimezone;
        }

        // Fallback to localStorage for backwards compatibility
        const settings = JSON.parse(localStorage.getItem('netstacks_settings') || '{}');
        const tzSetting = settings.system_timezone || settings.timezone;

        if (tzSetting && tzSetting !== 'auto') {
            return tzSetting;
        }

        // Final fallback to UTC
        return 'UTC';
    } catch (e) {
        console.error('Error getting timezone:', e);
        return 'UTC';
    }
}

/**
 * Format a datetime string from the backend
 * Note: Times from the backend are stored in the container's local timezone (configured via TZ env var)
 * but are sent as ISO strings without timezone offset. We just display them as-is.
 * @param {string} dateString - ISO 8601 datetime string from backend (in system timezone, no offset)
 * @param {object} options - Intl.DateTimeFormat options
 * @returns {string} Formatted datetime string
 */
function formatDateInUserTimezone(dateString, options = {}) {
    if (!dateString) return 'N/A';

    try {
        // The backend stores times in local timezone but without offset info
        // e.g., "2025-10-15T14:28:00" means 2:28 PM in the system's timezone
        // We just need to display it as-is, since it's already in the correct timezone

        // Extract date/time components
        const match = dateString.match(/^(\d{4})-(\d{2})-(\d{2})T(\d{2}):(\d{2}):(\d{2})/);
        if (!match) {
            // Fallback: try parsing as-is
            return new Date(dateString).toLocaleString('en-US', {
                year: 'numeric',
                month: '2-digit',
                day: '2-digit',
                hour: '2-digit',
                minute: '2-digit',
                second: '2-digit',
                hour12: true
            });
        }

        const [_, year, month, day, hour, minute, second] = match;

        // Simply format the components directly without any timezone conversion
        const date = new Date(
            parseInt(year),
            parseInt(month) - 1,  // Month is 0-indexed
            parseInt(day),
            parseInt(hour),
            parseInt(minute),
            parseInt(second)
        );

        const defaultOptions = {
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true
        };

        const formatOptions = { ...defaultOptions, ...options };

        return new Intl.DateTimeFormat('en-US', formatOptions).format(date);
    } catch (e) {
        console.error('Error formatting date:', e);
        return dateString;
    }
}

/**
 * Simple wrapper to format any date in system timezone
 * @param {Date|string} date - Date object or ISO string
 * @returns {string} Formatted datetime string in system timezone
 */
function formatDate(date) {
    if (!date) return 'N/A';
    try {
        const dateObj = date instanceof Date ? date : new Date(date);
        const systemTz = getUserTimezone();
        return dateObj.toLocaleString('en-US', {
            timeZone: systemTz,
            year: 'numeric',
            month: '2-digit',
            day: '2-digit',
            hour: '2-digit',
            minute: '2-digit',
            second: '2-digit',
            hour12: true
        });
    } catch (e) {
        console.error('Error formatting date:', e);
        return String(date);
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
    window.formatDate = formatDate;
    window.formatDateInUserTimezone = formatDateInUserTimezone;
    window.formatDateShort = formatDateShort;
    window.localToUTC = localToUTC;
    window.utcToLocal = utcToLocal;
    window.getCurrentTimeInUserTimezone = getCurrentTimeInUserTimezone;
    window.getTimezoneAbbreviation = getTimezoneAbbreviation;
}
