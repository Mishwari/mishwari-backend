"""Google Indexing API integration"""
import os
import requests
from google.oauth2 import service_account
from google.auth.transport.requests import Request


def notify_google_indexing(url, action='URL_UPDATED'):
    """
    Notify Google about new/updated URLs for instant indexing
    action: 'URL_UPDATED' or 'URL_DELETED'
    """
    # Skip if not in production or credentials not set
    service_account_file = os.getenv('GOOGLE_SERVICE_ACCOUNT_FILE')
    if not service_account_file:
        print(f'[INDEXING] GOOGLE_SERVICE_ACCOUNT_FILE not set in environment')
        return False
    if not os.path.exists(service_account_file):
        print(f'[INDEXING] Credentials file not found: {service_account_file}')
        return False
    
    print(f'[INDEXING] Attempting to index: {url} (action: {action})')
    
    try:
        SCOPES = ['https://www.googleapis.com/auth/indexing']
        credentials = service_account.Credentials.from_service_account_file(
            service_account_file, scopes=SCOPES
        )
        credentials.refresh(Request())
        
        endpoint = 'https://indexing.googleapis.com/v3/urlNotifications:publish'
        headers = {
            'Content-Type': 'application/json',
            'Authorization': f'Bearer {credentials.token}'
        }
        payload = {
            'url': url,
            'type': action
        }
        
        response = requests.post(endpoint, headers=headers, json=payload)
        
        if response.status_code == 200:
            result = response.json()
            print(f'[INDEXING] ✓ Success: {url}')
            print(f'[INDEXING] Response: {result}')
            return True
        else:
            print(f'[INDEXING] ✗ Failed ({response.status_code}): {response.text}')
            return False
            
    except Exception as e:
        print(f'[INDEXING] Error notifying Google: {str(e)}')
        return False
