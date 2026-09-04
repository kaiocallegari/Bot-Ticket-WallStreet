from __future__ import annotations

import html
import io
from datetime import datetime

import discord

import config
import database


# ---------------------------------------------------------------- embeds
def sucesso(desc: str, titulo: str = "✅ Sucesso") -> discord.Embed:
    return discord.Embed(title=titulo, description=desc, color=config.COR_SUCESSO)


def erro(desc: str, titulo: str = "❌ Erro") -> discord.Embed:
    return discord.Embed(title=titulo, description=desc, color=config.COR_ERRO)


def aviso(desc: str, titulo: str = "⚠️ Atenção") -> discord.Embed:
    return discord.Embed(title=titulo, description=desc, color=config.COR_AVISO)


def info(desc: str, titulo: str = "ℹ️ Informação") -> discord.Embed:
    return discord.Embed(title=titulo, description=desc, color=config.COR_INFO)


def painel_embed(guild: discord.Guild) -> discord.Embed:
    categorias = "\n\n".join(
        f"{m['emoji']} **{m['nome']}** — {m['descricao']}" for m in config.CATEGORIAS.values()
    )
    descricao = (
        f"{config.PAINEL_INTRO}\n\n"
        f"**▸ Categorias disponíveis:**\n\n{categorias}\n\n"
        f"{config.PAINEL_REGRAS}"
    )
    embed = discord.Embed(
        title=config.PAINEL_TITULO,
        description=descricao,
        color=config.COR_PADRAO,
        timestamp=discord.utils.utcnow(),
    )
    embed.set_footer(
        text=config.PAINEL_RODAPE, icon_url=guild.icon.url if guild.icon else None
    )
    return embed


def abertura_embed(
    membro: discord.abc.User, categoria: str, numero: int, assunto: str | None, texto: str | None
) -> discord.Embed:
    meta = config.CATEGORIAS[categoria]
    desc = (texto or config.MENSAGEM_ABERTURA_PADRAO).replace("{membro}", membro.mention)
    embed = discord.Embed(
        title=f"{meta['emoji']} Ticket de {meta['nome']} • #{numero:04d}",
        description=desc,
        color=config.COR_PADRAO,
        timestamp=discord.utils.utcnow(),
    )
    embed.add_field(name="Categoria", value=f"{meta['emoji']} {meta['nome']}", inline=True)
    embed.add_field(name="Aberto por", value=membro.mention, inline=True)
    if assunto:
        embed.add_field(name="Assunto", value=assunto[:1024], inline=False)
    embed.set_thumbnail(url=membro.display_avatar.url)
    return embed


def log_embed(
    acao: str,
    ticket: dict,
    autor: discord.abc.User,
    guild: discord.Guild,
    cor: int = config.COR_PADRAO,
    extra: str | None = None,
) -> discord.Embed:
    meta = config.CATEGORIAS.get(ticket["categoria"], {"nome": ticket["categoria"], "emoji": "🎫"})
    embed = discord.Embed(title=f"📋 {acao}", color=cor, timestamp=discord.utils.utcnow())
    embed.add_field(name="Ticket", value=f"#{ticket['numero']:04d}", inline=True)
    embed.add_field(name="Categoria", value=f"{meta['emoji']} {meta['nome']}", inline=True)
    embed.add_field(name="Responsável", value=autor.mention, inline=True)
    embed.add_field(name="Membro", value=f"<@{ticket['user_id']}>", inline=True)
    if ticket.get("claimed_by"):
        embed.add_field(name="Atendido por", value=f"<@{ticket['claimed_by']}>", inline=True)
    if extra:
        embed.add_field(name="Detalhes", value=extra[:1024], inline=False)
    embed.set_footer(text=guild.name, icon_url=guild.icon.url if guild.icon else None)
    return embed


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
    embed: discord.Embed,
    view: discord.ui.View | None = None,
    ephemeral: bool = True,
) -> None:
    """Responde sem quebrar caso a interação já tenha sido respondida/adiada."""
    kwargs = {"embed": embed, "ephemeral": ephemeral}
    if view is not None:
        kwargs["view"] = view
    if interaction.response.is_done():
        await interaction.followup.send(**kwargs)
    else:
        await interaction.response.send_message(**kwargs)


# ---------------------------------------------------------------- logs
async def enviar_log(
    guild: discord.Guild, embed: discord.Embed, arquivo: discord.File | None = None
) -> None:
    cfg = await database.get_config(guild.id)
    canal = guild.get_channel(cfg["canal_logs"] or 0)
    if not isinstance(canal, discord.TextChannel):
        return
    perms = canal.permissions_for(guild.me)
    if not perms.send_messages or (arquivo and not perms.attach_files):
        return
    try:
        await canal.send(embed=embed, file=arquivo)
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


async def gerar_transcript(canal: discord.TextChannel, ticket: dict) -> str | None:
    try:
        mensagens = [
            m async for m in canal.history(limit=config.LIMITE_TRANSCRIPT, oldest_first=True)
        ]
    except discord.HTTPException:
        return None

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
    return _HTML.format(
        numero=f"{ticket['numero']:04d}",
        categoria=html.escape(meta["nome"]),
        membro=html.escape(str(membro) if membro else f"ID {ticket['user_id']}"),
        assunto=html.escape(ticket["assunto"] or "—"),
        aberto=_fmt(aberto),
        total=len(linhas),
        mensagens="\n".join(linhas) or '<div class="fim">Nenhuma mensagem registrada.</div>',
        gerado=_fmt(discord.utils.utcnow()),
    )
