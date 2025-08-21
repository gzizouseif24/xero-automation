// Configuration
const API_BASE = 'http://localhost:8000/api';

// Global State
let currentStep = 1;
let uploadedFiles = [];
let validationResult = null;
let consolidationResult = null;

// Initialize
document.addEventListener('DOMContentLoaded', () => {
    checkAuthStatus();
    setupDragAndDrop();
    initializeTheme();
});

// Theme Management
function initializeTheme() {
    // Check for saved theme preference or default to light mode
    const savedTheme = localStorage.getItem('theme') || 'light';
    setTheme(savedTheme);
}

function toggleTheme() {
    const currentTheme = document.documentElement.getAttribute('data-theme') || 'light';
    const newTheme = currentTheme === 'light' ? 'dark' : 'light';
    setTheme(newTheme);
}

function setTheme(theme) {
    document.documentElement.setAttribute('data-theme', theme);
    localStorage.setItem('theme', theme);

    // Update theme toggle button
    const themeToggle = document.querySelector('.theme-toggle');
    if (themeToggle) {
        themeToggle.innerHTML = theme === 'light' ? '<i class="fas fa-moon"></i>' : '<i class="fas fa-sun"></i>';
        themeToggle.title = theme === 'light' ? 'Switch to Dark Mode' : 'Switch to Light Mode';
    }
}

// Step Management
function setActiveStep(stepNumber) {
    // Hide all content
    for (let i = 1; i <= 5; i++) {
        document.getElementById(`step-${i}-content`)?.classList.add('hidden');
        document.getElementById(`step-${i}`).classList.remove('active', 'completed');
    }

    // Show current content
    document.getElementById(`step-${stepNumber}-content`)?.classList.remove('hidden');

    // Update step indicators
    for (let i = 1; i < stepNumber; i++) {
        document.getElementById(`step-${i}`).classList.add('completed');
    }
    document.getElementById(`step-${stepNumber}`).classList.add('active');

    currentStep = stepNumber;
}

// Step 1: Authentication
async function checkAuthStatus() {
    try {
        const response = await fetch(`${API_BASE}/auth/status`);
        const data = await response.json();

        const statusBadge = document.getElementById('connection-status');
        const orgName = document.getElementById('org-name');

        if (data.authenticated) {
            statusBadge.textContent = 'Connected';
            statusBadge.className = 'status-badge connected';
            orgName.textContent = data.organization_name || '';

            // Auto-advance to step 2 if connected
            setTimeout(() => setActiveStep(2), 1000);
        } else {
            statusBadge.textContent = 'Not Connected';
            statusBadge.className = 'status-badge disconnected';
            orgName.textContent = '';
        }
    } catch (error) {
        console.error('Auth check failed:', error);
        showAlert('Failed to check authentication status', 'error');
    }
}

async function connectToXero() {
    try {
        const response = await fetch(`${API_BASE}/auth/connect`, { method: 'POST' });
        const data = await response.json();

        if (data.success) {
            if (data.auth_url) {
                // Open OAuth URL in popup window
                showAlert('Opening Xero authorization in new window...', 'info');
                const popup = window.open(
                    data.auth_url,
                    'xero-oauth',
                    'width=600,height=700,scrollbars=yes,resizable=yes'
                );

                // Listen for success message from popup
                const messageListener = (event) => {
                    if (event.data === 'xero-auth-success') {
                        window.removeEventListener('message', messageListener);
                        showAlert('Successfully connected to Xero!', 'success');
                        checkAuthStatus();
                    }
                };
                window.addEventListener('message', messageListener);

                // Also poll for popup closure as fallback
                const checkClosed = setInterval(() => {
                    if (popup.closed) {
                        clearInterval(checkClosed);
                        window.removeEventListener('message', messageListener);
                        // Check auth status after popup closes
                        showAlert('Checking connection status...', 'info');
                        setTimeout(() => {
                            checkAuthStatus();
                        }, 1000);
                    }
                }, 1000);

                showAlert('Please complete authorization in the popup window', 'info');
            } else {
                // Already connected
                showAlert(`Already connected to ${data.organization_name}!`, 'success');
                checkAuthStatus();
            }
        } else {
            const errorMsg = data.error || 'Failed to connect to Xero';
            showAlert(errorMsg, 'error');
            console.error('Connection failed:', data);
        }
    } catch (error) {
        console.error('Connection failed:', error);
        showAlert('Connection failed. Please check your network and try again.', 'error');
    }
}

