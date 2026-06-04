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