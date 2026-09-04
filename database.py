from __future__ import annotations

import os
from datetime import datetime, timezone
from typing import Any

import aiosqlite

import config

SCHEMA = """
CREATE TABLE IF NOT EXISTS guild_config (
    guild_id          INTEGER PRIMARY KEY,
    categoria_suporte INTEGER,
    categoria_comprar INTEGER,
    canal_logs        INTEGER,
    canal_avaliacoes  INTEGER,
    canal_painel      INTEGER,
    mensagem_painel   INTEGER,
    mensagem_abertura TEXT,
    limite_por_membro INTEGER NOT NULL DEFAULT 1,
    avaliacao_ativa   INTEGER NOT NULL DEFAULT 1,
    transcript_ativo  INTEGER NOT NULL DEFAULT 1,
    contador          INTEGER NOT NULL DEFAULT 0
);

CREATE TABLE IF NOT EXISTS staff_roles (
    guild_id INTEGER NOT NULL,
    role_id  INTEGER NOT NULL,
    PRIMARY KEY (guild_id, role_id)
);

CREATE TABLE IF NOT EXISTS tickets (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    guild_id    INTEGER NOT NULL,
    channel_id  INTEGER NOT NULL UNIQUE,
    user_id     INTEGER NOT NULL,
    categoria   TEXT NOT NULL,
    assunto     TEXT,
    numero      INTEGER NOT NULL,
    status      TEXT NOT NULL DEFAULT 'aberto',
    claimed_by  INTEGER,
    aberto_em   TEXT NOT NULL,
    fechado_em  TEXT,
    fechado_por INTEGER
);

CREATE INDEX IF NOT EXISTS idx_tickets_user ON tickets (guild_id, user_id, status);

CREATE TABLE IF NOT EXISTS avaliacoes (
    ticket_id  INTEGER PRIMARY KEY,
    guild_id   INTEGER NOT NULL,
    user_id    INTEGER NOT NULL,
    staff_id   INTEGER,
    nota       INTEGER NOT NULL,
    comentario TEXT,
    criado_em  TEXT NOT NULL
);
"""

PADRAO: dict[str, Any] = {
    "categoria_suporte": None,
    "categoria_comprar": None,
    "canal_logs": None,
    "canal_avaliacoes": None,
    "canal_painel": None,
    "mensagem_painel": None,
    "mensagem_abertura": None,
    "limite_por_membro": 1,
    "avaliacao_ativa": 1,
    "transcript_ativo": 1,
    "contador": 0,
}


def agora() -> str:
    return datetime.now(timezone.utc).isoformat()


async def conectar() -> aiosqlite.Connection:
    db = await aiosqlite.connect(config.DB_PATH)
    db.row_factory = aiosqlite.Row
    return db


async def init() -> None:
    pasta = os.path.dirname(os.path.abspath(config.DB_PATH))
    os.makedirs(pasta, exist_ok=True)
    db = await conectar()
    try:
        await db.executescript(SCHEMA)
        await db.commit()
    finally:
        await db.close()


