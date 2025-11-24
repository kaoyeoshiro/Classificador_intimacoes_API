import requests
import re
import base64
import os
import threading
import queue
import tkinter as tk
from tkinter import ttk, filedialog, messagebox
from tkinter.scrolledtext import ScrolledText
import xml.etree.ElementTree as ET
import time
import tempfile
from datetime import datetime
from typing import List, Dict, Any, Optional, Tuple

# NOVO: PDF e extração opcional
import fitz  # PyMuPDF
import pymupdf4llm

# =========================
# Configuração e constantes
# =========================
URL_WSDL = 'https://esaj.tjms.jus.br/mniws/servico-intercomunicacao-2.2.2/intercomunicacao?wsdl'
WS_USER = "PGEMS"
WS_PASS = "SAJ03PGEMS"

REGEX_CONTEUDO = r"<ns2:conteudo>(.*?)</ns2:conteudo>"

# Mapa de categorias (cdcategoria == tipoDocumento)
CATEGORIAS_MAP = {
    "6": "Despacho",
    "15": "Decisões Interlocutórias",
    "34": "Acórdãos",
    "21": "Peças da Defensoria",
    "8": "Sentença",
    "8338": "Manifestação do Procurador da Fazenda Pública Estadual",
    "8426": "Manifestação do Procurador da Fazenda Pública Municipal",
    "8333": "Manifestação do Ministério Público",
    "8335": "Recurso de Apelação",
    "9500": "Petição",
    "8305": "Contrarrazões de Apelação",
    "54": "Sentença do Juiz Leigo",
}

# =========================
# Rede com retry
# =========================
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry

def criar_sessao_com_retry():
    session = requests.Session()
    retry = Retry(
        total=5,
        backoff_factor=1,
        status_forcelist=[500, 502, 503, 504, 429]
    )
    adapter = HTTPAdapter(max_retries=retry)
    session.mount('http://', adapter)
    session.mount('https://', adapter)
    return session

# =========================
# Helpers de XML / datas
# =========================
def _all_desc_text(elem: ET.Element, name_endswith: str) -> List[str]:
    """Pega textos de todos os nós cujo nome (sem namespace) termina com name_endswith (case-insensitive)."""
    out = []
    target = name_endswith.lower()
    for e in elem.iter():
        tag_no_ns = e.tag.split('}')[-1].lower()
        if tag_no_ns.endswith(target):
            if e.text and e.text.strip():
                out.append(e.text.strip())
    return out

def _first_desc_text(elem: ET.Element, name_endswith: str) -> Optional[str]:
    vals = _all_desc_text(elem, name_endswith)
    return vals[0] if vals else None

def _parse_iso_date_maybe(s: Optional[str]) -> Optional[datetime]:
    """Tenta vários formatos comuns (ISO com/sem TZ, ESAJ etc.)."""
    if not s:
        return None
    s = s.strip()
    # Normaliza Z
    s = s.replace("Z", "+0000")
    # Tenta formatos
    fmts = [
        "%Y-%m-%dT%H:%M:%S.%f%z",
        "%Y-%m-%dT%H:%M:%S%z",
        "%Y-%m-%dT%H:%M:%S",
        "%Y-%m-%d %H:%M:%S",
        "%Y-%m-%d",
    ]
    if re.fullmatch(r"\d{14}", s):
        try:
            return datetime.strptime(s, "%Y%m%d%H%M%S")
        except Exception:
            pass
    if re.fullmatch(r"\d{8}", s):
        try:
            return datetime.strptime(s, "%Y%m%d")
        except Exception:
            pass
    for fmt in fmts:
        try:
            # Pequena gambiarra para "%z" sem dois pontos no timezone
            if "%z" in fmt and re.search(r"[+-]\d{2}:\d{2}$", s):
                s_try = s[:-3] + s[-2:]
            else:
                s_try = s
            return datetime.strptime(s_try, fmt)
        except Exception:
            continue
    # Tenta CreationDate do PDF: D:YYYYMMDDHHmmSS
    m = re.search(r"D:(\d{4})(\d{2})(\d{2})(\d{2})(\d{2})(\d{2})", s)
    if m:
        try:
            return datetime(
                int(m.group(1)), int(m.group(2)), int(m.group(3)),
                int(m.group(4)), int(m.group(5)), int(m.group(6))
            )
        except Exception:
            pass
    return None

# =========================
# Lógica ESAJ (funções puras)
# =========================
def extrair_info_instancia(xml_text: str) -> Dict[str, Any]:
    """
    Extrai informações sobre a instância do processo no XML
    """
    try:
        root = ET.fromstring(xml_text)
        info = {}
        
        # Busca dados básicos do processo
        for dados_basicos in root.iter():
            if dados_basicos.tag.endswith('dadosBasicos'):
                info['numero'] = dados_basicos.get('numero', '')
                info['competencia'] = dados_basicos.get('competencia', '')
                info['codigoLocalidade'] = dados_basicos.get('codigoLocalidade', '')
                info['classeProcessual'] = dados_basicos.get('classeProcessual', '')
                break
        
        # Busca movimentos para identificar instância atual
        movimentos = []
        for movimento in root.iter():
            if movimento.tag.endswith('movimento'):
                mov_text = movimento.text or ''
                # Procura por indicações de instância
                if any(term in mov_text.lower() for term in ['recurso', 'apelação', 'segunda instância', 'tribunal']):
                    movimentos.append(mov_text)
        
        info['movimentos_instancia'] = movimentos
        info['grau_estimado'] = 2 if movimentos else 1
        
        return info
    except Exception as e:
        return {'erro': str(e)}

