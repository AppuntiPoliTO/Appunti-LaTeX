@echo off
chcp 65001 >nul
title Sincronizzazione Appunti -> GitHub & Telegram
echo ===================================================
echo   AGGIORNAMENTO APPUNTI IN CORSO...
echo ===================================================

:: Assicura che anche questo file venga ignorato da Git e da Telegram
findstr /C:"aggiorna.bat" .gitignore >nul 2>&1
if errorlevel 1 echo aggiorna.bat>> .gitignore

:: 1. Aggiunge tutti i tuoi nuovi PDF e le modifiche locali
echo.
echo [1/4] Controllo nuovi file o PDF modificati...
git add .

:: 2. Crea il salvataggio (commit) con data e ora automatica
echo [2/4] Salvataggio modifiche...
git diff --staged --quiet
if errorlevel 1 (
    git commit -m "Aggiornamento appunti del %date% alle %time:~0,5%"
) else (
    echo Nessuna nuova modifica trovata nei tuoi file.
)

:: 3. Scarica il file telegram_state.json aggiornato da GitHub (evita conflitti)
echo [3/4] Sincronizzazione stato con GitHub (git pull)...
git pull --rebase origin main
if errorlevel 1 (
    echo.
    echo [!] ERRORE durante il pull da GitHub. Controlla la connessione.
    pause
    exit /b
)

:: 4. Invia tutto a GitHub (che farà partire il Bot su Telegram)
echo [4/4] Invio file su GitHub (git push)...
git push origin main

echo.
echo ===================================================
echo   FATTO! Tra 20-30 secondi vedrai i file su Telegram!
echo ===================================================
timeout /t 5