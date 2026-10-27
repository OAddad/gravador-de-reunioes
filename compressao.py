"""
compressao.py
Depois de transcrever, converte os áudios WAV (~1 GB por hora) para
Opus em .ogg (~15 MB por hora por faixa), um formato feito para voz.
Ainda dá para ouvir e retranscrever. O WAV só é apagado depois que o
.ogg fica pronto e com a mesma duração.
Autor: Addad
"""
import logging
from pathlib import Path

import av

log = logging.getLogger("gravador")

TAXA = 48000            # o Opus trabalha em 48 kHz
BITRATE = 32000         # 32 kbps mono: voz clara e ~14 MB por hora
TOLERANCIA_SEG = 1.0    # diferença de duração aceita entre o WAV e o .ogg
ARQUIVOS_WAV = ("audio_microfone.wav", "audio_sistema.wav")


def _duracao(caminho: Path) -> float:
    """Duração do áudio em segundos (lendo o arquivo inteiro, sem confiar no cabeçalho)."""
    with av.open(str(caminho)) as entrada:
        stream = entrada.streams.audio[0]
        ultimo = 0.0
        for pacote in entrada.demux(stream):
            if pacote.pts is not None and pacote.duration:
                ultimo = max(ultimo, float((pacote.pts + pacote.duration) * stream.time_base))
        return ultimo


def comprimir(wav: Path) -> Path:
    """Converte `wav` em .ogg (Opus mono), confere a duração e apaga o WAV.
    Devolve o caminho do .ogg. Se algo falhar, o WAV continua intacto."""
    wav = Path(wav)
    destino = wav.with_suffix(".ogg")
    parcial = wav.with_suffix(".ogg.part")
    with av.open(str(wav)) as entrada, av.open(str(parcial), "w", format="ogg") as saida:
        stream_saida = saida.add_stream("libopus", rate=TAXA, layout="mono")
        stream_saida.bit_rate = BITRATE
        conversor = av.AudioResampler(format="s16", layout="mono", rate=TAXA)
        fila = av.AudioFifo()
        tamanho = stream_saida.codec_context.frame_size or 960

        def codificar(quadro) -> None:
            for pacote in stream_saida.encode(quadro):
                saida.mux(pacote)

        def esvaziar(final: bool) -> None:
            while fila.samples >= tamanho:
                codificar(fila.read(tamanho))
            if final and fila.samples:
                codificar(fila.read(fila.samples))

        for quadro in entrada.decode(audio=0):
            quadro.pts = None
            for convertido in conversor.resample(quadro):
                fila.write(convertido)
            esvaziar(final=False)
        for convertido in conversor.resample(None):
            fila.write(convertido)
        esvaziar(final=True)
        codificar(None)

    original, comprimido = _duracao(wav), _duracao(parcial)
    if abs(original - comprimido) > TOLERANCIA_SEG:
        parcial.unlink(missing_ok=True)
        raise RuntimeError(f"Duração diferente após comprimir {wav.name}: {original:.1f}s x {comprimido:.1f}s")
    parcial.replace(destino)
    tamanho_wav = wav.stat().st_size
    wav.unlink()
    log.info("Comprimido %s: %.0f MB -> %.1f MB", wav.name, tamanho_wav / 1e6, destino.stat().st_size / 1e6)
    return destino


def comprimir_reuniao(pasta: Path) -> None:
    """Comprime os dois áudios de uma reunião (o que já estiver comprimido é pulado)."""
    for nome in ARQUIVOS_WAV:
        wav = Path(pasta) / nome
        if wav.exists():
            try:
                comprimir(wav)
            except Exception:
                log.exception("Não consegui comprimir %s (o WAV continua salvo)", wav)


def comprimir_pendentes(pasta_saida: Path) -> None:
    """Comprime os WAV das reuniões já transcritas que ficaram sem comprimir
    (ex.: o app foi fechado no meio da compressão)."""
    pasta_saida = Path(pasta_saida)
    if not pasta_saida.exists():
        return
    for pasta in pasta_saida.iterdir():
        if pasta.is_dir() and (pasta / "transcricao.txt").exists():
            for sobra in pasta.glob("*.ogg.part"):
                sobra.unlink(missing_ok=True)
            comprimir_reuniao(pasta)
