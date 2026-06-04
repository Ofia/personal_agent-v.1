import httpx


def run_local(prompt: str) -> str:
    r = httpx.post(                
        "http://localhost:11434/api/generate",   
        json={
            "model": "phi3:mini",     
            "prompt": prompt,      
            "stream": False        
        },
        timeout=3000                
    )
    return r.json()["response"]