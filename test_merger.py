"""
test_merger.py
Testes da junção, remoção de eco e formatação da transcrição.
Rodar com: python -m unittest test_merger.py
Autor: Addad
"""
import unittest

from merger import Segmento, agrupar, formatar, frases, montar_transcricao, remover_eco, tempo


class TestMerger(unittest.TestCase):
    """Garante que a transcrição sai em ordem, sem eco e bem formatada."""

    def test_ordem_cronologica(self):
        """Falas das duas trilhas devem ser intercaladas pelo horário."""
        mic = [Segmento(0, 2, "Addad", "Oi, tudo bem?"), Segmento(6, 8, "Addad", "Fechado.")]
        sis = [Segmento(3, 5, "Ana", "Tudo, e você?")]
        r = montar_transcricao(mic, sis)
        self.assertEqual([s.falante for s in r], ["Addad", "Ana", "Addad"])

    def test_remove_eco(self):
        """Trecho do mic igual ao do sistema no mesmo tempo é eco e sai."""
        mic = [Segmento(3, 5, "Addad", "tudo e voce"), Segmento(6, 7, "Addad", "beleza")]
        sis = [Segmento(3, 5, "Ana", "Tudo, e você?")]
        self.assertEqual([s.texto for s in remover_eco(mic, sis)], ["beleza"])

    def test_mantem_fala_simultanea_diferente(self):
        """Duas pessoas falando ao mesmo tempo coisas diferentes ficam as duas."""
        mic = [Segmento(3, 5, "Addad", "Espera, deixa eu ver")]
        sis = [Segmento(3, 5, "Ana", "O valor é dois mil")]
        self.assertEqual(len(remover_eco(mic, sis)), 1)

    def test_agrupa_mesmo_falante(self):
        """Falas seguidas e próximas do mesmo falante viram um bloco só."""
        r = agrupar([Segmento(0, 1, "Ana", "Então"), Segmento(1.5, 3, "Ana", "é isso.")])
        self.assertEqual(len(r), 1)
        self.assertEqual(r[0].texto, "Então é isso.")

    def test_nao_agrupa_pausa_longa(self):
        """Pausa longa separa em dois blocos."""
        r = agrupar([Segmento(0, 1, "Ana", "A"), Segmento(10, 11, "Ana", "B")])
        self.assertEqual(len(r), 2)

    def test_formatar(self):
        """Linha final tem horário, nome e texto."""
        txt = formatar([Segmento(65, 70, "Addad", "Olá")], "Cabeçalho")
        self.assertIn("[00:01:05] Addad: Olá", txt)
        self.assertEqual(tempo(3725), "01:02:05")

    def test_intercala_conversa_por_palavras(self):
        """Caso real: cada um fala em momentos diferentes; a ordem tem que
        seguir o tempo, mesmo com o Whisper devolvendo tudo de uma trilha junto."""
        def falas(falante, trechos):
            out = []
            for inicio, texto in trechos:
                for i, palavra in enumerate(texto.split()):
                    t = inicio + i * 0.3
                    out.append(Segmento(t, t + 0.25, falante, palavra))
            return out
        mic = falas("Addad", [(2, "fala chat tudo bem"), (24, "de gravação de voz")])
        sis = falas("GPT", [(8, "tudo certo Addad"), (45, "em reunião e chamada")])
        r = montar_transcricao(mic, sis)
        self.assertEqual([s.falante for s in r], ["Addad", "GPT", "Addad", "GPT"])
        self.assertEqual(r[0].texto, "fala chat tudo bem")
        self.assertEqual(r[2].texto, "de gravação de voz")

    def test_frases_quebram_na_pausa(self):
        """Pausa maior que 0,8s entre palavras abre uma frase nova."""
        p = [Segmento(0, 0.3, "A", "oi"), Segmento(0.4, 0.7, "A", "tudo"),
             Segmento(3, 3.3, "A", "bem")]
        self.assertEqual([f.texto for f in frases(p)], ["oi tudo", "bem"])

    def test_formatar_vazio(self):
        """Sem falas, avisa em vez de gerar arquivo vazio."""
        self.assertIn("nenhuma fala", formatar([], "C"))


if __name__ == "__main__":
    unittest.main()
