import os, re, sys
sys.stdout.reconfigure(encoding='utf-8')
from database import get_db

BASE = r'C:\Users\julia\OneDrive\Documentos\Clientes JF Florestal'
SUBPASTAS = ['CNH', 'Matricula', 'CCIR', 'CAR', 'Contrato', 'Proposta', 'Laudo', 'Outros']

db = get_db()
clientes = db.execute('SELECT id, nome FROM clientes ORDER BY nome').fetchall()
db.close()

criadas = 0
for c in clientes:
    nome_limpo = re.sub(r'[<>:"/\\|?*]', '', c['nome']).strip()[:60]
    pasta = os.path.join(BASE, nome_limpo)
    for sub in SUBPASTAS:
        caminho = os.path.join(pasta, sub)
        os.makedirs(caminho, exist_ok=True)
        criadas += 1

total_clientes = len(clientes)
print(f"Clientes: {total_clientes}")
print(f"Pastas criadas: {criadas}")
print(f"Local: {BASE}")
