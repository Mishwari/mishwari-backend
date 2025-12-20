import requests
import logging
import os

logger = logging.getLogger(__name__)

def notify_indexnow(url_list):
    """
    Notify Bing/Yandex via IndexNow protocol
    url_list: List of full URLs to be indexed (e.g., ['https://yallabus.app/bus_list/48'])
    """
    key = os.getenv('INDEXNOW_KEY')
    host = os.getenv('SITE_HOST', 'yallabus.app')
    
    if not key:
        logger.warning("[INDEXNOW] INDEXNOW_KEY not set, skipping")
        return False
    
    endpoint = "https://www.bing.com/indexnow"
    
    payload = {
        "host": host,
        "key": key,
        "keyLocation": f"https://{host}/{key}.txt",
        "urlList": url_list
    }
    
    try:
        response = requests.post(endpoint, json=payload, timeout=10)
        
        if response.status_code == 200:
            logger.info(f"[INDEXNOW] ✓ Success: {len(url_list)} URLs submitted")
            return True
        elif response.status_code == 202:
            logger.info(f"[INDEXNOW] ✓ Accepted: Key pending verification")
            return True
        else:
            logger.error(f"[INDEXNOW] ✗ Failed: {response.status_code} - {response.text}")
            return False
    except Exception as e:
        logger.error(f"[INDEXNOW] ✗ Exception: {e}")
        return False
