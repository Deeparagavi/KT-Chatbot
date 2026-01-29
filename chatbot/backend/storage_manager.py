import os
from pathlib import Path
try:
    from azure.storage.blob import BlobServiceClient
except ImportError:
    pass

class StorageManager:
    def __init__(self, backend="local"):
        self.backend = backend
        if backend=="azure":
            conn_str = os.getenv("AZURE_STORAGE_CONNECTION_STRING")
            container = os.getenv("AZURE_CONTAINER_NAME","chatbot")
            self.client = BlobServiceClient.from_connection_string(conn_str)
            self.container_client = self.client.get_container_client(container)

    def save_file(self, local_path: Path):
        if self.backend=="local":
            return str(local_path)
        elif self.backend=="azure":
            blob_name = local_path.name
            with open(local_path,"rb") as f:
                self.container_client.upload_blob(name=blob_name,data=f,overwrite=True)
            return f"azure://{self.container_client.container_name}/{blob_name}"

    def get_file(self, filename: str):
        if self.backend=="local":
            p = Path("./uploads") / filename
            return p if p.exists() else None
        elif self.backend=="azure":
            blob_client = self.container_client.get_blob_client(filename)
            return blob_client.download_blob().readall()
