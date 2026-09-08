from __future__ import annotations

import discord

import config
import cupons
import database
import ui
import utils


# ================================================================= permissão
async def garantir_gerente(interaction: discord.Interaction) -> bool:
    membro = interaction.user
    if isinstance(membro, discord.Member) and (
        membro.guild_permissions.administrator or membro.guild_permissions.manage_guild
    ):
        return True
    await utils.responder(
        interaction, utils.erro("Você precisa da permissão **Gerenciar Servidor** para usar esta opção.")
    )
    return False


_NOMES_CAMPO = {
    "categoria_suporte": "Categoria de Suporte",
    "categoria_comprar": "Categoria de Comprar",
    "canal_logs": "Canal de Logs",
    "canal_avaliacoes": "Canal de Avaliações",
}

_OPCOES = [
    ("categoria_suporte", "🗂️ Categoria de Suporte", "Categoria onde tickets de Suporte são criados"),
    ("categoria_comprar", "🗂️ Categoria de Comprar", "Categoria onde tickets de Comprar são criados"),
    ("canal_logs", "📋 Canal de Logs", "Canal de auditoria e arquivamento dos transcripts"),
    ("canal_avaliacoes", "⭐ Canal de Avaliações", "Canal onde as avaliações são publicadas"),
    ("cargo_adicionar", "➕ Autorizar Cargo de Staff", "Autoriza um cargo nas funções administrativas"),
    ("cargo_remover", "➖ Remover Cargo de Staff", "Remove a autorização de um cargo"),
    ("cargo_dono", "👑 Cargo de Dono", "Define o cargo com acesso à criação de cupons"),
    ("limite_tickets", "🔢 Limite de Tickets por Membro", "Máximo de tickets abertos por membro"),
    ("mensagem_abertura", "💬 Mensagem de Abertura", "Edita o texto de boas-vindas do ticket"),
    ("avaliacao", "⭐ Avaliação por Estrelas", "Liga ou desliga a avaliação por estrelas"),
    ("transcript", "🗂️ Transcript", "Liga ou desliga a geração do transcript"),
    ("painel_atendimento", "💎 Publicar Painel de Atendimento", "Publica o painel de tickets em um canal"),
    ("painel_cupons", "🎫 Publicar Painel de Cupons (dono)", "Publica o painel de gerenciamento de cupons"),
    ("painel_cupons_publico", "🎟️ Publicar Painel de Cupons (público)", 'Publica o painel "Meus Cupons"'),
    ("resetar", "🗑️ Resetar Configuração", "Apaga toda a configuração do servidor"),
]

_PUBLICAR_INFO = {
    "painel_atendimento": ("Painel de Atendimento", "canal_painel", "mensagem_painel"),
    "painel_cupons": ("Painel de Gerenciamento de Cupons", "canal_cupons", "mensagem_cupons"),
    "painel_cupons_publico": ("Painel de Cupons Público", "canal_cupons_publico", "mensagem_cupons_publico"),
}


# ================================================================= painel principal
class _ConfigButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Configuração", emoji="⚙️", style=discord.ButtonStyle.primary, custom_id="admin:config"
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await garantir_gerente(interaction):
            return
        await utils.responder(interaction, _menu_view())


class PainelAdminView(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"# {config.ADMIN_PAINEL_TITULO}\n{config.ADMIN_PAINEL_INTRO}"),
                discord.ui.Separator(),
                discord.ui.ActionRow(_ConfigButton()),
                accent_colour=config.COR_PADRAO,
            )
        )


# ================================================================= menu de opções
class _ConfigSelect(discord.ui.Select):
    def __init__(self) -> None:
        opcoes = [
            discord.SelectOption(label=titulo, value=chave, description=desc[:100])
            for chave, titulo, desc in _OPCOES
        ]
        super().__init__(placeholder="Selecione o que deseja configurar", options=opcoes)

    async def callback(self, interaction: discord.Interaction) -> None:
        await _despachar(interaction, self.values[0])


def _menu_view() -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=120)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay("### ⚙️  Configuração\nSelecione o que deseja configurar."),
            discord.ui.ActionRow(_ConfigSelect()),
            accent_colour=config.COR_PADRAO,
        )
    )
    return view


