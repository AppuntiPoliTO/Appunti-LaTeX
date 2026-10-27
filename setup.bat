@echo off
chcp 65001 >nul
title Setup Automatico Appunti GitHub-Telegram
echo ===================================================
echo   CREAZIONE STRUTTURA E FILE IN CORSO...
echo ===================================================

:: 1. Crea la cartella per le GitHub Actions e due materie di esempio
mkdir ".github\workflows" 2>nul
mkdir "Fisica" 2>nul
mkdir "Analisi_1" 2>nul

:: Crea due file di testo di prova dentro le cartelle (cosi Git le vede)
echo Appunti di prova di Fisica > "Fisica\esempio_fisica.txt"
echo Appunti di prova di Analisi > "Analisi_1\esempio_analisi.txt"

:: 2. Crea il file telegram_state.json iniziale
echo {"topics": {}, "files": {}, "index_msg_id": null} > telegram_state.json

:: 3. Crea lo script Python sync_telegram.py usando PowerShell per non sbagliare la formattazione
powershell -Command "$code = @'
import os
import json
import requests
from datetime import datetime

TOKEN = os.environ['TELEGRAM_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
STATE_FILE = 'telegram_state.json'

ALLOWED_EXTENSIONS = {'.pdf', '.md', '.txt', '.docx', '.pptx', '.zip', '.png', '.jpg'}
IGNORE_DIRS = {'.git', '.github', '__pycache__'}

if os.path.exists(STATE_FILE):
    with open(STATE_FILE, 'r', encoding='utf-8') as f:
        state = json.load(f)
else:
    state = {'topics': {}, 'files': {}, 'index_msg_id': None}

state_updated = False
now = datetime.now().strftime('%d/%m/%Y %H:%M')

subjects = [d for d in os.listdir('.') if os.path.isdir(d) and d not in IGNORE_DIRS and not d.startswith('.')]
subjects.sort()

for subject in subjects:
    if subject not in state['topics']:
        url = f'https://api.telegram.org/bot{TOKEN}/createForumTopic'
        topic_name = f'📚 {subject.replace(\"_\", \" \")}'
        res = requests.post(url, json={'chat_id': CHAT_ID, 'name': topic_name})
        
        if res.status_code == 200:
            topic_id = res.json()['result']['message_thread_id']
            state['topics'][subject] = topic_id
            state_updated = True
            print(f'Creato nuovo Topic per: {subject} (ID: {topic_id})')
        else:
            print(f'Errore creazione topic {subject}: {res.text}')
            continue

    topic_id = state['topics'][subject]

    for root, dirs, files in os.walk(subject):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                rel_path = os.path.relpath(os.path.join(root, file), '.').replace('\\', '/')
                display_name = os.path.relpath(rel_path, subject).replace('\\', '/')
                caption = f'📚 <b>{subject.replace(\"_\", \" \")}</b>\n📄 <code>{display_name}</code>\n🔄 <i>Aggiornato il: {now}</i>'

                if rel_path in state['files']:
                    msg_id = state['files'][rel_path]
                    url = f'https://api.telegram.org/bot{TOKEN}/editMessageMedia'
                    media = json.dumps({'type': 'document', 'media': 'attach://document', 'caption': caption, 'parse_mode': 'HTML'})
                    with open(rel_path, 'rb') as f:
                        res = requests.post(url, data={'chat_id': CHAT_ID, 'message_id': msg_id, 'media': media}, files={'document': f})
                    if res.status_code == 200:
                        print(f'[{subject}] File aggiornato: {display_name}')
                else:
                    url = f'https://api.telegram.org/bot{TOKEN}/sendDocument'
                    with open(rel_path, 'rb') as f:
                        res = requests.post(url, data={
                            'chat_id': CHAT_ID,
                            'message_thread_id': topic_id,
                            'caption': caption,
                            'parse_mode': 'HTML'
                        }, files={'document': f})
                    if res.status_code == 200:
                        state['files'][rel_path] = res.json()['result']['message_id']
                        state_updated = True
                        print(f'[{subject}] Nuovo file inviato: {display_name}')

if state['topics']:
    clean_chat_id = str(CHAT_ID).replace('-100', '')
    index_text = '🗂 <b>INDICE DELLE MATERIE</b>\n<i>Clicca su una materia per aprire la stanza con gli appunti aggiornati:</i>\n\n'
    for subj in sorted(state['topics'].keys()):
        t_id = state['topics'][subj]
        link = f'https://t.me/c/{clean_chat_id}/{t_id}'
        index_text += f'🔹 <a href=\"{link}\"><b>{subj.replace(\"_\", \" \")}</b></a>\n'
    
    index_text += f'\n🔄 <i>Ultimo controllo: {now}</i>'

    if not state['index_msg_id']:
        url = f'https://api.telegram.org/bot{TOKEN}/sendMessage'
        res = requests.post(url, json={'chat_id': CHAT_ID, 'text': index_text, 'parse_mode': 'HTML'})
        if res.status_code == 200:
            state['index_msg_id'] = res.json()['result']['message_id']
            state_updated = True
            requests.post(f'https://api.telegram.org/bot{TOKEN}/pinChatMessage', json={
                'chat_id': CHAT_ID, 'message_id': state['index_msg_id']
            })
    else:
        url = f'https://api.telegram.org/bot{TOKEN}/editMessageText'
        requests.post(url, json={
            'chat_id': CHAT_ID,
            'message_id': state['index_msg_id'],
            'text': index_text,
            'parse_mode': 'HTML'
        })

if state_updated:
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=4)
'@; Set-Content -Path 'sync_telegram.py' -Value $code -Encoding UTF8"

:: 4. Crea il file della GitHub Action (.github/workflows/telegram_sync.yml)
powershell -Command "$yaml = @'
name: Sync Appunti su Telegram

on:
  push:
    branches:
      - main
    paths-ignore:
      - 'telegram_state.json'
      - 'sync_telegram.py'
      - 'setup.bat'
      - '.github/**'

permissions:
  contents: write

jobs:
  sync:
    runs-on: ubuntu-latest
    steps:
      - name: Checkout repository
        uses: actions/checkout@v4

      - name: Set up Python
        uses: actions/setup-python@v5
        with:
          python-version: '3.x'

      - name: Install dependencies
        run: pip install requests

      - name: Run Sync Script
        env:
          TELEGRAM_TOKEN: ${{ secrets.TELEGRAM_TOKEN }}
          TELEGRAM_CHAT_ID: ${{ secrets.TELEGRAM_CHAT_ID }}
        run: python sync_telegram.py

      - name: Commit updated state
        run: |
          git config --global user.name \"github-actions[bot]\"
          git config --global user.email \"github-actions[bot]@users.noreply.github.com\"
          git add telegram_state.json
          git diff --staged --quiet || git commit -m \"Aggiorna stato Telegram [skip ci]\"
          git push
'@; Set-Content -Path '.github\workflows\telegram_sync.yml' -Value $yaml -Encoding UTF8"

:: 5. Crea un file .gitignore per non caricare il file setup.bat su GitHub
echo setup.bat > .gitignore

:: 6. Inizializza Git e prepara il primo commit
git init
git branch -M main
git add .
git commit -m "Primo commit: struttura automatica Telegram"

echo.
echo ===================================================
echo   TUTTO PRONTO!
echo ===================================================
echo Ora segui gli ultimi passaggi scritti nella guida per collegare GitHub.
pause