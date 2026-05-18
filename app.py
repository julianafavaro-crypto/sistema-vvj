from flask import Flask, render_template, request, redirect, url_for, jsonify, flash, send_file, session
from database import get_db, init_db, CHECKLISTS, FASES, STATUS_OPTIONS, CATEGORIAS_DOC, DOCS_CHECKLIST, EQUIPE, RESPONSAVEL_PADRAO, PROSPECTANTES, CATEGORIAS_FORNECEDOR, pasta_cliente
from datetime import date, datetime
from functools import wraps
import json, os, re, shutil
from werkzeug.utils import secure_filename
from werkzeug.security import generate_password_hash, check_password_hash
import storage as doc_storage

app = Flask(__name__)
app.secret_key = os.environ.get('SECRET_KEY', 'vvj-sistema-2026-dev')

# ── DECORADORES DE ACESSO ─────────────────────────────────────────────────────

def login_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('usuario_id'):
            flash("Faça login para continuar.", "info")
            return redirect(url_for('login'))
        return f(*args, **kwargs)
    return decorated

def proprietario_required(f):
    @wraps(f)
    def decorated(*args, **kwargs):
        if not session.get('usuario_id'):
            return redirect(url_for('login'))
        if session.get('perfil') != 'proprietario':
            flash("Acesso restrito aos proprietários.", "error")
            return redirect(url_for('dashboard'))
        return f(*args, **kwargs)
    return decorated

@app.context_processor
def inject_usuario():
    return dict(
        usuario_nome=session.get('usuario_nome', ''),
        usuario_perfil=session.get('perfil', ''),
        eh_proprietario=(session.get('perfil') == 'proprietario')
    )

EXTENSOES_PERMITIDAS = {'pdf','doc','docx','xls','xlsx','png','jpg','jpeg','gif','kml','shp','dwg','dxf','zip','rar','txt','odt'}

def extensao_ok(filename):
    return '.' in filename and filename.rsplit('.',1)[1].lower() in EXTENSOES_PERMITIDAS

def icone_doc(nome):
    ext = nome.rsplit('.',1)[-1].lower() if '.' in nome else ''
    return {'pdf':'📄','doc':'📝','docx':'📝','xls':'📊','xlsx':'📊',
            'png':'🖼','jpg':'🖼','jpeg':'🖼','kml':'🗺','shp':'🗺',
            'dwg':'📐','dxf':'📐','zip':'🗜','rar':'🗜'}.get(ext,'📎')

@app.context_processor
def inject_globals():
    return dict(hoje=date.today().isoformat(), fases=FASES, status_options=STATUS_OPTIONS,
                tipos_servico=list(CHECKLISTS.keys()), categorias_doc=CATEGORIAS_DOC, icone_doc=icone_doc)

# ─── LOGIN / LOGOUT ──────────────────────────────────────────────────────────

@app.route("/login", methods=["GET", "POST"])
def login():
    if session.get('usuario_id'):
        return redirect(url_for('dashboard'))
    if request.method == "POST":
        login_input = request.form.get("login", "").strip().lower()
        senha = request.form.get("senha", "")
        db = get_db()
        usuario = db.execute("SELECT * FROM usuarios WHERE login=? AND ativo=1", [login_input]).fetchone()
        db.close()
        if usuario and check_password_hash(usuario["senha_hash"], senha):
            session['usuario_id']   = usuario["id"]
            session['usuario_nome'] = usuario["nome"]
            session['perfil']       = usuario["perfil"]
            return redirect(url_for('dashboard'))
        flash("Login ou senha incorretos.", "error")
    return render_template("login.html")

@app.route("/logout")
def logout():
    session.clear()
    return redirect(url_for('login'))

@app.route("/minha-senha", methods=["POST"])
@login_required
def alterar_senha():
    nova = request.form.get("nova_senha", "")
    conf = request.form.get("confirmar_senha", "")
    if nova != conf or len(nova) < 4:
        flash("Senhas não conferem ou muito curta (mín. 4 caracteres).", "error")
        return redirect(request.referrer or url_for('dashboard'))
    db = get_db()
    db.execute("UPDATE usuarios SET senha_hash=? WHERE id=?",
               [generate_password_hash(nova), session['usuario_id']])
    db.commit(); db.close()
    flash("Senha alterada com sucesso!", "success")
    return redirect(url_for('dashboard'))

# ─── EQUIPE ──────────────────────────────────────────────────────────────────

@app.route("/equipe")
@proprietario_required
def equipe():
    db = get_db()
    membros = db.execute("SELECT * FROM usuarios ORDER BY perfil DESC, nome").fetchall()
    db.close()
    return render_template("equipe.html", membros=membros)

