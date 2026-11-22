# Agent Toolkit

A minimal AI agent built from scratch — tools, the agent loop, and document ingestion — wired
together behind a FastAPI server.

Built to understand how agents actually work underneath the frameworks, by assembling the pieces
one at a time rather than importing them.

## What it does

The agent can run code, read and write files, and answer from documents you've ingested. Each
capability is exposed two ways: as its own HTTP endpoint you can call directly, and as a tool the
agent can choose to invoke on its own during a conversation.

```
POST /chat              talk to the agent (it picks tools as needed)
POST /chat/local        same, against a locally-run model instead of an API
POST /tool/run_code     execute code
POST /tool/read_file    read a file
POST /tool/write_file   write a file
GET  /ping              health check
```

Having both surfaces is the point: you can test a tool in isolation, then watch the agent decide
to call that same tool on its own.

## Layout

```
agent-toolkit/
  main.py          FastAPI server — the HTTP surface
  agent.py         the agent loop: prompt -> tool choice -> execute -> respond
  ingest.py        document ingestion for retrieval
  local_model.py   run against a local model instead of a hosted API
  tools/
    run_code.py    code execution
    file_tools.py  read / write
  workspace/       where the agent does its work
```

## Running it

```bash
cd agent-toolkit
pip install fastapi uvicorn pydantic
uvicorn main:app --reload
```

Then:

```bash
curl -X POST localhost:8000/chat \
  -H "Content-Type: application/json" \
  -d '{"message": "read notes.txt and summarise it"}'
```

## Local vs hosted models

`/chat` runs against a hosted API; `/chat/local` runs the same loop against a model on your own
machine. Same agent, same tools, swappable backend — which makes the cost and latency difference
between the two directly comparable.

## Build notes

Written up step by step in [`agent-toolkit-lego-guide.md`](agent-toolkit-lego-guide.md) and
[`agent-toolkit-lego-guide-v2.md`](agent-toolkit-lego-guide-v2.md) — each piece explained as it
was added, in the order it was added.

## Status

Version 1, and a learning build rather than a production service. There's no auth on the
endpoints and `run_code` executes what it's given — run it locally, not on an open port.
