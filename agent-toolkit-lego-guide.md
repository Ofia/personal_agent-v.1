# Agent Toolkit — Lego Build Guide
> Every line of code has an inline comment explaining the syntax.

---

## Setup — Before Brick 1

```bash
mkdir agent-toolkit       # mkdir = make directory. Creates a folder called agent-toolkit
cd agent-toolkit          # cd = change directory. Move into that folder
python -m venv venv       # python -m = run a module. venv = the module. second venv = name of the folder it creates
source venv/Scripts/activate   # source = run this script in the current shell. activates the virtual environment
pip install fastapi uvicorn python-dotenv anthropic httpx chromadb sentence-transformers python-telegram-bot
# pip install = download and install packages. everything after is the list of packages separated by spaces
```

Create a file called `.env` in the project root:
```
ANTHROPIC_API_KEY=sk-ant-...    # your Claude API key — never commit this to git
TELEGRAM_BOT_TOKEN=...          # get this from @BotFather on Telegram
```

Install Ollama from https://ollama.com, then run:
```bash
ollama pull llama3    # pull = download the model. llama3 = the model name
```

---

## 🧱 Brick 1 — Hello FastAPI

**Concepts introduced:** `app`, decorators `@`, route functions, return JSON

```python
# main.py

from fastapi import FastAPI        # from X import Y = bring Y from the X package into this file

app = FastAPI()                    # FastAPI() = create the web application. app = variable holding it

@app.get("/")                      # @ = decorator. app.get = register a GET route. "/" = the URL path
def root():                        # def = define a function. root = its name. () = takes no parameters
    return {"status": "agent online"}   # return sends this dict back as JSON to whoever called the URL
                                        # {} = dict (key-value pairs). FastAPI auto-converts it to JSON

@app.get("/ping")                  # second route — registers GET /ping
def ping(name: str = "world"):     # name = parameter read from the URL. str = its type. "world" = default value
    return {"message": f"hello {name}"}   # f"..." = f-string. {name} inserts the value of name into the string
```

```bash
uvicorn main:app --reload
# uvicorn = the web server that runs FastAPI
# main:app = look in main.py, use the variable called app
# --reload = restart automatically when you save a file (dev mode)
```

Visit `http://localhost:8000/docs` — FastAPI auto-generates an interactive UI for all your endpoints.

---

## 🧱 Brick 2 — First Tool: Run Code

**Concepts introduced:** `BaseModel`, POST routes, `subprocess`

```python
# tools/run_code.py

import subprocess                  # subprocess = built-in Python module to run shell commands
from pydantic import BaseModel     # pydantic = data validation library. BaseModel = base class for input schemas

class CodeInput(BaseModel):        # class = define a new type. CodeInput = its name. BaseModel = it inherits validation from here
    code: str                      # code = field name. str = its type. FastAPI will enforce this — if missing, returns error
    language: str = "python"       # language = optional field. "python" = default value if not provided

def run_code(data: CodeInput):     # def = define function. data = the parameter. CodeInput = its expected type
    result = subprocess.run(       # subprocess.run = execute a command in the terminal
        ["python", "-c", data.code],   # list = the command. "python -c" runs code passed as a string. data.code = the code field from 
        capture_output=True,       # capture_output = grab stdout and stderr instead of printing them
        text=True,                 # text=True = return output as string, not bytes
        timeout=10                 # timeout = kill the process after 10 seconds (safety limit)
    )
    return {                       # return a dict — FastAPI sends it as JSON
        "stdout": result.stdout,   # stdout = what the code printed
        "stderr": result.stderr    # stderr = any error messages
    }
```

```python
# main.py — add these lines

from tools.run_code import CodeInput, run_code   # import the class and function from the file we just created

@app.post("/tool/run_code")        # POST = used when sending data (not just reading). "/tool/run_code" = URL path
def tool_run_code(data: CodeInput):    # data = FastAPI reads the JSON body and validates it against CodeInput
    return run_code(data)          # call our function and return its result as JSON
```

**Test in /docs:** POST `/tool/run_code` with `{"code": "print(2+2)"}` → should return `{"stdout": "4\n", "stderr": ""}`

---

## 🧱 Brick 3 — Two More Tools: Read + Write Files

**Concepts introduced:** `Path`, multiple models in one file

