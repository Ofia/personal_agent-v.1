import subprocess
from pydantic import BaseModel

class CodeInput(BaseModel):
    code:str
    language: str = "python"

def run_code(data: CodeInput):
    result = subprocess.run(
        ["python", "-c", data.code],
        capture_output=True,
        text=True,
        timeout=10
    )
    return {
        "stdout": result.stdout,
        "stderr":result.stderr
    }