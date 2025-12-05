from firebase_admin import auth, credentials, initialize_app
import os
import firebase_admin

def initialize_firebase():
    if not firebase_admin._apps:
        cred_path = os.getenv('FIREBASE_CREDENTIALS_PATH')
        if cred_path and os.path.exists(cred_path):
            cred = credentials.Certificate(cred_path)
            initialize_app(cred)
        else:
            # Try to initialize with environment variables
            project_id = os.getenv('FIREBASE_PROJECT_ID')
            if project_id:
                cred_dict = {
                    'type': 'service_account',
                    'project_id': project_id,
                    'private_key_id': os.getenv('FIREBASE_PRIVATE_KEY_ID'),
                    'private_key': os.getenv('FIREBASE_PRIVATE_KEY', '').replace('\\n', '\n'),
                    'client_email': os.getenv('FIREBASE_CLIENT_EMAIL'),
                    'client_id': os.getenv('FIREBASE_CLIENT_ID'),
                    'auth_uri': 'https://accounts.google.com/o/oauth2/auth',
                    'token_uri': 'https://oauth2.googleapis.com/token',
                    'auth_provider_x509_cert_url': 'https://www.googleapis.com/oauth2/v1/certs',
                    'client_x509_cert_url': f'https://www.googleapis.com/robot/v1/metadata/x509/{os.getenv("FIREBASE_CLIENT_EMAIL")}'
                }
                cred = credentials.Certificate(cred_dict)
                initialize_app(cred)
            else:
                initialize_app()

def verify_firebase_token(id_token: str) -> dict:
    """Verify Firebase ID token and extract phone number"""
    try:
        initialize_firebase()
        decoded_token = auth.verify_id_token(id_token)
        phone_number = decoded_token.get('phone_number')
        
        if not phone_number:
            raise ValueError('Phone number not found in token')
        
        if phone_number.startswith('+'):
            phone_number = phone_number[1:]
        
        return {
            'phone_number': phone_number,
            'uid': decoded_token.get('uid'),
            'firebase_verified': True
        }
    except Exception as e:
        raise ValueError(f'Invalid Firebase token: {str(e)}')
