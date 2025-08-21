"""
Authentication middleware for API server with improved token validation and session management
"""
import logging
from typing import Optional, Dict, Any
from contextlib import contextmanager
from src.xero_api_client import XeroAPIClient, XeroAPIError, XeroAuthenticationError

logger = logging.getLogger(__name__)

class AuthenticationManager:
    """
    Centralized authentication manager for API server
    Handles token validation, client session management, and error handling
    """
    
    def __init__(self):
        self._client: Optional[XeroAPIClient] = None
        self._connection_status: Optional[Dict[str, Any]] = None
        self._last_validation_time: Optional[float] = None
        
    def _validate_connection(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Validate current connection status with caching
        
        Args:
            force_refresh: Force refresh of connection status
            
        Returns:
            Connection status dictionary
        """
        import time
        
        current_time = time.time()
        
        # Use cached status if recent (within 30 seconds) and not forcing refresh
        if (not force_refresh and 
            self._connection_status and 
            self._last_validation_time and 
            (current_time - self._last_validation_time) < 30):
            return self._connection_status
        
        try:
            # Create temporary client for status check
            temp_client = XeroAPIClient()
            status = temp_client.get_connection_status()
            temp_client.close()
            
            self._connection_status = status
            self._last_validation_time = current_time
            
            logger.info(f"Connection status validated: authenticated={status.get('authenticated')}")
            return status
            
        except Exception as e:
            logger.error(f"Connection validation failed: {e}")
            error_status = {
                'authenticated': False,
                'tenant_id': None,
                'organization_name': None,
                'error': str(e)
            }
            self._connection_status = error_status
            self._last_validation_time = current_time
            return error_status
    
    def get_connection_status(self, force_refresh: bool = False) -> Dict[str, Any]:
        """
        Get current connection status
        
        Args:
            force_refresh: Force refresh of connection status
            
        Returns:
            Connection status dictionary
        """
        return self._validate_connection(force_refresh)
    
    def ensure_authenticated(self) -> bool:
        """
        Ensure we have valid authentication
        
        Returns:
            True if authenticated, False otherwise
        """
        status = self._validate_connection()
        return status.get('authenticated', False)
    
    @contextmanager
    def get_authenticated_client(self):
        """
        Context manager for getting an authenticated Xero API client
        Ensures proper session management and cleanup
        
        Yields:
            XeroAPIClient: Authenticated client instance
            
        Raises:
            XeroAuthenticationError: If authentication fails
        """
        client = None
        try:
            # Validate authentication first
            if not self.ensure_authenticated():
                raise XeroAuthenticationError("Not authenticated with Xero")
            
            # Create and authenticate client
            client = XeroAPIClient()
            if not client.authenticate():
                raise XeroAuthenticationError("Failed to authenticate Xero client")
            
            logger.debug("Authenticated client created successfully")
            yield client
            
        except XeroAuthenticationError:
            raise
        except Exception as e:
            logger.error(f"Failed to create authenticated client: {e}")
            raise XeroAuthenticationError(f"Client creation failed: {e}")
        finally:
            # Ensure client is properly closed
            if client:
                try:
                    client.close()
                    logger.debug("Client session closed")
                except Exception as e:
                    logger.warning(f"Error closing client: {e}")
    
    def initiate_oauth_flow(self) -> bool:
        """
        Initiate OAuth flow for authentication
        
        Returns:
            True if successful, False otherwise
        """
        try:
            logger.info("Initiating OAuth flow...")
            
            # Create client and run authorization
            client = XeroAPIClient()
            success = client.authenticate()
            client.close()
            
            if success:
                # Clear cached status to force refresh
                self._connection_status = None
                self._last_validation_time = None
                logger.info("OAuth flow completed successfully")
                return True
            else:
                logger.error("OAuth flow failed")
                return False
                
        except Exception as e:
            logger.error(f"OAuth flow error: {e}")
            return False
    
    def clear_authentication(self) -> None:
        """
        Clear authentication state and cached data
        """
        self._connection_status = None
        self._last_validation_time = None
        
        try:
            # Clear stored tokens
            from src.auth_manager import AuthManager
            auth_manager = AuthManager()
            auth_manager.revoke_tokens()
            logger.info("Authentication cleared successfully")
        except Exception as e:
            logger.error(f"Error clearing authentication: {e}")

# Global authentication manager instance
auth_manager = AuthenticationManager()