// Step 2: File Upload
function setupDragAndDrop() {
    const dropZone = document.getElementById('drop-zone');

    dropZone.addEventListener('dragover', (e) => {
        e.preventDefault();
        dropZone.classList.add('dragover');
    });

    dropZone.addEventListener('dragleave', () => {
        dropZone.classList.remove('dragover');
    });

    dropZone.addEventListener('drop', (e) => {
        e.preventDefault();
        dropZone.classList.remove('dragover');
        handleFiles(e.dataTransfer.files);
    });
}

function handleFileSelect(event) {
    handleFiles(event.target.files);
}

function handleFiles(files) {
    uploadedFiles = Array.from(files);
    displayFiles();
    document.getElementById('upload-btn').disabled = uploadedFiles.length === 0;
}

function displayFiles() {
    const fileList = document.getElementById('file-list');
    fileList.innerHTML = '';

    uploadedFiles.forEach((file, index) => {
        const fileItem = document.createElement('div');
        fileItem.className = 'file-item';
        fileItem.innerHTML = `
            <span>${file.name} (${formatFileSize(file.size)})</span>
            <button onclick="removeFile(${index})" style="background: none; border: none; color: #dc3545; cursor: pointer;"><i class="fas fa-times"></i></button>
        `;
        fileList.appendChild(fileItem);
    });
}

function removeFile(index) {
    uploadedFiles.splice(index, 1);
    displayFiles();
    document.getElementById('upload-btn').disabled = uploadedFiles.length === 0;
}

function formatFileSize(bytes) {
    if (bytes === 0) return '0 Bytes';
    const k = 1024;
    const sizes = ['Bytes', 'KB', 'MB', 'GB'];
    const i = Math.floor(Math.log(bytes) / Math.log(k));
    return Math.round(bytes / Math.pow(k, i) * 100) / 100 + ' ' + sizes[i];
}

async function uploadFiles() {
    if (uploadedFiles.length === 0) return;

    const formData = new FormData();
    uploadedFiles.forEach(file => {
        formData.append('files', file);
    });

    try {
        showLoading('Uploading and parsing files...');
        const response = await fetch(`${API_BASE}/upload`, {
            method: 'POST',
            body: formData
        });

        const data = await response.json();
        hideLoading();

        if (data.success) {
            showAlert('Files uploaded successfully!', 'success');

            // Display summary
            const summary = data.parsed_data_summary;
            showAlert(`Parsed: ${summary.site_employees} site employees, ${summary.travel_employees} travel employees, ${summary.overtime_employees} overtime rates`, 'info');

            // Move to validation step
            setActiveStep(3);
        } else {
            showAlert('Upload failed', 'error');
        }
    } catch (error) {
        hideLoading();
        console.error('Upload failed:', error);
        showAlert('Failed to upload files', 'error');
    }
}

// Step 3: Validation
async function validateData() {
    try {
        showLoading('Validating data against Xero...');
        const response = await fetch(`${API_BASE}/validate`, { method: 'POST' });
        const data = await response.json();
        hideLoading();

        validationResult = data;
        displayValidationResults(data);

        if (data.valid) {
            showAlert('Validation successful!', 'success');
        } else if (data.warnings.length > 0) {
            showAlert(`Validation completed with ${data.warnings.length} warnings`, 'warning');
        }
    } catch (error) {
        hideLoading();
        console.error('Validation failed:', error);
        showAlert('Validation failed', 'error');
    }
}

function displayValidationResults(result) {
    const container = document.getElementById('validation-results');
    container.innerHTML = '';

    // Summary cards
    const summaryGrid = document.createElement('div');
    summaryGrid.className = 'summary-grid';
    summaryGrid.innerHTML = `
        <div class="summary-card">
            <h3>${result.summary.valid_employees}/${result.summary.total_employees}</h3>
            <p>Valid Employees</p>
        </div>
        <div class="summary-card">
            <h3>${result.summary.valid_regions}/${result.summary.total_regions}</h3>
            <p>Valid Regions</p>
        </div>
    `;
    container.appendChild(summaryGrid);

    // Warnings
    if (result.warnings.length > 0) {
        const warningsDiv = document.createElement('div');
        warningsDiv.className = 'alert alert-warning';
        warningsDiv.innerHTML = `
            <strong>Warnings:</strong>
            <ul>${result.warnings.slice(0, 5).map(w => `<li>${w}</li>`).join('')}</ul>
            ${result.warnings.length > 5 ? `<p>...and ${result.warnings.length - 5} more</p>` : ''}
        `;
        container.appendChild(warningsDiv);
    }

    // Unmapped items
    if (result.unmapped_employees.length > 0) {
        const unmappedDiv = document.createElement('div');
        unmappedDiv.className = 'alert alert-info';
        unmappedDiv.innerHTML = `
            <strong>Unmapped Employees:</strong> ${result.unmapped_employees.join(', ')}
        `;
        container.appendChild(unmappedDiv);
    }

    if (result.unmapped_regions.length > 0) {
        const unmappedDiv = document.createElement('div');
        unmappedDiv.className = 'alert alert-info';
        unmappedDiv.innerHTML = `
            <strong>Unmapped Regions:</strong> ${result.unmapped_regions.join(', ')}
        `;
        container.appendChild(unmappedDiv);
    }
}

