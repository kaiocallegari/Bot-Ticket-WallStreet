from __future__ import annotations

import asyncio

import discord

import config
import database
import utils

PERM_MEMBRO = discord.PermissionOverwrite(
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    attach_files=True,
    embed_links=True,
)
PERM_STAFF = discord.PermissionOverwrite(
    view_channel=True,
    send_messages=True,
    read_message_history=True,
    attach_files=True,
    embed_links=True,
    manage_messages=True,
)


# ================================================================= abertura
class TicketModal(discord.ui.Modal):
    assunto = discord.ui.TextInput(
        label="Descreva o seu atendimento",
        style=discord.TextStyle.paragraph,
        placeholder="Explique com o máximo de detalhes possíveis...",
        max_length=1000,
        required=True,
    )

    def __init__(self, categoria: str) -> None:
        meta = config.CATEGORIAS[categoria]
        super().__init__(title=f"Abrir ticket • {meta['nome']}")
        self.categoria = categoria

    async def on_submit(self, interaction: discord.Interaction) -> None:
        await abrir_ticket(interaction, self.categoria, str(self.assunto))


async def abrir_ticket(interaction: discord.Interaction, categoria: str, assunto: str) -> None:
    guild = interaction.guild
    membro = interaction.user
    if guild is None or not isinstance(membro, discord.Member):
        return

    await interaction.response.defer(ephemeral=True, thinking=True)
    cfg = await database.get_config(guild.id)
    meta = config.CATEGORIAS[categoria]

    categoria_discord = guild.get_channel(cfg[meta["campo_config"]] or 0)
    if not isinstance(categoria_discord, discord.CategoryChannel):
        await interaction.followup.send(
            embed=utils.erro(
                f"A categoria de **{meta['nome']}** ainda não foi configurada.\n"
                f"Um administrador precisa usar `/config categoria-{categoria}`."
            ),
            ephemeral=True,
        )
        return

    if not guild.me.guild_permissions.manage_channels:
        await interaction.followup.send(
            embed=utils.erro("Não tenho a permissão **Gerenciar Canais** neste servidor."),
            ephemeral=True,
        )
        return

    limite = cfg["limite_por_membro"]
    if await database.contar_abertos(guild.id, membro.id) >= limite:
        await interaction.followup.send(
            embed=utils.aviso(
                f"Você já atingiu o limite de **{limite}** ticket(s) aberto(s). "
                "Finalize o atendimento atual antes de abrir outro."
            ),
            ephemeral=True,
        )
        return

    overwrites: dict[discord.abc.Snowflake, discord.PermissionOverwrite] = {
        guild.default_role: discord.PermissionOverwrite(view_channel=False),
        guild.me: PERM_STAFF,
        membro: PERM_MEMBRO,
    }
    for role_id in await database.get_cargos(guild.id):
        cargo = guild.get_role(role_id)
        if cargo:
            overwrites[cargo] = PERM_STAFF

    numero = await database.proximo_numero(guild.id)
    try:
        canal = await guild.create_text_channel(
            name=f"{meta['prefixo']}-{numero:04d}",
            category=categoria_discord,
            overwrites=overwrites,
            topic=f"Ticket #{numero:04d} • {meta['nome']} • {membro}",
            reason=f"Ticket aberto por {membro}",
        )
    except discord.Forbidden:
        await interaction.followup.send(
            embed=utils.erro("Não consegui criar o canal. Verifique minhas permissões na categoria."),
            ephemeral=True,
        )
        return
    except discord.HTTPException:
        await interaction.followup.send(
            embed=utils.erro("Erro ao criar o canal do ticket. Tente novamente."), ephemeral=True
        )
        return

    await database.criar_ticket(guild.id, canal.id, membro.id, categoria, numero, assunto)

    embed = utils.abertura_embed(membro, categoria, numero, assunto, cfg["mensagem_abertura"])
    await canal.send(content=membro.mention, embed=embed)
    await canal.send(
        embed=discord.Embed(
            description="**Opções exclusivas para o uso dos responsáveis pelo atendimento!**",
            color=config.COR_PADRAO,
        ),
        view=AtendimentoView(),
    )

    ticket = await database.get_ticket(canal.id)
    if ticket:
        await utils.enviar_log(
            guild, utils.log_embed("Ticket aberto", ticket, membro, guild, config.COR_SUCESSO, assunto)
        )

    await interaction.followup.send(
        embed=utils.sucesso(f"Seu ticket foi aberto em {canal.mention}."), ephemeral=True
    )


