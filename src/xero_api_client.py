"""
Xero API Client for Payroll Automation

This module provides a high-level interface for interacting with Xero APIs,
specifically for payroll automation tasks including fetching employees,
tracking categories, and creating timesheets.
"""

import requests
import time
import logging
from typing import List, Dict, Any, Optional, Tuple
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from .auth_manager import AuthManager
from config.settings import MAX_RETRIES, HOUR_TYPE_TO_XERO_MAPPING


# Configure logging
logger = logging.getLogger(__name__)


class XeroAPIError(Exception):
    """Base exception for Xero API errors"""
    pass


class XeroRateLimitError(XeroAPIError):
    """Exception raised when Xero API rate limit is exceeded"""
    def __init__(self, message: str, retry_after: int = None):
        super().__init__(message)
        self.retry_after = retry_after


class XeroAuthenticationError(XeroAPIError):
    """Exception raised for authentication failures"""
    pass


class XeroValidationError(XeroAPIError):
    """Exception raised for validation errors from Xero API"""
    pass





class XeroAPIClient:
    """
    High-level Xero API client for payroll automation
    
    Handles authentication, API calls, error handling, rate limiting, and retry logic
    for Xero integration.
    """
    
    # Rate limiting constants
    DEFAULT_RATE_LIMIT = 60  # requests per minute
    RATE_LIMIT_WINDOW = 60  # seconds
    
    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None):
        """
        Initialize Xero API client
        
        Args:
            client_id: Xero app client ID
            client_secret: Xero app client secret
        """
        self.auth_manager = AuthManager(client_id, client_secret)
        self.base_url = "https://api.xero.com"
        self.tenant_id = None  # Will be set after authentication
        
        # Rate limiting tracking
        self._request_times = []
        self._rate_limit = self.DEFAULT_RATE_LIMIT
        
        # Configure HTTP session with retry strategy
        self.session = requests.Session()
        retry_strategy = Retry(
            total=MAX_RETRIES,
            status_forcelist=[429, 500, 502, 503, 504],
            allowed_methods=["HEAD", "GET", "OPTIONS"],
            backoff_factor=1
        )
        adapter = HTTPAdapter(max_retries=retry_strategy)
        self.session.mount("http://", adapter)
        self.session.mount("https://", adapter)
    
    def _wait_for_rate_limit(self) -> None:
        """
        Implement rate limiting by waiting if necessary
        """
        current_time = time.time()
        
        # Remove requests older than the rate limit window
        self._request_times = [
            req_time for req_time in self._request_times 
            if current_time - req_time < self.RATE_LIMIT_WINDOW
        ]
        
        # If we're at the rate limit, wait
        if len(self._request_times) >= self._rate_limit:
            oldest_request = min(self._request_times)
            wait_time = self.RATE_LIMIT_WINDOW - (current_time - oldest_request)
            if wait_time > 0:
                logger.info(f"Rate limit reached, waiting {wait_time:.2f} seconds")
                time.sleep(wait_time)
        
        # Record this request
        self._request_times.append(current_time)
    
    def _make_request(self, method: str, endpoint: str, **kwargs) -> requests.Response:
        """
        Make HTTP request with proper error handling and retry logic
        
        Args:
            method: HTTP method (GET, POST, etc.)
            endpoint: API endpoint (relative to base_url)
            **kwargs: Additional arguments for requests
            
        Returns:
            Response object
            
        Raises:
            XeroAPIError: For various API errors
            XeroRateLimitError: When rate limit is exceeded
            XeroAuthenticationError: For auth failures
        """
        # Ensure we're authenticated
        if not self.authenticate():
            raise XeroAuthenticationError("Failed to authenticate with Xero")
        
        # Apply rate limiting
        self._wait_for_rate_limit()
        
        # Get auth headers from auth manager (includes tenant ID)
        headers = self.auth_manager.get_auth_headers()
        headers.update(kwargs.get('headers', {}))
        
        kwargs['headers'] = headers
        
        url = f"{self.base_url}/{endpoint.lstrip('/')}"
        
        try:
            logger.debug(f"Making {method} request to {url}")
            response = self.session.request(method, url, **kwargs)
            
            # Handle rate limiting
            if response.status_code == 429:
                retry_after = int(response.headers.get('Retry-After', 60))
                raise XeroRateLimitError(
                    f"Rate limit exceeded. Retry after {retry_after} seconds",
                    retry_after=retry_after
                )
            
            # Handle authentication errors
            if response.status_code == 401:
                logger.info("Received 401, attempting token refresh")
                try:
                    # Try to refresh token and retry once
                    self.auth_manager.refresh_access_token()
                    
                    # Update headers with new token
                    headers = self.auth_manager.get_auth_headers()
                    kwargs['headers'] = headers
                    
                    logger.debug(f"Retrying {method} request to {url} with new token")
                    response = self.session.request(method, url, **kwargs)
                    
                    if response.status_code == 401:
                        raise XeroAuthenticationError("Authentication failed after token refresh")
                        
                except Exception as e:
                    raise XeroAuthenticationError(f"Token refresh failed: {e}")
            
            # Handle validation errors
            if response.status_code == 400:
                error_data = self._parse_error_response(response)
                raise XeroValidationError(f"Validation error: {error_data}")
            
            # Handle other client errors
            if 400 <= response.status_code < 500:
                error_data = self._parse_error_response(response)
                raise XeroAPIError(f"Client error {response.status_code}: {error_data}")
            
            # Handle server errors
            if response.status_code >= 500:
                raise XeroAPIError(f"Server error {response.status_code}: {response.text}")
            
            logger.debug(f"Request successful: {response.status_code}")
            return response
            
        except requests.exceptions.RequestException as e:
            raise XeroAPIError(f"Network error: {e}")
    
    def _parse_error_response(self, response: requests.Response) -> str:
        """
        Parse error response from Xero API
        
        Args:
            response: Error response from API
            
        Returns:
            Formatted error message
        """
        try:
            error_data = response.json()
            if 'Elements' in error_data:
                # Handle validation errors format
                errors = []
                for element in error_data['Elements']:
                    if 'ValidationErrors' in element:
                        for validation_error in element['ValidationErrors']:
                            errors.append(validation_error.get('Message', 'Unknown validation error'))
                return '; '.join(errors)
            elif 'Message' in error_data:
                return error_data['Message']
            elif 'error_description' in error_data:
                return error_data['error_description']
            else:
                return str(error_data)
        except (ValueError, KeyError):
            return response.text or f"HTTP {response.status_code}"
    
    def _get_current_token(self) -> str:
        """
        Get current access token
        
        Returns:
            Current access token
        """
        return self.auth_manager.ensure_valid_access_token()
    
    def authenticate(self) -> bool:
        """
        Ensure the client is authenticated with Xero
        
        Returns:
            True if authentication successful, False otherwise
        """
        # Use AuthManager to load existing tokens or start authorization
        if not self.auth_manager.load_tokens_from_storage():
            print("AUTH: Xero authorization required...")
            success = self.auth_manager.authorize()
            if not success:
                return False

        # Tenant ID is handled by AuthManager
        return True
    

    
    def get_employees(self) -> List[Dict[str, Any]]:
        """
        Fetch employees from Xero with pagination support
        
        Returns:
            List of employee dictionaries with 'employee_id' and 'name' keys
            
        Raises:
            XeroAPIError: If API request fails
            XeroAuthenticationError: If authentication fails
        """
        employees = []
        page = 1
        
        try:
            # Try UK payroll first
            try:
                while True:
                    response = self._make_request(
                        'GET', 
                        f'payroll.xro/2.0/employees?page={page}'
                    )
                    
                    data = response.json()
                    # Handle both uppercase and lowercase response formats
                    page_employees = data.get('Employees', data.get('employees', []))
                    
                    if not page_employees:
                        break
                    
                    for emp in page_employees:
                        # Handle both uppercase and lowercase field names
                        employee = {
                            'employee_id': emp.get('EmployeeID', emp.get('employeeID')),
                            'name': f"{emp.get('FirstName', emp.get('firstName', ''))} {emp.get('LastName', emp.get('lastName', ''))}".strip()
                        }
                        if employee['employee_id'] and employee['name']:
                            employees.append(employee)
                    
                    # Check if there are more pages
                    if len(page_employees) < 100:  # Xero default page size
                        break
                    page += 1
                
                logger.info(f"Fetched {len(employees)} employees from Payroll API")
                return employees
                
            except XeroValidationError as e:
                if "Not an UK Customer" in str(e):
                    logger.info("UK Payroll not available, falling back to Contacts API")
                    # Fall back to Contacts API
                    page = 1
                    employees = []
                    
                    while True:
                        response = self._make_request(
                            'GET',
                            f'api.xro/2.0/Contacts?where=IsCustomer==false+AND+IsSupplier==false&page={page}'
                        )
                        
                        data = response.json()
                        page_contacts = data.get('Contacts', [])
                        
                        if not page_contacts:
                            break
                        
                        for contact in page_contacts:
                            employee = {
                                'employee_id': contact.get('ContactID'),
                                'name': contact.get('Name', '').strip()
                            }
                            if employee['employee_id'] and employee['name']:
                                employees.append(employee)
                        
                        # Check if there are more pages
                        if len(page_contacts) < 100:
                            break
                        page += 1
                    
                    logger.info(f"Fetched {len(employees)} employees from Contacts API")
                    return employees
                else:
                    raise
                    
        except (XeroAPIError, XeroAuthenticationError):
            raise
        except Exception as e:
            raise XeroAPIError(f"Unexpected error fetching employees: {e}")

    def get_employee(self, employee_id: str) -> Dict[str, Any]:
        """
        Fetch a single employee record from Xero Payroll by employee ID.

        Args:
            employee_id: Xero EmployeeID (UUID)

        Returns:
            The parsed employee object (dictionary) as returned by Xero. The
            API typically nests this under the 'employee' key; this method
            returns that inner object when present.

        Raises:
            XeroAPIError: For network/HTTP errors or unexpected response shapes.
            XeroAuthenticationError: If authentication fails.
        """
        try:
            response = self._make_request('GET', f'payroll.xro/2.0/Employees/{employee_id}')
            data = response.json()

            # Some responses include the employee object nested under the 'employee' key
            if isinstance(data, dict) and 'employee' in data:
                return data['employee']

            # Fallback: return the response body as-is
            return data

        except (XeroAPIError, XeroAuthenticationError):
            raise
        except Exception as e:
            raise XeroAPIError(f"Unexpected error fetching employee {employee_id}: {e}")

    def get_employee_payroll_calendar_id(self, employee_id: str) -> Optional[str]:
        """
        Convenience helper to extract the `payrollCalendarID` for a given employee.

        Returns the payroll calendar UUID string if present, otherwise None.
        """
        emp = self.get_employee(employee_id)
        if not isinstance(emp, dict):
            return None

        # Accept both camelCase and PascalCase variants
        return emp.get('payrollCalendarID') or emp.get('PayrollCalendarID')
    
    def get_payroll_calendar(self, calendar_id: str) -> Dict[str, Any]:
        """
        Fetch payroll calendar details by ID.
        
        Args:
            calendar_id: Payroll calendar ID
            
        Returns:
            Payroll calendar details including pay periods
            
        Raises:
            XeroAPIError: If API request fails
        """
        try:
            response = self._make_request('GET', f'payroll.xro/2.0/PayrollCalendars/{calendar_id}')
            data = response.json()
            
            # Handle different response structures
            if 'payrollCalendar' in data:
                return data['payrollCalendar']
            elif 'PayrollCalendar' in data:
                return data['PayrollCalendar']
            else:
                return data
                
        except (XeroAPIError, XeroAuthenticationError):
            raise
        except Exception as e:
            raise XeroAPIError(f"Unexpected error fetching payroll calendar {calendar_id}: {e}")
    
    def get_payroll_calendars(self) -> List[Dict[str, Any]]:
        """
        Fetch all payroll calendars.
        
        Returns:
            List of payroll calendar dictionaries
            
        Raises:
            XeroAPIError: If API request fails
        """
        try:
            response = self._make_request('GET', 'payroll.xro/2.0/PayrollCalendars')
            data = response.json()
            
            # Handle different response structures
            if 'payrollCalendars' in data:
                return data['payrollCalendars']
            elif 'PayrollCalendars' in data:
                return data['PayrollCalendars']
            else:
                return data if isinstance(data, list) else []
                
        except (XeroAPIError, XeroAuthenticationError):
            raise
        except Exception as e:
            raise XeroAPIError(f"Unexpected error fetching payroll calendars: {e}")
    
    def get_tracking_categories(self):
        """Fetch tracking categories from Xero API"""
        try:
            print("DEBUG: About to call tracking categories API")

            # Use the standard _make_request method which handles auth properly
            response = self._make_request('GET', 'api.xro/2.0/TrackingCategories')

            print(f"DEBUG: Response status: {response.status_code}")
            print(f"DEBUG: Response content-type: {response.headers.get('Content-Type')}")

            # Check if response is JSON or XML, as the API can return either
            content_type = response.headers.get('Content-Type', '').lower()

            if 'application/json' in content_type:
                # Handle standard JSON response
                data = response.json()
                return data.get('TrackingCategories', [])

            elif 'text/xml' in content_type:
                # Handle XML response, which the UK Demo Company uses for this endpoint
                import xml.etree.ElementTree as ET

                root = ET.fromstring(response.text)
                tracking_categories = []

                # Parse XML to extract tracking categories into the expected dictionary format
                for tc_elem in root.findall('.//TrackingCategory'):
                    name_elem = tc_elem.find('Name')
                    id_elem = tc_elem.find('TrackingCategoryID')
                    
                    if name_elem is not None and id_elem is not None:
                        tc_data = {
                            'Name': name_elem.text,
                            'TrackingCategoryID': id_elem.text,
                            'Options': []
                        }

                        # Parse the options within the category
                        options_elem = tc_elem.find('Options')
                        if options_elem is not None:
                            for option_elem in options_elem.findall('.//Option'):
                                option_name_elem = option_elem.find('Name')
                                option_id_elem = option_elem.find('TrackingOptionID')

                                if option_name_elem is not None and option_id_elem is not None:
                                    tc_data['Options'].append({
                                        'Name': option_name_elem.text,
                                        'TrackingOptionID': option_id_elem.text,
                                    })

                        tracking_categories.append(tc_data)

                return tracking_categories

            else:
                raise XeroAPIError(f"Unexpected content type from TrackingCategories endpoint: {content_type}")

        except XeroAPIError:
            raise
        except Exception as e:
            raise XeroAPIError(f"Unexpected error fetching tracking categories: {e}")
           
    def get_tracking_category_options(self, category_name: str = None) -> List[str]:
        """
        Get tracking category option names (for backward compatibility)
        
        Args:
            category_name: Specific category to get options for (if None, gets all)
            
        Returns:
            List of tracking option names
        """
        categories = self.get_tracking_categories()
        
        if category_name:
            return list(categories.get(category_name, {}).keys())
        
        # Return all option names from all categories
        all_options = []
        for options in categories.values():
            all_options.extend(options.keys())
        
        return all_options
    
    

    # This is the ONLY earnings_rates method you need.
