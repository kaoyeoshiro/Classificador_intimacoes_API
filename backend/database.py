import json
import os
from typing import List, Dict, Any
from .models import ProcessoData, ClassificacaoResult

DB_FILE = "processes.json"
CLASSIFICATIONS_FILE = "classifications.json"

def load_db() -> List[ProcessoData]:
    if not os.path.exists(DB_FILE):
        return []
    try:
        with open(DB_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [ProcessoData(**d) for d in data]
    except Exception:
        return []

def save_db(processes: List[ProcessoData]):
    with open(DB_FILE, "w", encoding="utf-8") as f:
        json.dump([p.model_dump(mode='json') for p in processes], f, indent=2, ensure_ascii=False)

def load_classifications() -> List[Dict[str, Any]]:
    if not os.path.exists(CLASSIFICATIONS_FILE):
        return []
    try:
        with open(CLASSIFICATIONS_FILE, "r", encoding="utf-8") as f:
            return json.load(f)
    except:
        return []

def save_classification_result(result: ClassificacaoResult):
    data = load_classifications()
    # Remove existing classification for this process if exists (replace)
    data = [c for c in data if c['numero_processo'] != result.numero_processo]
    
    data.append(result.model_dump(mode='json'))
    with open(CLASSIFICATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)

def delete_process(numero: str):
    processes = load_db()
    processes = [p for p in processes if p.numero != numero]
    save_db(processes)

def delete_classification(numero: str):
    data = load_classifications()
    data = [c for c in data if c['numero_processo'] != numero]
    with open(CLASSIFICATIONS_FILE, "w", encoding="utf-8") as f:
        json.dump(data, f, indent=2, ensure_ascii=False)
