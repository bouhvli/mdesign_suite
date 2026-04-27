import requests
import getpass
from typing import Literal

class PluginLogger:
    """Logger class for QGIS plugin to post logs to Supabase"""
    
    def __init__(self, supabase_url: str, supabase_key: str):
        """
        Initialize the logger with Supabase credentials
        
        Args:
            supabase_url: Your Supabase project URL
            supabase_key: Your Supabase anon key
        """
        self.api_url = f"{supabase_url}/rest/v1/logs"
        self.headers = {
            "apikey": supabase_key,
            "Authorization": f"Bearer {supabase_key}",
            "Content-Type": "application/json",
            "Prefer": "return=minimal"
        }
    
    def log(
        self,
        types: Literal['survey', 'design', 'validation'],
        design_session: str,
        description: str = ""
    ) -> bool:
        """
        Post a log entry to Supabase
        
        Args:
            types: Type of operation (survey, design, or validation)
            design_session: Design session identifier (project name)
            description: Optional description of the operation
        
        Returns:
            bool: True if successful, False otherwise
        """
        # Get current username
        username = getpass.getuser()
        
        payload = {
            "types": types,
            "username": username,
            "design_session": design_session,
            "description": description
        }
        
        try:
            response = requests.post(
                self.api_url,
                json=payload,
                headers=self.headers,
                timeout=10
            )
            return response.status_code in [200, 201]
        except:
            return False

