from __future__ import annotations

import discord
from discord import app_commands
from discord.ext import commands

import admin
import config
import cupons
import database
import ui
import utils


class TicketBot(commands.Bot):
    def __init__(self) -> None:
        intents = discord.Intents.default()
        intents.members = True
        intents.message_content = True
        super().__init__(command_prefix="!", intents=intents, help_command=None)

    async def setup_hook(self) -> None:
        await database.init()

        self.add_view(ui.PainelView())
        self.add_view(ui.AtendimentoView())
        self.add_view(ui.AvaliacaoView())
        self.add_view(cupons.PainelCuponsView())
        self.add_view(cupons.PainelCupomPublicoView())
        self.add_view(admin.PainelAdminView())

        self.tree.add_command(grupo_config)
        self.tree.add_command(grupo_ticket)
        self.tree.add_command(grupo_cupom)

        if config.GUILD_ID:
            guild = discord.Object(id=int(config.GUILD_ID))
            self.tree.copy_global_to(guild=guild)
            await self.tree.sync(guild=guild)
        else:
            await self.tree.sync()

    async def on_ready(self) -> None:
        for guild in self.guilds:
            await database.limpar_orfaos(guild.id, {c.id for c in guild.channels})
            await database.expirar_cupons(guild.id)
        await self.change_presence(
            activity=discord.Activity(
                type=discord.ActivityType.watching, name="a Central de Atendimento"
            )
        )
        print(f"Conectado como {self.user} • {len(self.guilds)} servidor(es)")

    async def on_guild_channel_delete(self, canal: discord.abc.GuildChannel) -> None:
        ticket = await database.get_ticket(canal.id)
        if ticket and ticket["status"] == "aberto":
            await database.fechar(canal.id, self.user.id)


bot = TicketBot()


# ==================================================================== /config
grupo_config = app_commands.Group(
    name="config",
    description="Configurações da Central de Atendimento",
    guild_only=True,
    default_permissions=discord.Permissions(manage_guild=True),
)


@grupo_config.command(name="painel-admin", description="Publica o painel administrativo neste canal")
async def cfg_painel_admin(interaction: discord.Interaction) -> None:
    guild, canal = interaction.guild, interaction.channel
    if guild is None or not isinstance(canal, discord.TextChannel):
        return
    mensagem = await canal.send(view=admin.PainelAdminView())
    await database.set_config(guild.id, canal_painel_admin=canal.id, mensagem_painel_admin=mensagem.id)
    await utils.responder(interaction, utils.sucesso("Painel administrativo publicado com sucesso."))


