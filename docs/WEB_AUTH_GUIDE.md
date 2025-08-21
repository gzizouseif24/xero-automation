# Web-Only Authentication Guide

## 🌐 Pure HTML/JavaScript Authentication Workflow

Your Xero payroll automation system now works **exclusively through web API endpoints** - no manual scripts needed!

## 🚀 Quick Start

1. **Start your API server:**
   ```bash
   python -m uvicorn src.api_server:app --reload --host 0.0.0.0 --port 8000
   ```
   Or alternatively:
   ```bash
   python src/api_server.py
   ```

2. **Open your HTML application** (served at `http://localhost:8000`)

3. **Everything else happens through your web interface!**

## 📋 Available API Endpoints

### Authentication Endpoints

| Endpoint | Method | Purpose | Response |
|----------|--------|---------|----------|
| `/api/auth/status` | GET | Check authentication status | `{authenticated: bool, organization_name: string, tenant_id: string, error: string}` |
| `/api/auth/connect` | POST | Start OAuth flow | `{success: bool, message: string, organization_name: string, tenant_id: string}` |
| `/api/auth/disconnect` | POST | Clear tokens | `{success: bool, message: string}` |

### Data Processing Endpoints

| Endpoint | Method | Purpose |
|----------|--------|---------|
| `/api/upload` | POST | Upload Excel files |
| `/api/validate` | POST | Validate data against Xero |
| `/api/consolidate` | POST | Consolidate validated data |
| `/api/submit-timesheets` | POST | Submit timesheets to Xero |
| `/api/mappings` | GET | Get employee/region mappings |

## 🔄 Authentication Flow

### First Time Setup
```javascript
// 1. Check authentication status
fetch('/api/auth/status')
  .then(response => response.json())
  .then(data => {
    if (!data.authenticated) {
      // Show "Connect to Xero" button
      showConnectButton();
    } else {
      // User is already authenticated
      showMainInterface(data.organization_name);
    }
  });

// 2. When user clicks "Connect to Xero"
function connectToXero() {
  fetch('/api/auth/connect', { method: 'POST' })
    .then(response => response.json())
    .then(data => {
      if (data.success) {
        alert(`Connected to ${data.organization_name}!`);
        location.reload(); // Refresh to show authenticated state
      } else {
        alert('Connection failed. Please try again.');
      }
    })
    .catch(error => {
      console.error('Connection error:', error);
      alert('Connection failed. Please try again.');
    });
}
```

### Handling Authentication Errors
```javascript
// Wrap API calls with authentication error handling
async function makeAuthenticatedRequest(url, options = {}) {
  try {
    const response = await fetch(url, options);
    
    if (response.status === 401) {
      // Authentication failed - show reconnect option
      if (confirm('Authentication expired. Reconnect to Xero?')) {
        await connectToXero();
        // Retry the original request
        return fetch(url, options);
      }
      throw new Error('Authentication required');
    }
    
    return response;
  } catch (error) {
    console.error('API request failed:', error);
    throw error;
  }
}

// Example usage
makeAuthenticatedRequest('/api/mappings')
  .then(response => response.json())
  .then(data => {
    console.log('Mappings:', data);
  });
```

## 🔧 Complete HTML Example

