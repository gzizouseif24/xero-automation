#!/usr/bin/env python3
"""
Xero Payroll Automation - Main Application Entry Point

This module provides the main entry point for the Xero Payroll Automation system.
It handles command-line interface and orchestrates the payroll processing workflow.
"""

import argparse
import sys
from pathlib import Path
from typing import Optional


class PayrollAutomationApp:
    """Main application controller for Xero Payroll Automation."""
    
    def __init__(self):
        """Initialize the application."""
        self.input_folder: Optional[Path] = None
    
    def run(self, input_folder: str) -> None:
        """
        Main application entry point.
        
        Args:
            input_folder: Path to folder containing timesheet files
        """
        self.input_folder = Path(input_folder)
        
        if not self.input_folder.exists():
            print(f"Error: Input folder '{input_folder}' does not exist.")
            sys.exit(1)
        
        if not self.input_folder.is_dir():
            print(f"Error: '{input_folder}' is not a directory.")
            sys.exit(1)
        
        print(f"Processing payroll files from: {self.input_folder}")
        print("Xero Payroll Automation - Ready for implementation")
        
        # TODO: Implement payroll processing workflow
        # This will be implemented in subsequent tasks


def create_cli_parser() -> argparse.ArgumentParser:
    """Create and configure the command-line argument parser."""
    parser = argparse.ArgumentParser(
        description="Xero Payroll Automation - Automate weekly payroll processing",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python -m src.main /path/to/timesheet/files
  python -m src.main C:\\Payroll\\Week_2025_06_08
        """
    )
    
    parser.add_argument(
        "input_folder",
        help="Path to folder containing timesheet files (Site Timesheet, Travel Time, Employee Overtime Rates)"
    )
    
    parser.add_argument(
        "--version",
        action="version",
        version="Xero Payroll Automation 1.0.0"
    )
    
    return parser


def main() -> None:
    """Main CLI entry point."""
    parser = create_cli_parser()
    args = parser.parse_args()
    
    app = PayrollAutomationApp()
    app.run(args.input_folder)


if __name__ == "__main__":
    main()