import os
import json
import hashlib
import requests
import subprocess
from datetime import datetime

TOKEN = os.environ['TELEGRAM_TOKEN']
CHAT_ID = os.environ['TELEGRAM_CHAT_ID']
STATE_FILE = 'telegram_state.json'

ALLOWED_EXTENSIONS = {'.pdf', '.md', '.txt', '.docx', '.pptx', '.zip', '.png', '.jpg', '.url'}
IGNORE_DIRS = {'.git', '.github', '__pycache__'}

def get_file_hash(filepath):
    h = hashlib.md5()
    with open(filepath, 'rb') as f:
        while chunk := f.read(8192):
            h.update(chunk)
    return h.hexdigest()

try:
    commit_msg = subprocess.check_output(['git', 'log', '-1', '--pretty=%B']).decode('utf-8', errors='ignore').strip()
except:
    commit_msg = ''

ignore_notes = {'Aggiornamento appunti', 'Aggiorna stato Telegram [skip ci]', 'Primo commit', 'Fix'}
note_text = f'\n📝 <b>Info:</b> <i>{commit_msg}</i>' if (commit_msg and commit_msg not in ignore_notes) else ''

if os.path.exists(STATE_FILE):
    with open(STATE_FILE, 'r', encoding='utf-8-sig') as f:
        state = json.load(f)
else:
    state = {'topics': {}, 'files': {}, 'hashes': {}, 'index_msg_id': None, 'issues_topic_id': None}

if 'hashes' not in state: state['hashes'] = {}
if 'issues_topic_id' not in state: state['issues_topic_id'] = None

state_updated = False
now = datetime.now().strftime('%d/%m/%Y %H:%M')

# --- 1. CREA TOPIC APERTO PER SEGNALAZIONE PROBLEMI (SE NON ESISTE) ---
if not state['issues_topic_id']:
    res = requests.post(f'https://api.telegram.org/bot{TOKEN}/createForumTopic', json={
        'chat_id': CHAT_ID,
        'name': '🛠️ Segnalazioni e Problemi'
    })
    if res.status_code == 200:
        issues_id = res.json()['result']['message_thread_id']
        state['issues_topic_id'] = issues_id
        state_updated = True
        welcome_issues = (
            '🛠️ <b>SEGNALAZIONE ERRORI E PROBLEMI</b>\n\n'
            'Hai trovato un errore di battitura, una formula sbagliata o un problema nei PDF?\n'
            'Scrivici pure qui sotto indicando:\n'
            '1️⃣ <b>Materia e nome del PDF</b>\n'
            '2️⃣ <b>Pagina / Capitolo</b>\n'
            '3️⃣ <b>Cosa correggere</b> (anche con uno screenshot!)'
        )
        requests.post(f'https://api.telegram.org/bot{TOKEN}/sendMessage', json={
            'chat_id': CHAT_ID, 'message_thread_id': issues_id, 'text': welcome_issues, 'parse_mode': 'HTML'
        })

subjects = [d for d in os.listdir('.') if os.path.isdir(d) and d not in IGNORE_DIRS and not d.startswith('.')]
subjects.sort()

# --- 2. PULIZIA AUTOMATICA CARTELLE RIMOSSE ---
for old_subj in list(state['topics'].keys()):
    if old_subj not in subjects:
        t_id = state['topics'][old_subj]
        requests.post(f'https://api.telegram.org/bot{TOKEN}/deleteForumTopic', json={'chat_id': CHAT_ID, 'message_thread_id': t_id})
        del state['topics'][old_subj]
        for f_path in list(state['files'].keys()):
            if f_path.startswith(old_subj + '/'):
                del state['files'][f_path]
                state['hashes'].pop(f_path, None)
        state_updated = True

# --- 3. PULIZIA AUTOMATICA SINGOLI FILE RIMOSSI ---
for f_path in list(state['files'].keys()):
    if not os.path.exists(f_path):
        msg_id = state['files'][f_path]
        requests.post(f'https://api.telegram.org/bot{TOKEN}/deleteMessage', json={'chat_id': CHAT_ID, 'message_id': msg_id})
        del state['files'][f_path]
        state['hashes'].pop(f_path, None)
        state_updated = True

