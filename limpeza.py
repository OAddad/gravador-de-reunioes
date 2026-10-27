"""
limpeza.py
Apaga os áudios das reuniões antigas (padrão: mais de 30 dias) e mantém
só a transcrição, para liberar espaço. Por segurança, só apaga o áudio
de reunião que já tem transcricao.txt: se a transcrição falhou, o áudio fica.
Autor: Addad
"""
import logging
import re
from datetime import datetime, timedelta
from pathlib import Path

log = logging.getLogger("gravador")

PADRAO_DATA = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})h(\d{2})_")
ARQUIVOS_AUDIO = ("audio_microfone.wav", "audio_sistema.wav",
                  "audio_microfone.ogg", "audio_sistema.ogg")


def _data_da_reuniao(pasta: Path) -> datetime:
    """Data da reunião pelo nome da pasta (2026-10-27_19h49_Nome);
    se o nome não seguir o padrão, usa a data da transcrição."""
    m = PADRAO_DATA.match(pasta.name)
    if m:
        ano, mes, dia, hora, minuto = map(int, m.groups())
        return datetime(ano, mes, dia, hora, minuto)
    return datetime.fromtimestamp((pasta / "transcricao.txt").stat().st_mtime)


def limpar_audios_antigos(pasta_saida: Path, dias: int = 30,
                          agora: datetime | None = None) -> tuple[int, int]:
    """Apaga os áudios das reuniões com mais de `dias` dias que já têm
    transcrição. Devolve (arquivos apagados, bytes liberados).
    Com `dias` igual a 0 ou menos, não apaga nada (limpeza desligada)."""
    pasta_saida = Path(pasta_saida)
    if dias <= 0 or not pasta_saida.exists():
        return 0, 0
    limite = (agora or datetime.now()) - timedelta(days=dias)
    apagados, liberados = 0, 0
    for pasta in pasta_saida.iterdir():
        if not pasta.is_dir() or not (pasta / "transcricao.txt").exists():
            continue
        try:
            if _data_da_reuniao(pasta) >= limite:
                continue
        except (OSError, ValueError):
            continue
        for nome in ARQUIVOS_AUDIO:
            audio = pasta / nome
            if audio.exists():
                try:
                    tamanho = audio.stat().st_size
                    audio.unlink()
                    apagados += 1
                    liberados += tamanho
                except OSError as erro:
                    log.warning("Não consegui apagar %s: %s", audio, erro)
    if apagados:
        log.info("Limpeza: %d áudios apagados, %.1f GB liberados", apagados, liberados / 1024 ** 3)
    return apagados, liberados
