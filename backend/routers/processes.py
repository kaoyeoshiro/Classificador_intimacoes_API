from fastapi import APIRouter, HTTPException, BackgroundTasks
from typing import List, Dict, Any
from ..models import ProcessoData
from ..services.tjms_client import soap_consultar_processo
from ..services.xml_parser import parse_processo_xml
from ..database import load_db, save_db, load_classifications
import json
import os

router = APIRouter(prefix="/processes", tags=["processes"])

@router.get("/", response_model=List[Dict[str, Any]])
def list_processes():
    processes = load_db()
    classifications = load_classifications()
    
    result = []
    for p in processes:
        p_dict = p.model_dump(mode='json')
        # Find classification
        cls = next((c for c in classifications if c['numero_processo'] == p.numero), None)
        if cls:
            p_dict['classificacao'] = cls['classificacao']
            p_dict['data_classificacao'] = cls['data_classificacao']
        result.append(p_dict)
        
    return result

@router.post("/{numero_processo}", response_model=ProcessoData)
def add_process(numero_processo: str):
    # 1. Fetch XML
    try:
        xml_content = soap_consultar_processo(numero_processo)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao consultar TJ-MS: {str(e)}")
    
    # 2. Parse XML
    try:
        process_data = parse_processo_xml(xml_content)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao processar XML: {str(e)}")
    
    # 3. Save to DB
    db = load_db()
    # Remove existing if any
    db = [p for p in db if p.numero != process_data.numero]
    db.append(process_data)
    save_db(db)
    
    return process_data

@router.get("/{numero_processo}", response_model=Dict[str, Any])
def get_process(numero_processo: str):
    db = load_db()
    process = next((p for p in db if p.numero == numero_processo), None)
    
    if not process:
        raise HTTPException(status_code=404, detail="Processo não encontrado")
        
    p_dict = process.model_dump(mode='json')
    
    # Add classification if exists
    classifications = load_classifications()
    cls = next((c for c in classifications if c['numero_processo'] == numero_processo), None)
    if cls:
        p_dict['classificacao'] = cls['classificacao']
        p_dict['data_classificacao'] = cls['data_classificacao']
        
    return p_dict
