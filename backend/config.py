import os
from dotenv import load_dotenv

from pathlib import Path

env_path = Path(__file__).resolve().parent.parent / ".env"
load_dotenv(dotenv_path=env_path)

class Config:
    TJMS_USER = os.getenv("TJMS_USER", "PGEMS")
    TJMS_PASS = os.getenv("TJMS_PASS", "SAJ03PGEMS")
    TJMS_WSDL_URL = "https://esaj.tjms.jus.br/mniws/servico-intercomunicacao-2.2.2/intercomunicacao?wsdl"
    
    OPENROUTER_API_KEY = os.getenv("OPENROUTER_API_KEY")
    # Model ID requested by user. Ensure this model is available on OpenRouter.
    OPENROUTER_MODEL_ID = os.getenv("OPENROUTER_MODEL_ID", "google/gemini-2.0-pro-exp-02-05:free")