function proceedToConsolidate() {
    if (validationResult && validationResult.summary.valid_employees > 0) {
        setActiveStep(4);
    } else {
        showAlert('No valid data to consolidate', 'error');
    }
}

// Step 4: Consolidation
async function consolidateData() {
    try {
        showLoading('Consolidating data...');
        const response = await fetch(`${API_BASE}/consolidate`, { method: 'POST' });
        const data = await response.json();
        hideLoading();

        if (data.success) {
            consolidationResult = data;
            displayConsolidationResults(data);
            showAlert('Data consolidated successfully!', 'success');

            // Enable next step
            setTimeout(() => setActiveStep(5), 1500);
        } else {
            showAlert('Consolidation failed', 'error');
        }
    } catch (error) {
        hideLoading();
        console.error('Consolidation failed:', error);
        showAlert('Failed to consolidate data', 'error');
    }
}

function displayConsolidationResults(result) {
    const container = document.getElementById('consolidation-results');
    container.innerHTML = `
        <div class="summary-grid">
            <div class="summary-card">
                <h3>${result.summary.total_employees}</h3>
                <p>Total Employees</p>
            </div>
            <div class="summary-card">
                <h3>${result.summary.pay_period_end_date}</h3>
                <p>Pay Period End</p>
            </div>
        </div>
    `;

    if (result.summary.unknown_regions.length > 0) {
        const warningDiv = document.createElement('div');
        warningDiv.className = 'alert alert-warning';
        warningDiv.innerHTML = `
            <strong>Unknown Regions Found:</strong> ${result.summary.unknown_regions.join(', ')}<br>
            <small>${result.summary.unknown_region_entries} entries affected</small>
        `;
        container.appendChild(warningDiv);
    }
}

async function downloadJSON() {
    try {
        window.location.href = `${API_BASE}/download-json`;
    } catch (error) {
        console.error('Download failed:', error);
        showAlert('Failed to download JSON', 'error');
    }
}

// Step 5: Submit
async function submitTimesheets(dryRun = false) {
    try {
        showLoading(dryRun ? 'Running dry run...' : 'Submitting timesheets to Xero...');

        // Get mappings first
        const mappingsResponse = await fetch(`${API_BASE}/mappings`);
        const mappings = await mappingsResponse.json();

        // Load consolidated data
        const jsonResponse = await fetch(`${API_BASE}/download-json`);
        const payrollData = await jsonResponse.json();

        // Prepare submission request
        const request = {
            payroll_data: payrollData,
            mappings: {
                employee_mappings: mappings.employee_mappings,
                region_mappings: mappings.region_mappings,
                earnings_mappings: mappings.hour_type_mappings
            },
            dry_run: dryRun
        };

        const response = await fetch(`${API_BASE}/submit-timesheets`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request)
        });

        const result = await response.json();
        hideLoading();

        displaySubmissionResults(result, dryRun);

    } catch (error) {
        hideLoading();
        console.error('Submission failed:', error);
        showAlert('Failed to submit timesheets', 'error');
    }
}

