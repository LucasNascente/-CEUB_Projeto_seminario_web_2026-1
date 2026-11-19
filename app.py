from flask import Flask, request, redirect, url_for, render_template_string, flash
import sqlite3

app = Flask(__name__)
app.secret_key = 'demo-local-change-me'
DB = 'usuarios.db'
PERFIS = {'administrador': 'Cadastrar, listar, editar e excluir usuários', 'tecnico': 'Consultar usuários e atualizar atendimentos', 'solicitante': 'Consultar e abrir chamados'}

def conectar():
    db = sqlite3.connect(DB)
    db.row_factory = sqlite3.Row
    return db

def iniciar():
    with conectar() as db:
        db.execute('CREATE TABLE IF NOT EXISTS usuarios (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT NOT NULL, email TEXT NOT NULL UNIQUE, perfil TEXT NOT NULL)')

HTML = '''<!doctype html><html lang="pt-br"><head><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>CRUD de Usuários</title><style>
*{box-sizing:border-box}body{margin:0;background:#f2f5fa;color:#17243b;font-family:Arial,sans-serif}header{background:#173f76;color:white;padding:24px 0}.wrap{max-width:1000px;margin:auto;padding:0 20px}h1{margin:0;font-size:26px}header p{margin:7px 0 0;color:#dce8ff}main{padding-top:28px!important}.grid{display:grid;grid-template-columns:330px 1fr;gap:20px}.card{background:white;border:1px solid #e0e6ee;border-radius:12px;padding:22px;box-shadow:0 4px 14px #1c376008}h2{font-size:19px;margin:0 0 18px}label{display:block;font-size:13px;font-weight:bold;margin:14px 0 6px}input,select{width:100%;padding:11px;border:1px solid #cbd4df;border-radius:7px;font-size:14px}button,.btn{background:#215b9b;color:white;border:0;border-radius:7px;padding:10px 14px;cursor:pointer;font-size:14px;text-decoration:none;display:inline-block}button:hover,.btn:hover{background:#174778}.submit{width:100%;margin-top:18px}.danger{background:#b43a46}.danger:hover{background:#8c2531}.muted{color:#65748b;font-size:13px}.table-wrap{overflow-x:auto}table{width:100%;border-collapse:collapse;font-size:14px}th,td{text-align:left;padding:12px 8px;border-bottom:1px solid #e9edf3}th{color:#52657e;font-size:12px;text-transform:uppercase}.actions{display:flex;gap:6px;align-items:center}.actions form{margin:0}.actions button,.actions .btn{font-size:12px;padding:7px 9px}.pill{display:inline-block;padding:5px 8px;border-radius:30px;background:#eaf1ff;color:#244c86;font-size:12px}.notice{padding:12px;background:#eaf6ed;border-radius:8px;margin-bottom:16px;color:#205b32}.profiles{margin-top:20px}.profiles p{margin:9px 0;font-size:14px}@media(max-width:750px){.grid{grid-template-columns:1fr}}
</style></head><body><header><div class="wrap"><h1>Gestão de Usuários</h1><p>CRUD simples • Flask + SQLite</p></div></header><main class="wrap">{% for m in get_flashed_messages() %}<div class="notice">{{m}}</div>{% endfor %}<div class="grid"><section class="card"><h2>{{ 'Editar usuário' if usuario else 'Cadastrar usuário' }}</h2><form method="post" action="{{url_for('editar', id=usuario['id']) if usuario else url_for('cadastrar')}}"><label>Nome</label><input name="nome" required maxlength="120" value="{{usuario['nome'] if usuario else ''}}" placeholder="Nome completo"><label>E-mail</label><input name="email" type="email" required maxlength="180" value="{{usuario['email'] if usuario else ''}}" placeholder="usuario@email.com"><label>Perfil</label><select name="perfil" required>{% for p in perfis %}<option value="{{p}}" {% if usuario and usuario['perfil']==p %}selected{% endif %}>{{p|capitalize}}</option>{% endfor %}</select><button class="submit">{{'Salvar alterações' if usuario else 'Cadastrar usuário'}}</button>{% if usuario %}<p><a href="/">Cancelar edição</a></p>{% endif %}</form></section><section class="card"><h2>Usuários cadastrados ({{usuarios|length}})</h2><div class="table-wrap"><table><thead><tr><th>ID</th><th>Nome</th><th>E-mail</th><th>Perfil</th><th>Ações</th></tr></thead><tbody>{% for u in usuarios %}<tr><td>{{u['id']}}</td><td>{{u['nome']}}</td><td>{{u['email']}}</td><td><span class="pill">{{u['perfil']|capitalize}}</span></td><td><div class="actions"><a class="btn" href="{{url_for('editar',id=u['id'])}}">Editar</a><form method="post" action="{{url_for('excluir',id=u['id'])}}" onsubmit="return confirm('Excluir este usuário?')"><button class="danger">Excluir</button></form></div></td></tr>{% else %}<tr><td colspan="5" class="muted">Nenhum usuário cadastrado ainda.</td></tr>{% endfor %}</tbody></table></div></section></div><section class="card profiles"><h2>Perfis e funcionalidades</h2>{% for perfil, descricao in perfis.items() %}<p><strong>{{perfil|capitalize}}:</strong> {{descricao}}</p>{% endfor %}<p class="muted">Demonstração acadêmica: os perfis são cadastrados, mas não há autenticação ou bloqueio de permissões nesta versão.</p></section></main></body></html>'''

