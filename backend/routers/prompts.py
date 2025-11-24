from fastapi import APIRouter, HTTPException
from pydantic import BaseModel
from typing import List, Optional
import json
import os

router = APIRouter(prefix="/prompts", tags=["prompts"])

PROMPTS_FILE = "prompts.json"

class PromptConfig(BaseModel):
    id: str
    name: str
    classes: List[str] # List of class codes, e.g. ["7", "1116"]
    content: str

def load_prompts() -> List[PromptConfig]:
    if not os.path.exists(PROMPTS_FILE):
        # Default prompts if file doesn't exist
        return [
            PromptConfig(
                id="default",
                name="Padrão",
                classes=[],
                content="""Analise as movimentações do processo abaixo e classifique a situação atual.
Foque nas últimas movimentações para entender o status.

Retorne um JSON no seguinte formato:
{
    "tipo_intimacao": "Código da classificação (Ex: 7, 1116, Sentença, Despacho, etc)",
    "resumo": "Breve explicação do porquê escolheu essa classificação"
}"""
            )
        ]
    try:
        with open(PROMPTS_FILE, "r", encoding="utf-8") as f:
            data = json.load(f)
            return [PromptConfig(**d) for d in data]
    except:
        return []

def save_prompts(prompts: List[PromptConfig]):
    with open(PROMPTS_FILE, "w", encoding="utf-8") as f:
        json.dump([p.model_dump() for p in prompts], f, indent=2, ensure_ascii=False)

@router.get("/", response_model=List[PromptConfig])
def list_prompts():
    return load_prompts()

@router.post("/", response_model=PromptConfig)
def create_prompt(prompt: PromptConfig):
    prompts = load_prompts()
    if any(p.id == prompt.id for p in prompts):
        raise HTTPException(status_code=400, detail="Prompt ID already exists")
    prompts.append(prompt)
    save_prompts(prompts)
    return prompt

@router.put("/{prompt_id}", response_model=PromptConfig)
def update_prompt(prompt_id: str, prompt: PromptConfig):
    prompts = load_prompts()
    for i, p in enumerate(prompts):
        if p.id == prompt_id:
            prompts[i] = prompt
            save_prompts(prompts)
            return prompt
    raise HTTPException(status_code=404, detail="Prompt not found")

@router.delete("/{prompt_id}")
def delete_prompt(prompt_id: str):
    prompts = load_prompts()
    prompts = [p for p in prompts if p.id != prompt_id]
    save_prompts(prompts)
    return {"message": "Prompt deleted"}
