# confluence_sync.py
import os
from rag_store import RAGStore, store
try:
    from atlassian import Confluence
except Exception:
    Confluence = None

def sync_all():
    base = os.getenv('CONFLUENCE_BASE_URL')
    user = os.getenv('CONFLUENCE_USERNAME')
    token = os.getenv('CONFLUENCE_TOKEN')
    if not base or not user or not token or Confluence is None:
        print('Confluence not configured or atlassian lib missing')
        return
    c = Confluence(url=base, username=user, password=token)
    space_keys = os.getenv('CONFLUENCE_SPACE_KEYS', '')
    for space in space_keys.split(','):
        start = 0
        limit = 50
        while True:
            res = c.get_all_pages_from_space(space=space.strip(), start=start, limit=limit)
            if not res:
                break
            docs = []
            for page in res:
                text = page.get('body', {}).get('storage', {}).get('value', '') or ''
                meta = {"title": page.get('title'), "id": page.get('id'), "space": space}
                docs.append((text, meta))
            store.add_documents(docs)
            if len(res) < limit:
                break
            start += limit
    print('Confluence sync complete')

if __name__ == '__main__':
    sync_all()