```python
# tools/file_tools.py

from pydantic import BaseModel     # same as before — for input validation
from pathlib import Path           # Path = modern way to work with file paths in Python

WORKSPACE = Path("./workspace")    # Path("./workspace") = a path object pointing to a folder called workspace
WORKSPACE.mkdir(exist_ok=True)     # .mkdir() = create the folder. exist_ok=True = don't error if it already exists

class ReadInput(BaseModel):        # separate model for the read endpoint
    path: str                      # path = the filename the agent wants to read

class WriteInput(BaseModel):       # separate model for the write endpoint
    path: str                      # path = where to write
    content: str                   # content = what to write

def read_file(data: ReadInput):
    p = WORKSPACE / data.path      # / = Path operator. joins paths. same as os.path.join(WORKSPACE, data.path)
    if not p.exists():             # .exists() = returns True if the file is on disk
        return {"error": "file not found"}   # early return with an error message
    return {"content": p.read_text()}        # .read_text() = open file, read it as a string, close it

def write_file(data: WriteInput):
    p = WORKSPACE / data.path      # build the full path
    p.write_text(data.content)     # .write_text() = create/overwrite file with this string
    return {"written": str(p)}     # str(p) = convert the Path object to a plain string for the response
```

```python
# main.py — add these lines

from tools.file_tools import ReadInput, WriteInput, read_file, write_file   # import everything we need

@app.post("/tool/read_file")
def tool_read_file(data: ReadInput):    # FastAPI reads JSON body, validates against ReadInput
    return read_file(data)

@app.post("/tool/write_file")
def tool_write_file(data: WriteInput):
    return write_file(data)
```

---

## 🧱 Brick 4 — The Agent Brain: /chat

**Concepts introduced:** Anthropic SDK, tool loop, conversation history

```python
# agent.py

import anthropic                   # the official Anthropic Python SDK
import httpx                       # httpx = HTTP client. lets us make requests to our own tool endpoints
import json                        # json = built-in module to convert between dicts and JSON strings
from dotenv import load_dotenv     # load_dotenv = reads .env file and puts the values into environment variables
load_dotenv()                      # call it immediately so the API key is available

client = anthropic.Anthropic()     # Anthropic() = create client. automatically reads ANTHROPIC_API_KEY from environment

TOOLS = [                          # list of tool definitions we give to Claude so it knows what tools exist
    {
        "name": "run_code",                        # name Claude will use to call this tool
        "description": "Run Python code and return the output",   # Claude reads this to decide when to use it
        "input_schema": {                          # JSON Schema — tells Claude what shape of input to send
            "type": "object",                      # the input is a JSON object (dict)
            "properties": {
                "code": {"type": "string"}         # one field called code, must be a string
            },
            "required": ["code"]                   # code is required — Claude must always include it
        }
    },
    {
        "name": "read_file",
        "description": "Read a file from the workspace",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"}
            },
            "required": ["path"]
        }
    },
    {
        "name": "write_file",
        "description": "Write content to a file in the workspace",
        "input_schema": {
            "type": "object",
            "properties": {
                "path": {"type": "string"},
                "content": {"type": "string"}
            },
            "required": ["path", "content"]
        }
    }
]

def call_tool(name: str, tool_input: dict) -> str:    # -> str = return type hint. this function returns a string
    r = httpx.post(                                    # httpx.post = make a POST request
        f"http://localhost:8000/tool/{name}",          # f-string builds the URL using the tool name
        json=tool_input                                # json= serializes the dict to JSON and sets Content-Type header
    )
    return json.dumps(r.json())    # r.json() = parse response as dict. json.dumps() = convert back to string for Claude

def run_agent(user_message: str) -> str:
    messages = [                               # list = conversation history. each item is one message
        {"role": "user", "content": user_message}   # role = who sent it. content = what they said
    ]

    while True:                                # while True = loop forever until we hit a return statement
        response = client.messages.create(    # .create() = send a request to Claude API
            model="claude-sonnet-4-20250514", # which model to use
            max_tokens=1024,                  # max tokens in the response
            tools=TOOLS,                      # pass our tool definitions so Claude can use them
            messages=messages                 # the full conversation history
        )

        if response.stop_reason == "end_turn":        # end_turn = Claude is done, has a final answer
            return response.content[0].text           # [0] = first content block. .text = the text inside it

        if response.stop_reason == "tool_use":        # tool_use = Claude wants to call one of our tools
            tool_block = next(                        # next() = get the first item from the iterator
                b for b in response.content           # iterate over content blocks
                if b.type == "tool_use"               # filter to only tool_use blocks
            )
            tool_result = call_tool(tool_block.name, tool_block.input)   # call the actual tool

            messages.append(                          # .append() = add item to end of list
                {"role": "assistant", "content": response.content}   # add Claude's response (with tool call) to history
            )
            messages.append({                         # add the tool result back as a user message (that's how the API works)
                "role": "user",
                "content": [{
                    "type": "tool_result",            # special type that pairs with a tool_use block
                    "tool_use_id": tool_block.id,     # must match the id of the tool_use block above
                    "content": tool_result            # the string result from our tool
                }]
            })
                                                      # loop continues — Claude will see the result and decide next step
```