ESTILOS = {
    "primary": discord.ButtonStyle.primary,
    "success": discord.ButtonStyle.success,
    "secondary": discord.ButtonStyle.secondary,
    "danger": discord.ButtonStyle.danger,
}


class CategoriaButton(discord.ui.Button):
    def __init__(self, chave: str, meta: dict) -> None:
        super().__init__(
            label=meta["nome"],
            emoji=meta["emoji"],
            style=ESTILOS.get(meta.get("estilo", "secondary"), discord.ButtonStyle.secondary),
            custom_id=f"painel:{chave}",
        )
        self.chave = chave

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.send_modal(TicketModal(self.chave))


class PainelView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        for chave, meta in config.CATEGORIAS.items():
            self.add_item(CategoriaButton(chave, meta))


# ================================================================= finalização
async def finalizar_ticket(
    canal: discord.TextChannel, ticket: dict, staff: discord.Member, motivo: str | None = None
) -> None:
    guild = canal.guild
    cfg = await database.get_config(guild.id)
    await database.fechar(canal.id, staff.id)
    ticket = await database.get_ticket(canal.id) or ticket

    pagina = await utils.gerar_transcript(canal, ticket) if cfg["transcript_ativo"] else None

    await utils.enviar_log(
        guild,
        utils.log_embed("Ticket finalizado", ticket, staff, guild, config.COR_ERRO, motivo),
        utils.arquivo_transcript(pagina, ticket["numero"]) if pagina else None,
    )

    membro = guild.get_member(ticket["user_id"])
    if membro:
        await _enviar_dm(membro, ticket, guild, cfg, pagina)

    await canal.send(
        embed=utils.aviso(
            f"Ticket finalizado por {staff.mention}.\n"
            f"Este canal será apagado em **{config.DELAY_DELETAR} segundos**."
        )
    )
    await asyncio.sleep(config.DELAY_DELETAR)
    try:
        await canal.delete(reason=f"Ticket finalizado por {staff}")
    except discord.HTTPException:
        pass


async def _enviar_dm(
    membro: discord.Member, ticket: dict, guild: discord.Guild, cfg: dict, pagina: str | None
) -> None:
    meta = config.CATEGORIAS.get(ticket["categoria"], {"nome": ticket["categoria"], "emoji": "🎫"})
    embed = discord.Embed(
        title="🎫 Atendimento finalizado",
        description=(
            f"Seu ticket **#{ticket['numero']:04d}** ({meta['emoji']} {meta['nome']}) "
            f"no servidor **{guild.name}** foi finalizado."
        ),
        color=config.COR_PADRAO,
        timestamp=discord.utils.utcnow(),
    )
    try:
        await membro.send(
            embed=embed,
            file=utils.arquivo_transcript(pagina, ticket["numero"]) if pagina else None,
        )
    except discord.HTTPException:
        return

    if not cfg["avaliacao_ativa"]:
        return

    aval = discord.Embed(
        title="⭐ Avalie o atendimento",
        description="Selecione abaixo quantas estrelas a equipe merece por este atendimento.",
        color=config.COR_AVISO,
    )
    aval.set_footer(text=f"ticket:{ticket['id']}")
    try:
        await membro.send(embed=aval, view=AvaliacaoView())
    except discord.HTTPException:
        pass


class ConfirmarView(discord.ui.View):
    def __init__(self, ticket: dict) -> None:
        super().__init__(timeout=60)
        self.ticket = ticket

    @discord.ui.button(label="Confirmar", emoji="✅", style=discord.ButtonStyle.success)
    async def confirmar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        canal = interaction.channel
        if not isinstance(canal, discord.TextChannel) or not isinstance(
            interaction.user, discord.Member
        ):
            return
        await interaction.response.edit_message(
            embed=utils.sucesso("Finalizando o atendimento..."), view=None
        )
        self.stop()
        await finalizar_ticket(canal, self.ticket, interaction.user)

    @discord.ui.button(label="Cancelar", emoji="✖️", style=discord.ButtonStyle.secondary)
    async def cancelar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        await interaction.response.edit_message(
            embed=utils.info("Finalização cancelada."), view=None
        )
        self.stop()


