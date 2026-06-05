# Agent Toolkit — Lego Build Guide v2
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

## ✅ Brick 1 — Hello FastAPI (DONE)

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

## ✅ Brick 2 — First Tool: Run Code (DONE)

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
        ["python", "-c", data.code],   # list = the command. "python -c" runs code passed as a string. data.code = the code field from input
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

## ✅ Brick 3 — Two More Tools: Read + Write Files (DONE)

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

## ✅ Brick 4 — The Agent Brain: /chat (DONE)

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
    },
    {
        "name": "search_knowledge",
        "description": "Search my personal knowledge base — notes, documents, memories",
        "input_schema": {
            "type": "object",
            "properties": {
                "query": {"type": "string"}        # what to search for
            },
            "required": ["query"]
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
        response = client.messages.create(    # .create() = the actual API call that reaches Claude over the internet
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

## 👉 Brick 5 — Local AI with Ollama 

**Concepts introduced:** calling a local HTTP API, swappable model backends

**What it does:** Adds a second brain — a model running entirely on your machine. No internet needed, no API cost. Use it for quick/cheap tasks, use Claude for complex reasoning. You pick per request.

```python
# local_model.py

import httpx                       # same HTTP client as before

def run_local(prompt: str) -> str:
    r = httpx.post(                # Ollama runs a local server on port 11434 — same idea as our FastAPI server
        "http://localhost:11434/api/generate",   # this is Ollama's endpoint, same pattern as our /chat
        json={
            "model": "llama3",     # which local model to use — must match what you pulled with ollama pull
            "prompt": prompt,      # the user's message
            "stream": False        # False = wait for the full response before returning. True = stream token by token
        },
        timeout=120                # local models are slow — give it 2 minutes before timing out
    )
    return r.json()["response"]    # Ollama returns {"response": "...", "done": true, ...}. we only want the text
```

```python
# main.py — add these lines

from local_model import run_local

@app.post("/chat/local")           # separate endpoint — /chat uses Claude, /chat/local uses Ollama
def chat_local(data: ChatInput):   # reuses the same ChatInput model (just a message: str field)
    reply = run_local(data.message)
    return {"reply": reply}
```

Make sure Ollama is running before you test:
```bash
ollama server       # starts the local Ollama server if it isn't already running
```

**Test in /docs:** POST `/chat/local` with `{"message": "say hello"}` — slower than Claude, but free and local.

---

## 🧱 Brick 6 — Feed It Your Data (ChromaDB) (IM HERE)

**Concepts introduced:** embeddings, vector database, chunking, multi-format file extraction

**What it does:** Turns your personal files into searchable memory for the agent. Handles PDFs, Word docs, Excel, CSV, images, and plain text — all in one script you run once.

First install the extra dependencies:
```bash
pip install pymupdf python-docx pandas pytesseract pillow
# pymupdf     = extract text from PDFs
# python-docx = extract text from Word documents
# pandas      = read Excel and CSV files
# pytesseract = OCR — extract text from images and scanned PDFs
# pillow      = open image files (pytesseract needs this)
```

For scanned PDFs and images, also install Tesseract OCR (it's a separate program, not a Python package):
https://github.com/UB-Mannheim/tesseract/wiki — download, install, add to PATH.
Skip this if you only have text-based PDFs and Word docs.

Organise your files before ingesting — subfolders help the agent know context:
```
my_data/
├── properties/
│   ├── apartment_contract.pdf
│   └── expenses.xlsx
├── finance/
│   └── bank_statements_2024.pdf
├── personal/
│   └── insurance_policies.pdf
└── notes/
    └── random_thoughts.md
```

```python
# ingest.py  ← run this once to load your data. not a FastAPI endpoint.

import chromadb                                        # chromadb = local vector database
from sentence_transformers import SentenceTransformer  # converts text → vectors (numbers)
from pathlib import Path                               # for working with file paths
import fitz                                            # pymupdf — extracts text from PDFs
from docx import Document as DocxDocument              # python-docx — extracts text from Word docs
                                                       # aliased as DocxDocument to avoid clash with other Document names
import pandas as pd                                    # pandas — reads CSV and Excel files
import pytesseract                                     # OCR — extracts text from images and scanned PDFs
from PIL import Image                                  # pillow — opens image files for pytesseract
import traceback                                       # built-in — prints full error details if a file fails

MODEL = SentenceTransformer("all-MiniLM-L6-v2")   # load the embedding model. runs locally. downloads once (~80MB)
                                                    # converts text → list of 384 numbers (a vector)

DB = chromadb.PersistentClient(path="./chroma_db") # PersistentClient = save data to disk (not just in memory)

# collection = named group of vectors — like a table in a database

# ── extractors — one function per file type ───────────────────────────────────

def extract_txt(path: Path) -> str:
    return path.read_text(errors="ignore")             # read plain text. errors="ignore" = skip unreadable characters

def extract_pdf(path: Path) -> str:
    doc = fitz.open(str(path))                         # fitz.open = open the PDF file
    pages = [page.get_text() for page in doc]          # list comprehension — call .get_text() on every page
    text = "\n".join(pages)                            # join all pages into one big string

    if len(text.strip()) < 100:                        # .strip() removes whitespace. if barely any text was found...
        print(f"  → looks like a scanned PDF, trying OCR...")   # it's probably a scan — use OCR instead
        pages = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)             # render the page as an image at 200 DPI (higher = better OCR)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)   # convert raw pixels to PIL image
            pages.append(pytesseract.image_to_string(img))   # OCR the image → returns extracted text as string
        text = "\n".join(pages)

    return text

def extract_docx(path: Path) -> str:            IM HERE!!
    doc = DocxDocument(str(path))                      # open the Word document
    return "\n".join(                                  # join all paragraphs into one string
        p.text for p in doc.paragraphs                 # iterate over every paragraph in the doc
        if p.text.strip()                              # skip empty paragraphs
    )

def extract_excel(path: Path) -> str:
    sheets = pd.read_excel(str(path), sheet_name=None) # sheet_name=None = read ALL sheets. returns dict {name: dataframe}
    parts = []
    for name, df in sheets.items():                    # .items() = iterate over key-value pairs in the dict
        parts.append(f"Sheet: {name}\n{df.to_string(index=False)}")   # to_string() = table as readable text. index=False = no row numbers
    return "\n\n".join(parts)                          # join sheets separated by a blank line

def extract_csv(path: Path) -> str:
    df = pd.read_csv(str(path))                        # read the CSV into a dataframe (a table structure)
    return df.to_string(index=False)                   # convert table to readable text, no row numbers

def extract_image(path: Path) -> str:
    img = Image.open(str(path))                        # PIL opens the image file
    return pytesseract.image_to_string(img)            # OCR → returns extracted text as a string

# ── router — maps file extensions to extractor functions ─────────────────────

EXTRACTORS = {                                         # dict = key: value pairs. extension → function
    ".txt":  extract_txt,
    ".md":   extract_txt,                              # markdown is plain text — same extractor works
    ".pdf":  extract_pdf,
    ".docx": extract_docx,
    ".xlsx": extract_excel,
    ".xls":  extract_excel,                            # old Excel format — same extractor works
    ".csv":  extract_csv,
    ".png":  extract_image,
    ".jpg":  extract_image,
    ".jpeg": extract_image,
}

def extract(path: Path) -> str | None:                 # str | None = returns either a string or None
    ext = path.suffix.lower()                          # .suffix = file extension including dot e.g. ".pdf". .lower() handles .PDF vs .pdf
    extractor = EXTRACTORS.get(ext)                    # .get() = look up the function. returns None if extension not in dict
    if not extractor:                                  # if no extractor found for this file type
        print(f"  → skipping {path.name} (unsupported type: {ext})")
        return None
    return extractor(path)                             # call whichever function matched and return its result

# ── chunker — splits text into overlapping pieces ────────────────────────────

def chunk_text(text: str, size: int = 400, overlap: int = 50) -> list[str]:
    words = text.split()                               # split by spaces into a list of words
    if not words:                                      # empty file — nothing to chunk
        return []
    chunks = []
    for i in range(0, len(words), size - overlap):     # range(start, stop, step). step = size minus overlap
        chunks.append(" ".join(words[i:i + size]))     # words[i:i+size] = slice. " ".join() = rejoin into string
    return chunks

# ── main ingestion loop ───────────────────────────────────────────────────────

def ingest_folder(folder: str):
    all_paths = [
        p for p in Path(folder).rglob("*")            # rglob("*") = every file at any depth in the folder
        if p.is_file()                                 # .is_file() = skip directories, only process actual files
    ]
    print(f"Found {len(all_paths)} files in {folder}\n")

    for path in all_paths:
        print(f"Processing: {path.name}")
        try:                                           # try/except = attempt this, catch any error so one bad file doesn't stop everything
            text = extract(path)                       # extract text using the right function for this file type

            if not text or len(text.strip()) < 50:     # skip files with almost no content (empty, broken, or image-only)
                print(f"  → skipping, not enough text\n")
                continue                              # continue = skip to the next file in the loop

            chunks = chunk_text(text)
            if not chunks:
                continue

            embeddings = MODEL.encode(chunks).tolist() # .encode() = convert list of strings → list of vectors
                                                       # .tolist() = convert numpy array to plain Python list

            relative = path.relative_to(folder)        # relative_to() = path relative to the root my_data folder
                                                       # e.g. properties/contract.pdf instead of ./my_data/properties/contract.pdf
            base_id = str(relative).replace("\\", "/").replace(" ", "_")   # normalize Windows backslashes and spaces in IDs

            collection.add(
                documents=chunks,                      # the original text chunks
                embeddings=embeddings,                 # their vector representations
                ids=[f"{base_id}_{i}" for i in range(len(chunks))]   # unique id per chunk e.g. properties/contract.pdf_0
            )
            print(f"  → {len(chunks)} chunks stored\n")

        except Exception as e:                         # Exception = catches any type of error
            print(f"  → failed: {e}")
            traceback.print_exc()                      # print the full error stack so you can debug it
            print()

    print("Done. All files processed.")

if __name__ == "__main__":         # only runs if you execute this file directly — not when imported
    ingest_folder("./my_data")
```

```bash
mkdir my_data                      # create the folder
# drop your files in my_data/ — subfolders are fine
python ingest.py                   # run it. creates ./chroma_db with your data
```

You'll see a log for every file. One bad file won't stop the rest.

---

## 🧱 Brick 7 — Agent Can Search Your Data

**Concepts introduced:** query embeddings, semantic search

**What it does:** Adds a search tool so the agent can look up your personal data when answering questions. The agent decides on its own when to use it — you don't have to tell it.

```python
# tools/search_knowledge.py

import chromadb
from sentence_transformers import SentenceTransformer
from pydantic import BaseModel

MODEL = SentenceTransformer("all-MiniLM-L6-v2")   # must be the same model used in ingest.py — vectors only match if the model matches
DB = chromadb.PersistentClient(path="./chroma_db") # open the same database that ingest.py created
collection = DB.get_or_create_collection("my_data")

class SearchInput(BaseModel):
    query: str                     # the search question in plain English
    n_results: int = 3             # how many chunks to return. default 3 — increase for broader context

def search_knowledge(data: SearchInput):
    embedding = MODEL.encode([data.query]).tolist()   # wrap query in a list — encode() expects a list of strings
                                                      # converts the question into a vector so we can compare it to stored vectors
    results = collection.query(                       # .query() = find stored vectors closest to our question vector
        query_embeddings=embedding,                   # the question vector to search with
        n_results=data.n_results                      # how many of the closest matches to return
    )
    return {"results": results["documents"][0]}       # results["documents"] = list of lists (one per query). [0] = our query's results
```

```python
# main.py — add these lines

from tools.search_knowledge import SearchInput, search_knowledge

@app.post("/tool/search_knowledge")
def tool_search(data: SearchInput):
    return search_knowledge(data)
```

The `search_knowledge` tool is already in the `TOOLS` list in `agent.py` from Brick 4 — nothing to change there.

**Test:** POST `/chat` with `{"message": "what do my notes say about [something in your documents]"}` — Claude will automatically call search_knowledge and use the results to answer.

---

## 🧱 Brick 8 — Telegram Bot

**Concepts introduced:** async/await, bot handlers, polling

**What it does:** Lets you message your agent from your phone via Telegram. No frontend needed — Telegram is your UI.

Get your bot token first: open Telegram, search `@BotFather`, send `/newbot`, follow the steps, copy the token into `.env`.

```python
# telegram_bot.py

import httpx                                           # to call our FastAPI server
from telegram import Update                            # Update = one incoming event from Telegram (a message, a button press, etc.)
from telegram.ext import (
    ApplicationBuilder,                                # builds and configures the bot application
    MessageHandler,                                    # handles a specific type of incoming event
    filters,                                           # used to filter which messages trigger which handler
    ContextTypes                                       # type hint for the context parameter (bot state, job queue, etc.)
)
from dotenv import load_dotenv
import os                                              # os = built-in module. lets us read environment variables

load_dotenv()
TOKEN = os.getenv("TELEGRAM_BOT_TOKEN")   # os.getenv() = read a value from the environment (loaded from .env by load_dotenv)

async def handle_message(update: Update, ctx: ContextTypes.DEFAULT_TYPE):
    # async = this function is asynchronous — it can pause and wait (await) without blocking other messages
    user_msg = update.message.text              # .message = the message object. .text = the text the user typed
    await update.message.reply_text("thinking...")   # await = pause here until Telegram confirms it was sent
                                                     # reply_text() = send a message back in the same chat

    r = httpx.post(                             # call our own FastAPI server — same as testing in /docs
        "http://localhost:8000/chat",
        json={"message": user_msg},
        timeout=120                             # agent can take a while if it uses multiple tools
    )
    reply = r.json().get("reply", "error")      # .get("reply", "error") = get the "reply" key, fall back to "error" if missing

    await update.message.reply_text(reply)      # send the agent's answer back to the user in Telegram

app = ApplicationBuilder().token(TOKEN).build()    # .token() = authenticate with Telegram using your bot token
                                                   # .build() = create the application object
app.add_handler(                                   # register a handler — tells the bot what to do when a message arrives
    MessageHandler(
        filters.TEXT & ~filters.COMMAND,           # TEXT = only handle text messages. ~ = NOT. COMMAND = /start /help etc.
        handle_message                             # the function to call when a matching message arrives
    )
)
app.run_polling()   # start the bot — continuously checks Telegram for new messages (polling = ask Telegram every few seconds)
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
├── my_data/                  ← Put your documents here (any subfolder structure)
└── chroma_db/                ← Auto-created by ChromaDB when you run ingest.py
```
