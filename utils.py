from __future__ import annotations

import html
import io
import re
import unicodedata
from datetime import datetime

import discord

import config
import database


# ---------------------------------------------------------------- texto
def slug(texto: str, maximo: int = 20) -> str:
    """Normaliza um nome para uso em nome de canal (sem acento, minúsculo, com hífens)."""
    texto = unicodedata.normalize("NFKD", texto).encode("ascii", "ignore").decode()
    texto = re.sub(r"[^a-zA-Z0-9]+", "-", texto).strip("-").lower()
    return texto[:maximo].strip("-") or "staff"


# ---------------------------------------------------------------- avisos (Components V2)
def _notice(titulo: str, desc: str, cor: int) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(f"### {titulo}\n{desc}"),
            accent_colour=cor,
        )
    )
    return view


def sucesso(desc: str, titulo: str = "✅  Sucesso") -> discord.ui.LayoutView:
    return _notice(titulo, desc, config.COR_SUCESSO)


def erro(desc: str, titulo: str = "❌  Erro") -> discord.ui.LayoutView:
    return _notice(titulo, desc, config.COR_ERRO)


def aviso(desc: str, titulo: str = "⚠️  Atenção") -> discord.ui.LayoutView:
    return _notice(titulo, desc, config.COR_AVISO)


def info(desc: str, titulo: str = "ℹ️  Informação") -> discord.ui.LayoutView:
    return _notice(titulo, desc, config.COR_INFO)


def abertura_view(
    membro: discord.abc.User, categoria: str, numero: int, assunto: str | None, texto: str | None
) -> discord.ui.LayoutView:
    meta = config.CATEGORIAS[categoria]
    desc = (texto or config.MENSAGEM_ABERTURA_PADRAO).replace("{membro}", membro.mention)
    corpo = f"### {meta['emoji']}  Ticket de {meta['nome']} • #{numero:04d}\n{desc}"
    linhas = [f"**Categoria** • {meta['emoji']} {meta['nome']}", f"**Aberto por** • {membro.mention}"]
    if assunto:
        linhas.append(f"**Assunto** • {assunto[:1024]}")

    container = discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(corpo),
            accessory=discord.ui.Thumbnail(membro.display_avatar.url),
        ),
        discord.ui.Separator(),
        discord.ui.TextDisplay("\n".join(linhas)),
        accent_colour=config.COR_PADRAO,
    )
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def log_view(
    acao: str,
    ticket: dict,
    autor: discord.abc.User,
    guild: discord.Guild,
    cor: int = config.COR_PADRAO,
    extra: str | None = None,
) -> discord.ui.LayoutView:
    meta = config.CATEGORIAS.get(ticket["categoria"], {"nome": ticket["categoria"], "emoji": "🎫"})
    linhas = [
        f"**Ticket** • #{ticket['numero']:04d}",
        f"**Categoria** • {meta['emoji']} {meta['nome']}",
        f"**Responsável** • {autor.mention}",
        f"**Membro** • <@{ticket['user_id']}>",
    ]
    if ticket.get("claimed_by"):
        linhas.append(f"**Atendido por** • <@{ticket['claimed_by']}>")
    corpo = "\n".join(linhas)
    if extra:
        corpo += f"\n\n**Detalhes**\n{extra[:1024]}"

    agora = discord.utils.format_dt(discord.utils.utcnow(), style="R")
    container = discord.ui.Container(
        discord.ui.TextDisplay(f"### 📋  {acao}\n{corpo}"),
        discord.ui.Separator(),
        discord.ui.TextDisplay(f"-# {guild.name} • {agora}"),
        accent_colour=cor,
    )
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


# ---------------------------------------------------------------- permissões
async def eh_staff(membro: discord.Member) -> bool:
    if membro.guild_permissions.administrator or membro.guild_permissions.manage_guild:
        return True
    cargos = set(await database.get_cargos(membro.guild.id))
    return bool(cargos) and any(r.id in cargos for r in membro.roles)


async def garantir_staff(interaction: discord.Interaction) -> bool:
    membro = interaction.user
    if isinstance(membro, discord.Member) and await eh_staff(membro):
        return True
    await responder(interaction, erro("Você não tem permissão para usar esta opção."))
    return False


async def responder(
    interaction: discord.Interaction,
    view: discord.ui.LayoutView,
    ephemeral: bool = True,
) -> None:
    """Responde sem quebrar caso a interação já tenha sido respondida/adiada."""
    if interaction.response.is_done():
        await interaction.followup.send(view=view, ephemeral=ephemeral)
    else:
        await interaction.response.send_message(view=view, ephemeral=ephemeral)


# ---------------------------------------------------------------- logs
async def enviar_log(
    guild: discord.Guild, view: discord.ui.LayoutView, arquivo: discord.File | None = None
) -> None:
    cfg = await database.get_config(guild.id)
    canal = guild.get_channel(cfg["canal_logs"] or 0)
    if not isinstance(canal, discord.TextChannel):
        return
    perms = canal.permissions_for(guild.me)
    if not perms.send_messages or (arquivo and not perms.attach_files):
        return
    try:
        await canal.send(view=view, file=arquivo)
    except discord.HTTPException:
        pass


