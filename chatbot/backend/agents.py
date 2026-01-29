class TextAgent:
    def generate(self, query, context=""):
        return f"TextAgent answer for '{query}'"

class ImageAgent:
    def analyze_image(self, path):
        return {"text":"OCR detected text"}
    def generate(self, query):
        return "ImageAgent generated content"

class ConfluenceAgent:
    def search(self, query):
        return "ConfluenceAgent content"

class MasterAgent:
    def __init__(self, agents):
        self.agents = agents
    def generate(self, query, context=""):
        outputs = [a.generate(query, context) if hasattr(a,"generate") else a.search(query) for a in self.agents]
        return "\\n".join(outputs)
