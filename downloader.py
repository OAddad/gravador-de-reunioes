"""
downloader.py
Baixa os modelos do Whisper do HuggingFace em vários pedaços ao mesmo
tempo (o servidor limita a velocidade de cada conexão) e informa a
porcentagem do download.
Autor: Addad
"""
import logging
import threading
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path
from typing import Callable

log = logging.getLogger("gravador")

REPOSITORIOS = {
    "tiny": "Systran/faster-whisper-tiny",
    "base": "Systran/faster-whisper-base",
    "small": "Systran/faster-whisper-small",
    "medium": "Systran/faster-whisper-medium",
    "large-v3": "Systran/faster-whisper-large-v3",
    "large-v3-turbo": "dropbox-dash/faster-whisper-large-v3-turbo",
}
ARQUIVOS_NECESSARIOS = ("config.json", "model.bin", "tokenizer.json")
ARQUIVOS_OPCIONAIS = ("vocabulary.txt", "vocabulary.json", "preprocessor_config.json")
CONEXOES = 8
TAMANHO_BLOCO = 1024 * 1024
TIMEOUT = 30

AvisoDownload = Callable[[int, int], None]   # (bytes baixados, bytes totais)


def _url(repo: str, arquivo: str) -> str:
    """Endereço direto do arquivo no HuggingFace."""
    return f"https://huggingface.co/{repo}/resolve/main/{arquivo}"


def _consultar(url: str) -> tuple[str, int] | None:
    """Segue os redirecionamentos e devolve (endereço final, tamanho).
    None se o arquivo não existir no repositório."""
    pedido = urllib.request.Request(url, method="HEAD", headers={"User-Agent": "gravador-reunioes"})
    try:
        with urllib.request.urlopen(pedido, timeout=TIMEOUT) as resp:
            return resp.geturl(), int(resp.headers.get("Content-Length", 0))
    except urllib.error.HTTPError as erro:
        if erro.code == 404:
            return None
        raise


class _Contador:
    """Soma os bytes baixados por todas as conexões e avisa o progresso."""

    def __init__(self, total: int, aviso: AvisoDownload):
        """Começa do zero com o total esperado."""
        self.total = total
        self.baixado = 0
        self.aviso = aviso
        self.trava = threading.Lock()

    def somar(self, n: int) -> None:
        """Registra mais `n` bytes e avisa a tela."""
        with self.trava:
            self.baixado += n
            self.aviso(self.baixado, self.total)


def _baixar_pedaco(url: str, destino: Path, inicio: int, fim: int, contador: _Contador) -> None:
    """Baixa os bytes [inicio, fim] e escreve na posição certa do arquivo."""
    pedido = urllib.request.Request(
        url, headers={"Range": f"bytes={inicio}-{fim}", "User-Agent": "gravador-reunioes"}
    )
    with urllib.request.urlopen(pedido, timeout=TIMEOUT) as resp, open(destino, "r+b") as arq:
        arq.seek(inicio)
        while True:
            bloco = resp.read(TAMANHO_BLOCO)
            if not bloco:
                break
            arq.write(bloco)
            contador.somar(len(bloco))


def _baixar_arquivo(url: str, tamanho: int, destino: Path, contador: _Contador) -> None:
    """Baixa um arquivo dividido em CONEXOES pedaços paralelos."""
    parcial = destino.with_suffix(destino.suffix + ".part")
    with open(parcial, "wb") as arq:
        arq.truncate(tamanho)
    passo = -(-tamanho // CONEXOES)
    faixas = [(i, min(i + passo, tamanho) - 1) for i in range(0, tamanho, passo)]
    with ThreadPoolExecutor(max_workers=CONEXOES) as grupo:
        tarefas = [grupo.submit(_baixar_pedaco, url, parcial, a, b, contador) for a, b in faixas]
        for tarefa in tarefas:
            tarefa.result()
    if parcial.stat().st_size != tamanho:
        raise RuntimeError(f"Download incompleto de {destino.name}")
    parcial.replace(destino)


def garantir_modelo(nome: str, pasta_modelos: Path,
                    aviso: AvisoDownload = lambda _b, _t: None) -> Path:
    """Garante que o modelo está na pasta (baixa o que faltar) e devolve o caminho."""
    repo = REPOSITORIOS.get(nome)
    if repo is None:
        raise ValueError(f"Modelo desconhecido: {nome}")
    pasta = pasta_modelos / nome
    pasta.mkdir(parents=True, exist_ok=True)

    pendentes = []
    for arquivo in ARQUIVOS_NECESSARIOS + ARQUIVOS_OPCIONAIS:
        destino = pasta / arquivo
        if destino.exists():
            continue
        info = _consultar(_url(repo, arquivo))
        if info is None:
            if arquivo in ARQUIVOS_NECESSARIOS:
                raise RuntimeError(f"{arquivo} não encontrado em {repo}")
            continue
        pendentes.append((arquivo, *info))

    if not pendentes:
        return pasta
    total = sum(tamanho for _a, _u, tamanho in pendentes)
    log.info("Baixando modelo %s: %.0f MB", nome, total / 1024 / 1024)
    contador = _Contador(total, aviso)
    for arquivo, url, tamanho in pendentes:
        _baixar_arquivo(url, tamanho, pasta / arquivo, contador)
    log.info("Modelo %s baixado.", nome)
    return pasta


def baixar_url(url: str, destino: Path, aviso: AvisoDownload = lambda _b, _t: None) -> Path:
    """Baixa um arquivo qualquer (ex.: modelo de voz do GitHub) em partes paralelas."""
    destino = Path(destino)
    destino.parent.mkdir(parents=True, exist_ok=True)
    info = _consultar(url)
    if info is None:
        raise RuntimeError(f"Arquivo não encontrado: {url}")
    url_final, tamanho = info
    log.info("Baixando %s: %.0f MB", destino.name, tamanho / 1024 / 1024)
    _baixar_arquivo(url_final, tamanho, destino, _Contador(tamanho, aviso))
    return destino
