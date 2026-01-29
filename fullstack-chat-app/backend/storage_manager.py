import os
from pathlib import Path
from urllib.parse import quote_plus
try:
    from azure.storage.blob import BlobServiceClient
except Exception:
    BlobServiceClient = None

STORAGE_BACKEND = os.getenv("STORAGE_BACKEND","local")
AZURE_CONN = os.getenv("AZURE_STORAGE_CONNECTION_STRING","")
AZURE_CONTAINER = os.getenv("AZURE_CONTAINER_NAME","chatbot")

class StorageManager:
    def __init__(self, upload_dir: str = "./uploads"):
        self.upload_dir = Path(upload_dir)
        self.upload_dir.mkdir(parents=True, exist_ok=True)
        self.backend = STORAGE_BACKEND
        self.azure_client = None
        if self.backend and self.backend.startswith("azure") and BlobServiceClient and AZURE_CONN:
            try:
                self.azure_client = BlobServiceClient.from_connection_string(AZURE_CONN)
                try:
                    self.azure_client.create_container(AZURE_CONTAINER)
                except Exception:
                    pass
            except Exception as e:
                print("Azure init error:", e)
                self.azure_client = None

    def save_file(self, local_path: Path):
        if self.azure_client:
            try:
                container_client = self.azure_client.get_container_client(AZURE_CONTAINER)
                blob_name = local_path.name
                with open(local_path, "rb") as data:
                    container_client.upload_blob(name=blob_name, data=data, overwrite=True)
                return f"https://{self.azure_client.account_name}.blob.core.windows.net/{AZURE_CONTAINER}/{quote_plus(blob_name)}"
            except Exception as e:
                print("Azure upload failed:", e)
                return str(local_path)
        return str(local_path)

    def get_file(self, filename: str, dest: str = None):
        dest = dest or str(self.upload_dir / filename)
        if self.azure_client:
            try:
                container_client = self.azure_client.get_container_client(AZURE_CONTAINER)
                blob_client = container_client.get_blob_client(filename)
                with open(dest, "wb") as f:
                    stream = blob_client.download_blob()
                    f.write(stream.readall())
                return dest
            except Exception:
                return None
        p = self.upload_dir / filename
        return str(p) if p.exists() else None
