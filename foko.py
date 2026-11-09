"""Módulo Foko — serviços feitos em parceria com a FOKO Geotecnologias.

Regra de divisão: lucro = recebido do cliente − custas pagas; cada parte fica com
o percentual combinado (padrão 50/50). Os recebimentos entram na conta da JF.
Custas pagas pela Foko são ressarcidas a ela antes da divisão do lucro.
"""
from datetime import date
from functools import wraps
from flask import (Blueprint, render_template, request, redirect, url_for,
                   flash, session, send_file)
from database import get_db
import storage as doc_storage

foko_bp = Blueprint("foko", __name__, url_prefix="/foko")

EXTENSOES_OK = {"pdf", "doc", "docx", "xls", "xlsx", "png", "jpg", "jpeg",
                "dwg", "dxf", "kml", "shp", "zip", "rar", "txt", "odt"}
STATUS_FOKO = ["Em andamento", "Aguardando cliente", "Aguardando órgão",
               "Proposta aprovada", "Concluído", "Cancelado"]
TIPOS_MOV = {
    "recebimento": "Recebimento do cliente",
    "custo": "Custa / despesa",
    "repasse": "Repasse à Foko",
}
_tabelas_ok = False


def garantir_tabelas():
    global _tabelas_ok
    if _tabelas_ok:
        return
    db = get_db()
    db.execute("""CREATE TABLE IF NOT EXISTS foko_servicos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        titulo TEXT NOT NULL,
        cliente_nome TEXT,
        projeto_id INTEGER,
        valor_total REAL DEFAULT 0,
        percentual_foko REAL DEFAULT 50,
        status TEXT DEFAULT 'Em andamento',
        data_contrato TEXT,
        observacoes TEXT,
        created_at TEXT
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS foko_movimentos (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        servico_id INTEGER REFERENCES foko_servicos(id) ON DELETE CASCADE,
        tipo TEXT NOT NULL,
        descricao TEXT,
        valor REAL NOT NULL,
        data TEXT,
        pago_por TEXT DEFAULT 'JF'
    )""")
    db.execute("""CREATE TABLE IF NOT EXISTS foko_docs (
        id INTEGER PRIMARY KEY AUTOINCREMENT,
        servico_id INTEGER REFERENCES foko_servicos(id) ON DELETE CASCADE,
        nome_original TEXT NOT NULL,
        caminho TEXT NOT NULL,
        categoria TEXT DEFAULT 'Contrato',
        tamanho INTEGER,
        data_upload TEXT
    )""")
    db.commit()
    db.close()
    _tabelas_ok = True


@foko_bp.before_request
def _antes():
    if not session.get("usuario_id"):
        return redirect(url_for("login"))
    if session.get("perfil") != "proprietario":
        flash("Acesso restrito aos proprietários.", "error")
        return redirect(url_for("dashboard"))
    garantir_tabelas()


def resumo(servico, movs):
    """Calcula a divisão financeira de um serviço."""
    pct = float(servico["percentual_foko"] if servico["percentual_foko"] is not None else 50)
    total = float(servico["valor_total"] or 0)
    recebido = sum(m["valor"] for m in movs if m["tipo"] == "recebimento")
    custos = sum(m["valor"] for m in movs if m["tipo"] == "custo")
    custos_foko = sum(m["valor"] for m in movs if m["tipo"] == "custo" and m["pago_por"] == "Foko")
    repassado = sum(m["valor"] for m in movs if m["tipo"] == "repasse")
    lucro = recebido - custos
    parte_foko = lucro * pct / 100
    parte_jf = lucro - parte_foko
    # Foko recebe: sua parte do lucro + custas que ela mesma pagou − o que já foi repassado
    a_repassar = parte_foko + custos_foko - repassado
    lucro_prev = total - custos
    return {
        "pct_foko": pct, "pct_jf": 100 - pct,
        "recebido": recebido, "a_receber": max(total - recebido, 0),
        "custos": custos, "lucro": lucro,
        "parte_foko": parte_foko, "parte_jf": parte_jf,
        "repassado": repassado, "a_repassar": a_repassar,
        "lucro_prev": lucro_prev,
        "parte_foko_prev": lucro_prev * pct / 100,
        "parte_jf_prev": lucro_prev - lucro_prev * pct / 100,
    }


def _movs(db, servico_id=None):
    if servico_id is None:
        return db.execute("SELECT * FROM foko_movimentos ORDER BY data DESC, id DESC").fetchall()
    return db.execute("SELECT * FROM foko_movimentos WHERE servico_id=? ORDER BY data DESC, id DESC",
                      [servico_id]).fetchall()