@app.route("/equipe/novo", methods=["GET","POST"])
@proprietario_required
def equipe_novo():
    if request.method == "POST":
        login_novo = request.form.get("login","").strip().lower()
        senha = request.form.get("senha","vvj2026")
        db = get_db()
        existente = db.execute("SELECT id FROM usuarios WHERE login=?", [login_novo]).fetchone()
        if existente:
            flash("Login já existe. Escolha outro.", "error")
            db.close()
            return redirect(url_for('equipe_novo'))
        db.execute("""INSERT INTO usuarios (nome, login, senha_hash, perfil, cargo)
                      VALUES (?,?,?,?,?)""",
                   [request.form["nome"], login_novo,
                    generate_password_hash(senha),
                    request.form.get("perfil","tecnico"),
                    request.form.get("cargo","")])
        db.commit(); db.close()
        flash(f"Membro cadastrado! Login: {login_novo} / Senha: {senha}", "success")
        return redirect(url_for('equipe'))
    return render_template("equipe_form.html", membro=None, titulo="Novo Membro")

@app.route("/equipe/<int:id>/editar", methods=["GET","POST"])
@proprietario_required
def equipe_editar(id):
    db = get_db()
    membro = db.execute("SELECT * FROM usuarios WHERE id=?", [id]).fetchone()
    if request.method == "POST":
        nova_senha = request.form.get("nova_senha","").strip()
        if nova_senha:
            db.execute("UPDATE usuarios SET nome=?,perfil=?,cargo=?,ativo=?,senha_hash=? WHERE id=?",
                       [request.form["nome"], request.form.get("perfil","tecnico"),
                        request.form.get("cargo",""), int(request.form.get("ativo",1)),
                        generate_password_hash(nova_senha), id])
        else:
            db.execute("UPDATE usuarios SET nome=?,perfil=?,cargo=?,ativo=? WHERE id=?",
                       [request.form["nome"], request.form.get("perfil","tecnico"),
                        request.form.get("cargo",""), int(request.form.get("ativo",1)), id])
        db.commit(); db.close()
        flash("Membro atualizado!", "success")
        return redirect(url_for('equipe'))
    db.close()
    return render_template("equipe_form.html", membro=membro, titulo="Editar Membro")

@app.route("/equipe/<int:id>/excluir", methods=["POST"])
@proprietario_required
def equipe_excluir(id):
    if id == session.get('usuario_id'):
        flash("Não é possível excluir seu próprio usuário.", "error")
        return redirect(url_for('equipe'))
    db = get_db()
    db.execute("DELETE FROM usuarios WHERE id=?", [id])
    db.commit(); db.close()
    flash("Membro removido.", "info")
    return redirect(url_for('equipe'))

# ─── DASHBOARD ───────────────────────────────────────────────────────────────

@app.route("/")
@login_required
def dashboard():
    db = get_db()
    projetos = db.execute("SELECT p.*, c.nome as cliente_nome FROM projetos p LEFT JOIN clientes c ON p.cliente_id=c.id ORDER BY p.created_at DESC").fetchall()
    clientes = db.execute("SELECT COUNT(*) as total FROM clientes").fetchone()
    financeiro = db.execute("SELECT COALESCE(SUM(valor),0) as total FROM pagamentos WHERE status='Pago'").fetchone()
    a_receber = db.execute("SELECT COALESCE(SUM(valor),0) as total FROM pagamentos WHERE status='Pendente'").fetchone()
    atrasados = db.execute("SELECT COALESCE(SUM(valor),0) as total FROM pagamentos WHERE status='Pendente' AND data_vencimento < ?", [date.today().isoformat()]).fetchone()

    por_fase = {f: 0 for f in FASES}
    por_status = {}
    for p in projetos:
        por_fase[p["fase"]] = por_fase.get(p["fase"], 0) + 1
        por_status[p["status"]] = por_status.get(p["status"], 0) + 1

    from datetime import timedelta
    data_7dias = (date.today() + timedelta(days=7)).isoformat()
    alertas = db.execute("""
        SELECT p.id, p.nome, c.nome as cliente_nome, p.data_previsao, p.fase
        FROM projetos p LEFT JOIN clientes c ON p.cliente_id=c.id
        WHERE p.data_previsao IS NOT NULL AND p.data_previsao <= ?
        AND p.fase != 'Faturamento' AND p.status != 'Concluído'
        ORDER BY p.data_previsao
    """, [data_7dias]).fetchall()

    pagamentos_atrasados = db.execute("""
        SELECT pg.*, p.nome as projeto_nome FROM pagamentos pg
        JOIN projetos p ON pg.projeto_id=p.id
        WHERE pg.status='Pendente' AND pg.data_vencimento < ?
        ORDER BY pg.data_vencimento
    """, [date.today().isoformat()]).fetchall()

    db.close()
    return render_template("dashboard.html",
        projetos=projetos, total_clientes=clientes["total"],
        total_recebido=financeiro["total"], total_a_receber=a_receber["total"],
        total_atrasado=atrasados["total"],
        por_fase=por_fase, por_status=por_status,
        alertas=alertas, pagamentos_atrasados=pagamentos_atrasados)

# ─── CLIENTES ────────────────────────────────────────────────────────────────

@app.route("/clientes")
@login_required
def clientes():
    db = get_db()
    busca = request.args.get("busca", "")
    if busca:
        rows = db.execute("SELECT * FROM clientes WHERE nome LIKE ? OR cpf_cnpj LIKE ? OR cidade LIKE ? ORDER BY nome", [f"%{busca}%"]*3).fetchall()
    else:
        rows = db.execute("SELECT * FROM clientes ORDER BY nome").fetchall()
    db.close()
    return render_template("clientes.html", clientes=rows, busca=busca)