@app.get('/')
def inicio():
    with conectar() as db:
        usuarios = db.execute('SELECT * FROM usuarios ORDER BY id DESC').fetchall()
    return render_template_string(HTML, usuarios=usuarios, usuario=None, perfis=PERFIS)

@app.post('/cadastrar')
def cadastrar():
    nome = request.form.get('nome','').strip()
    email = request.form.get('email','').strip().lower()
    perfil = request.form.get('perfil','')
    if not nome or not email or perfil not in PERFIS:
        flash('Preencha os dados corretamente.')
    else:
        try:
            with conectar() as db:
                db.execute('INSERT INTO usuarios (nome,email,perfil) VALUES (?,?,?)',(nome,email,perfil))
            flash('Usuário cadastrado com sucesso!')
        except sqlite3.IntegrityError:
            flash('Este e-mail já está cadastrado.')
    return redirect(url_for('inicio'))

@app.route('/editar/<int:id>', methods=['GET','POST'])
def editar(id):
    with conectar() as db:
        usuario = db.execute('SELECT * FROM usuarios WHERE id=?',(id,)).fetchone()
        if usuario is None:
            flash('Usuário não encontrado.')
            return redirect(url_for('inicio'))
        if request.method == 'POST':
            nome = request.form.get('nome','').strip()
            email = request.form.get('email','').strip().lower()
            perfil = request.form.get('perfil','')
            if not nome or not email or perfil not in PERFIS:
                flash('Preencha os dados corretamente.')
            else:
                try:
                    db.execute('UPDATE usuarios SET nome=?,email=?,perfil=? WHERE id=?',(nome,email,perfil,id))
                    db.commit()
                    flash('Usuário atualizado com sucesso!')
                    return redirect(url_for('inicio'))
                except sqlite3.IntegrityError:
                    flash('Este e-mail já está cadastrado.')
        usuarios = db.execute('SELECT * FROM usuarios ORDER BY id DESC').fetchall()
    return render_template_string(HTML, usuarios=usuarios, usuario=usuario, perfis=PERFIS)

@app.post('/excluir/<int:id>')
def excluir(id):
    with conectar() as db:
        db.execute('DELETE FROM usuarios WHERE id=?',(id,))
    flash('Usuário excluído.')
    return redirect(url_for('inicio'))

if __name__ == '__main__':
    iniciar()
    app.run(debug=True)