async def _despachar(interaction: discord.Interaction, chave: str) -> None:
    guild = interaction.guild
    if guild is None:
        return

    if chave in ("categoria_suporte", "categoria_comprar"):
        await utils.responder(interaction, _canal_view(chave, discord.ChannelType.category))
    elif chave in ("canal_logs", "canal_avaliacoes"):
        await utils.responder(interaction, _canal_view(chave, discord.ChannelType.text))
    elif chave in ("cargo_adicionar", "cargo_remover", "cargo_dono"):
        await utils.responder(interaction, _cargo_view(chave))
    elif chave == "limite_tickets":
        await interaction.response.send_modal(LimiteModal())
    elif chave == "mensagem_abertura":
        cfg = await database.get_config(guild.id)
        await interaction.response.send_modal(ui.AberturaModal(cfg["mensagem_abertura"]))
    elif chave == "avaliacao":
        await _alternar(interaction, "avaliacao_ativa", "Avaliação por estrelas")
    elif chave == "transcript":
        await _alternar(interaction, "transcript_ativo", "Geração de transcript")
    elif chave in _PUBLICAR_INFO:
        await utils.responder(interaction, _publicar_view(chave))
    elif chave == "resetar":
        await utils.responder(interaction, _resetar_view())


# ================================================================= canais/categorias
class _CanalSelect(discord.ui.ChannelSelect):
    def __init__(self, campo: str, tipo: discord.ChannelType) -> None:
        rotulo = "a categoria" if tipo is discord.ChannelType.category else "o canal"
        super().__init__(placeholder=f"Selecione {rotulo}", channel_types=[tipo])
        self.campo = campo

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        canal = self.values[0]
        await database.set_config(guild.id, **{self.campo: canal.id})
        await utils.responder(
            interaction, utils.sucesso(f"**{_NOMES_CAMPO[self.campo]}** definido como {canal.mention}.")
        )


def _canal_view(campo: str, tipo: discord.ChannelType) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=60)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(f"Selecione o novo valor para **{_NOMES_CAMPO[campo]}**."),
            discord.ui.ActionRow(_CanalSelect(campo, tipo)),
            accent_colour=config.COR_INFO,
        )
    )
    return view


# ================================================================= cargos
class _CargoSelect(discord.ui.RoleSelect):
    def __init__(self, acao: str) -> None:
        placeholders = {
            "cargo_adicionar": "Selecione o cargo a autorizar",
            "cargo_remover": "Selecione o cargo a remover",
            "cargo_dono": "Selecione o cargo de dono",
        }
        super().__init__(placeholder=placeholders[acao])
        self.acao = acao

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        cargo = self.values[0]

        if self.acao == "cargo_adicionar":
            novo = await database.add_cargo(guild.id, cargo.id)
            view = (
                utils.sucesso(f"O cargo {cargo.mention} agora tem acesso aos tickets.")
                if novo
                else utils.aviso(f"O cargo {cargo.mention} já estava autorizado.")
            )
        elif self.acao == "cargo_remover":
            removido = await database.remove_cargo(guild.id, cargo.id)
            view = (
                utils.sucesso(f"O cargo {cargo.mention} não tem mais acesso aos tickets.")
                if removido
                else utils.aviso(f"O cargo {cargo.mention} não estava autorizado.")
            )
        else:
            await database.set_config(guild.id, cargo_dono=cargo.id)
            view = utils.sucesso(f"O cargo {cargo.mention} agora tem acesso à criação de cupons.")

        await utils.responder(interaction, view)


def _cargo_view(acao: str) -> discord.ui.LayoutView:
    textos = {
        "cargo_adicionar": "Selecione o cargo que terá acesso às funções administrativas de ticket.",
        "cargo_remover": "Selecione o cargo que terá o acesso removido.",
        "cargo_dono": "Selecione o cargo que terá acesso à criação de cupons.",
    }
    view = discord.ui.LayoutView(timeout=60)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(textos[acao]),
            discord.ui.ActionRow(_CargoSelect(acao)),
            accent_colour=config.COR_INFO,
        )
    )
    return view


