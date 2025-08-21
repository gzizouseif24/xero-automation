"""
Non-interactive token storage solution for web applications
Provides secure token storage without requiring interactive password prompts
"""
import os
import json
import logging
from pathlib import Path
from typing import Optional, Dict, Any
from cryptography.fernet import Fernet
from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.kdf.pbkdf2 import PBKDF2HMAC
import base64

logger = logging.getLogger(__name__)

class WebCompatibleTokenStorage:
    """
    Token storage that works with web applications without interactive prompts
    Uses file-based storage with encryption derived from environment variables
    """
    
    def __init__(self, storage_dir: Optional[str] = None):
        """
        Initialize token storage
        
        Args:
            storage_dir: Directory to store token files (default: .xero_tokens in project root)
        """
        if storage_dir:
            self.storage_dir = Path(storage_dir)
        else:
            # Use project root/.xero_tokens directory
            project_root = Path(__file__).parent.parent
            self.storage_dir = project_root / ".xero_tokens"
        
        # Ensure storage directory exists
        self.storage_dir.mkdir(exist_ok=True, mode=0o700)  # Restrict permissions
        
        # Token file path
        self.token_file = self.storage_dir / "tokens.enc"
        
        # Initialize encryption
        self._cipher = self._get_cipher()
    
    def _get_cipher(self) -> Fernet:
        """
        Get encryption cipher using environment-based key derivation
        
        Returns:
            Fernet cipher for encryption/decryption
        """
        try:
            # Use client credentials to derive encryption key
            client_id = os.getenv('XERO_CLIENT_ID', '')
            client_secret = os.getenv('XERO_CLIENT_SECRET', '')
            
            if not client_id or not client_secret:
                raise ValueError("XERO_CLIENT_ID and XERO_CLIENT_SECRET must be set for token encryption")
            
            # Create a deterministic key from client credentials
            password = f"{client_id}:{client_secret}".encode()
            salt = b"xero_token_storage_salt_v1"  # Fixed salt for deterministic key
            
            # Derive key using PBKDF2
            kdf = PBKDF2HMAC(
                algorithm=hashes.SHA256(),
                length=32,
                salt=salt,
                iterations=100000,
            )
            key = base64.urlsafe_b64encode(kdf.derive(password))
            
            return Fernet(key)
            
        except Exception as e:
            logger.error(f"Failed to initialize encryption: {e}")
            raise
    
    def save_tokens(self, token_data: Dict[str, Any]) -> bool:
        """
        Save tokens to encrypted storage
        
        Args:
            token_data: Token data dictionary
            
        Returns:
            True if successful, False otherwise
        """
        try:
            # Serialize token data
            json_data = json.dumps(token_data, default=str)
            
            # Encrypt data
            encrypted_data = self._cipher.encrypt(json_data.encode())
            
            # Write to file with restricted permissions
            with open(self.token_file, 'wb') as f:
                f.write(encrypted_data)
            
            # Set file permissions (owner read/write only)
            os.chmod(self.token_file, 0o600)
            
            logger.info("Tokens saved to encrypted storage")
            return True
            
        except Exception as e:
            logger.error(f"Failed to save tokens: {e}")
            return False
    
    def load_tokens(self) -> Optional[Dict[str, Any]]:
        """
        Load tokens from encrypted storage
        
        Returns:
            Token data dictionary if successful, None otherwise
        """
        try:
            if not self.token_file.exists():
                logger.debug("No token file found")
                return None
            
            # Read encrypted data
            with open(self.token_file, 'rb') as f:
                encrypted_data = f.read()
            
            # Decrypt data
            decrypted_data = self._cipher.decrypt(encrypted_data)
            
            # Parse JSON
            token_data = json.loads(decrypted_data.decode())
            
            logger.debug("Tokens loaded from encrypted storage")
            return token_data
            
        except Exception as e:
            logger.error(f"Failed to load tokens: {e}")
            return None
    
    def clear_tokens(self) -> bool:
        """
        Clear stored tokens
        
        Returns:
            True if successful, False otherwise
        """
        try:
            if self.token_file.exists():
                self.token_file.unlink()
                logger.info("Tokens cleared from storage")
            return True
            
        except Exception as e:
            logger.error(f"Failed to clear tokens: {e}")
            return False
    
    def has_tokens(self) -> bool:
        """
        Check if tokens exist in storage
        
        Returns:
            True if tokens exist, False otherwise
        """
        return self.token_file.exists()

# Global instance for use throughout the application (lazy-loaded)
web_token_storage = None

def get_web_token_storage():
    """Get the web token storage instance (lazy-loaded)"""
    global web_token_storage
    if web_token_storage is None:
        web_token_storage = WebCompatibleTokenStorage()
    return web_token_storage