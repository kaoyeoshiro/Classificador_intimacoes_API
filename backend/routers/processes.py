from fastapi import APIRouter, HTTPException, BackgroundTasks, UploadFile, File
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

    # Sort by classification date (most recent first)
    # Processes with classification come first, sorted by date descending
    # Processes without classification come after
    result.sort(key=lambda x: (
        x.get('data_classificacao') is not None,  # True (classified) comes after False (not classified) if reverse=True? No.
        # Let's be explicit:
        # We want: Classified (Newest -> Oldest) -> Unclassified
        # Tuple comparison: (is_classified, date)
        # (1, "2023-10-27") > (1, "2023-10-26") > (0, "")
        # So reverse=True works.
        x.get('data_classificacao') is not None,
        x.get('data_classificacao', '')
    ), reverse=True)

    return result

@router.post("/upload", response_model=List[ProcessoData])
async def upload_processes(files: List[UploadFile] = File(...)):
    uploaded_processes = []
    db = load_db()
    
    for file in files:
        try:
            content = await file.read()
            xml_content = content.decode('utf-8')
            process_data = parse_processo_xml(xml_content)
            
            # Check for duplicates
            existing_process = next((p for p in db if p.numero == process_data.numero), None)
            if existing_process:
                # Check if classified
                classifications = load_classifications()
                is_classified = any(c['numero_processo'] == process_data.numero for c in classifications)
                
                if is_classified:
                    if existing_process.xml_raw == process_data.xml_raw:
                        print(f"Skipping {process_data.numero}: Already classified and identical.")
                        continue # Skip this file
                    else:
                        # Content changed, remove old classification to re-analyze
                        from ..database import delete_classification
                        delete_classification(process_data.numero)

            # Remove existing if any
            db = [p for p in db if p.numero != process_data.numero]
            db.append(process_data)
            uploaded_processes.append(process_data)
        except Exception as e:
            print(f"Error parsing file {file.filename}: {e}")
            continue
            
    save_db(db)
    return uploaded_processes

@router.delete("/{numero_processo}")
def delete_process_endpoint(numero_processo: str):
    from ..database import delete_process, delete_classification
    delete_process(numero_processo)
    delete_classification(numero_processo)
    return {"message": "Processo excluído com sucesso"}

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
    
    # 3. Check for duplicates
    db = load_db()
    existing_process = next((p for p in db if p.numero == process_data.numero), None)
    
    if existing_process:
        # Check if classified
        classifications = load_classifications()
        is_classified = any(c['numero_processo'] == process_data.numero for c in classifications)
        
        if is_classified:
            if existing_process.xml_raw == process_data.xml_raw:
                raise HTTPException(status_code=409, detail="Processo já classificado com esta mesma intimação.")
            else:
                # Content changed, remove old classification to re-analyze
                from ..database import delete_classification
                delete_classification(process_data.numero)

    # 4. Save to DB
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
