@echo off
echo Iniciando Classificador de Intimacoes...

:: Check if venv exists
if exist "venv" (
    echo Ativando ambiente virtual...
    call venv\Scripts\activate
) else (
    echo AVISO: Ambiente virtual 'venv' nao encontrado. Tentando rodar com python global...
)

:: Start Backend in background
echo Iniciando Backend...
start /B uvicorn backend.main:app --reload

:: Wait a bit for backend to start
timeout /t 5 /nobreak >nul

:: Open Frontend
echo Abrindo Dashboard...
start http://localhost:8000

echo.
echo Sistema iniciado!
echo Backend rodando em http://localhost:8000
echo Pressione qualquer tecla para fechar esta janela (o servidor continuara rodando em segundo plano se nao for fechado corretamente).
echo Para encerrar o servidor, feche a janela do python/uvicorn que pode ter aberto ou use o Gerenciador de Tarefas.
pause
