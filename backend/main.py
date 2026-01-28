import os
import sqlite3
from datetime import datetime
from typing import Optional
from fastapi import FastAPI, HTTPException, Header, Depends, BackgroundTasks
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel
from dotenv import load_dotenv

load_dotenv()

ADMIN_PASSWORD = os.getenv("ADMIN_PASSWORD")


app = FastAPI(title="FinancePro TechLead - Versão Estável Final")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)

DB_PATH = os.path.join(os.path.dirname(__file__), "database.db")

def get_db():
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn

def init_db():
    with get_db() as conn:
        conn.execute("CREATE TABLE IF NOT EXISTS categorias (id INTEGER PRIMARY KEY AUTOINCREMENT, nome TEXT UNIQUE)")
        conn.execute("""CREATE TABLE IF NOT EXISTS despesas (
            id INTEGER PRIMARY KEY AUTOINCREMENT, categoria_id INTEGER, valor REAL, 
            mes TEXT, vencimento TEXT, uso TEXT, pago BOOLEAN DEFAULT 0)""")
        conn.execute("CREATE TABLE IF NOT EXISTS configuracoes (mes TEXT PRIMARY KEY, renda_mensal REAL DEFAULT 0, fechado BOOLEAN DEFAULT 0)")
        conn.execute("CREATE TABLE IF NOT EXISTS logs_exportacao (id INTEGER PRIMARY KEY AUTOINCREMENT, mes TEXT, data TEXT, status TEXT)")
        
        cursor = conn.cursor()
        cols_config = [row['name'] for row in cursor.execute("PRAGMA table_info(configuracoes)").fetchall()]
        if 'fechado' not in cols_config:
            conn.execute("ALTER TABLE configuracoes ADD COLUMN fechado BOOLEAN DEFAULT 0")
            
        cols_logs = [row['name'] for row in cursor.execute("PRAGMA table_info(logs_exportacao)").fetchall()]
        if 'data' not in cols_logs:
            conn.execute("ALTER TABLE logs_exportacao ADD COLUMN data TEXT")

init_db()

class DespesaSchema(BaseModel):
    categoria_id: int
    valor: float
    mes: str
    vencimento: str
    uso: str 

def verificar_admin(x_admin_password: Optional[str] = Header(None)):
    if x_admin_password != "admin":
        raise HTTPException(status_code=403, detail="Acesso administrativo negado.")

def validar_bloqueio(mes: str):
    with get_db() as conn:
        res = conn.execute("SELECT fechado FROM configuracoes WHERE mes = ?", (mes,)).fetchone()
        if res and res['fechado']:
            raise HTTPException(status_code=400, detail="Mês encerrado. Alterações bloqueadas.")

@app.get("/dashboard-v2")
def get_dash(mes: str):
    with get_db() as conn:
        total = conn.execute("SELECT SUM(valor) FROM despesas WHERE mes = ?", (mes,)).fetchone()[0] or 0
        cfg = conn.execute("SELECT renda_mensal, fechado FROM configuracoes WHERE mes = ?", (mes,)).fetchone()
        renda = cfg['renda_mensal'] if cfg else 0
        fechado = bool(cfg['fechado']) if cfg else False
        
        fixo = conn.execute("SELECT SUM(valor) FROM despesas WHERE mes = ? AND uso = 'FIXO'", (mes,)).fetchone()[0] or 0
        variavel = conn.execute("SELECT SUM(valor) FROM despesas WHERE mes = ? AND uso = 'VARIAVEL'", (mes,)).fetchone()[0] or 0
        
        cats = conn.execute("""
            SELECT c.nome, SUM(d.valor) as total FROM despesas d 
            JOIN categorias c ON d.categoria_id = c.id WHERE d.mes = ? GROUP BY c.nome
        """, (mes,)).fetchall()
        
        return {
            "total_gastos": total, "renda_mensal": renda, "fechado": fechado,
            "fixo": fixo, "variavel": variavel,
            "percentual_uso": round((total/renda*100),1) if renda > 0 else 0,
            "distribuicao_categoria": [dict(r) for r in cats]
        }

@app.post("/despesas-v2")
def add_despesa(d: DespesaSchema, _ = Depends(verificar_admin)):
    validar_bloqueio(d.mes)
    with get_db() as conn:
        conn.execute("INSERT INTO despesas (categoria_id, valor, mes, vencimento, uso) VALUES (?,?,?,?,?)",
                     (d.categoria_id, d.valor, d.mes, d.vencimento, d.uso))
        conn.commit()
    return {"status": "ok"}

@app.patch("/despesas-v2/{id}/pagar")
def pagar(id: int, _ = Depends(verificar_admin)):
    with get_db() as conn:
        row = conn.execute("SELECT mes FROM despesas WHERE id = ?", (id,)).fetchone()
        if not row: raise HTTPException(status_code=404, detail="Não encontrado")
        validar_bloqueio(row['mes'])
        conn.execute("UPDATE despesas SET pago = 1 WHERE id = ?", (id,))
        conn.commit()
        return {"status": "ok"}

@app.delete("/despesas-v2/{id}")
def delete(id: int, _ = Depends(verificar_admin)):
    with get_db() as conn:
        row = conn.execute("SELECT mes FROM despesas WHERE id = ?", (id,)).fetchone()
        validar_bloqueio(row['mes'])
        conn.execute("DELETE FROM despesas WHERE id = ?", (id,))
        conn.commit()
    return {"status": "ok"}

@app.post("/config/fechar-mes")
def fechar(mes: str, bg: BackgroundTasks, _ = Depends(verificar_admin)):
    with get_db() as conn:
        conn.execute("INSERT INTO configuracoes (mes, fechado) VALUES (?, 1) ON CONFLICT(mes) DO UPDATE SET fechado=1", (mes,))
        conn.execute("INSERT INTO logs_exportacao (mes, data, status) VALUES (?,?,?)", 
                     (mes, datetime.now().strftime("%d/%m/%Y %H:%M"), "EXPORTADO"))
        conn.commit()
    return {"status": "fechado"}

@app.get("/despesas-v2")
def list_despesas(mes: str):
    with get_db() as conn:
        return [dict(r) for r in conn.execute("""
            SELECT d.*, c.nome as categoria FROM despesas d 
            JOIN categorias c ON d.categoria_id = c.id WHERE d.mes = ? ORDER BY d.vencimento ASC
        """, (mes,)).fetchall()]

@app.get("/categorias")
def get_cats():
    with get_db() as conn:
        return [dict(r) for r in conn.execute("SELECT * FROM categorias").fetchall()]

@app.post("/config/reabrir-mes")
def reabrir(mes: str, _ = Depends(verificar_admin)):
    with get_db() as conn:
        conn.execute("UPDATE configuracoes SET fechado = 0 WHERE mes = ?", (mes,))
        conn.commit()
    return {"status": "reaberto"}

@app.post("/config/renda")
def set_renda(mes: str, valor: float, _ = Depends(verificar_admin)):
    validar_bloqueio(mes)
    with get_db() as conn:
        conn.execute("INSERT INTO configuracoes (mes, renda_mensal) VALUES (?, ?) ON CONFLICT(mes) DO UPDATE SET renda_mensal=excluded.renda_mensal", (mes, valor))
        conn.commit()
    return {"status": "ok"}