"""
recorder.py
Grava o microfone e o áudio do sistema (WASAPI loopback do Windows)
em dois arquivos WAV separados, alinhados pelo relógio.
Também mede o volume de cada faixa, inclusive parado (modo monitor),
para a tela mostrar se o som está chegando antes de gravar.
Autor: Addad
"""
import threading
import time
import wave
from pathlib import Path

import numpy as np
import pyaudiowpatch as pyaudio

LARGURA_AMOSTRA = 2          # 16 bits
TOLERANCIA_SEG = 0.5         # atraso aceito antes de preencher com silêncio
GANHO_NIVEL = 4.0            # deixa a voz normal perto do meio da barra


class _Trilha:
    """Captura um dispositivo. Com `caminho`, grava num WAV e completa com
    silêncio quando o Windows para de mandar áudio (o loopback fica mudo
    quando nada toca), mantendo as duas trilhas sincronizadas.
    Sem `caminho`, só mede o volume (monitor)."""

    def __init__(self, pa: pyaudio.PyAudio, info: dict, caminho: Path | None, inicio: float):
        """Abre o dispositivo `info` e começa a capturar."""
        self.canais = int(info["maxInputChannels"]) or 1
        self.taxa = int(info["defaultSampleRate"])
        self.inicio = inicio
        self.escritos = 0
        self.nivel = 0.0
        self.trava = threading.Lock()
        self.wav = None
        if caminho is not None:
            self.wav = wave.open(str(caminho), "wb")
            self.wav.setnchannels(self.canais)
            self.wav.setsampwidth(LARGURA_AMOSTRA)
            self.wav.setframerate(self.taxa)
        self.stream = pa.open(
            format=pyaudio.paInt16,
            channels=self.canais,
            rate=self.taxa,
            input=True,
            input_device_index=info["index"],
            frames_per_buffer=1024,
            stream_callback=self._callback,
        )

    def _preencher_ate(self, quadros_alvo: int) -> None:
        """Escreve silêncio até o arquivo ter `quadros_alvo` quadros."""
        falta = quadros_alvo - self.escritos
        if falta > 0:
            self.wav.writeframes(b"\x00" * falta * self.canais * LARGURA_AMOSTRA)
            self.escritos += falta

    def _callback(self, dados, n_quadros, _info, _status):
        """Recebe cada bloco de áudio: mede o volume e, se gravando, salva."""
        amostras = np.frombuffer(dados, dtype=np.int16)
        if amostras.size:
            rms = float(np.sqrt(np.mean(amostras.astype(np.float32) ** 2))) / 32768.0
            with self.trava:
                self.nivel = max(self.nivel, min(1.0, rms * GANHO_NIVEL))
        if self.wav is not None:
            with self.trava:
                decorrido = time.monotonic() - self.inicio
                alvo = int((decorrido - TOLERANCIA_SEG) * self.taxa) - n_quadros
                self._preencher_ate(alvo)
                self.wav.writeframes(dados)
                self.escritos += n_quadros
        return (None, pyaudio.paContinue)

    def ler_nivel(self) -> float:
        """Maior volume desde a última leitura (0 a 1); zera para a próxima."""
        with self.trava:
            valor, self.nivel = self.nivel, 0.0
        return valor

    def fechar(self) -> None:
        """Para a captura e, se gravando, completa o silêncio final e fecha o WAV."""
        self.stream.stop_stream()
        self.stream.close()
        if self.wav is not None:
            with self.trava:
                decorrido = time.monotonic() - self.inicio
                self._preencher_ate(int(decorrido * self.taxa))
                self.wav.close()


def _dispositivo_loopback(pa: pyaudio.PyAudio) -> dict:
    """Acha o loopback (o que sai na caixa/fone) do dispositivo de saída padrão."""
    wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    saida = pa.get_device_info_by_index(wasapi["defaultOutputDevice"])
    if saida.get("isLoopbackDevice"):
        return saida
    for loop in pa.get_loopback_device_info_generator():
        if saida["name"] in loop["name"]:
            return loop
    raise RuntimeError(
        "Não achei o loopback da saída de áudio padrão. "
        "Confira em Configurações > Som qual é o dispositivo de saída."
    )


def _dispositivo_microfone(pa: pyaudio.PyAudio) -> dict:
    """Retorna o microfone padrão do Windows (preferindo WASAPI)."""
    wasapi = pa.get_host_api_info_by_type(pyaudio.paWASAPI)
    indice = wasapi.get("defaultInputDevice", -1)
    if indice is not None and indice >= 0:
        return pa.get_device_info_by_index(indice)
    return pa.get_default_input_device_info()


class Gravador:
    """Controla as duas trilhas (microfone e sistema): monitorar ou gravar."""

    def __init__(self):
        """Prepara o gravador parado."""
        self.pa = None
        self.trilhas: list[_Trilha] = []
        self.inicio = 0.0
        self.gravando = False

    def _abrir(self, caminho_mic: Path | None, caminho_sistema: Path | None) -> None:
        """Abre as duas trilhas (gravando se houver caminhos)."""
        self._fechar_tudo()
        self.pa = pyaudio.PyAudio()
        try:
            mic = _dispositivo_microfone(self.pa)
            sistema = _dispositivo_loopback(self.pa)
            self.inicio = time.monotonic()
            self.trilhas = [
                _Trilha(self.pa, mic, caminho_mic, self.inicio),
                _Trilha(self.pa, sistema, caminho_sistema, self.inicio),
            ]
        except Exception:
            self._fechar_tudo()
            raise

    def _fechar_tudo(self) -> None:
        """Fecha as trilhas abertas e libera o áudio do Windows."""
        for trilha in self.trilhas:
            trilha.fechar()
        self.trilhas = []
        if self.pa:
            self.pa.terminate()
            self.pa = None

    def monitorar(self) -> None:
        """Abre as duas faixas só para medir o volume (não grava nada)."""
        self.gravando = False
        self._abrir(None, None)

    def iniciar(self, caminho_mic: Path, caminho_sistema: Path) -> None:
        """Começa a gravar o microfone e o áudio do sistema ao mesmo tempo."""
        self._abrir(caminho_mic, caminho_sistema)
        self.gravando = True

    def niveis(self) -> list[float]:
        """Volume atual [microfone, sistema], de 0 a 1."""
        if len(self.trilhas) != 2:
            return [0.0, 0.0]
        return [t.ler_nivel() for t in self.trilhas]

    def segundos(self) -> float:
        """Tempo de gravação até agora."""
        return time.monotonic() - self.inicio if self.gravando else 0.0

    def parar(self) -> float:
        """Encerra a gravação (ou o monitor) e devolve a duração em segundos."""
        duracao = self.segundos()
        self._fechar_tudo()
        self.gravando = False
        return duracao
