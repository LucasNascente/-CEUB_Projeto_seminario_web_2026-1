from flask import Flask, request, jsonify
import sqlite3

app = Flask(__name__)
DB = 'usuarios.db'
PERFIS = {
    'administrador': ['cadastrar', 'listar', 'editar', 'excluir'],
    'tecnico': ['listar', 'editar'],
    'solicitante': ['listar'],
}

def conectar():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def iniciar_banco():
    with conectar() as db:
        db.execute('''CREATE TABLE IF NOT EXISTS usuarios (
            id INTEGER PRIMARY KEY AUTOINCREMENT,
            nome TEXT NOT NULL,
            email TEXT NOT NULL UNIQUE,
            perfil TEXT NOT NULL
        )''')

@app.post('/usuarios')
def cadastrar():
    dados = request.get_json(silent=True) or {}
    if not dados.get('nome') or not dados.get('email') or dados.get('perfil') not in PERFIS:
        return jsonify(erro='Informe nome, email e perfil válido'), 400
    try:
        with conectar() as db:
            cur = db.execute('INSERT INTO usuarios (nome,email,perfil) VALUES (?,?,?)',
                             (dados['nome'], dados['email'], dados['perfil']))
            return jsonify(id=cur.lastrowid, mensagem='Usuário cadastrado'), 201
    except sqlite3.IntegrityError:
        return jsonify(erro='E-mail já cadastrado'), 409

@app.get('/usuarios')
def listar():
    with conectar() as db:
        return jsonify([dict(u) for u in db.execute('SELECT * FROM usuarios ORDER BY id')])

@app.put('/usuarios/<int:id>')
def editar(id):
    dados = request.get_json(silent=True) or {}
    if not dados.get('nome') or not dados.get('email') or dados.get('perfil') not in PERFIS:
        return jsonify(erro='Informe nome, email e perfil válido'), 400
    try:
        with conectar() as db:
            cur = db.execute('UPDATE usuarios SET nome=?, email=?, perfil=? WHERE id=?',
                             (dados['nome'], dados['email'], dados['perfil'], id))
            if not cur.rowcount:
                return jsonify(erro='Usuário não encontrado'), 404
        return jsonify(mensagem='Usuário atualizado')
    except sqlite3.IntegrityError:
        return jsonify(erro='E-mail já cadastrado'), 409

@app.delete('/usuarios/<int:id>')
def excluir(id):
    with conectar() as db:
        cur = db.execute('DELETE FROM usuarios WHERE id=?', (id,))
        if not cur.rowcount:
            return jsonify(erro='Usuário não encontrado'), 404
    return jsonify(mensagem='Usuário excluído')

@app.get('/perfis')
def perfis():
    return jsonify(PERFIS)

if __name__ == '__main__':
    iniciar_banco()
    app.run(debug=True)
