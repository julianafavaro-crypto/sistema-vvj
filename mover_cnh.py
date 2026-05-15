import sys, os, shutil
sys.stdout.reconfigure(encoding='utf-8')
from database import get_db, init_db, pasta_cliente

init_db()
db = get_db()

cliente = db.execute("SELECT * FROM clientes WHERE nome LIKE '%KLINSMAN%'").fetchone()
if not cliente:
    print("Cliente Klinsman nao encontrado")
    db.close(); exit()

origem = r"C:\Users\julia\Downloads\CNH-e.pdf.pdf"
pasta = pasta_cliente(cliente['nome'])
destino_dir = os.path.join(pasta, "CNH")
os.makedirs(destino_dir, exist_ok=True)
destino = os.path.join(destino_dir, "CNH-e.pdf")

if os.path.exists(origem):
    shutil.copy2(origem, destino)
    tamanho = os.path.getsize(destino)
    db.execute("""INSERT INTO documentos (cliente_id, nome_original, nome_arquivo, categoria, caminho, tamanho, observacao)
                  VALUES (?,?,?,?,?,?,?)""",
        [cliente['id'], 'CNH-e.pdf', 'CNH-e.pdf', 'CNH', destino, tamanho, 'CNH digital - KLINSMAN FELIPE DA SILVEIRA - CPF 079.443.639-00'])
    db.commit()
    print(f"CNH copiada para: {destino}")
else:
    print(f"Arquivo original nao encontrado em: {origem}")

db.close()
