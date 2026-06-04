import chromadb                                        
from sentence_transformers import SentenceTransformer  
from pathlib import Path                               
import fitz                                            
from docx import Document as DocxDocument              
                                                       
import pandas as pd                                    
import pytesseract                                     
from PIL import Image                                  
import traceback                                       


MODEL = SentenceTransformer("all-MiniLM-L6-v2")

DB = chromadb.PersistentClient(path="./chroma_db")
collection = DB.get_or_create_collection("my_data")

def extract_txt(path: Path) -> str:
    return path.read_text(errors="ignore")

def extract_pdf(path: Path) -> str:
    doc = fitz.open(str(path))
    pages = [page.get_text() for page in doc]
    text = "\n" .join(pages)

    if len(text.strip()) < 100: 
        print(f' -> looks like a scanned PDF, trying OCR...')
        pages = []
        for page in doc:
            pix = page.get_pixmap(dpi=200)
            img = Image.frombytes("RGB", [pix.width, pix.height], pix.samples)
            pages.append(pytesseract.image_to_string(img))
        text = "\n".join(pages)

    return text

def extract_docx(path: Path) -> str:
    doc = DocxDocument(str(path))
    return "\n".join(
        p.text for p in doc.paragraphs
        if p.text.strip()                              # skip empty paragraphs
    )
