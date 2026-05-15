import os, sqlite3
from datetime import date

# ── Detecção de ambiente ───────────────────────────────────────────────────────
try:
    from dotenv import load_dotenv
    load_dotenv()
except ImportError:
    pass

DATABASE_URL = os.environ.get('DATABASE_URL', '')
USE_PG = bool(DATABASE_URL)
DB = "gestao.db"   # SQLite local


# ── Wrapper de compatibilidade SQLite ↔ PostgreSQL ────────────────────────────
class _PgRow(dict):
    """Dict com acesso por atributo e por índice (compatível com sqlite3.Row)."""
    def __getattr__(self, k):
        try: return self[k]
        except KeyError: raise AttributeError(k)
    def __getitem__(self, k):
        if isinstance(k, int):
            return list(self.values())[k]
        return super().__getitem__(k)

class _PgCursor:
    def __init__(self, cur, conn):
        self._cur = cur; self._conn = conn
        self.lastrowid = None

    def fetchone(self):
        r = self._cur.fetchone()
        return _PgRow(r) if r else None

    def fetchall(self):
        return [_PgRow(r) for r in self._cur.fetchall()]

    def __iter__(self):
        return (self.fetchall()).__iter__()

class _PgConn:
    def __init__(self, raw):
        self._raw = raw

    def execute(self, sql, params=None):
        import psycopg2.extras
        sql2 = (sql
            .replace('?', '%s')
            .replace("date('now')", 'CURRENT_DATE')
            .replace("(date('now'))", '(CURRENT_DATE)')
            .replace('AUTOINCREMENT', '')
            .replace('INTEGER PRIMARY KEY', 'SERIAL PRIMARY KEY')
        )
        cur = self._raw.cursor(cursor_factory=psycopg2.extras.RealDictCursor)
        cur.execute(sql2, params or [])
        pgcur = _PgCursor(cur, self._raw)
        if sql.strip().upper().startswith('INSERT'):
            try:
                cur2 = self._raw.cursor()
                cur2.execute('SELECT lastval()')
                pgcur.lastrowid = cur2.fetchone()[0]
            except Exception:
                pgcur.lastrowid = None
        return pgcur

    def commit(self): self._raw.commit()
    def close(self):  self._raw.close()


def get_db():
    if USE_PG:
        import psycopg2
        url = DATABASE_URL.replace('postgres://', 'postgresql://', 1)
        conn = psycopg2.connect(url)
        conn.autocommit = False
        return _PgConn(conn)
    else:
        conn = sqlite3.connect(DB)
        conn.row_factory = sqlite3.Row
        conn.execute("PRAGMA foreign_keys = ON")
        return conn

CHECKLISTS = {
    "CAR": ["Matrícula do imóvel", "CCIR atualizado", "CPF/CNPJ do proprietário", "Planta de localização", "Declaração de uso do solo", "Vistoria de campo"],
    "Georreferenciamento": ["Matrícula do imóvel", "CCIR", "Planta antiga (se houver)", "ART paga", "Vistoria de campo SIGEF", "Processamento QGIS/AutoCAD", "Submissão SIGEF/INCRA", "Certificação INCRA"],
    "Reserva Legal": ["CAR aprovado", "Mapa de uso do solo", "Proposta de RL", "ART emitida", "Protocolo IAT", "Aprovação IAT", "Averbação em cartório"],
    "PRAD": ["Auto de infração ou demanda", "Diagnóstico ambiental", "Projeto PRAD elaborado", "ART emitida", "Protocolo IBAMA/IAT", "Aprovação do órgão", "Implantação monitorada"],
    "Licenciamento Ambiental": ["Requerimento preenchido", "Matrícula", "Planta de localização", "Memorial descritivo", "ART", "Protocolo IAT/IBAMA", "Vistoria de campo", "LP emitida", "LI emitida", "LO emitida"],
    "Averbação": ["Certidão de matrícula atualizada", "Planta aprovada", "ART", "Ofício ao cartório", "Registro cartorário"],
    "ITR/CCIR": ["CPF do proprietário", "Matrícula", "NIRF (ITR)", "Área declarada", "Declaração uso e cobertura", "DIAT/DITR emitida"],
    "SIGARH": ["Outorga de uso da água", "Planta de captação", "Dados de consumo", "Cadastro SIGARH", "Protocolo SUDERHSA"],
    "Laudo CREA": ["Dados do imóvel", "Vistoria técnica", "Registro fotográfico", "Laudo elaborado", "ART vinculada"],
    "Retificação Administrativa": ["Certidão de matrícula", "Planta atual", "Memorial descritivo", "Requerimento UCT/SMU", "Protocolo prefeitura", "Aprovação"],
    "Outro": ["Definir escopo com cliente", "Coletar documentação", "Elaborar produto técnico", "Protocolar se necessário", "Entregar ao cliente"],
}

