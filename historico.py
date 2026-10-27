"""
historico.py
Lista as últimas reuniões transcritas (pastas com transcricao.txt)
para a janela mostrar com os botões Abrir e Mostrar na pasta.
Autor: Addad
"""
import re
from dataclasses import dataclass
from pathlib import Path

PADRAO_PASTA = re.compile(r"^(\d{4})-(\d{2})-(\d{2})_(\d{2})h(\d{2})_(.+)$")


@dataclass
class Reuniao:
    """Uma reunião já transcrita: texto para a lista e o caminho do .txt."""
    rotulo: str
    arquivo: Path


def _rotulo(nome_pasta: str) -> str:
    """'2026-10-27_19h49_Teste Card' vira '27/10 19:49  Teste Card'."""
    m = PADRAO_PASTA.match(nome_pasta)
    if not m:
        return nome_pasta
    _ano, mes, dia, hora, minuto, contato = m.groups()
    return f"{dia}/{mes} {hora}:{minuto}  {contato}"


def ultimas_reunioes(pasta_saida: Path, quantidade: int = 5) -> list[Reuniao]:
    """As `quantidade` reuniões mais recentes que já têm transcricao.txt."""
    pasta_saida = Path(pasta_saida)
    if not pasta_saida.exists():
        return []
    reunioes = []
    for pasta in sorted(pasta_saida.iterdir(), key=lambda p: p.name, reverse=True):
        arquivo = pasta / "transcricao.txt"
        if pasta.is_dir() and arquivo.exists():
            reunioes.append(Reuniao(_rotulo(pasta.name), arquivo))
            if len(reunioes) == quantidade:
                break
    return reunioes
