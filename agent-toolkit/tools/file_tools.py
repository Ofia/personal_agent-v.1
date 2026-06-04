from pydantic import BaseModel
from pathlib import Path

WORKSPACE = Path("./workspace")
WORKSPACE.mkdir(exist_ok=True)

class ReadInput(BaseModel):
    path: str

class WriteInput(BaseModel):
    path: str
    content: str

def read_file(data: ReadInput):
    p = WORKSPACE /data.path
    if not p.exists():
        return {"error": "file not found"}
    return {"content": p.read_text()}

def write_file(data: WriteInput):
    p = WORKSPACE / data.path      
    p.write_text(data.content)     
    return {"written": str(p)}