"""
test_historico.py
Testes da lista das últimas reuniões.
Rodar com: python -m unittest test_historico.py
Autor: Addad
"""
import tempfile
import unittest
from datetime import datetime
from pathlib import Path

from historico import audio_da_faixa, ultimas_reunioes


class TestHistorico(unittest.TestCase):
    """Garante a ordem, o limite, o rótulo e o que cada reunião tem."""

    def _criar(self, raiz: Path, nome: str, texto: bool = True, audio: str = "") -> Path:
        """Cria a pasta de uma reunião com transcrição e/ou áudio (.wav ou .ogg)."""
        pasta = raiz / nome
        pasta.mkdir()
        if texto:
            (pasta / "transcricao.txt").write_text("x", encoding="utf-8")
        if audio:
            for faixa in ("audio_microfone", "audio_sistema"):
                (pasta / f"{faixa}{audio}").write_bytes(b"0")
        return pasta

    def test_ordem_limite_e_rotulo(self):
        """Mais recente primeiro, no máximo 5, ignorando pastas vazias."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            for i in range(7):
                self._criar(raiz, f"2026-10-2{i}_10h00_Pessoa {i}")
            self._criar(raiz, "2026-10-29_09h00_Vazia", texto=False)
            r = ultimas_reunioes(raiz)
            self.assertEqual(len(r), 5)
            self.assertEqual(r[0].rotulo, "26/10 10:00  Pessoa 6")
            self.assertEqual(r[0].contato, "Pessoa 6")
            self.assertEqual(r[0].data, datetime(2026, 10, 26, 10, 0))
            self.assertEqual(r[0].arquivo.name, "transcricao.txt")

    def test_reuniao_que_falhou_aparece_sem_texto(self):
        """Só com áudio (transcrição falhou): aparece, sem arquivo e com áudio."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            self._criar(raiz, "2026-10-27_20h00_Falhou", texto=False, audio=".wav")
            r = ultimas_reunioes(raiz)
            self.assertEqual(len(r), 1)
            self.assertIsNone(r[0].arquivo)
            self.assertTrue(r[0].tem_audio)

    def test_audio_comprimido_e_sem_audio(self):
        """Acha o .ogg quando o WAV já foi comprimido; sem áudio, não dá pra refazer."""
        with tempfile.TemporaryDirectory() as tmp:
            raiz = Path(tmp)
            com_ogg = self._criar(raiz, "2026-10-27_20h00_Ogg", audio=".ogg")
            self._criar(raiz, "2026-10-26_20h00_Limpa")
            self.assertEqual(audio_da_faixa(com_ogg, "audio_sistema").suffix, ".ogg")
            r = ultimas_reunioes(raiz)
            self.assertTrue(r[0].tem_audio)
            self.assertFalse(r[1].tem_audio)

    def test_pasta_inexistente(self):
        """Sem pasta de saída ainda, a lista vem vazia."""
        self.assertEqual(ultimas_reunioes(Path("/nao/existe")), [])


if __name__ == "__main__":
    unittest.main()
