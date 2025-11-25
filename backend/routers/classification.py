from fastapi import APIRouter, HTTPException, Query
from fastapi.responses import StreamingResponse
import asyncio
from ..models import ClassificacaoResult
from ..services.ai_classifier import classify_process
from ..database import load_db, save_classification_result, load_classifications
import json
import os
from datetime import datetime
from typing import Optional

router = APIRouter(prefix="/classify", tags=["classification"])

@router.post("/{numero_processo}", response_model=ClassificacaoResult)
async def classify_process_endpoint(numero_processo: str):
    # 1. Get process data
    db = load_db()
    process_data = next((p for p in db if p.numero == numero_processo), None)
    
    if not process_data:
        raise HTTPException(status_code=404, detail="Processo não encontrado. Adicione-o primeiro.")
    
    # 2. Call AI
    try:
        result = await classify_process(process_data)
    except Exception as e:
        raise HTTPException(status_code=500, detail=f"Erro na classificação: {str(e)}")
    
    # 3. Save result
    save_classification_result(result)
    
    return result

    return result

@router.post("/analyze_all")
async def analyze_all_endpoint(
    force: bool = False,
    max_concurrent: int = Query(default=5, ge=1, le=20),
    classe_processual: Optional[str] = None
):
    """
    Classifica todos os processos pendentes em lote.

    Args:
        force: Se True, reclassifica processos já classificados
        max_concurrent: Número máximo de classificações simultâneas (1-20)
        classe_processual: Se especificado, classifica apenas processos desta classe
    """
    processes = load_db()
    classifications = load_classifications()

    # Filter processes to analyze
    to_analyze = []
    for p in processes:
        # Filter by classe if specified
        if classe_processual and p.classeProcessual != classe_processual:
            continue

        is_classified = any(c['numero_processo'] == p.numero for c in classifications)
        if not is_classified or force:
            to_analyze.append(p)

    if not to_analyze:
        return {
            "message": "Nenhum processo pendente para análise.",
            "total_processos": len(processes),
            "total_analisados": 0,
            "sucesso": 0,
            "erros": 0,
            "detalhes_erros": []
        }

    start_time = datetime.now()
    semaphore = asyncio.Semaphore(max_concurrent)
    results = []
    errors = []

    async def analyze_with_limit(process):
        async with semaphore:
            try:
                result = await classify_process(process)
                save_classification_result(result)
                results.append({
                    "numero": process.numero,
                    "classe": process.classeProcessual,
                    "classificacao": result.classificacao.get("tipo_intimacao", "N/A")
                })
            except Exception as e:
                error_detail = {
                    "numero": process.numero,
                    "classe": process.classeProcessual,
                    "erro": str(e)
                }
                errors.append(error_detail)
                print(f"Erro ao classificar {process.numero}: {str(e)}")

    await asyncio.gather(*[analyze_with_limit(p) for p in to_analyze])

    end_time = datetime.now()
    duration = (end_time - start_time).total_seconds()

    return {
        "message": "Classificação em lote concluída",
        "total_processos": len(processes),
        "processos_analisados": len(to_analyze),
        "sucesso": len(results),
        "erros": len(errors),
        "duracao_segundos": round(duration, 2),
        "processos_por_segundo": round(len(results) / duration, 2) if duration > 0 else 0,
        "resultados": results,
        "detalhes_erros": errors
    }

