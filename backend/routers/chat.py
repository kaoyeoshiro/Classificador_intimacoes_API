from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
from ..database import load_db, load_classifications
from ..services.ai_classifier import get_client
from ..routers.prompts import load_prompts
from ..config import Config

router = APIRouter(prefix="/chat", tags=["chat"])

class ChatMessage(BaseModel):
    role: str  # "user" or "assistant"
    content: str

class ChatRequest(BaseModel):
    message: str
    history: List[ChatMessage] = []

class ChatResponse(BaseModel):
    response: str

CHAT_SYSTEM_PROMPT = """
Você é um assistente jurídico especializado que está ajudando o usuário a entender uma classificação de intimação processual que você fez anteriormente.

Seu objetivo é:
1. Explicar de forma clara por que você classificou o processo de determinada maneira
2. Responder às dúvidas do usuário sobre a classificação
3. Ajudar o usuário a melhorar os prompts de classificação, se ele estiver fornecendo feedback

Seja cordial, claro e técnico. Se o usuário sugerir melhorias ou apontar erros na classificação, agradeça o feedback e explique como as sugestões dele podem melhorar o prompt.
"""

@router.post("/{numero_processo}", response_model=ChatResponse)
async def chat_about_process(numero_processo: str, request: ChatRequest):
    """
    Endpoint para conversar com a IA sobre um processo classificado.
    Envia todo o contexto necessário: dados do processo, classificação atual, 
    prompt usado e histórico da conversa.
    """
    
    # 1. Verificar se o processo existe
    db = load_db()
    process_data = next((p for p in db if p.numero == numero_processo), None)
    
    if not process_data:
        raise HTTPException(status_code=404, detail="Processo não encontrado.")
    
    # 2. Verificar se o processo foi classificado
    classifications = load_classifications()
    classification = next((c for c in classifications if c['numero_processo'] == numero_processo), None)
    
    if not classification:
        raise HTTPException(
            status_code=400, 
            detail="Este processo ainda não foi classificado. Classifique-o primeiro antes de iniciar uma conversa."
        )
    
    # 3. Buscar o prompt que foi usado na classificação
    prompts = load_prompts()
    class_code = process_data.classeProcessual
    prompt_used = None
    
    for p in prompts:
        if class_code in p.classes:
            prompt_used = p.content
            break
    
    if not prompt_used:
        prompt_used = "Nenhum prompt específico foi encontrado para esta classe processual."
    
    # 4. Preparar o contexto completo
    movs_text = "\n".join([
        f"{m.dataHora}: {m.descricao} - {m.complemento or ''}"
        for m in process_data.movimentos[-20:]  # Últimas 20 movimentações
    ])
    
    context = f"""
CONTEXTO DO PROCESSO:

Número: {process_data.numero}
Classe Processual: {process_data.classeProcessual}
Competência: {process_data.competencia}

CLASSIFICAÇÃO ATUAL:
Tipo de Intimação: {classification.get('classificacao', {}).get('tipo_intimacao') or classification.get('classificacao', {}).get('codigo') or 'N/A'}
Explicação: {classification.get('classificacao', {}).get('resumo') or classification.get('classificacao', {}).get('justificativa') or 'N/A'}
Data da Classificação: {classification.get('data_classificacao')}

PROMPT USADO NA CLASSIFICAÇÃO:
{prompt_used}

ÚLTIMAS MOVIMENTAÇÕES DO PROCESSO:
{movs_text}

---

O usuário quer conversar com você sobre essa classificação. Responda à pergunta dele considerando todo o contexto acima.
"""
    
    # 5. Construir mensagens para a API
    messages = [
        {"role": "system", "content": CHAT_SYSTEM_PROMPT}
    ]
    
    # Adicionar o contexto como primeira mensagem do assistente (para economy de tokens)
    messages.append({"role": "user", "content": context})
    
    # Adicionar histórico da conversa
    for msg in request.history:
        messages.append({"role": msg.role, "content": msg.content})
    
    # Adicionar mensagem atual do usuário
    messages.append({"role": "user", "content": request.message})
    
    # 6. Chamar a API
    try:
        client = get_client()
        response = await client.chat.completions.create(
            model=Config.OPENROUTER_MODEL_ID,
            messages=messages
        )
        
        ai_response = response.choices[0].message.content
        
        return ChatResponse(response=ai_response)
        
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro ao comunicar com a IA: {str(e)}")
