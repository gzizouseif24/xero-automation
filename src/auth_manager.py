"""
OAuth 2.0 Manager for Xero API Authentication
...
"""
import json
import secrets
import urllib.parse
import webbrowser
from datetime import datetime, timedelta
from typing import Dict, Optional, Tuple, List
import requests
from http.server import HTTPServer, BaseHTTPRequestHandler
import threading
import time
import os
from dotenv import load_dotenv
from config.settings import OAUTH_SCOPES

# Import web-compatible token storage
from src.token_storage import get_web_token_storage

class OAuthCallbackHandler(BaseHTTPRequestHandler):
    """HTTP request handler for OAuth callback"""
    
    def do_GET(self):
        """Handle GET request from OAuth callback"""
        # Parse the callback URL to extract authorization code
        parsed_url = urllib.parse.urlparse(self.path)
        query_params = urllib.parse.parse_qs(parsed_url.query)
        
        if 'code' in query_params:
            # Store the authorization code for the main thread to retrieve
            self.server.auth_code = query_params['code'][0]
            self.server.auth_state = query_params.get('state', [None])[0]
            
            # Send success response to browser
            self.send_response(200)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(b'''
                <html>
                <head><title>Xero Authorization Complete</title></head>
                <body>
                    <h1>Authorization Successful!</h1>
                    <p>You can now close this browser window and return to the application.</p>
                </body>
                </html>
            ''')
        elif 'error' in query_params:
            # Handle authorization error
            error = query_params['error'][0]
            error_description = query_params.get('error_description', ['Unknown error'])[0]
            self.server.auth_error = f"{error}: {error_description}"
            
            self.send_response(400)
            self.send_header('Content-type', 'text/html')
            self.end_headers()
            self.wfile.write(f'''
                <html>
                <head><title>Xero Authorization Error</title></head>
                <body>
                    <h1>Authorization Failed</h1>
                    <p>Error: {error}</p>
                    <p>Description: {error_description}</p>
                </body>
                </html>
            '''.encode())
        
        # Signal that we've received the callback
        self.server.callback_received = True
    
    def log_message(self, format, *args):
        """Suppress default HTTP server logging"""
        pass


