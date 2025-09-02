# Xero Payroll Automation

**Automate your payroll process** - Upload Excel timesheets, validate data, and create draft timesheets in Xero automatically.

![Xero Payroll Automation](https://img.shields.io/badge/Status-Production%20Ready-brightgreen)
![Python](https://img.shields.io/badge/Python-3.8%2B-blue)

## Overview

Xero Payroll Automation streamlines payroll processing by automatically converting Excel timesheet files into draft timesheets in Xero, eliminating hours of manual data entry.

## Key Features

- **Excel Processing**: Handles site timesheets, travel time, and overtime rate files
- **Data Validation**: Matches employee names and validates regions against Xero
- **Business Rules**: Processes holidays, overtime, and region overrides
- **Xero Integration**: Secure OAuth 2.0 authentication with automatic token management
- **Web Interface**: Modern UI with drag & drop file upload and real-time progress

## How It Works

1. **Connect** to your Xero account via OAuth
2. **Upload** Excel timesheet files (.xlsx, .xls, .zip)
3. **Validate** employee names and regions against Xero data
4. **Consolidate** data with business rules
5. **Submit** draft timesheets to Xero

## Installation

1. Clone the repository
2. Install dependencies: `pip install -r requirements.txt`
3. Configure environment variables:
   ```env
   XERO_CLIENT_ID=your_client_id
   XERO_CLIENT_SECRET=your_client_secret
   ```
4. Run the application: `python -m uvicorn src.api_server:app --host 0.0.0.0 --port 8000 --reload`
5. Access at `http://localhost:8000`

