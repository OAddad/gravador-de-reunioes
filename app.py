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
from diarizacao import atribuir_pessoas, preparar_pessoas, renomear, separar  # noqa: E402
from historico import FAIXAS, Reuniao, audio_da_faixa, ultimas_reunioes  # noqa: E402
from compressao import duracao_audio, comprimir_pendentes, comprimir_reuniao  # noqa: E402
from limpeza import limpar_audios_antigos  # noqa: E402
from merger import formatar, montar_transcricao, tempo  # noqa: E402
from recorder import Gravador  # noqa: E402
from transcriber import PASTA_MODELOS, Transcritor  # noqa: E402

COR_CARD = "#1C1F26"
COR_TEXTO = "#F2F4F7"
COR_SUAVE = "#9AA3B2"
COR_REC = "#E5484D"
OPCOES_PESSOAS = ["1", "2", "3", "4", "5", "6", "Não sei"]


def _nome_pasta(nome: str) -> str:
    """Remove caracteres que o Windows não aceita em nome de pasta."""
    return re.sub(r"[^\w\- ]", "", nome).strip() or "Contato"


def _esconder_da_captura(janela: tk.Toplevel) -> None:
    """Pede ao Windows para não mostrar a janela em capturas de tela
    (compartilhamento no Meet, Zoom, prints). Na tela de quem grava ela
    aparece normal. Precisa do Windows 10 versão 2004 ou mais novo;
    em versões antigas o card só continua aparecendo."""
    if sys.platform != "win32":
        return
    try:
        import ctypes
        janela.update_idletasks()
        user32 = ctypes.windll.user32
        hwnd = user32.GetAncestor(janela.winfo_id(), 2)  # 2 = GA_ROOT: a janela de verdade
        if not user32.SetWindowDisplayAffinity(hwnd, 0x11):  # 0x11 = WDA_EXCLUDEFROMCAPTURE
            logging.info("Windows não aceitou esconder o card da captura de tela")
    except Exception:
        logging.exception("Erro ao esconder o card da captura de tela")


class CardGravando(tk.Toplevel):
    """Card fino, sempre por cima de tudo, enquanto grava: uma linha só com
    o ponto vermelho, com quem é a conversa, o tempo e o Parar.
    Dá pra arrastar segurando em qualquer parte (menos no botão).
    Não aparece para quem vê sua tela compartilhada."""

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
        _esconder_da_captura(self)

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


