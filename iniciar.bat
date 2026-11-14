@echo off
title Controle Sicovab
cd /d "%~dp0"

if not exist ".venv\instalado.txt" (
    echo Primeira execucao: preparando o ambiente. Isso leva alguns minutos...
    if not exist ".venv\Scripts\python.exe" ( py -3.12 -m venv .venv 2>nul || py -3 -m venv .venv 2>nul || python -m venv .venv )
    if not exist ".venv\Scripts\python.exe" (
        echo.
        echo Nao encontrei o Python. Instale o Python 3.12 em https://www.python.org/downloads/
        echo e marque a opcao "Add python.exe to PATH". Depois rode este arquivo de novo.
        pause
        exit /b 1
    )
    ".venv\Scripts\python.exe" -m pip install --upgrade pip
    ".venv\Scripts\python.exe" -m pip install -r requirements.txt || ( echo Falha ao instalar os pacotes. Verifique a internet e rode de novo. & pause & exit /b 1 )
    echo ok> ".venv\instalado.txt"
)

rem evita a pergunta de e-mail do Streamlit na primeira execucao
if not exist "%USERPROFILE%\.streamlit\credentials.toml" (
    if not exist "%USERPROFILE%\.streamlit" mkdir "%USERPROFILE%\.streamlit"
    > "%USERPROFILE%\.streamlit\credentials.toml" echo [general]
    >> "%USERPROFILE%\.streamlit\credentials.toml" echo email = ""
)

echo.
echo Controle Sicovab rodando. Neste computador: http://localhost:8501
for /f "tokens=2 delims=:" %%a in ('ipconfig ^| findstr /c:"IPv4"') do for /f "tokens=1" %%b in ("%%a") do echo Em outro computador da rede: http://%%b:8501
echo Para encerrar, feche esta janela.
echo.
".venv\Scripts\python.exe" -m streamlit run app.py --server.address 0.0.0.0 --server.port 8501 --server.headless false --browser.serverAddress localhost
pause
