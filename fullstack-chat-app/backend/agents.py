
import os, json
from typing import Dict, Any, List
from PIL import Image
import pytesseract

try:
    import openai
except Exception:
    openai = None

OPENAI_API_KEY = os.getenv("OPENAI_API_KEY","")
OPENAI_MODEL = os.getenv("OPENAI_MODEL","gpt-4o-mini")
print("openai")
print(openai)
print(OPENAI_API_KEY)
if openai and OPENAI_API_KEY:
    print("OpenAI API KEY {}".format(OPENAI_API_KEY))
    openai.api_key = OPENAI_API_KEY

class TextAgent:
    def __init__(self):
        pass
    def generate(self, prompt: str, context: str=""):
        full = context + "\n\nUser: " + prompt
        if openai and OPENAI_API_KEY:
            try:
                resp = openai.chat.completions.create(model=OPENAI_MODEL, messages=[{"role":"user","content":full}])
                try:
                    print("Answer3 : {}".format(resp.choices[0].message.content))
                    return resp.choices[0].message.content
                except Exception:
                    print("Answer4 : {}".format(resp['choices'][0]['message']['content'] if isinstance(resp, dict) else str(resp)))
                    return resp['choices'][0]['message']['content'] if isinstance(resp, dict) else str(resp)
            except Exception as e:
                print("Answer5 : {}".format(e))
                return f"[openai error] {e}"
        print("Answer6 : {}".format(prompt))
        return f"[local answer] {prompt}"

class ImageAgent:
    def __init__(self):
        pass
    def analyze_image(self, image_path: str) -> Dict[str, Any]:
        res = {"labels": [], "text": ""}
        try:
            img = Image.open(image_path)
            text = pytesseract.image_to_string(img)
            res["text"] = text.strip()
            if res["text"]:
                res["labels"].append("contains_text")
            else:
                res["labels"].append("image_only")
        except Exception as e:
            res["text"] = f"[ocr error] {str(e)}"
        return res

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
            out.append({"title": content.get("title"), "id": content.get("id")})
        return out

class MasterAgent:
    def __init__(self, agents: List[Any]):
        self.agents = agents
    def generate(self, prompt: str, context: str=""):
        parts = []
        for a in self.agents:
            if hasattr(a, "generate"):
                try:
                    parts.append(a.generate(prompt, context))
                except Exception:
                    parts.append("")
            elif hasattr(a, "search"):
                try:
                    parts.append(str(a.search(prompt)))
                except Exception:
                    parts.append("")
        return "\n\n".join([p for p in parts if p])
