"""
diarizacao.py
Separa as vozes do áudio do computador (reunião em grupo no Meet, por
exemplo) em "Pessoa 1", "Pessoa 2"... usando o sherpa-onnx, tudo local.
Depois cada palavra transcrita recebe a pessoa que estava falando, e o
app pergunta o nome de cada uma no final.
Autor: Addad
"""
import logging
import os
import tarfile
import tempfile
import wave
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

import numpy as np

from downloader import AvisoDownload, baixar_url
from merger import Segmento, frases

log = logging.getLogger("gravador")

TAXA = 16000
LIMIAR_AUTOMATICO = 0.9          # no modo "Não sei": testado para não separar demais
AMOSTRA_SEG = 8.0                # duração máxima do trecho do botão Ouvir
BASE = "https://github.com/k2-fsa/sherpa-onnx/releases/download"
URL_SEGMENTACAO = f"{BASE}/speaker-segmentation-models/sherpa-onnx-pyannote-segmentation-3-0.tar.bz2"
URL_VOZ = (f"{BASE}/speaker-recongition-models/"
           "3dspeaker_speech_campplus_sv_zh_en_16k-common_advanced.onnx")


@dataclass
class Trecho:
    """Um pedaço do áudio em que uma pessoa (número) está falando."""
    inicio: float
    fim: float
    pessoa: int


@dataclass
class Pessoa:
    """Uma voz encontrada: rótulo provisório, trecho de exemplo e o áudio dele."""
    rotulo: str
    exemplo: str
    amostra: Path | None


def garantir_modelos(pasta_modelos: Path, aviso: AvisoDownload = lambda _b, _t: None) -> tuple[Path, Path]:
    """Baixa (só na primeira vez) os dois modelos de voz (~35 MB no total)."""
    pasta = Path(pasta_modelos) / "vozes"
    pasta.mkdir(parents=True, exist_ok=True)
    segmentacao, voz = pasta / "segmentacao.onnx", pasta / "voz.onnx"
    if not voz.exists():
        baixar_url(URL_VOZ, voz, aviso)
    if not segmentacao.exists():
        with tempfile.TemporaryDirectory() as tmp:
            pacote = baixar_url(URL_SEGMENTACAO, Path(tmp) / "seg.tar.bz2", aviso)
            with tarfile.open(pacote) as tar:
                membro = next(m for m in tar.getmembers() if m.name.endswith("/model.onnx"))
                origem = tar.extractfile(membro)
                segmentacao.write_bytes(origem.read())
    return segmentacao, voz


def separar(caminho_audio: Path, pasta_modelos: Path, n_pessoas: int | None,
            progresso: Callable[[float], None] = lambda _f: None,
            aviso_download: AvisoDownload = lambda _b, _t: None) -> tuple[list[Trecho], np.ndarray]:
    """Descobre quem fala quando no áudio. `n_pessoas` None = descobrir sozinho.
    Devolve os trechos (em ordem) e o áudio em 16 kHz (para as amostras)."""
    import sherpa_onnx
    from faster_whisper.audio import decode_audio

    segmentacao, voz = garantir_modelos(pasta_modelos, aviso_download)
    nucleos = max(1, (os.cpu_count() or 2) - 1)
    config = sherpa_onnx.OfflineSpeakerDiarizationConfig(
        segmentation=sherpa_onnx.OfflineSpeakerSegmentationModelConfig(
            pyannote=sherpa_onnx.OfflineSpeakerSegmentationPyannoteModelConfig(model=str(segmentacao)),
            num_threads=nucleos),
        embedding=sherpa_onnx.SpeakerEmbeddingExtractorConfig(model=str(voz), num_threads=nucleos),
        clustering=sherpa_onnx.FastClusteringConfig(
            num_clusters=n_pessoas if n_pessoas else -1, threshold=LIMIAR_AUTOMATICO),
        min_duration_on=0.3,
        min_duration_off=0.5,
    )
    if not config.validate():
        raise RuntimeError("Configuração da separação de vozes inválida")
    separador = sherpa_onnx.OfflineSpeakerDiarization(config)
    audio = decode_audio(str(caminho_audio), sampling_rate=TAXA)

    def ao_avancar(feitos: int, total: int) -> int:
        progresso(feitos / max(total, 1))
        return 0

    resultado = separador.process(audio, callback=ao_avancar).sort_by_start_time()
    trechos = [Trecho(r.start, r.end, r.speaker) for r in resultado]
    log.info("Vozes separadas: %d trechos, %d pessoas", len(trechos), len({t.pessoa for t in trechos}))
    return trechos, audio


def _pessoa_da_palavra(palavra: Segmento, trechos: list[Trecho]) -> int | None:
    """Pessoa do trecho que contém o meio da palavra; se nenhum contém, a do mais próximo."""
    if not trechos:
        return None
    meio = (palavra.inicio + palavra.fim) / 2
    melhor, distancia = None, float("inf")
    for t in trechos:
        if t.inicio <= meio <= t.fim:
            return t.pessoa
        d = min(abs(meio - t.inicio), abs(meio - t.fim))
        if d < distancia:
            melhor, distancia = t.pessoa, d
    return melhor


def atribuir_pessoas(palavras: list[Segmento], trechos: list[Trecho]) -> list[str]:
    """Troca o falante de cada palavra por "Pessoa 1", "Pessoa 2"... (na ordem
    em que cada voz aparece). Devolve os rótulos usados, em ordem."""
    numeros: dict[int, str] = {}
    for palavra in sorted(palavras, key=lambda p: p.inicio):
        pessoa = _pessoa_da_palavra(palavra, trechos)
        if pessoa is None:
            continue
        if pessoa not in numeros:
            numeros[pessoa] = f"Pessoa {len(numeros) + 1}"
        palavra.falante = numeros[pessoa]
    return list(numeros.values())


def _salvar_amostra(audio: np.ndarray, inicio: float, fim: float, destino: Path) -> None:
    """Grava um trecho do áudio (16 kHz) num WAV para o botão Ouvir."""
    a, b = int(inicio * TAXA), int(min(fim, inicio + AMOSTRA_SEG) * TAXA)
    trecho = (np.clip(audio[a:b], -1, 1) * 32767).astype("<i2")
    with wave.open(str(destino), "wb") as w:
        w.setnchannels(1)
        w.setsampwidth(2)
        w.setframerate(TAXA)
        w.writeframes(trecho.tobytes())


def preparar_pessoas(palavras: list[Segmento], rotulos: list[str],
                     audio: np.ndarray | None, pasta: Path) -> list[Pessoa]:
    """Para cada pessoa: a frase mais longa dela (exemplo) e o áudio dessa frase."""
    pessoas = []
    for rotulo in rotulos:
        dela = frases([p for p in palavras if p.falante == rotulo])
        if not dela:
            continue
        maior = max(dela, key=lambda f: f.fim - f.inicio)
        amostra = None
        if audio is not None:
            amostra = Path(pasta) / f"amostra_{rotulo.replace(' ', '_').lower()}.wav"
            try:
                _salvar_amostra(audio, maior.inicio, maior.fim, amostra)
            except Exception:
                log.exception("Não consegui salvar a amostra de %s", rotulo)
                amostra = None
        exemplo = maior.texto if len(maior.texto) <= 90 else maior.texto[:89] + "…"
        pessoas.append(Pessoa(rotulo, exemplo, amostra))
    return pessoas


def renomear(palavras: list[Segmento], nomes: dict[str, str]) -> None:
    """Troca "Pessoa N" pelo nome que o usuário deu."""
    for palavra in palavras:
        palavra.falante = nomes.get(palavra.falante, palavra.falante)
