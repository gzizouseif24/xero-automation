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


### 3. Run the Application

### 4. Open in Browser


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

### Business Rules
The system includes configurable business rules:
- **Hour capping** (default: 40 hours regular time)
- **Holiday processing** (8 hours for 'HOL' entries)
- **Overtime calculations** based on employee rates
- **Region mapping** to Xero tracking categories


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
- **Secure token handling** - Automatic refresh and proper cleanup
- **Input validation** - All uploads and data validated before processing


---