# ---------------------------------------------------------------- transcript
_HTML = """<!DOCTYPE html>
<html lang="pt-BR"><head><meta charset="utf-8">
<title>Ticket #{numero}</title>
<style>
:root{{color-scheme:dark}}
body{{margin:0;padding:32px;background:#1e1f22;color:#dbdee1;
font-family:"gg sans",-apple-system,Segoe UI,Roboto,sans-serif;font-size:15px}}
.box{{max-width:860px;margin:0 auto}}
.head{{background:#2b2d31;border-radius:8px;padding:20px 24px;margin-bottom:24px}}
.head h1{{margin:0 0 12px;font-size:20px;color:#fff}}
.head p{{margin:4px 0;color:#b5bac1;font-size:14px}}
.msg{{display:flex;gap:14px;padding:10px 8px;border-radius:6px}}
.msg:hover{{background:#2b2d31}}
.msg img{{width:40px;height:40px;border-radius:50%;flex:none}}
.autor{{font-weight:600;color:#fff}}
.hora{{color:#949ba4;font-size:12px;margin-left:8px}}
.txt{{white-space:pre-wrap;word-wrap:break-word;margin-top:2px}}
.anexo{{color:#00a8fc;font-size:13px;display:block}}
.emb{{border-left:4px solid #5865f2;background:#2b2d31;padding:8px 12px;
border-radius:4px;margin-top:6px;font-size:14px}}
.fim{{text-align:center;color:#949ba4;font-size:12px;margin-top:28px}}
</style></head><body><div class="box">
<div class="head"><h1>💎 Ticket #{numero} — {categoria}</h1>
<p><b>Membro:</b> {membro}</p><p><b>Assunto:</b> {assunto}</p>
<p><b>Aberto em:</b> {aberto}</p><p><b>Mensagens:</b> {total}</p></div>
{mensagens}
<div class="fim">Transcript gerado em {gerado}</div>
</div></body></html>"""


def _fmt(dt: datetime) -> str:
    return dt.strftime("%d/%m/%Y %H:%M")


def arquivo_transcript(pagina: str, numero: int) -> discord.File:
    """Cria um discord.File novo a partir do HTML (um File só pode ser enviado uma vez)."""
    return discord.File(io.BytesIO(pagina.encode("utf-8")), filename=f"ticket-{numero:04d}.html")


def transcript_view(
    ticket: dict,
    canal_nome: str,
    staff: discord.abc.User,
    membro: discord.abc.User | None,
    total_mensagens: int,
) -> discord.ui.LayoutView:
    meta = config.CATEGORIAS.get(ticket["categoria"], {"nome": ticket["categoria"], "emoji": "🎫"})
    aberto_por = str(membro) if membro else f"ID {ticket['user_id']}"

    linhas = [
        f"**Ticket** • {meta['emoji']} #{ticket['numero']:04d} - {canal_nome}",
        f"**Mensagens** • {total_mensagens}",
        f"**Aberto por** • {aberto_por}\nID: {ticket['user_id']}",
        f"**Fechado por** • {staff}",
    ]

    agora = discord.utils.format_dt(discord.utils.utcnow(), style="f")
    container = discord.ui.Container(
        discord.ui.Section(
            discord.ui.TextDisplay(
                "### 🗂️  Histórico de ticket gerado\n"
                "O histórico desta conversa foi salvo e pode ser acessado pelo arquivo abaixo."
            ),
            accessory=discord.ui.Thumbnail(staff.display_avatar.url),
        ),
        discord.ui.Separator(),
        discord.ui.TextDisplay("\n".join(linhas)),
        discord.ui.Separator(),
        discord.ui.TextDisplay(f"-# {agora}"),
        accent_colour=config.COR_INFO,
    )
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


async def gerar_transcript(canal: discord.TextChannel, ticket: dict) -> tuple[str | None, int]:
    try:
        mensagens = [
            m async for m in canal.history(limit=config.LIMITE_TRANSCRIPT, oldest_first=True)
        ]
    except discord.HTTPException:
        return None, 0

    linhas = []
    for m in mensagens:
        conteudo = html.escape(m.content or "")
        anexos = "".join(
            f'<a class="anexo" href="{html.escape(a.url)}">📎 {html.escape(a.filename)}</a>'
            for a in m.attachments
        )
        embeds = ""
        for e in m.embeds:
            titulo = html.escape(e.title or "")
            desc = html.escape(e.description or "")
            if titulo or desc:
                embeds += f'<div class="emb"><b>{titulo}</b><br>{desc}</div>'
        if not (conteudo or anexos or embeds):
            continue
        linhas.append(
            f'<div class="msg"><img src="{m.author.display_avatar.url}" alt="">'
            f'<div><span class="autor">{html.escape(m.author.display_name)}</span>'
            f'<span class="hora">{_fmt(m.created_at)}</span>'
            f'<div class="txt">{conteudo}</div>{anexos}{embeds}</div></div>'
        )

    meta = config.CATEGORIAS.get(ticket["categoria"], {"nome": ticket["categoria"]})
    membro = canal.guild.get_member(ticket["user_id"])
    aberto = datetime.fromisoformat(ticket["aberto_em"])
    pagina = _HTML.format(
        numero=f"{ticket['numero']:04d}",
        categoria=html.escape(meta["nome"]),
        membro=html.escape(str(membro) if membro else f"ID {ticket['user_id']}"),
        assunto=html.escape(ticket["assunto"] or "—"),
        aberto=_fmt(aberto),
        total=len(mensagens),
        mensagens="\n".join(linhas) or '<div class="fim">Nenhuma mensagem registrada.</div>',
        gerado=_fmt(discord.utils.utcnow()),
    )
    return pagina, len(mensagens)
