from openai import OpenAI
import json
from ..config import Config
from ..models import ProcessoData, ClassificacaoResult

def get_client():
    if not Config.OPENROUTER_API_KEY:
        raise ValueError("OPENROUTER_API_KEY não configurada no arquivo .env")
    return OpenAI(
        base_url="https://openrouter.ai/api/v1",
        api_key=Config.OPENROUTER_API_KEY,
    )

SYSTEM_PROMPT = """
Você é um assistente jurídico especializado em classificar intimações e movimentações processuais.
Sua tarefa é analisar os dados de um processo judicial e identificar a natureza da última intimação ou movimentação relevante.
Retorne APENAS um JSON com a classificação.
"""

from ..routers.prompts import load_prompts

def get_prompt_for_class(classe_processual: str) -> str:
    prompts = load_prompts()
    
    # 1. Try to find a prompt that explicitly lists this class
    for p in prompts:
        if classe_processual in p.classes:
            return p.content
            
    # 2. Strict Mode: No fallback. Return None if no specific prompt found.
    return None

def classify_process(process_data: ProcessoData) -> ClassificacaoResult:
    # Revert to using classeProcessual as it contains the code (e.g. "7")
    class_code = process_data.classeProcessual
    
    prompt = get_prompt_for_class(class_code)
    
    if not prompt:
        return ClassificacaoResult(
            numero_processo=process_data.numero,
            classe_processual=process_data.classeProcessual or "N/A",
            classificacao={
                "tipo_intimacao": "N/A",
                "resumo": f"Processo não classificado: Nenhum prompt configurado para a classe '{class_code}'. Verifique se este código está incluído em algum prompt."
            }
        )
    
    # Prepare context from movements
    movs_text = "\n".join([f"{m.dataHora}: {m.descricao} - {m.complemento or ''}" for m in process_data.movimentos[-10:]]) # Last 10 movements
    
    full_content = f"""
    {prompt}
    
    Dados do Processo:
    Número: {process_data.numero}
    Classe: {process_data.classeProcessual}
    Competência: {process_data.competencia}
    
    Últimas Movimentações:
    {movs_text}
    """
    
    client = get_client()
    response = client.chat.completions.create(
        model=Config.OPENROUTER_MODEL_ID,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": full_content}
        ],
        response_format={"type": "json_object"}
    )
    
    content = response.choices[0].message.content
    try:
        result_json = json.loads(content)
        # Normalize keys
        if "codigo" in result_json and "tipo_intimacao" not in result_json:
            result_json["tipo_intimacao"] = result_json["codigo"]
        if "justificativa" in result_json and "resumo" not in result_json:
            result_json["resumo"] = result_json["justificativa"]
        if "explicacao" in result_json and "resumo" not in result_json:
            result_json["resumo"] = result_json["explicacao"]
            
    except json.JSONDecodeError:
        result_json = {"erro": "Falha ao decodificar JSON da IA", "raw_content": content}
        
    return ClassificacaoResult(
        numero_processo=process_data.numero,
        classe_processual=process_data.classeProcessual or "N/A",
        classificacao=result_json
    )