# ================================================================= opções simples
class LimiteModal(discord.ui.Modal, title="Limite de tickets por membro"):
    quantidade = discord.ui.TextInput(
        label="Quantidade (1 a 10)", max_length=2, required=True, placeholder="ex: 1"
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        texto = str(self.quantidade.value).strip()
        if not texto.isdigit() or not (1 <= int(texto) <= 10):
            await utils.responder(interaction, utils.erro("Informe um número inteiro entre 1 e 10."))
            return
        valor = int(texto)
        await database.set_config(guild.id, limite_por_membro=valor)
        await utils.responder(
            interaction, utils.sucesso(f"Limite definido em **{valor}** ticket(s) por membro.")
        )


async def _alternar(interaction: discord.Interaction, campo: str, rotulo: str) -> None:
    guild = interaction.guild
    if guild is None:
        return
    cfg = await database.get_config(guild.id)
    novo_valor = 0 if cfg[campo] else 1
    await database.set_config(guild.id, **{campo: novo_valor})
    estado = "ativada" if novo_valor else "desativada"
    await utils.responder(interaction, utils.sucesso(f"**{rotulo}** {estado}."))


# ================================================================= publicar painéis
class _PublicarSelect(discord.ui.ChannelSelect):
    def __init__(self, chave: str) -> None:
        super().__init__(placeholder="Selecione o canal", channel_types=[discord.ChannelType.text])
        self.chave = chave

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        canal = guild.get_channel(self.values[0].id)
        if not isinstance(canal, discord.TextChannel):
            await utils.responder(interaction, utils.erro("Não consegui acessar esse canal."))
            return

        nome, campo_canal, campo_mensagem = _PUBLICAR_INFO[self.chave]
        if self.chave == "painel_atendimento":
            mensagem = await canal.send(view=ui.PainelView())
        elif self.chave == "painel_cupons":
            mensagem = await canal.send(view=cupons.PainelCuponsView())
        else:
            mensagem = await canal.send(view=cupons.PainelCupomPublicoView())

        await database.set_config(guild.id, **{campo_canal: canal.id, campo_mensagem: mensagem.id})

        texto = f"**{nome}** publicado em {canal.mention}."
        if self.chave == "painel_atendimento":
            cfg = await database.get_config(guild.id)
            faltando = [
                meta["nome"]
                for meta in config.CATEGORIAS.values()
                if not isinstance(guild.get_channel(cfg[meta["campo_config"]] or 0), discord.CategoryChannel)
            ]
            if faltando:
                texto += "\n\n⚠️ Configure ainda a categoria de: **" + "**, **".join(faltando) + "**."

        await utils.responder(interaction, utils.sucesso(texto))


def _publicar_view(chave: str) -> discord.ui.LayoutView:
    nome = _PUBLICAR_INFO[chave][0]
    view = discord.ui.LayoutView(timeout=60)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(f"Selecione o canal onde o **{nome}** será publicado."),
            discord.ui.ActionRow(_PublicarSelect(chave)),
            accent_colour=config.COR_INFO,
        )
    )
    return view


# ================================================================= resetar
class _ResetarConfirmarButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Confirmar", emoji="✅", style=discord.ButtonStyle.danger)

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        await database.reset_config(guild.id)
        await interaction.response.edit_message(
            view=utils.sucesso("Configuração apagada. Os tickets já registrados foram mantidos.")
        )
        if self.view:
            self.view.stop()


class _ResetarCancelarButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(label="Cancelar", emoji="✖️", style=discord.ButtonStyle.secondary)

    async def callback(self, interaction: discord.Interaction) -> None:
        await interaction.response.edit_message(view=utils.info("Operação cancelada."))
        if self.view:
            self.view.stop()


def _resetar_view() -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=60)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(
                "### ⚠️  Resetar configuração?\nIsso apaga canais, categorias, cargos e mensagens "
                "configuradas. Os tickets já registrados são mantidos. Tem certeza?"
            ),
            discord.ui.ActionRow(_ResetarConfirmarButton(), _ResetarCancelarButton()),
            accent_colour=config.COR_AVISO,
        )
    )
    return view
