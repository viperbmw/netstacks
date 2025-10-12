// Credential Profile Management
// Stores credentials securely in browser's localStorage

const CRED_STORAGE_KEY = 'netstacks_credential_profiles';

// Load credential profiles on page load
$(document).ready(function() {
    loadCredentialProfiles();
    setupCredentialHandlers();
});

function setupCredentialHandlers() {
    // Get Config credential handlers
    $('#get-cred-profile').change(function() {
        const profileName = $(this).val();
        if (profileName) {
            loadCredentialProfile(profileName, 'get');
        }
    });

    $('#get-save-creds').click(function() {
        saveCredentialProfile('get');
    });

    $('#get-delete-creds').click(function() {
        deleteCredentialProfile($('#get-cred-profile').val());
    });

    // Set Config credential handlers
    $('#set-cred-profile').change(function() {
        const profileName = $(this).val();
        if (profileName) {
            loadCredentialProfile(profileName, 'set');
        }
    });

    $('#set-save-creds').click(function() {
        saveCredentialProfile('set');
    });

    $('#set-delete-creds').click(function() {
        deleteCredentialProfile($('#set-cred-profile').val());
    });
}

function getCredentialProfiles() {
    const stored = localStorage.getItem(CRED_STORAGE_KEY);
    return stored ? JSON.parse(stored) : {};
}

function saveCredentialProfiles(profiles) {
    localStorage.setItem(CRED_STORAGE_KEY, JSON.stringify(profiles));
}

function loadCredentialProfiles() {
    const profiles = getCredentialProfiles();
    const getSelect = $('#get-cred-profile');
    const setSelect = $('#set-cred-profile');

    // Clear existing options except the first one
    getSelect.find('option:not(:first)').remove();
    setSelect.find('option:not(:first)').remove();

    // Add profile options
    Object.keys(profiles).sort().forEach(function(profileName) {
        getSelect.append(`<option value="${profileName}">${profileName}</option>`);
        setSelect.append(`<option value="${profileName}">${profileName}</option>`);
    });
}

function saveCredentialProfile(formType) {
    const username = $(`#${formType}-username`).val();
    const password = $(`#${formType}-password`).val();

    if (!username || !password) {
        alert('Please enter username and password first');
        return;
    }

    const profileName = prompt('Enter a name for this credential profile:');
    if (!profileName) {
        return;
    }

    // WARNING: Storing passwords in localStorage is NOT secure!
    // For production, use a proper secret management solution
    const profiles = getCredentialProfiles();
    profiles[profileName] = {
        username: username,
        // Simple Base64 encoding (NOT encryption - just obfuscation)
        password: btoa(password),
        created: new Date().toISOString()
    };

    saveCredentialProfiles(profiles);
    loadCredentialProfiles();

    // Select the newly created profile
    $(`#${formType}-cred-profile`).val(profileName);

    alert(`Credential profile "${profileName}" saved successfully!\n\nWARNING: Credentials are stored in browser localStorage. Clear them before using shared computers.`);
}

function loadCredentialProfile(profileName, formType) {
    const profiles = getCredentialProfiles();
    const profile = profiles[profileName];

    if (!profile) {
        alert('Profile not found');
        return;
    }

    $(`#${formType}-username`).val(profile.username);
    // Decode the Base64 encoded password
    $(`#${formType}-password`).val(atob(profile.password));
}

function deleteCredentialProfile(profileName) {
    if (!profileName) {
        alert('Please select a profile to delete');
        return;
    }

    if (!confirm(`Are you sure you want to delete the profile "${profileName}"?`)) {
        return;
    }

    const profiles = getCredentialProfiles();
    delete profiles[profileName];
    saveCredentialProfiles(profiles);
    loadCredentialProfiles();

    alert(`Profile "${profileName}" deleted`);
}

// Add a function to clear all credentials (for security)
function clearAllCredentials() {
    if (confirm('Are you sure you want to delete ALL saved credential profiles?')) {
        localStorage.removeItem(CRED_STORAGE_KEY);
        loadCredentialProfiles();
        alert('All credential profiles cleared');
    }
}