@app.route("/clientes/novo", methods=["GET","POST"])
def cliente_novo():
    if request.method == "POST":
        db = get_db()
        db.execute("INSERT INTO clientes (nome,tipo,cpf_cnpj,email,telefone,endereco,cidade,estado,estado_civil,prospectante,observacoes) VALUES (?,?,?,?,?,?,?,?,?,?,?)",
            [request.form["nome"], request.form["tipo"], request.form.get("cpf_cnpj",""),
             request.form.get("email",""), request.form.get("telefone",""),
             request.form.get("endereco",""), request.form.get("cidade",""),
             request.form.get("estado","PR"), request.form.get("estado_civil","Não informado"),
             request.form.get("prospectante","") or None,
             request.form.get("observacoes","")])
        db.commit()
        db.close()
        flash("Cliente cadastrado com sucesso!", "success")
        return redirect(url_for("clientes"))
    return render_template("cliente_form.html", cliente=None, titulo="Novo Cliente", prospectantes=PROSPECTANTES)

@app.route("/clientes/<int:id>/editar", methods=["GET","POST"])
def cliente_editar(id):
    db = get_db()
    cliente = db.execute("SELECT * FROM clientes WHERE id=?", [id]).fetchone()
    if request.method == "POST":
        db.execute("UPDATE clientes SET nome=?,tipo=?,cpf_cnpj=?,email=?,telefone=?,endereco=?,cidade=?,estado=?,estado_civil=?,prospectante=?,observacoes=? WHERE id=?",
            [request.form["nome"], request.form["tipo"], request.form.get("cpf_cnpj",""),
             request.form.get("email",""), request.form.get("telefone",""),
             request.form.get("endereco",""), request.form.get("cidade",""),
             request.form.get("estado","PR"), request.form.get("estado_civil","Não informado"),
             request.form.get("prospectante","") or None,
             request.form.get("observacoes",""), id])
        db.commit()
        db.close()
        flash("Cliente atualizado!", "success")
        return redirect(url_for("clientes"))
    db.close()
    return render_template("cliente_form.html", cliente=cliente, titulo="Editar Cliente", prospectantes=PROSPECTANTES)

@app.route("/clientes/<int:id>/excluir", methods=["POST"])
def cliente_excluir(id):
    db = get_db()
    db.execute("DELETE FROM clientes WHERE id=?", [id])
    db.commit()
    db.close()
    flash("Cliente removido.", "info")
    return redirect(url_for("clientes"))

# ─── PROJETOS ────────────────────────────────────────────────────────────────

@app.route("/projetos")
def projetos():
    db = get_db()
    fase   = request.args.get("fase", "")
    status = request.args.get("status", "")
    busca  = request.args.get("busca", "")
    aba    = request.args.get("aba", "ativos")   # "ativos" | "arquivados"

    base = "SELECT p.*, c.nome as cliente_nome FROM projetos p LEFT JOIN clientes c ON p.cliente_id=c.id WHERE "
    base += "p.arquivado=1" if aba == "arquivados" else "p.arquivado=0 OR p.arquivado IS NULL"
    params = []
    if fase:
        base += " AND p.fase=?"; params.append(fase)
    if status:
        base += " AND p.status=?"; params.append(status)
    if busca:
        base += " AND (p.nome LIKE ? OR c.nome LIKE ? OR p.numero_processo LIKE ?)"; params += [f"%{busca}%"]*3
    base += " ORDER BY p.created_at DESC"

    rows = db.execute(base, params).fetchall()
    total_arquivados = db.execute("SELECT COUNT(*) FROM projetos WHERE arquivado=1").fetchone()[0]
    db.close()
    return render_template("projetos.html", projetos=rows, fase=fase, status=status,
                           busca=busca, aba=aba, total_arquivados=total_arquivados)

