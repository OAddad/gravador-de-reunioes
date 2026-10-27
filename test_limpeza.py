"""
test_limpeza.py
Testes da limpeza automática dos áudios antigos.
Rodar com: python -m unittest test_limpeza.py
Autor: Addad
"""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from limpeza import limpar_audios_antigos

AGORA = datetime(2026, 12, 1, 12, 0)


class TestLimpeza(unittest.TestCase):
    """Garante que só os áudios antigos e já transcritos são apagados."""

    def _reuniao(self, raiz: Path, nome: str, com_txt: bool = True) -> Path:
        """Cria a pasta de uma reunião com os dois áudios (e a transcrição)."""
        pasta = raiz / nome
        pasta.mkdir()
        (pasta / "audio_microfone.wav").write_bytes(b"0" * 100)
        (pasta / "audio_sistema.wav").write_bytes(b"0" * 200)
        if com_txt:
            (pasta / "transcricao.txt").write_text("texto", encoding="utf-8")
        return pasta

    def test_apaga_so_antigas_com_transcricao(self):
        """Antiga com texto: apaga áudio e mantém texto. Recente ou sem texto: não mexe."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            antiga = self._reuniao(raiz, "2026-10-01_10h00_Ana")
            recente = self._reuniao(raiz, "2026-11-20_10h00_Bia")
            falhou = self._reuniao(raiz, "2026-09-01_10h00_Caio", com_txt=False)
            apagados, liberados = limpar_audios_antigos(raiz, 30, AGORA)
            self.assertEqual((apagados, liberados), (2, 300))
            self.assertFalse((antiga / "audio_microfone.wav").exists())
            self.assertTrue((antiga / "transcricao.txt").exists())
            self.assertTrue((recente / "audio_sistema.wav").exists())
            self.assertTrue((falhou / "audio_microfone.wav").exists())

    def test_limpeza_desligada(self):
        """Com 0 dias a limpeza fica desligada e nada é apagado."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self._reuniao(raiz, "2025-01-01_10h00_Ana")
            self.assertEqual(limpar_audios_antigos(raiz, 0, AGORA), (0, 0))

    def test_pasta_inexistente(self):
        """Sem a pasta de saída ainda, não faz nada."""
        self.assertEqual(limpar_audios_antigos(Path("/nao/existe"), 30, AGORA), (0, 0))


if __name__ == "__main__":
    unittest.main()
