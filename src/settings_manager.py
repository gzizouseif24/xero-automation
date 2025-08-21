"""
Settings Manager for Xero Payroll Automation.

This module provides functionality to read, write, and validate
configuration settings from config/settings.py through a web interface.
"""

import os
import ast
import re
from pathlib import Path
from typing import Dict, Any, List, Union
import logging

logger = logging.getLogger(__name__)


class SettingsManager:
    """
    Manages application settings with read/write capabilities to config/settings.py
    """
    
    def __init__(self, settings_file_path: str = None):
        """Initialize the settings manager."""
        if settings_file_path is None:
            # Default to config/settings.py relative to project root
            project_root = Path(__file__).parent.parent
            settings_file_path = project_root / "config" / "settings.py"
        
        self.settings_file_path = Path(settings_file_path)
        self.settings_cache = {}
        self._load_settings()
    
    def _load_settings(self) -> None:
        """Load settings from the settings.py file."""
        try:
            if not self.settings_file_path.exists():
                raise FileNotFoundError(f"Settings file not found: {self.settings_file_path}")
            
            # Read the file content
            with open(self.settings_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse the Python file to extract variable assignments
            tree = ast.parse(content)
            
            settings = {}
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            var_name = target.id
                            # Skip private variables and imports
                            if not var_name.startswith('_') and var_name.isupper():
                                try:
                                    # Evaluate the value safely
                                    value = ast.literal_eval(node.value)
                                    settings[var_name] = value
                                except (ValueError, TypeError):
                                    # Handle complex expressions by extracting from source
                                    logger.warning(f"Could not parse value for {var_name}, skipping")
            
            self.settings_cache = settings
            logger.info(f"Loaded {len(settings)} settings from {self.settings_file_path}")
            
        except Exception as e:
            logger.error(f"Failed to load settings: {e}")
            self.settings_cache = {}
    
    def get_all_settings(self) -> Dict[str, Any]:
        """Get all current settings organized by category."""
        return {
            "xero_api": {
                "XERO_API_BASE_URL": self.settings_cache.get("XERO_API_BASE_URL", ""),
                "XERO_PAYROLL_API_BASE_URL": self.settings_cache.get("XERO_PAYROLL_API_BASE_URL", ""),
                "OAUTH_SCOPES": self.settings_cache.get("OAUTH_SCOPES", [])
            },
            "file_processing": {
                "SUPPORTED_FILE_EXTENSIONS": self.settings_cache.get("SUPPORTED_FILE_EXTENSIONS", []),
                "EXPECTED_FILES": self.settings_cache.get("EXPECTED_FILES", [])
            },
            "employee_matching": {
                "FUZZY_MATCH_THRESHOLD": self.settings_cache.get("FUZZY_MATCH_THRESHOLD", 85.0),
                "FUZZY_MATCH_CUTOFF": self.settings_cache.get("FUZZY_MATCH_CUTOFF", 60.0)
            },
            "hour_types": {
                "HOUR_TYPE_TO_XERO_MAPPING": self.settings_cache.get("HOUR_TYPE_TO_XERO_MAPPING", {}),
                "HOUR_TYPE_KEYS": self.settings_cache.get("HOUR_TYPE_KEYS", []),
                "HOLIDAY_HOURS_PER_DAY": self.settings_cache.get("HOLIDAY_HOURS_PER_DAY", 8.0)
            },
            "parser_config": {
                "SITE_TIMESHEET_CONFIG": self.settings_cache.get("SITE_TIMESHEET_CONFIG", {}),
                "TRAVEL_TIME_CONFIG": self.settings_cache.get("TRAVEL_TIME_CONFIG", {}),
                "OVERTIME_RATES_CONFIG": self.settings_cache.get("OVERTIME_RATES_CONFIG", {})
            },
            "api_settings": {
                "API_RATE_LIMIT_DELAY": self.settings_cache.get("API_RATE_LIMIT_DELAY", 1.0),
                "MAX_RETRIES": self.settings_cache.get("MAX_RETRIES", 3)
            }
        }
    
    def get_setting(self, key: str) -> Any:
        """Get a specific setting value."""
        return self.settings_cache.get(key)
    
    def update_settings(self, updates: Dict[str, Any]) -> bool:
        """
        Update multiple settings and write to file.
        
        Args:
            updates: Dictionary of setting_key -> new_value
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Validate updates first
            validation_errors = self._validate_settings(updates)
            if validation_errors:
                logger.error(f"Settings validation failed: {validation_errors}")
                return False
            
            # Update cache
            for key, value in updates.items():
                self.settings_cache[key] = value
            
            # Write to file
            return self._write_settings_file()
            
        except Exception as e:
            logger.error(f"Failed to update settings: {e}")
            return False
    
    def _validate_settings(self, updates: Dict[str, Any]) -> List[str]:
        """
        Validate setting values before applying them.
        
        Returns:
            List of validation error messages (empty if valid)
        """
        errors = []
        
        for key, value in updates.items():
            # Type validation based on expected types
            if key in ["FUZZY_MATCH_THRESHOLD", "FUZZY_MATCH_CUTOFF", "HOLIDAY_HOURS_PER_DAY", "API_RATE_LIMIT_DELAY"]:
                if not isinstance(value, (int, float)) or value < 0:
                    errors.append(f"{key} must be a positive number")
            
            elif key == "MAX_RETRIES":
                if not isinstance(value, int) or value < 1:
                    errors.append(f"{key} must be a positive integer")
            
            elif key in ["OAUTH_SCOPES", "SUPPORTED_FILE_EXTENSIONS", "EXPECTED_FILES", "HOUR_TYPE_KEYS"]:
                if not isinstance(value, list):
                    errors.append(f"{key} must be a list")
            
            elif key in ["XERO_API_BASE_URL", "XERO_PAYROLL_API_BASE_URL"]:
                if not isinstance(value, str) or not value.startswith("https://"):
                    errors.append(f"{key} must be a valid HTTPS URL")
            
            elif key in ["HOUR_TYPE_TO_XERO_MAPPING", "SITE_TIMESHEET_CONFIG", "TRAVEL_TIME_CONFIG", "OVERTIME_RATES_CONFIG"]:
                if not isinstance(value, dict):
                    errors.append(f"{key} must be a dictionary")
            
            # Range validation
            if key == "FUZZY_MATCH_THRESHOLD" and isinstance(value, (int, float)):
                if not (0 <= value <= 100):
                    errors.append(f"{key} must be between 0 and 100")
            
            if key == "FUZZY_MATCH_CUTOFF" and isinstance(value, (int, float)):
                if not (0 <= value <= 100):
                    errors.append(f"{key} must be between 0 and 100")
        
        return errors
    
    def _write_settings_file(self) -> bool:
        """Write current settings back to the settings.py file."""
        try:
            # Read the original file
            with open(self.settings_file_path, 'r', encoding='utf-8') as f:
                content = f.read()
            
            # Parse the AST to find variable assignments and their positions
            tree = ast.parse(content)
            
            # Create a mapping of variable names to their line ranges
            variable_ranges = {}
            lines = content.split('\n')
            
            for node in ast.walk(tree):
                if isinstance(node, ast.Assign):
                    for target in node.targets:
                        if isinstance(target, ast.Name):
                            var_name = target.id
                            if var_name in self.settings_cache:
                                # Find the actual end of this assignment by looking for brackets/braces
                                start_line = node.lineno - 1  # Convert to 0-based
                                end_line = start_line
                                
                                # For multi-line assignments, find the closing bracket/brace
                                if isinstance(node.value, (ast.Dict, ast.List)):
                                    bracket_count = 0
                                    brace_count = 0
                                    in_assignment = False
                                    
                                    for i in range(start_line, len(lines)):
                                        line = lines[i]
                                        if not in_assignment and '=' in line:
                                            in_assignment = True
                                        
                                        if in_assignment:
                                            bracket_count += line.count('[') - line.count(']')
                                            brace_count += line.count('{') - line.count('}')
                                            
                                            if bracket_count == 0 and brace_count == 0 and ('=' in lines[start_line]):
                                                end_line = i
                                                break
                                
                                variable_ranges[var_name] = (start_line, end_line)
            
            # Replace each setting in reverse order (to maintain line numbers)
            sorted_vars = sorted(variable_ranges.items(), key=lambda x: x[1][0], reverse=True)
            
            for var_name, (start_line, end_line) in sorted_vars:
                if var_name in self.settings_cache:
                    # Generate the new formatted assignment
                    new_assignment = self._format_setting_value(var_name, self.settings_cache[var_name])
                    
                    # Replace the lines
                    lines[start_line:end_line + 1] = new_assignment.split('\n')
            
            # Write the updated content
            updated_content = '\n'.join(lines)
            
            with open(self.settings_file_path, 'w', encoding='utf-8') as f:
                f.write(updated_content)
            
            logger.info(f"Successfully updated settings file: {self.settings_file_path}")
            return True
            
        except Exception as e:
            logger.error(f"Failed to write settings file: {e}")
            return False
    
    def _format_setting_value(self, key: str, value: Any) -> str:
        """Format a setting value with proper indentation and structure."""
        if isinstance(value, dict):
            if not value:  # Empty dict
                return f"{key} = {{}}"
            
            # Multi-line dictionary formatting
            lines = [f"{key} = {{"]
            for dict_key, dict_value in value.items():
                if isinstance(dict_value, str):
                    formatted_value = repr(dict_value)
                elif isinstance(dict_value, list):
                    formatted_value = repr(dict_value)
                else:
                    formatted_value = repr(dict_value)
                
                # Add comment for parser config items
                comment = ""
                if key in ["SITE_TIMESHEET_CONFIG", "TRAVEL_TIME_CONFIG", "OVERTIME_RATES_CONFIG"]:
                    comment = self._get_config_comment(key, dict_key)
                
                lines.append(f'    "{dict_key}": {formatted_value},{comment}')
            
            lines.append("}")
            return "\n".join(lines)
        
        elif isinstance(value, list):
            if not value:  # Empty list
                return f"{key} = []"
            
            # Multi-line list formatting for readability
            if len(value) > 3 or any(len(str(item)) > 20 for item in value):
                lines = [f"{key} = ["]
                for item in value:
                    lines.append(f'    {repr(item)},')
                lines.append("]")
                return "\n".join(lines)
            else:
                # Single line for short lists
                return f"{key} = {repr(value)}"
        
        else:
            # Simple values (strings, numbers, booleans)
            return f"{key} = {repr(value)}"
    
    def _get_config_comment(self, config_key: str, field_key: str) -> str:
        """Get appropriate comment for configuration fields."""
        comments = {
            "SITE_TIMESHEET_CONFIG": {
                "date_row_search_range": "  # Maximum rows to search for date headers",
                "employee_start_row": "  # Row where employee data typically starts",
                "overtime_column": "  # Column K (11th column) for overtime totals",
                "region_override_hours": "  # Hours to assign for region override entries"
            },
            "TRAVEL_TIME_CONFIG": {
                "employee_name_column": "  # Column A",
                "site_name_column": "  # Column B",
                "hours_column": "  # Column D",
                "data_start_row": "  # Row where data starts"
            },
            "OVERTIME_RATES_CONFIG": {
                "employee_name_columns": "  # Try column A, then B",
                "overtime_flag_columns": "  # Try column C, then D",
                "overtime_rate_columns": "  # Try column D, then E"
            }
        }
        
        return comments.get(config_key, {}).get(field_key, "")
    
    def reset_to_defaults(self) -> bool:
        """Reset all settings to their default values."""
        try:
            # Default settings
            defaults = {
                "XERO_API_BASE_URL": "https://api.xero.com/api.xro/2.0",
                "XERO_PAYROLL_API_BASE_URL": "https://api.xero.com/payroll.xro/2.0",
                "OAUTH_SCOPES": ["offline_access", "payroll.employees.read", "payroll.timesheets"],
                "SUPPORTED_FILE_EXTENSIONS": [".xlsx", ".xls"],
                "EXPECTED_FILES": ["Site Timesheet", "Travel Time", "Employee Overtime Rates"],
                "FUZZY_MATCH_THRESHOLD": 85.0,
                "FUZZY_MATCH_CUTOFF": 60.0,
                "HOUR_TYPE_TO_XERO_MAPPING": {
                    "REGULAR": "Regular Hours",
                    "OVERTIME": "Overtime Hours",
                    "HOLIDAY": "Holiday",
                    "TRAVEL": "Travel Hours"
                },
                "HOUR_TYPE_KEYS": ["REGULAR", "OVERTIME", "TRAVEL", "HOLIDAY"],
                "HOLIDAY_HOURS_PER_DAY": 8.0,
                "SITE_TIMESHEET_CONFIG": {
                    "date_row_search_range": 20,
                    "employee_start_row": 11,
                    "overtime_column": 11,
                    "region_override_hours": 8.0,
                },
                "TRAVEL_TIME_CONFIG": {
                    "employee_name_column": 1,
                    "site_name_column": 2,
                    "hours_column": 4,
                    "data_start_row": 2,
                    "fake_employee_patterns": ['test', 'fake', 'example', 'dummy', 'sample', 'xxx'],
                },
                "OVERTIME_RATES_CONFIG": {
                    "exact_title_phrase": "overtime rate for employees",
                    "data_start_row": 2,
                    "max_search_columns": 20,
                    "employee_name_columns": [1, 2],
                    "overtime_flag_columns": [3, 4],
                    "overtime_rate_columns": [4, 5],
                },
                "API_RATE_LIMIT_DELAY": 1.0,
                "MAX_RETRIES": 3
            }
            
            return self.update_settings(defaults)
            
        except Exception as e:
            logger.error(f"Failed to reset settings: {e}")
            return False
    
    def export_settings(self) -> Dict[str, Any]:
        """Export current settings for backup."""
        return self.settings_cache.copy()
    
    def import_settings(self, settings: Dict[str, Any]) -> bool:
        """Import settings from backup."""
        return self.update_settings(settings)
    
    def get_setting_info(self) -> Dict[str, Dict[str, str]]:
        """Get metadata about each setting for the UI."""
        return {
            "XERO_API_BASE_URL": {
                "type": "url",
                "description": "Base URL for Xero API calls",
                "category": "xero_api"
            },
            "XERO_PAYROLL_API_BASE_URL": {
                "type": "url", 
                "description": "Base URL for Xero Payroll API calls",
                "category": "xero_api"
            },
            "OAUTH_SCOPES": {
                "type": "list",
                "description": "OAuth scopes required for Xero authentication",
                "category": "xero_api"
            },
            "SUPPORTED_FILE_EXTENSIONS": {
                "type": "list",
                "description": "File extensions accepted for upload",
                "category": "file_processing"
            },
            "EXPECTED_FILES": {
                "type": "list",
                "description": "Expected file names for processing",
                "category": "file_processing"
            },
            "FUZZY_MATCH_THRESHOLD": {
                "type": "number",
                "description": "Minimum similarity score for automatic employee matching (0-100)",
                "category": "employee_matching",
                "min": 0,
                "max": 100
            },
            "FUZZY_MATCH_CUTOFF": {
                "type": "number",
                "description": "Minimum similarity score to suggest employee matches (0-100)",
                "category": "employee_matching",
                "min": 0,
                "max": 100
            },
            "HOLIDAY_HOURS_PER_DAY": {
                "type": "number",
                "description": "Default hours to assign for holiday entries",
                "category": "hour_types",
                "min": 0
            },
            "API_RATE_LIMIT_DELAY": {
                "type": "number",
                "description": "Seconds to wait between API calls",
                "category": "api_settings",
                "min": 0
            },
            "MAX_RETRIES": {
                "type": "integer",
                "description": "Maximum number of API call retries",
                "category": "api_settings",
                "min": 1
            },
            "SITE_TIMESHEET_CONFIG": {
                "type": "dict",
                "description": "Configuration for parsing site timesheet files",
                "category": "parser_config"
            },
            "TRAVEL_TIME_CONFIG": {
                "type": "dict",
                "description": "Configuration for parsing travel time files",
                "category": "parser_config"
            },
            "OVERTIME_RATES_CONFIG": {
                "type": "dict",
                "description": "Configuration for parsing overtime rates files",
                "category": "parser_config"
            }
        }