def soap_buscar_processo_generico(session, numero_processo: str, timeout=60, debug=False) -> str:
    """
    Busca genérica do processo sem especificar classe processual específica.
    Permite que o ESAJ encontre o processo em qualquer instância/classe.
    """
    xml_data = f'''
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/" xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
        <soapenv:Header/>
        <soapenv:Body>
            <ser:consultarProcesso>
                <tip:idConsultante>{WS_USER}</tip:idConsultante>
                <tip:senhaConsultante>{WS_PASS}</tip:senhaConsultante>
                <tip:numeroProcesso>{numero_processo}</tip:numeroProcesso>
                <tip:movimentos>true</tip:movimentos>
                <tip:incluirDocumentos>true</tip:incluirDocumentos>
            </ser:consultarProcesso>
        </soapenv:Body>
    </soapenv:Envelope>'''.strip()

    if debug:
        print(f"[DEBUG] Busca genérica para processo: {numero_processo}")
    
    r = session.post(URL_WSDL, data=xml_data, timeout=timeout)
    r.raise_for_status()
    return r.text

def soap_consultar_processo(session, numero_processo: str, timeout=60, debug=False) -> str:
    xml_data = f'''
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/" xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
        <soapenv:Header/>
        <soapenv:Body>
            <ser:consultarProcesso>
                <tip:idConsultante>{WS_USER}</tip:idConsultante>
                <tip:senhaConsultante>{WS_PASS}</tip:senhaConsultante>
                <tip:numeroProcesso>{numero_processo}</tip:numeroProcesso>
                <tip:movimentos>true</tip:movimentos>
                <tip:incluirDocumentos>true</tip:incluirDocumentos>
            </ser:consultarProcesso>
        </soapenv:Body>
    </soapenv:Envelope>'''.strip()

    if debug:
        print(f"[DEBUG] XML sendo enviado:\n{xml_data}")
    
    r = session.post(URL_WSDL, data=xml_data, timeout=timeout)
    r.raise_for_status()
    return r.text

def consultar_todas_instancias(session, numero_processo: str, timeout=60, debug=False) -> List[Dict[str, Any]]:
    """
    Busca o processo usando consulta genérica que permite o ESAJ 
    encontrar automaticamente em todas as instâncias/classes processuais
    """
    resultados = []
    
    try:
        if debug:
            print(f"[DEBUG] Buscando processo {numero_processo} em todas as instâncias...")
        
        # Faz busca genérica (sem especificar classe processual)
        xml_response = soap_buscar_processo_generico(session, numero_processo, timeout, debug)
        
        # Verifica se a resposta indica sucesso
        if '<sucesso>true</sucesso>' in xml_response:
            info_instancia = extrair_info_instancia(xml_response)
            
            # Determina o tipo de instância baseado nos dados retornados
            segmento = info_instancia.get('competencia', '')
            grau_estimado = info_instancia.get('grau_estimado', 1)
            
            # Classifica a instância baseado nos movimentos e dados
            if grau_estimado >= 2 or any(termo in str(info_instancia.get('movimentos_instancia', [])).lower() 
                                        for termo in ['recurso', 'apelação', 'tribunal', 'segunda instância']):
                instancia_tipo = 'superior'
                descricao = 'Instância Superior (2ª ou Superior)'
            else:
                instancia_tipo = 'primeira'
                descricao = 'Primeira Instância'
            
            resultado = {
                'instancia': instancia_tipo,
                'descricao': descricao,
                'numero_consultado': numero_processo,
                'xml_content': xml_response,
                'info': info_instancia,
                'sucesso': True,
                'tem_documentos': '<documento' in xml_response.lower(),
                'tipo': 'generico'
            }
            
            if debug:
                docs_info = "com documentos" if resultado['tem_documentos'] else "sem documentos"
                print(f"[DEBUG] ✓ {descricao}: {len(xml_response)} chars, {docs_info}")
                print(f"[DEBUG] Competência: {info_instancia.get('competencia', 'N/A')}")
                print(f"[DEBUG] Código Localidade: {info_instancia.get('codigoLocalidade', 'N/A')}")
            
            resultados.append(resultado)
            
        else:
            if debug:
                print(f"[DEBUG] ✗ Processo {numero_processo} não encontrado em nenhuma instância")
                
    except requests.exceptions.Timeout:
        if debug:
            print(f"[DEBUG] ⏱ Timeout na busca do processo {numero_processo}")
    except requests.exceptions.HTTPError as e:
        if debug:
            print(f"[DEBUG] ✗ Erro HTTP na busca: {e}")
    except Exception as e:
        if debug:
            print(f"[DEBUG] ✗ Erro na busca: {type(e).__name__}: {e}")
    
    return resultados

def extrair_docs_info(xml_text: str) -> List[Dict[str, Any]]:
    """
    Extrai docs do XML com:
      - id (str)
      - tipo_documento (str|None)  [= cdcategoria]
      - ordem_insercao (int|None)  [se houver 'ordem']
      - data_inclusao (datetime|None) [dataInclusao / dataHoraInclusao / dataHora / data]
      - ord_xml (int)  [posição de varredura, fallback estável]
    """
    root = ET.fromstring(xml_text)
    docs: List[Dict[str, Any]] = []
    ord_xml = 0

    for elem in root.iter():
        # idDocumento pode ser atributo OU nó filho
        doc_id = elem.attrib.get("idDocumento") or elem.attrib.get("id")
        if not doc_id:
            doc_id = _first_desc_text(elem, "idDocumento")
        if not doc_id:
            continue

        ord_xml += 1

        # tipoDocumento idem (pode estar como atributo ou filho). É o cdcategoria.
        tipo = elem.attrib.get("tipoDocumento")
        if not tipo:
            tipo = _first_desc_text(elem, "tipoDocumento")

        # ordem (se existir)
        ordem_txt = _first_desc_text(elem, "ordem")
        ordem_int = int(ordem_txt) if (ordem_txt and ordem_txt.isdigit()) else None

        # datas
        dt_txt = (
            _first_desc_text(elem, "dataJuntada")
            or _first_desc_text(elem, "dataHoraJuntada")
            or _first_desc_text(elem, "dataInclusao")
            or _first_desc_text(elem, "dataHoraInclusao")
            or _first_desc_text(elem, "dataHora")
            or _first_desc_text(elem, "data")
        )
        if not dt_txt:
            for attr_key in (
                "dataJuntada",
                "dataHoraJuntada",
                "dataInclusao",
                "dataHoraInclusao",
                "dataHora",
                "data",
            ):
                attr_val = elem.attrib.get(attr_key)
                if attr_val:
                    dt_txt = attr_val.strip()
                    break
        dt_incl = _parse_iso_date_maybe(dt_txt)

        docs.append({
            "id": doc_id,
            "tipo_documento": tipo,
            "ordem_insercao": ordem_int,
            "data_inclusao": dt_incl,
            "data_texto": dt_txt,
            "ord_xml": ord_xml,
        })

    # Dedup por id (mantém o 1º e enriquece se vier mais info depois)
    seen: Dict[str, Dict[str, Any]] = {}
    merged: List[Dict[str, Any]] = []
    for d in docs:
        i = d["id"]
        if i not in seen:
            seen[i] = d
            merged.append(d)
        else:
            prev = seen[i]
            if not prev.get("tipo_documento") and d.get("tipo_documento"):
                prev["tipo_documento"] = d["tipo_documento"]
            if prev.get("ordem_insercao") is None and d.get("ordem_insercao") is not None:
                prev["ordem_insercao"] = d["ordem_insercao"]
            if prev.get("data_inclusao") is None and d.get("data_inclusao") is not None:
                prev["data_inclusao"] = d["data_inclusao"]
            if not prev.get("data_texto") and d.get("data_texto"):
                prev["data_texto"] = d["data_texto"]
    return merged

