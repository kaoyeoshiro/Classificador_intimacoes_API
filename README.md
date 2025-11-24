# Classificador de Intimações - API

Sistema moderno para gestão e classificação de processos judiciais utilizando Inteligência Artificial.

## 🚀 Funcionalidades

- **Gestão de Processos**: Importação e visualização de processos judiciais.
- **Classificação via IA**: Utiliza modelos de linguagem (LLMs) para analisar e classificar intimações com base em prompts personalizáveis.
- **Gestão de Prompts**: Interface para criar, editar e testar diferentes prompts de classificação para classes processuais específicas.
- **Histórico de Movimentações**: Visualização detalhada das movimentações processuais extraídas via XML.
- **Exportação**: Exportação dos dados e classificações para formatos JSON e Excel.
- **Interface Responsiva**: Frontend moderno construído com React e TailwindCSS.

## 🛠️ Tecnologias Utilizadas

### Backend
- **Python 3.x**
- **FastAPI**: Framework web moderno e de alta performance.
- **Uvicorn**: Servidor ASGI.
- **Pandas/OpenPyXL**: Manipulação e exportação de dados.
- **OpenAI API Client**: Integração com LLMs (OpenRouter/Gemini).

### Frontend
- **React**: Biblioteca JavaScript para interfaces de usuário (via CDN).
- **TailwindCSS**: Framework CSS utilitário (via CDN).
- **Axios**: Cliente HTTP.
- **Babel**: Transpilador JavaScript (via CDN).

## 📦 Instalação e Configuração

1. **Clone o repositório**
   ```bash
   git clone https://github.com/kaoyeoshiro/Classificador_intimacoes_API.git
   cd Classificador_intimacoes_API
   ```

2. **Crie um ambiente virtual (opcional, mas recomendado)**
   ```bash
   python -m venv venv
   # Windows
   venv\Scripts\activate
   # Linux/Mac
   source venv/bin/activate
   ```

3. **Instale as dependências**
   ```bash
   pip install -r backend/requirements.txt
   ```

4. **Configuração de Variáveis de Ambiente**
   Crie um arquivo `.env` na raiz ou na pasta `backend` com as chaves necessárias (ex: API Key do OpenRouter/OpenAI).

## 🏃‍♂️ Executando o Projeto

Para iniciar o servidor API e servir o frontend:

```bash
uvicorn backend.main:app --reload
```

O sistema estará acessível em: `http://localhost:8000`

## 📂 Estrutura do Projeto

```
Classificador_intimacoes_API/
├── backend/
│   ├── routers/        # Rotas da API (processos, classificação, exportação)
│   ├── config.py       # Configurações do sistema
│   ├── main.py         # Ponto de entrada da aplicação FastAPI
│   ├── models.py       # Modelos de dados Pydantic
│   └── requirements.txt # Dependências do Python
├── frontend/
│   └── index.html      # Aplicação Single Page (SPA) em React
├── api.py              # Script legado/auxiliar de integração
└── README.md           # Documentação do projeto
```

## 🤝 Contribuição

Contribuições são bem-vindas! Sinta-se à vontade para abrir issues ou enviar pull requests.
