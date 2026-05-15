# Abstração de armazenamento de documentos.
# Local (dev):   salva no OneDrive local
# Producao (R2): salva no Cloudflare R2 (compativel com S3)
import os, io, re
from werkzeug.utils import secure_filename

# ── Configuração via variáveis de ambiente ─────────────────────────────────────
R2_ENDPOINT   = os.environ.get('R2_ENDPOINT', '')
R2_ACCESS_KEY = os.environ.get('R2_ACCESS_KEY', '')
R2_SECRET_KEY = os.environ.get('R2_SECRET_KEY', '')
R2_BUCKET     = os.environ.get('R2_BUCKET', 'vvj-docs')

USE_R2 = bool(R2_ENDPOINT and R2_ACCESS_KEY and R2_SECRET_KEY)

LOCAL_DOCS = os.environ.get(
    'LOCAL_DOCS_PATH',
    r'C:/Users/julia/OneDrive/Documentos/Clientes JF Florestal'
)

def _r2():
    import boto3
    from botocore.config import Config
    return boto3.client(
        's3',
        endpoint_url=R2_ENDPOINT,
        aws_access_key_id=R2_ACCESS_KEY,
        aws_secret_access_key=R2_SECRET_KEY,
        config=Config(signature_version='s3v4'),
        region_name='auto',
    )

def _nome_limpo(nome):
    return re.sub(r'[<>:"/\\|?*]', '', nome).strip()[:60]

# ── API pública ────────────────────────────────────────────────────────────────

def upload(arquivo_werkzeug, nome_cliente, categoria):
    """
    Recebe um FileStorage do Flask, salva no destino correto.
    Retorna (caminho_ou_chave, nome_arquivo, tamanho).
    """
    nome_orig   = arquivo_werkzeug.filename
    nome_seguro = secure_filename(nome_orig)
    if not nome_seguro:
        nome_seguro = "arquivo"

    if USE_R2:
        chave = f"{_nome_limpo(nome_cliente)}/{categoria}/{nome_seguro}"
        # Garantir chave única no bucket
        r2 = _r2()
        base, ext = os.path.splitext(chave)
        tentativa = chave
        c = 1
        while True:
            try:
                r2.head_object(Bucket=R2_BUCKET, Key=tentativa)
                tentativa = f"{base}_{c}{ext}"; c += 1
            except Exception:
                break
        arquivo_werkzeug.seek(0)
        r2.upload_fileobj(arquivo_werkzeug, R2_BUCKET, tentativa)
        arquivo_werkzeug.seek(0)
        tamanho = len(arquivo_werkzeug.read())
        return tentativa, tentativa.split('/')[-1], tamanho

    else:
        pasta = os.path.join(LOCAL_DOCS, _nome_limpo(nome_cliente), categoria)
        os.makedirs(pasta, exist_ok=True)
        caminho = os.path.join(pasta, nome_seguro)
        base, ext = os.path.splitext(caminho)
        c = 1
        while os.path.exists(caminho):
            caminho = f"{base}_{c}{ext}"; c += 1
        arquivo_werkzeug.save(caminho)
        tamanho = os.path.getsize(caminho)
        return caminho, os.path.basename(caminho), tamanho


def stream_download(caminho_ou_chave, nome_original):
    """
    Retorna (stream_io, mimetype, nome_para_download).
    """
    if USE_R2:
        obj = _r2().get_object(Bucket=R2_BUCKET, Key=caminho_ou_chave)
        data = obj['Body'].read()
        return io.BytesIO(data), 'application/octet-stream', nome_original
    else:
        with open(caminho_ou_chave, 'rb') as f:
            data = f.read()
        return io.BytesIO(data), 'application/octet-stream', nome_original


def excluir(caminho_ou_chave):
    """Remove o arquivo do armazenamento."""
    if USE_R2:
        try:
            _r2().delete_object(Bucket=R2_BUCKET, Key=caminho_ou_chave)
        except Exception:
            pass
    else:
        try:
            if os.path.exists(caminho_ou_chave):
                os.remove(caminho_ou_chave)
        except Exception:
            pass


def disponivel(caminho_ou_chave):
    """Verifica se o arquivo existe."""
    if USE_R2:
        try:
            _r2().head_object(Bucket=R2_BUCKET, Key=caminho_ou_chave)
            return True
        except Exception:
            return False
    else:
        return os.path.exists(caminho_ou_chave)