@app.route("/projetos/novo", methods=["GET","POST"])
def projeto_novo():
    db = get_db()
    if request.method == "POST":
        tipo = request.form.get("tipo_servico","Outro")
        cur = db.execute(
            "INSERT INTO projetos (cliente_id,nome,tipo_servico,fase,status,numero_processo,orgao,area,responsavel,valor_total,valor_entrada,data_inicio,data_previsao,descricao,observacoes) VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)",
            [request.form.get("cliente_id") or None, request.form["nome"], tipo,
             request.form.get("fase","Captação"), request.form.get("status","Em andamento"),
             request.form.get("numero_processo",""), request.form.get("orgao",""),
             request.form.get("area",""), request.form.get("responsavel","Juliana"),
             float(request.form.get("valor_total",0) or 0),
             float(request.form.get("valor_entrada",0) or 0),
             request.form.get("data_inicio",""), request.form.get("data_previsao",""),
             request.form.get("descricao",""), request.form.get("observacoes","")])
        proj_id = cur.lastrowid
        for item in CHECKLISTS.get(tipo, CHECKLISTS["Outro"]):
            db.execute("INSERT INTO tarefas (projeto_id, descricao, fase) VALUES (?,?,?)", [proj_id, item, "Execução"])
        db.execute("INSERT INTO historico (projeto_id, descricao) VALUES (?,?)", [proj_id, "Projeto criado"])
        valor_entrada = float(request.form.get("valor_entrada",0) or 0)
        if valor_entrada > 0:
            db.execute("INSERT INTO pagamentos (projeto_id,descricao,valor,data_vencimento,status) VALUES (?,?,?,?,?)",
                [proj_id, "Entrada", valor_entrada, request.form.get("data_inicio",""), "Pendente"])
        db.commit()
        db.close()
        flash("Projeto criado com sucesso!", "success")
        return redirect(url_for("projeto_detalhe", id=proj_id))
    clientes_list = db.execute("SELECT id, nome FROM clientes ORDER BY nome").fetchall()
    db.close()
    return render_template("projeto_form.html", projeto=None, clientes=clientes_list,
                           equipe=list(EQUIPE.keys()), responsavel_padrao=RESPONSAVEL_PADRAO,
                           titulo="Novo Projeto")

@app.route("/projetos/<int:id>")
def projeto_detalhe(id):
    db = get_db()
    projeto = db.execute("SELECT p.*, c.nome as cliente_nome, c.telefone as cliente_tel, c.email as cliente_email FROM projetos p LEFT JOIN clientes c ON p.cliente_id=c.id WHERE p.id=?", [id]).fetchone()
    tarefas = db.execute("SELECT * FROM tarefas WHERE projeto_id=? ORDER BY fase, id", [id]).fetchall()
    pagamentos = db.execute("SELECT * FROM pagamentos WHERE projeto_id=? ORDER BY data_vencimento", [id]).fetchall()
    historico = db.execute("SELECT * FROM historico WHERE projeto_id=? ORDER BY id DESC", [id]).fetchall()
    custos = db.execute("SELECT * FROM custos WHERE projeto_id=? ORDER BY data DESC", [id]).fetchall()
    total_pago = sum(p["valor"] for p in pagamentos if p["status"] == "Pago")
    total_pendente = sum(p["valor"] for p in pagamentos if p["status"] == "Pendente")
    total_custos = sum(c["valor"] for c in custos)
    total_custos_a_cobrar = sum(c["valor"] for c in custos if c["status"] == "A cobrar")
    tarefas_total = len(tarefas)
    tarefas_ok = sum(1 for t in tarefas if t["concluida"])
    progresso = int(tarefas_ok / tarefas_total * 100) if tarefas_total else 0
    clientes_list = db.execute("SELECT id, nome FROM clientes ORDER BY nome").fetchall()
    db.close()
    return render_template("projeto_detalhe.html", projeto=projeto, tarefas=tarefas,
        pagamentos=pagamentos, historico=historico, custos=custos,
        total_pago=total_pago, total_pendente=total_pendente,
        total_custos=total_custos, total_custos_a_cobrar=total_custos_a_cobrar,
        progresso=progresso, tarefas_ok=tarefas_ok,
        tarefas_total=tarefas_total, clientes=clientes_list,
        categorias_custo=CATEGORIAS_CUSTO)

@app.route("/projetos/<int:id>/editar", methods=["GET","POST"])
def projeto_editar(id):
    db = get_db()
    if request.method == "POST":
        fase_anterior = db.execute("SELECT fase FROM projetos WHERE id=?", [id]).fetchone()["fase"]
        nova_fase = request.form.get("fase","Captação")
        db.execute(
            "UPDATE projetos SET cliente_id=?,nome=?,tipo_servico=?,fase=?,status=?,numero_processo=?,orgao=?,area=?,responsavel=?,valor_total=?,data_inicio=?,data_previsao=?,data_conclusao=?,descricao=?,observacoes=? WHERE id=?",
            [request.form.get("cliente_id") or None, request.form["nome"],
             request.form.get("tipo_servico","Outro"), nova_fase,
             request.form.get("status","Em andamento"), request.form.get("numero_processo",""),
             request.form.get("orgao",""), request.form.get("area",""),
             request.form.get("responsavel","Juliana"),
             float(request.form.get("valor_total",0) or 0),
             request.form.get("data_inicio",""), request.form.get("data_previsao",""),
             request.form.get("data_conclusao",""),
             request.form.get("descricao",""), request.form.get("observacoes",""), id])
        if fase_anterior != nova_fase:
            db.execute("INSERT INTO historico (projeto_id, descricao) VALUES (?,?)", [id, f"Fase alterada: {fase_anterior} → {nova_fase}"])
        db.commit()
        db.close()
        flash("Projeto atualizado!", "success")
        return redirect(url_for("projeto_detalhe", id=id))
    projeto = db.execute("SELECT * FROM projetos WHERE id=?", [id]).fetchone()
    clientes_list = db.execute("SELECT id, nome FROM clientes ORDER BY nome").fetchall()
    db.close()
    return render_template("projeto_form.html", projeto=projeto, clientes=clientes_list,
                           equipe=list(EQUIPE.keys()), responsavel_padrao=RESPONSAVEL_PADRAO,
                           titulo="Editar Projeto")