@router.get("/batch_progress")
async def batch_classify_with_progress(
    force: bool = False,
    max_concurrent: int = Query(default=5, ge=1, le=20),
    classe_processual: Optional[str] = None
):
    """
    Classifica todos os processos pendentes com feedback em tempo real via SSE.

    Args:
        force: Se True, reclassifica processos já classificados
        max_concurrent: Número máximo de classificações simultâneas (1-20)
        classe_processual: Se especificado, classifica apenas processos desta classe

    Returns:
        Stream de eventos com o progresso da classificação
    """
    async def event_generator():
        processes = load_db()
        classifications = load_classifications()

        # Filter processes to analyze
        to_analyze = []
        for p in processes:
            if classe_processual and p.classeProcessual != classe_processual:
                continue
            is_classified = any(c['numero_processo'] == p.numero for c in classifications)
            if not is_classified or force:
                to_analyze.append(p)

        total = len(to_analyze)

        if total == 0:
            yield f"data: {json.dumps({'type': 'info', 'message': 'Nenhum processo pendente para análise'})}\n\n"
            yield f"data: {json.dumps({'type': 'complete', 'total': 0, 'sucesso': 0, 'erros': 0})}\n\n"
            return

        # Send initial info
        yield f"data: {json.dumps({'type': 'start', 'total': total, 'max_concurrent': max_concurrent})}\n\n"

        start_time = datetime.now()
        semaphore = asyncio.Semaphore(max_concurrent)
        completed = 0
        success_count = 0
        error_count = 0
        results = []
        errors = []

        # Create a queue for events
        event_queue = asyncio.Queue()

        async def analyze_with_progress(process):
            nonlocal completed, success_count, error_count
            async with semaphore:
                try:
                    # Send processing event
                    progress_data = {
                        'type': 'processing',
                        'numero': process.numero,
                        'classe': process.classeProcessual,
                        'completed': completed,
                        'total': total
                    }
                    await event_queue.put(progress_data)

                    result = await classify_process(process)
                    save_classification_result(result)

                    completed += 1
                    success_count += 1

                    # Send success event
                    success_data = {
                        'type': 'success',
                        'numero': process.numero,
                        'classe': process.classeProcessual,
                        'classificacao': result.classificacao.get("tipo_intimacao", "N/A"),
                        'completed': completed,
                        'total': total,
                        'progress_percent': round((completed / total) * 100, 1)
                    }
                    await event_queue.put(success_data)
                    results.append(success_data)

                except Exception as e:
                    completed += 1
                    error_count += 1

                    # Send error event
                    error_data = {
                        'type': 'error',
                        'numero': process.numero,
                        'classe': process.classeProcessual,
                        'erro': str(e),
                        'completed': completed,
                        'total': total,
                        'progress_percent': round((completed / total) * 100, 1)
                    }
                    await event_queue.put(error_data)
                    errors.append(error_data)

        # Start all tasks
        tasks = [asyncio.create_task(analyze_with_progress(p)) for p in to_analyze]

        # Process events as they come
        while completed < total:
            try:
                event_data = await asyncio.wait_for(event_queue.get(), timeout=1.0)
                yield f"data: {json.dumps(event_data)}\n\n"
            except asyncio.TimeoutError:
                continue

        # Wait for all tasks to complete
        await asyncio.gather(*tasks)

        end_time = datetime.now()
        duration = (end_time - start_time).total_seconds()

        # Send completion event
        complete_data = {
            'type': 'complete',
            'total': total,
            'sucesso': success_count,
            'erros': error_count,
            'duracao_segundos': round(duration, 2),
            'processos_por_segundo': round(success_count / duration, 2) if duration > 0 else 0,
            'resultados': results,
            'detalhes_erros': errors
        }
        yield f"data: {json.dumps(complete_data)}\n\n"

    return StreamingResponse(event_generator(), media_type="text/event-stream")

@router.get("/statistics")
def get_classification_statistics():
    """
    Retorna estatísticas sobre as classificações realizadas.
    """
    processes = load_db()
    classifications = load_classifications()

    total_processes = len(processes)
    total_classified = len(classifications)
    pending = total_processes - total_classified

    # Group by classe processual
    by_class = {}
    for p in processes:
        classe = p.classeProcessual or "N/A"
        if classe not in by_class:
            by_class[classe] = {"total": 0, "classified": 0, "pending": 0}
        by_class[classe]["total"] += 1

        is_classified = any(c['numero_processo'] == p.numero for c in classifications)
        if is_classified:
            by_class[classe]["classified"] += 1
        else:
            by_class[classe]["pending"] += 1

    # Classification types distribution
    classification_types = {}
    for c in classifications:
        tipo = c.get('classificacao', {}).get('tipo_intimacao', 'N/A')
        classification_types[tipo] = classification_types.get(tipo, 0) + 1

    return {
        "total_processes": total_processes,
        "total_classified": total_classified,
        "pending_classification": pending,
        "completion_rate": round((total_classified / total_processes * 100), 2) if total_processes > 0 else 0,
        "by_class": by_class,
        "classification_types": classification_types
    }

@router.get("/", response_model=list)
def list_classifications():
    return load_classifications()
