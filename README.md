# Gravador de Reuniões

Grava ligações e reuniões no Windows (WhatsApp Desktop, Google Meet, Zoom, qualquer coisa que toque no PC) e transcreve tudo **localmente**, sem mandar áudio pra nenhum servidor. O texto sai com o nome de quem falou e o horário de cada fala, pronto pra colar numa IA.

```
[00:00:04] Addad: Fala, tudo bem com você?
[00:00:09] Marina: Tudo certo! Vamos falar do orçamento?
```

## Como funciona

- Grava **duas faixas separadas**: o seu microfone e o som do computador (WASAPI loopback). Por isso sabe quem falou sem precisar de IA pra adivinhar.
- Transcreve com o **Whisper** ([faster-whisper](https://github.com/SYSTRAN/faster-whisper)) rodando no próprio PC.
- Usa a placa de vídeo NVIDIA quando ela existe (modelo `large-v3-turbo`, mais preciso). Sem placa, roda no processador com o modelo `small`.
- Intercala as duas faixas pela hora de cada palavra, para a conversa sair na ordem certa.

## Instalar (uma vez)

1. Instale o **Python 3.11 ou 3.12** em [python.org](https://www.python.org/downloads/) e marque "Add Python to PATH".
2. Baixe esta pasta (Code > Download ZIP) e descompacte onde quiser.
3. Dê dois cliques em `iniciar.bat`. Na primeira vez ele instala as bibliotecas (alguns minutos; com placa NVIDIA baixa mais ~1,3 GB das bibliotecas CUDA). Não feche a janela preta.

Na primeira transcrição o app baixa o modelo do Whisper para a pasta `modelos/` (464 MB o `small`, 1,5 GB o `large-v3-turbo`). Isso acontece uma vez só. Copiando a pasta inteira para outro PC, o modelo vai junto.

## Usar

1. Em **Você**, coloque o seu nome (fica salvo).
2. Em **Com quem é a conversa?**, digite o nome da outra pessoa (obrigatório, a cada gravação).
3. Clique **Gravar**. A janela some e fica um card pequeno por cima de tudo, com o nome, o tempo e o botão **Parar**. Dá pra arrastar o card.
4. Clique **Parar**. A janela volta mostrando a porcentagem da transcrição.
5. Pronto: o texto já fica copiado. Em **Últimas reuniões** aparecem as 5 mais recentes com **Abrir** e **Na pasta**.

As gravações ficam em `Documentos\Transcricoes\<data>_<nome>\` com os dois áudios e a `transcricao.txt`.

**Compressão:** depois de transcrever, o app converte os dois áudios WAV para `.ogg` (Opus), de ~1 GB para ~22 MB por hora. Continua dando para ouvir e retranscrever. O WAV só é apagado depois que o `.ogg` fica pronto e com a mesma duração.

**Limpeza automática:** ao abrir, o app apaga os áudios das reuniões com mais de 30 dias e mantém só a `transcricao.txt`. Áudio de reunião sem transcrição (que falhou) nunca é apagado. O prazo fica em `config.json` (`"dias_manter_audio": 30`; use `0` para nunca apagar).

## Dicas

- **Use fone de ouvido.** Na caixa de som a voz do outro vaza no seu microfone. O app tenta remover esse eco, mas com fone a separação é perfeita.
- Grava o microfone e a saída de som **padrão** do Windows. Se trocar de fone, ajuste em Configurações > Som antes de gravar.
- Em `config.json` dá pra trocar o modelo (`"modelo": "auto"`, `"small"`, `"medium"`, `"large-v3-turbo"`...), o idioma e a pasta de saída.
- Se algo der errado, o `gravador.log` (na pasta do app) mostra o que aconteceu. O `diagnostico.bat` abre o app com o erro visível na tela.

## Avisos

- Avise as pessoas de que a conversa está sendo gravada.
- Só funciona no **Windows** (a captura do som do computador usa WASAPI).

## Testes

```
.venv\Scripts\python -m unittest test_merger.py test_historico.py test_limpeza.py test_compressao.py
```