def _num(txt, padrao=0.0):
    try:
        return float(str(txt).replace(",", ".")) if txt not in (None, "") else padrao
    except ValueError:
        return padrao


@foko_bp.route("/")
def index():
    db = get_db()
    servicos = db.execute("SELECT * FROM foko_servicos ORDER BY id DESC").fetchall()
    movs = _movs(db)
    db.close()
    linhas = []
    tot = {k: 0.0 for k in ("valor_total", "recebido", "a_receber", "custos", "lucro",
                            "parte_foko", "parte_jf", "a_repassar", "lucro_prev")}
    for s in servicos:
        r = resumo(s, [m for m in movs if m["servico_id"] == s["id"]])
        linhas.append((s, r))
        tot["valor_total"] += float(s["valor_total"] or 0)
        for k in ("recebido", "a_receber", "custos", "lucro", "parte_foko",
                  "parte_jf", "a_repassar", "lucro_prev"):
            tot[k] += r[k]
    return render_template("foko.html", linhas=linhas, tot=tot)


@foko_bp.route("/novo", methods=["GET", "POST"])
def novo():
    db = get_db()
    if request.method == "POST":
        cur = db.execute(
            """INSERT INTO foko_servicos (titulo, cliente_nome, projeto_id, valor_total,
               percentual_foko, status, data_contrato, observacoes, created_at)
               VALUES (?,?,?,?,?,?,?,?,?)""",
            [request.form["titulo"], request.form.get("cliente_nome", ""),
             request.form.get("projeto_id") or None,
             _num(request.form.get("valor_total")),
             _num(request.form.get("percentual_foko"), 50),
             request.form.get("status", "Em andamento"),
             request.form.get("data_contrato", ""),
             request.form.get("observacoes", ""), date.today().isoformat()])
        sid = cur.lastrowid
        db.commit()
        db.close()
        flash("Serviço Foko cadastrado!", "success")
        return redirect(url_for("foko.detalhe", id=sid))
    projetos = db.execute("SELECT id, nome FROM projetos ORDER BY nome").fetchall()
    db.close()
    return render_template("foko_form.html", s=None, projetos=projetos,
                           status_foko=STATUS_FOKO, titulo="Novo serviço com a Foko")


@foko_bp.route("/<int:id>/editar", methods=["GET", "POST"])
def editar(id):
    db = get_db()
    s = db.execute("SELECT * FROM foko_servicos WHERE id=?", [id]).fetchone()
    if not s:
        db.close()
        return redirect(url_for("foko.index"))
    if request.method == "POST":
        db.execute(
            """UPDATE foko_servicos SET titulo=?, cliente_nome=?, projeto_id=?, valor_total=?,
               percentual_foko=?, status=?, data_contrato=?, observacoes=? WHERE id=?""",
            [request.form["titulo"], request.form.get("cliente_nome", ""),
             request.form.get("projeto_id") or None,
             _num(request.form.get("valor_total")),
             _num(request.form.get("percentual_foko"), 50),
             request.form.get("status", "Em andamento"),
             request.form.get("data_contrato", ""),
             request.form.get("observacoes", ""), id])
        db.commit()
        db.close()
        flash("Serviço atualizado!", "success")
        return redirect(url_for("foko.detalhe", id=id))
    projetos = db.execute("SELECT id, nome FROM projetos ORDER BY nome").fetchall()
    db.close()
    return render_template("foko_form.html", s=s, projetos=projetos,
                           status_foko=STATUS_FOKO, titulo="Editar serviço Foko")


@foko_bp.route("/<int:id>")
def detalhe(id):
    db = get_db()
    s = db.execute("SELECT * FROM foko_servicos WHERE id=?", [id]).fetchone()
    if not s:
        db.close()
        flash("Serviço não encontrado.", "error")
        return redirect(url_for("foko.index"))
    movs = _movs(db, id)
    docs = db.execute("SELECT * FROM foko_docs WHERE servico_id=? ORDER BY id DESC", [id]).fetchall()
    projeto = None
    if s["projeto_id"]:
        projeto = db.execute("SELECT id, nome FROM projetos WHERE id=?", [s["projeto_id"]]).fetchone()
    db.close()
    return render_template("foko_detalhe.html", s=s, movs=movs, docs=docs, projeto=projeto,
                           r=resumo(s, movs), tipos_mov=TIPOS_MOV, hoje=date.today().isoformat())


