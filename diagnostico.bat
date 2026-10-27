@echo off
cd /d "%~dp0"
echo ===== DIAGNOSTICO DO GRAVADOR =====
echo.
echo [1] Python do sistema:
py -3 --version 2>nul || python --version
echo.
if not exist .venv (
    echo [2] A pasta .venv NAO existe: a instalacao nao chegou a rodar.
    goto fim
)
echo [2] Python do app:
.venv\Scripts\python --version
echo.
echo [3] Bibliotecas:
.venv\Scripts\python -c "import faster_whisper, pyaudiowpatch; print('ok, bibliotecas instaladas')"
echo.
echo [4] Abrindo o app (se der erro, aparece aqui embaixo):
.venv\Scripts\python app.py
:fim
echo.
echo ===== Tire um print desta tela e mande para o Claude =====
pause