# Paste this into your XeroAPIClient class.

    def get_earnings_rates(self) -> Dict[str, str]:
        """
        Primary method to fetch earnings rates.

        This method discovers all unique earnings rates by iterating through
        each employee's pay template. This is the definitive method that works
        with the limited OAuth scopes provided in the PRD.
        """
        print("INFO: Discovering Earnings Rate IDs by iterating through employee pay templates...")
        
        try:
            employees = self.get_employees()
            if not employees:
                logger.warning("No employees found, cannot discover earnings rates.")
                return {}
        except XeroAPIError as e:
            raise XeroAPIError("Could not fetch employees, which is a required step for discovering earnings rates.") from e
            
        all_discovered_rates = {}
        print(f"INFO: Found {len(employees)} employees. Checking their pay templates for all unique earnings rates...")
        
        for employee in employees:
            employee_id = employee.get('employee_id')
            employee_name = employee.get('name')
            
            if not employee_id:
                continue
            
            try:
                # This endpoint is covered by the 'payroll.employees.read' scope
                endpoint = f'payroll.xro/2.0/Employees/{employee_id}/PayTemplates'
                response = self._make_request('GET', endpoint)
                data = response.json()
                
                # Based on the user's discovery from the API Explorer.
                pay_template_data = data.get('payTemplate', {})
                earnings_lines = pay_template_data.get('earningTemplates', [])
                
                if not earnings_lines:
                    logger.info(f"No additional earning templates found for {employee_name}.")
                    continue

                for line in earnings_lines:
                    rate_name = line.get('name')
                    rate_id = line.get('earningsRateID')
                    
                    if rate_name and rate_id and rate_name not in all_discovered_rates:
                        all_discovered_rates[rate_name] = rate_id
                        print(f"   ✅ Discovered rate: '{rate_name}' (ID: {rate_id}) from {employee_name}'s template.")
                            
            except XeroAPIError as e:
                if "404" in str(e):
                    logger.warning(f"No pay template found for employee {employee_name}. Skipping.")
                else:
                    logger.error(f"Error fetching pay template for {employee_name}: {e}")
            except Exception as e:
                logger.error(f"An unexpected error occurred for {employee_name}: {e}")

        # --- IMPORTANT CHANGE ---
        # It's possible that the BASE rate (Regular Hours) isn't in the earningTemplates.
        # Let's add it manually from the main pay template object if it's missing.
        # This part is hypothetical but good defensive coding.
        # For now, the loop above should be sufficient based on your JSON.

        if not all_discovered_rates:
            raise XeroAPIError("Could not discover ANY earnings rates across ALL employee pay templates. "
                               "ACTION REQUIRED: In the Xero UI, go to at least one employee's 'Pay Template' "
                               "and manually add lines for 'Overtime Hours' and any other rates you need. "
                               "The script will then be able to discover their IDs.")

        print(f"INFO: Finished discovery. Found {len(all_discovered_rates)} unique earnings rates.")
        return all_discovered_rates
    

    
    
    def get_hour_type_mapping(self) -> Dict[str, str]:
        """
        Get mapping of internal hour types to Xero earnings rate IDs
        
        Returns:
            Dictionary mapping hour types to earnings rate IDs:
            {
                'REGULAR': 'earnings_rate_id_1',
                'OVERTIME': 'earnings_rate_id_2', 
                'HOLIDAY': 'earnings_rate_id_3'
            }
        """
        earnings_rates = self.get_earnings_rates()
        
        # Common mappings for different naming conventions
        hour_type_mappings = {
            'REGULAR': ['Regular Hours', 'Regular', 'Ordinary Hours', 'Standard Hours'],
            'OVERTIME': ['Overtime Hours', 'Overtime', 'OT Hours', 'Time and a Half'],
            'HOLIDAY': ['Holiday', 'Holiday Hours', 'Public Holiday', 'Holiday Pay'],
            'TRAVEL': ['Travel Hours', 'Travel', 'Travel Time', 'Travel Pay']
        }
        
        mapping = {}
        
        for hour_type, possible_names in hour_type_mappings.items():
            for name in possible_names:
                if name in earnings_rates:
                    mapping[hour_type] = earnings_rates[name]
                    break
        
        return mapping
    
    def create_timesheet(self, timesheet_data: Dict[str, Any]) -> str:
        """
        Create a single timesheet in Xero using the Payroll API.
        
        Args:
            timesheet_data: Timesheet data dictionary with required fields:
                - payrollCalendarID: The Xero identifier for the Payroll Calendar
                - employeeID: The Xero identifier for the Employee
                - startDate: The Start Date of the Timesheet period (YYYY-MM-DD)
                - endDate: The End Date of the Timesheet period (YYYY-MM-DD)
                Optional fields:
                - status: Timesheet status (defaults to "Draft")
                - timesheetLines: Collection of worked hours by day
            
        Returns:
            Created timesheet ID
            
        Raises:
            XeroAPIError: If API request fails
            XeroAuthenticationError: If authentication fails
            XeroValidationError: If timesheet data is invalid
        """
        try:
            # Normalize field names to lowercase as required by Xero API
            normalized_data = {}
            field_mappings = {
                'payrollCalendarID': ['payrollCalendarID', 'PayrollCalendarID', 'payrollCalendarId'],
                'employeeID': ['employeeID', 'EmployeeID', 'employeeId'],
                'startDate': ['startDate', 'StartDate'],
                'endDate': ['endDate', 'EndDate'],
                'status': ['status', 'Status'],
                'timesheetLines': ['timesheetLines', 'TimesheetLines']
            }
            
            for target_field, source_fields in field_mappings.items():
                for source_field in source_fields:
                    if source_field in timesheet_data:
                        normalized_data[target_field] = timesheet_data[source_field]
                        break
            
            # Validate required fields
            required_fields = ['payrollCalendarID', 'employeeID', 'startDate', 'endDate']
            missing_fields = [field for field in required_fields if field not in normalized_data]
            if missing_fields:
                raise XeroValidationError(f"Missing required fields: {', '.join(missing_fields)}")
            
            logger.debug(f"Creating timesheet for employee {normalized_data.get('employeeID')}")
            logger.debug(f"Timesheet request payload: {normalized_data}")
            
            # Make the API request
            response = self._make_request(
                'POST',
                'payroll.xro/2.0/timesheets',
                json=normalized_data
            )
            
            logger.debug(f"Timesheet response status: {response.status_code}")
            
            # Parse the response
            data = response.json()
            
            # Handle different response structures
            timesheet = None
            timesheet_id = None
            
            # Check for 'timesheet' in response (single timesheet format)
            if 'timesheet' in data:
                timesheet = data['timesheet']
                timesheet_id = timesheet.get('timesheetID')
            # Check for 'Timesheets' array in response
            elif 'Timesheets' in data and data['Timesheets']:
                timesheet = data['Timesheets'][0]
                timesheet_id = timesheet.get('TimesheetID')
            
            if not timesheet_id:
                # Log the full response for debugging
                logger.error(f"No timesheet ID found in response: {data}")
                raise XeroAPIError("No timesheet ID returned from Xero API")
            
            logger.info(f"Successfully created timesheet with ID: {timesheet_id}")
            return timesheet_id
            
        except (XeroAPIError, XeroAuthenticationError, XeroValidationError):
            raise
        except Exception as e:
            raise XeroAPIError(f"Unexpected error creating timesheet: {e}")
    
    
    def get_connection_status(self) -> Dict[str, Any]:
        """
        Get connection status and basic info
        
        Returns:
            Dictionary with connection information
        """
        status = {
            'authenticated': False,
            'tenant_id': None,
            'organization_name': None,
            'error': None
        }
        
        try:
            if not self.auth_manager.load_tokens_from_storage():
                status['error'] = 'Not authorized'
                return status
            
            # Use auth manager's auth headers
            headers = self.auth_manager.get_auth_headers()
            
            response = self.session.get(
                f"{self.base_url}/connections",
                headers=headers
            )
            
            if response.status_code == 200:
                connections = response.json()
                if connections:
                    connection = connections[0]
                    status['authenticated'] = True
                    status['tenant_id'] = connection.get('tenantId')
                    status['organization_name'] = connection.get('tenantName')
                    self.tenant_id = status['tenant_id']
                else:
                    status['error'] = f"API error: {response.status_code}"
                    
        except Exception as e:
            status['error'] = str(e)
        
        return status

    def get_organizations(self) -> List[Dict[str, Any]]:
        """Fetch organization details from Xero"""
        try:
            # The 'connections' endpoint is often the most reliable way to get org info
            response = self._make_request('GET', 'connections')
            return response.json()
        except XeroAPIError:
            # Fallback for older APIs if connections doesn't work
            response = self._make_request('GET', 'api.xro/2.0/Organisation')
            return response.json().get('Organisations', [])
    
    
    def resolve_employee_mapping(self, sheet_name: str) -> Optional[str]:
        """
        Resolve employee name from sheet to Xero employee ID.
        
        Args:
            sheet_name: Employee name from timesheet
            
        Returns:
            Xero employee ID if found, None otherwise
        """
        employees = self.get_employees()
        
        # Try exact match first
        for emp in employees:
            if emp['name'].lower() == sheet_name.lower():
                return emp['employee_id']
        
        # Try partial match (last name)
        sheet_parts = sheet_name.split()
        if sheet_parts:
            last_name = sheet_parts[-1].lower()
            for emp in employees:
                if last_name in emp['name'].lower():
                    return emp['employee_id']
        
        return None
    
    def resolve_region_mapping(self, region_name: str) -> Optional[str]:
        """
        Resolve region name to Xero tracking option ID.
        
        Args:
            region_name: Region name from timesheet
            
        Returns:
            Xero tracking option ID if found, None otherwise
        """
        tracking_categories = self.get_tracking_categories()
        
        for category in tracking_categories:
            if 'region' in category.get('Name', '').lower():
                for option in category.get('Options', []):
                    if option.get('Name', '').lower() == region_name.lower():
                        return option.get('TrackingOptionID')
        
        return None
    
    def resolve_earnings_rate_mapping(self, hour_type: str) -> Optional[str]:
        """
        Resolve hour type to Xero earnings rate ID.
        
        Args:
            hour_type: Hour type (REGULAR, OVERTIME, etc.)
            
        Returns:
            Xero earnings rate ID if found, None otherwise
        """
        mappings = self.get_hour_type_mapping()
        return mappings.get(hour_type)
    
    
    def close(self):
        """
        Close the HTTP session
        """
        if hasattr(self, 'session'):
            self.session.close()