function displaySubmissionResults(result, isDryRun) {
    const container = document.getElementById('submission-summary');
    container.innerHTML = '';

    // Defensive access in case server returned a partial/errored payload
    const created = Array.isArray(result.created_timesheets) ? result.created_timesheets : [];
    const failed = Array.isArray(result.failed_timesheets) ? result.failed_timesheets : [];
    const warnings = Array.isArray(result.warnings) ? result.warnings : [];
    const errors = Array.isArray(result.errors) ? result.errors : [];

    if (result.success) {
        const successDiv = document.createElement('div');
        successDiv.className = 'alert alert-success';
        successDiv.innerHTML = `
            <strong>${isDryRun ? 'Dry Run' : 'Submission'} Successful!</strong><br>
            ${created.length} timesheets ${isDryRun ? 'validated' : 'created'}
        `;
        container.appendChild(successDiv);
    } else if (errors.length > 0) {
        const errorDiv = document.createElement('div');
        errorDiv.className = 'alert alert-error';
        errorDiv.innerHTML = `<strong>Submission error:</strong><br><ul>${errors.map(e => `<li>${e}</li>`).join('')}</ul>`;
        container.appendChild(errorDiv);
    }

    if (failed.length > 0) {
        const failedDiv = document.createElement('div');
        failedDiv.className = 'alert alert-error';
        failedDiv.innerHTML = `
            <strong>Failed Timesheets:</strong>
            <ul>${failed.map(f => `<li>${f.employee}: ${f.error || (f.errors ? f.errors.join('; ') : 'Unknown')}</li>`).join('')}</ul>
        `;
        container.appendChild(failedDiv);
    }

    if (warnings.length > 0) {
        const warningsDiv = document.createElement('div');
        warningsDiv.className = 'alert alert-warning';
        warningsDiv.innerHTML = `
            <strong>Warnings:</strong>
            <ul>${warnings.map(w => `<li>${w}</li>`).join('')}</ul>
        `;
        container.appendChild(warningsDiv);
    }
}

// Utility Functions
function showAlert(message, type = 'info') {
    const alertDiv = document.createElement('div');
    alertDiv.className = `alert alert-${type}`;
    alertDiv.textContent = message;
    alertDiv.style.position = 'fixed';
    alertDiv.style.top = '20px';
    alertDiv.style.right = '20px';
    alertDiv.style.zIndex = '9999';
    alertDiv.style.minWidth = '300px';

    document.body.appendChild(alertDiv);

    setTimeout(() => {
        alertDiv.remove();
    }, 5000);
}

function showLoading(message) {
    const resultsArea = document.getElementById('results-area');
    resultsArea.classList.remove('hidden');
    resultsArea.innerHTML = `
        <div style="text-align: center; padding: 20px;">
            <div class="loading"></div>
            <p style="margin-top: 10px;">${message}</p>
        </div>
    `;
}

function hideLoading() {
    document.getElementById('results-area').classList.add('hidden');
}

// Settings Management
let currentSettings = {};
let settingInfo = {};
let activeSettingsTab = 'xero_api';
let settingsChanged = false;

// Step Management - Back to 5 steps
function setActiveStep(stepNumber) {
    // Hide all content
    for (let i = 1; i <= 5; i++) {
        document.getElementById(`step-${i}-content`)?.classList.add('hidden');
        document.getElementById(`step-${i}`).classList.remove('active', 'completed');
    }

    // Show current content
    document.getElementById(`step-${stepNumber}-content`)?.classList.remove('hidden');

    // Update step indicators
    for (let i = 1; i < stepNumber; i++) {
        document.getElementById(`step-${i}`).classList.add('completed');
    }
    document.getElementById(`step-${stepNumber}`).classList.add('active');

    currentStep = stepNumber;
}

// Settings Modal Functions
function openSettingsModal() {
    document.getElementById('settings-modal').classList.remove('hidden');
    loadSettings();
}

function closeSettingsModal() {
    document.getElementById('settings-modal').classList.add('hidden');

    // Warn about unsaved changes
    if (settingsChanged) {
        if (confirm('You have unsaved changes. Are you sure you want to close?')) {
            settingsChanged = false;
        } else {
            // Reopen modal
            document.getElementById('settings-modal').classList.remove('hidden');
        }
    }
}

// Close modal when clicking outside
document.addEventListener('click', (event) => {
    const modal = document.getElementById('settings-modal');
    if (event.target === modal) {
        closeSettingsModal();
    }
});

// Close modal with Escape key
document.addEventListener('keydown', (event) => {
    if (event.key === 'Escape') {
        const modal = document.getElementById('settings-modal');
        if (!modal.classList.contains('hidden')) {
            closeSettingsModal();
        }
    }
});

// Settings Functions
async function loadSettings() {
    try {
        showLoading('Loading settings...');
        const response = await fetch(`${API_BASE}/settings`);

        if (!response.ok) {
            throw new Error(`HTTP ${response.status}: ${response.statusText}`);
        }

        const data = await response.json();
        hideLoading();

        console.log('Settings loaded:', data); // Debug log

        currentSettings = data.settings || {};
        settingInfo = data.setting_info || {};
        settingsChanged = false;

        renderSettingsForm();
        showAlert('Settings loaded successfully', 'success');

    } catch (error) {
        hideLoading();
        console.error('Failed to load settings:', error);
        showAlert(`Failed to load settings: ${error.message}`, 'error');

        // Initialize with empty settings to prevent errors
        currentSettings = {
            xero_api: {},
            file_processing: {},
            employee_matching: {},
            hour_types: {},
            parser_config: {},
            api_settings: {}
        };
        settingInfo = {};
        renderSettingsForm();
    }
}

