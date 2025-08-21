# Xero Payroll Automation

**Automate your payroll process** - Upload Excel timesheets, validate data, and create draft timesheets in Xero automatically.

![Xero Payroll Automation](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)

## What It Does

This system takes your Excel timesheet files and automatically creates draft timesheets in Xero, saving hours of manual data entry.

**Simple 5-Step Process:**
1. **Connect** to your Xero account
2. **Upload** Excel timesheet files 
3. **Validate** employee names and regions
4. **Consolidate** data with business rules
5. **Submit** draft timesheets to Xero

## Quick Start

### 1. Prerequisites
- Python 3.8+
- Xero developer app ([Create one here](https://developer.xero.com/))

### 2. Install & Setup
```bash
# Install dependencies
pip install -r requirements.txt

# Create .env file with your Xero app credentials
echo "XERO_CLIENT_ID=your_client_id" > .env
echo "XERO_CLIENT_SECRET=your_client_secret" >> .env
```

### 3. Run the Application
```bash
python -m uvicorn src.api_server:app --reload --host 0.0.0.0 --port 8000
```

### 4. Open in Browser
```
http://localhost:8000
```

## Supported File Types

The system automatically detects and processes:

- **Site Timesheets** - Employee hours by region and date
- **Travel Time** - Travel hours and expenses  
- **Overtime Rates** - Employee-specific overtime rates

Supports `.xlsx`, `.xls` files and `.zip` archives containing multiple files.

## Key Features

### 🔐 Secure Authentication
- OAuth2 integration with Xero
- Encrypted token storage
- Automatic token refresh

### 📊 Smart Data Processing
- Automatic Excel file parsing
- Employee name matching with fuzzy logic
- Region validation against Xero data
- Business rule application (40-hour caps, etc.)

### ✅ Validation & Testing
- **Dry Run Mode** - Test without creating actual timesheets
- Employee and region validation
- Detailed error reporting
- Debug payload generation

### 🎯 User-Friendly Interface
- Step-by-step workflow
- Drag & drop file upload
- Real-time validation feedback
- Settings management

## How It Works

### File Processing
1. **Upload** your Excel files (or ZIP containing multiple files)
2. **Automatic parsing** extracts employee hours, regions, and dates
3. **Validation** checks employees exist in Xero and regions are mapped
4. **Consolidation** applies business rules and merges data sources

### Timesheet Creation
1. **Mapping** connects your data to Xero employees and tracking categories
2. **Payload generation** creates Xero API-compatible timesheet data
3. **Dry run testing** validates everything without creating actual timesheets
4. **Submission** creates draft timesheets in Xero for final review

## Configuration

### Xero App Setup
1. Go to [Xero Developer Portal](https://developer.xero.com/)
2. Create a new app with these settings:
   - **Redirect URI**: `http://localhost:8000/api/auth/callback`
   - **Scopes**: `offline_access`, `payroll.employees.read`, `payroll.timesheets`
3. Copy your Client ID and Client Secret to the `.env` file

### Business Rules
The system includes configurable business rules:
- **Hour capping** (default: 40 hours regular time)
- **Holiday processing** (8 hours for 'HOL' entries)
- **Overtime calculations** based on employee rates
- **Region mapping** to Xero tracking categories

## Troubleshooting

### Common Issues

**"Not Connected" Status**
- Check your `.env` file has correct Xero credentials
- Ensure redirect URI matches in Xero app settings
- Try disconnecting and reconnecting

**Employee Not Found**
- Use the validation step to map employee names
- Check spelling and name format in Excel files
- Add employees to Xero if they don't exist

**Region Validation Errors**
- Ensure regions in Excel match Xero tracking categories
- Add missing regions as tracking options in Xero
- Use the validation report to see specific mismatches

**File Upload Issues**
- Supported formats: `.xlsx`, `.xls`, `.zip`
- Check file isn't corrupted or password protected
- Ensure Excel files follow expected format

## Development

### Project Structure
```
├── src/                    # Backend Python code
│   ├── api_server.py      # Main FastAPI server
│   ├── parsers.py         # Excel file parsing
│   ├── xero_api_client.py # Xero API integration
│   └── ...
├── static/                # Frontend web interface
│   ├── index.html         # Main web page
│   ├── app.js            # JavaScript application
│   └── css/              # Modular CSS files
├── config/               # Configuration files
└── requirements.txt      # Python dependencies
```

### Running in Development
```bash
# Enable debug logging
export LOG_LEVEL=DEBUG

# Run with auto-reload
python -m uvicorn src.api_server:app --reload --port 8000

# Run tests
pytest
```

## API Endpoints

The system provides a REST API for integration:

```http
# Authentication
GET  /api/auth/status          # Check connection status
POST /api/auth/connect         # Start OAuth flow
POST /api/auth/disconnect      # Clear authentication

# Data Processing  
POST /api/upload               # Upload Excel files
POST /api/validate             # Validate against Xero
POST /api/consolidate          # Apply business rules
POST /api/submit-timesheets    # Create Xero timesheets

# Settings
GET  /api/settings             # Get configuration
PUT  /api/settings             # Update settings
```

## Security

- **No credentials stored** - Uses OAuth2 with encrypted token storage
- **Environment variables** - Sensitive data in `.env` file only
- **Secure token handling** - Automatic refresh and proper cleanup
- **Input validation** - All uploads and data validated before processing

## Support

- **Documentation** - Comprehensive inline documentation
- **Debug files** - Automatic generation in `debug_timesheet_payloads/`
- **Error reporting** - Detailed error messages with suggested fixes
- **Dry run testing** - Test everything before actual submission

---

**Ready to automate your payroll?** Start with the Quick Start guide above! 🚀