FASES = ["Captação", "Execução", "Entrega", "Faturamento"]
STATUS_OPTIONS = ["Em andamento", "Aguardando cliente", "Aguardando órgão", "Concluído", "Cancelado", "Proposta enviada", "Proposta aprovada"]

# Equipe técnica — nome: serviços sob sua responsabilidade principal
EQUIPE = {
    "Juliana":           ["CAR", "Reserva Legal", "PRAD", "Laudo CREA", "SIGARH", "Outro"],
    "Adriane Ciliao":    ["Licenciamento Ambiental", "Averbação", "Retificação Administrativa"],
    "Ricardo":           ["Georreferenciamento"],   # planta e memorial descritivo
    "Paulo Cesar":       ["ITR/CCIR"],
    "Luciana":           [],
    "Helena":            [],   # coordenadora da equipe
    "Dirley Schimidlen": [],   # gerência / prospecção
}

# Responsável padrão por tipo de serviço (para preencher automaticamente)
RESPONSAVEL_PADRAO = {
    "Georreferenciamento":        "Ricardo",
    "ITR/CCIR":                   "Paulo Cesar",
    "Licenciamento Ambiental":    "Adriane Ciliao",
    "Averbação":                  "Adriane Ciliao",
    "Retificação Administrativa": "Adriane Ciliao",
    "CAR":                        "Juliana",
    "Reserva Legal":              "Juliana",
    "PRAD":                       "Juliana",
    "Laudo CREA":                 "Juliana",
    "SIGARH":                     "Juliana",
    "Outro":                      "Juliana",
}

# Lista de prospectantes (quem capta/indica clientes)
PROSPECTANTES = ["Juliana", "Dirley Schimidlen", "Ricardo", "Indicação", "Site", "Instagram", "WhatsApp", "Outro"]

