"""
Timesheet Builder for Xero API Integration

This module provides functionality to convert internal timesheet data structures
to Xero API-compatible timesheet format, handling date formatting, timezone
considerations, and API schema mapping.
"""

import logging
from datetime import date, datetime, timezone
from typing import Dict, Any, List, Optional
from .models import EmployeeTimesheet, DailyEntry, HourType

# Configure logging
logger = logging.getLogger(__name__)


class TimesheetBuilderError(Exception):
    """Base exception for timesheet builder errors"""
    pass


class TimesheetBuilder:
    """
    Converts internal timesheet data to Xero API timesheet format
    
    This class handles the transformation of consolidated timesheet data
    into the specific format required by the Xero Timesheets API, including
    proper date formatting, timezone handling, and schema mapping.
    """
    
    def __init__(self):
        """Initialize the timesheet builder"""
        self.logger = logging.getLogger(__name__)
    
    def build_timesheet(self, employee_timesheet: EmployeeTimesheet, 
                       tracking_mappings: Dict[str, str],
                       earnings_mappings: Dict[str, str]) -> Dict[str, Any]:
        """
        Convert an EmployeeTimesheet to Xero API timesheet format
        
        Args:
            employee_timesheet: Internal timesheet data structure
            tracking_mappings: Map of region names to Xero tracking option IDs
            earnings_mappings: Map of hour types to Xero earnings rate IDs
            
        Returns:
            Dictionary in Xero API timesheet format
            
        Raises:
            TimesheetBuilderError: If conversion fails or data is invalid
        """
        try:
            # Validate required data
            self._validate_employee_timesheet(employee_timesheet)
            self._validate_mappings(employee_timesheet, tracking_mappings, earnings_mappings)
            
            # Build the timesheet structure matching Xero API PascalCase format
            timesheet = {}
            # Optional payroll calendar
            if hasattr(employee_timesheet, 'payroll_calendar_id') and employee_timesheet.payroll_calendar_id:
                timesheet["PayrollCalendarID"] = employee_timesheet.payroll_calendar_id

            # Determine date range to use for submission. If the employee's entries span a very
            # long period (demo mixed files), prefer using a single pay-week based on the earliest
            # entry (ignore extended demo end date) and log that decision.
            from datetime import timedelta
            entry_dates = [entry.entry_date for entry in employee_timesheet.daily_entries] if employee_timesheet.daily_entries else []
            start_date = self._get_start_date(employee_timesheet)
            end_date = employee_timesheet.pay_period_end_date
            if entry_dates:
                min_date = min(entry_dates)
                max_date = max(entry_dates)
                if (max_date - min_date).days > 30:
                    # Mixed/demo data detected; ignore extended end date and use a 7-day period
                    computed_end = min_date + timedelta(days=6)
                    self.logger.info(f"Mixed-period data detected for {employee_timesheet.employee_name} ({min_date} to {max_date}); ignoring extended end date {end_date} and using {computed_end} for submission")
                    start_date = min_date
                    end_date = computed_end

            # Required fields (PascalCase)
            timesheet["EmployeeID"] = employee_timesheet.xero_employee_id
            timesheet["StartDate"] = self._format_date(start_date)
            timesheet["EndDate"] = self._format_date(end_date)
            timesheet["Status"] = "Draft"

            # Build lines (PascalCase)
            timesheet["TimesheetLines"] = self._build_timesheet_lines(
                employee_timesheet, tracking_mappings, earnings_mappings
            )
            
            self.logger.debug(f"Built timesheet for employee {employee_timesheet.employee_name}")
            return timesheet
            
        except Exception as e:
            raise TimesheetBuilderError(f"Failed to build timesheet for {employee_timesheet.employee_name}: {e}")
    
    def build_batch_timesheets(self, employee_timesheets: List[EmployeeTimesheet],
                              tracking_mappings: Dict[str, str],
                              earnings_mappings: Dict[str, str]) -> Dict[str, Any]:
        """
        Convert multiple EmployeeTimesheets to Xero API batch format
        
        Args:
            employee_timesheets: List of internal timesheet data structures
            tracking_mappings: Map of region names to Xero tracking option IDs
            earnings_mappings: Map of hour types to Xero earnings rate IDs
            
        Returns:
            Dictionary in Xero API batch timesheet format
            
        Raises:
            TimesheetBuilderError: If conversion fails for any timesheet
        """
        try:
            timesheets = []
            
            for employee_timesheet in employee_timesheets:
                timesheet = self.build_timesheet(
                    employee_timesheet, tracking_mappings, earnings_mappings
                )
                timesheets.append(timesheet)
            
            batch_data = {
                "Timesheets": timesheets
            }
            
            self.logger.info(f"Built batch of {len(timesheets)} timesheets")
            return batch_data
            
        except Exception as e:
            raise TimesheetBuilderError(f"Failed to build batch timesheets: {e}")
    
    def _validate_employee_timesheet(self, employee_timesheet: EmployeeTimesheet) -> None:
        """
        Validate employee timesheet data before conversion
        
        Args:
            employee_timesheet: Timesheet to validate
            
        Raises:
            TimesheetBuilderError: If validation fails
        """
        if not employee_timesheet.xero_employee_id:
            raise TimesheetBuilderError(
                f"Employee {employee_timesheet.employee_name} missing Xero employee ID"
            )
        
        if not employee_timesheet.daily_entries:
            raise TimesheetBuilderError(
                f"Employee {employee_timesheet.employee_name} has no daily entries"
            )
        
        # Do not require per-entry Xero IDs here; mappings are provided separately.
        # Per-entry Xero IDs may be present for persisted data but are not required
        # for building payloads from mappings passed into this builder.
    
    def _validate_mappings(self, employee_timesheet: EmployeeTimesheet,
                          tracking_mappings: Dict[str, str],
                          earnings_mappings: Dict[str, str]) -> None:
        """
        Validate that all required mappings are available
        
        Args:
            employee_timesheet: Timesheet to validate mappings for
            tracking_mappings: Region to tracking ID mappings
            earnings_mappings: Hour type to earnings rate ID mappings
            
        Raises:
            TimesheetBuilderError: If required mappings are missing
        """
        # Check tracking mappings
        regions = employee_timesheet.get_regions()
        missing_regions = [region for region in regions if region not in tracking_mappings]
        if missing_regions:
            raise TimesheetBuilderError(
                f"Missing tracking mappings for regions: {missing_regions}"
            )
        
        # Check earnings mappings
        hour_types = {entry.hour_type.value for entry in employee_timesheet.daily_entries}
        missing_hour_types = [ht for ht in hour_types if ht not in earnings_mappings]
        if missing_hour_types:
            raise TimesheetBuilderError(
                f"Missing earnings rate mappings for hour types: {missing_hour_types}"
            )
    
    def _get_start_date(self, employee_timesheet: EmployeeTimesheet) -> date:
        """
        Calculate the start date for the timesheet based on daily entries
        
        Args:
            employee_timesheet: Timesheet to calculate start date for
            
        Returns:
            Start date of the timesheet period
        """
        if not employee_timesheet.daily_entries:
            # Default to 7 days before end date if no entries
            from datetime import timedelta
            return employee_timesheet.pay_period_end_date - timedelta(days=6)
        
        return min(entry.entry_date for entry in employee_timesheet.daily_entries)
    
    def _format_date(self, date_obj: date) -> str:
        """
        Format date for Xero API (ISO 8601 format)
        
        Args:
            date_obj: Date to format
            
        Returns:
            ISO 8601 formatted date string
        """
        # Xero expects dates in ISO 8601 format (YYYY-MM-DD)
        return date_obj.isoformat()
    
    def _format_datetime(self, datetime_obj: datetime) -> str:
        """
        Format datetime for Xero API with timezone information
        
        Args:
            datetime_obj: Datetime to format
            
        Returns:
            ISO 8601 formatted datetime string with timezone
        """
        # Ensure timezone is set (default to UTC if none)
        if datetime_obj.tzinfo is None:
            datetime_obj = datetime_obj.replace(tzinfo=timezone.utc)
        
        return datetime_obj.isoformat()
    
    def _build_timesheet_lines(self, employee_timesheet: EmployeeTimesheet,
                              tracking_mappings: Dict[str, str],
                              earnings_mappings: Dict[str, str]) -> List[Dict[str, Any]]:
        """
        Build timesheet lines from daily entries
        
        Args:
            employee_timesheet: Source timesheet data
            tracking_mappings: Region to tracking ID mappings
            earnings_mappings: Hour type to earnings rate ID mappings
            
        Returns:
            List of timesheet line dictionaries
        """
        timesheet_lines = []
        
        # Group entries by date and region for consolidation
        grouped_entries = self._group_daily_entries(employee_timesheet.daily_entries)
        
        for (entry_date, region_name, hour_type), entries in grouped_entries.items():
            # Sum hours for the same date/region/hour_type combination
            total_hours = sum(entry.hours for entry in entries)
            
            # Skip zero-hour entries
            if total_hours <= 0:
                continue
            
            # Get the first entry for reference data
            reference_entry = entries[0]
            
            # Build timesheet line in PascalCase to match Xero API
            line = {
                "Date": self._format_date(entry_date),
                "EarningsRateID": earnings_mappings[hour_type.value],
                "NumberOfUnits": round(float(total_hours), 2)  # normalize numeric format
            }

            # Only include TrackingItemID if a valid mapping is provided (None or missing -> omit)
            tracking_id = tracking_mappings.get(region_name) if tracking_mappings else None
            if tracking_id:
                line["TrackingItemID"] = tracking_id
            
            # Add RatePerUnit if applicable for overtime
            if reference_entry.overtime_rate is not None and hour_type == HourType.OVERTIME:
                line["RatePerUnit"] = reference_entry.overtime_rate
            
            timesheet_lines.append(line)
        
        return timesheet_lines
    
    def _group_daily_entries(self, daily_entries: List[DailyEntry]) -> Dict[tuple, List[DailyEntry]]:
        """
        Group daily entries by date, region, and hour type for consolidation
        
        Args:
            daily_entries: List of daily entries to group
            
        Returns:
            Dictionary with (date, region, hour_type) tuples as keys and entry lists as values
        """
        grouped = {}
        
        for entry in daily_entries:
            key = (entry.entry_date, entry.region_name, entry.hour_type)
            if key not in grouped:
                grouped[key] = []
            grouped[key].append(entry)
        
        return grouped
    
    def validate_timesheet_data(self, timesheet_data: Dict[str, Any]) -> List[str]:
        """
        Validate Xero timesheet data structure
        
        Args:
            timesheet_data: Timesheet data to validate
            
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
            if not isinstance(lines, list):
                errors.append("TimesheetLines must be a list")
            else:
                for i, line in enumerate(lines):
                    line_errors = self._validate_timesheet_line(line, i)
                    errors.extend(line_errors)
        
        # Validate date format
        for date_field in ["StartDate", "EndDate"]:
            if date_field in timesheet_data:
                try:
                    datetime.fromisoformat(timesheet_data[date_field])
                except ValueError:
                    errors.append(f"Invalid date format for {date_field}: {timesheet_data[date_field]}")
        
        return errors
    
    def _validate_timesheet_line(self, line: Dict[str, Any], line_index: int) -> List[str]:
        """
        Validate a single timesheet line
        
        Args:
            line: Timesheet line to validate
            line_index: Index of the line for error reporting
            
        Returns:
            List of validation error messages
        """
        errors = []
        line_prefix = f"Line {line_index + 1}: "
        
        # Check required fields
        required_fields = ["Date", "EarningsRateID", "NumberOfUnits"]
        for field in required_fields:
            if field not in line:
                errors.append(f"{line_prefix}Missing required field: {field}")
        
        # Validate NumberOfUnits format
        if "NumberOfUnits" in line:
            units = line["NumberOfUnits"]
            if not isinstance(units, (int, float)) or units < 0:
                errors.append(f"{line_prefix}NumberOfUnits must be a non-negative number")
        
        # Validate date format
        if "Date" in line:
            try:
                datetime.fromisoformat(line["Date"])
            except ValueError:
                errors.append(f"{line_prefix}Invalid date format: {line['Date']}")
        
        # Validate tracking item ID if present
        if "TrackingItemID" in line:
            tracking_item = line["TrackingItemID"]
            if not isinstance(tracking_item, str):
                errors.append(f"{line_prefix}TrackingItemID must be a string (tracking option ID)")
        
        return errors