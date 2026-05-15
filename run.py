import os
import subprocess
from database import init_db

# Inicializa banco e usuários padrão antes de subir
init_db()

port = os.environ.get('PORT', '8080')
cmd = ['gunicorn', 'app:app', '--bind', f'0.0.0.0:{port}', '--workers', '2']
subprocess.run(cmd)
