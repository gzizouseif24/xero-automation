"""
Command Line Interface utilities for Xero Payroll Automation.

This module provides CLI-specific functionality including user interaction,
progress reporting, and command-line argument handling.
"""

import os
from typing import List, Optional
from src.auth_manager import AuthManager


class UserInterface:
    """Handles user interaction and CLI display."""
    
    @staticmethod
    def confirm_match(timesheet_name: str, suggested_match: str) -> bool:
        """
        Prompt user to confirm an employee name match.
        
        Args:
            timesheet_name: Name found in timesheet files
            suggested_match: Suggested match from Xero employees
            
        Returns:
            True if user confirms the match, False otherwise
        """
        while True:
            response = input(
                f"Match '{timesheet_name}' to '{suggested_match}'? (y/n): "
            ).lower().strip()
            
            if response in ['y', 'yes']:
                return True
            elif response in ['n', 'no']:
                return False
            else:
                print("Please enter 'y' for yes or 'n' for no.")
    
    @staticmethod
    def display_progress(message: str) -> None:
        """Display a progress message to the user."""
        print(f"⏳ {message}")
    
    @staticmethod
    def display_success(message: str) -> None:
        """Display a success message to the user."""
        print(f"✅ {message}")
    
    @staticmethod
    def display_error(message: str) -> None:
        """Display an error message to the user."""
        print(f"❌ {message}")
    
    @staticmethod
    def display_warning(message: str) -> None:
        """Display a warning message to the user."""
        print(f"⚠️  {message}")
    
    @staticmethod
    def display_validation_errors(errors: List[str]) -> None:
        """
        Display a list of validation errors.
        
        Args:
            errors: List of error messages to display
        """
        print("\n❌ Validation Errors Found:")
        for i, error in enumerate(errors, 1):
            print(f"   {i}. {error}")
        print()
    
    @staticmethod
    def display_summary(processed_employees: int, total_timesheets: int) -> None:
        """
        Display processing summary.
        
        Args:
            processed_employees: Number of employees processed
            total_timesheets: Total number of timesheets created
        """
        print(f"\n📊 Processing Summary:")
        print(f"   Employees processed: {processed_employees}")
        print(f"   Timesheets created: {total_timesheets}")
        print(f"   Status: Draft pay run ready in Xero")


class XeroAuthCLI:
    """Command line interface for Xero OAuth authentication."""
    
    def __init__(self):
        """Initialize the auth CLI with credentials from environment."""
        # Load credentials from .env file in spec directory
        env_path = os.path.join('.kiro', 'specs', 'xero-payroll-automation', '.env')
        if os.path.exists(env_path):
            self._load_env_file(env_path)
        
        client_id = os.getenv('Client_id') or os.getenv('XERO_CLIENT_ID')
        client_secret = os.getenv('Client_secret_1') or os.getenv('XERO_CLIENT_SECRET')
        
        if not client_id or not client_secret:
            raise ValueError("Xero client credentials not found. Please check .env file.")
        
        self.auth_manager = AuthManager(client_id, client_secret)
    
    def _load_env_file(self, env_path: str) -> None:
        """Load environment variables from .env file."""
        try:
            with open(env_path, 'r') as f:
                for line in f:
                    line = line.strip()
                    if line and not line.startswith('#') and '=' in line:
                        key, value = line.split('=', 1)
                        key = key.strip()
                        value = value.strip().strip('"\'')
                        os.environ[key] = value
        except Exception as e:
            print(f"Warning: Could not load .env file: {e}")
    
    def check_auth_status(self) -> None:
        """Check and display current authentication status."""
        print("🔐 Checking Xero authentication status...")
        
        if self.auth_manager.is_authorized():
            print("✅ Authenticated with Xero")
            if self.auth_manager.tenant_name:
                print(f"   Organization: {self.auth_manager.tenant_name}")
            if self.auth_manager.is_access_token_valid():
                print("   Access token is valid")
                if self.auth_manager.token_expires_at:
                    print(f"   Token expires at: {self.auth_manager.token_expires_at}")
            else:
                print("   Access token expired (will be refreshed automatically)")
        else:
            print("❌ Not authenticated with Xero")
            print("   Run 'python -m src.cli auth' to authorize the application")
    
    def authorize(self) -> bool:
        """Perform OAuth authorization flow."""
        print("🚀 Starting Xero OAuth authorization...")
        print("   This will open your web browser for authentication")
        
        try:
            success = self.auth_manager.authorize()
            if success:
                print("✅ Authorization successful!")
                print("   You can now use the Xero API")
                return True
            else:
                print("❌ Authorization failed")
                return False
        except Exception as e:
            print(f"❌ Authorization error: {e}")
            return False
    
    def revoke_auth(self) -> None:
        """Revoke current authorization."""
        print("🔓 Revoking Xero authorization...")
        
        try:
            self.auth_manager.revoke_tokens()
            print("✅ Authorization revoked successfully")
        except Exception as e:
            print(f"❌ Error revoking authorization: {e}")
    
    def test_token(self) -> None:
        """Test token validity and refresh."""
        print("🧪 Testing token validity...")
        
        try:
            token = self.auth_manager.ensure_valid_access_token()
            print("✅ Token is valid")
            print(f"   Token: {token[:20]}...")
        except RuntimeError as e:
            print(f"❌ Token error: {e}")
            print("   Run 'python -m src.cli auth' to re-authorize")
        except Exception as e:
            print(f"❌ Unexpected error: {e}")


def main():
    """Main CLI entry point."""
    import sys
    
    if len(sys.argv) < 2:
        print("Xero Payroll Automation CLI")
        print("Usage:")
        print("  python -m src.cli status    - Check authentication status")
        print("  python -m src.cli auth      - Authorize with Xero")
        print("  python -m src.cli revoke    - Revoke authorization")
        print("  python -m src.cli test      - Test token validity")
        return
    
    command = sys.argv[1].lower()
    
    try:
        auth_cli = XeroAuthCLI()
        
        if command == 'status':
            auth_cli.check_auth_status()
        elif command == 'auth':
            auth_cli.authorize()
        elif command == 'revoke':
            auth_cli.revoke_auth()
        elif command == 'test':
            auth_cli.test_token()
        else:
            print(f"Unknown command: {command}")
            print("Available commands: status, auth, revoke, test")
    
    except Exception as e:
        print(f"❌ Error: {e}")


if __name__ == '__main__':
    main()