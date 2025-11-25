#!/usr/bin/env python3
"""
Script de exemplo para classificação em lote de processos.

Uso:
    python batch_classify_example.py --mode simple
    python batch_classify_example.py --mode progress
    python batch_classify_example.py --mode stats
"""

import requests
import json
import argparse
import time
from datetime import datetime


BASE_URL = "http://localhost:8000"


def print_header(title):
    """Imprime um cabeçalho formatado."""
    print("\n" + "=" * 70)
    print(f"  {title}")
    print("=" * 70 + "\n")


def get_statistics():
    """Obtém e exibe estatísticas das classificações."""
    print_header("ESTATÍSTICAS DE CLASSIFICAÇÃO")

    response = requests.get(f"{BASE_URL}/classify/statistics")
    stats = response.json()

    print(f"Total de processos: {stats['total_processes']}")
    print(f"Processos classificados: {stats['total_classified']}")
    print(f"Processos pendentes: {stats['pending_classification']}")
    print(f"Taxa de conclusão: {stats['completion_rate']}%")

    print("\n📊 Por Classe Processual:")
    for classe, data in stats['by_class'].items():
        print(f"  Classe {classe}:")
        print(f"    Total: {data['total']}")
        print(f"    Classificados: {data['classified']}")
        print(f"    Pendentes: {data['pending']}")

    print("\n🏷️  Tipos de Classificação:")
    for tipo, count in stats['classification_types'].items():
        print(f"  {tipo}: {count}")


def simple_batch_classify(force=False, max_concurrent=5, classe=None):
    """Executa classificação em lote simples (sem streaming)."""
    print_header("CLASSIFICAÇÃO EM LOTE - MODO SIMPLES")

    params = {
        'force': force,
        'max_concurrent': max_concurrent
    }
    if classe:
        params['classe_processual'] = classe

    print(f"⚙️  Configurações:")
    print(f"  - Forçar reclassificação: {'Sim' if force else 'Não'}")
    print(f"  - Concorrência máxima: {max_concurrent}")
    print(f"  - Filtro de classe: {classe or 'Todos'}")
    print("\n⏳ Aguardando conclusão...\n")

    start_time = time.time()

    response = requests.post(
        f"{BASE_URL}/classify/analyze_all",
        params=params
    )

    end_time = time.time()
    result = response.json()

    print("✅ Classificação concluída!")
    print(f"\n📈 Resultados:")
    print(f"  Total de processos: {result['total_processos']}")
    print(f"  Processos analisados: {result['processos_analisados']}")
    print(f"  Sucessos: {result['sucesso']}")
    print(f"  Erros: {result['erros']}")
    print(f"  Duração: {result['duracao_segundos']:.2f}s")
    print(f"  Velocidade: {result['processos_por_segundo']:.2f} processos/s")
    print(f"  Tempo de resposta: {end_time - start_time:.2f}s")

    if result['erros'] > 0:
        print("\n❌ Erros encontrados:")
        for error in result['detalhes_erros'][:5]:  # Mostra apenas os 5 primeiros
            print(f"  - {error['numero']} (Classe {error['classe']}): {error['erro']}")
        if len(result['detalhes_erros']) > 5:
            print(f"  ... e mais {len(result['detalhes_erros']) - 5} erros")

    if result['sucesso'] > 0:
        print("\n✅ Exemplos de classificações bem-sucedidas:")
        for success in result['resultados'][:5]:  # Mostra apenas os 5 primeiros
            print(f"  - {success['numero']}: {success['classificacao']}")
        if len(result['resultados']) > 5:
            print(f"  ... e mais {len(result['resultados']) - 5} classificações")


