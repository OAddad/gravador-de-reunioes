"""
test_compressao.py
Testes da compressão dos áudios depois da transcrição.
Rodar com: python -m unittest test_compressao.py
Autor: Addad
"""
import math
import struct
import tempfile
import unittest
import wave
from pathlib import Path

from compressao import _duracao, comprimir, comprimir_reuniao


def _criar_wav(caminho: Path, segundos: float, canais: int) -> None:
    """Grava um WAV de teste (tom de 440 Hz) igual ao formato do gravador."""
    taxa = 48000
    with wave.open(str(caminho), "wb") as w:
        w.setnchannels(canais)
        w.setsampwidth(2)
        w.setframerate(taxa)
        quadros = bytearray()
        for i in range(int(taxa * segundos)):
            valor = int(8000 * math.sin(2 * math.pi * 440 * i / taxa))
            quadros += struct.pack("<h", valor) * canais
        w.writeframes(bytes(quadros))


class TestCompressao(unittest.TestCase):
    """Garante que o .ogg sai com a mesma duração, menor, e que o WAV some."""

    def test_comprime_e_apaga_wav(self):
        """WAV estéreo vira .ogg mono bem menor, com a mesma duração."""
        with tempfile.TemporaryDirectory() as tmp:
            wav = Path(tmp) / "audio_sistema.wav"
            _criar_wav(wav, 5, canais=2)
            tamanho_wav = wav.stat().st_size
            ogg = comprimir(wav)
            self.assertFalse(wav.exists())
            self.assertTrue(ogg.exists())
            self.assertLess(ogg.stat().st_size, tamanho_wav / 10)
            self.assertAlmostEqual(_duracao(ogg), 5, delta=0.5)

    def test_reuniao_inteira(self):
        """Os dois áudios da pasta são comprimidos; a transcrição não é tocada."""
        with tempfile.TemporaryDirectory() as tmp:
            pasta = Path(tmp)
            _criar_wav(pasta / "audio_microfone.wav", 2, canais=1)
            _criar_wav(pasta / "audio_sistema.wav", 2, canais=2)
            (pasta / "transcricao.txt").write_text("texto", encoding="utf-8")
            comprimir_reuniao(pasta)
            self.assertEqual(sorted(p.name for p in pasta.iterdir()),
                             ["audio_microfone.ogg", "audio_sistema.ogg", "transcricao.txt"])


if __name__ == "__main__":
    unittest.main()
