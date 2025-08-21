#!/usr/bin/env python3
"""
Token Clearing Utility for Xero Payroll Automation

This script provides a simple way to clear stored authentication tokens
for testing and development purposes.
"""

import os
import sys
from pathlib import Path

# Add the project root to Python path so we can import our modules
project_root = Path(__file__).parent.parent
sys.path.insert(0, str(project_root))

# Load environment variables from .env file
def load_env_file():
    """Load environment variables from .env file."""
    env_file = project_root / '.env'
    if env_file.exists():
        with open(env_file, 'r') as f:
            for line in f:
                line = line.strip()
                if line and not line.startswith('#') and '=' in line:
                    key, value = line.split('=', 1)
                    key = key.strip()
                    value = value.strip().strip('"\'')
                    os.environ[key] = value
        print(f"✅ Loaded environment variables from {env_file}")
    else:
        print(f"⚠️  No .env file found at {env_file}")

# Load environment variables before importing our modules
load_env_file()

from src.token_storage import get_web_token_storage
from src.auth_manager import AuthManager


def clear_tokens_via_storage():
    """Clear tokens using the token storage directly."""
    try:
        storage = get_web_token_storage()
        if storage.has_tokens():
            success = storage.clear_tokens()
            if success:
                print("✅ Tokens cleared successfully via storage")
                return True
            else:
                print("❌ Failed to clear tokens via storage")
                return False
        else:
            print("ℹ️  No tokens found in storage")
            return True
    except Exception as e:
        print(f"❌ Error clearing tokens via storage: {e}")
        return False


def clear_tokens_via_auth_manager():
    """Clear tokens using the AuthManager."""
    try:
        auth_manager = AuthManager()
        auth_manager.revoke_tokens()
        print("✅ Tokens cleared successfully via AuthManager")
        return True
    except Exception as e:
        print(f"❌ Error clearing tokens via AuthManager: {e}")
        return False


def clear_token_directory():
    """Manually clear the entire token directory."""
    try:
        project_root = Path(__file__).parent.parent
        token_dir = project_root / ".xero_tokens"
        
        if not token_dir.exists():
            print("ℹ️  Token directory doesn't exist")
            return True
        
        # Remove all files in the token directory
        files_removed = 0
        for file_path in token_dir.iterdir():
            if file_path.is_file():
                file_path.unlink()
                files_removed += 1
                print(f"   Removed: {file_path.name}")
        
        if files_removed > 0:
            print(f"✅ Cleared {files_removed} files from token directory")
        else:
            print("ℹ️  Token directory was already empty")
        
        return True
    except Exception as e:
        print(f"❌ Error clearing token directory: {e}")
        return False


def show_token_status():
    """Show current token status."""
    try:
        print("\n📊 Current Token Status:")
        
        # Check storage
        storage = get_web_token_storage()
        if storage.has_tokens():
            print("   Storage: ✅ Tokens present")
        else:
            print("   Storage: ❌ No tokens")
        
        # Check AuthManager
        auth_manager = AuthManager()
        if auth_manager.is_authorized():
            print("   AuthManager: ✅ Authorized")
            if auth_manager.tenant_name:
                print(f"   Organization: {auth_manager.tenant_name}")
        else:
            print("   AuthManager: ❌ Not authorized")
        
        # Check token directory
        project_root = Path(__file__).parent.parent
        token_dir = project_root / ".xero_tokens"
        if token_dir.exists():
            files = list(token_dir.glob("*"))
            if files:
                print(f"   Token Directory: ✅ {len(files)} files")
                for file_path in files:
                    print(f"      - {file_path.name}")
            else:
                print("   Token Directory: ❌ Empty")
        else:
            print("   Token Directory: ❌ Doesn't exist")
            
    except Exception as e:
        print(f"❌ Error checking token status: {e}")


def main():
    """Main function - clears tokens immediately."""
    print("🧹 Clearing Xero Authentication Tokens...")
    print("=" * 40)
    
    # Show current status first
    print("\n📊 Current Status:")
    show_token_status()
    
    # Clear tokens using all methods
    print("\n🚀 Clearing tokens...")
    
    success1 = clear_tokens_via_auth_manager()
    success2 = clear_tokens_via_storage()
    success3 = clear_token_directory()
    
    print("\n📊 Final Status:")
    show_token_status()
    
    if success1 and success2 and success3:
        print("\n✅ SUCCESS: All tokens have been cleared!")
        print("   You can now test fresh authentication flows.")
    else:
        print("\n⚠️  WARNING: Some clearing methods had issues")
        print("   Check the output above for details.")
    
    print("\n💡 Next steps:")
    print("   - Start API server: python -m uvicorn src.api_server:app --reload")
    print("   - Open http://localhost:8000 and test authentication")





if __name__ == "__main__":
    main()