function showSettingsTab(tabName) {
    // Update tab buttons
    document.querySelectorAll('.tab-btn').forEach(btn => {
        btn.classList.remove('active');
    });
    event.target.classList.add('active');

    // Update active tab
    activeSettingsTab = tabName;

    // Re-render form for the active tab
    renderSettingsForm();
}

function renderSettingsForm() {
    const container = document.getElementById('settings-content');

    // Safety check
    if (!currentSettings || !currentSettings[activeSettingsTab]) {
        container.innerHTML = '<p>No settings available for this category. Please try reloading.</p>';
        return;
    }

    const settings = currentSettings[activeSettingsTab];

    let html = `<div class="settings-section active">`;
    html += `<div class="settings-form">`;

    for (const [key, value] of Object.entries(settings)) {
        const info = settingInfo[key] || {};
        html += renderSettingField(key, value, info);
    }

    html += `</div></div>`;

    // Add change indicator if settings have been modified
    if (settingsChanged) {
        html = `<div class="settings-changed"><i class="fas fa-exclamation-triangle"></i> You have unsaved changes</div>` + html;
    }

    container.innerHTML = html;
}

function renderSettingField(key, value, info) {
    const type = info.type || 'text';
    const description = info.description || '';

    let html = `<div class="form-group">`;
    html += `<label for="${key}">${key.replace(/_/g, ' ')}</label>`;
    if (description) {
        html += `<div class="description">${description}</div>`;
    }

    switch (type) {
        case 'list':
            html += renderListField(key, value);
            break;
        case 'dict':
            html += renderDictField(key, value);
            break;
        case 'number':
        case 'integer':
            const min = info.min !== undefined ? `min="${info.min}"` : '';
            const max = info.max !== undefined ? `max="${info.max}"` : '';
            const step = type === 'integer' ? 'step="1"' : 'step="0.1"';
            html += `<input type="number" id="${key}" value="${value}" ${min} ${max} ${step} onchange="updateSetting('${key}', this.value, '${type}')">`;
            break;
        case 'url':
            html += `<input type="url" id="${key}" value="${value}" onchange="updateSetting('${key}', this.value, 'string')">`;
            break;
        default:
            html += `<input type="text" id="${key}" value="${value}" onchange="updateSetting('${key}', this.value, 'string')">`;
    }

    html += `</div>`;
    return html;
}

function renderListField(key, value) {
    let html = `<div class="list-input" id="${key}-container">`;

    if (Array.isArray(value)) {
        value.forEach((item, index) => {
            html += `<div class="list-item">`;
            html += `<input type="text" value="${item}" onchange="updateListItem('${key}', ${index}, this.value)">`;
            html += `<button onclick="removeListItem('${key}', ${index})">Remove</button>`;
            html += `</div>`;
        });
    }

    html += `<button class="add-list-item" onclick="addListItem('${key}')">Add Item</button>`;
    html += `</div>`;

    return html;
}

function renderDictField(key, value) {
    let html = `<div class="dict-input" id="${key}-container">`;

    if (typeof value === 'object' && value !== null) {
        for (const [dictKey, dictValue] of Object.entries(value)) {
            html += `<div class="dict-item">`;
            html += `<input type="text" value="${dictKey}" onchange="updateDictKey('${key}', '${dictKey}', this.value)" placeholder="Key">`;
            html += `<input type="text" value="${dictValue}" onchange="updateDictValue('${key}', '${dictKey}', this.value)" placeholder="Value">`;
            html += `<button onclick="removeDictItem('${key}', '${dictKey}')">Remove</button>`;
            html += `</div>`;
        }
    }

    html += `<button class="add-list-item" onclick="addDictItem('${key}')">Add Item</button>`;
    html += `</div>`;

    return html;
}

function updateSetting(key, value, type) {
    let parsedValue = value;

    if (type === 'number' || type === 'integer') {
        parsedValue = type === 'integer' ? parseInt(value) : parseFloat(value);
    }

    currentSettings[activeSettingsTab][key] = parsedValue;
    settingsChanged = true;
    renderSettingsForm();
}