def soap_baixar_conteudos(session, numero_processo: str, lista_ids: List[str], timeout=120) -> str:
    xml_data = f'''
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/" xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
        <soapenv:Header/>
        <soapenv:Body>
            <ser:consultarProcesso>
                <tip:idConsultante>{WS_USER}</tip:idConsultante>
                <tip:senhaConsultante>{WS_PASS}</tip:senhaConsultante>
                <tip:numeroProcesso>{numero_processo}</tip:numeroProcesso>
                {''.join(f'<tip:documento>{i}</tip:documento>' for i in lista_ids)}
            </ser:consultarProcesso>
        </soapenv:Body>
    </soapenv:Envelope>'''.strip()
    r = session.post(URL_WSDL, data=xml_data, timeout=timeout)
    r.raise_for_status()
    return r.text

def decode_conteudos_base64(xml_text: str) -> List[str]:
    return re.findall(REGEX_CONTEUDO, xml_text)

# =========================
# Utilidades de arquivo
# =========================
def limpar_processo(raw):
    cleaned = re.sub(r'[^\d]', '', (raw or '').strip())
    # Trunca para os primeiros 20 dígitos se tiver mais que 20
    return cleaned[:20] if len(cleaned) > 20 else cleaned

def _dirs(base_dir, modo_pasta, numero):
    if modo_pasta == "unica":
        # Salva diretamente na pasta selecionada (sem criar subpastas documentos_pdf/documentos_txt)
        pasta_pdf = base_dir
        pasta_txt = base_dir
        pasta_xml = base_dir
    else:
        pasta_pdf = os.path.join(base_dir, "processo_pdf", numero)
        pasta_txt = os.path.join(base_dir, "processo_txt", numero)
        pasta_xml = os.path.join(base_dir, "processo_xml", numero)
    os.makedirs(pasta_pdf, exist_ok=True)
    os.makedirs(pasta_txt, exist_ok=True)
    os.makedirs(pasta_xml, exist_ok=True)
    return pasta_pdf, pasta_txt, pasta_xml

def _sanitize_filename(s: str) -> str:
    s = s.strip().replace("/", "-").replace("\\", "-").replace(":", "-")
    s = re.sub(r'\s+', ' ', s)
    s = re.sub(r'[<>|"?*]', '-', s)
    return s.strip()

def _is_rtf_content(data: bytes) -> bool:
    """Verifica se os bytes representam um arquivo RTF"""
    try:
        # RTF sempre começa com {\rtf
        if data.startswith(b'{\\rtf'):
            return True
        # Também verifica se contém texto RTF típico
        data_str = data[:1000].decode('latin-1', errors='ignore').lower()
        return '\\rtf' in data_str and '{' in data_str
    except:
        return False

