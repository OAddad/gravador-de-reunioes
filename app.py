"""
app.py
Janela do Gravador de Reuniões: digita o nome do contato e clica Gravar.
Enquanto grava, a janela some e fica só um card pequeno por cima de tudo
(nome, tempo e Parar). Ao parar, a janela volta com a porcentagem da
transcrição e entrega o .txt (já copiado para a área de transferência).
Autor: Addad
"""
import logging
import os
import queue
import re
import subprocess
import sys
import threading
import tkinter as tk
from datetime import datetime
from pathlib import Path
from tkinter import messagebox, ttk

PASTA_APP = Path(__file__).resolve().parent

logging.basicConfig(
    filename=PASTA_APP / "gravador.log",
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(message)s",
    encoding="utf-8",
)
# pythonw roda sem console: sys.stderr é None e algumas bibliotecas quebram
if sys.stderr is None:
    sys.stderr = open(os.devnull, "w")
if sys.stdout is None:
    sys.stdout = open(os.devnull, "w")

from config import carregar_config, salvar_config  # noqa: E402
from historico import ultimas_reunioes  # noqa: E402
from limpeza import limpar_audios_antigos  # noqa: E402
from merger import formatar, montar_transcricao, tempo  # noqa: E402
from recorder import Gravador  # noqa: E402
from transcriber import Transcritor  # noqa: E402

COR_CARD = "#1C1F26"
COR_TEXTO = "#F2F4F7"
COR_SUAVE = "#9AA3B2"
COR_REC = "#E5484D"


def _nome_pasta(nome: str) -> str:
    """Remove caracteres que o Windows não aceita em nome de pasta."""
    return re.sub(r"[^\w\- ]", "", nome).strip() or "Contato"


class CardGravando(tk.Toplevel):
    """Card fino, sempre por cima de tudo, enquanto grava: uma linha só com
    o ponto vermelho, com quem é a conversa, o tempo e o Parar.
    Dá pra arrastar segurando em qualquer parte (menos no botão)."""

    def __init__(self, raiz: tk.Tk, contato: str, ao_parar):
        """Cria o card no canto superior direito da tela."""
        super().__init__(raiz)
        self.overrideredirect(True)
        self.attributes("-topmost", True)
        self.configure(bg=COR_CARD, highlightthickness=1, highlightbackground="#3A3F4B",
                       cursor="fleur")
        largura, altura = 340, 40
        x = self.winfo_screenwidth() - largura - 24
        self.geometry(f"{largura}x{altura}+{x}+24")

        self.ponto = tk.Label(self, text="●", fg=COR_REC, bg=COR_CARD, font=("Segoe UI", 11))
        self.ponto.pack(side="left", padx=(12, 6))
        nome = contato if len(contato) <= 18 else contato[:17] + "…"
        lbl_nome = tk.Label(self, text=nome, fg=COR_TEXTO, bg=COR_CARD,
                            font=("Segoe UI Semibold", 10))
        lbl_nome.pack(side="left")
        tk.Button(self, text="■ Parar", command=ao_parar, fg="white", bg=COR_REC,
                  activebackground="#C73A3F", activeforeground="white", relief="flat",
                  font=("Segoe UI Semibold", 9), cursor="hand2", padx=10, pady=1
                  ).pack(side="right", padx=(6, 8))
        self.lbl_tempo = tk.Label(self, text="00:00:00", fg=COR_TEXTO, bg=COR_CARD,
                                  font=("Consolas", 13, "bold"))
        self.lbl_tempo.pack(side="right", padx=6)

        for elemento in (self, self.ponto, lbl_nome, self.lbl_tempo):
            elemento.bind("<ButtonPress-1>", self._pegar)
            elemento.bind("<B1-Motion>", self._arrastar)
        self._piscar_visivel = True

    def _pegar(self, evento) -> None:
        """Guarda onde o mouse pegou o card."""
        self._dx, self._dy = evento.x_root - self.winfo_x(), evento.y_root - self.winfo_y()

    def _arrastar(self, evento) -> None:
        """Move o card junto com o mouse."""
        self.geometry(f"+{evento.x_root - self._dx}+{evento.y_root - self._dy}")

    def atualizar(self, segundos: float) -> None:
        """Atualiza o tempo e faz o ponto vermelho piscar."""
        self.lbl_tempo.configure(text=tempo(segundos))
        self._piscar_visivel = not self._piscar_visivel
        self.ponto.configure(fg=COR_REC if self._piscar_visivel or segundos < 1 else COR_CARD)


