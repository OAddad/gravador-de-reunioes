"""
test_historico.py
Testes da lista das últimas reuniões.
Rodar com: python -m unittest test_historico.py
Autor: Addad
"""
import tempfile
import unittest
from pathlib import Path

from historico import ultimas_reunioes


class TestHistorico(unittest.TestCase):
    """Garante a ordem, o limite e o rótulo das últimas reuniões."""

    def _criar(self, raiz: Path, nome: str, com_txt: bool = True) -> None:
        """Cria a pasta de uma reunião (com ou sem transcrição)."""
        pasta = raiz / nome
        pasta.mkdir()
        if com_txt:
            (pasta / "transcricao.txt").write_text("x", encoding="utf-8")

    def test_ordem_limite_e_rotulo(self):
        """Mais recente primeiro, no máximo 5, ignorando pastas sem texto."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            for i in range(7):
                self._criar(raiz, f"2026-10-2{i}_10h00_Pessoa {i}")
            self._criar(raiz, "2026-10-29_09h00_Sem texto", com_txt=False)
            r = ultimas_reunioes(raiz)
            self.assertEqual(len(r), 5)
            self.assertEqual(r[0].rotulo, "26/10 10:00  Pessoa 6")
            self.assertEqual(r[0].arquivo.name, "transcricao.txt")

    def test_pasta_inexistente(self):
        """Sem pasta de saída ainda, a lista vem vazia."""
        self.assertEqual(ultimas_reunioes(Path("/nao/existe")), [])


if __name__ == "__main__":
    unittest.main()
