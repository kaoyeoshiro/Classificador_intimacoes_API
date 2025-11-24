from pydantic import BaseModel
from typing import List, Optional, Dict, Any
from datetime import datetime

class Movimento(BaseModel):
    dataHora: Optional[datetime]
    descricao: str
    complemento: Optional[str] = None
    codigo: Optional[str] = None

class ProcessoData(BaseModel):
    numero: str
    competencia: Optional[str]
    classeProcessual: Optional[str]
    assuntos: List[str] = []
    movimentos: List[Movimento] = []
    xml_raw: Optional[str] = None # Store raw XML if needed

class ClassificacaoRequest(BaseModel):
    numero_processo: str
    # Optional: override model or prompt?

class ClassificacaoResult(BaseModel):
    numero_processo: str
    classe_processual: str
    classificacao: Dict[str, Any] # JSON result from AI
    data_classificacao: datetime = datetime.now()
