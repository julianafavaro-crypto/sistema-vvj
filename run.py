import os
import subprocess
import sys

port = os.environ.get('PORT', '8080')
cmd = ['gunicorn', 'app:app', '--bind', f'0.0.0.0:{port}', '--workers', '2']
subprocess.run(cmd)