# ================================================================= painel do staff
class NomeModal(discord.ui.Modal, title="Trocar nome do canal"):
    nome = discord.ui.TextInput(
        label="Novo nome", max_length=90, placeholder="ex: suporte-joao", required=True
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        canal = interaction.channel
        if not isinstance(canal, discord.TextChannel):
            return
        try:
            await canal.edit(name=str(self.nome), reason=f"Renomeado por {interaction.user}")
        except discord.Forbidden:
            await utils.responder(interaction, utils.erro("Não tenho permissão para renomear este canal."))
            return
        except discord.HTTPException:
            await utils.responder(interaction, utils.erro("Não consegui renomear o canal (limite do Discord)."))
            return
        await utils.responder(interaction, utils.sucesso(f"Canal renomeado para **{canal.name}**."))


class MembroSelect(discord.ui.UserSelect):
    def __init__(self, adicionar: bool, ticket: dict) -> None:
        super().__init__(
            placeholder="Selecione o membro" if adicionar else "Selecione quem será removido",
            min_values=1,
            max_values=1,
        )
        self.adicionar = adicionar
        self.ticket = ticket

    async def callback(self, interaction: discord.Interaction) -> None:
        canal = interaction.channel
        alvo = self.values[0]
        if not isinstance(canal, discord.TextChannel) or not isinstance(alvo, discord.Member):
            await utils.responder(interaction, utils.erro("Membro inválido."))
            return

        if not self.adicionar and alvo.id == self.ticket["user_id"]:
            await utils.responder(
                interaction, utils.erro("Não é possível remover o autor do ticket.")
            )
            return

        try:
            if self.adicionar:
                await canal.set_permissions(alvo, overwrite=PERM_MEMBRO, reason=f"Adicionado por {interaction.user}")
            else:
                await canal.set_permissions(alvo, overwrite=None, reason=f"Removido por {interaction.user}")
        except discord.Forbidden:
            await utils.responder(interaction, utils.erro("Não tenho permissão para alterar este canal."))
            return

        acao = "adicionado ao" if self.adicionar else "removido do"
        await utils.responder(interaction, utils.sucesso(f"{alvo.mention} foi {acao} ticket."))
        await canal.send(
            embed=utils.info(
                f"{alvo.mention} foi {acao} atendimento por {interaction.user.mention}.",
                titulo="👥 Participantes",
            )
        )
        if interaction.guild:
            await utils.enviar_log(
                interaction.guild,
                utils.log_embed(
                    "Membro adicionado" if self.adicionar else "Membro removido",
                    self.ticket,
                    interaction.user,
                    interaction.guild,
                    config.COR_INFO,
                    f"{alvo.mention} (`{alvo.id}`)",
                ),
            )


class MembroView(discord.ui.View):
    def __init__(self, adicionar: bool, ticket: dict) -> None:
        super().__init__(timeout=60)
        self.add_item(MembroSelect(adicionar, ticket))


class MoverSelect(discord.ui.Select):
    def __init__(self, ticket: dict) -> None:
        opcoes = [
            discord.SelectOption(
                label=meta["nome"], value=chave, emoji=meta["emoji"], description=meta["descricao"][:100]
            )
            for chave, meta in config.CATEGORIAS.items()
            if chave != ticket["categoria"]
        ]
        super().__init__(placeholder="Selecione a nova categoria", options=opcoes)
        self.ticket = ticket

    async def callback(self, interaction: discord.Interaction) -> None:
        canal, guild = interaction.channel, interaction.guild
        if not isinstance(canal, discord.TextChannel) or guild is None:
            return
        destino = self.values[0]
        meta = config.CATEGORIAS[destino]
        cfg = await database.get_config(guild.id)
        categoria_discord = guild.get_channel(cfg[meta["campo_config"]] or 0)
        if not isinstance(categoria_discord, discord.CategoryChannel):
            await utils.responder(
                interaction, utils.erro(f"A categoria de **{meta['nome']}** não está configurada.")
            )
            return

        try:
            await canal.edit(
                category=categoria_discord,
                name=f"{meta['prefixo']}-{self.ticket['numero']:04d}",
                reason=f"Movido por {interaction.user}",
            )
        except discord.Forbidden:
            await utils.responder(interaction, utils.erro("Não tenho permissão para mover este canal."))
            return
        except discord.HTTPException:
            await utils.responder(interaction, utils.erro("Não consegui mover o canal."))
            return

        await database.mover(canal.id, destino)
        await utils.responder(
            interaction, utils.sucesso(f"Ticket movido para **{meta['nome']}**.")
        )
        await canal.send(
            embed=utils.info(
                f"Ticket movido para {meta['emoji']} **{meta['nome']}** por {interaction.user.mention}.",
                titulo="🔁 Ticket movido",
            )
        )
        await utils.enviar_log(
            guild,
            utils.log_embed(
                "Ticket movido", self.ticket, interaction.user, guild, config.COR_INFO, meta["nome"]
            ),
        )


class MoverView(discord.ui.View):
    def __init__(self, ticket: dict) -> None:
        super().__init__(timeout=60)
        self.add_item(MoverSelect(ticket))


async def _ticket_valido(interaction: discord.Interaction) -> dict | None:
    """Confere staff + ticket aberto. Responde e devolve None quando inválido."""
    if not await utils.garantir_staff(interaction):
        return None
    canal = interaction.channel
    if not isinstance(canal, discord.TextChannel):
        return None
    ticket = await database.get_ticket(canal.id)
    if not ticket or ticket["status"] != "aberto":
        await utils.responder(interaction, utils.erro("Este canal não é um ticket aberto."))
        return None
    return ticket


class AtendimentoView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)

    @discord.ui.button(
        label="Chamar Membro", emoji="🔔", style=discord.ButtonStyle.secondary,
        custom_id="atd:chamar", row=0,
    )
    async def chamar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        ticket = await _ticket_valido(interaction)
        if not ticket:
            return
        await interaction.response.send_message(
            content=f"<@{ticket['user_id']}>",
            embed=utils.aviso(
                f"{interaction.user.mention} está chamando você neste atendimento.",
                titulo="🔔 Chamado da equipe",
            ),
            allowed_mentions=discord.AllowedMentions(users=True),
        )

    @discord.ui.button(
        label="Adicionar Membro", emoji="➕", style=discord.ButtonStyle.secondary,
        custom_id="atd:adicionar", row=0,
    )
    async def adicionar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        ticket = await _ticket_valido(interaction)
        if not ticket:
            return
        await interaction.response.send_message(
            embed=utils.info("Selecione quem deve ser adicionado ao ticket."),
            view=MembroView(True, ticket),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Remover Membro", emoji="❌", style=discord.ButtonStyle.secondary,
        custom_id="atd:remover", row=0,
    )
    async def remover(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        ticket = await _ticket_valido(interaction)
        if not ticket:
            return
        await interaction.response.send_message(
            embed=utils.info("Selecione quem deve ser removido do ticket."),
            view=MembroView(False, ticket),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Mover Ticket", emoji="🔁", style=discord.ButtonStyle.secondary,
        custom_id="atd:mover", row=0,
    )
    async def mover(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        ticket = await _ticket_valido(interaction)
        if not ticket:
            return
        await interaction.response.send_message(
            embed=utils.info("Selecione a categoria de destino."),
            view=MoverView(ticket),
            ephemeral=True,
        )

    @discord.ui.button(
        label="Trocar Nome do Canal", emoji="📝", style=discord.ButtonStyle.secondary,
        custom_id="atd:nome", row=1,
    )
    async def renomear(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        if await _ticket_valido(interaction):
            await interaction.response.send_modal(NomeModal())

    @discord.ui.button(
        label="Assumir Atendimento", emoji="🤔", style=discord.ButtonStyle.secondary,
        custom_id="atd:assumir", row=1,
    )
    async def assumir(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        ticket = await _ticket_valido(interaction)
        if not ticket:
            return
        if ticket["claimed_by"]:
            await utils.responder(
                interaction,
                utils.aviso(f"Este ticket já está sendo atendido por <@{ticket['claimed_by']}>."),
            )
            return
        await database.assumir(interaction.channel.id, interaction.user.id)
        await interaction.response.send_message(
            embed=utils.sucesso(
                f"{interaction.user.mention} assumiu este atendimento.", titulo="🤔 Atendimento assumido"
            )
        )
        if interaction.guild:
            await utils.enviar_log(
                interaction.guild,
                utils.log_embed(
                    "Ticket assumido", ticket, interaction.user, interaction.guild, config.COR_INFO
                ),
            )

    @discord.ui.button(
        label="Finalizar Ticket", emoji="✅", style=discord.ButtonStyle.success,
        custom_id="atd:finalizar", row=1,
    )
    async def finalizar(self, interaction: discord.Interaction, _: discord.ui.Button) -> None:
        ticket = await _ticket_valido(interaction)
        if not ticket:
            return
        await interaction.response.send_message(
            embed=utils.aviso("Tem certeza que deseja finalizar este atendimento?"),
            view=ConfirmarView(ticket),
            ephemeral=True,
        )


# ================================================================= avaliação
class ComentarioModal(discord.ui.Modal, title="Avaliar atendimento"):
    comentario = discord.ui.TextInput(
        label="Comentário (opcional)",
        style=discord.TextStyle.paragraph,
        max_length=500,
        required=False,
    )

    def __init__(self, ticket_id: int, nota: int, mensagem: discord.Message) -> None:
        super().__init__()
        self.ticket_id = ticket_id
        self.nota = nota
        self.mensagem = mensagem

    async def on_submit(self, interaction: discord.Interaction) -> None:
        ticket = await database.get_ticket_id(self.ticket_id)
        if not ticket:
            await utils.responder(interaction, utils.erro("Ticket não encontrado."))
            return

        texto = str(self.comentario).strip() or None
        await database.salvar_avaliacao(
            ticket["id"], ticket["guild_id"], ticket["user_id"], ticket["claimed_by"], self.nota, texto
        )

        estrelas = "⭐" * self.nota + "▫️" * (5 - self.nota)
        confirmacao = utils.sucesso(
            f"Obrigado por avaliar!\n\n**Nota:** {estrelas} ({self.nota}/5)",
            titulo="⭐ Avaliação registrada",
        )
        try:
            await interaction.response.edit_message(embed=confirmacao, view=None)
        except discord.HTTPException:
            await self.mensagem.edit(embed=confirmacao, view=None)
            await utils.responder(interaction, confirmacao)

        guild = interaction.client.get_guild(ticket["guild_id"])
        if guild is None:
            return
        cfg = await database.get_config(guild.id)
        canal = guild.get_channel(cfg["canal_avaliacoes"] or 0)
        if not isinstance(canal, discord.TextChannel):
            return

        embed = discord.Embed(
            title="⭐ Nova avaliação de atendimento",
            color=config.COR_AVISO,
            timestamp=discord.utils.utcnow(),
        )
        embed.add_field(name="Ticket", value=f"#{ticket['numero']:04d}", inline=True)
        embed.add_field(name="Nota", value=f"{estrelas} ({self.nota}/5)", inline=True)
        embed.add_field(name="Membro", value=f"<@{ticket['user_id']}>", inline=True)
        embed.add_field(
            name="Atendido por",
            value=f"<@{ticket['claimed_by']}>" if ticket["claimed_by"] else "Ninguém assumiu",
            inline=True,
        )
        if texto:
            embed.add_field(name="Comentário", value=texto[:1024], inline=False)
        try:
            await canal.send(embed=embed)
        except discord.HTTPException:
            pass


class AvaliacaoSelect(discord.ui.Select):
    def __init__(self) -> None:
        super().__init__(
            placeholder="Escolha de 1 a 5 estrelas",
            custom_id="avaliacao:nota",
            options=[
                discord.SelectOption(label=f"{n} estrela{'s' if n > 1 else ''}", value=str(n), emoji="⭐")
                for n in range(1, 6)
            ],
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        mensagem = interaction.message
        rodape = mensagem.embeds[0].footer.text if mensagem and mensagem.embeds else None
        if not rodape or not rodape.startswith("ticket:"):
            await utils.responder(interaction, utils.erro("Não consegui identificar o ticket."))
            return
        ticket_id = int(rodape.split(":", 1)[1])

        if await database.ja_avaliou(ticket_id):
            await utils.responder(interaction, utils.aviso("Este atendimento já foi avaliado."))
            return

        await interaction.response.send_modal(
            ComentarioModal(ticket_id, int(self.values[0]), mensagem)
        )


class AvaliacaoView(discord.ui.View):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(AvaliacaoSelect())


# ================================================================= config
class AberturaModal(discord.ui.Modal, title="Mensagem de abertura"):
    def __init__(self, atual: str | None) -> None:
        super().__init__()
        self.texto = discord.ui.TextInput(
            label="Texto do ticket",
            style=discord.TextStyle.paragraph,
            default=atual or config.MENSAGEM_ABERTURA_PADRAO,
            max_length=2000,
            required=True,
            placeholder="Use {membro} para mencionar quem abriu o ticket.",
        )
        self.add_item(self.texto)

    async def on_submit(self, interaction: discord.Interaction) -> None:
        if interaction.guild is None:
            return
        await database.set_config(interaction.guild.id, mensagem_abertura=str(self.texto))
        await utils.responder(interaction, utils.sucesso("Mensagem de abertura atualizada."))