@grupo_config.command(name="ver", description="Mostra toda a configuração atual do servidor")
async def cfg_ver(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    cfg = await database.get_config(guild.id)

    def canal(valor: int | None) -> str:
        c = guild.get_channel(valor or 0)
        return c.mention if isinstance(c, discord.TextChannel) else "`não definido`"

    def categoria(valor: int | None) -> str:
        c = guild.get_channel(valor or 0)
        return f"**{c.name}**" if isinstance(c, discord.CategoryChannel) else "`não definida`"

    cargos = await database.get_cargos(guild.id)
    lista = ", ".join(f"<@&{r}>" for r in cargos) or "`nenhum cargo autorizado`"

    categorias_txt = (
        f"**Suporte** • {categoria(cfg['categoria_suporte'])}\n"
        f"**Comprar** • {categoria(cfg['categoria_comprar'])}"
    )
    canais_txt = (
        f"**Painel administrativo** • {canal(cfg['canal_painel_admin'])}\n"
        f"**Logs** • {canal(cfg['canal_logs'])}\n"
        f"**Avaliações** • {canal(cfg['canal_avaliacoes'])}"
    )
    opcoes_txt = (
        f"**Limite por membro** • {cfg['limite_por_membro']}\n"
        f"**Tickets criados** • {cfg['contador']}\n"
        f"**Avaliação** • {'Ativada' if cfg['avaliacao_ativa'] else 'Desativada'}\n"
        f"**Transcript** • {'Ativado' if cfg['transcript_ativo'] else 'Desativado'}\n"
        f"**Cargos autorizados** • {lista}"
    )
    mensagem_txt = (cfg["mensagem_abertura"] or config.MENSAGEM_ABERTURA_PADRAO)[:1024]

    cargo_dono_txt = f"<@&{cfg['cargo_dono']}>" if cfg["cargo_dono"] else "`não definido`"
    total_cupons_ativos = len(await database.listar_cupons(guild.id, "ativo"))
    cupons_txt = (
        f"**Painel de donos** • {canal(cfg['canal_cupons'])}\n"
        f"**Painel público** • {canal(cfg['canal_cupons_publico'])}\n"
        f"**Cargo de dono** • {cargo_dono_txt}\n"
        f"**Cupons ativos** • {total_cupons_ativos}"
    )

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay("### ⚙️  Configuração da Central de Atendimento"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"**🗂️  Categorias**\n{categorias_txt}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"**📡  Canais**\n{canais_txt}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"**🎚️  Opções**\n{opcoes_txt}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"**🎫  Cupons**\n{cupons_txt}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"**💬  Mensagem de abertura**\n{mensagem_txt}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"-# {guild.name}"),
            accent_colour=config.COR_PADRAO,
        )
    )
    await utils.responder(interaction, view)


# ==================================================================== /ticket
grupo_ticket = app_commands.Group(
    name="ticket", description="Comandos de atendimento", guild_only=True
)


async def _ticket_do_canal(interaction: discord.Interaction) -> dict | None:
    if not await utils.garantir_staff(interaction):
        return None
    ticket = await database.get_ticket(interaction.channel.id)
    if not ticket or ticket["status"] != "aberto":
        await utils.responder(interaction, utils.erro("Este canal não é um ticket aberto."))
        return None
    return ticket


@grupo_ticket.command(name="fechar", description="Finaliza o ticket deste canal")
@app_commands.describe(motivo="Motivo do encerramento (opcional)")
async def ticket_fechar(interaction: discord.Interaction, motivo: str | None = None) -> None:
    ticket = await _ticket_do_canal(interaction)
    if not ticket:
        return
    await utils.responder(interaction, utils.sucesso("Finalizando o atendimento..."))
    await ui.finalizar_ticket(interaction.channel, ticket, interaction.user, motivo)


@grupo_ticket.command(name="adicionar", description="Adiciona um membro ao ticket")
@app_commands.describe(membro="Quem será adicionado")
async def ticket_adicionar(interaction: discord.Interaction, membro: discord.Member) -> None:
    ticket = await _ticket_do_canal(interaction)
    if not ticket:
        return
    try:
        await interaction.channel.set_permissions(
            membro, overwrite=ui.PERM_MEMBRO, reason=f"Adicionado por {interaction.user}"
        )
    except discord.Forbidden:
        await utils.responder(interaction, utils.erro("Não tenho permissão para alterar este canal."))
        return
    await utils.responder(interaction, utils.sucesso(f"{membro.mention} foi adicionado ao ticket."))
    await utils.enviar_log(
        interaction.guild,
        utils.log_view(
            "Membro adicionado", ticket, interaction.user, interaction.guild, config.COR_INFO,
            f"{membro.mention} (`{membro.id}`)",
        ),
    )


