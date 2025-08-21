"""
FastAPI Server for Xero Payroll Automation - Task 3
Provides REST API endpoints for the complete payroll workflow.
"""

import os
import json
import logging
from pathlib import Path
from dotenv import load_dotenv
from typing import Dict, Any, List, Optional
from datetime import datetime
import tempfile
import zipfile
from fastapi import FastAPI, HTTPException, UploadFile, File, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse, FileResponse, HTMLResponse, RedirectResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel, Field

# Import our modules
from src.parsers import SiteTimesheetParser, TravelTimeParser, OvertimeRatesParser
from src.xero_api_client import XeroAPIClient, XeroAPIError, XeroAuthenticationError, XeroValidationError
from src.consolidator import DataConsolidator
from src.validation import EmployeeMatcher
from src.models import PayrollData, EmployeeTimesheet, DailyEntry, HourType
from src.timesheet_builder import TimesheetBuilder
from src.auth_middleware import auth_manager
from src.settings_manager import SettingsManager

# Configure logging
logging.basicConfig(level=logging.INFO)
logger = logging.getLogger(__name__)

# Load environment variables from .env (cwd or project root)
try:
    cwd_env = Path.cwd() / '.env'
    project_env = Path(__file__).parent.parent / '.env'
    if cwd_env.exists():
        load_dotenv(dotenv_path=str(cwd_env))
        logger.info(f"ENV: Loaded .env from cwd: {cwd_env}")
    elif project_env.exists():
        load_dotenv(dotenv_path=str(project_env))
        logger.info(f"ENV: Loaded .env from project root: {project_env}")
    else:
        load_dotenv()
        logger.info("WARNING: .env not found in cwd or project root; attempted default load")
except Exception as e:
    logger.warning(f"Failed to load .env: {e}")

# Create FastAPI app
app = FastAPI(
    title="Xero Payroll Automation API",
    description="API for automating payroll processing with Xero integration",
    version="1.0.0"
)

# Configure CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],  # In production, specify actual origins
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Global state for processing status
processing_status = {
    "is_processing": False,
    "current_step": "",
    "progress": 0,
    "errors": [],
    "warnings": []
}

# Pydantic models for request/response
class AuthStatus(BaseModel):
    authenticated: bool
    organization_name: Optional[str] = None
    tenant_id: Optional[str] = None
    error: Optional[str] = None

class ValidationResult(BaseModel):
    valid: bool
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)
    unmapped_regions: List[str] = Field(default_factory=list)
    unmapped_employees: List[str] = Field(default_factory=list)
    summary: Dict[str, Any] = Field(default_factory=dict)

class MappingResolution(BaseModel):
    employee_mappings: Dict[str, str]  # sheet_name -> xero_name
    region_mappings: Dict[str, str]    # sheet_region -> xero_tracking_id
    earnings_mappings: Dict[str, str]  # hour_type -> earnings_rate_id

class TimesheetSubmissionRequest(BaseModel):
    payroll_data: Dict[str, Any]
    mappings: MappingResolution
    dry_run: bool = False

class TimesheetSubmissionResult(BaseModel):
    success: bool
    created_timesheets: List[str] = Field(default_factory=list)
    failed_timesheets: List[Dict[str, Any]] = Field(default_factory=list)
    errors: List[str] = Field(default_factory=list)
    warnings: List[str] = Field(default_factory=list)

class ProcessingStatus(BaseModel):
    is_processing: bool
    current_step: str
    progress: int
    errors: List[str]
    warnings: List[str]

class SettingsResponse(BaseModel):
    settings: Dict[str, Any]
    setting_info: Dict[str, Dict[str, Any]]  # Changed from str to Any to allow integers

class SettingsUpdateRequest(BaseModel):
    updates: Dict[str, Any]

# Helper functions
def get_xero_client():
    """
    DEPRECATED: Use auth_manager.get_authenticated_client() context manager instead.
    This function is kept for backward compatibility but should be replaced.
    """
    logger.warning("get_xero_client() is deprecated. Use auth_manager.get_authenticated_client() instead.")
    try:
        client = XeroAPIClient()
        if not client.authenticate():
            raise XeroAuthenticationError("Failed to authenticate with Xero")
        return client
    except XeroAuthenticationError:
        raise HTTPException(status_code=401, detail="Authentication with Xero failed")
    except Exception as e:
        logger.error(f"Failed to create Xero client: {e}")
        raise HTTPException(status_code=500, detail=str(e))

def update_processing_status(step: str, progress: int, error: str = None, warning: str = None):
    """Update global processing status."""
    processing_status["current_step"] = step
    processing_status["progress"] = progress
    if error:
        processing_status["errors"].append(error)
    if warning:
        processing_status["warnings"].append(warning)

# Initialize settings manager
settings_manager = SettingsManager()

# API Endpoints

