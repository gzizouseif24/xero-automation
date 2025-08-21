"""
Data models for Xero Payroll Automation system.

This module contains the core data structures used throughout the application
for representing timesheet data, employee information, and validation results.
"""

from dataclasses import dataclass, field
from datetime import date
from typing import List, Optional, Dict, Any
import json
from enum import Enum
import logging


class HourType(Enum):
    """Enumeration of supported hour types for timesheet entries."""
    REGULAR = "REGULAR"
    OVERTIME = "OVERTIME" 
    TRAVEL = "TRAVEL"
    HOLIDAY = "HOLIDAY"


@dataclass
class DailyEntry:
    """
    Represents a single day's timesheet entry for an employee.
    
    This class encapsulates all information needed for a single timesheet entry,
    including date, region allocation, hours worked, and hour type classification.
    """
    entry_date: date
    region_name: str
    hours: float
    hour_type: HourType
    overtime_rate: Optional[float] = None
    xero_tracking_id: Optional[str] = None
    xero_earnings_rate_id: Optional[str] = None
    # Metadata for reconciliation when region is unknown or unmapped
    original_region: Optional[str] = None
    region_valid: bool = True
    
    def __post_init__(self):
        """Validate data after initialization."""
        self._validate()
    
    def _validate(self):
        """Validate the daily entry data."""
        if self.hours < 0:
            raise ValueError(f"Hours cannot be negative: {self.hours}")
        
        if self.hours > 24:
            raise ValueError(f"Hours cannot exceed 24 in a day: {self.hours}")
        
        if not self.region_name or not self.region_name.strip():
            raise ValueError("Region name cannot be empty")
        
        if self.overtime_rate is not None and self.overtime_rate < 0:
            raise ValueError(f"Overtime rate cannot be negative: {self.overtime_rate}")
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the daily entry to a dictionary for serialization."""
        return {
            "entry_date": self.entry_date.isoformat(),
            "region_name": self.region_name,
            "hours": self.hours,
            "hour_type": self.hour_type.value,
            "overtime_rate": self.overtime_rate,
            "xero_tracking_id": self.xero_tracking_id,
            "xero_earnings_rate_id": self.xero_earnings_rate_id,
            # Include reconciliation metadata for internal use if present
            "original_region": self.original_region,
            "region_valid": self.region_valid
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'DailyEntry':
        """Create a DailyEntry from a dictionary."""
        return cls(
            entry_date=date.fromisoformat(data["entry_date"]),
            region_name=data["region_name"],
            hours=data["hours"],
            hour_type=HourType(data["hour_type"]),
            overtime_rate=data.get("overtime_rate"),
            xero_tracking_id=data.get("xero_tracking_id"),
            xero_earnings_rate_id=data.get("xero_earnings_rate_id")
            ,
            original_region=data.get("original_region"),
            region_valid=data.get("region_valid", True)
        )


@dataclass
class EmployeeTimesheet:
    """
    Represents a complete timesheet for a single employee over a pay period.
    
    This class aggregates all daily entries for an employee and includes
    metadata about the pay period and Xero integration.
    """
    employee_name: str
    daily_entries: List[DailyEntry]
    pay_period_end_date: date
    xero_employee_id: Optional[str] = None
    payroll_calendar_id: Optional[str] = None
    
    def __post_init__(self):
        """Validate data after initialization."""
        self._validate()
    
    def _validate(self):
        """Validate the employee timesheet data."""
        if not self.employee_name or not self.employee_name.strip():
            raise ValueError("Employee name cannot be empty")
        
        if not self.daily_entries:
            raise ValueError("Employee timesheet must have at least one daily entry")
        
        # Validate that all daily entries are within the pay period
        for entry in self.daily_entries:
            if entry.entry_date > self.pay_period_end_date:
                # Strict validation: entries after the pay period end are invalid
                raise ValueError(
                    f"Daily entry date {entry.entry_date} is after pay period end date {self.pay_period_end_date}"
                )
    
    def get_total_hours(self, hour_type: Optional[HourType] = None) -> float:
        """
        Calculate total hours for the timesheet.
        
        Args:
            hour_type: If specified, only count hours of this type
            
        Returns:
            Total hours worked
        """
        if hour_type is None:
            return sum(entry.hours for entry in self.daily_entries)
        else:
            return sum(entry.hours for entry in self.daily_entries if entry.hour_type == hour_type)
    
    def get_regions(self) -> set[str]:
        """Get all unique regions worked in during this pay period."""
        return {entry.region_name for entry in self.daily_entries}
    
    def get_entries_by_region(self, region_name: str) -> List[DailyEntry]:
        """Get all daily entries for a specific region."""
        return [entry for entry in self.daily_entries if entry.region_name == region_name]
    
    def get_entries_by_date(self, entry_date: date) -> List[DailyEntry]:
        """Get all daily entries for a specific date."""
        return [entry for entry in self.daily_entries if entry.entry_date == entry_date]
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the employee timesheet to a dictionary for serialization."""
        return {
            "employee_name": self.employee_name,
            "daily_entries": [entry.to_dict() for entry in self.daily_entries],
            "pay_period_end_date": self.pay_period_end_date.isoformat(),
            "xero_employee_id": self.xero_employee_id,
            "payroll_calendar_id": self.payroll_calendar_id
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'EmployeeTimesheet':
        """Create an EmployeeTimesheet from a dictionary."""
        return cls(
            employee_name=data["employee_name"],
            daily_entries=[DailyEntry.from_dict(entry) for entry in data["daily_entries"]],
            pay_period_end_date=date.fromisoformat(data["pay_period_end_date"]),
            xero_employee_id=data.get("xero_employee_id"),
            payroll_calendar_id=data.get("payroll_calendar_id")
        )
    
    def to_json(self) -> str:
        """Convert the employee timesheet to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'EmployeeTimesheet':
        """Create an EmployeeTimesheet from a JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)


