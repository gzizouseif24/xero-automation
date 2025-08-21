# Dry Run Test Functionality Documentation

## Overview
The dry run functionality allows users to test timesheet submissions without actually creating timesheets in Xero. This feature validates payloads, checks for errors, and generates debug files locally for inspection before real submission.

## Architecture Flow

### 1. Frontend Trigger (`static/index.html` & `static/app.js`)

**HTML Button:**
```html
<button class="btn" onclick="submitTimesheets(true)">
    Dry Run (Test Only)
</button>
```

**JavaScript Function:**
```javascript
async function submitTimesheets(dryRun = false) {
    try {
        showLoading(dryRun ? 'Running dry run...' : 'Submitting timesheets to Xero...');
        
        // Prepare submission request
        const request = {
            payroll_data: payrollData,
            mappings: {
                employee_mappings: mappings.employee_mappings,
                region_mappings: mappings.region_mappings,
                earnings_mappings: mappings.hour_type_mappings
            },
            dry_run: dryRun  // Key parameter
        };
        
        // Submit to API
        const response = await fetch(`${API_BASE}/submit-timesheets`, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(request)
        });
    }
}
```

### 2. API Endpoint (`src/api_server.py`)

**Request Model:**
```python
class TimesheetSubmissionRequest(BaseModel):
    payroll_data: Dict[str, Any]
    mappings: MappingResolution
    dry_run: bool = False  # Default to false for real submissions
```

**Main Endpoint:**
```python
@app.post("/api/submit-timesheets", response_model=TimesheetSubmissionResult)
async def submit_timesheets(request: TimesheetSubmissionRequest):
```

## Key Dry Run Logic

### 1. Entry Filtering
```python
# Create filtered timesheet
entries_for_timesheet = employee_timesheet.daily_entries if request.dry_run else [entry for entry in employee_timesheet.daily_entries if entry.region_name != 'Unknown']
```

**Behavior:**
- **Dry Run Mode**: Includes ALL entries (even 'Unknown' regions) for complete validation
- **Real Submission**: Filters out 'Unknown' region entries to prevent API errors

### 2. Payload File Handling
```python
# Use existing payload or build new one
if existing_payload_file and not request.dry_run:
    # Load existing edited payload for real submission
    with open(existing_payload_file, 'r', encoding='utf-8') as pf:
        existing_payload_data = json.load(pf)
else:
    # Build new payload (for dry run or first-time submission)
    timesheet_payload = builder.build_timesheet(...)
```

**Behavior:**
- **Dry Run Mode**: Always builds fresh payloads (ignores existing edited files)
- **Real Submission**: Uses existing edited payloads if available

### 3. Submission vs Validation
```python
# Submit or validate
if not request.dry_run:
    # Real submission to Xero API
    timesheet_id = client.create_timesheet(timesheet_payload)
    created_timesheets.append(timesheet_id)
else:
    # Dry run validation only
    errors = builder.validate_timesheet_data(timesheet_payload)
    if errors:
        failed_timesheets.append({
            "employee": employee_timesheet.employee_name,
            "errors": errors
        })
    else:
        created_timesheets.append(f"dry-run-{employee_timesheet.employee_name}")
```

## Payload Generation & Debug Files

### 1. Debug Directory Creation
```python
# Create payload directory
payload_dir = Path("debug_timesheet_payloads")
payload_dir.mkdir(exist_ok=True)
```

### 2. Payload File Naming
```python
# Generate timestamped filename
timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
payload_file = payload_dir / f"{safe_name}_{timestamp}.json"

# Save payload to disk
with open(payload_file, 'w', encoding='utf-8') as pf:
    json.dump(timesheet_payload, pf, indent=2, default=str)
```

**File Format:** `{employee_name}_{timestamp}.json`
**Example:** `Chelsea_Serati_20250820T124033Z.json`

### 3. Payload Content Structure
```json
{
  "PayrollCalendarID": "d490809d-5682-4c27-8021-785100ed2f42",
  "EmployeeID": "0651c356-20a5-4d55-9129-1516c85df721",
  "StartDate": "2025-06-02",
  "EndDate": "2025-06-08",
  "Status": "Draft",
  "TimesheetLines": [
    {
      "Date": "2025-06-03",
      "EarningsRateID": "488b126f-acee-4e41-ab4a-3744b0735e04",
      "NumberOfUnits": 9.0,
      "TrackingItemID": "34b9b859-07a9-451a-b4d3-effc9946634a"
    }
  ]
}
```

## Validation Logic (`src/timesheet_builder.py`)