class AuthManager:
    """
    Manages OAuth 2.0 authentication flow for Xero API
    
    Handles:
    - Initial authorization with required scopes
    - Secure token storage using encrypted file storage
    - Automatic token refresh
    - Token validation
    - Tenant/organization selection
    """
    
    # Xero OAuth 2.0 endpoints
    AUTHORIZATION_URL = "https://login.xero.com/identity/connect/authorize"
    TOKEN_URL = "https://identity.xero.com/connect/token"
    CONNECTIONS_URL = "https://api.xero.com/connections"
    
    # Required scopes for payroll automation
    REQUIRED_SCOPES = OAUTH_SCOPES

    # Web-compatible token storage using encrypted file storage
    # Uses environment-based key derivation for security
    
    def __init__(self, client_id: Optional[str] = None, client_secret: Optional[str] = None, redirect_uri: Optional[str] = None):
        """
        Initialize OAuth manager
        
        Args:
            client_id: Xero app client ID (optional, will load from environment if not provided)
            client_secret: Xero app client secret (optional, will load from environment if not provided)
            redirect_uri: OAuth callback URI (optional, will load from environment or use default)
        """
        # Load environment variables from .env file
        load_dotenv()

        # If client_id is not provided, load from environment
        if client_id is None:
            client_id = os.getenv('XERO_CLIENT_ID')

        # If client_secret is not provided, load from environment
        if client_secret is None:
            client_secret = os.getenv('XERO_CLIENT_SECRET')

        # If redirect_uri is not provided, load from environment; fallback to default
        if redirect_uri is None:
            redirect_uri = os.getenv('XERO_REDIRECT_URI', "http://localhost:5000/callback")
        
        # After loading, validate that we have the essential credentials
        if not client_id or not client_secret:
            raise ValueError("Xero Client ID and Client Secret must be provided or set in environment variables (XERO_CLIENT_ID, XERO_CLIENT_SECRET)")
        
        self.client_id = client_id
        self.client_secret = client_secret
        self.redirect_uri = redirect_uri
        self.access_token: Optional[str] = None
        self.refresh_token: Optional[str] = None
        self.token_expires_at: Optional[datetime] = None
        self.tenant_id: Optional[str] = None
        self.tenant_name: Optional[str] = None
        
    def get_authorization_url(self) -> Tuple[str, str]:
        """
        Generate authorization URL for OAuth flow
        
        Returns:
            Tuple of (authorization_url, state) where state is used for CSRF protection
        """
        # Generate random state for CSRF protection
        state = secrets.token_urlsafe(32)
        
        # Build authorization URL with required parameters
        params = {
            'response_type': 'code',
            'client_id': self.client_id,
            'redirect_uri': self.redirect_uri,
            'scope': ' '.join(self.REQUIRED_SCOPES),
            'state': state
        }
        
        auth_url = f"{self.AUTHORIZATION_URL}?{urllib.parse.urlencode(params)}"
        return auth_url, state
    
    def start_callback_server(self, port: int = 5000) -> HTTPServer:
        """
        Start local HTTP server to handle OAuth callback
        
        Args:
            port: Port to listen on (default 5000)
            
        Returns:
            HTTPServer instance
        """
        server = HTTPServer(('localhost', port), OAuthCallbackHandler)
        server.auth_code = None
        server.auth_state = None
        server.auth_error = None
        server.callback_received = False
        return server
    
    def wait_for_callback(self, server: HTTPServer, expected_state: str, timeout: int = 300) -> str:
        """
        Wait for OAuth callback and extract authorization code
        
        Args:
            server: HTTP server instance
            expected_state: Expected state value for CSRF protection
            timeout: Timeout in seconds (default 5 minutes)
            
        Returns:
            Authorization code
            
        Raises:
            TimeoutError: If callback not received within timeout
            ValueError: If state doesn't match or authorization error occurred
        """
        start_time = time.time()
        
        while not server.callback_received and (time.time() - start_time) < timeout:
            server.handle_request()
            time.sleep(0.1)
        
        if not server.callback_received:
            raise TimeoutError("OAuth callback not received within timeout period")
        
        if server.auth_error:
            raise ValueError(f"OAuth authorization failed: {server.auth_error}")
        
        if server.auth_state != expected_state:
            raise ValueError("OAuth state mismatch - possible CSRF attack")
        
        if not server.auth_code:
            raise ValueError("No authorization code received")
        
        return server.auth_code

    def is_authorized(self) -> bool:
        """
        Check if we have valid, stored tokens by attempting to load them.
        """
        # If tokens are already in memory from a previous check, we are good.
        if self.refresh_token:
            return True
        # Otherwise, try loading from secure storage.
        return self.load_tokens_from_storage()
    
    def exchange_code_for_tokens(self, authorization_code: str) -> Dict:
        """
        Exchange authorization code for access and refresh tokens
        
        Args:
            authorization_code: Authorization code from OAuth callback
            
        Returns:
            Token response dictionary
            
        Raises:
            requests.RequestException: If token exchange fails
        """
        token_data = {
            'grant_type': 'authorization_code',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'code': authorization_code,
            'redirect_uri': self.redirect_uri
        }
        
        response = requests.post(
            self.TOKEN_URL,
            data=token_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        if response.status_code != 200:
            raise requests.RequestException(f"Token exchange failed: {response.status_code} - {response.text}")
        
        token_response = response.json()
        
        # Store tokens and expiration time
        self.access_token = token_response['access_token']
        self.refresh_token = token_response.get('refresh_token')
        
        # Calculate expiration time (subtract 60 seconds for safety margin)
        expires_in = token_response.get('expires_in', 1800)  # Default 30 minutes
        self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
        
        return token_response
    
    def get_connections(self) -> List[Dict]:
        """
        Get list of connected Xero organizations/tenants
        
        Returns:
            List of connection dictionaries containing tenant info
            
        Raises:
            requests.RequestException: If API call fails
            RuntimeError: If no valid access token
        """
        if not self.access_token:
            raise RuntimeError("No access token available. Please authorize first.")
        
        headers = {
            'Authorization': f'Bearer {self.access_token}',
            'Content-Type': 'application/json'
        }
        
        response = requests.get(self.CONNECTIONS_URL, headers=headers)
        
        if response.status_code != 200:
            raise requests.RequestException(f"Failed to get connections: {response.status_code} - {response.text}")
        
        return response.json()
    
    def select_tenant(self) -> bool:
        """
        Select the first available tenant/organization automatically
        
        Returns:
            True if tenant found and selected, False otherwise
        """
        try:
            connections = self.get_connections()
            
            if not connections:
                print("❌ No tenants available")
                return False
            
            # Automatically select the first available tenant
            selected_tenant = connections[0]
            self.tenant_id = selected_tenant['tenantId']
            self.tenant_name = selected_tenant['tenantName']
            print(f"✅ Auto-selected tenant: {self.tenant_name} (ID: {self.tenant_id})")
            return True
                    
        except Exception as e:
            print(f"❌ Error selecting tenant: {e}")
            return False
    
    def save_tokens_to_storage(self) -> None:
        """
        Save tokens securely to web-compatible storage
        
        Raises:
            RuntimeError: If no tokens to save
        """
        if not self.refresh_token:
            raise RuntimeError("No refresh token to save")
        
        token_data = {
            'refresh_token': self.refresh_token,
            'access_token': self.access_token,
            'expires_at': self.token_expires_at.isoformat() if self.token_expires_at else None,
            'tenant_id': self.tenant_id,
            'tenant_name': self.tenant_name
        }
        
        success = get_web_token_storage().save_tokens(token_data)
        if success:
            print("OK Tokens saved to secure storage")
        else:
            raise RuntimeError("Failed to save tokens to storage")
    
    def load_tokens_from_storage(self) -> bool:
        """
        Load tokens from web-compatible storage
        
        Returns:
            True if tokens loaded successfully, False otherwise
        """
        try:
            token_data = get_web_token_storage().load_tokens()
            if token_data:
                self.refresh_token = token_data.get('refresh_token')
                self.access_token = token_data.get('access_token')
                self.tenant_id = token_data.get('tenant_id')
                self.tenant_name = token_data.get('tenant_name')
                
                if token_data.get('expires_at'):
                    self.token_expires_at = datetime.fromisoformat(token_data['expires_at'])
                
                return True
            return False
        except Exception as e:
            print(f"Warning: Failed to load tokens: {e}")
            return False
    
    def is_access_token_valid(self) -> bool:
        """
        Check if current access token is valid (not expired)
        
        Returns:
            True if token is valid, False otherwise
        """
        if not self.access_token or not self.token_expires_at:
            return False
        
        return datetime.now() < self.token_expires_at
    
    def refresh_access_token(self) -> Dict:
        """
        Refresh access token using refresh token
        
        Returns:
            New token response dictionary
            
        Raises:
            RuntimeError: If no refresh token available
            requests.RequestException: If token refresh fails
        """
        if not self.refresh_token:
            raise RuntimeError("No refresh token available")
        
        refresh_data = {
            'grant_type': 'refresh_token',
            'client_id': self.client_id,
            'client_secret': self.client_secret,
            'refresh_token': self.refresh_token
        }
        
        response = requests.post(
            self.TOKEN_URL,
            data=refresh_data,
            headers={'Content-Type': 'application/x-www-form-urlencoded'}
        )
        
        if response.status_code != 200:
            raise requests.RequestException(f"Token refresh failed: {response.status_code} - {response.text}")
        
        token_response = response.json()
        
        # Update tokens (Xero uses rotating refresh tokens)
        self.access_token = token_response['access_token']
        if 'refresh_token' in token_response:
            self.refresh_token = token_response['refresh_token']
        
        # Update expiration time
        expires_in = token_response.get('expires_in', 1800)
        self.token_expires_at = datetime.now() + timedelta(seconds=expires_in - 60)
        
        # Save updated tokens
        try:
            self.save_tokens_to_storage()
        except Exception as e:
            print(f"Warning: Failed to save refreshed tokens: {e}")
        
        return token_response
    
    def ensure_valid_access_token(self) -> str:
        """
        Ensure we have a valid access token, refreshing if necessary
        
        Returns:
            Valid access token
            
        Raises:
            RuntimeError: If unable to obtain valid token
        """
        # Try to load tokens from storage if we don't have them
        if not self.access_token:
            if not self.load_tokens_from_storage():
                raise RuntimeError("No stored tokens found. Please run initial authorization.")
        
        # Refresh token if expired
        if not self.is_access_token_valid():
            try:
                self.refresh_access_token()
            except requests.RequestException as e:
                raise RuntimeError(f"Failed to refresh access token: {e}")
        
        if not self.access_token:
            raise RuntimeError("Unable to obtain valid access token")
        
        return self.access_token
    
    def get_auth_headers(self) -> Dict[str, str]:
        """
        Get authorization headers for API calls
        
        Returns:
            Dictionary with authorization headers including tenant ID
            
        Raises:
            RuntimeError: If no valid access token or tenant ID
        """
        access_token = self.ensure_valid_access_token()
        
        if not self.tenant_id:
            raise RuntimeError("No tenant selected. Please run authorization and tenant selection.")
        
        return {
            'Authorization': f'Bearer {access_token}',
            'Xero-tenant-id': self.tenant_id,
            'Content-Type': 'application/json'
        }
    
    def authorize(self) -> bool:
        """
        Complete OAuth 2.0 authorization flow including tenant selection
        
        Returns:
            True if authorization successful, False otherwise
        """
        try:
            print("Starting Xero OAuth 2.0 authorization...")
            
            # Generate authorization URL
            auth_url, state = self.get_authorization_url()
            
            # Start callback server
            server = self.start_callback_server()
            print(f"Started callback server on {self.redirect_uri}")
            
            # Open browser for user authorization
            print(f"Opening browser for authorization...")
            print(f"If browser doesn't open automatically, visit: {auth_url}")
            webbrowser.open(auth_url)
            
            # Wait for callback
            print("Waiting for authorization callback...")
            auth_code = self.wait_for_callback(server, state)
            
            # Exchange code for tokens
            print("Exchanging authorization code for tokens...")
            self.exchange_code_for_tokens(auth_code)
            
            # Select tenant/organization
            print("Selecting tenant/organization...")
            if not self.select_tenant():
                print("❌ Tenant selection cancelled")
                return False
            
            # Save tokens securely
            print("Saving tokens to secure storage...")
            self.save_tokens_to_storage()
            
            print("✅ Authorization successful!")
            print(f"   Organization: {self.tenant_name}")
            print(f"   Tenant ID: {self.tenant_id}")
            return True
            
        except Exception as e:
            print(f"❌ Authorization failed: {e}")
            return False
        finally:
            # Clean up server
            try:
                server.server_close()
            except:
                pass
    
    def revoke_tokens(self) -> None:
        """
        Revoke stored tokens and clear from storage
        """
        # Clear from storage
        try:
            get_web_token_storage().clear_tokens()
        except Exception as e:
            print(f"Warning: Failed to clear tokens from storage: {e}")
        
        # Clear in-memory tokens
        self.access_token = None
        self.refresh_token = None
        self.token_expires_at = None
        self.tenant_id = None
        self.tenant_name = None
        
        print("OK Tokens revoked and cleared from secure storage")