@dataclass
class PayrollData:
    """
    Represents the complete payroll data for a pay period.
    
    This class aggregates all employee timesheets and provides methods
    for batch operations and serialization.
    """
    employee_timesheets: List[EmployeeTimesheet]
    pay_period_end_date: date
    
    def __post_init__(self):
        """Validate data after initialization."""
        self._validate()
    
    def _validate(self):
        """Validate the payroll data."""
        if not self.employee_timesheets:
            raise ValueError("Payroll data must contain at least one employee timesheet")
        
        # Validate that all timesheets have the same pay period end date
        for timesheet in self.employee_timesheets:
            if timesheet.pay_period_end_date != self.pay_period_end_date:
                raise ValueError(
                    f"Employee {timesheet.employee_name} has mismatched pay period end date: "
                    f"{timesheet.pay_period_end_date} vs {self.pay_period_end_date}"
                )
    
    def get_employee_timesheet(self, employee_name: str) -> Optional[EmployeeTimesheet]:
        """Get timesheet for a specific employee."""
        for timesheet in self.employee_timesheets:
            if timesheet.employee_name == employee_name:
                return timesheet
        return None
    
    def get_all_regions(self) -> set[str]:
        """Get all unique regions across all employee timesheets."""
        regions = set()
        for timesheet in self.employee_timesheets:
            regions.update(timesheet.get_regions())
        return regions
    
    def get_total_hours(self, hour_type: Optional[HourType] = None) -> float:
        """Calculate total hours across all employees."""
        return sum(timesheet.get_total_hours(hour_type) for timesheet in self.employee_timesheets)
    
    def to_dict(self) -> Dict[str, Any]:
        """Convert the payroll data to a dictionary for serialization."""
        return {
            "employee_timesheets": [timesheet.to_dict() for timesheet in self.employee_timesheets],
            "pay_period_end_date": self.pay_period_end_date.isoformat()
        }
    
    @classmethod
    def from_dict(cls, data: Dict[str, Any]) -> 'PayrollData':
        """Create PayrollData from a dictionary."""
        return cls(
            employee_timesheets=[
                EmployeeTimesheet.from_dict(timesheet) 
                for timesheet in data["employee_timesheets"]
            ],
            pay_period_end_date=date.fromisoformat(data["pay_period_end_date"])
        )
    
    def to_json(self) -> str:
        """Convert the payroll data to JSON string."""
        return json.dumps(self.to_dict(), indent=2)
    
    @classmethod
    def from_json(cls, json_str: str) -> 'PayrollData':
        """Create PayrollData from a JSON string."""
        data = json.loads(json_str)
        return cls.from_dict(data)