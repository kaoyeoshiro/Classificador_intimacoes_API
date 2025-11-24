from fastapi import APIRouter, HTTPException
from ..models import ClassificacaoResult
from ..services.ai_classifier import classify_process
from ..database import load_db, save_classification_result, load_classifications
import json
import os

router = APIRouter(prefix="/classify", tags=["classification"])

@router.post("/{numero_processo}", response_model=ClassificacaoResult)
def classify_process_endpoint(numero_processo: str):
    # 1. Get process data
    db = load_db()
    process_data = next((p for p in db if p.numero == numero_processo), None)
    
    if not process_data:
        raise HTTPException(status_code=404, detail="Processo não encontrado. Adicione-o primeiro.")
    
    # 2. Call AI
    try:
        result = classify_process(process_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na classificação: {str(e)}")
    
    # 3. Save result
    save_classification_result(result)
    
    return result

@router.get("/", response_model=list)
def list_classifications():
    return load_classifications()