@app.get("/api/settings", response_model=SettingsResponse)
async def get_settings():
    """Get current application settings."""
    try:
        logger.info("Getting settings...")
        settings = settings_manager.get_all_settings()
        setting_info = settings_manager.get_setting_info()
        
        logger.info(f"Loaded {len(settings)} setting categories")
        
        return SettingsResponse(
            settings=settings,
            setting_info=setting_info
        )
    except Exception as e:
        logger.error(f"Failed to get settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.put("/api/settings")
async def update_settings(request: SettingsUpdateRequest):
    """Update application settings."""
    try:
        success = settings_manager.update_settings(request.updates)
        
        if success:
            return {
                "success": True,
                "message": "Settings updated successfully",
                "updated_count": len(request.updates)
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to update settings")
            
    except Exception as e:
        logger.error(f"Failed to update settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/reset")
async def reset_settings():
    """Reset all settings to default values."""
    try:
        success = settings_manager.reset_to_defaults()
        
        if success:
            return {
                "success": True,
                "message": "Settings reset to defaults successfully"
            }
        else:
            raise HTTPException(status_code=500, detail="Failed to reset settings")
            
    except Exception as e:
        logger.error(f"Failed to reset settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/settings/export")
async def export_settings():
    """Export current settings for backup."""
    try:
        settings = settings_manager.export_settings()
        return {
            "success": True,
            "settings": settings,
            "exported_at": datetime.utcnow().isoformat()
        }
    except Exception as e:
        logger.error(f"Failed to export settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/settings/import")
async def import_settings(settings: Dict[str, Any]):
    """Import settings from backup."""
    try:
        success = settings_manager.import_settings(settings)
        
        if success:
            return {
                "success": True,
                "message": "Settings imported successfully"
            }
        else:
            raise HTTPException(status_code=400, detail="Failed to import settings")
            
    except Exception as e:
        logger.error(f"Failed to import settings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/")
async def root():
    """Root endpoint. Serve the static UI index.html if present, otherwise return JSON."""
    index_path = static_dir / "index.html"
    if index_path.exists():
        return FileResponse(path=str(index_path), media_type="text/html")

    return {"message": "Xero Payroll Automation API", "version": "1.0.0"}

@app.get("/favicon.ico")
async def favicon():
    """Serve favicon to prevent 404 errors."""
    favicon_path = static_dir / "favicon.ico"
    if favicon_path.exists():
        return FileResponse(path=str(favicon_path), media_type="image/x-icon")
    else:
        # Return empty response to prevent 404
        from fastapi.responses import Response
        return Response(content="", media_type="image/x-icon")

@app.get("/api/auth/status", response_model=AuthStatus)
async def get_auth_status():
    """Check authentication status with Xero using improved auth middleware."""
    try:
        status = auth_manager.get_connection_status()
        
        return AuthStatus(
            authenticated=status.get("authenticated", False),
            organization_name=status.get("organization_name"),
            tenant_id=status.get("tenant_id"),
            error=status.get("error")
        )
    except Exception as e:
        logger.error(f"Auth status check failed: {e}")
        return AuthStatus(authenticated=False, error=str(e))

@app.post("/api/auth/connect")
async def connect_to_xero():
    """Initiate Xero OAuth connection - returns authorization URL for redirect."""
    try:
        # Check if we already have a valid connection first
        status = auth_manager.get_connection_status()
        if status.get("authenticated"):
            return {
                "success": True,
                "message": "Already connected to Xero",
                "organization_name": status.get("organization_name"),
                "tenant_id": status.get("tenant_id")
            }
        
        # If not connected, get authorization URL
        try:
            client = XeroAPIClient()
            auth_url, state = client.auth_manager.get_authorization_url()
            
            return {
                "success": True,
                "auth_url": auth_url,
                "message": "Please complete authorization in the opened window"
            }
                    
        except Exception as e:
            logger.error(f"OAuth initiation failed: {e}")
            return {
                "success": False,
                "error": f"Failed to initiate OAuth: {str(e)}"
            }
            
    except Exception as e:
        logger.error(f"Connection failed: {e}")
        return {
            "success": False,
            "error": f"Connection failed: {str(e)}"
        }

@app.get("/api/auth/callback")
async def oauth_callback(code: str = None, state: str = None, error: str = None):
    """Handle OAuth callback from Xero."""
    try:
        if error:
            logger.error(f"OAuth error: {error}")
            # Redirect to main app with error parameter
            return RedirectResponse(url=f"/?error={error}", status_code=302)
        
        if not code:
            logger.error("No authorization code received")
            return RedirectResponse(url="/?error=no_code", status_code=302)
        
        logger.info("Processing OAuth callback with authorization code")
        
        # Exchange code for tokens using AuthManager
        client = XeroAPIClient()
        tokens = client.auth_manager.exchange_code_for_tokens(code)
        
        if tokens and tokens.get('access_token'):
            logger.info("Successfully exchanged code for tokens")
            
            # CRITICAL: Select tenant/organization
            if not client.auth_manager.select_tenant():
                logger.error("Failed to select tenant")
                return RedirectResponse(url="/?error=tenant_selection_failed", status_code=302)
            
            logger.info(f"Selected tenant: {client.auth_manager.tenant_name}")
            
            # CRITICAL: Save tokens to persistent storage
            try:
                client.auth_manager.save_tokens_to_storage()
                logger.info("Tokens saved to persistent storage")
            except Exception as e:
                logger.error(f"Failed to save tokens: {e}")
                return RedirectResponse(url="/?error=token_save_failed", status_code=302)
            
            # Clear cached status to force refresh
            auth_manager._connection_status = None
            auth_manager._last_validation_time = None
            
            # SUCCESS PAGE: Show success page that can be closed (for popup workflow)
            logger.info("Showing success page for popup closure")
            return HTMLResponse(content=f"""
            <html>
                <head><title>Xero Authorization Complete</title></head>
                <body style="font-family: Arial, sans-serif; text-align: center; padding: 50px; background: #f8f9fa;">
                    <div style="max-width: 400px; margin: 0 auto; background: white; padding: 30px; border-radius: 10px; box-shadow: 0 2px 10px rgba(0,0,0,0.1);">
                        <h2 style="color: #28a745; margin-bottom: 20px;">✅ Successfully Connected!</h2>
                        <p><strong>Organization:</strong> {client.auth_manager.tenant_name}</p>
                        <p style="color: #6c757d; margin: 20px 0;">You can now close this window and return to the application.</p>
                        <button onclick="window.close()" style="padding: 12px 24px; font-size: 16px; background: #007bff; color: white; border: none; border-radius: 5px; cursor: pointer; margin-right: 10px;">
                            Close Window
                        </button>
                    </div>
                    <script>
                        // Notify parent window of success
                        if (window.opener) {{
                            window.opener.postMessage('xero-auth-success', '*');
                        }}
                        // Auto-close after 5 seconds
                        setTimeout(function() {{
                            window.close();
                        }}, 5000);
                    </script>
                </body>
            </html>
            """, status_code=200)
        else:
            logger.error("Token exchange failed - no access token received")
            return RedirectResponse(url="/?error=token_exchange_failed", status_code=302)
            
    except Exception as e:
        logger.error(f"OAuth callback failed: {e}")
        return RedirectResponse(url=f"/?error=callback_failed", status_code=302)

@app.post("/api/auth/disconnect")
async def disconnect_from_xero():
    """Clear Xero authentication and disconnect."""
    try:
        auth_manager.clear_authentication()
        return {"success": True, "message": "Successfully disconnected from Xero"}
    except Exception as e:
        logger.error(f"Disconnect failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/upload")
async def upload_files(files: List[UploadFile] = File(...)):
    """Upload Excel files for processing."""
    try:
        # Create temporary directory for uploaded files
        with tempfile.TemporaryDirectory() as temp_dir:
            temp_path = Path(temp_dir)
            uploaded_files = []
            
            for file in files:
                # Save uploaded file to disk first
                file_path = temp_path / file.filename
                content = await file.read()
                with open(file_path, 'wb') as f:
                    f.write(content)

                # If the uploaded file is a ZIP archive, extract its contents
                if zipfile.is_zipfile(file_path):
                    with zipfile.ZipFile(file_path, 'r') as zf:
                        zf.extractall(temp_path)

                    # Collect extracted Excel files
                    for ext in ("*.xlsx", "*.xls"):
                        for extracted_file in temp_path.glob(ext):
                            uploaded_files.append(str(extracted_file))
                else:
                    # Treat as a regular Excel file
                    uploaded_files.append(str(file_path))
            
            # Parse files
            parsed_data = parse_excel_files(uploaded_files)
            
            # Store parsed data in session/cache (in production, use proper session management)
            # For now, save to a temporary file
            output_path = Path("temp_parsed_data.json")
            with open(output_path, 'w') as f:
                json.dump(parsed_data, f, default=str)
            
            return {
                "success": True,
                "message": f"Successfully uploaded and parsed {len(uploaded_files)} files",
                "parsed_data_summary": {
                    "site_employees": len(parsed_data.get("site_data", {}).get("employees", [])),
                    "travel_employees": len(parsed_data.get("travel_data", {}).get("employees", [])),
                    "overtime_employees": len(parsed_data.get("overtime_data", {}).get("overtime_rates_lookup", {}))
                }
            }
    except Exception as e:
        logger.error(f"Upload failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/validate", response_model=ValidationResult)
async def validate_data():
    """Validate parsed data against Xero using improved authentication."""
    try:
        # Load parsed data
        parsed_data_path = Path("temp_parsed_data.json")
        if not parsed_data_path.exists():
            raise HTTPException(status_code=400, detail="No parsed data found. Please upload files first.")
        
        with open(parsed_data_path, 'r') as f:
            parsed_data = json.load(f)
        
        # Use authenticated client with proper session management
        with auth_manager.get_authenticated_client() as client:
            # Fetch Xero data
            xero_employees = client.get_employees()
            tracking_categories = client.get_tracking_categories()
            
            # Extract regions
            xero_regions = []
            for category in tracking_categories:
                if 'region' in category.get('Name', '').lower():
                    for option in category.get('Options', []):
                        xero_regions.append(option.get('Name', ''))
        
        # Validate employees and regions
        validation_result = validate_against_xero(
            parsed_data,
            xero_employees,
            xero_regions
        )
        
        # Store validation result
        validation_path = Path("temp_validation_result.json")
        with open(validation_path, 'w') as f:
            json.dump(validation_result, f, default=str)
        
        return ValidationResult(**validation_result)
        
    except XeroAuthenticationError as e:
        logger.error(f"Authentication failed during validation: {e}")
        raise HTTPException(status_code=401, detail="Authentication with Xero failed. Please reconnect.")
    except Exception as e:
        logger.error(f"Validation failed: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.post("/api/consolidate")
async def consolidate_data():
    """Consolidate validated data into final JSON."""
    try:
        # Load parsed data and validation result
        parsed_data_path = Path("temp_parsed_data.json")
        validation_path = Path("temp_validation_result.json")
        
        if not parsed_data_path.exists() or not validation_path.exists():
            raise HTTPException(status_code=400, detail="Missing parsed data or validation result")
        
        with open(parsed_data_path, 'r') as f:
            parsed_data = json.load(f)
        
        with open(validation_path, 'r') as f:
            validation_result = json.load(f)
        
        # Consolidate data
        consolidator = DataConsolidator()

        # Convert date strings back to date objects
        site_data_raw = parsed_data["site_data"]
        travel_data_raw = parsed_data["travel_data"]
        overtime_data = parsed_data["overtime_data"]

        # PRE-PROCESS: Cap regular hours at 40 per employee BEFORE consolidation
        site_data_raw = cap_regular_hours_in_parsed_data(site_data_raw)

        # Get valid regions and valid employees from validation result
        valid_regions = set(validation_result.get("valid_regions", []))
        valid_employees_map = validation_result.get("valid_employees", {})

        # Filter parsed site/travel data to only include validated employees
        def filter_and_map_employees(data):
            filtered = {"file_type": data.get("file_type"), "employees": [], }
            if "pay_period_end_date" in data:
                filtered["pay_period_end_date"] = data.get("pay_period_end_date")
            for emp in data.get("employees", []):
                name = emp.get("employee_name")
                if name in valid_employees_map:
                    mapped_name = valid_employees_map[name]
                    # copy entries
                    filtered_emp = {
                        "employee_name": mapped_name,
                        "entries": emp.get("entries", [])
                    }
                    filtered["employees"].append(filtered_emp)
            return filtered

        site_data = convert_dates_in_data(filter_and_map_employees(site_data_raw))
        travel_data = convert_dates_in_data(filter_and_map_employees(travel_data_raw))

        # Ensure there are validated employees to consolidate
        if not site_data.get("employees") and not travel_data.get("employees"):
            raise HTTPException(status_code=400, detail="No validated employees to consolidate. Resolve mappings first.")

        # Consolidate
        consolidated = consolidator.consolidate(
            site_data,
            travel_data,
            overtime_data,
            valid_regions
        )
        
        # Convert to JSON format
        json_data = consolidator.to_target_json_format(consolidated)
        
        # Save consolidated data
        output_path = Path("consolidated_payroll_data.json")
        with open(output_path, 'w') as f:
            json.dump(json_data, f, indent=2, default=str)
        
        # Get unknown region report
        unknown_report = consolidator.get_unknown_region_report()
        
        return {
            "success": True,
            "message": "Data consolidated successfully",
            "output_file": str(output_path),
            "summary": {
                "total_employees": len(json_data.get("employees", [])),
                "pay_period_end_date": json_data.get("pay_period_end_date"),
                "unknown_regions": unknown_report.get("unknown_regions", []),
                "unknown_region_entries": len(unknown_report.get("unknown_region_entries", []))
            }
        }
        
    except Exception as e:
        # Save debug snapshot for investigation: parsed inputs and exception
        try:
            debug_path = Path('debug_consolidate_error.json')
            debug_payload = {
                'error': str(e),
                'parsed_data_sample': None,
                'validation_result_sample': None
            }
            # try to include parsed data and validation result if available in locals
            if 'parsed_data' in locals():
                debug_payload['parsed_data_sample'] = parsed_data
            if 'validation_result' in locals():
                debug_payload['validation_result_sample'] = validation_result
            with open(debug_path, 'w', encoding='utf-8') as df:
                json.dump(debug_payload, df, indent=2, default=str)
            logger.error(f"Wrote consolidation debug to {debug_path}")
        except Exception as ex:
            logger.error(f"Failed to write consolidation debug file: {ex}")

        logger.error(f"Consolidation failed: {e}")
        raise HTTPException(status_code=500, detail=f"Consolidation failed: {e}. Debug written to debug_consolidate_error.json")

@app.post("/api/submit-timesheets", response_model=TimesheetSubmissionResult)
async def submit_timesheets(request: TimesheetSubmissionRequest):
    """Submit timesheets to Xero using improved authentication."""
    try:
        # Validate payroll data format
        if not isinstance(request.payroll_data, dict):
            logger.error("Invalid payroll_data: expected object, got %s", type(request.payroll_data))
            raise HTTPException(status_code=400, detail="Invalid payroll_data format: expected JSON object")

        # Convert payroll data from dict
        if 'employee_timesheets' in request.payroll_data:
            payroll_data = PayrollData.from_dict(request.payroll_data)
        else:
            # Try to accept the consolidated JSON format produced by consolidate endpoint
            try:
                consolidated = request.payroll_data
                employee_timesheets = []
                for emp in consolidated.get('employees', []):
                    et = EmployeeTimesheet.from_dict({
                        'employee_name': emp['employee_name'],
                        'daily_entries': emp.get('daily_entries', []),
                        'pay_period_end_date': consolidated.get('pay_period_end_date')
                    })
                    employee_timesheets.append(et)

                payroll_data = PayrollData(employee_timesheets=employee_timesheets, pay_period_end_date=employee_timesheets[0].pay_period_end_date if employee_timesheets else None)
            except Exception:
                raise HTTPException(status_code=400, detail="Invalid payroll_data format")
        
        # Build timesheet payloads
        builder = TimesheetBuilder()
        payroll_calendar_cache = {}
        created_timesheets = []
        failed_timesheets = []
        
        # Create payload directory
        payload_dir = Path("debug_timesheet_payloads")
        payload_dir.mkdir(exist_ok=True)
        
        # Use authenticated client with proper session management
        with auth_manager.get_authenticated_client() as client:
            for employee_timesheet in payroll_data.employee_timesheets:
                try:
                    # Map employee name to Xero employee ID if provided in mappings
                    xero_emp_id = request.mappings.employee_mappings.get(employee_timesheet.employee_name) if request.mappings and request.mappings.employee_mappings else employee_timesheet.xero_employee_id

                    if not xero_emp_id:
                        failed_timesheets.append({
                            "employee": employee_timesheet.employee_name,
                            "error": "Employee not mapped to a Xero EmployeeID"
                        })
                        continue

                    # Create filtered timesheet
                    entries_for_timesheet = employee_timesheet.daily_entries if request.dry_run else [entry for entry in employee_timesheet.daily_entries if entry.region_name != 'Unknown']

                    filtered_timesheet = EmployeeTimesheet(
                        employee_name=employee_timesheet.employee_name,
                        daily_entries=entries_for_timesheet,
                        pay_period_end_date=employee_timesheet.pay_period_end_date,
                        xero_employee_id=xero_emp_id
                    )
                    
                    # Generate expected filename for this employee
                    safe_name = "".join(c if c.isalnum() or c in (' ', '_', '-') else '_' for c in employee_timesheet.employee_name).replace(' ', '_')
                    
                    # Check for existing payload file
                    existing_payload_file = None
                    for payload_file in payload_dir.glob(f"{safe_name}_*.json"):
                        try:
                            with open(payload_file, 'r', encoding='utf-8') as pf:
                                existing_payload_data = json.load(pf)
                                
                                if 'Timesheets' in existing_payload_data and existing_payload_data['Timesheets']:
                                    existing_employee_id = existing_payload_data['Timesheets'][0].get('EmployeeID')
                                else:
                                    existing_employee_id = existing_payload_data.get('EmployeeID')
                                
                                if existing_employee_id == xero_emp_id:
                                    existing_payload_file = payload_file
                                    logger.info(f"Found existing payload for {employee_timesheet.employee_name}: {payload_file}")
                                    break
                        except Exception as e:
                            logger.warning(f"Could not read existing payload file {payload_file}: {e}")
                            continue
                    
                    # Use existing payload or build new one
                    if existing_payload_file and not request.dry_run:
                        try:
                            with open(existing_payload_file, 'r', encoding='utf-8') as pf:
                                existing_payload_data = json.load(pf)
                            
                            if 'Timesheets' in existing_payload_data and existing_payload_data['Timesheets']:
                                timesheet_payload = existing_payload_data['Timesheets'][0]
                            else:
                                timesheet_payload = existing_payload_data
                                
                            logger.info(f"Using existing edited payload for {employee_timesheet.employee_name}")
                        except Exception as e:
                            logger.error(f"Failed to load existing payload for {employee_timesheet.employee_name}: {e}")
                            timesheet_payload = None
                    else:
                        timesheet_payload = None
                    
                    # Build new payload if needed
                    if timesheet_payload is None:
                        region_mappings = request.mappings.region_mappings if request.mappings else {}
                        earnings_mappings = dict(request.mappings.earnings_mappings) if request.mappings and request.mappings.earnings_mappings else {}

                        # Get payroll calendar ID
                        emp_id = filtered_timesheet.xero_employee_id
                        if emp_id in payroll_calendar_cache:
                            filtered_timesheet.payroll_calendar_id = payroll_calendar_cache[emp_id]
                        else:
                            try:
                                pcid = client.get_employee_payroll_calendar_id(emp_id)
                                if pcid:
                                    payroll_calendar_cache[emp_id] = pcid
                                    filtered_timesheet.payroll_calendar_id = pcid
                            except Exception as e:
                                logger.warning(f"Failed to fetch payrollCalendarID for {emp_id}: {e}")

                        # Business rule: treat HOLIDAY as REGULAR if specific earnings rates are missing
                        # TRAVEL should have its own earnings rate and not fall back to REGULAR
                        if 'REGULAR' in earnings_mappings:
                            if 'HOLIDAY' not in earnings_mappings:
                                earnings_mappings['HOLIDAY'] = earnings_mappings['REGULAR']

                        # Prepare region mappings
                        effective_region_mappings = dict(region_mappings)
                        effective_region_mappings.setdefault('Unknown', None)

                        # Build payload
                        timesheet_payload = builder.build_timesheet(
                            filtered_timesheet,
                            effective_region_mappings,
                            earnings_mappings
                        )
                    
                    # Save payload to disk if new
                    if existing_payload_file is None:
                        try:
                            timestamp = datetime.utcnow().strftime('%Y%m%dT%H%M%SZ')
                            payload_file = payload_dir / f"{safe_name}_{timestamp}.json"
                            with open(payload_file, 'w', encoding='utf-8') as pf:
                                json.dump(timesheet_payload, pf, indent=2, default=str)
                            logger.info(f"Saved NEW timesheet payload for {employee_timesheet.employee_name}")
                        except Exception as e:
                            logger.warning(f"Failed to save timesheet payload for {employee_timesheet.employee_name}: {e}")
                    
                    # Submit or validate
                    if not request.dry_run:
                        timesheet_id = client.create_timesheet(timesheet_payload)
                        created_timesheets.append(timesheet_id)
                    else:
                        errors = builder.validate_timesheet_data(timesheet_payload)
                        if errors:
                            failed_timesheets.append({
                                "employee": employee_timesheet.employee_name,
                                "errors": errors
                            })
                        else:
                            created_timesheets.append(f"dry-run-{employee_timesheet.employee_name}")
                    
                except Exception as e:
                    logger.error(f"Failed to create timesheet for {employee_timesheet.employee_name}: {e}")
                    failed_timesheets.append({
                        "employee": employee_timesheet.employee_name,
                        "error": str(e)
                    })
        
        return TimesheetSubmissionResult(
            success=len(created_timesheets) > 0,
            created_timesheets=created_timesheets,
            failed_timesheets=failed_timesheets,
            warnings=[f"{len(failed_timesheets)} timesheets failed"] if failed_timesheets else []
        )
        
    except XeroAuthenticationError as e:
        logger.error(f"Authentication failed during timesheet submission: {e}")
        return TimesheetSubmissionResult(
            success=False,
            created_timesheets=[],
            failed_timesheets=[],
            errors=["Authentication with Xero failed. Please reconnect."],
            warnings=[]
        )
    except Exception as e:
        logger.error(f"Timesheet submission failed: {e}")
        return TimesheetSubmissionResult(
            success=False,
            created_timesheets=[],
            failed_timesheets=[],
            errors=[str(e)],
            warnings=[]
        )



@app.get("/api/mappings")
async def get_mappings():
    """Get current mappings for employees, regions, and earnings rates using improved authentication."""
    try:
        # Use authenticated client with proper session management
        with auth_manager.get_authenticated_client() as client:
            # Get employees
            xero_employees = client.get_employees()
            employee_mappings = {emp['name']: emp['employee_id'] for emp in xero_employees}
            
            # Get regions
            tracking_categories = client.get_tracking_categories()
            region_mappings = {}
            for category in tracking_categories:
                if 'region' in category.get('Name', '').lower():
                    for option in category.get('Options', []):
                        region_mappings[option.get('Name')] = option.get('TrackingOptionID')
            
            # Get earnings rates
            earnings_rates = client.get_earnings_rates()
            
            # Map hour types to earnings rates
            hour_type_mappings = client.get_hour_type_mapping()
        
        return {
            "employee_mappings": employee_mappings,
            "region_mappings": region_mappings,
            "earnings_rates": earnings_rates,
            "hour_type_mappings": hour_type_mappings
        }
        
    except XeroAuthenticationError as e:
        logger.error(f"Authentication failed while getting mappings: {e}")
        raise HTTPException(status_code=401, detail="Authentication with Xero failed. Please reconnect.")
    except Exception as e:
        logger.error(f"Failed to get mappings: {e}")
        raise HTTPException(status_code=500, detail=str(e))

@app.get("/api/download-json")
async def download_json():
    """Download the consolidated JSON file."""
    file_path = Path("consolidated_payroll_data.json")
    if not file_path.exists():
        raise HTTPException(status_code=404, detail="Consolidated JSON not found")
    
    return FileResponse(
        path=str(file_path),
        filename="consolidated_payroll_data.json",
        media_type="application/json"
    )

@app.get("/api/status", response_model=ProcessingStatus)
async def get_processing_status():
    """Get current processing status."""
    return ProcessingStatus(**processing_status)

# Helper functions for data processing

def cap_regular_hours_in_parsed_data(site_data: Dict[str, Any]) -> Dict[str, Any]:
    """
    Cap regular hours at 40 per employee by reducing from the last working day.
    
    IMPORTANT: Only caps regular hours if the employee has overtime entries.
    If no overtime entries exist, regular hours are left unchanged.
    
    This processes the raw parsed data BEFORE consolidation to avoid complex logic later.
    
    Args:
        site_data: Raw site timesheet data from parser
        
    Returns:
        Modified site data with regular hours capped at 40 per employee (only if they have overtime)
    """
    from datetime import date
    
    # Process each employee
    for employee_data in site_data.get("employees", []):
        entries = employee_data.get("entries", [])
        employee_name = employee_data.get("employee_name", "Unknown")
        
        # Find all regular and overtime entries for this employee
        regular_entries = [entry for entry in entries if entry.get("hour_type") == "REGULAR"]
        overtime_entries = [entry for entry in entries if entry.get("hour_type") == "OVERTIME"]
        
        # CRITICAL CHECK: Only cap regular hours if employee has overtime entries
        if not overtime_entries:
            print(f"Employee {employee_name}: No overtime entries found, skipping regular hour capping")
            continue
        
        # Calculate total regular hours
        total_regular_hours = sum(float(entry.get("hours", 0)) for entry in regular_entries)
        total_overtime_hours = sum(float(entry.get("hours", 0)) for entry in overtime_entries)
        
        print(f"Employee {employee_name}: {total_regular_hours} regular hours, {total_overtime_hours} overtime hours")
        
        # If <= 40 regular hours, no changes needed even with overtime
        if total_regular_hours <= 40:
            print(f"Employee {employee_name}: Regular hours already <= 40, no capping needed")
            continue
            
        # Calculate excess hours to remove
        excess_hours = total_regular_hours - 40
        print(f"Employee {employee_name}: Capping {excess_hours} excess regular hours (has overtime)")
        
        # Sort regular entries by date (latest first) to reduce from last working days
        regular_entries_by_date = sorted(
            regular_entries, 
            key=lambda x: x.get("entry_date") if isinstance(x.get("entry_date"), date) else date.fromisoformat(x.get("entry_date")), 
            reverse=True
        )
        
        # Build reduction map: which entries to reduce and by how much
        reductions = {}  # key: entry_index, value: reduction_amount
        remaining_excess = excess_hours
        
        # Map entries to their indices for easy lookup
        entry_indices = {id(entry): idx for idx, entry in enumerate(entries)}
        
        for reg_entry in regular_entries_by_date:
            if remaining_excess <= 0:
                break
                
            entry_hours = float(reg_entry.get("hours", 0))
            if entry_hours >= remaining_excess:
                # This entry can absorb all remaining excess
                entry_idx = entry_indices[id(reg_entry)]
                reductions[entry_idx] = remaining_excess
                remaining_excess = 0
            else:
                # This entry will be completely consumed
                entry_idx = entry_indices[id(reg_entry)]
                reductions[entry_idx] = entry_hours
                remaining_excess -= entry_hours
        
        # Apply reductions to the entries
        for entry_idx, reduction in reductions.items():
            entry = entries[entry_idx]
            current_hours = float(entry.get("hours", 0))
            new_hours = current_hours - reduction
            
            if new_hours > 0:
                # Update entry with reduced hours
                entry["hours"] = new_hours
                print(f"Employee {employee_name}: Reduced entry from {current_hours} to {new_hours} hours")
            else:
                # Mark entry for removal (set hours to 0, will be filtered out later)
                entry["hours"] = 0
                print(f"Employee {employee_name}: Removed entry with {current_hours} hours")
        
        # Remove entries with 0 hours
        original_count = len(entries)
        employee_data["entries"] = [entry for entry in entries if float(entry.get("hours", 0)) > 0]
        new_count = len(employee_data["entries"])
        
        if original_count != new_count:
            print(f"Employee {employee_name}: Removed {original_count - new_count} zero-hour entries")
    
    return site_data

def parse_excel_files(file_paths: List[str]) -> Dict[str, Any]:
    """Parse Excel files using the parser registry."""
    parsers = [
        SiteTimesheetParser(),
        OvertimeRatesParser(),
        TravelTimeParser(),
    ]
    
    site_data = {"employees": [], "file_type": "site_timesheet"}
    travel_data = {"employees": [], "file_type": "travel_time"}
    overtime_data = {"employees": [], "file_type": "overtime_rates", "overtime_rates_lookup": {}}
    
    for file_path in file_paths:
        for parser in parsers:
            try:
                if parser.validate_format(file_path):
                    parsed = parser.parse(file_path)
                    
                    if isinstance(parser, SiteTimesheetParser):
                        site_data["employees"].extend(parsed.get("employees", []))
                        if "pay_period_end_date" in parsed:
                            site_data["pay_period_end_date"] = parsed["pay_period_end_date"]
                    elif isinstance(parser, TravelTimeParser):
                        travel_data["employees"].extend(parsed.get("employees", []))
                    elif isinstance(parser, OvertimeRatesParser):
                        overtime_data["overtime_rates_lookup"].update(
                            parsed.get("overtime_rates_lookup", {})
                        )
                    break
            except Exception as e:
                logger.warning(f"Parser {parser.__class__.__name__} failed for {file_path}: {e}")
    
    return {
        "site_data": site_data,
        "travel_data": travel_data,
        "overtime_data": overtime_data
    }

def validate_against_xero(parsed_data: Dict[str, Any], 
                          xero_employees: List[Dict[str, Any]], 
                          xero_regions: List[str]) -> Dict[str, Any]:
    """Validate parsed data against Xero data."""
    errors = []
    warnings = []
    unmapped_regions = set()
    unmapped_employees = set()
    
    # Create employee matcher
    matcher = EmployeeMatcher()
    matcher.set_xero_employees(xero_employees)
    
    # Collect all regions and employees from parsed data
    all_regions = set()
    all_employees = set()
    
    for emp_data in parsed_data.get("site_data", {}).get("employees", []):
        all_employees.add(emp_data.get("employee_name"))
        for entry in emp_data.get("entries", []):
            all_regions.add(entry.get("region_name"))
    
    for emp_data in parsed_data.get("travel_data", {}).get("employees", []):
        all_employees.add(emp_data.get("employee_name"))
        for entry in emp_data.get("entries", []):
            all_regions.add(entry.get("region_name"))
    
    # Validate regions
    valid_regions = []
    for region in all_regions:
        if region and region in xero_regions:
            valid_regions.append(region)
        elif region:
            unmapped_regions.add(region)
            warnings.append(f"Region '{region}' not found in Xero")
    
    # Validate employees
    valid_employees = {}
    for employee in all_employees:
        if employee:
            match_result = matcher.match_employee(employee, require_confirmation=False)
            if match_result.matched_name:
                valid_employees[employee] = match_result.matched_name
            else:
                unmapped_employees.add(employee)
                warnings.append(f"Employee '{employee}' not found in Xero")
    
    return {
        "valid": len(errors) == 0,
        "errors": errors,
        "warnings": warnings,
        "unmapped_regions": list(unmapped_regions),
        "unmapped_employees": list(unmapped_employees),
        "valid_regions": valid_regions,
        "valid_employees": valid_employees,
        "summary": {
            "total_regions": len(all_regions),
            "valid_regions": len(valid_regions),
            "total_employees": len(all_employees),
            "valid_employees": len(valid_employees)
        }
    }

def convert_dates_in_data(data: Dict[str, Any]) -> Dict[str, Any]:
    """Convert date strings to date objects in parsed data."""
    from datetime import date
    
    if "pay_period_end_date" in data and isinstance(data["pay_period_end_date"], str):
        data["pay_period_end_date"] = date.fromisoformat(data["pay_period_end_date"])
    
    for emp_data in data.get("employees", []):
        for entry in emp_data.get("entries", []):
            if "entry_date" in entry and isinstance(entry["entry_date"], str):
                entry["entry_date"] = date.fromisoformat(entry["entry_date"])
    
    return data

# Mount static files for UI
from pathlib import Path
static_dir = Path(__file__).parent.parent / "static"
if static_dir.exists():
    # Mount static files under /static to avoid clashing with API root routes
    app.mount("/static", StaticFiles(directory=str(static_dir), html=True), name="static")

if __name__ == "__main__":
    import uvicorn
    # Run via uvicorn when the module is executed directly
    uvicorn.run(app, host="0.0.0.0", port=8000, reload=True)