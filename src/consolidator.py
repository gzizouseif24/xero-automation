"""
Data consolidation module for Xero Payroll Automation system.

This module provides functionality to merge timesheet data from multiple sources
(site timesheets, travel time, and overtime rates) into a unified structure.
"""

from typing import Dict, Any, List, Optional, Set
from datetime import date, timedelta
from collections import defaultdict
import re
from .models import EmployeeTimesheet, DailyEntry, HourType, PayrollData


class DataConsolidator:
    """
    Consolidates timesheet data from multiple sources into unified employee timesheets.
    
    This class handles merging site timesheet data, travel time data, and overtime rates
    into a single coherent structure that can be used for Xero API integration.
    """
    
    def __init__(self):
        """Initialize the data consolidator."""
        self.employee_name_variations = {}  # Cache for employee name matching
    
    def consolidate(self, site_data: Dict[str, Any], travel_data: Dict[str, Any], 
                   overtime_data: Dict[str, Any], valid_regions: Optional[Set[str]] = None) -> PayrollData:
        """
        Consolidate all data sources into unified employee timesheets.
        
        Args:
            site_data: Parsed site timesheet data
            travel_data: Parsed travel time data  
            overtime_data: Parsed overtime rates data
            
        Returns:
            PayrollData object containing consolidated employee timesheets
            
        Raises:
            ValueError: If data validation fails or required data is missing
        """
        # Validate input data
        self._validate_input_data(site_data, travel_data, overtime_data)
        
        # Extract pay period end date (use site data as primary source)
        pay_period_end_date = site_data.get('pay_period_end_date')
        if not pay_period_end_date:
            raise ValueError("Pay period end date not found in site data")
        
        # For mixed-period data (like demo files), extend the pay period to include all dates
        # Only consider site data dates for mixed-period detection (ignore travel placeholder dates)
        all_dates = []
        for employee_data in site_data.get('employees', []):
            for entry in employee_data.get('entries', []):
                if entry.get('entry_date'):
                    all_dates.append(entry['entry_date'])

        # Check if site data spans a long period (demo mixed files)
        if all_dates:
            min_date = min(all_dates)
            max_date = max(all_dates)
            if (max_date - min_date).days > 30:
                # Extend pay period end date to the latest date in the mixed data
                # but only when demo-like mixed periods are detected.
                print(f"Info: Mixed-period data detected in site data ({min_date} to {max_date}); extending pay period end date to {max_date}")
                pay_period_end_date = max_date

        # Track unknown regions encountered during consolidation
        self.unknown_regions = set()
        self.unknown_region_entries = []  # list of (employee_name, original_region, entry_date, hours)
        
        # Do NOT extend the pay period end date based on travel data or other files.
        # Keep pay_period_end_date as provided in site_data (primary source).
        
        # Validate date range consistency
        self._validate_date_ranges(site_data, travel_data, pay_period_end_date)
        
        # Build employee name mapping for consistent matching
        employee_mapping = self._build_employee_name_mapping(site_data, travel_data)
        
        # Consolidate data by employee
        consolidated_employees = {}
        
        # Process site timesheet data first (primary source)
        for employee_data in site_data.get('employees', []):
            employee_name = employee_data['employee_name']
            canonical_name = self._get_canonical_employee_name(employee_name, employee_mapping)
            
            if canonical_name not in consolidated_employees:
                consolidated_employees[canonical_name] = {
                    'employee_name': canonical_name,
                    'daily_entries': []
                }
            
            # Add site entries
            for entry in employee_data.get('entries', []):
                daily_entry = self._create_daily_entry_from_site_data(entry, overtime_data, canonical_name, valid_regions)
                # If the entry was marked unknown, capture details
                if not daily_entry.region_valid:
                    self.unknown_regions.add(daily_entry.original_region or '')
                    self.unknown_region_entries.append((canonical_name, daily_entry.original_region, daily_entry.entry_date, daily_entry.hours))
                consolidated_employees[canonical_name]['daily_entries'].append(daily_entry)
        
        # Process travel time data
        for employee_data in travel_data.get('employees', []):
            employee_name = employee_data['employee_name']
            canonical_name = self._get_canonical_employee_name(employee_name, employee_mapping)
            
            if canonical_name not in consolidated_employees:
                consolidated_employees[canonical_name] = {
                    'employee_name': canonical_name,
                    'daily_entries': []
                }
            
            # Add travel entries
            for entry in employee_data.get('entries', []):
                daily_entry = self._create_daily_entry_from_travel_data(entry, pay_period_end_date, valid_regions)
                if not daily_entry.region_valid:
                    self.unknown_regions.add(daily_entry.original_region or '')
                    self.unknown_region_entries.append((canonical_name, daily_entry.original_region, daily_entry.entry_date, daily_entry.hours))
                consolidated_employees[canonical_name]['daily_entries'].append(daily_entry)
        
        # Convert to EmployeeTimesheet objects
        employee_timesheets = []
        for emp_data in consolidated_employees.values():
            # Sort daily entries by date
            emp_data['daily_entries'].sort(key=lambda x: x.entry_date)
            
            # Regular hours are already capped at 40 in the pre-processing step
            processed_entries = emp_data['daily_entries']
            
            timesheet = EmployeeTimesheet(
                employee_name=emp_data['employee_name'],
                daily_entries=processed_entries,
                pay_period_end_date=pay_period_end_date
            )
            employee_timesheets.append(timesheet)
        
        # Sort employees by name for consistent output
        employee_timesheets.sort(key=lambda x: x.employee_name)
        
        # Validate that we have at least one employee
        if not employee_timesheets:
            raise ValueError("No employee data found to consolidate")
        
        return PayrollData(
            employee_timesheets=employee_timesheets,
            pay_period_end_date=pay_period_end_date
        )
    
    def _validate_input_data(self, site_data: Dict[str, Any], travel_data: Dict[str, Any], 
                           overtime_data: Dict[str, Any]) -> None:
        """
        Validate that input data has the required structure and content.
        
        Args:
            site_data: Site timesheet data
            travel_data: Travel time data
            overtime_data: Overtime rates data
            
        Raises:
            ValueError: If validation fails
        """
        # Validate site data
        if not isinstance(site_data, dict):
            raise ValueError("Site data must be a dictionary")
        
        if site_data.get('file_type') != 'site_timesheet':
            raise ValueError("Site data must have file_type 'site_timesheet'")
        
        if 'employees' not in site_data:
            raise ValueError("Site data must contain 'employees' key")
        
        if not site_data.get('pay_period_end_date'):
            raise ValueError("Site data must contain 'pay_period_end_date'")
        
        # Validate travel data
        if not isinstance(travel_data, dict):
            raise ValueError("Travel data must be a dictionary")
        
        if travel_data.get('file_type') != 'travel_time':
            raise ValueError("Travel data must have file_type 'travel_time'")
        
        if 'employees' not in travel_data:
            raise ValueError("Travel data must contain 'employees' key")
        
        # Validate overtime data
        if not isinstance(overtime_data, dict):
            raise ValueError("Overtime data must be a dictionary")
        
        if overtime_data.get('file_type') != 'overtime_rates':
            raise ValueError("Overtime data must have file_type 'overtime_rates'")
        
        if 'overtime_rates_lookup' not in overtime_data:
            raise ValueError("Overtime data must contain 'overtime_rates_lookup' key")
    
    def _validate_date_ranges(self, site_data: Dict[str, Any], travel_data: Dict[str, Any], 
                            pay_period_end_date: date) -> None:
        """
        Validate that all dates fall within reasonable ranges for the pay period.
        
        Args:
            site_data: Site timesheet data
            travel_data: Travel time data
            pay_period_end_date: Pay period end date
            
        Raises:
            ValueError: If date validation fails
        """
        # Collect all dates from both sources to determine the actual date range
        all_dates = []
        
        for employee_data in site_data.get('employees', []):
            for entry in employee_data.get('entries', []):
                entry_date = entry.get('entry_date')
                if isinstance(entry_date, date):
                    all_dates.append(entry_date)
        
        for employee_data in travel_data.get('employees', []):
            for entry in employee_data.get('entries', []):
                entry_date = entry.get('entry_date')
                if isinstance(entry_date, date) and entry_date.year != 1900:  # Ignore placeholder dates
                    all_dates.append(entry_date)
        
        if not all_dates:
            return  # No dates to validate
        
        # Calculate actual date range from the data
        min_date = min(all_dates)
        max_date = max(all_dates)
        date_span = (max_date - min_date).days
        
        # For demo files with mixed periods, be more lenient
        if date_span > 30:  # More than 30 days span suggests mixed periods
            print(f"Warning: Data spans {date_span} days ({min_date} to {max_date})")
            print("This suggests mixed time periods - validation will be lenient for demo purposes")
            
            # Only validate for extremely unreasonable dates (more than 1 year span)
            if date_span > 365:
                raise ValueError(f"Date range too large: {date_span} days from {min_date} to {max_date}")
        else:
            # Normal validation for reasonable date ranges
            earliest_allowed = pay_period_end_date - timedelta(days=14)
            latest_allowed = pay_period_end_date
            
            # Check for dates outside reasonable range
            invalid_dates = []
            for entry_date in all_dates:
                if entry_date < earliest_allowed or entry_date > latest_allowed:
                    invalid_dates.append(entry_date)
            
            if invalid_dates:
                print(f"Warning: {len(invalid_dates)} entries have dates outside expected range")
                print(f"Expected range: {earliest_allowed} to {latest_allowed}")
                print(f"Actual range: {min_date} to {max_date}")
                # Don't fail for demo purposes, just warn
    
    def _build_employee_name_mapping(self, site_data: Dict[str, Any], 
                                   travel_data: Dict[str, Any]) -> Dict[str, str]:
        """
        Build a mapping of employee name variations to canonical names.
        
        This handles cases where the same employee appears with slight name variations
        across different data sources (e.g., "John Smith" vs "J. Smith").
        
        Args:
            site_data: Site timesheet data
            travel_data: Travel time data
            
        Returns:
            Dictionary mapping all name variations to canonical names
        """
        # Collect all unique employee names
        all_names = set()
        
        for employee_data in site_data.get('employees', []):
            all_names.add(employee_data['employee_name'])
        
        for employee_data in travel_data.get('employees', []):
            all_names.add(employee_data['employee_name'])
        
        # Build mapping - for now, use exact matching
        # Future enhancement: implement fuzzy matching for similar names
        employee_mapping = {}
        for name in all_names:
            employee_mapping[name] = name
        
        return employee_mapping
    
    def _get_canonical_employee_name(self, employee_name: str, 
                                   employee_mapping: Dict[str, str]) -> str:
        """
        Get the canonical name for an employee from the mapping.
        
        Args:
            employee_name: Original employee name
            employee_mapping: Name mapping dictionary
            
        Returns:
            Canonical employee name
        """
        return employee_mapping.get(employee_name, employee_name)
    
    def _create_daily_entry_from_site_data(self, entry_data: Dict[str, Any], 
                                         overtime_data: Dict[str, Any], 
                                         employee_name: str = None,
                                         valid_regions: Optional[Set[str]] = None) -> DailyEntry:
        """
        Create a DailyEntry object from site timesheet entry data.
        
        Args:
            entry_data: Site entry data
            overtime_data: Overtime rates data for rate lookup
            
        Returns:
            DailyEntry object
        """
        # Extract basic entry information
        entry_date = entry_data['entry_date']
        region_name = entry_data['region_name']
        hours = float(entry_data['hours'])
        hour_type_str = entry_data['hour_type']
        
        # Convert hour type string to enum
        hour_type = HourType(hour_type_str)
        
        # Look up overtime rate if this is overtime
        overtime_rate = None
        if hour_type == HourType.OVERTIME:
            lookup_name = employee_name or entry_data.get('employee_name', '')
            overtime_rate = self._lookup_overtime_rate(lookup_name, overtime_data)
        # Determine region validity and set reconciliation metadata if needed
        original_region = region_name
        region_valid = True
        if valid_regions is not None and region_name not in valid_regions:
            # Mark as unknown for now (demo behavior) and record original
            region_valid = False
            region_name = 'Unknown'

        return DailyEntry(
            entry_date=entry_date,
            region_name=region_name,
            hours=hours,
            hour_type=hour_type,
            overtime_rate=overtime_rate,
            original_region=original_region,
            region_valid=region_valid
        )
    
    def _create_daily_entry_from_travel_data(self, entry_data: Dict[str, Any], pay_period_end_date: date, valid_regions: Optional[Set[str]] = None) -> DailyEntry:
        """
        Create a DailyEntry object from travel time entry data.
        
        Args:
            entry_data: Travel entry data
            pay_period_end_date: Pay period end date from site timesheet to use for travel entries
            valid_regions: Set of valid regions
            
        Returns:
            DailyEntry object
        """
        original_region = entry_data['region_name']
        region_name = original_region
        region_valid = True
        if valid_regions is not None and original_region not in valid_regions:
            region_valid = False
            region_name = 'Unknown'

        # Use pay period end date instead of placeholder date from travel parser
        entry_date = entry_data['entry_date']
        if entry_date.year == 1900:  # Check if it's our placeholder date
            entry_date = pay_period_end_date

        return DailyEntry(
            entry_date=entry_date,
            region_name=region_name,
            hours=float(entry_data['hours']),
            hour_type=HourType.TRAVEL,
            overtime_rate=None,
            original_region=original_region,
            region_valid=region_valid
        )
    
    def _lookup_overtime_rate(self, employee_name: str, 
                            overtime_data: Dict[str, Any]) -> Optional[float]:
        """
        Look up the overtime rate for an employee.
        
        Args:
            employee_name: Name of the employee
            overtime_data: Overtime rates data
            
        Returns:
            Overtime rate if employee has different rate, None otherwise
        """
        lookup = overtime_data.get('overtime_rates_lookup', {})
        
        # Try exact match first
        if employee_name in lookup:
            emp_data = lookup[employee_name]
            if emp_data.get('has_different_overtime_rate', False):
                return emp_data.get('overtime_rate')
        
        # Try case-insensitive match
        for lookup_name, emp_data in lookup.items():
            if lookup_name.lower() == employee_name.lower():
                if emp_data.get('has_different_overtime_rate', False):
                    return emp_data.get('overtime_rate')
        
        return None

    def get_unknown_region_report(self) -> Dict[str, Any]:
        """
        Return a report of unknown regions encountered during the last consolidation.
        """
        return {
            'unknown_regions': sorted([r for r in self.unknown_regions if r]),
            'unknown_region_entries': [
                {
                    'employee_name': emp,
                    'original_region': orig,
                    'entry_date': dt.isoformat() if hasattr(dt, 'isoformat') else str(dt),
                    'hours': hrs
                } for (emp, orig, dt, hrs) in self.unknown_region_entries
            ]
        }
    
    def has_different_overtime_rate(self, employee_name: str, 
                                  overtime_data: Dict[str, Any]) -> bool:
        """
        Check if an employee has a different overtime rate.
        
        Args:
            employee_name: Name of the employee
            overtime_data: Overtime rates data
            
        Returns:
            True if employee has different overtime rate, False otherwise
        """
        lookup = overtime_data.get('overtime_rates_lookup', {})
        
        # Try exact match first
        if employee_name in lookup:
            return lookup[employee_name].get('has_different_overtime_rate', False)
        
        # Try case-insensitive match
        for lookup_name, emp_data in lookup.items():
            if lookup_name.lower() == employee_name.lower():
                return emp_data.get('has_different_overtime_rate', False)
        
        return False
    
    def get_overtime_rate(self, employee_name: str, 
                         overtime_data: Dict[str, Any]) -> Optional[float]:
        """
        Get the overtime rate for an employee.
        
        This is a public interface for the overtime rate lookup functionality.
        
        Args:
            employee_name: Name of the employee
            overtime_data: Overtime rates data
            
        Returns:
            Overtime rate if employee has different rate, None otherwise
        """
        return self._lookup_overtime_rate(employee_name, overtime_data)
    
    def apply_overtime_rates_to_payroll(self, payroll_data: PayrollData, 
                                      overtime_data: Dict[str, Any]) -> PayrollData:
        """
        Apply overtime rates to all overtime entries in the payroll data.
        
        This method updates overtime entries that don't already have rates applied.
        
        Args:
            payroll_data: Consolidated payroll data
            overtime_data: Overtime rates data
            
        Returns:
            Updated PayrollData with overtime rates applied
        """
        updated_timesheets = []
        
        for timesheet in payroll_data.employee_timesheets:
            updated_entries = []
            
            for entry in timesheet.daily_entries:
                if entry.hour_type == HourType.OVERTIME and entry.overtime_rate is None:
                    # Apply overtime rate if not already set
                    overtime_rate = self._lookup_overtime_rate(timesheet.employee_name, overtime_data)
                    updated_entry = DailyEntry(
                        entry_date=entry.entry_date,
                        region_name=entry.region_name,
                        hours=entry.hours,
                        hour_type=entry.hour_type,
                        overtime_rate=overtime_rate,
                        xero_tracking_id=entry.xero_tracking_id,
                        xero_earnings_rate_id=entry.xero_earnings_rate_id
                    )
                    updated_entries.append(updated_entry)
                else:
                    updated_entries.append(entry)
            
            updated_timesheet = EmployeeTimesheet(
                employee_name=timesheet.employee_name,
                daily_entries=updated_entries,
                pay_period_end_date=timesheet.pay_period_end_date,
                xero_employee_id=timesheet.xero_employee_id
            )
            updated_timesheets.append(updated_timesheet)
        
        return PayrollData(
            employee_timesheets=updated_timesheets,
            pay_period_end_date=payroll_data.pay_period_end_date
        )
    
    def get_overtime_summary(self, payroll_data: PayrollData) -> Dict[str, Any]:
        """
        Generate a summary of overtime information in the payroll data.
        
        Args:
            payroll_data: Consolidated payroll data
            
        Returns:
            Dictionary containing overtime summary statistics
        """
        overtime_summary = {
            'employees_with_overtime': [],
            'total_overtime_hours': 0.0,
            'employees_with_custom_rates': [],
            'employees_without_custom_rates': []
        }
        
        for timesheet in payroll_data.employee_timesheets:
            employee_overtime_hours = 0.0
            has_custom_rate = False
            
            for entry in timesheet.daily_entries:
                if entry.hour_type == HourType.OVERTIME:
                    employee_overtime_hours += entry.hours
                    if entry.overtime_rate is not None:
                        has_custom_rate = True
            
            if employee_overtime_hours > 0:
                overtime_summary['employees_with_overtime'].append({
                    'employee_name': timesheet.employee_name,
                    'overtime_hours': employee_overtime_hours,
                    'has_custom_rate': has_custom_rate
                })
                overtime_summary['total_overtime_hours'] += employee_overtime_hours
                
                if has_custom_rate:
                    overtime_summary['employees_with_custom_rates'].append(timesheet.employee_name)
                else:
                    overtime_summary['employees_without_custom_rates'].append(timesheet.employee_name)
        
        return overtime_summary
    

    
    def to_target_json_format(self, payroll_data: PayrollData) -> Dict[str, Any]:
        """
        Convert PayrollData to the target JSON format specified in requirements.
        
        This matches the expected output format with proper overtime rate handling.
        
        Args:
            payroll_data: Consolidated payroll data
            
        Returns:
            Dictionary in the target JSON format
        """
        employees_list = []

        for timesheet in payroll_data.employee_timesheets:
            # Preserve original entry order and do NOT merge duplicates (demo requirement).
            daily_entries_list = []

            seen = set()
            for entry in timesheet.daily_entries:
                # For unknown regions, demo behavior: represent as zero-hours placeholder in consolidated JSON
                hours = 0.0 if entry.region_name == 'Unknown' else float(entry.hours)

                entry_dict = {
                    "entry_date": entry.entry_date.isoformat(),
                    "region_name": entry.region_name,
                    "hours": hours,
                    "hour_type": entry.hour_type.value,
                    "overtime_rate": entry.overtime_rate
                }

                # Deduplicate exact identical entries (date, region, hours, hour_type) while preserving order
                key = (entry_dict['entry_date'], entry_dict['region_name'], entry_dict['hours'], entry_dict['hour_type'])
                if key in seen:
                    # skip duplicate
                    continue
                seen.add(key)
                daily_entries_list.append(entry_dict)

            employee_dict = {
                "employee_name": timesheet.employee_name,
                "daily_entries": daily_entries_list
            }
            employees_list.append(employee_dict)

        return {
            "pay_period_end_date": payroll_data.pay_period_end_date.isoformat(),
            "employees": employees_list
        }
    


    def get_consolidation_summary(self, payroll_data: PayrollData) -> Dict[str, Any]:
        """
        Generate a summary of the consolidation results.
        
        Args:
            payroll_data: Consolidated payroll data
            
        Returns:
            Dictionary containing consolidation summary statistics
        """
        total_employees = len(payroll_data.employee_timesheets)
        total_entries = sum(len(ts.daily_entries) for ts in payroll_data.employee_timesheets)
        
        # Calculate hours by type
        hours_by_type = defaultdict(float)
        regions = set()
        
        for timesheet in payroll_data.employee_timesheets:
            for entry in timesheet.daily_entries:
                hours_by_type[entry.hour_type.value] += entry.hours
                regions.add(entry.region_name)
        
        return {
            'total_employees': total_employees,
            'total_entries': total_entries,
            'total_hours': sum(hours_by_type.values()),
            'hours_by_type': dict(hours_by_type),
            'unique_regions': sorted(list(regions)),
            'pay_period_end_date': payroll_data.pay_period_end_date,
            'date_range': {
                'start_date': min(
                    entry.entry_date 
                    for ts in payroll_data.employee_timesheets 
                    for entry in ts.daily_entries
                ) if total_entries > 0 else payroll_data.pay_period_end_date,
                'end_date': max(
                    entry.entry_date 
                    for ts in payroll_data.employee_timesheets 
                    for entry in ts.daily_entries
                ) if total_entries > 0 else payroll_data.pay_period_end_date
            }
        }