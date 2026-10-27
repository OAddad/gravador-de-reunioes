"""
transcriber.py
Transcreve cada trilha de áudio com o Whisper rodando local (faster-whisper).
Tenta a placa NVIDIA em modos diferentes; se nenhum funcionar, usa a CPU.
Informa o progresso (0 a 1) enquanto transcreve.
Autor: Addad
"""
import logging
import os
import site
import sys
from pathlib import Path
from typing import Callable

from downloader import AvisoDownload, garantir_modelo
from merger import Segmento

Progresso = Callable[[float], None]
log = logging.getLogger("gravador")
PASTA_MODELOS = Path(__file__).resolve().parent / "modelos"


def _preparar_cuda() -> None:
    """No Windows, as DLLs do CUDA instaladas pelo pip (nvidia-cublas-cu12 e
    nvidia-cudnn-cu12) ficam em site-packages/nvidia/*/bin; o Windows só
    as encontra se a pasta for registrada antes de carregar o Whisper."""
    if sys.platform != "win32":
        return
    for base in site.getsitepackages():
        for lib in ("cublas", "cudnn"):
            pasta = Path(base) / "nvidia" / lib / "bin"
            if pasta.is_dir():
                os.add_dll_directory(str(pasta))
                os.environ["PATH"] = str(pasta) + os.pathsep + os.environ.get("PATH", "")


_preparar_cuda()

# Ordem de tentativa: (dispositivo, tipo de cálculo)
TENTATIVAS_GPU = [("cuda", "float16"), ("cuda", "int8_float16"), ("cuda", "int8")]
TENTATIVA_CPU = ("cpu", "int8")


def _tem_gpu() -> bool:
    """True se houver placa NVIDIA E as bibliotecas CUDA instaladas.
    Sem o cuBLAS a placa até aparece, mas a transcrição falha depois."""
    try:
        import ctranslate2
        if ctranslate2.get_cuda_device_count() == 0:
            return False
        if sys.platform == "win32":
            import ctypes
            ctypes.WinDLL("cublas64_12.dll")
        return True
    except Exception as erro:
        log.info("Placa de vídeo não será usada: %s", erro)
        return False


class Transcritor:
    """Carrega o modelo uma vez e transcreve quantos arquivos precisar."""

    def __init__(self, modelo: str = "auto", idioma: str = "pt",
                 aviso_download: AvisoDownload = lambda _b, _t: None):
        """Guarda as escolhas; o modelo só é carregado no primeiro uso.
        `aviso_download(baixado, total)` recebe o progresso do download."""
        self.modelo_pedido = modelo
        self.aviso_download = aviso_download
        self.idioma = idioma
        self.modelo = None
        self.dispositivo = None

    def _nome_modelo(self, gpu: bool) -> str:
        """Resolve "auto" para o modelo certo do hardware."""
        if self.modelo_pedido != "auto":
            return self.modelo_pedido
        return "large-v3-turbo" if gpu else "small"

    def _carregar(self, so_cpu: bool = False) -> None:
        """Carrega o Whisper testando a GPU em vários modos antes da CPU.
        Na primeira vez baixa o modelo da internet (em paralelo)."""
        from faster_whisper import WhisperModel

        tentativas = [] if so_cpu or not _tem_gpu() else list(TENTATIVAS_GPU)
        tentativas.append(TENTATIVA_CPU)
        ultimo_erro = None
        for dispositivo, tipo in tentativas:
            nome = self._nome_modelo(dispositivo == "cuda")
            caminho = garantir_modelo(nome, PASTA_MODELOS, self.aviso_download)
            log.info("Carregando modelo %s em %s (%s)...", nome, dispositivo, tipo)
            try:
                self.modelo = WhisperModel(
                    str(caminho),
                    device=dispositivo,
                    compute_type=tipo,
                )
                self.dispositivo = dispositivo
                log.info("Modelo carregado em %s (%s).", dispositivo, tipo)
                return
            except Exception as erro:
                log.warning("Falhou em %s (%s): %s", dispositivo, tipo, erro)
                ultimo_erro = erro
        raise RuntimeError(f"Não consegui carregar o Whisper: {ultimo_erro}")

    def _rodar(self, caminho: Path, falante: str, progresso: Progresso) -> list[Segmento]:
        """Executa o Whisper num arquivo e devolve UMA entrada por palavra,
        com o horário exato de cada uma (os blocos do Whisper são longos
        demais para intercalar as duas trilhas na ordem certa)."""
        log.info("Transcrevendo %s", Path(caminho).name)
        trechos, info = self.modelo.transcribe(
            str(caminho),
            language=self.idioma,
            beam_size=5,
            vad_filter=True,
            condition_on_previous_text=False,
            word_timestamps=True,
        )
        total = max(info.duration, 0.001)
        resultado = []
        for t in trechos:
            progresso(min(t.end / total, 1.0))
            for p in t.words or []:
                if p.word.strip():
                    resultado.append(Segmento(p.start, p.end, falante, p.word.strip()))
        progresso(1.0)
        return resultado

    def transcrever(self, caminho: Path, falante: str,
                    progresso: Progresso = lambda _f: None) -> list[Segmento]:
        """Transcreve um arquivo. Se a GPU falhar no meio (driver, CUDA,
        memória), recarrega na CPU e tenta de novo."""
        if self.modelo is None:
            self._carregar()
        try:
            return self._rodar(caminho, falante, progresso)
        except Exception as erro:
            log.warning("Erro ao transcrever em %s: %s", self.dispositivo, erro)
            if self.dispositivo != "cuda":
                raise
            self._carregar(so_cpu=True)
            return self._rodar(caminho, falante, progresso)