# --- 4. SINCRONIZZAZIONE CARTELLE, FILE E LINK ---
for subject in subjects:
    if subject not in state['topics']:
        url = f'https://api.telegram.org/bot{TOKEN}/createForumTopic'
        topic_name = f'📚 {subject.replace("_", " ")}'
        res = requests.post(url, json={'chat_id': CHAT_ID, 'name': topic_name})
        
        if res.status_code == 200:
            topic_id = res.json()['result']['message_thread_id']
            state['topics'][subject] = topic_id
            state_updated = True
        else:
            continue

    topic_id = state['topics'][subject]
    
    # Chiude il topic della materia agli utenti normali (il bot e gli admin possono comunque postare!)
    requests.post(f'https://api.telegram.org/bot{TOKEN}/closeForumTopic', json={'chat_id': CHAT_ID, 'message_thread_id': topic_id})

    for root, dirs, files in os.walk(subject):
        for file in files:
            ext = os.path.splitext(file)[1].lower()
            if ext in ALLOWED_EXTENSIONS:
                rel_path = os.path.relpath(os.path.join(root, file), '.').replace('\\', '/')
                display_name = os.path.relpath(rel_path, subject).replace('\\', '/')
                
                current_hash = get_file_hash(rel_path)
                if rel_path in state['files'] and state['hashes'].get(rel_path) == current_hash:
                    continue

                if file.lower().endswith('.link.txt') or ext == '.url':
                    with open(rel_path, 'r', encoding='utf-8-sig') as lf:
                        raw_lines = [line.strip() for line in lf if line.strip()]
                    
                    if ext == '.url':
                        clean_title = display_name[:-4].replace('_', ' ')
                        target_url = ''
                        for l in raw_lines:
                            if l.upper().startswith('URL='):
                                target_url = l[4:].strip()
                        links_formatted = f'🌐 <a href="{target_url}"><b>{clean_title}</b></a>'
                    else:
                        clean_title = display_name[:-9].replace('_', ' ')
                        links_list = []
                        for l in raw_lines:
                            if '|' in l:
                                nome, indirizzo = l.split('|', 1)
                                links_list.append(f'🌐 <a href="{indirizzo.strip()}"><b>{nome.strip()}</b></a>')
                            else:
                                links_list.append(f'🌐 {l}')
                        links_formatted = '\n'.join(links_list)

                    msg_text = f'🔗 <b>{clean_title}</b>\n\n{links_formatted}{note_text}\n\n🔄 <i>Aggiornato il: {now}</i>'

                    if rel_path in state['files']:
                        msg_id = state['files'][rel_path]
                        res = requests.post(f'https://api.telegram.org/bot{TOKEN}/editMessageText', json={'chat_id': CHAT_ID, 'message_id': msg_id, 'text': msg_text, 'parse_mode': 'HTML'})
                        if res.status_code == 200:
                            state['hashes'][rel_path] = current_hash
                            state_updated = True
                    else:
                        res = requests.post(f'https://api.telegram.org/bot{TOKEN}/sendMessage', json={'chat_id': CHAT_ID, 'message_thread_id': topic_id, 'text': msg_text, 'parse_mode': 'HTML'})
                        if res.status_code == 200:
                            state['files'][rel_path] = res.json()['result']['message_id']
                            state['hashes'][rel_path] = current_hash
                            state_updated = True
                else:
                    caption = f'📚 <b>{subject.replace("_", " ")}</b>\n📄 <code>{display_name}</code>{note_text}\n🔄 <i>Aggiornato il: {now}</i>'

                    if rel_path in state['files']:
                        msg_id = state['files'][rel_path]
                        media = json.dumps({'type': 'document', 'media': 'attach://document', 'caption': caption, 'parse_mode': 'HTML'})
                        with open(rel_path, 'rb') as f:
                            res = requests.post(f'https://api.telegram.org/bot{TOKEN}/editMessageMedia', data={'chat_id': CHAT_ID, 'message_id': msg_id, 'media': media}, files={'document': f})
                        if res.status_code == 200:
                            state['hashes'][rel_path] = current_hash
                            state_updated = True
                    else:
                        with open(rel_path, 'rb') as f:
                            res = requests.post(f'https://api.telegram.org/bot{TOKEN}/sendDocument', data={'chat_id': CHAT_ID, 'message_thread_id': topic_id, 'caption': caption, 'parse_mode': 'HTML'}, files={'document': f})
                        if res.status_code == 200:
                            state['files'][rel_path] = res.json()['result']['message_id']
                            state['hashes'][rel_path] = current_hash
                            state_updated = True

# --- 5. AGGIORNAMENTO INDICE ---
if state['topics']:
    clean_chat_id = str(CHAT_ID).replace('-100', '')
    index_text = '🗂 <b>INDICE DELLE MATERIE</b>\n<i>Clicca su una materia per aprire la stanza con gli appunti aggiornati:</i>\n\n'
    for subj in sorted(state['topics'].keys()):
        t_id = state['topics'][subj]
        link = f'https://t.me/c/{clean_chat_id}/{t_id}'
        index_text += f'🔹 <a href="{link}"><b>{subj.replace("_", " ")}</b></a>\n'
    
    if state.get('issues_topic_id'):
        iss_link = f'https://t.me/c/{clean_chat_id}/{state["issues_topic_id"]}'
        index_text += f'\n🛠 <a href="{iss_link}"><b>Segnala un errore o problema qui</b></a>\n'

    index_text += f'\n🔄 <i>Ultimo controllo: {now}</i>'

    if not state['index_msg_id']:
        res = requests.post(f'https://api.telegram.org/bot{TOKEN}/sendMessage', json={'chat_id': CHAT_ID, 'text': index_text, 'parse_mode': 'HTML'})
        if res.status_code == 200:
            state['index_msg_id'] = res.json()['result']['message_id']
            state_updated = True
            requests.post(f'https://api.telegram.org/bot{TOKEN}/pinChatMessage', json={'chat_id': CHAT_ID, 'message_id': state['index_msg_id']})
    else:
        requests.post(f'https://api.telegram.org/bot{TOKEN}/editMessageText', json={'chat_id': CHAT_ID, 'message_id': state['index_msg_id'], 'text': index_text, 'parse_mode': 'HTML'})

if state_updated:
    with open(STATE_FILE, 'w', encoding='utf-8') as f:
        json.dump(state, f, indent=4)