@grupo_ticket.command(name="remover", description="Remove um membro do ticket")
@app_commands.describe(membro="Quem será removido")
async def ticket_remover(interaction: discord.Interaction, membro: discord.Member) -> None:
    ticket = await _ticket_do_canal(interaction)
    if not ticket:
        return
    if membro.id == ticket["user_id"]:
        await utils.responder(interaction, utils.erro("Não é possível remover o autor do ticket."))
        return
    try:
        await interaction.channel.set_permissions(
            membro, overwrite=None, reason=f"Removido por {interaction.user}"
        )
    except discord.Forbidden:
        await utils.responder(interaction, utils.erro("Não tenho permissão para alterar este canal."))
        return
    await utils.responder(interaction, utils.sucesso(f"{membro.mention} foi removido do ticket."))
    await utils.enviar_log(
        interaction.guild,
        utils.log_view(
            "Membro removido", ticket, interaction.user, interaction.guild, config.COR_INFO,
            f"{membro.mention} (`{membro.id}`)",
        ),
    )


@grupo_ticket.command(name="stats", description="Total de tickets, abertos e média das avaliações")
async def ticket_stats(interaction: discord.Interaction) -> None:
    if not await utils.garantir_staff(interaction):
        return
    dados = await database.stats(interaction.guild.id)
    media = (
        f"⭐ {dados['media']:.2f}/5 ({dados['avaliacoes']} avaliações)"
        if dados["media"] is not None
        else "`sem avaliações`"
    )
    corpo = (
        f"**Total de tickets** • {dados['total']}\n"
        f"**Abertos agora** • {dados['abertos']}\n"
        f"**Média das avaliações** • {media}"
    )
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(f"### 📊  Estatísticas de atendimento\n{corpo}"),
            discord.ui.Separator(),
            discord.ui.TextDisplay(f"-# {interaction.guild.name}"),
            accent_colour=config.COR_PADRAO,
        )
    )
    await utils.responder(interaction, view)


# ==================================================================== /cupom
grupo_cupom = app_commands.Group(
    name="cupom", description="Gerenciamento de cupons de desconto", guild_only=True
)


@grupo_cupom.command(name="ver", description="Mostra os detalhes de um cupom")
@app_commands.describe(codigo="Código do cupom")
async def cupom_ver(interaction: discord.Interaction, codigo: str) -> None:
    if not await cupons.garantir_dono(interaction):
        return
    codigo = codigo.strip().upper()
    cupom = await database.get_cupom(interaction.guild.id, codigo)
    if not cupom:
        await utils.responder(interaction, utils.erro(f"Nenhum cupom encontrado com o código `{codigo}`."))
        return
    await utils.responder(interaction, cupons.detalhe_view(cupom))


@grupo_cupom.command(name="listar", description="Lista os cupons ativos")
async def cupom_listar(interaction: discord.Interaction) -> None:
    if not await cupons.garantir_dono(interaction):
        return
    await cupons.enviar_cupons_ativos(interaction)


@grupo_cupom.command(name="cancelar", description="Cancela um cupom ativo")
@app_commands.describe(codigo="Código do cupom")
async def cupom_cancelar(interaction: discord.Interaction, codigo: str) -> None:
    if not await cupons.garantir_dono(interaction):
        return
    await cupons.cancelar_e_notificar(interaction, codigo.strip().upper())


# ==================================================================== erros
@bot.tree.error
async def on_app_command_error(
    interaction: discord.Interaction, error: app_commands.AppCommandError
) -> None:
    if isinstance(error, app_commands.MissingPermissions):
        view = utils.erro("Você precisa da permissão **Gerenciar Servidor** para usar este comando.")
    elif isinstance(error, app_commands.CommandOnCooldown):
        view = utils.aviso(f"Aguarde {error.retry_after:.0f}s para usar este comando novamente.")
    elif isinstance(error, app_commands.NoPrivateMessage):
        view = utils.erro("Este comando só funciona dentro de um servidor.")
    else:
        view = utils.erro("Ocorreu um erro inesperado ao executar este comando.")
        print(f"[erro] {type(error).__name__}: {error}")
    try:
        await utils.responder(interaction, view)
    except discord.HTTPException:
        pass


if __name__ == "__main__":
    if not config.TOKEN:
        raise SystemExit("Defina DISCORD_TOKEN no arquivo .env")
    bot.run(config.TOKEN)