@app.route("/projetos/<int:id>/excluir", methods=["POST"])
def projeto_excluir(id):
    db = get_db()
    db.execute("DELETE FROM projetos WHERE id=?", [id])
    db.commit()
    db.close()
    flash("Projeto removido.", "info")
    return redirect(url_for("projetos"))

@app.route("/projetos/<int:id>/arquivar", methods=["POST"])
def projeto_arquivar(id):
    db = get_db()
    projeto = db.execute("SELECT arquivado FROM projetos WHERE id=?", [id]).fetchone()
    novo_estado = 0 if projeto["arquivado"] else 1
    db.execute("UPDATE projetos SET arquivado=? WHERE id=?", [novo_estado, id])
    msg = "arquivado" if novo_estado else "reativado"
    db.execute("INSERT INTO historico (projeto_id, descricao) VALUES (?,?)", [id, f"Projeto {msg}."])
    db.commit()
    db.close()
    flash(f"Projeto {msg} com sucesso.", "success")
    if novo_estado:
        return redirect(url_for("projetos"))
    return redirect(url_for("projeto_detalhe", id=id))

@app.route("/projetos/<int:id>/avancar-fase", methods=["POST"])
def avancar_fase(id):
    db = get_db()
    projeto = db.execute("SELECT * FROM projetos WHERE id=?", [id]).fetchone()
    idx = FASES.index(projeto["fase"]) if projeto["fase"] in FASES else 0
    if idx < len(FASES) - 1:
        nova_fase = FASES[idx + 1]
        db.execute("UPDATE projetos SET fase=? WHERE id=?", [nova_fase, id])
        db.execute("INSERT INTO historico (projeto_id, descricao) VALUES (?,?)", [id, f"Avançou para fase: {nova_fase}"])
        db.commit()
    db.close()
    return redirect(url_for("projeto_detalhe", id=id))

# ─── TAREFAS ─────────────────────────────────────────────────────────────────

@app.route("/tarefas/<int:id>/toggle", methods=["POST"])
def tarefa_toggle(id):
    db = get_db()
    tarefa = db.execute("SELECT * FROM tarefas WHERE id=?", [id]).fetchone()
    nova = 1 - tarefa["concluida"]
    data = date.today().isoformat() if nova else None
    db.execute("UPDATE tarefas SET concluida=?, data_conclusao=? WHERE id=?", [nova, data, id])
    db.commit()
    proj_id = tarefa["projeto_id"]
    db.close()
    return redirect(url_for("projeto_detalhe", id=proj_id))

@app.route("/tarefas/nova", methods=["POST"])
def tarefa_nova():
    db = get_db()
    proj_id = request.form["projeto_id"]
    db.execute("INSERT INTO tarefas (projeto_id, descricao, fase) VALUES (?,?,?)",
        [proj_id, request.form["descricao"], request.form.get("fase","Execução")])
    db.execute("INSERT INTO historico (projeto_id, descricao) VALUES (?,?)", [proj_id, f"Tarefa adicionada: {request.form['descricao']}"])
    db.commit()
    db.close()
    return redirect(url_for("projeto_detalhe", id=proj_id))

# ─── PAGAMENTOS ──────────────────────────────────────────────────────────────

@app.route("/pagamentos/novo", methods=["POST"])
def pagamento_novo():
    db = get_db()
    proj_id = request.form["projeto_id"]
    db.execute("INSERT INTO pagamentos (projeto_id,descricao,valor,data_vencimento,forma,status) VALUES (?,?,?,?,?,?)",
        [proj_id, request.form["descricao"], float(request.form["valor"]),
         request.form.get("data_vencimento",""), request.form.get("forma","Pix"), "Pendente"])
    db.execute("INSERT INTO historico (projeto_id, descricao) VALUES (?,?)", [proj_id, f"Cobrança lançada: R$ {request.form['valor']}"])
    db.commit()
    db.close()
    return redirect(url_for("projeto_detalhe", id=proj_id))

@app.route("/pagamentos/<int:id>/pagar", methods=["POST"])
def pagamento_pagar(id):
    db = get_db()
    pg = db.execute("SELECT * FROM pagamentos WHERE id=?", [id]).fetchone()
    db.execute("UPDATE pagamentos SET status='Pago', data_pagamento=? WHERE id=?", [date.today().isoformat(), id])
    db.execute("INSERT INTO historico (projeto_id, descricao) VALUES (?,?)", [pg["projeto_id"], f"Pagamento recebido: R$ {pg['valor']:.2f}"])
    db.commit()
    proj_id = pg["projeto_id"]
    db.close()
    return redirect(url_for("projeto_detalhe", id=proj_id))

@app.route("/pagamentos/<int:id>/excluir", methods=["POST"])
def pagamento_excluir(id):
    db = get_db()
    pg = db.execute("SELECT * FROM pagamentos WHERE id=?", [id]).fetchone()
    proj_id = pg["projeto_id"]
    db.execute("DELETE FROM pagamentos WHERE id=?", [id])
    db.commit()
    db.close()
    return redirect(url_for("projeto_detalhe", id=proj_id))

