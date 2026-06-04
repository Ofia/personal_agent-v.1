from fastapi import FastAPI
from tools.run_code import CodeInput, run_code
from tools.file_tools import ReadInput, WriteInput, read_file, write_file
from agent import run_agent
from pydantic import BaseModel
from local_model import run_local

app=FastAPI()

@app.get("/")
def root():
    return {"status": "agent online"}

@app.get("/ping")
def ping(name: str = "world"):
    return {"message": f'hello {name}'}

@app.post("/tool/run_code")
def tool_run_code(data: CodeInput):
    return run_code(data)


@app.post("/tool/read_file")
def tool_read_file(data: ReadInput):   
    return read_file(data)

@app.post("/tool/write_file")
def tool_write_file(data: WriteInput):
    return write_file(data)

class ChatInput(BaseModel):
    message: str

@app.post("/chat")
def chat(data: ChatInput):
    reply = run_agent(data.message)  
    return {"reply": reply}

@app.post("/chat/local")           
def chat_local(data: ChatInput):   
    reply = run_local(data.message)
    return {"reply": reply}


