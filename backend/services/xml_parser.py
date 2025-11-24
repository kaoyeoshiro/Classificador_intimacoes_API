import xml.etree.ElementTree as ET
from typing import Dict, Any, List, Optional
from datetime import datetime
import re
from ..models import ProcessoData, Movimento

def _parse_date(date_str: str) -> Optional[datetime]:
    if not date_str:
        return None
    try:
        # Format: YYYYMMDDHHMMSS
        return datetime.strptime(date_str, "%Y%m%d%H%M%S")
    except ValueError:
        try:
             # Format: YYYYMMDD
            return datetime.strptime(date_str, "%Y%m%d")
        except ValueError:
            return None

def parse_processo_xml(xml_content: str) -> ProcessoData:
    """
    Parses the TJ-MS XML response and extracts relevant process data.
    """
    root = ET.fromstring(xml_content)
    
    # Namespaces are often tricky in ElementTree with SOAP. 
    # We'll use a strategy to ignore namespaces or handle them if needed.
    # The sample XML uses ns2 for data.
    
    # Helper to find elements ignoring namespace
    def find_all(element, tag_name):
        return [e for e in element.iter() if e.tag.endswith(tag_name)]
    
    def find_first(element, tag_name):
        results = find_all(element, tag_name)
        return results[0] if results else None

    dados_basicos = find_first(root, 'dadosBasicos')
    
    numero = ""
    competencia = ""
    classe_processual = ""
    assuntos = []
    
    if dados_basicos is not None:
        numero = dados_basicos.get('numero', '')
        competencia = dados_basicos.get('competencia', '')
        classe_processual = dados_basicos.get('classeProcessual', '')
        
        for assunto in find_all(dados_basicos, 'assunto'):
            codigo = find_first(assunto, 'codigoNacional')
            if codigo is not None and codigo.text:
                assuntos.append(codigo.text)

    movimentos = []
    for mov in find_all(root, 'movimento'):
        data_hora_str = mov.get('dataHora')
        data_hora = _parse_date(data_hora_str)
        
        descricao = ""
        codigo_mov = ""
        
        # Try to find movimentoLocal or movimentoNacional
        mov_local = find_first(mov, 'movimentoLocal')
        if mov_local is not None:
            descricao = mov_local.get('descricao', '')
            codigo_mov = mov_local.get('codigoMovimento', '')
        else:
            mov_nac = find_first(mov, 'movimentoNacional')
            if mov_nac is not None:
                codigo_mov = mov_nac.get('codigoNacional', '')
                # Descricao might not be present for nacional, usually needs a lookup table, 
                # but let's check if there is a descricao attribute or child
                descricao = mov_nac.get('descricao', f"Movimento Nacional {codigo_mov}")

        complemento = None
        comp_elem = find_first(mov, 'complemento')
        if comp_elem is not None and comp_elem.text:
            complemento = comp_elem.text
            
        movimentos.append(Movimento(
            dataHora=data_hora,
            descricao=descricao,
            complemento=complemento,
            codigo=codigo_mov
        ))
    
    # Sort movements by date
    movimentos.sort(key=lambda x: x.dataHora if x.dataHora else datetime.min)

    return ProcessoData(
        numero=numero,
        competencia=competencia,
        classeProcessual=classe_processual,
        assuntos=assuntos,
        movimentos=movimentos,
        xml_raw=xml_content
    )
