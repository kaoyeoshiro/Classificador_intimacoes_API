# Classificação em Lote de Processos

## Visão Geral

O sistema oferece três endpoints para classificação de processos em lote, cada um com diferentes níveis de detalhe e feedback.

## Endpoints Disponíveis

### 1. `/classify/analyze_all` (POST)

Endpoint padrão para classificação em lote com resultado final consolidado.

**Parâmetros:**
- `force` (bool, opcional): Se `true`, reclassifica processos já classificados. Padrão: `false`
- `max_concurrent` (int, opcional): Número de classificações simultâneas (1-20). Padrão: `5`
- `classe_processual` (string, opcional): Filtra apenas processos de uma classe específica

**Exemplo de uso:**

```bash
# Classificar apenas processos pendentes
curl -X POST "http://localhost:8000/classify/analyze_all"

# Classificar com 10 processos simultâneos
curl -X POST "http://localhost:8000/classify/analyze_all?max_concurrent=10"

# Forçar reclassificação de todos os processos
curl -X POST "http://localhost:8000/classify/analyze_all?force=true"

# Classificar apenas processos de classe "7"
curl -X POST "http://localhost:8000/classify/analyze_all?classe_processual=7"
```

**Resposta:**

```json
{
  "message": "Classificação em lote concluída",
  "total_processos": 100,
  "processos_analisados": 50,
  "sucesso": 48,
  "erros": 2,
  "duracao_segundos": 125.5,
  "processos_por_segundo": 0.38,
  "resultados": [
    {
      "numero": "0000000-00.0000.0.00.0000",
      "classe": "7",
      "classificacao": "Despacho"
    }
  ],
  "detalhes_erros": [
    {
      "numero": "0000000-00.0000.0.00.0001",
      "classe": "7",
      "erro": "Timeout na API"
    }
  ]
}
```

### 2. `/classify/batch_progress` (GET)

Endpoint com feedback em tempo real usando Server-Sent Events (SSE).

**Parâmetros:**
- Mesmos parâmetros do `/analyze_all`

**Exemplo de uso com JavaScript:**

```javascript
const eventSource = new EventSource(
  'http://localhost:8000/classify/batch_progress?max_concurrent=5'
);

eventSource.onmessage = (event) => {
  const data = JSON.parse(event.data);

  switch(data.type) {
    case 'start':
      console.log(`Iniciando classificação de ${data.total} processos`);
      break;

    case 'processing':
      console.log(`Processando: ${data.numero}`);
      break;

    case 'success':
      console.log(`✓ ${data.numero}: ${data.classificacao} (${data.progress_percent}%)`);
      break;

    case 'error':
      console.error(`✗ ${data.numero}: ${data.erro}`);
      break;

    case 'complete':
      console.log(`Concluído! ${data.sucesso} sucesso, ${data.erros} erros`);
      eventSource.close();
      break;
  }
};

eventSource.onerror = (error) => {
  console.error('Erro na conexão SSE:', error);
  eventSource.close();
};
```

**Exemplo com Python:**

```python
import requests
import json

response = requests.get(
    'http://localhost:8000/classify/batch_progress',
    params={'max_concurrent': 5},
    stream=True
)

for line in response.iter_lines():
    if line:
        line = line.decode('utf-8')
        if line.startswith('data: '):
            data = json.loads(line[6:])

            if data['type'] == 'success':
                print(f"✓ {data['numero']}: {data['classificacao']}")
            elif data['type'] == 'error':
                print(f"✗ {data['numero']}: {data['erro']}")
            elif data['type'] == 'complete':
                print(f"\nConcluído! {data['sucesso']} sucessos, {data['erros']} erros")
                print(f"Duração: {data['duracao_segundos']}s")
```

**Eventos SSE:**

1. **start**: Início do processo
   ```json
   {"type": "start", "total": 50, "max_concurrent": 5}
   ```

2. **processing**: Processo sendo classificado
   ```json
   {"type": "processing", "numero": "xxx", "classe": "7", "completed": 10, "total": 50}
   ```

3. **success**: Classificação bem-sucedida
   ```json
   {
     "type": "success",
     "numero": "xxx",
     "classe": "7",
     "classificacao": "Despacho",
     "completed": 11,
     "total": 50,
     "progress_percent": 22.0
   }
   ```

4. **error**: Erro na classificação
   ```json
   {
     "type": "error",
     "numero": "xxx",
     "classe": "7",
     "erro": "Timeout",
     "completed": 12,
     "total": 50,
     "progress_percent": 24.0
   }
   ```

5. **complete**: Processo concluído
   ```json
   {
     "type": "complete",
     "total": 50,
     "sucesso": 48,
     "erros": 2,
     "duracao_segundos": 125.5,
     "processos_por_segundo": 0.38,
     "resultados": [...],
     "detalhes_erros": [...]
   }
   ```

### 3. `/classify/statistics` (GET)

Endpoint para consultar estatísticas das classificações.

**Exemplo de uso:**

```bash
curl "http://localhost:8000/classify/statistics"
```

**Resposta:**

```json
{
  "total_processes": 150,
  "total_classified": 120,
  "pending_classification": 30,
  "completion_rate": 80.0,
  "by_class": {
    "7": {
      "total": 100,
      "classified": 85,
      "pending": 15
    },
    "195": {
      "total": 50,
      "classified": 35,
      "pending": 15
    }
  },
  "classification_types": {
    "Despacho": 45,
    "Sentença": 30,
    "Decisão": 25,
    "N/A": 20
  }
}
```

## Configurações de Desempenho

### Concorrência

O parâmetro `max_concurrent` controla quantas classificações são processadas simultaneamente:

- **Valores baixos (1-3)**: Mais estável, menor uso de recursos, mais lento
- **Valores médios (5-10)**: Equilíbrio entre velocidade e estabilidade (recomendado)
- **Valores altos (15-20)**: Mais rápido, maior uso de recursos, pode causar timeout

**Recomendações:**
- Para processos simples: `max_concurrent=10`
- Para processos complexos: `max_concurrent=5`
- Para servidores com recursos limitados: `max_concurrent=3`

### Filtragem por Classe

Use o parâmetro `classe_processual` para processar apenas uma classe por vez:

```bash
# Classificar apenas Execuções Fiscais (classe 7)
curl -X POST "http://localhost:8000/classify/analyze_all?classe_processual=7&max_concurrent=10"
```

Isso é útil para:
- Processar classes com prompts diferentes separadamente
- Testar configurações específicas
- Processar classes prioritárias primeiro

## Melhores Práticas

1. **Monitoramento**: Use `/classify/statistics` para verificar o progresso antes de iniciar classificações em massa

2. **Teste primeiro**: Comece com `max_concurrent=3` e aumente gradualmente

3. **Filtro por classe**: Processe classes separadamente para melhor controle

4. **SSE para grandes volumes**: Use `/batch_progress` para volumes acima de 50 processos

5. **Tratamento de erros**: Sempre verifique `detalhes_erros` na resposta e trate casos específicos

## Troubleshooting

### Timeout Errors

Se você receber muitos erros de timeout:
- Reduza `max_concurrent`
- Verifique a conectividade com a API da IA
- Aumente o timeout da API (configuração do servidor)

### Classificações Inconsistentes

Se as classificações não estão corretas:
- Verifique os prompts configurados para cada classe
- Use `force=true` para reclassificar
- Revise as últimas movimentações (agora configuradas para 25)

### Processos não aparecendo

Se processos não aparecem como pendentes:
- Verifique se já foram classificados com `/classify/statistics`
- Use `force=true` para forçar reclassificação
- Confirme que o processo está no banco com `/processes/`
