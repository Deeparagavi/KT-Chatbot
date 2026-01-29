# agents.py
import os
import json
from typing import Dict, Any
import threading
from concurrent.futures import ThreadPoolExecutor
from PIL import Image
import pytesseract
# optional openai
try:
    import openai
except Exception:
    openai = None

OPENAI_API_KEY = os.getenv('OPENAI_API_KEY')
OPENAI_MODEL = os.getenv('OPENAI_MODEL', 'gpt-4o-mini')
if openai and OPENAI_API_KEY:
    openai.api_key = OPENAI_API_KEY

class TextAgent:
    def __init__(self):
        pass

    def generate(self, prompt: str):
        """If OpenAI key present, returns a generator that yields token chunks as they arrive.
        Otherwise returns a synchronous dict with 'text'."""
        if openai and OPENAI_API_KEY:
            def gen():
                try:
                    response = openai.chat.completions.create(
                        model=OPENAI_MODEL,
                        messages=[{"role":"user","content": prompt}],
                        stream=True
                    )
                    for event in response:
                        # streaming events — depending on SDK, structure may differ
                        try:
                            if getattr(event, 'type', None) == 'response.delta':
                                delta = getattr(event, 'delta', {}) or {}
                                text = delta.get('content') or ''
                                if text:
                                    yield text
                            else:
                                # fallback: try parsing as dict
                                d = dict(event)
                                if 'delta' in d and isinstance(d['delta'], dict):
                                    t = d['delta'].get('content','')
                                    if t:
                                        yield t
                        except Exception:
                            continue
                except Exception as e:
                    yield f"[openai error] {str(e)}"
            return gen()
        else:
            return {"source": "local", "text": f"[local answer to] {prompt}"}

class ImageAgent:
    def __init__(self):
        pass
    def analyze_image(self, image_path: str):
        """
                Extracts text from the image using OCR and returns metadata.
                Stores a short description for RAG retrieval.
                """
        result = {"labels": [], "text": ""}
        try:
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img)
            result["text"] = text.strip()
            # Optional: add some simple labels (you can enhance later)
            if len(text.strip()) > 0:
                result["labels"].append("contains_text")
            else:
                result["labels"].append("image_only")
        except Exception as e:
            result["text"] = f"[OCR error] {str(e)}"
        return result

class ConfluenceAgent:
    def __init__(self):
        try:
            from atlassian import Confluence
        except Exception:
            Confluence = None
        self.base = os.getenv("CONFLUENCE_BASE_URL")
        self.user = os.getenv("CONFLUENCE_USERNAME")
        self.token = os.getenv("CONFLUENCE_TOKEN")
        if Confluence and self.base and self.user and self.token:
            self.client = Confluence(url=self.base, username=self.user, password=self.token)
        else:
            self.client = None
    def search(self, query: str, space_keys: str=None):
        if not self.client:
            return []
        cql = f'text ~ "{query}"'
        if space_keys:
            cql += f' and space = {space_keys}'
        results = self.client.cql(cql, expand='content')
        out = []
        for r in results.get('results', []):
            content = r.get('content', {})
            out.append({"title": content.get('title'), "id": content.get('id')})
        return out

class MasterOrchestrator:
    def __init__(self, multi_agent=False):
        self.text_agent = TextAgent()
        self.image_agent = ImageAgent()
        self.confluence_agent = ConfluenceAgent()
        self.multi = multi_agent

    def handle_query(self, payload: Dict[str, Any]):
        prompt = payload.get('text', '')
        images = payload.get('images', [])
        results = []
        if self.multi:
            with ThreadPoolExecutor() as ex:
                futures = []
                futures.append(ex.submit(self.text_agent.generate, prompt))
                if images:
                    for img in images:
                        futures.append(ex.submit(self.image_agent.analyze_image, img))
                futures.append(ex.submit(self.confluence_agent.search, prompt))
                for fut in futures:
                    try:
                        results.append(fut.result(timeout=30))
                    except Exception as e:
                        results.append({"error": str(e)})
        else:
            results.append(self.text_agent.generate(prompt))
        # Merge
        merged_texts = []
        sources = []
        for r in results:
            if isinstance(r, dict):
                merged_texts.append(r.get('text','') or json.dumps(r))
                sources.append(r.get('source','agent'))
            elif hasattr(r, '__iter__') and not isinstance(r, str):
                # streaming generator — collect into one string (non-streaming use)
                try:
                    collected = ''.join(list(r))
                    merged_texts.append(collected)
                except Exception:
                    merged_texts.append(str(r))
            else:
                merged_texts.append(str(r))
        merged = {"text": "\n".join([t for t in merged_texts if t]), "sources": sources}
        return merged
