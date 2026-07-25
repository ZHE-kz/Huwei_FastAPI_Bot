import os
import time
from google.cloud import firestore
from google.oauth2 import service_account

# 全域變數快取
_local_cache = {}

# 取得目前檔案所在的絕對路徑
current_dir = os.path.dirname(os.path.abspath(__file__))
key_path = os.path.join(current_dir, "huwei agent.json")

if os.path.exists(key_path):
    # 直接使用 Google Cloud 官方憑證與服務帳戶連線 Firestore
    credentials = service_account.Credentials.from_service_account_file(key_path)
    sync_db = firestore.Client(credentials=credentials, project=credentials.project_id)
else:
    print("🚨 警告：找不到 huwei agent.json 憑證檔案！")
    sync_db = firestore.Client()

def get_db():
    return sync_db

def get_cached_collection(collection_name: str, ttl_seconds: int = 3600):
    now = time.time()
    if collection_name in _local_cache:
        cache_data, timestamp = _local_cache[collection_name]
        if now - timestamp < ttl_seconds:
            return cache_data

    db = get_db()
    docs = db.collection(collection_name).stream()
    
    data = []
    for doc in docs:
        doc_dict = doc.to_dict() or {}
        doc_dict['id'] = doc.id
        data.append(doc_dict)
    
    _local_cache[collection_name] = (data, now)
    return data

def force_clear_cache(collection_name: str = None):
    if collection_name and collection_name in _local_cache:
        del _local_cache[collection_name]
    else:
        _local_cache.clear()