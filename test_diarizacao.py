"""
test_diarizacao.py
Testes da parte da separação de vozes que não depende do modelo:
dar a cada palavra a pessoa certa, montar exemplos e renomear.
Rodar com: python -m unittest test_diarizacao.py
Autor: Addad
"""
import tempfile
import unittest
from pathlib import Path

import numpy as np

from diarizacao import Trecho, atribuir_pessoas, preparar_pessoas, renomear
from merger import Segmento, frases, montar_transcricao


def _palavras(trechos: list[tuple[float, str]]) -> list[Segmento]:
    """Palavras de 0,3 s seguidas a partir de cada início, todas do 'Contato'."""
    out = []
    for inicio, texto in trechos:
        for i, p in enumerate(texto.split()):
            t = inicio + i * 0.3
            out.append(Segmento(t, t + 0.25, "Contato", p))
    return out


class TestDiarizacao(unittest.TestCase):
    """Garante que as palavras vão para a pessoa certa e na ordem certa."""

    def test_atribui_na_ordem_de_aparicao(self):
        """Quem fala primeiro vira Pessoa 1, mesmo com número interno maior."""
        palavras = _palavras([(0, "bom dia pessoal"), (5, "oi tudo bem"), (10, "vamos começar")])
        trechos = [Trecho(0, 1, 7), Trecho(5, 6, 2), Trecho(10, 11, 7)]
        rotulos = atribuir_pessoas(palavras, trechos)
        self.assertEqual(rotulos, ["Pessoa 1", "Pessoa 2"])
        self.assertEqual([f.falante for f in frases(palavras)], ["Pessoa 1", "Pessoa 2", "Pessoa 1"])

    def test_palavra_fora_de_trecho_vai_pro_mais_proximo(self):
        """Palavra num buraco entre trechos fica com a pessoa do trecho mais perto."""
        palavras = [Segmento(3.0, 3.2, "Contato", "hm")]
        atribuir_pessoas(palavras, [Trecho(0, 2.9, 0), Trecho(6, 8, 1)])
        self.assertEqual(palavras[0].falante, "Pessoa 1")

    def test_troca_de_pessoa_sem_pausa_quebra_a_frase(self):
        """Duas pessoas emendadas sem pausa viram duas falas, não uma."""
        palavras = _palavras([(0, "eu acho que sim")]) + _palavras([(1.2, "discordo totalmente")])
        atribuir_pessoas(palavras, [Trecho(0, 1.15, 0), Trecho(1.15, 2, 1)])
        r = montar_transcricao([], palavras)
        self.assertEqual([f.falante for f in r], ["Pessoa 1", "Pessoa 2"])

    def test_exemplos_amostras_e_renomear(self):
        """Cada pessoa ganha um exemplo e um WAV curto; depois recebe o nome dado."""
        palavras = _palavras([(0, "frase curta"), (3, "uma frase bem mais longa aqui")])
        atribuir_pessoas(palavras, [Trecho(0, 1, 0), Trecho(3, 5, 0)])
        audio = np.zeros(16000 * 6, dtype=np.float32)
        with tempfile.TemporaryDirectory() as tmp:
            pessoas = preparar_pessoas(palavras, ["Pessoa 1"], audio, Path(tmp))
            self.assertEqual(pessoas[0].exemplo, "uma frase bem mais longa aqui")
            self.assertTrue(pessoas[0].amostra.exists())
        renomear(palavras, {"Pessoa 1": "Marina"})
        self.assertEqual({p.falante for p in palavras}, {"Marina"})


if __name__ == "__main__":
    unittest.main()