class App:
    """Janela principal e fluxo gravar > parar > transcrever."""

    def __init__(self, raiz: tk.Tk):
        """Monta a interface e prepara gravador e transcritor."""
        self.raiz = raiz
        self.cfg = carregar_config()
        self.gravador = Gravador()
        self.transcritor = Transcritor(
            self.cfg["modelo"], self.cfg["idioma"], self._avisar_download,
            modo_salvo=self.cfg.get("modo_placa", ""), ao_achar_modo=self._salvar_modo)
        self.transcrevendo = False
        self.fila: queue.Queue = queue.Queue()
        self.pasta_atual: Path | None = None
        self.contato = ""
        self.inicio_dt = datetime.now()
        self.ultimo_pct_download = -1
        self.card: CardGravando | None = None
        self.tique = 0
        self._montar_tela()
        self.raiz.after(200, self._tick)
        # carrega o modelo já ao abrir, para a transcrição começar na hora ao parar
        threading.Thread(target=self._preparar_modelo, daemon=True).start()
        # apaga os áudios das reuniões antigas (mantém a transcrição)
        threading.Thread(target=self._limpar, daemon=True).start()
        self.raiz.protocol("WM_DELETE_WINDOW", self._fechar)

    def _montar_tela(self) -> None:
        """Cria os campos, botões e rótulos da janela."""
        self.raiz.title("Gravador de Reuniões")
        self.raiz.resizable(False, False)
        q = ttk.Frame(self.raiz, padding=16)
        q.grid()
        linha_eu = ttk.Frame(q)
        linha_eu.grid(row=0, column=0, columnspan=2, sticky="we")
        ttk.Label(linha_eu, text="Você:").pack(side="left")
        self.campo_eu = ttk.Entry(linha_eu, width=28)
        self.campo_eu.insert(0, self.cfg["meu_nome"])
        self.campo_eu.pack(side="left", padx=(6, 0), fill="x", expand=True)
        self.campo_eu.bind("<FocusOut>", self._salvar_meu_nome)
        self.campo_eu.bind("<Return>", self._salvar_meu_nome)
        ttk.Label(q, text="Com quem é a conversa?").grid(row=1, column=0, columnspan=2, sticky="w", pady=(10, 2))
        self.campo_nome = ttk.Entry(q, width=36)
        self.campo_nome.grid(row=2, column=0, columnspan=2, sticky="we")
        self.campo_nome.focus()
        self.botao = ttk.Button(q, text="● Gravar", command=self._gravar)
        self.botao.grid(row=3, column=0, sticky="we", pady=(12, 0))
        ttk.Button(q, text="Abrir pasta", command=self._abrir_pasta).grid(
            row=3, column=1, sticky="we", pady=(12, 0), padx=(8, 0))
        self.lbl_status = ttk.Label(q, text="Pronto.", foreground="#555", wraplength=280)
        self.lbl_status.grid(row=4, column=0, columnspan=2, pady=(12, 0))
        self.barra = ttk.Progressbar(q, length=280, maximum=100)
        self.barra.grid(row=5, column=0, columnspan=2, pady=(8, 0))
        self.barra.grid_remove()
        ttk.Separator(q).grid(row=6, column=0, columnspan=2, sticky="we", pady=(14, 8))
        ttk.Label(q, text="Últimas reuniões", font=("Segoe UI Semibold", 9)).grid(
            row=7, column=0, columnspan=2, sticky="w")
        self.lista = ttk.Frame(q)
        self.lista.grid(row=8, column=0, columnspan=2, sticky="we", pady=(4, 0))
        self._atualizar_lista()

    # ---------- configurações e lista ----------
    def _salvar_meu_nome(self, _evento=None) -> None:
        """Guarda o nome de quem usa o app (vale para as próximas gravações)."""
        nome = self.campo_eu.get().strip()
        if nome and nome != self.cfg["meu_nome"]:
            self.cfg["meu_nome"] = nome
            salvar_config(self.cfg)
            logging.info("Nome do operador trocado para %s", nome)

    def _atualizar_lista(self) -> None:
        """Mostra as 5 últimas transcrições com Abrir e Mostrar na pasta."""
        for filho in self.lista.winfo_children():
            filho.destroy()
        reunioes = ultimas_reunioes(Path(self.cfg["pasta_saida"]))
        if not reunioes:
            ttk.Label(self.lista, text="Nenhuma transcrição ainda.", foreground="#777").grid(sticky="w")
            return
        for i, r in enumerate(reunioes):
            ttk.Label(self.lista, text=r.rotulo, width=24).grid(row=i, column=0, sticky="w", pady=1)
            ttk.Button(self.lista, text="Abrir", width=7,
                       command=lambda a=r.arquivo: os.startfile(a)).grid(row=i, column=1, padx=(4, 0))
            ttk.Button(self.lista, text="Na pasta", width=9,
                       command=lambda a=r.arquivo: subprocess.Popen(f'explorer /select,"{a}"')
                       ).grid(row=i, column=2, padx=(4, 0))

    # ---------- gravar ----------
    def _gravar(self) -> None:
        """Valida o nome, cria a pasta, começa a gravar e troca a janela pelo card."""
        self._salvar_meu_nome()
        nome = self.campo_nome.get().strip()
        if not nome:
            messagebox.showwarning("Falta o nome", "Digite o nome da pessoa antes de gravar.")
            return
        self.contato = nome
        self.inicio_dt = datetime.now()
        carimbo = self.inicio_dt.strftime("%Y-%m-%d_%Hh%M")
        self.pasta_atual = Path(self.cfg["pasta_saida"]) / f"{carimbo}_{_nome_pasta(nome)}"
        self.pasta_atual.mkdir(parents=True, exist_ok=True)
        try:
            self.gravador.iniciar(self.pasta_atual / "audio_microfone.wav",
                                  self.pasta_atual / "audio_sistema.wav")
        except Exception as erro:
            logging.exception("Erro ao começar a gravar")
            messagebox.showerror("Erro ao gravar", str(erro))
            return
        logging.info("Gravando com %s em %s", nome, self.pasta_atual)
        self.raiz.withdraw()
        self.card = CardGravando(self.raiz, nome, self._parar)

    def _parar(self) -> None:
        """Para a gravação, fecha o card, mostra a janela e começa a transcrever."""
        if not self.gravador.gravando:
            return
        duracao = self.gravador.parar()
        logging.info("Gravação parada: %.0f s", duracao)
        if self.card:
            self.card.destroy()
            self.card = None
        self.raiz.deiconify()
        self.raiz.lift()
        self.botao.configure(state="disabled")
        self.campo_nome.configure(state="disabled")
        self.barra["value"] = 0
        self.barra.grid()
        self.ultimo_pct_download = -1
        self.transcrevendo = True
        if self.transcritor.modelo is None:
            self._status("Carregando o modelo de transcrição...")
        else:
            self._status("Transcrevendo... 0%")
        threading.Thread(target=self._transcrever, args=(duracao,), daemon=True).start()

    # ---------- transcrever ----------
    def _preparar_modelo(self) -> None:
        """Roda em thread ao abrir o app: baixa (se preciso) e carrega o modelo."""
        self.fila.put(("carregando", None))
        try:
            self.transcritor.preparar()
            onde = "na placa de vídeo" if self.transcritor.dispositivo == "cuda" else "no processador"
            self.fila.put(("modelo_pronto", onde))
        except Exception as erro:
            logging.exception("Erro ao carregar o modelo ao abrir")
            self.fila.put(("modelo_erro", str(erro)))

    def _limpar(self) -> None:
        """Roda em thread ao abrir: apaga áudios com mais de N dias já transcritos."""
        try:
            limpar_audios_antigos(Path(self.cfg["pasta_saida"]), int(self.cfg["dias_manter_audio"]))
        except Exception:
            logging.exception("Erro na limpeza dos áudios antigos")

    def _salvar_modo(self, modo: str) -> None:
        """Guarda o modo da placa que funcionou, para pular os que falham."""
        self.cfg["modo_placa"] = modo
        salvar_config(self.cfg)

    def _avisar_download(self, baixado: int, total: int) -> None:
        """Roda na thread do download: manda a porcentagem só quando muda."""
        pct = int(baixado * 100 / max(total, 1))
        if pct != self.ultimo_pct_download:
            self.ultimo_pct_download = pct
            self.fila.put(("download", (pct, total // (1024 * 1024))))

    def _avisar_progresso(self, etapa: int, fracao: float) -> None:
        """Microfone vale de 0 a 50%, áudio do computador de 50 a 100%."""
        self.fila.put(("progresso", int((etapa + fracao) * 50)))

    def _transcrever(self, duracao: float) -> None:
        """Roda em thread: transcreve as duas trilhas e salva o .txt."""
        try:
            pasta, eu, outro = self.pasta_atual, self.cfg["meu_nome"], self.contato
            mic = self.transcritor.transcrever(
                pasta / "audio_microfone.wav", eu, lambda f: self._avisar_progresso(0, f))
            sistema = self.transcritor.transcrever(
                pasta / "audio_sistema.wav", outro, lambda f: self._avisar_progresso(1, f))
            cabecalho = (
                f"Reunião: {eu} x {outro}\n"
                f"Data: {self.inicio_dt.strftime('%d/%m/%Y %H:%M')}\n"
                f"Duração: {tempo(duracao)}\n"
                f"Participantes: {eu} (microfone), {outro} (áudio do computador)"
            )
            texto = formatar(montar_transcricao(mic, sistema), cabecalho)
            (pasta / "transcricao.txt").write_text(texto, encoding="utf-8")
            self.fila.put(("ok", texto))
        except Exception as erro:
            logging.exception("Erro na transcrição")
            self.fila.put(("erro", str(erro)))

    # ---------- laço da tela ----------
    def _tick(self) -> None:
        """Atualiza o card e recebe progresso e resultado da transcrição."""
        self.tique += 1
        if self.card and self.tique % 2 == 0:
            self.card.atualizar(self.gravador.segundos())
        tipo, conteudo = None, None
        try:
            while True:
                tipo, conteudo = self.fila.get_nowait()
                if tipo == "download":
                    pct, total_mb = conteudo
                    self.barra.grid()
                    self.barra["value"] = pct
                    self._status(f"Baixando o modelo (só na primeira vez)... {pct}% de {total_mb} MB")
                elif tipo == "carregando":
                    if not self.transcrevendo:
                        self._status("Carregando o modelo de transcrição...")
                elif tipo in ("modelo_pronto", "modelo_erro"):
                    if not self.transcrevendo:
                        self.barra.grid_remove()
                        self._status(f"Pronto. Modelo carregado {conteudo}." if tipo == "modelo_pronto"
                                     else "Pronto. O modelo carrega ao transcrever.")
                elif tipo == "progresso":
                    self.barra["value"] = conteudo
                    self._status(f"Transcrevendo... {conteudo}%")
                else:
                    break
                tipo = None
        except queue.Empty:
            pass
        if tipo:
            self.transcrevendo = False
            self.barra.grid_remove()
            self.botao.configure(state="normal")
            self.campo_nome.configure(state="normal")
            self.campo_nome.delete(0, "end")  # toda gravação nova pede o nome de novo
            self.campo_nome.focus()
        if tipo == "ok":
            self.raiz.clipboard_clear()
            self.raiz.clipboard_append(conteudo)
            self._status("Pronto! Transcrição salva e copiada. É só colar na IA.")
            self._atualizar_lista()
        elif tipo == "erro":
            self._status("Erro na transcrição. Os áudios ficaram salvos na pasta.")
            messagebox.showerror("Erro na transcrição", conteudo)
        self.raiz.after(250, self._tick)

    def _status(self, texto: str) -> None:
        """Mostra uma mensagem curta embaixo dos botões."""
        self.lbl_status.configure(text=texto)

    def _abrir_pasta(self) -> None:
        """Abre no Explorer a pasta da última reunião (ou a pasta geral)."""
        alvo = self.pasta_atual or Path(self.cfg["pasta_saida"])
        alvo.mkdir(parents=True, exist_ok=True)
        os.startfile(alvo)

    def _fechar(self) -> None:
        """Ao fechar a janela, confirma se ainda estiver gravando."""
        if self.gravador.gravando:
            if not messagebox.askyesno("Gravando", "Ainda está gravando. Parar e sair sem transcrever?"):
                return
            self.gravador.parar()
        self.raiz.destroy()


if __name__ == "__main__":
    janela = tk.Tk()
    App(janela)
    janela.mainloop()