```python
# main.py — add these lines

from agent import run_agent        # import the function we just wrote
from pydantic import BaseModel     # already imported above, but shown here for clarity

class ChatInput(BaseModel):
    message: str                   # the user's message

@app.post("/chat")
def chat(data: ChatInput):
    reply = run_agent(data.message)   # run the full agent loop
    return {"reply": reply}
```

**Test:** POST `/chat` with `{"message": "write a file called hello.txt with the text hello world, then read it back"}`

---

## 🧱 Brick 5 — Local AI with Ollama - IM HERE!!!!

**Concepts introduced:** calling a local HTTP API, swappable model backends

```python
# local_model.py

import httpx                       # same HTTP client as before

def run_local(prompt: str) -> str:
    r = httpx.post(                # Ollama runs a local server on port 11434
        "http://localhost:11434/api/generate",
        json={
            "model": "llama3",     # which local model to use (must be pulled first with ollama pull llama3)
            "prompt": prompt,      # the user's message
            "stream": False        # False = wait for full response. True = stream token by token
        },
        timeout=120                # local models are slow — give it 2 minutes
    )
    return r.json()["response"]    # Ollama returns {"response": "...", ...}. we only want the text
```

```python
# main.py — add these lines

from local_model import run_local

@app.post("/chat/local")           # separate endpoint — /chat uses Claude, /chat/local uses Ollama
def chat_local(data: ChatInput):   # reuses the same ChatInput model (just a message field)
    reply = run_local(data.message)
    return {"reply": reply}
```

---

## 🧱 Brick 6 — Feed It Your Data (ChromaDB)

**Concepts introduced:** embeddings, vector database, chunking

Run this file once to load your documents. Not a FastAPI endpoint.

```python
# ingest.py

import chromadb                                        # chromadb = local vector database
from sentence_transformers import SentenceTransformer  # library that converts text to embeddings (vectors)
from pathlib import Path                               # for working with file paths

MODEL = SentenceTransformer("all-MiniLM-L6-v2")   # load the embedding model. runs locally. downloads once (~80MB)
                                                    # this model converts text → list of 384 numbers (a vector)

DB = chromadb.PersistentClient(path="./chroma_db") # PersistentClient = save data to disk at this path
collection = DB.get_or_create_collection("my_data")# collection = a named group of vectors (like a table)

def chunk_text(text: str, size: int = 400, overlap: int = 50):
    # split text into overlapping chunks so context isn't lost at boundaries
    words = text.split()           # .split() = split string by spaces into a list of words
    chunks = []                    # empty list to hold our chunks
    for i in range(0, len(words), size - overlap):   # range(start, stop, step) — step = size minus overlap
        chunks.append(             # add each chunk to the list
            " ".join(words[i:i+size])   # words[i:i+size] = slice the list. " ".join() = rejoin words into a string
        )
    return chunks                  # return the list of text chunks

def ingest_folder(folder: str):
    for path in Path(folder).rglob("*.txt"):   # .rglob() = recursively find all files matching pattern
        text = path.read_text(errors="ignore") # read the file. errors="ignore" = skip unreadable characters
        chunks = chunk_text(text)              # split into chunks
        embeddings = MODEL.encode(chunks).tolist()   # .encode() = convert list of strings → list of vectors
                                                     # .tolist() = convert numpy array to plain Python list
        collection.add(                        # store everything in ChromaDB
            documents=chunks,                  # the original text chunks
            embeddings=embeddings,             # their vector representations
            ids=[f"{path.stem}_{i}" for i in range(len(chunks))]   # unique id per chunk. path.stem = filename without extension
        )
        print(f"Ingested {path} → {len(chunks)} chunks")   # progress log

if __name__ == "__main__":         # __name__ == "__main__" = only run this if the file is executed directly (not imported)
    ingest_folder("./my_data")     # point it at your folder of .txt or .md files
```

