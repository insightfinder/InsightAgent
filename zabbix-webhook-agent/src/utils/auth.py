"""
Authentication utilities for the Zabbix Webhook Agent
"""
from fastapi import HTTPException, Security, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from src.core.config import settings

security = HTTPBearer()


def verify_api_key(credentials: HTTPAuthorizationCredentials = Security(security)) -> bool:
    """
    Verify the API key from the Authorization header
    
    Args:
        credentials: HTTP authorization credentials
        
    Returns:
        bool: True if authentication is successful
        
    Raises:
        HTTPException: If authentication fails
    """
    if credentials.credentials != settings.api_key:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid API key",
            headers={"WWW-Authenticate": "Bearer"},
        )
    return True


def get_current_user(authenticated: bool = Security(verify_api_key)) -> dict:
    """
    Get current authenticated user (placeholder for future user management)
    
    Args:
        authenticated: Authentication status from verify_api_key
        
    Returns:
        dict: User information
    """
    return {"authenticated": authenticated, "user_type": "api_user"}