def init_db():
    conn = get_db()
    c = conn.cursor()

    c.execute("""CREATE TABLE IF NOT EXISTS clientes (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        tipo TEXT DEFAULT 'PF',
        cpf_cnpj TEXT,
        email TEXT,
        telefone TEXT,
        endereco TEXT,
        cidade TEXT,
        estado TEXT DEFAULT 'PR',
        estado_civil TEXT DEFAULT 'Não informado',
        prospectante TEXT,
        observacoes TEXT,
        created_at TEXT DEFAULT (date('now'))
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS projetos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER REFERENCES clientes(id),
        nome TEXT NOT NULL,
        tipo_servico TEXT,
        fase TEXT DEFAULT 'Captação',
        status TEXT DEFAULT 'Em andamento',
        numero_processo TEXT,
        orgao TEXT,
        area TEXT,
        responsavel TEXT DEFAULT 'Juliana',
        valor_total REAL DEFAULT 0,
        valor_entrada REAL DEFAULT 0,
        data_inicio TEXT,
        data_previsao TEXT,
        data_conclusao TEXT,
        descricao TEXT,
        observacoes TEXT,
        created_at TEXT DEFAULT (date('now'))
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS tarefas (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        projeto_id INTEGER REFERENCES projetos(id) ON DELETE CASCADE,
        descricao TEXT NOT NULL,
        fase TEXT,
        concluida INTEGER DEFAULT 0,
        data_conclusao TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS pagamentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        projeto_id INTEGER REFERENCES projetos(id) ON DELETE CASCADE,
        descricao TEXT,
        valor REAL NOT NULL,
        data_vencimento TEXT,
        data_pagamento TEXT,
        status TEXT DEFAULT 'Pendente',
        forma TEXT DEFAULT 'Pix'
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS historico (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        projeto_id INTEGER REFERENCES projetos(id) ON DELETE CASCADE,
        descricao TEXT NOT NULL,
        data TEXT DEFAULT (date('now'))
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS documentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        cliente_id INTEGER REFERENCES clientes(id) ON DELETE CASCADE,
        projeto_id INTEGER REFERENCES projetos(id) ON DELETE SET NULL,
        nome_original TEXT NOT NULL,
        nome_arquivo TEXT NOT NULL,
        categoria TEXT DEFAULT 'Outros',
        caminho TEXT NOT NULL,
        tamanho INTEGER,
        data_upload TEXT DEFAULT (date('now')),
        observacao TEXT
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS fornecedores (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        tipo TEXT DEFAULT 'PJ',
        cpf_cnpj TEXT,
        categoria TEXT,
        contato TEXT,
        telefone TEXT,
        email TEXT,
        cidade TEXT,
        estado TEXT DEFAULT 'PR',
        observacoes TEXT,
        created_at TEXT DEFAULT (date('now'))
    )""")

    c.execute("""CREATE TABLE IF NOT EXISTS usuarios (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        nome TEXT NOT NULL,
        login TEXT NOT NULL UNIQUE,
        senha_hash TEXT NOT NULL,
        perfil TEXT DEFAULT 'tecnico',
        cargo TEXT,
        ativo INTEGER DEFAULT 1,
        created_at TEXT DEFAULT (date('now'))
    )""")

    # Cria usuários padrão se não existirem
    from werkzeug.security import generate_password_hash
    usuarios_padrao = [
        ("Juliana",          "juliana",  "vvj2026", "proprietario", "Proprietária"),
        ("Patrícia",         "patricia", "vvj2026", "proprietario", "Proprietária"),
        ("Dirley",           "dirley",   "vvj2026", "proprietario", "Proprietário"),
        ("Venicius",         "venicius", "vvj2026", "proprietario", "Proprietário"),
        ("Adriane Ciliao",   "adriane",  "vvj2026", "tecnico",      "Licenciamento"),
        ("Ricardo",          "ricardo",  "vvj2026", "tecnico",      "Georreferenciamento"),
        ("Helena",           "helena",   "vvj2026", "tecnico",      "Coordenadora"),
        ("Luciana",          "luciana",  "vvj2026", "tecnico",      "Técnica"),
    ]
    for nome, login, senha, perfil, cargo in usuarios_padrao:
        existe = c.execute("SELECT id FROM usuarios WHERE login=?", [login]).fetchone()
        if not existe:
            c.execute(
                "INSERT INTO usuarios (nome, login, senha_hash, perfil, cargo) VALUES (?,?,?,?,?)",
                [nome, login, generate_password_hash(senha), perfil, cargo]
            )

    conn.commit()
    conn.close()

CATEGORIAS_FORNECEDOR = [
    "Topografia / Geo", "Cartório", "Laboratório", "Gráfica / Impressão",
    "Transporte / Campo", "Consultoria Jurídica", "Consultoria Ambiental",
    "TI / Software", "Contador / Financeiro", "Outros"
]

PASTA_DOCS = r"C:\Users\julia\OneDrive\Documentos\Clientes JF Florestal"

CATEGORIAS_DOC = [
    # Pessoais PF
    "CNH", "RG/CPF", "Comprovante Residência",
    "Certidão Casamento", "Certidão Divórcio",
    # Empresariais PJ
    "Contrato Social", "Cartão CNPJ",
    # Imóvel
    "Matrícula", "CCIR", "CAR", "ITR",
    # Técnicos / Serviço
    "Planta", "Memorial Descritivo", "ART",
    "Proposta", "Contrato de Serviço", "Laudo", "PRAD",
    # Outros
    "Procuração", "Outros"
]

# Checklist de documentos necessários por tipo de cliente
DOCS_CHECKLIST = {
    'PF': {
        'Documentos Pessoais': ['CNH', 'Comprovante Residência'],
        'Se casado': ['Certidão Casamento'],
        'Se divorciado': ['Certidão Divórcio'],
        'Imóvel': ['Matrícula', 'CCIR', 'CAR', 'ITR'],
    },
    'PJ': {
        'Documentos da Empresa': ['Contrato Social', 'Cartão CNPJ', 'Matrícula'],
        'Representante Legal': ['CNH', 'Comprovante Residência'],
        'Imóvel': ['CCIR', 'CAR', 'ITR'],
    }
}

import re, os

def pasta_cliente(nome_cliente):
    nome_limpo = re.sub(r'[<>:"/\\|?*]', '', nome_cliente).strip()[:60]
    return os.path.join(PASTA_DOCS, nome_limpo)
