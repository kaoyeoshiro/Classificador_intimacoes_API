from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from .routers import processes, classification, export, prompts, chat

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
app.include_router(chat.router)

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
    from fastapi.responses import FileResponse
    response = FileResponse(os.path.join(frontend_dir, "index.html"))
    # Disable caching for the HTML file to ensure users get the latest version
    response.headers["Cache-Control"] = "no-cache, no-store, must-revalidate"
    response.headers["Pragma"] = "no-cache"
    response.headers["Expires"] = "0"
    return response