```html
<!DOCTYPE html>
<html>
<head>
    <title>Xero Payroll Automation</title>
</head>
<body>
    <div id="auth-section">
        <h2>Authentication</h2>
        <div id="auth-status"></div>
        <button id="connect-btn" onclick="connectToXero()" style="display:none;">
            Connect to Xero
        </button>
        <button id="disconnect-btn" onclick="disconnectFromXero()" style="display:none;">
            Disconnect
        </button>
    </div>

    <div id="main-section" style="display:none;">
        <h2>Payroll Processing</h2>
        <input type="file" id="file-upload" multiple accept=".xlsx,.xls">
        <button onclick="uploadFiles()">Upload Files</button>
        <button onclick="validateData()">Validate Data</button>
        <button onclick="submitTimesheets()">Submit to Xero</button>
    </div>

    <script>
        // Check authentication on page load
        window.onload = function() {
            checkAuthStatus();
        };

        async function checkAuthStatus() {
            try {
                const response = await fetch('/api/auth/status');
                const data = await response.json();
                
                const statusDiv = document.getElementById('auth-status');
                const connectBtn = document.getElementById('connect-btn');
                const disconnectBtn = document.getElementById('disconnect-btn');
                const mainSection = document.getElementById('main-section');
                
                if (data.authenticated) {
                    statusDiv.innerHTML = `✅ Connected to: ${data.organization_name}`;
                    connectBtn.style.display = 'none';
                    disconnectBtn.style.display = 'inline';
                    mainSection.style.display = 'block';
                } else {
                    statusDiv.innerHTML = `❌ Not connected${data.error ? ': ' + data.error : ''}`;
                    connectBtn.style.display = 'inline';
                    disconnectBtn.style.display = 'none';
                    mainSection.style.display = 'none';
                }
            } catch (error) {
                console.error('Status check failed:', error);
            }
        }

        async function connectToXero() {
            try {
                const response = await fetch('/api/auth/connect', { method: 'POST' });
                const data = await response.json();
                
                if (data.success) {
                    alert(`Successfully connected to ${data.organization_name}!`);
                    checkAuthStatus(); // Refresh status
                } else {
                    alert('Connection failed. Please try again.');
                }
            } catch (error) {
                console.error('Connection failed:', error);
                alert('Connection failed. Please try again.');
            }
        }

        async function disconnectFromXero() {
            if (confirm('Are you sure you want to disconnect from Xero?')) {
                try {
                    const response = await fetch('/api/auth/disconnect', { method: 'POST' });
                    const data = await response.json();
                    
                    if (data.success) {
                        alert('Disconnected successfully!');
                        checkAuthStatus(); // Refresh status
                    }
                } catch (error) {
                    console.error('Disconnect failed:', error);
                }
            }
        }

        async function uploadFiles() {
            const fileInput = document.getElementById('file-upload');
            const files = fileInput.files;
            
            if (files.length === 0) {
                alert('Please select files to upload');
                return;
            }
            
            const formData = new FormData();
            for (let file of files) {
                formData.append('files', file);
            }
            
            try {
                const response = await fetch('/api/upload', {
                    method: 'POST',
                    body: formData
                });
                
                if (response.status === 401) {
                    alert('Authentication expired. Please reconnect to Xero.');
                    checkAuthStatus();
                    return;
                }
                
                const data = await response.json();
                alert(`Upload successful! Processed ${data.parsed_data_summary.site_employees} site employees.`);
            } catch (error) {
                console.error('Upload failed:', error);
                alert('Upload failed. Please try again.');
            }
        }

        async function validateData() {
            try {
                const response = await fetch('/api/validate', { method: 'POST' });
                
                if (response.status === 401) {
                    alert('Authentication expired. Please reconnect to Xero.');
                    checkAuthStatus();
                    return;
                }
                
                const data = await response.json();
                alert(`Validation complete! ${data.summary.valid_employees} employees validated.`);
            } catch (error) {
                console.error('Validation failed:', error);
                alert('Validation failed. Please try again.');
            }
        }

        async function submitTimesheets() {
            // Implementation for timesheet submission
            alert('Timesheet submission feature - implement based on your needs');
        }
    </script>
</body>
</html>
```

## 🔒 Security Features

- **No password prompts** - Works seamlessly with web interfaces
- **Encrypted token storage** - Tokens stored securely using environment-based encryption
- **Automatic token refresh** - Handles expired tokens transparently
- **Session management** - Proper cleanup and error handling

## 📁 File Structure

```
your-project/
├── src/
│   ├── api_server.py          # Main API server
│   ├── auth_manager.py        # OAuth flow management
│   ├── auth_middleware.py     # Web-compatible auth middleware
│   ├── token_storage.py       # Secure token storage
│   └── xero_api_client.py     # Xero API integration
├── static/
│   └── index.html             # Your HTML frontend
├── .xero_tokens/              # Encrypted token storage (auto-created)
│   └── tokens.enc
├── backup_scripts/            # Manual scripts (for reference only)
│   ├── clear_tokens.py
│   ├── run_auth_flow.py
│   └── test_*.py
└── .env                       # Environment variables
```

## 🎯 Key Benefits

✅ **Web-Native** - Everything works through HTTP API calls  
✅ **No Manual Scripts** - Pure web interface workflow  
✅ **No Password Prompts** - Compatible with HTML/JavaScript frontends  
✅ **Secure** - Encrypted token storage with environment-based keys  
✅ **Robust** - Proper error handling and token refresh  
✅ **Simple** - Clean API endpoints for all operations  

## 🚨 Important Notes

1. **Manual scripts are in `backup_scripts/`** - Only use for reference or emergency
2. **Always use the web API endpoints** - Don't run manual scripts
3. **Token storage is automatic** - No need to manage tokens manually
4. **Authentication is persistent** - Tokens survive server restarts
5. **Error handling is built-in** - API returns proper HTTP status codes

Your authentication system is now **100% web-compatible** and ready for production use!