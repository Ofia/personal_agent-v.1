import anthropic                   
import httpx                       
import json                        
from dotenv import load_dotenv     
load_dotenv()

client = anthropic.Anthropic()

TOOLS = [                         
    {
        "name": "run_code",                        
        "description": "Run Python code and return the output",   
        "input_schema": {                          
            "type": "object",                      
            "properties": {
                "code": {"type": "string"}         
            },
            "required": ["code"]                   
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

def call_tool(name: str, tool_input: dict) -> str:   
    r = httpx.post(                                    
        f"http://localhost:8000/tool/{name}",          
        json=tool_input                                
    )
    return json.dumps(r.json())

def run_agent(user_message: str) -> str:
    messages = [                               
        {"role": "user", "content": user_message}   
    ]

    while True:                                
        response = client.messages.create(    
            model="claude-sonnet-4-20250514", 
            max_tokens=1024,                  
            tools=TOOLS,                      
            messages=messages                 
        )

        if response.stop_reason == "end_turn":        
            return response.content[0].text           

        if response.stop_reason == "tool_use":        
            tool_block = next(                        
                b for b in response.content           
                if b.type == "tool_use"               
            )
            tool_result = call_tool(tool_block.name, tool_block.input)   

            messages.append(                          
                {"role": "assistant", "content": response.content}   
            )
            messages.append({                         
                "role": "user",
                "content": [{
                    "type": "tool_result",            
                    "tool_use_id": tool_block.id,     
                    "content": tool_result            
                }]
            })