# ─── CUSTOS DOCUMENTAIS ──────────────────────────────────────────────────────

CATEGORIAS_CUSTO = [
    "Taxa IBAMA/SINAFLOR", "Taxa IAT", "Taxa INCRA", "Taxa Cartório",
    "ART CREA", "Muda/Reposição Florestal", "Transporte/Campo",
    "Cópia/Impressão", "Despachante", "Outros"
]

@app.route("/custos/novo", methods=["POST"])
@login_required
def custo_novo():
    db = get_db()
    proj_id = request.form["projeto_id"]
    valor = float(request.form.get("valor", 0) or 0)
    descricao = request.form.get("descricao", "")
    db.execute("""INSERT INTO custos (projeto_id, descricao, valor, data, categoria, observacao)
                  VALUES (?,?,?,?,?,?)""",
        [proj_id, descricao, valor,
         request.form.get("data", date.today().isoformat()),
         request.form.get("categoria", "Outros"),
         request.form.get("observacao", "")])
    db.execute("INSERT INTO historico (projeto_id, descricao) VALUES (?,?)",
        [proj_id, f"Custo documental lançado: {descricao} — R$ {valor:.2f}"])
    db.commit()
    db.close()
    return redirect(url_for("projeto_detalhe", id=proj_id))

@app.route("/custos/<int:id>/cobrado", methods=["POST"])
@login_required
def custo_cobrado(id):
    db = get_db()
    custo = db.execute("SELECT * FROM custos WHERE id=?", [id]).fetchone()
    db.execute("UPDATE custos SET status='Cobrado' WHERE id=?", [id])
    db.execute("INSERT INTO historico (projeto_id, descricao) VALUES (?,?)",
        [custo["projeto_id"], f"Custo marcado como cobrado: {custo['descricao']} — R$ {custo['valor']:.2f}"])
    db.commit()
    proj_id = custo["projeto_id"]
    db.close()
    return redirect(url_for("projeto_detalhe", id=proj_id))

@app.route("/custos/<int:id>/excluir", methods=["POST"])
@login_required
def custo_excluir(id):
    db = get_db()
    custo = db.execute("SELECT * FROM custos WHERE id=?", [id]).fetchone()
    proj_id = custo["projeto_id"]
    db.execute("DELETE FROM custos WHERE id=?", [id])
    db.commit()
    db.close()
    return redirect(url_for("projeto_detalhe", id=proj_id))

# ─── HISTÓRICO ───────────────────────────────────────────────────────────────

@app.route("/historico/novo", methods=["POST"])
def historico_novo():
    db = get_db()
    proj_id = request.form["projeto_id"]
    db.execute("INSERT INTO historico (projeto_id, descricao) VALUES (?,?)", [proj_id, request.form["descricao"]])
    db.commit()
    db.close()
    return redirect(url_for("projeto_detalhe", id=proj_id))

# ─── PROPOSTA ────────────────────────────────────────────────────────────────

@app.route("/propostas")
@proprietario_required
def propostas():
    db = get_db()
    clientes_list = db.execute("SELECT id, nome, telefone, email, cpf_cnpj, cidade, estado FROM clientes ORDER BY nome").fetchall()
    db.close()
    return render_template("propostas.html", clientes=clientes_list, checklists=CHECKLISTS)

# ─── FINANCEIRO ──────────────────────────────────────────────────────────────

@app.route("/financeiro")
@proprietario_required
def financeiro():
    db = get_db()
    ano = request.args.get("ano", str(date.today().year))
    mes = request.args.get("mes", date.today().strftime("%Y-%m"))
    pagamentos = db.execute("""
        SELECT pg.*, p.nome as projeto_nome, c.nome as cliente_nome
        FROM pagamentos pg
        JOIN projetos p ON pg.projeto_id=p.id
        LEFT JOIN clientes c ON p.cliente_id=c.id
        WHERE substr(COALESCE(pg.data_pagamento, pg.data_vencimento), 1, 7) = ?
        ORDER BY pg.data_vencimento
    """, [mes]).fetchall()
    total_pago = sum(p["valor"] for p in pagamentos if p["status"] == "Pago")
    todos = db.execute("""
        SELECT pg.*, p.nome as projeto_nome, c.nome as cliente_nome
        FROM pagamentos pg
        JOIN projetos p ON pg.projeto_id=p.id
        LEFT JOIN clientes c ON p.cliente_id=c.id
        ORDER BY pg.data_vencimento DESC
    """).fetchall()
    # Totais gerais (todos os meses)
    total_pendente = sum(p["valor"] for p in todos if p["status"] == "Pendente")
    total_atrasado = sum(p["valor"] for p in todos if p["status"] == "Pendente" and p["data_vencimento"] and p["data_vencimento"] < date.today().isoformat())

    # Resumo anual mês a mês
    MESES_NOMES = ["Jan","Fev","Mar","Abr","Mai","Jun","Jul","Ago","Set","Out","Nov","Dez"]
    resumo_anual = []
    acumulado = 0.0
    for m in range(1, 13):
        chave = f"{ano}-{m:02d}"
        recebido = sum(p["valor"] for p in todos if p["status"] == "Pago" and p["data_pagamento"] and p["data_pagamento"].startswith(chave))
        pendente  = sum(p["valor"] for p in todos if p["status"] == "Pendente" and (p["data_vencimento"] or "").startswith(chave))
        acumulado += recebido
        resumo_anual.append({
            "mes": MESES_NOMES[m-1],
            "chave": chave,
            "recebido": recebido,
            "pendente": pendente,
            "acumulado": acumulado,
        })
    total_ano = acumulado

    db.close()
    return render_template("financeiro.html", pagamentos=pagamentos, todos=todos,
        mes=mes, ano=ano, total_pago=total_pago, total_pendente=total_pendente,
        total_atrasado=total_atrasado, resumo_anual=resumo_anual, total_ano=total_ano)

