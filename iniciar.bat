@echo off
cd /d "%~dp0"
rem Troque este numero sempre que o requirements.txt mudar, para reinstalar.
set VERSAO=5
if not exist .venv\Scripts\python.exe (
    echo Criando o ambiente do app, aguarde...
    py -3 -m venv .venv 2>nul || python -m venv .venv
)
set /p INSTALADA=<.venv\versao.txt 2>nul
if not "%INSTALADA%"=="%VERSAO%" (
    echo Instalando/atualizando as bibliotecas. Pode levar alguns minutos, NAO feche esta janela...
    echo.
    .venv\Scripts\python -m pip install --upgrade pip
    .venv\Scripts\python -m pip install -r requirements.txt
    .venv\Scripts\python -c "import faster_whisper, pyaudiowpatch, sherpa_onnx" 2>nul
    if errorlevel 1 (
        echo.
        echo ===== A instalacao falhou. Tire um print desta tela e mande para o Claude =====
        pause
        exit /b 1
    )
    echo %VERSAO%>.venv\versao.txt
    echo.
    echo Instalado com sucesso! Abrindo o app...
)
start "" .venv\Scripts\pythonw.exe app.py
