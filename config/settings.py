"""
Configuration settings for Xero Payroll Automation.

This module contains application configuration constants and settings
that can be adjusted for different environments or requirements.
"""

# Xero API Configuration
XERO_API_BASE_URL = 'https://api.xero.com/api.xro/2.0'
XERO_PAYROLL_API_BASE_URL = 'https://api.xero.com/payroll.xro/2.0'

# OAuth 2.0 Configuration
OAUTH_SCOPES = [
    'offline_access',
    'payroll.employees.read',
    'payroll.timesheets',
]

# File Processing Configuration
SUPPORTED_FILE_EXTENSIONS = ['.xlsx', '.xls', '.csv']
EXPECTED_FILES = [
    'Site Timesheet',
    'Travel Time',
    'Employee Overtime Rates',
]

# Employee Matching Configuration
FUZZY_MATCH_THRESHOLD = 92.5
FUZZY_MATCH_CUTOFF = 60

# Hour Type Mappings for Xero API (enum key -> Xero display name)
HOUR_TYPE_TO_XERO_MAPPING = {
    "REGULAR": 'Regular Hours',
    "OVERTIME": 'Overtime Hours',
    "HOLIDAY": 'Holiday',
    "TRAVEL": 'Travel Hours',
}

# Hour Type Enum Keys (used internally by parsers and models)
HOUR_TYPE_KEYS = [
    'REGULAR',
    'OVERTIME',
    'TRAVEL',
    'HOLIDAY',
]

# Holiday Processing
HOLIDAY_HOURS_PER_DAY = 8

# Parser Configuration
SITE_TIMESHEET_CONFIG = {
    "date_row_search_range": 25,  # Maximum rows to search for date headers
    "employee_start_row": 12,  # Row where employee data typically starts
    "overtime_column": 11,  # Column K (11th column) for overtime totals
    "region_override_hours": 8.0,  # Hours to assign for region override entries
}

TRAVEL_TIME_CONFIG = {
    "employee_name_column": 1,  # Column A
    "site_name_column": 2,  # Column B
    "hours_column": 4,  # Column D
    "data_start_row": 2,  # Row where data starts
    "fake_employee_patterns": ['test', 'fake', 'example', 'dummy', 'sample', 'xxx'],
}

OVERTIME_RATES_CONFIG = {
    "exact_title_phrase": 'overtime rate for employees',
    "data_start_row": 2,
    "max_search_columns": 20,
    "employee_name_columns": [1, 2],  # Try column A, then B
    "overtime_flag_columns": [3, 4],  # Try column C, then D
    "overtime_rate_columns": [4, 5],  # Try column D, then E
}

# API Rate Limiting
API_RATE_LIMIT_DELAY = 1
MAX_RETRIES = 5