# ─── DETALHE DO CLIENTE ──────────────────────────────────────────────────────

@app.route("/clientes/<int:id>")
def cliente_detalhe(id):
    db = get_db()
    cliente  = db.execute("SELECT * FROM clientes WHERE id=?", [id]).fetchone()
    projetos = db.execute("SELECT * FROM projetos WHERE cliente_id=? ORDER BY created_at DESC", [id]).fetchall()
    documentos = db.execute("SELECT * FROM documentos WHERE cliente_id=? ORDER BY data_upload DESC", [id]).fetchall()
    # pagamentos agrupados por projeto_id
    pags_raw = db.execute("""SELECT * FROM pagamentos WHERE projeto_id IN
        (SELECT id FROM projetos WHERE cliente_id=?) ORDER BY data_vencimento""", [id]).fetchall()
    namespace_pags = {}
    for pg in pags_raw:
        namespace_pags.setdefault(pg["projeto_id"], []).append(pg)
    db.close()
    # Montar checklist de docs necessários com status (recebido/pendente)
    cats_enviadas = {d["categoria"] for d in documentos}
    checklist_grupos = DOCS_CHECKLIST.get(cliente["tipo"], DOCS_CHECKLIST["PF"])
    estado_civil = (cliente["estado_civil"] or "").lower()
    checklist = {}
    for grupo, docs in checklist_grupos.items():
        # Filtrar grupos condicionais
        if grupo == "Se casado" and "casado" not in estado_civil and "união" not in estado_civil:
            continue
        if grupo == "Se divorciado" and "divorciado" not in estado_civil:
            continue
        checklist[grupo] = [{"doc": d, "ok": d in cats_enviadas} for d in docs]
    db.close()
    return render_template("cliente_detalhe.html", cliente=cliente, projetos=projetos,
                           documentos=documentos, namespace_pags=namespace_pags,
                           checklist=checklist, cats_enviadas=cats_enviadas)

# ─── DOCUMENTOS ──────────────────────────────────────────────────────────────

@app.route("/documentos/upload", methods=["POST"])
def documento_upload():
    cliente_id = int(request.form["cliente_id"])
    projeto_id = request.form.get("projeto_id") or None
    categoria  = request.form.get("categoria", "Outros")
    observacao = request.form.get("observacao", "")
    arquivo    = request.files.get("arquivo")

    if not arquivo or arquivo.filename == "":
        flash("Nenhum arquivo selecionado.", "error")
        return redirect(url_for("cliente_detalhe", id=cliente_id))

    if not extensao_ok(arquivo.filename):
        flash("Tipo de arquivo não permitido.", "error")
        return redirect(url_for("cliente_detalhe", id=cliente_id))

    db = get_db()
    cliente = db.execute("SELECT nome FROM clientes WHERE id=?", [cliente_id]).fetchone()

    nome_orig = arquivo.filename
    chave, nome_arquivo, tamanho = doc_storage.upload(arquivo, cliente["nome"], categoria)

    db.execute("""INSERT INTO documentos (cliente_id, projeto_id, nome_original, nome_arquivo, categoria, caminho, tamanho, observacao)
                  VALUES (?,?,?,?,?,?,?,?)""",
        [cliente_id, projeto_id, nome_orig, nome_arquivo, categoria, chave, tamanho, observacao])
    db.commit()
    db.close()
    flash(f"Arquivo '{nome_orig}' enviado com sucesso!", "success")
    return redirect(url_for("cliente_detalhe", id=cliente_id))

@app.route("/documentos/<int:id>/download")
def documento_download(id):
    db = get_db()
    doc = db.execute("SELECT * FROM documentos WHERE id=?", [id]).fetchone()
    db.close()
    if not doc or not doc_storage.disponivel(doc["caminho"]):
        flash("Arquivo não encontrado.", "error")
        return redirect(url_for("clientes"))
    stream, mime, nome = doc_storage.stream_download(doc["caminho"], doc["nome_original"])
    return send_file(stream, as_attachment=True, download_name=nome, mimetype=mime)