function updateListItem(key, index, value) {
    currentSettings[activeSettingsTab][key][index] = value;
    settingsChanged = true;
}

function addListItem(key) {
    if (!currentSettings[activeSettingsTab][key]) {
        currentSettings[activeSettingsTab][key] = [];
    }
    currentSettings[activeSettingsTab][key].push('');
    settingsChanged = true;
    renderSettingsForm();
}

function removeListItem(key, index) {
    currentSettings[activeSettingsTab][key].splice(index, 1);
    settingsChanged = true;
    renderSettingsForm();
}

function updateDictKey(key, oldKey, newKey) {
    const dict = currentSettings[activeSettingsTab][key];
    const value = dict[oldKey];
    delete dict[oldKey];
    dict[newKey] = value;
    settingsChanged = true;
    renderSettingsForm();
}

function updateDictValue(key, dictKey, value) {
    currentSettings[activeSettingsTab][key][dictKey] = value;
    settingsChanged = true;
}

function addDictItem(key) {
    if (!currentSettings[activeSettingsTab][key]) {
        currentSettings[activeSettingsTab][key] = {};
    }
    currentSettings[activeSettingsTab][key][''] = '';
    settingsChanged = true;
    renderSettingsForm();
}

function removeDictItem(key, dictKey) {
    delete currentSettings[activeSettingsTab][key][dictKey];
    settingsChanged = true;
    renderSettingsForm();
}

async function saveSettings() {
    try {
        showLoading('Saving settings...');

        // Flatten settings for API
        const flatSettings = {};
        for (const category of Object.values(currentSettings)) {
            Object.assign(flatSettings, category);
        }

        const response = await fetch(`${API_BASE}/settings`, {
            method: 'PUT',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ updates: flatSettings })
        });

        const result = await response.json();
        hideLoading();

        if (result.success) {
            settingsChanged = false;
            renderSettingsForm();
            showAlert('Settings saved successfully!', 'success');
        } else {
            showAlert('Failed to save settings', 'error');
        }

    } catch (error) {
        hideLoading();
        console.error('Failed to save settings:', error);
        showAlert('Failed to save settings', 'error');
    }
}

async function resetSettings() {
    if (!confirm('Are you sure you want to reset all settings to defaults? This cannot be undone.')) {
        return;
    }

    try {
        showLoading('Resetting settings...');

        const response = await fetch(`${API_BASE}/settings/reset`, {
            method: 'POST'
        });

        const result = await response.json();
        hideLoading();

        if (result.success) {
            showAlert('Settings reset to defaults successfully!', 'success');
            loadSettings(); // Reload settings
        } else {
            showAlert('Failed to reset settings', 'error');
        }

    } catch (error) {
        hideLoading();
        console.error('Failed to reset settings:', error);
        showAlert('Failed to reset settings', 'error');
    }
}

async function exportSettings() {
    try {
        const response = await fetch(`${API_BASE}/settings/export`);
        const result = await response.json();

        if (result.success) {
            // Create download link
            const blob = new Blob([JSON.stringify(result.settings, null, 2)], { type: 'application/json' });
            const url = URL.createObjectURL(blob);
            const a = document.createElement('a');
            a.href = url;
            a.download = `xero-payroll-settings-${new Date().toISOString().split('T')[0]}.json`;
            document.body.appendChild(a);
            a.click();
            document.body.removeChild(a);
            URL.revokeObjectURL(url);

            showAlert('Settings exported successfully!', 'success');
        } else {
            showAlert('Failed to export settings', 'error');
        }

    } catch (error) {
        console.error('Failed to export settings:', error);
        showAlert('Failed to export settings', 'error');
    }
}

function importSettings() {
    const input = document.createElement('input');
    input.type = 'file';
    input.accept = '.json';
    input.onchange = async (event) => {
        const file = event.target.files[0];
        if (!file) return;

        try {
            const text = await file.text();
            const settings = JSON.parse(text);

            showLoading('Importing settings...');

            const response = await fetch(`${API_BASE}/settings/import`, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(settings)
            });

            const result = await response.json();
            hideLoading();

            if (result.success) {
                showAlert('Settings imported successfully!', 'success');
                loadSettings(); // Reload settings
            } else {
                showAlert('Failed to import settings', 'error');
            }

        } catch (error) {
            hideLoading();
            console.error('Failed to import settings:', error);
            showAlert('Failed to import settings - invalid file format', 'error');
        }
    };

    input.click();
}