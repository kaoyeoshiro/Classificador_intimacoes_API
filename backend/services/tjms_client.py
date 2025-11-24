import requests
from requests.adapters import HTTPAdapter
from urllib3.util.retry import Retry
from ..config import Config

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

def soap_consultar_processo(numero_processo: str, timeout=60) -> str:
    """
    Realiza a consulta do processo via SOAP no TJ-MS.
    """
    session = criar_sessao_com_retry()
    
    xml_data = f'''
    <soapenv:Envelope xmlns:soapenv="http://schemas.xmlsoap.org/soap/envelope/" xmlns:ser="http://www.cnj.jus.br/servico-intercomunicacao-2.2.2/" xmlns:tip="http://www.cnj.jus.br/tipos-servico-intercomunicacao-2.2.2">
        <soapenv:Header/>
        <soapenv:Body>
            <ser:consultarProcesso>
                <tip:idConsultante>{Config.TJMS_USER}</tip:idConsultante>
                <tip:senhaConsultante>{Config.TJMS_PASS}</tip:senhaConsultante>
                <tip:numeroProcesso>{numero_processo}</tip:numeroProcesso>
                <tip:movimentos>true</tip:movimentos>
                <tip:incluirDocumentos>true</tip:incluirDocumentos>
            </ser:consultarProcesso>
        </soapenv:Body>
    </soapenv:Envelope>'''.strip()

    response = session.post(Config.TJMS_WSDL_URL, data=xml_data, timeout=timeout)
    response.raise_for_status()
    return response.text