@app.route("/documentos/<int:id>/abrir")
def documento_abrir(id):
    db = get_db()
    doc = db.execute("SELECT * FROM documentos WHERE id=?", [id]).fetchone()
    db.close()
    if not doc or not doc_storage.disponivel(doc["caminho"]):
        flash("Arquivo não encontrado.", "error")
        return redirect(url_for("clientes"))
    stream, mime, nome = doc_storage.stream_download(doc["caminho"], doc["nome_original"])
    return send_file(stream, download_name=nome, mimetype=mime)

@app.route("/documentos/<int:id>/excluir", methods=["POST"])
def documento_excluir(id):
    db = get_db()
    doc = db.execute("SELECT * FROM documentos WHERE id=?", [id]).fetchone()
    cliente_id = doc["cliente_id"]
    doc_storage.excluir(doc["caminho"])
    db.execute("DELETE FROM documentos WHERE id=?", [id])
    db.commit()
    db.close()
    flash("Documento removido.", "info")
    return redirect(url_for("cliente_detalhe", id=cliente_id))

@app.route("/clientes/<int:id>/abrir-pasta")
def abrir_pasta_cliente(id):
    # Funciona apenas localmente
    if doc_storage.USE_R2:
        flash("Pasta disponível apenas no OneDrive local.", "info")
        return redirect(url_for("cliente_detalhe", id=id))
    db = get_db()
    cliente = db.execute("SELECT nome FROM clientes WHERE id=?", [id]).fetchone()
    db.close()
    pasta = pasta_cliente(cliente["nome"])
    os.makedirs(pasta, exist_ok=True)
    os.startfile(pasta)
    return redirect(url_for("cliente_detalhe", id=id))

# ─── FORNECEDORES ────────────────────────────────────────────────────────────

@app.route("/fornecedores")
def fornecedores():
    db = get_db()
    busca = request.args.get("busca", "")
    categoria = request.args.get("categoria", "")
    q = "SELECT * FROM fornecedores WHERE 1=1"
    params = []
    if busca:
        q += " AND (nome LIKE ? OR contato LIKE ? OR cidade LIKE ?)"; params += [f"%{busca}%"]*3
    if categoria:
        q += " AND categoria=?"; params.append(categoria)
    q += " ORDER BY nome"
    rows = db.execute(q, params).fetchall()
    db.close()
    return render_template("fornecedores.html", fornecedores=rows, busca=busca,
                           categoria=categoria, categorias=CATEGORIAS_FORNECEDOR)

@app.route("/fornecedores/novo", methods=["GET","POST"])
def fornecedor_novo():
    if request.method == "POST":
        db = get_db()
        db.execute("""INSERT INTO fornecedores
            (nome,tipo,cpf_cnpj,categoria,contato,telefone,email,cidade,estado,observacoes)
            VALUES (?,?,?,?,?,?,?,?,?,?)""",
            [request.form["nome"], request.form.get("tipo","PJ"),
             request.form.get("cpf_cnpj",""), request.form.get("categoria",""),
             request.form.get("contato",""), request.form.get("telefone",""),
             request.form.get("email",""), request.form.get("cidade",""),
             request.form.get("estado","PR"), request.form.get("observacoes","")])
        db.commit(); db.close()
        flash("Fornecedor cadastrado!", "success")
        return redirect(url_for("fornecedores"))
    return render_template("fornecedor_form.html", fornecedor=None, titulo="Novo Fornecedor",
                           categorias=CATEGORIAS_FORNECEDOR)

@app.route("/fornecedores/<int:id>/editar", methods=["GET","POST"])
def fornecedor_editar(id):
    db = get_db()
    fornecedor = db.execute("SELECT * FROM fornecedores WHERE id=?", [id]).fetchone()
    if request.method == "POST":
        db.execute("""UPDATE fornecedores SET
            nome=?,tipo=?,cpf_cnpj=?,categoria=?,contato=?,telefone=?,email=?,cidade=?,estado=?,observacoes=?
            WHERE id=?""",
            [request.form["nome"], request.form.get("tipo","PJ"),
             request.form.get("cpf_cnpj",""), request.form.get("categoria",""),
             request.form.get("contato",""), request.form.get("telefone",""),
             request.form.get("email",""), request.form.get("cidade",""),
             request.form.get("estado","PR"), request.form.get("observacoes",""), id])
        db.commit(); db.close()
        flash("Fornecedor atualizado!", "success")
        return redirect(url_for("fornecedores"))
    db.close()
    return render_template("fornecedor_form.html", fornecedor=fornecedor, titulo="Editar Fornecedor",
                           categorias=CATEGORIAS_FORNECEDOR)

@app.route("/fornecedores/<int:id>/excluir", methods=["POST"])
def fornecedor_excluir(id):
    db = get_db()
    db.execute("DELETE FROM fornecedores WHERE id=?", [id])
    db.commit(); db.close()
    flash("Fornecedor removido.", "info")
    return redirect(url_for("fornecedores"))

if __name__ == "__main__":
    init_db()
    print("\n" + "="*50)
    print("  Sistema JF Florestal / VKS-Valls iniciado!")
    print("  Acesse: http://localhost:5000")
    print("="*50 + "\n")
    app.run(debug=False, host="0.0.0.0", port=5000)
