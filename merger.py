"""
merger.py
Junta as transcrições das duas trilhas em ordem de tempo, remove eco
(quando o microfone capta a voz da outra pessoa saindo na caixa de som)
e formata o texto final.
Autor: Addad
"""
from dataclasses import dataclass
from difflib import SequenceMatcher

PAUSA_FRASE_SEG = 0.8       # pausa entre palavras que quebra uma frase
PAUSA_AGRUPAR_SEG = 2.0      # falas seguidas do mesmo falante viram um bloco
SIMILARIDADE_ECO = 0.6


@dataclass
class Segmento:
    """Um trecho de fala: início e fim em segundos, quem falou e o texto."""
    inicio: float
    fim: float
    falante: str
    texto: str


def _se_sobrepoe(a: Segmento, b: Segmento) -> bool:
    """True se os dois trechos acontecem ao mesmo tempo."""
    return a.inicio < b.fim and b.inicio < a.fim


def _parecido(a: str, b: str) -> bool:
    """True se os textos são quase iguais (sinal de eco)."""
    return SequenceMatcher(None, a.lower(), b.lower()).ratio() >= SIMILARIDADE_ECO


def remover_eco(mic: list[Segmento], sistema: list[Segmento]) -> list[Segmento]:
    """Tira do microfone os trechos que são só o eco do áudio do sistema."""
    return [
        m for m in mic
        if not any(_se_sobrepoe(m, s) and _parecido(m.texto, s.texto) for s in sistema)
    ]


def agrupar(segmentos: list[Segmento]) -> list[Segmento]:
    """Ordena por tempo e junta falas seguidas do mesmo falante."""
    resultado: list[Segmento] = []
    for seg in sorted(segmentos, key=lambda s: s.inicio):
        ultimo = resultado[-1] if resultado else None
        if (ultimo and ultimo.falante == seg.falante
                and seg.inicio - ultimo.fim <= PAUSA_AGRUPAR_SEG):
            ultimo.fim = max(ultimo.fim, seg.fim)
            ultimo.texto = f"{ultimo.texto} {seg.texto}"
        else:
            resultado.append(Segmento(seg.inicio, seg.fim, seg.falante, seg.texto))
    return resultado


def frases(palavras: list[Segmento]) -> list[Segmento]:
    """Junta palavras de uma trilha em frases curtas, quebrando nas pausas e
    quando muda quem fala (vozes separadas no áudio do computador).
    Frases curtas permitem intercalar as duas trilhas na ordem certa."""
    resultado: list[Segmento] = []
    for p in sorted(palavras, key=lambda s: s.inicio):
        ultima = resultado[-1] if resultado else None
        if (ultima and ultima.falante == p.falante
                and p.inicio - ultima.fim <= PAUSA_FRASE_SEG):
            ultima.fim = max(ultima.fim, p.fim)
            # "resolvê" + "-la" vira "resolvê-la"; pontuação também gruda
            separador = "" if p.texto[0] in "-,.!?;:" else " "
            ultima.texto = f"{ultima.texto}{separador}{p.texto}"
        else:
            resultado.append(Segmento(p.inicio, p.fim, p.falante, p.texto))
    return resultado


def tempo(segundos: float) -> str:
    """Converte segundos para HH:MM:SS."""
    s = int(segundos)
    return f"{s // 3600:02d}:{s % 3600 // 60:02d}:{s % 60:02d}"


def montar_transcricao(mic: list[Segmento], sistema: list[Segmento]) -> list[Segmento]:
    """Pipeline completo: palavras viram frases curtas por trilha, remove o
    eco e intercala as duas trilhas em ordem cronológica."""
    frases_mic, frases_sis = frases(mic), frases(sistema)
    return agrupar(remover_eco(frases_mic, frases_sis) + frases_sis)


def formatar(segmentos: list[Segmento], cabecalho: str) -> str:
    """Gera o texto final: cabeçalho + uma linha por fala com horário e nome."""
    linhas = [cabecalho, ""]
    linhas += [f"[{tempo(s.inicio)}] {s.falante}: {s.texto}" for s in segmentos]
    if not segmentos:
        linhas.append("(nenhuma fala detectada)")
    return "\n".join(linhas) + "\n"
