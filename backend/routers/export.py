from fastapi import APIRouter, HTTPException, Response
from typing import List
from ..models import ProcessoData, ClassificacaoResult
from ..database import load_db, load_classifications
import json
import pandas as pd
from io import BytesIO
from datetime import datetime

router = APIRouter(prefix="/export", tags=["export"])

@router.get("/json")
def export_json():
    """
    Export all processes and their classifications to JSON.
    """
    processes = load_db()
    classifications = load_classifications()
    
    # Merge data
    data = []
    for p in processes:
        p_dict = p.model_dump(mode='json')
        # Remove raw XML to keep it clean
        if 'xml_raw' in p_dict:
            del p_dict['xml_raw']
            
        # Find classification
        cls = next((c for c in classifications if c['numero_processo'] == p.numero), None)
        if cls:
            p_dict['classificacao'] = cls['classificacao']
            p_dict['data_classificacao'] = cls['data_classificacao']
        data.append(p_dict)
        
    return data

@router.get("/excel")
def export_excel():
    """
    Export summary data to Excel.
    """
    processes = load_db()
    classifications = load_classifications()
    
    rows = []
    for p in processes:
        cls = next((c for c in classifications if c['numero_processo'] == p.numero), None)
        
        row = {
            "Número do Processo": p.numero,
            "Classe Processual": p.classeProcessual,
            "Código de Classificação": ""
        }
        
        if cls and 'classificacao' in cls:
            c_data = cls['classificacao']
            # Mapping 'tipo_intimacao' to 'Código de Classificação' as requested
            row["Código de Classificação"] = c_data.get('tipo_intimacao') or c_data.get('codigo', '')
            
        rows.append(row)
    
    df = pd.DataFrame(rows)
    
    output = BytesIO()
    with pd.ExcelWriter(output, engine='openpyxl') as writer:
        df.to_excel(writer, index=False, sheet_name='Processos')
        
    output.seek(0)
    
    headers = {
        'Content-Disposition': f'attachment; filename="processos_{datetime.now().strftime("%Y%m%d_%H%M%S")}.xlsx"'
    }
    
    return Response(content=output.getvalue(), media_type='application/vnd.openxmlformats-officedocument.spreadsheetml.sheet', headers=headers)