```bash
mkdir my_data                # create the folder
# drop your .txt or .md files in ./my_data
python ingest.py             # run it once. creates ./chroma_db folder with your data
```

---

## 🧱 Brick 7 — Agent Can Search Your Data

**Concepts introduced:** query embeddings, semantic search

```python
# tools/search_knowledge.py

import chromadb
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel

MODEL = SentenceTransformer("all-MiniLM-L6-v2")   # same model as ingest.py — must match!
DB = chromadb.PersistentClient(path="./chroma_db") # open the same database
collection = DB.get_or_create_collection("my_data")

class SearchInput(BaseModel):
    query: str                     # the search question
    n_results: int = 3             # how many chunks to return. default 3

def search_knowledge(data: SearchInput):
    embedding = MODEL.encode([data.query]).tolist()   # [data.query] = wrap in list because encode() expects a list
                                                      # converts the question to a vector
    results = collection.query(    # .query() = find the closest vectors in the database
        query_embeddings=embedding,# the question vector to search with
        n_results=data.n_results   # how many results to return
    )
    return {"results": results["documents"][0]}   # results["documents"] = list of lists. [0] = first query's results
```

```python
# main.py — add these lines

from tools.search_knowledge import SearchInput, search_knowledge

@app.post("/tool/search_knowledge")
def tool_search(data: SearchInput):
    return search_knowledge(data)
```

Add to `TOOLS` list in `agent.py`:
```python
{
    "name": "search_knowledge",
    "description": "Search my personal knowledge base — notes, documents, memories",
    "input_schema": {
        "type": "object",
        "properties": {
            "query": {"type": "string"}   # what to search for
        },
        "required": ["query"]
    }
}
```

---

## 🧱 Brick 8 — Telegram Bot

**Concepts introduced:** async/await, bot handlers, polling

```python
# telegram_bot.py

import httpx                                           # to call our FastAPI server
from telegram import Update                            # Update = a message event from Telegram
from telegram.ext import (
    ApplicationBuilder,                                # builds the bot application
    MessageHandler,                                    # handles incoming messages
    filters,                                           # used to filter which messages to handle
    ContextTypes                                       # type hint for the context parameter
)
from dotenv import load_dotenv
import os                                              # os = built-in module. lets us read environment variables

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")   # os.getenv() = read a value from environment variables (set in .env)

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # async = this function can pause and wait without blocking other code
    user_msg = update.message.text         # .message.text = the text the user sent in Telegram
    await update.message.reply_text("thinking...")   # await = pause here until Telegram confirms message sent
                                                     # reply_text() = send a message back in the same chat

    r = httpx.post(                        # call our own FastAPI server
        "http://localhost:8000/chat",
        json={"message": user_msg}
    )
    reply = r.json().get("reply", "error")   # .get("reply", "error") = get "reply" key, use "error" if missing

    await update.message.reply_text(reply) # send the agent's reply back to Telegram

app = ApplicationBuilder().token(TOKEN).build()   # .token() = authenticate with Telegram. .build() = create the app
app.add_handler(                                  # register a handler for incoming messages
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,          # TEXT = only text messages. ~ = NOT. COMMAND = /start etc.
        handle_message                            # which function to call when a message arrives
    )
)
app.run_polling()   # start the bot — checks Telegram for new messages every few seconds
```

```bash
# Terminal 1 — keep FastAPI running
uvicorn main:app --reload

# Terminal 2 — run the bot
python telegram_bot.py
```

Message your bot on Telegram — it routes through your full agent stack.

---

## Final File Structure

```
agent-toolkit/
├── main.py                   ← FastAPI app — all routes live here
├── agent.py                  ← Agent loop — calls Claude + routes tool calls
├── local_model.py            ← Ollama wrapper for local AI
├── ingest.py                 ← Run once to load your documents into ChromaDB
├── telegram_bot.py           ← Telegram interface
├── .env                      ← API keys — never commit to git
├── tools/
│   ├── run_code.py           ← Tool: execute Python
│   ├── file_tools.py         ← Tool: read + write files
│   └── search_knowledge.py   ← Tool: search your data
├── workspace/                ← Auto-created. Agent's file sandbox
├── my_data/                  ← Put your .txt / .md documents here
└── chroma_db/                ← Auto-created by ChromaDB when you run ingest.py
```
