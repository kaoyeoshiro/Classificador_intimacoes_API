import sys
import os
from pathlib import Path

# Add project root to path
sys.path.append(str(Path(__file__).resolve().parent.parent))

from backend.services.xml_parser import parse_processo_xml

def test_xml_parsing():
    xml_content = """<?xml version="1.0" encoding="UTF-8"?>
<processo>
    <dadosBasicos numero="5000000-00.2024.8.12.0001" classeProcessual="7" competencia="Cível">
        <assunto>
            <codigoNacional>999</codigoNacional>
        </assunto>
    </dadosBasicos>
    <movimento dataHora="20240101100000">
        <movimentoNacional codigoNacional="123" descricao="Movimento de Teste"/>
    </movimento>
    <movimento dataHora="20240102100000">
        <movimentoLocal codigoMovimento="456" descricao="Movimento Local"/>
        <complemento>Detalhe extra</complemento>
    </movimento>
</processo>
"""
    
    print("Parsing XML...")
    process_data = parse_processo_xml(xml_content)
    
    print(f"Numero: {process_data.numero}")
    assert process_data.numero == "5000000-00.2024.8.12.0001"
    
    print(f"Classe: {process_data.classeProcessual}")
    assert process_data.classeProcessual == "7"
    
    print(f"Movimentos: {len(process_data.movimentos)}")
    assert len(process_data.movimentos) == 2
    
    print(f"Movimento 1: {process_data.movimentos[0].descricao}")
    assert process_data.movimentos[0].descricao == "Movimento de Teste"
    
    print(f"Movimento 2: {process_data.movimentos[1].descricao} - {process_data.movimentos[1].complemento}")
    assert process_data.movimentos[1].descricao == "Movimento Local"
    assert process_data.movimentos[1].complemento == "Detalhe extra"
    
    print("XML Parsing verification passed!")

if __name__ == "__main__":
    test_xml_parsing()