# ---------------------------------------------------------------- config
async def get_config(guild_id: int) -> dict[str, Any]:
    db = await conectar()
    try:
        cur = await db.execute("SELECT * FROM guild_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        if row is None:
            await db.execute("INSERT INTO guild_config (guild_id) VALUES (?)", (guild_id,))
            await db.commit()
            return {"guild_id": guild_id, **PADRAO}
        return dict(row)
    finally:
        await db.close()


async def set_config(guild_id: int, **campos: Any) -> None:
    invalidos = set(campos) - set(PADRAO)
    if invalidos:
        raise ValueError(f"Campos inválidos: {invalidos}")
    if not campos:
        return
    await get_config(guild_id)
    sets = ", ".join(f"{c} = ?" for c in campos)
    db = await conectar()
    try:
        await db.execute(
            f"UPDATE guild_config SET {sets} WHERE guild_id = ?",
            (*campos.values(), guild_id),
        )
        await db.commit()
    finally:
        await db.close()


async def reset_config(guild_id: int) -> None:
    db = await conectar()
    try:
        await db.execute("DELETE FROM guild_config WHERE guild_id = ?", (guild_id,))
        await db.execute("DELETE FROM staff_roles WHERE guild_id = ?", (guild_id,))
        await db.commit()
    finally:
        await db.close()


# ---------------------------------------------------------------- cargos
async def add_cargo(guild_id: int, role_id: int) -> bool:
    db = await conectar()
    try:
        cur = await db.execute(
            "INSERT OR IGNORE INTO staff_roles (guild_id, role_id) VALUES (?, ?)",
            (guild_id, role_id),
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def remove_cargo(guild_id: int, role_id: int) -> bool:
    db = await conectar()
    try:
        cur = await db.execute(
            "DELETE FROM staff_roles WHERE guild_id = ? AND role_id = ?", (guild_id, role_id)
        )
        await db.commit()
        return cur.rowcount > 0
    finally:
        await db.close()


async def get_cargos(guild_id: int) -> list[int]:
    db = await conectar()
    try:
        cur = await db.execute("SELECT role_id FROM staff_roles WHERE guild_id = ?", (guild_id,))
        return [r["role_id"] for r in await cur.fetchall()]
    finally:
        await db.close()


# ---------------------------------------------------------------- tickets
async def proximo_numero(guild_id: int) -> int:
    await get_config(guild_id)
    db = await conectar()
    try:
        await db.execute(
            "UPDATE guild_config SET contador = contador + 1 WHERE guild_id = ?", (guild_id,)
        )
        cur = await db.execute("SELECT contador FROM guild_config WHERE guild_id = ?", (guild_id,))
        row = await cur.fetchone()
        await db.commit()
        return int(row["contador"])
    finally:
        await db.close()


async def criar_ticket(
    guild_id: int, channel_id: int, user_id: int, categoria: str, numero: int, assunto: str | None
) -> int:
    db = await conectar()
    try:
        cur = await db.execute(
            "INSERT INTO tickets (guild_id, channel_id, user_id, categoria, assunto, numero, "
            "status, aberto_em) VALUES (?, ?, ?, ?, ?, ?, 'aberto', ?)",
            (guild_id, channel_id, user_id, categoria, assunto, numero, agora()),
        )
        await db.commit()
        return int(cur.lastrowid)
    finally:
        await db.close()


async def get_ticket(channel_id: int) -> dict[str, Any] | None:
    db = await conectar()
    try:
        cur = await db.execute("SELECT * FROM tickets WHERE channel_id = ?", (channel_id,))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def get_ticket_id(ticket_id: int) -> dict[str, Any] | None:
    db = await conectar()
    try:
        cur = await db.execute("SELECT * FROM tickets WHERE id = ?", (ticket_id,))
        row = await cur.fetchone()
        return dict(row) if row else None
    finally:
        await db.close()


async def contar_abertos(guild_id: int, user_id: int) -> int:
    db = await conectar()
    try:
        cur = await db.execute(
            "SELECT COUNT(*) AS t FROM tickets WHERE guild_id = ? AND user_id = ? "
            "AND status = 'aberto'",
            (guild_id, user_id),
        )
        return int((await cur.fetchone())["t"])
    finally:
        await db.close()


async def assumir(channel_id: int, staff_id: int) -> None:
    db = await conectar()
    try:
        await db.execute("UPDATE tickets SET claimed_by = ? WHERE channel_id = ?", (staff_id, channel_id))
        await db.commit()
    finally:
        await db.close()


async def fechar(channel_id: int, staff_id: int) -> None:
    db = await conectar()
    try:
        await db.execute(
            "UPDATE tickets SET status = 'fechado', fechado_em = ?, fechado_por = ? "
            "WHERE channel_id = ?",
            (agora(), staff_id, channel_id),
        )
        await db.commit()
    finally:
        await db.close()


async def mover(channel_id: int, categoria: str) -> None:
    db = await conectar()
    try:
        await db.execute("UPDATE tickets SET categoria = ? WHERE channel_id = ?", (categoria, channel_id))
        await db.commit()
    finally:
        await db.close()


async def limpar_orfaos(guild_id: int, canais: set[int]) -> int:
    db = await conectar()
    try:
        cur = await db.execute(
            "SELECT channel_id FROM tickets WHERE guild_id = ? AND status = 'aberto'", (guild_id,)
        )
        orfaos = [r["channel_id"] for r in await cur.fetchall() if r["channel_id"] not in canais]
        for cid in orfaos:
            await db.execute(
                "UPDATE tickets SET status = 'fechado', fechado_em = ? WHERE channel_id = ?",
                (agora(), cid),
            )
        await db.commit()
        return len(orfaos)
    finally:
        await db.close()


# ---------------------------------------------------------------- avaliações
async def salvar_avaliacao(
    ticket_id: int,
    guild_id: int,
    user_id: int,
    staff_id: int | None,
    nota: int,
    comentario: str | None,
) -> None:
    db = await conectar()
    try:
        await db.execute(
            "INSERT OR REPLACE INTO avaliacoes (ticket_id, guild_id, user_id, staff_id, nota, "
            "comentario, criado_em) VALUES (?, ?, ?, ?, ?, ?, ?)",
            (ticket_id, guild_id, user_id, staff_id, nota, comentario, agora()),
        )
        await db.commit()
    finally:
        await db.close()


async def ja_avaliou(ticket_id: int) -> bool:
    db = await conectar()
    try:
        cur = await db.execute("SELECT 1 FROM avaliacoes WHERE ticket_id = ?", (ticket_id,))
        return await cur.fetchone() is not None
    finally:
        await db.close()


async def stats(guild_id: int) -> dict[str, Any]:
    db = await conectar()
    try:
        cur = await db.execute(
            "SELECT COUNT(*) AS total, SUM(status = 'aberto') AS abertos FROM tickets "
            "WHERE guild_id = ?",
            (guild_id,),
        )
        t = await cur.fetchone()
        cur = await db.execute(
            "SELECT AVG(nota) AS media, COUNT(*) AS total FROM avaliacoes WHERE guild_id = ?",
            (guild_id,),
        )
        a = await cur.fetchone()
        return {
            "total": int(t["total"] or 0),
            "abertos": int(t["abertos"] or 0),
            "media": float(a["media"]) if a["media"] is not None else None,
            "avaliacoes": int(a["total"] or 0),
        }
    finally:
        await db.close()