class DialogoNomes(tk.Toplevel):
    """Janela que aparece depois de separar as vozes: para cada pessoa
    encontrada, mostra um trecho do que ela falou, um botão para ouvir e
    um campo para digitar o nome."""

    def __init__(self, raiz: tk.Tk, pessoas: list, contato: str,
                 resposta: dict, pronto: threading.Event):
        """Monta a lista de pessoas; o primeiro nome já vem com o contato."""
        super().__init__(raiz)
        self.pessoas, self.resposta, self.pronto = pessoas, resposta, pronto
        self.title("Quem é quem?")
        self.resizable(False, False)
        self.attributes("-topmost", True)
        q = ttk.Frame(self, padding=16)
        q.grid()
        ttk.Label(q, text=f"Encontrei {len(pessoas)} vozes no áudio do computador. "
                          "Dê o nome de cada uma. Se duas forem a mesma pessoa, "
                          "repita o nome.", wraplength=420).grid(
            row=0, column=0, columnspan=3, sticky="w", pady=(0, 10))
        self.campos = []
        for i, p in enumerate(pessoas):
            linha = 1 + i * 2
            ttk.Label(q, text=p.rotulo, font=("Segoe UI Semibold", 9)).grid(row=linha, column=0, sticky="w")
            campo = ttk.Entry(q, width=24)
            if i == 0:
                campo.insert(0, contato)
            campo.grid(row=linha, column=1, padx=(8, 0), sticky="w")
            ouvir = ttk.Button(q, text="▶ Ouvir", width=8, command=lambda a=p.amostra: self._ouvir(a))
            ouvir.grid(row=linha, column=2, padx=(8, 0))
            if not p.amostra:
                ouvir.configure(state="disabled")
            ttk.Label(q, text=f"“{p.exemplo}”", foreground="#666", wraplength=420).grid(
                row=linha + 1, column=0, columnspan=3, sticky="w", pady=(2, 10))
            self.campos.append(campo)
        ttk.Button(q, text="Salvar transcrição", command=self._salvar).grid(
            row=1 + len(pessoas) * 2, column=0, columnspan=3, sticky="e")
        self.protocol("WM_DELETE_WINDOW", self._salvar)
        self.campos[0].focus()
        self.bind("<Return>", lambda _e: self._salvar())
        self.grab_set()

    def _ouvir(self, amostra) -> None:
        """Toca o trecho da pessoa (sem travar a janela)."""
        try:
            import winsound
            winsound.PlaySound(str(amostra), winsound.SND_FILENAME | winsound.SND_ASYNC)
        except Exception:
            logging.exception("Não consegui tocar a amostra")

    def _salvar(self) -> None:
        """Guarda os nomes (vazio mantém "Pessoa N") e libera a transcrição."""
        try:
            import winsound
            winsound.PlaySound(None, 0)
        except Exception:
            pass
        for pessoa, campo in zip(self.pessoas, self.campos):
            self.resposta[pessoa.rotulo] = campo.get().strip() or pessoa.rotulo
        self.grab_release()
        self.destroy()
        self.pronto.set()


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
        linha_pessoas = ttk.Frame(q)
        linha_pessoas.grid(row=3, column=0, columnspan=2, sticky="w", pady=(8, 0))
        ttk.Label(linha_pessoas, text="Pessoas do outro lado:").pack(side="left")
        self.campo_pessoas = ttk.Combobox(linha_pessoas, width=8, state="readonly",
                                          values=OPCOES_PESSOAS)
        self.campo_pessoas.set("1")
        self.campo_pessoas.pack(side="left", padx=(6, 0))
        ttk.Label(linha_pessoas, text="(reunião em grupo: 2 ou mais)", foreground="#777").pack(
            side="left", padx=(6, 0))
        self.botao = ttk.Button(q, text="● Gravar", command=self._gravar)
        self.botao.grid(row=4, column=0, sticky="we", pady=(12, 0))
        ttk.Button(q, text="Abrir pasta", command=self._abrir_pasta).grid(
            row=4, column=1, sticky="we", pady=(12, 0), padx=(8, 0))
        self.lbl_status = ttk.Label(q, text="Pronto.", foreground="#555", wraplength=280)
        self.lbl_status.grid(row=5, column=0, columnspan=2, pady=(12, 0))
        self.barra = ttk.Progressbar(q, length=280, maximum=100)
        self.barra.grid(row=6, column=0, columnspan=2, pady=(8, 0))
        self.barra.grid_remove()
        ttk.Separator(q).grid(row=7, column=0, columnspan=2, sticky="we", pady=(14, 8))
        ttk.Label(q, text="Últimas reuniões", font=("Segoe UI Semibold", 9)).grid(
            row=8, column=0, columnspan=2, sticky="w")
        self.lista = ttk.Frame(q)
        self.lista.grid(row=9, column=0, columnspan=2, sticky="we", pady=(4, 0))
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
        """Mostra as 5 últimas reuniões com Abrir, Na pasta e Refazer.
        Reunião cuja transcrição falhou aparece como "(sem texto)"."""
        for filho in self.lista.winfo_children():
            filho.destroy()
        reunioes = ultimas_reunioes(Path(self.cfg["pasta_saida"]))
        if not reunioes:
            ttk.Label(self.lista, text="Nenhuma reunião ainda.", foreground="#777").grid(sticky="w")
            return
        for i, r in enumerate(reunioes):
            rotulo = r.rotulo if r.arquivo else f"{r.rotulo} (sem texto)"
            ttk.Label(self.lista, text=rotulo, width=26).grid(row=i, column=0, sticky="w", pady=1)
            abrir = ttk.Button(self.lista, text="Abrir", width=6,
                               command=lambda a=r.arquivo: os.startfile(a))
            abrir.grid(row=i, column=1, padx=(4, 0))
            if not r.arquivo:
                abrir.configure(state="disabled")
            alvo = r.arquivo or r.pasta
            ttk.Button(self.lista, text="Na pasta", width=8,
                       command=lambda a=alvo: subprocess.Popen(f'explorer /select,"{a}"')
                       ).grid(row=i, column=2, padx=(4, 0))
            refazer = ttk.Button(self.lista, text="Refazer", width=8,
                                 command=lambda reuniao=r: self._refazer(reuniao))
            refazer.grid(row=i, column=3, padx=(4, 0))
            if not r.tem_audio:
                refazer.configure(state="disabled")  # áudio já apagado pela limpeza

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
        self._iniciar_transcricao(self.pasta_atual, self.contato, self.inicio_dt, duracao)

    def _refazer(self, reuniao: Reuniao) -> None:
        """Transcreve de novo uma reunião a partir do áudio salvo (WAV ou comprimido)."""
        if self.gravador.gravando or self.transcrevendo:
            messagebox.showinfo("Aguarde", "Espere terminar a gravação ou a transcrição atual.")
            return
        if reuniao.arquivo and not messagebox.askyesno(
                "Refazer transcrição", f"Transcrever de novo {reuniao.rotulo}?\n"
                "A transcrição atual será substituída."):
            return
        logging.info("Refazendo a transcrição de %s", reuniao.pasta.name)
        self._iniciar_transcricao(reuniao.pasta, reuniao.contato,
                                  reuniao.data or datetime.now(), None)

    def _iniciar_transcricao(self, pasta: Path, contato: str, data: datetime,
                             duracao: float | None) -> None:
        """Trava a janela, mostra o progresso e transcreve em segundo plano."""
        self.pasta_atual = pasta
        escolha = self.campo_pessoas.get()
        n_pessoas = None if escolha == "Não sei" else int(escolha)
        self.campo_pessoas.configure(state="disabled")
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
        threading.Thread(target=self._transcrever, args=(pasta, contato, data, duracao, n_pessoas),
                         daemon=True).start()

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
        """Roda em thread ao abrir: comprime os áudios que ficaram sem comprimir
        e apaga os com mais de N dias já transcritos."""
        try:
            comprimir_pendentes(Path(self.cfg["pasta_saida"]))
        except Exception:
            logging.exception("Erro ao comprimir áudios pendentes")
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

    def _separar_vozes(self, audio_sis: Path, palavras: list, contato: str,
                       n_pessoas: int | None, pasta: Path) -> list[str]:
        """Separa as vozes do áudio do computador e pergunta o nome de cada
        pessoa. Devolve os nomes, na ordem em que falaram. Se der erro,
        mantém tudo com o nome do contato (a transcrição não se perde)."""
        try:
            trechos, audio = separar(
                audio_sis, PASTA_MODELOS, n_pessoas,
                lambda f: self.fila.put(("vozes", int(f * 100))), self._avisar_download)
            rotulos = atribuir_pessoas(palavras, trechos)
        except Exception:
            logging.exception("Erro ao separar as vozes; seguindo com um nome só")
            return [contato]
        if len(rotulos) < 2:
            renomear(palavras, {r: contato for r in rotulos})
            return [contato]
        pessoas = preparar_pessoas(palavras, rotulos, audio, pasta)
        resposta: dict = {}
        pronto = threading.Event()
        self.fila.put(("nomear", (pessoas, contato, resposta, pronto)))
        pronto.wait()
        for p in pessoas:
            if p.amostra:
                p.amostra.unlink(missing_ok=True)
        renomear(palavras, resposta)
        # mesmo nome em duas vozes (era a mesma pessoa) aparece uma vez só
        return list(dict.fromkeys(resposta.get(r, r) for r in rotulos))

    def _transcrever(self, pasta: Path, outro: str, data: datetime,
                     duracao: float | None, n_pessoas: int | None = 1) -> None:
        """Roda em thread: transcreve as duas trilhas, separa as vozes do áudio
        do computador (se for reunião em grupo) e salva o .txt.
        Lê o WAV ou, se já foi comprimido, o .ogg."""
        try:
            eu = self.cfg["meu_nome"]
            audio_mic, audio_sis = (audio_da_faixa(pasta, f) for f in FAIXAS)
            if audio_mic is None or audio_sis is None:
                raise RuntimeError("Os áudios dessa reunião não existem mais.")
            if duracao is None:
                duracao = duracao_audio(audio_sis)
            mic = self.transcritor.transcrever(
                audio_mic, eu, lambda f: self._avisar_progresso(0, f))
            sistema = self.transcritor.transcrever(
                audio_sis, outro, lambda f: self._avisar_progresso(1, f))
            outros = [outro]
            if n_pessoas != 1:
                outros = self._separar_vozes(audio_sis, sistema, outro, n_pessoas, pasta)
            nomes = ", ".join(outros)
            cabecalho = (
                f"Reunião: {eu} x {nomes}\n"
                f"Data: {data.strftime('%d/%m/%Y %H:%M')}\n"
                f"Duração: {tempo(duracao)}\n"
                f"Participantes: {eu} (microfone), {nomes} (áudio do computador)"
            )
            texto = formatar(montar_transcricao(mic, sistema), cabecalho)
            (pasta / "transcricao.txt").write_text(texto, encoding="utf-8")
            self.fila.put(("ok", texto))
            # depois de entregar o texto, comprime os áudios (~1 GB/h vira ~22 MB/h)
            comprimir_reuniao(pasta)
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
                elif tipo == "vozes":
                    self.barra["value"] = conteudo
                    self._status(f"Separando as vozes... {conteudo}%")
                elif tipo == "nomear":
                    pessoas, contato, resposta, pronto = conteudo
                    self._status("Quem é quem? Dê o nome de cada pessoa.")
                    DialogoNomes(self.raiz, pessoas, contato, resposta, pronto)
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
            self.campo_pessoas.configure(state="readonly")
            self.campo_pessoas.set("1")
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
