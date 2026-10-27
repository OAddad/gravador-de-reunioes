"""
historico.py
Lista as últimas reuniões (com transcrição ou só com áudio, quando a
transcrição falhou) para a janela mostrar com Abrir, Na pasta e Refazer.
Autor: Addad
"""
import re
from dataclasses import dataclass
from datetime import datetime
from pathlib import Path

PADRAO_PASTA = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})h(\d{2})_(.+)$")
FAIXAS = ("audio_microfone", "audio_sistema")


@dataclass
class Reuniao:
    """Uma reunião gravada: texto para a lista, pasta, transcrição (se houver),
    nome do contato e data tirados do nome da pasta."""
    rotulo: str
    pasta: Path
    arquivo: Path | None
    contato: str
    data: datetime | None

    @property
    def tem_audio(self) -> bool:
        """True se ainda existem os dois áudios (WAV ou comprimido)."""
        return all(audio_da_faixa(self.pasta, f) is not None for f in FAIXAS)


def audio_da_faixa(pasta: Path, faixa: str) -> Path | None:
    """Arquivo de áudio de uma faixa: o WAV original ou, se já comprimido, o .ogg."""
    for extensao in (".wav", ".ogg"):
        caminho = Path(pasta) / f"{faixa}{extensao}"
        if caminho.exists():
            return caminho
    return None


def _ler_pasta(pasta: Path) -> tuple[str, str, datetime | None]:
    """'2026-10-27_19h49_Teste Card' vira ('27/10 19:49  Teste Card', 'Teste Card', data)."""
    m = PADRAO_PASTA.match(pasta.name)
    if not m:
        return pasta.name, pasta.name, None
    ano, mes, dia, hora, minuto, contato = m.groups()
    data = datetime(int(ano), int(mes), int(dia), int(hora), int(minuto))
    return f"{dia}/{mes} {hora}:{minuto}  {contato}", contato, data


def ultimas_reunioes(pasta_saida: Path, quantidade: int = 5) -> list[Reuniao]:
    """As `quantidade` reuniões mais recentes que têm transcrição ou áudio."""
    pasta_saida = Path(pasta_saida)
    if not pasta_saida.exists():
        return []
    reunioes = []
    for pasta in sorted(pasta_saida.iterdir(), key=lambda p: p.name, reverse=True):
        if not pasta.is_dir():
            continue
        arquivo = pasta / "transcricao.txt"
        tem_texto = arquivo.exists()
        tem_audio = any(audio_da_faixa(pasta, f) for f in FAIXAS)
        if not (tem_texto or tem_audio):
            continue
        rotulo, contato, data = _ler_pasta(pasta)
        reunioes.append(Reuniao(rotulo, pasta, arquivo if tem_texto else None, contato, data))
        if len(reunioes) == quantidade:
            break
    return reunioes