def salvar_arquivos(base_dir, modo_pasta, numero, base_filename, pdf_bytes, save_mode):
    """
    save_mode: 'pdf' | 'pdf_txt' | 'txt'
    Retorna (pdf_path_ou_None, txt_path_ou_None)
    """
    pasta_pdf, pasta_txt, _ = _dirs(base_dir, modo_pasta, numero)
    base_filename = _sanitize_filename(base_filename)
    
    # Verifica se é RTF disfarçado de PDF
    is_rtf = _is_rtf_content(pdf_bytes)
    
    if is_rtf:
        # Salva como RTF em vez de PDF
        pdf_path = os.path.join(pasta_pdf, f"{base_filename}.rtf")
        txt_path = os.path.join(pasta_txt, f"{base_filename}.txt")
    else:
        # Salva como PDF normalmente
        pdf_path = os.path.join(pasta_pdf, f"{base_filename}.pdf")
        txt_path = os.path.join(pasta_txt, f"{base_filename}.txt")

    pdf_saved = None
    txt_saved = None

    if save_mode in ("pdf", "pdf_txt"):
        with open(pdf_path, "wb") as f:
            f.write(pdf_bytes)
        pdf_saved = pdf_path

    if save_mode in ("pdf_txt", "txt"):
        md_text = None
        
        if is_rtf:
            # Para arquivos RTF, extrai texto diretamente
            try:
                # Tenta decodificar como RTF/texto puro
                try:
                    md_text = pdf_bytes.decode('utf-8', errors='ignore')
                except:
                    md_text = pdf_bytes.decode('latin-1', errors='ignore')
                
                # Remove códigos RTF básicos para melhor legibilidade
                if md_text.startswith('{\\rtf'):
                    # Remove códigos RTF mais comuns
                    import re
                    md_text = re.sub(r'\\[a-z]+\d*', ' ', md_text)  # Remove comandos RTF
                    md_text = re.sub(r'[{}]', '', md_text)  # Remove chaves
                    md_text = re.sub(r'\s+', ' ', md_text)  # Normaliza espaços
                    md_text = md_text.strip()
                    
            except Exception as e:
                md_text = f"[ERRO] Não foi possível extrair texto do RTF: {e}"
        else:
            # Para arquivos PDF, usa a lógica existente
            # Tenta extrair markdown do arquivo salvo; se não salvou, usa temporário com caminho ASCII
            try:
                if save_mode != "txt" and pdf_saved is not None:
                    md_text = pymupdf4llm.to_markdown(pdf_path)
                else:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(pdf_bytes)
                        temp_pdf = tmp.name
                    try:
                        md_text = pymupdf4llm.to_markdown(temp_pdf)
                    finally:
                        try:
                            os.remove(temp_pdf)
                        except OSError:
                            pass
            except Exception:
                # Fallback 1: usar um temporário mesmo quando o PDF foi salvo (problemas de caminho unicode)
                try:
                    with tempfile.NamedTemporaryFile(delete=False, suffix=".pdf") as tmp:
                        tmp.write(pdf_bytes)
                        temp_pdf = tmp.name
                    try:
                        md_text = pymupdf4llm.to_markdown(temp_pdf)
                    finally:
                        try:
                            os.remove(temp_pdf)
                        except OSError:
                            pass
                except Exception:
                    # Fallback 2: extrair texto simples via PyMuPDF diretamente dos bytes
                    try:
                        texto_simples = []
                        with fitz.open(stream=pdf_bytes, filetype="pdf") as doc:
                            for page in doc:
                                texto_simples.append(page.get_text("text"))
                        md_text = "\n\n".join(texto_simples)
                    except Exception:
                        md_text = None

        if md_text is not None:
            with open(txt_path, "w", encoding="utf-8") as f:
                f.write(md_text)
            txt_saved = txt_path

    return pdf_saved, txt_saved

def salvar_xml_processo(base_dir, modo_pasta, numero, xml_content):
    """
    Salva o XML completo do processo
    Retorna o caminho do arquivo XML salvo ou None se houver erro
    """
    try:
        _, _, pasta_xml = _dirs(base_dir, modo_pasta, numero)
        xml_filename = f"{numero}_processo_completo.xml"
        xml_path = os.path.join(pasta_xml, xml_filename)
        
        with open(xml_path, "w", encoding="utf-8") as f:
            f.write(xml_content)
        
        return xml_path
    except Exception:
        return None


def mesclar_pdfs(ord_paths: List[str], saida: str, log_queue=None):
    if not ord_paths:
        return
    
    # Filtra apenas arquivos PDF reais (exclui RTF)
    pdf_paths = [p for p in ord_paths if p.endswith('.pdf')]
    rtf_count = len(ord_paths) - len(pdf_paths)
    
    if rtf_count > 0 and log_queue:
        log_queue.put(f"[INFO] {rtf_count} arquivo(s) RTF excluído(s) da mesclagem de PDFs")
    
    if not pdf_paths:
        if log_queue:
            log_queue.put(f"[AVISO] Nenhum arquivo PDF válido para mesclar")
        return False
    
    with fitz.open() as destino:
        for p in pdf_paths:
            try:
                with fitz.open(p) as src:
                    destino.insert_pdf(src)
            except Exception:
                if log_queue:
                    log_queue.put(f"[AVISO] Falha ao mesclar {p}")
                pass
        # Só salva se o documento tiver pelo menos uma página
        if destino.page_count > 0:
            destino.save(saida, deflate=True)
            return True
        else:
            if log_queue:
                log_queue.put(f"[AVISO] Não foi possível criar PDF juntado - nenhuma página válida encontrada")
            return False

