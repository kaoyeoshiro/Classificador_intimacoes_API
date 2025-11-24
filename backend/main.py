from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import processes, classification, export, prompts

app = FastAPI(title="Classificador de Intimações API")

# CORS
app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"], # Allow all for dev
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

app.include_router(processes.router)
app.include_router(classification.router)
app.include_router(export.router)
app.include_router(prompts.router)

from fastapi.staticfiles import StaticFiles
from fastapi.responses import FileResponse
import os

# Mount frontend directory
# Ensure absolute path or relative to where main.py is run
# Assuming running from project root or backend folder
# Let's try to find the frontend folder relative to this file
current_dir = os.path.dirname(os.path.abspath(__file__))
project_root = os.path.dirname(current_dir)
frontend_dir = os.path.join(project_root, "frontend")

app.mount("/static", StaticFiles(directory=frontend_dir), name="static")

@app.get("/")
def root():
    return FileResponse(os.path.join(frontend_dir, "index.html"))