### 1. Validation Function
```python
def validate_timesheet_data(self, timesheet_data: Dict[str, Any]) -> List[str]:
    """
    Validate Xero timesheet data structure
    
    Returns:
        List of validation error messages (empty if valid)
    """
    errors = []
    
    # Check required fields
    required_fields = ["EmployeeID", "StartDate", "EndDate", "TimesheetLines"]
    for field in required_fields:
        if field not in timesheet_data:
            errors.append(f"Missing required field: {field}")
    
    # Validate timesheet lines
    if "TimesheetLines" in timesheet_data:
        lines = timesheet_data["TimesheetLines"]
        for i, line in enumerate(lines):
            line_errors = self._validate_timesheet_line(line, i)
            errors.extend(line_errors)
    
    return errors
```

### 2. Line Validation
```python
def _validate_timesheet_line(self, line: Dict[str, Any], line_index: int) -> List[str]:
    """Validate a single timesheet line"""
    errors = []
    
    # Check required fields
    required_fields = ["Date", "EarningsRateID", "NumberOfUnits"]
    for field in required_fields:
        if field not in line:
            errors.append(f"Line {line_index + 1}: Missing required field: {field}")
    
    # Validate NumberOfUnits format
    if "NumberOfUnits" in line:
        units = line["NumberOfUnits"]
        if not isinstance(units, (int, float)) or units < 0:
            errors.append(f"Line {line_index + 1}: NumberOfUnits must be a non-negative number")
    
    return errors
```

## Frontend Result Display

### 1. Result Processing
```javascript
function displaySubmissionResults(result, isDryRun) {
    const created = Array.isArray(result.created_timesheets) ? result.created_timesheets : [];
    const failed = Array.isArray(result.failed_timesheets) ? result.failed_timesheets : [];
    
    if (result.success) {
        const successDiv = document.createElement('div');
        successDiv.innerHTML = `
            <strong>${isDryRun ? 'Dry Run' : 'Submission'} Successful!</strong><br>
            ${created.length} timesheets ${isDryRun ? 'validated' : 'created'}
        `;
    }
}
```

### 2. Dry Run vs Real Submission Messages
- **Dry Run Success**: "Dry Run Successful! X timesheets validated"
- **Real Submission Success**: "Submission Successful! X timesheets created"

## File Locations & Outputs

### 1. Generated Files
- **Payload Files**: `debug_timesheet_payloads/{employee}_{timestamp}.json`
- **Consolidated Data**: `consolidated_payroll_data.json`
- **Validation Results**: `temp_validation_result.json`
- **Error Debug**: `debug_consolidate_error.json`

### 2. Directory Structure
```
project_root/
├── debug_timesheet_payloads/
│   ├── Chelsea_Serati_20250820T124033Z.json
│   ├── Charlotte_Danes_20250820T124034Z.json
│   └── Jack_Allan_20250820T124035Z.json
├── consolidated_payroll_data.json
├── temp_validation_result.json
└── debug_consolidate_error.json (if errors occur)
```

## Benefits of Dry Run Mode

### 1. Risk-Free Testing
- Validates payloads without creating actual Xero timesheets
- Identifies errors before real submission
- Allows inspection of generated JSON payloads

### 2. Debugging Capabilities
- Generates timestamped payload files for inspection
- Includes validation error details
- Preserves all entries (including 'Unknown' regions) for complete testing

### 3. Iterative Development
- Test mapping configurations
- Verify hour calculations
- Check date formatting and API compliance

## Usage Workflow

1. **Upload Files** → Parse timesheet data
2. **Validate Data** → Check against Xero employees/regions
3. **Consolidate** → Apply business rules (40-hour cap, etc.)
4. **Dry Run Test** → Generate and validate payloads locally
5. **Review Payloads** → Inspect `debug_timesheet_payloads/` files
6. **Real Submission** → Submit validated payloads to Xero

## Error Handling

### 1. Validation Errors
```json
{
  "success": false,
  "failed_timesheets": [
    {
      "employee": "John Doe",
      "errors": [
        "Line 1: Missing required field: EarningsRateID",
        "Line 2: NumberOfUnits must be a non-negative number"
      ]
    }
  ]
}
```

### 2. System Errors
- Authentication failures
- Missing mapping configurations
- File I/O errors
- Network connectivity issues

## Configuration

### 1. Default Settings
- `dry_run: false` (real submission by default)
- Payload directory: `debug_timesheet_payloads/`
- Timestamp format: `%Y%m%dT%H%M%SZ`

### 2. Customizable Aspects
- Payload directory location
- Validation rules
- Error message formatting
- File naming conventions