@foko_bp.route("/<int:id>/excluir", methods=["POST"])
def excluir(id):
    db = get_db()
    for d in db.execute("SELECT caminho FROM foko_docs WHERE servico_id=?", [id]).fetchall():
        doc_storage.excluir(d["caminho"])
    db.execute("DELETE FROM foko_docs WHERE servico_id=?", [id])
    db.execute("DELETE FROM foko_movimentos WHERE servico_id=?", [id])
    db.execute("DELETE FROM foko_servicos WHERE id=?", [id])
    db.commit()
    db.close()
    flash("Serviço removido.", "info")
    return redirect(url_for("foko.index"))


@foko_bp.route("/<int:id>/movimento", methods=["POST"])
def movimento_novo(id):
    tipo = request.form.get("tipo", "recebimento")
    if tipo not in TIPOS_MOV:
        tipo = "recebimento"
    valor = _num(request.form.get("valor"))
    if valor <= 0:
        flash("Informe um valor maior que zero.", "error")
        return redirect(url_for("foko.detalhe", id=id))
    db = get_db()
    db.execute(
        """INSERT INTO foko_movimentos (servico_id, tipo, descricao, valor, data, pago_por)
           VALUES (?,?,?,?,?,?)""",
        [id, tipo, request.form.get("descricao", "") or TIPOS_MOV[tipo], valor,
         request.form.get("data") or date.today().isoformat(),
         request.form.get("pago_por", "JF") if tipo == "custo" else "JF"])
    db.commit()
    db.close()
    return redirect(url_for("foko.detalhe", id=id))


@foko_bp.route("/movimento/<int:mid>/excluir", methods=["POST"])
def movimento_excluir(mid):
    db = get_db()
    m = db.execute("SELECT servico_id FROM foko_movimentos WHERE id=?", [mid]).fetchone()
    db.execute("DELETE FROM foko_movimentos WHERE id=?", [mid])
    db.commit()
    db.close()
    return redirect(url_for("foko.detalhe", id=m["servico_id"]) if m else url_for("foko.index"))


@foko_bp.route("/<int:id>/documento", methods=["POST"])
def documento_upload(id):
    arquivo = request.files.get("arquivo")
    if not arquivo or not arquivo.filename:
        flash("Nenhum arquivo selecionado.", "error")
        return redirect(url_for("foko.detalhe", id=id))
    ext = arquivo.filename.rsplit(".", 1)[-1].lower() if "." in arquivo.filename else ""
    if ext not in EXTENSOES_OK:
        flash("Tipo de arquivo não permitido.", "error")
        return redirect(url_for("foko.detalhe", id=id))
    categoria = request.form.get("categoria", "Contrato")
    chave, _nome, tamanho = doc_storage.upload(arquivo, "Foko", categoria)
    db = get_db()
    db.execute(
        """INSERT INTO foko_docs (servico_id, nome_original, caminho, categoria, tamanho, data_upload)
           VALUES (?,?,?,?,?,?)""",
        [id, arquivo.filename, chave, categoria, tamanho, date.today().isoformat()])
    db.commit()
    db.close()
    flash(f"Arquivo '{arquivo.filename}' anexado.", "success")
    return redirect(url_for("foko.detalhe", id=id))


@foko_bp.route("/documento/<int:did>")
def documento_abrir(did):
    db = get_db()
    d = db.execute("SELECT * FROM foko_docs WHERE id=?", [did]).fetchone()
    db.close()
    if not d or not doc_storage.disponivel(d["caminho"]):
        flash("Arquivo não encontrado.", "error")
        return redirect(url_for("foko.index"))
    stream, _mime, nome = doc_storage.stream_download(d["caminho"], d["nome_original"])
    mime = "application/pdf" if nome.lower().endswith(".pdf") else "application/octet-stream"
    return send_file(stream, download_name=nome, mimetype=mime,
                     as_attachment=request.args.get("baixar") == "1")


@foko_bp.route("/documento/<int:did>/excluir", methods=["POST"])
def documento_excluir(did):
    db = get_db()
    d = db.execute("SELECT * FROM foko_docs WHERE id=?", [did]).fetchone()
    sid = d["servico_id"] if d else None
    if d:
        doc_storage.excluir(d["caminho"])
        db.execute("DELETE FROM foko_docs WHERE id=?", [did])
        db.commit()
    db.close()
    return redirect(url_for("foko.detalhe", id=sid) if sid else url_for("foko.index"))
