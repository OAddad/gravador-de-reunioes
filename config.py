"""
config.py
Configurações do Gravador de Reuniões e histórico de nomes já usados.
Autor: Addad
"""
import json
from pathlib import Path

PASTA_APP = Path(__file__).resolve().parent
ARQUIVO_CONFIG = PASTA_APP / "config.json"
ARQUIVO_HISTORICO = PASTA_APP / "historico_nomes.json"

PADRAO = {
    "meu_nome": "Addad",
    "pasta_saida": str(Path.home() / "Documents" / "Transcricoes"),
    # "auto" = large-v3-turbo se tiver placa NVIDIA, "small" se for só CPU.
    # Outras opções: "tiny", "base", "small", "medium", "large-v3", "large-v3-turbo"
    "modelo": "auto",
    "idioma": "pt",
    # Depois de quantos dias apagar os áudios (a transcrição fica). 0 = nunca apagar.
    "dias_manter_audio": 30,
}


def carregar_config() -> dict:
    """Lê o config.json; se não existir, cria com os valores padrão."""
    if not ARQUIVO_CONFIG.exists():
        ARQUIVO_CONFIG.write_text(
            json.dumps(PADRAO, indent=2, ensure_ascii=False), encoding="utf-8"
        )
        return dict(PADRAO)
    dados = json.loads(ARQUIVO_CONFIG.read_text(encoding="utf-8"))
    return {**PADRAO, **dados}


def salvar_config(cfg: dict) -> None:
    """Grava as configurações no config.json (ex.: quando o operador troca o nome)."""
    ARQUIVO_CONFIG.write_text(json.dumps(cfg, indent=2, ensure_ascii=False), encoding="utf-8")


def carregar_nomes() -> list[str]:
    """Retorna os nomes de contatos usados antes (mais recente primeiro)."""
    if not ARQUIVO_HISTORICO.exists():
        return []
    try:
        return json.loads(ARQUIVO_HISTORICO.read_text(encoding="utf-8"))
    except json.JSONDecodeError:
        return []


def salvar_nome(nome: str) -> list[str]:
    """Coloca o nome no topo do histórico (sem repetir) e devolve a lista nova."""
    nomes = [n for n in carregar_nomes() if n.lower() != nome.lower()]
    nomes.insert(0, nome)
    nomes = nomes[:100]
    ARQUIVO_HISTORICO.write_text(
        json.dumps(nomes, indent=2, ensure_ascii=False), encoding="utf-8"
    )
    return nomes