def progress_batch_classify(force=False, max_concurrent=5, classe=None):
    """Executa classificação em lote com progresso em tempo real (SSE)."""
    print_header("CLASSIFICAÇÃO EM LOTE - MODO PROGRESSO")

    params = {
        'force': force,
        'max_concurrent': max_concurrent
    }
    if classe:
        params['classe_processual'] = classe

    print(f"⚙️  Configurações:")
    print(f"  - Forçar reclassificação: {'Sim' if force else 'Não'}")
    print(f"  - Concorrência máxima: {max_concurrent}")
    print(f"  - Filtro de classe: {classe or 'Todos'}")
    print("\n🔄 Iniciando classificação com feedback em tempo real...\n")

    response = requests.get(
        f"{BASE_URL}/classify/batch_progress",
        params=params,
        stream=True
    )

    start_time = time.time()
    success_count = 0
    error_count = 0
    total = 0

    for line in response.iter_lines():
        if line:
            line = line.decode('utf-8')
            if line.startswith('data: '):
                try:
                    data = json.loads(line[6:])

                    if data['type'] == 'start':
                        total = data['total']
                        print(f"📋 Total de processos a classificar: {total}\n")

                    elif data['type'] == 'processing':
                        print(f"⏳ Processando: {data['numero']} (Classe {data['classe']})")

                    elif data['type'] == 'success':
                        success_count += 1
                        print(f"✅ {data['numero']}: {data['classificacao']} [{data['progress_percent']:.1f}%]")

                    elif data['type'] == 'error':
                        error_count += 1
                        print(f"❌ {data['numero']}: {data['erro']} [{data['progress_percent']:.1f}%]")

                    elif data['type'] == 'complete':
                        end_time = time.time()
                        print("\n" + "=" * 70)
                        print("🎉 CLASSIFICAÇÃO CONCLUÍDA!")
                        print("=" * 70)
                        print(f"\n📊 Estatísticas Finais:")
                        print(f"  Total: {data['total']}")
                        print(f"  Sucessos: {data['sucesso']}")
                        print(f"  Erros: {data['erros']}")
                        print(f"  Duração: {data['duracao_segundos']:.2f}s")
                        print(f"  Velocidade: {data['processos_por_segundo']:.2f} processos/s")
                        print(f"  Tempo total: {end_time - start_time:.2f}s")

                    elif data['type'] == 'info':
                        print(f"ℹ️  {data['message']}")

                except json.JSONDecodeError as e:
                    print(f"⚠️  Erro ao decodificar JSON: {e}")


def main():
    parser = argparse.ArgumentParser(
        description="Script de classificação em lote de processos"
    )
    parser.add_argument(
        '--mode',
        choices=['simple', 'progress', 'stats'],
        default='simple',
        help='Modo de operação: simple (padrão), progress (streaming), stats (estatísticas)'
    )
    parser.add_argument(
        '--force',
        action='store_true',
        help='Forçar reclassificação de processos já classificados'
    )
    parser.add_argument(
        '--concurrent',
        type=int,
        default=5,
        help='Número máximo de classificações simultâneas (padrão: 5)'
    )
    parser.add_argument(
        '--class',
        dest='classe',
        help='Filtrar apenas processos de uma classe específica'
    )
    parser.add_argument(
        '--url',
        default='http://localhost:8000',
        help='URL base da API (padrão: http://localhost:8000)'
    )

    args = parser.parse_args()

    global BASE_URL
    BASE_URL = args.url

    try:
        if args.mode == 'stats':
            get_statistics()
        elif args.mode == 'simple':
            simple_batch_classify(
                force=args.force,
                max_concurrent=args.concurrent,
                classe=args.classe
            )
        elif args.mode == 'progress':
            progress_batch_classify(
                force=args.force,
                max_concurrent=args.concurrent,
                classe=args.classe
            )

    except requests.exceptions.ConnectionError:
        print("\n❌ Erro: Não foi possível conectar à API.")
        print(f"   Verifique se o servidor está rodando em {BASE_URL}")
    except KeyboardInterrupt:
        print("\n\n⚠️  Operação cancelada pelo usuário.")
    except Exception as e:
        print(f"\n❌ Erro inesperado: {e}")


if __name__ == "__main__":
    main()