# =========================
# Núcleo: selecionar, ordenar e baixar COMPLETO
# =========================
def _ordenar_docs(docs: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    # chave: ordem_insercao → data_inclusao → ord_xml
    return sorted(
        docs,
        key=lambda d: (
            d.get("ordem_insercao") if d.get("ordem_insercao") is not None else float('inf'),
            d.get("data_inclusao") or datetime.max,
            d.get("ord_xml") or 10**9,
        )
    )

def _download_em_ordem_com_fallback(session, numero: str, ids_ordenados: List[str], timeout: int, log_queue) -> List[Tuple[str, bytes]]:
    """
    Tenta baixar todos de uma vez respeitando a ordem solicitada.
    Se vier menos payloads do que IDs, rebusca os faltantes 1-a-1 mantendo a ordem.
    Retorna lista [(id, pdf_bytes)] na ordem dos ids_ordenados.
    """
    if not ids_ordenados:
        return []

    # 1) tentativa em lote
    xml_download = soap_baixar_conteudos(session, numero, ids_ordenados, timeout=timeout)
    payloads = decode_conteudos_base64(xml_download)

    resultados: Dict[str, bytes] = {}
    for doc_id, payload in zip(ids_ordenados, payloads):
        try:
            resultados[doc_id] = base64.b64decode(payload)
        except Exception:
            pass

    # 2) fallback individual para os que faltarem
    faltantes = [doc_id for doc_id in ids_ordenados if doc_id not in resultados]
    if faltantes:
        log_queue.put(f"[AVISO] {len(faltantes)} documento(s) não vieram no lote; tentando individualmente...")
        for doc_id in faltantes:
            try:
                xml_one = soap_baixar_conteudos(session, numero, [doc_id], timeout=timeout)
                pay_one = decode_conteudos_base64(xml_one)
                if pay_one:
                    resultados[doc_id] = base64.b64decode(pay_one[0])
            except Exception as e:
                log_queue.put(f"[ERRO] Falha no fallback do ID {doc_id}: {e}")

    # 3) monta lista final na ordem pedida (ignorando os que realmente não vieram)
    ordered = [(doc_id, resultados[doc_id]) for doc_id in ids_ordenados if doc_id in resultados]
    return ordered


def _string_starts_with_year(text: Optional[str], year: str) -> bool:
    if not text:
        return False
    text = text.strip()
    if text.startswith(year):
        return True
    digits = re.sub(r"\D", "", text)
    return digits.startswith(year)


def _doc_matches_year(doc: Dict[str, Any], years: List[str]) -> bool:
    if not years:
        return True

    # Pré-processa para busca rápida
    year_ints: List[Optional[int]] = []
    for y in years:
        try:
            year_ints.append(int(y))
        except ValueError:
            year_ints.append(None)

    dt = doc.get("data_inclusao")
    if isinstance(dt, datetime):
        for year_int in year_ints:
            if year_int is not None and dt.year == year_int:
                return True

    for year in years:
        if _string_starts_with_year(doc.get("data_texto"), year):
            return True
        if _string_starts_with_year(doc.get("id"), year):
            return True

    return False

# =========================
# Worker de processamento
# =========================
def processar_processos(cfg, log_queue, progress_callback):
    session = criar_sessao_com_retry()

    total = min(cfg["max_processos"], len(cfg["processos"]))
    cont = 0

    def finalizar_processo(usar_pausa: bool = True):
        nonlocal cont
        cont += 1
        progress_callback(cont, total)
        if usar_pausa and cont < total:
            time.sleep(cfg["pausa"])

    # Set de tipos selecionados
    tipos_selecionados = {k for k, v in cfg["categorias"].items() if v}
    filtrar_por_ano = bool(cfg.get("filtrar_por_ano"))
    anos_filtro: List[str] = cfg.get("anos_filtro") or []
    anos_filtro = [a.strip() for a in anos_filtro if a.strip()]
    anos_texto = ", ".join(anos_filtro)
    if filtrar_por_ano and anos_filtro:
        log_queue.put(f"Filtro de ano ativo: {anos_texto}")

    for idx, raw in enumerate(cfg["processos"]):
        if cont >= cfg["max_processos"]:
            break

        numero = limpar_processo(raw)
        if not numero:
            log_queue.put(f"[AVISO] Linha {idx+1} vazia/ inválida — pulando.")
            finalizar_processo(usar_pausa=False)
            continue

        log_queue.put("="*60)
        log_queue.put(f"Processando {numero} ({cont+1}/{total})")

        try:
            # 1) consulta (busca em todas instâncias ou simples)
            if cfg["multiplas_instancias"]:
                log_queue.put("Buscando processo em todas as instâncias automaticamente...")
                log_queue.put(f"[DEBUG] Timeout configurado: {cfg['timeout_consulta']}s")
                resultados_instancias = consultar_todas_instancias(session, numero, timeout=cfg["timeout_consulta"], debug=True)
                
                if not resultados_instancias:
                    log_queue.put(f"[AVISO] Processo {numero} não encontrado em nenhuma instância")
                    finalizar_processo()
                    continue
                
                resultado = resultados_instancias[0]  # Só teremos 1 resultado na busca genérica
                docs_info = "com documentos" if resultado['tem_documentos'] else "sem documentos"
                log_queue.put(f"✓ Processo encontrado em: {resultado['descricao']} ({docs_info})")
                log_queue.put(f"  Competência: {resultado['info'].get('competencia', 'N/A')}")
                log_queue.put(f"  Localidade: {resultado['info'].get('codigoLocalidade', 'N/A')}")
                
                # 1.5) salvar XML
                if cfg["save_xml"] or cfg["save_mode"] == "xml_only":
                    xml_path = salvar_xml_processo(cfg["base_dir"], cfg["modo_pasta"], numero, resultado['xml_content'])
                    if xml_path:
                        log_queue.put(f"XML salvo: {xml_path}")

                # Se for modo "Somente XML", pula o processamento de documentos
                if cfg["save_mode"] == "xml_only":
                    finalizar_processo()
                    continue
                
                xml_consulta = resultado['xml_content']
                
            else:
                log_queue.put("Consultando XML do processo...")
                log_queue.put(f"[DEBUG] Timeout configurado: {cfg['timeout_consulta']}s")
                log_queue.put(f"[DEBUG] Fazendo requisição SOAP para: {URL_WSDL}")
                xml_consulta = soap_consultar_processo(session, numero, timeout=cfg["timeout_consulta"], debug=True)
                log_queue.put(f"[DEBUG] XML recebido com {len(xml_consulta)} caracteres")

                # 1.5) salvar XML se solicitado
                if cfg["save_xml"] or cfg["save_mode"] == "xml_only":
                    xml_path = salvar_xml_processo(cfg["base_dir"], cfg["modo_pasta"], numero, xml_consulta)
                    if xml_path:
                        log_queue.put(f"XML do processo salvo: {xml_path}")

                # Se for modo "Somente XML", pula o processamento de documentos
                if cfg["save_mode"] == "xml_only":
                    finalizar_processo()
                    continue

            # 2) extrai todos os documentos
            todos_docs = extrair_docs_info(xml_consulta)
            if not todos_docs:
                log_queue.put(f"[INFO] Nenhum documento encontrado em {numero}.")
                finalizar_processo(usar_pausa=False)
                continue

            docs_pos_ano = todos_docs
            if filtrar_por_ano and anos_filtro:
                docs_pos_ano = [d for d in todos_docs if _doc_matches_year(d, anos_filtro)]
                if not docs_pos_ano:
                    log_queue.put(f"[INFO] Nenhum documento dos anos {anos_texto} em {numero}.")
                    finalizar_processo(usar_pausa=False)
                    continue

            # 3) filtra pelos tipos selecionados (cdcategoria)
            docs_filtrados = [d for d in docs_pos_ano if d.get("tipo_documento") in tipos_selecionados]
            if not docs_filtrados:
                log_queue.put(f"[INFO] Nenhum doc das categorias selecionadas em {numero}.")
                finalizar_processo(usar_pausa=False)
                continue

            # 4) ordena
            docs_ordenados = _ordenar_docs(docs_filtrados)
            ids_ordenados = [d["id"] for d in docs_ordenados]
            log_queue.put(f"IDs selecionados (ordenados): {ids_ordenados}")

            # 5) baixa em ordem (com fallback 1-a-1 se faltar)
            id_bytes_list = _download_em_ordem_com_fallback(
                session, numero, ids_ordenados, cfg["timeout_download"], log_queue
            )

            if not id_bytes_list:
                log_queue.put("[INFO] Não foi possível obter conteúdos (mesmo com fallback).")
                finalizar_processo(usar_pausa=False)
                continue

            # 6) salvar com numeração "N. Descrição"
            pasta_pdf, _, _ = _dirs(cfg["base_dir"], cfg["modo_pasta"], numero)
            saved_paths = []

            ordinal = 0
            for doc_id, pdf_bytes in id_bytes_list:
                # encontra o doc correspondente
                d = next((x for x in docs_ordenados if x["id"] == doc_id), None)
                if not d:
                    continue
                ordinal += 1
                tipo = d.get("tipo_documento") or "documento"
                descricao = CATEGORIAS_MAP.get(str(tipo), f"Documento {tipo}")
                if cfg["modo_pasta"] == "unica":
                    base_filename = f"{numero} - {ordinal}. {descricao}"
                else:
                    base_filename = f"{ordinal}. {descricao}"

                pdf_path, txt_path = salvar_arquivos(
                    base_dir=cfg["base_dir"],
                    modo_pasta=cfg["modo_pasta"],
                    numero=numero,
                    base_filename=base_filename,
                    pdf_bytes=pdf_bytes,
                    save_mode=cfg["save_mode"]
                )
                if pdf_path:
                    if pdf_path.endswith('.rtf'):
                        log_queue.put(f"RTF detectado e salvo: {pdf_path}")
                    else:
                        log_queue.put(f"PDF salvo: {pdf_path}")
                    saved_paths.append(pdf_path)
                if txt_path:
                    log_queue.put(f"Texto salvo: {txt_path}")

            # 7) (opcional) juntar PDFs do processo
            if cfg["merge_pdfs"] and saved_paths:
                saida_merge = os.path.join(pasta_pdf, f"{numero}_JUNTADO.pdf")
                if mesclar_pdfs(saved_paths, saida_merge, log_queue):
                    log_queue.put(f"PDF juntado criado: {saida_merge}")

            finalizar_processo()

        except requests.exceptions.Timeout as e:
            log_queue.put(f"[TIMEOUT] Processo {numero} - Tempo limite de {cfg['timeout_consulta']}s excedido.")
            log_queue.put(f"[TIMEOUT] Detalhes: {e}")
            time.sleep(3)
            finalizar_processo(usar_pausa=False)
        except requests.exceptions.ConnectionError as e:
            log_queue.put(f"[CONEXÃO] Erro de conexão para processo {numero}: {e}")
            time.sleep(3)
            finalizar_processo(usar_pausa=False)
        except requests.exceptions.HTTPError as e:
            log_queue.put(f"[HTTP] Erro HTTP para processo {numero}: {e}")
            time.sleep(3)
            finalizar_processo(usar_pausa=False)
        except Exception as e:
            log_queue.put(f"[ERRO] Processo {numero}: {type(e).__name__}: {e}")
            time.sleep(2)
            finalizar_processo(usar_pausa=False)

    log_queue.put("")
    log_queue.put(f"✔ Finalizado. Processos processados: {cont}/{total}")

# =========================
# Interface Tkinter
# =========================
class ESAJApp(tk.Tk):
    def __init__(self):
        super().__init__()
        self.title("ESAJ Downloader — PGE/MS")
        self.geometry("1040x780")

        self.log_queue = queue.Queue()
        self.worker_thread = None

        # Variáveis de estado
        self.base_dir = tk.StringVar(value=os.getcwd())
        self.modo_pasta = tk.StringVar(value="unica")      # 'unica' | 'subpasta'
        self.save_mode = tk.StringVar(value="pdf_txt")     # 'pdf' | 'pdf_txt' | 'txt'
        self.max_processos = tk.IntVar(value=200)
        self.timeout_consulta = tk.IntVar(value=60)
        self.timeout_download = tk.IntVar(value=120)
        self.pausa = tk.DoubleVar(value=2.0)
        self.merge_pdfs = tk.BooleanVar(value=False)
        self.save_xml = tk.BooleanVar(value=False)
        self.multiplas_instancias = tk.BooleanVar(value=False)
        self.filtrar_por_ano = tk.BooleanVar(value=False)
        self.ano_filtro = tk.StringVar(value="")

        # Checkboxes por categoria (ativo por padrão Petição e Sentença)
        self.categorias_vars: Dict[str, tk.BooleanVar] = {
            cod: tk.BooleanVar(value=(cod in {"9500", "8"}))
            for cod in CATEGORIAS_MAP.keys()
        }

        self._montar_ui()
        self.after(150, self._drain_log_queue)

    def _montar_ui(self):
        top = ttk.Frame(self)
        top.pack(side=tk.TOP, fill=tk.X, padx=10, pady=10)

        # Pasta de saída
        path_frame = ttk.Frame(top)
        path_frame.pack(side=tk.TOP, fill=tk.X)
        ttk.Label(path_frame, text="Pasta de saída:").pack(side=tk.LEFT)
        ttk.Entry(path_frame, textvariable=self.base_dir, width=80).pack(side=tk.LEFT, padx=6)
        ttk.Button(path_frame, text="Escolher...", command=self._escolher_pasta).pack(side=tk.LEFT)

        # Organização
        org_frame = ttk.LabelFrame(top, text="Organização de arquivos")
        org_frame.pack(side=tk.TOP, fill=tk.X, pady=8)
        ttk.Radiobutton(org_frame, text="Pasta única (usa a pasta escolhida)", value="unica", variable=self.modo_pasta).pack(side=tk.LEFT, padx=6, pady=4)
        ttk.Radiobutton(org_frame, text="Subpastas por processo (processo_pdf / processo_txt / processo_xml)", value="subpasta", variable=self.modo_pasta).pack(side=tk.LEFT, padx=6, pady=4)

        # Categorias (checkboxes)
        cats_frame = ttk.LabelFrame(top, text="Categorias a baixar (cdcategoria / descrição)")
        cats_frame.pack(side=tk.TOP, fill=tk.X, pady=8)
        # Controles selecionar/limpar
        btns = ttk.Frame(cats_frame)
        btns.grid(row=0, column=0, columnspan=3, sticky="w", padx=4, pady=(4,0))
        ttk.Button(btns, text="Selecionar tudo", command=self._select_all).pack(side=tk.LEFT, padx=4)
        ttk.Button(btns, text="Limpar tudo", command=self._clear_all).pack(side=tk.LEFT, padx=4)

        # Lista de checkboxes em 3 colunas
        cols = 3
        row = 1
        col = 0
        for cod, desc in sorted(CATEGORIAS_MAP.items(), key=lambda x: int(x[0])):
            cb = ttk.Checkbutton(cats_frame, text=f"{cod} — {desc}", variable=self.categorias_vars[cod])
            cb.grid(row=row, column=col, sticky="w", padx=6, pady=3)
            col += 1
            if col >= cols:
                col = 0
                row += 1

        # Opções
        opt_frame = ttk.LabelFrame(top, text="Opções")
        opt_frame.pack(side=tk.TOP, fill=tk.X, pady=8)
        ttk.Checkbutton(opt_frame, text="Juntar PDFs por processo (ordem cronológica)", variable=self.merge_pdfs).pack(side=tk.LEFT, padx=6, pady=4)
        ttk.Checkbutton(opt_frame, text="Salvar XML completo do processo", variable=self.save_xml).pack(side=tk.LEFT, padx=6, pady=4)
        ttk.Checkbutton(opt_frame, text="Busca automática em todas instâncias", variable=self.multiplas_instancias).pack(side=tk.LEFT, padx=6, pady=4)
        year_frame = ttk.Frame(opt_frame)
        year_frame.pack(side=tk.LEFT, padx=6, pady=4)
        ttk.Checkbutton(
            year_frame,
            text="Filtrar por ano:",
            variable=self.filtrar_por_ano,
            command=self._update_year_entry_state,
        ).pack(side=tk.LEFT)
        self.entry_ano = ttk.Entry(year_frame, textvariable=self.ano_filtro, width=6)
        self.entry_ano.pack(side=tk.LEFT, padx=(4, 0))

        # Formato de salvamento
        fmt = ttk.LabelFrame(top, text="Formato de salvamento")
        fmt.pack(side=tk.TOP, fill=tk.X, pady=8)
        ttk.Radiobutton(fmt, text="PDF", value="pdf", variable=self.save_mode).pack(side=tk.LEFT, padx=6, pady=4)
        ttk.Radiobutton(fmt, text="PDF + TXT (Markdown)", value="pdf_txt", variable=self.save_mode).pack(side=tk.LEFT, padx=6, pady=4)
        ttk.Radiobutton(fmt, text="Somente TXT (Markdown)", value="txt", variable=self.save_mode).pack(side=tk.LEFT, padx=6, pady=4)
        ttk.Radiobutton(fmt, text="Somente XML", value="xml_only", variable=self.save_mode).pack(side=tk.LEFT, padx=6, pady=4)

        # Avançado
        adv = ttk.LabelFrame(top, text="Avançado")
        adv.pack(side=tk.TOP, fill=tk.X, pady=8)
        ttk.Label(adv, text="Máximo de processos:").grid(row=0, column=0, padx=6, pady=4, sticky="e")
        ttk.Spinbox(adv, from_=1, to=5000, textvariable=self.max_processos, width=8).grid(row=0, column=1, padx=6, pady=4, sticky="w")

        ttk.Label(adv, text="Timeout consulta (s):").grid(row=0, column=2, padx=6, pady=4, sticky="e")
        ttk.Spinbox(adv, from_=10, to=300, textvariable=self.timeout_consulta, width=8).grid(row=0, column=3, padx=6, pady=4, sticky="w")

        ttk.Label(adv, text="Timeout download (s):").grid(row=0, column=4, padx=6, pady=4, sticky="e")
        ttk.Spinbox(adv, from_=10, to=600, textvariable=self.timeout_download, width=8).grid(row=0, column=5, padx=6, pady=4, sticky="w")

        ttk.Label(adv, text="Pausa entre processos (s):").grid(row=0, column=6, padx=6, pady=4, sticky="e")
        ttk.Spinbox(adv, from_=0, to=30, increment=0.5, textvariable=self.pausa, width=8).grid(row=0, column=7, padx=6, pady=4, sticky="w")

        # Área de entrada dos processos
        middle = ttk.Frame(self)
        middle.pack(side=tk.TOP, fill=tk.BOTH, expand=True, padx=10, pady=6)

        left = ttk.Frame(middle)
        left.pack(side=tk.LEFT, fill=tk.BOTH, expand=True)

        ttk.Label(left, text="Números de processos (um por linha — pode colar completo):").pack(anchor="w")
        self.txt_processos = ScrolledText(left, height=12, width=50)
        self.txt_processos.pack(fill=tk.BOTH, expand=True, pady=4)

        # Botões iniciar/parar
        controls = ttk.Frame(left)
        controls.pack(fill=tk.X, pady=4)
        self.btn_start = ttk.Button(controls, text="Iniciar", command=self._on_start)
        self.btn_start.pack(side=tk.LEFT, padx=4)
        self.btn_stop = ttk.Button(controls, text="Cancelar", command=self._on_cancel, state=tk.DISABLED)
        self.btn_stop.pack(side=tk.LEFT, padx=4)

        # Progresso
        prog = ttk.Frame(left)
        prog.pack(fill=tk.X, pady=4)
        self.progress = ttk.Progressbar(prog, mode="determinate")
        self.progress.pack(fill=tk.X, padx=4)
        self.lbl_prog = ttk.Label(prog, text="0/0")
        self.lbl_prog.pack(anchor="e", padx=4)

        # Log
        right = ttk.Frame(middle)
        right.pack(side=tk.LEFT, fill=tk.BOTH, expand=True, padx=(10,0))
        ttk.Label(right, text="Log:").pack(anchor="w")
        self.txt_log = ScrolledText(right, height=20)
        self.txt_log.pack(fill=tk.BOTH, expand=True)

        # Rodapé
        footer = ttk.Frame(self)
        footer.pack(side=tk.BOTTOM, fill=tk.X, padx=10, pady=6)
        ttk.Label(footer, text=f"WSDL: {URL_WSDL} | Usuário: {WS_USER}").pack(anchor="w")

        self._update_year_entry_state()

    def _select_all(self):
        for var in self.categorias_vars.values():
            var.set(True)

    def _clear_all(self):
        for var in self.categorias_vars.values():
            var.set(False)

    def _escolher_pasta(self):
        path = filedialog.askdirectory(initialdir=self.base_dir.get())
        if path:
            self.base_dir.set(path)

    def _update_year_entry_state(self):
        state = tk.NORMAL if self.filtrar_por_ano.get() else tk.DISABLED
        self.entry_ano.configure(state=state)

    def _on_start(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showwarning("Em execução", "Já existe um processamento em andamento.")
            return

        processos_raw = [ln for ln in self.txt_processos.get("1.0", "end").splitlines() if ln.strip()]
        if not processos_raw:
            messagebox.showinfo("Atenção", "Insira ao menos um número de processo (um por linha).")
            return

        # Remove duplicatas - processa cada número apenas uma vez
        processos_limpos = []
        numeros_vistos = set()
        duplicatas_removidas = 0

        for raw in processos_raw:
            numero_limpo = limpar_processo(raw)
            if numero_limpo and numero_limpo not in numeros_vistos:
                numeros_vistos.add(numero_limpo)
                processos_limpos.append(raw)  # Mantém o formato original para log
            elif numero_limpo:
                duplicatas_removidas += 1

        if duplicatas_removidas > 0:
            messagebox.showinfo("Duplicatas removidas",
                f"{duplicatas_removidas} processo(s) duplicado(s) foi(ram) removido(s).\n"
                f"Total único(s) a processar: {len(processos_limpos)}")

        processos_raw = processos_limpos

        anos_input = self.ano_filtro.get().strip()
        anos_validos: List[str] = []
        if self.filtrar_por_ano.get():
            tokens = [tok for tok in re.split(r"[\s,;]+", anos_input) if tok]
            if not tokens:
                messagebox.showinfo("Atenção", "Informe ao menos um ano ou desmarque o filtro.")
                return
            invalidos = [tok for tok in tokens if not re.fullmatch(r"\d{4}", tok)]
            if invalidos:
                anos_err = ", ".join(invalidos)
                messagebox.showinfo("Atenção", f"Os valores devem ter 4 dígitos (inválidos: {anos_err}).")
                return
            anos_validos = tokens

        cfg = {
            "processos": processos_raw,
            "modo_pasta": self.modo_pasta.get(),
            "save_mode": self.save_mode.get(),
            "base_dir": self.base_dir.get(),
            "max_processos": int(self.max_processos.get()),
            "timeout_consulta": int(self.timeout_consulta.get()),
            "timeout_download": int(self.timeout_download.get()),
            "pausa": float(self.pausa.get()),
            "merge_pdfs": bool(self.merge_pdfs.get()),
            "save_xml": bool(self.save_xml.get()),
            "multiplas_instancias": bool(self.multiplas_instancias.get()),
            "categorias": {cod: bool(var.get()) for cod, var in self.categorias_vars.items()},
            "filtrar_por_ano": bool(self.filtrar_por_ano.get()),
            "anos_filtro": anos_validos,
        }

        # Só exige categorias se não for modo "Somente XML"
        if not any(cfg["categorias"].values()) and cfg["save_mode"] != "xml_only":
            messagebox.showinfo("Atenção", "Selecione ao menos uma categoria para baixar ou escolha 'Somente XML'.")
            return

        total = min(cfg["max_processos"], len(cfg["processos"]))
        self.progress.configure(maximum=total, value=0)
        self.lbl_prog.configure(text=f"0/{total}")
        if cfg["save_mode"] == "xml_only":
            self._log("=== Iniciando processamento (modo: Somente XML) ===")
        else:
            self._log("=== Iniciando processamento (apenas categorias selecionadas, ordem garantida) ===")
        self._toggle_buttons(running=True)

        def runner():
            def progress_callback(done, total_local):
                self._update_progress(done, total_local)
            try:
                processar_processos(cfg, self.log_queue, progress_callback)
            finally:
                self._toggle_buttons(running=False)

        self.worker_thread = threading.Thread(target=runner, daemon=True)
        self.worker_thread.start()

    def _on_cancel(self):
        if self.worker_thread and self.worker_thread.is_alive():
            messagebox.showinfo("Cancelar", "Para cancelar imediatamente, feche a janela. Esta interface não interrompe threads em andamento com segurança.")
        else:
            messagebox.showinfo("Cancelar", "Não há processamento em andamento.")

    def _toggle_buttons(self, running: bool):
        self.btn_start.configure(state=tk.DISABLED if running else tk.NORMAL)
        self.btn_stop.configure(state=tk.NORMAL if running else tk.DISABLED)

    def _update_progress(self, done, total):
        try:
            self.progress.configure(value=done, maximum=total)
            self.lbl_prog.configure(text=f"{done}/{total}")
            self.update_idletasks()
        except tk.TclError:
            pass

    def _log(self, msg):
        self.txt_log.insert(tk.END, msg + "\n")
        self.txt_log.see(tk.END)

    def _drain_log_queue(self):
        try:
            while True:
                msg = self.log_queue.get_nowait()
                self._log(msg)
        except queue.Empty:
            pass
        self.after(150, self._drain_log_queue)

# =========================
# Main
# =========================
if __name__ == "__main__":
    app = ESAJApp()
    app.mainloop()
