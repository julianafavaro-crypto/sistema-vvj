@echo off
title JF Florestal / VKS-Valls — Sistema de Gestao
color 0A
echo.
echo  ==========================================
echo   JF Florestal / VKS-Valls
echo   Sistema de Gestao de Servicos
echo  ==========================================
echo.
echo  Iniciando servidor...
echo  Acesse: http://localhost:5000
echo.
echo  Para encerrar, feche esta janela.
echo.
cd /d "%~dp0"
start "" "http://localhost:5000"
python app.py
pause
