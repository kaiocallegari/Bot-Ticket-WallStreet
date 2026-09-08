from __future__ import annotations

import re
from datetime import datetime, timezone

import discord

import config
import database
import utils

_CODIGO_RE = re.compile(rf"^[A-Z0-9-]{{{config.CODIGO_MIN},{config.CODIGO_MAX}}}$")


# ================================================================= permissão de dono
async def eh_dono(membro: discord.Member) -> bool:
    if membro.guild.owner_id == membro.id:
        return True
    cfg = await database.get_config(membro.guild.id)
    cargo_dono = cfg["cargo_dono"]
    return bool(cargo_dono) and any(r.id == cargo_dono for r in membro.roles)


async def garantir_dono(interaction: discord.Interaction) -> bool:
    membro = interaction.user
    if isinstance(membro, discord.Member) and await eh_dono(membro):
        return True
    await utils.responder(interaction, utils.erro("Apenas os donos da loja podem usar esta opção."))
    return False


# ================================================================= helpers de exibição
def _nome_titular(guild: discord.Guild, user_id: int) -> str:
    membro = guild.get_member(user_id)
    return str(membro) if membro else f"ID {user_id}"


def _formatar_linha_cupom(cupom: dict) -> str:
    validade = discord.utils.format_dt(datetime.fromisoformat(cupom["expira_em"]), style="R")
    return f"`{cupom['codigo']}` • {cupom['desconto']}% • <@{cupom['titular_id']}> • vence {validade}"


def _log_view(titulo: str, linhas: list[str], guild: discord.Guild, cor: int) -> discord.ui.LayoutView:
    corpo = "\n".join(linhas)
    agora = discord.utils.format_dt(discord.utils.utcnow(), style="R")
    container = discord.ui.Container(
        discord.ui.TextDisplay(f"### {titulo}\n{corpo}"),
        discord.ui.Separator(),
        discord.ui.TextDisplay(f"-# {guild.name} • {agora}"),
        accent_colour=cor,
    )
    view = discord.ui.LayoutView(timeout=None)
    view.add_item(container)
    return view


def detalhe_view(cupom: dict) -> discord.ui.LayoutView:
    status_emojis = {"ativo": "🟢", "usado": "🔵", "expirado": "⏰", "cancelado": "🔴"}
    emoji = status_emojis.get(cupom["status"], "🎫")
    criado = discord.utils.format_dt(datetime.fromisoformat(cupom["criado_em"]), style="f")
    expira = discord.utils.format_dt(datetime.fromisoformat(cupom["expira_em"]), style="f")

    linhas = [
        f"**Código** • `{cupom['codigo']}`",
        f"**Desconto** • {cupom['desconto']}%",
        f"**Titular** • <@{cupom['titular_id']}>",
        f"**Criado por** • <@{cupom['criado_por']}>",
        f"**Criado em** • {criado}",
        f"**Validade** • {expira}",
        f"**Status** • {emoji} {cupom['status'].capitalize()}",
    ]
    if cupom["status"] == "usado":
        usado_em = discord.utils.format_dt(datetime.fromisoformat(cupom["usado_em"]), style="f")
        linhas.append(f"**Usado em** • {usado_em}")
        linhas.append(f"**Usado por** • <@{cupom['usado_por']}>")
        if cupom["ticket_id"]:
            linhas.append(f"**Ticket** • #{cupom['ticket_id']}")
        if cupom["valor_original"] is not None:
            linhas.append(f"**Valor original** • {utils.formatar_real(cupom['valor_original'])}")
        if cupom["valor_final"] is not None:
            linhas.append(f"**Valor final** • {utils.formatar_real(cupom['valor_final'])}")

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(f"### 🎫  Cupom `{cupom['codigo']}`\n" + "\n".join(linhas)),
            accent_colour=config.COR_INFO,
        )
    )
    return view


async def enviar_cupons_ativos(interaction: discord.Interaction) -> None:
    guild = interaction.guild
    if guild is None:
        return
    cupons = await database.listar_cupons(guild.id, "ativo")
    if not cupons:
        await utils.responder(interaction, utils.info("Não há cupons ativos no momento."))
        return

    total = len(cupons)
    linhas = [_formatar_linha_cupom(c) for c in cupons[:20]]
    corpo = "\n".join(linhas)
    if total > 20:
        corpo += f"\n\n-# Mostrando os 20 mais recentes de {total} cupons ativos."

    view = discord.ui.LayoutView(timeout=None)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay(f"### 📋  Cupons ativos\n{corpo}"),
            accent_colour=config.COR_INFO,
        )
    )
    await utils.responder(interaction, view)


async def cancelar_e_notificar(interaction: discord.Interaction, codigo: str) -> None:
    guild = interaction.guild
    if guild is None:
        return
    cupom = await database.get_cupom(guild.id, codigo)
    if not cupom:
        await utils.responder(interaction, utils.erro(f"Nenhum cupom encontrado com o código `{codigo}`."))
        return
    if cupom["status"] != "ativo":
        await utils.responder(interaction, utils.erro("Este cupom não está ativo e não pode ser cancelado."))
        return

    cancelado = await database.cancelar_cupom(guild.id, codigo)
    if not cancelado:
        await utils.responder(interaction, utils.erro("Este cupom não pôde ser cancelado."))
        return

    await utils.responder(interaction, utils.sucesso(f"Cupom `{codigo}` cancelado com sucesso."))
    await utils.enviar_log(
        guild,
        _log_view(
            "🗑️  Cupom cancelado",
            [f"**Código** • `{codigo}`", f"**Cancelado por** • {interaction.user.mention}"],
            guild,
            config.COR_ERRO,
        ),
    )


# ================================================================= painel de donos
class _CriarCupomButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Criar Cupom", emoji="🎫", style=discord.ButtonStyle.danger, custom_id="cupom:criar"
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await garantir_dono(interaction):
            return
        await interaction.response.send_modal(CriarCupomModal())


class _CuponsAtivosButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Cupons Ativos", emoji="📋", style=discord.ButtonStyle.secondary, custom_id="cupom:ativos"
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await garantir_dono(interaction):
            return
        await enviar_cupons_ativos(interaction)


class _CancelarSelect(discord.ui.Select):
    def __init__(self, guild: discord.Guild, cupons: list[dict]) -> None:
        opcoes = [
            discord.SelectOption(
                label=f"{c['codigo']} ({c['desconto']}%)",
                value=c["codigo"],
                description=f"Titular: {_nome_titular(guild, c['titular_id'])}"[:100],
            )
            for c in cupons[:25]
        ]
        super().__init__(placeholder="Selecione o cupom para cancelar", options=opcoes)

    async def callback(self, interaction: discord.Interaction) -> None:
        await cancelar_e_notificar(interaction, self.values[0])


def _cancelar_view(guild: discord.Guild, cupons: list[dict]) -> discord.ui.LayoutView:
    view = discord.ui.LayoutView(timeout=60)
    view.add_item(
        discord.ui.Container(
            discord.ui.TextDisplay("Selecione o cupom ativo que deseja cancelar."),
            discord.ui.ActionRow(_CancelarSelect(guild, cupons)),
            accent_colour=config.COR_AVISO,
        )
    )
    return view


class _CancelarCupomButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Cancelar Cupom", emoji="🗑️", style=discord.ButtonStyle.secondary, custom_id="cupom:cancelar"
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        if not await garantir_dono(interaction):
            return
        guild = interaction.guild
        cupons = await database.listar_cupons(guild.id, "ativo")
        if not cupons:
            await utils.responder(interaction, utils.info("Não há cupons ativos para cancelar."))
            return
        await utils.responder(interaction, _cancelar_view(guild, cupons))


class PainelCuponsView(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"# {config.CUPOM_PAINEL_DONO_TITULO}\n{config.CUPOM_PAINEL_DONO_INTRO}"
                ),
                discord.ui.Separator(),
                discord.ui.ActionRow(
                    _CriarCupomButton(), _CuponsAtivosButton(), _CancelarCupomButton()
                ),
                accent_colour=config.COR_PADRAO,
            )
        )


# ================================================================= criação de cupom
class CriarCupomModal(discord.ui.Modal, title="Criar cupom de desconto"):
    def __init__(self) -> None:
        super().__init__()
        self.codigo_input = discord.ui.TextInput(
            placeholder="ex: BLACKFRIDAY30", max_length=config.CODIGO_MAX, required=True
        )
        self.desconto_input = discord.ui.Select(
            options=[discord.SelectOption(label=f"{d}%", value=str(d)) for d in config.DESCONTOS],
            required=True,
        )
        self.titular_input = discord.ui.UserSelect(required=True)
        self.dias_input = discord.ui.TextInput(
            placeholder=f"ex: 30 (máx. {config.VALIDADE_MAX_DIAS})", required=True, max_length=4
        )

        self.add_item(discord.ui.Label(text="Nome do cupom", component=self.codigo_input))
        self.add_item(discord.ui.Label(text="Porcentagem de desconto", component=self.desconto_input))
        self.add_item(discord.ui.Label(text="Cliente titular", component=self.titular_input))
        self.add_item(discord.ui.Label(text="Validade em dias", component=self.dias_input))

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return

        codigo = str(self.codigo_input.value).strip().upper()
        if not _CODIGO_RE.match(codigo):
            await utils.responder(
                interaction,
                utils.erro(
                    f"O código precisa ter de {config.CODIGO_MIN} a {config.CODIGO_MAX} caracteres, "
                    "usando apenas letras, números e hífen."
                ),
            )
            return

        existente = await database.get_cupom(guild.id, codigo)
        if existente and existente["status"] == "ativo":
            await utils.responder(interaction, utils.erro(f"Já existe um cupom ativo com o código `{codigo}`."))
            return
        if existente:
            await utils.responder(
                interaction,
                utils.erro(f"O código `{codigo}` já foi usado neste servidor. Escolha um código diferente."),
            )
            return

        dias_texto = str(self.dias_input.value).strip()
        if not dias_texto.isdigit():
            await utils.responder(interaction, utils.erro("A validade precisa ser um número inteiro de dias."))
            return
        dias = int(dias_texto)
        if not (1 <= dias <= config.VALIDADE_MAX_DIAS):
            await utils.responder(
                interaction,
                utils.erro(f"A validade precisa estar entre 1 e {config.VALIDADE_MAX_DIAS} dias."),
            )
            return

        if not self.desconto_input.values:
            await utils.responder(interaction, utils.erro("Selecione uma porcentagem de desconto."))
            return
        desconto = int(self.desconto_input.values[0])
        if desconto not in config.DESCONTOS:
            await utils.responder(interaction, utils.erro("Porcentagem de desconto inválida."))
            return

        if not self.titular_input.values:
            await utils.responder(interaction, utils.erro("Selecione o cliente titular do cupom."))
            return
        titular = self.titular_input.values[0]
        if titular.bot:
            await utils.responder(interaction, utils.erro("O titular do cupom não pode ser um bot."))
            return

        criado = await database.criar_cupom(guild.id, codigo, desconto, titular.id, interaction.user.id, dias)
        if not criado:
            await utils.responder(interaction, utils.erro(f"Já existe um cupom com o código `{codigo}`."))
            return

        cupom = await database.get_cupom(guild.id, codigo)
        vencimento = discord.utils.format_dt(datetime.fromisoformat(cupom["expira_em"]), style="R")

        await utils.responder(
            interaction,
            utils.sucesso(
                f"**Código** • `{codigo}`\n**Desconto** • {desconto}%\n"
                f"**Titular** • {titular.mention}\n**Validade** • {vencimento}",
                titulo="🎫  Cupom criado",
            ),
        )

        await utils.enviar_log(
            guild,
            _log_view(
                "🎫  Cupom criado",
                [
                    f"**Código** • `{codigo}`",
                    f"**Desconto** • {desconto}%",
                    f"**Titular** • {titular.mention} (`{titular.id}`)",
                    f"**Criado por** • {interaction.user.mention}",
                    f"**Validade** • {vencimento}",
                ],
                guild,
                config.COR_SUCESSO,
            ),
        )

        try:
            await titular.send(
                view=utils.info(
                    f"Você recebeu um cupom de desconto em **{guild.name}**!\n\n"
                    f"**Código** • `{codigo}`\n**Desconto** • {desconto}%\n**Validade** • {vencimento}",
                    titulo="🎫  Novo cupom",
                )
            )
        except discord.HTTPException:
            pass


# ================================================================= painel público
class _MeusCuponsButton(discord.ui.Button):
    def __init__(self) -> None:
        super().__init__(
            label="Meus Cupons", emoji="🎟️", style=discord.ButtonStyle.primary, custom_id="cupom:meus"
        )

    async def callback(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        if guild is None:
            return
        cupons = await database.cupons_do_membro(guild.id, interaction.user.id)
        if not cupons:
            await utils.responder(interaction, utils.info("Você não tem nenhum cupom ativo no momento."))
            return

        linhas = [
            f"`{c['codigo']}` • {c['desconto']}% • vence "
            f"{discord.utils.format_dt(datetime.fromisoformat(c['expira_em']), style='R')}"
            for c in cupons
        ]
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay("### 🎟️  Meus cupons\n" + "\n".join(linhas)),
                accent_colour=config.COR_INFO,
            )
        )
        await utils.responder(interaction, view)


class PainelCupomPublicoView(discord.ui.LayoutView):
    def __init__(self) -> None:
        super().__init__(timeout=None)
        self.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(
                    f"# {config.CUPOM_PAINEL_PUB_TITULO}\n{config.CUPOM_PAINEL_PUB_INTRO}"
                ),
                discord.ui.Separator(),
                discord.ui.ActionRow(_MeusCuponsButton()),
                accent_colour=config.COR_PADRAO,
            )
        )


# ================================================================= aplicação no ticket
class AplicarCupomModal(discord.ui.Modal, title="Aplicar cupom de desconto"):
    codigo = discord.ui.TextInput(label="Código do cupom", max_length=config.CODIGO_MAX, required=True)
    valor = discord.ui.TextInput(
        label="Valor total da compra", placeholder="ex: 100,50", required=True, max_length=20
    )

    async def on_submit(self, interaction: discord.Interaction) -> None:
        guild = interaction.guild
        canal = interaction.channel
        if guild is None or not isinstance(canal, discord.TextChannel):
            return

        ticket = await database.get_ticket(canal.id)
        if not ticket or ticket["status"] != "aberto":
            await utils.responder(interaction, utils.erro("Este canal não é um ticket aberto."))
            return

        if not await utils.garantir_staff(interaction):
            return

        codigo = str(self.codigo.value).strip().upper()
        cupom = await database.get_cupom(guild.id, codigo)
        if not cupom:
            await utils.responder(interaction, utils.erro(f"Nenhum cupom encontrado com o código `{codigo}`."))
            return

        if cupom["status"] == "usado":
            await utils.responder(interaction, utils.erro("Este cupom já foi utilizado."))
            return
        if cupom["status"] == "cancelado":
            await utils.responder(interaction, utils.erro("Este cupom foi cancelado."))
            return
        if cupom["status"] != "ativo":
            await utils.responder(interaction, utils.erro("Este cupom não está mais ativo."))
            return

        if datetime.fromisoformat(cupom["expira_em"]) <= datetime.now(timezone.utc):
            await database.expirar_cupons(guild.id)
            await utils.responder(interaction, utils.erro("Este cupom está vencido."))
            return

        if cupom["titular_id"] != ticket["user_id"]:
            await utils.responder(interaction, utils.erro("Este cupom pertence a outro cliente."))
            return

        bruto = re.sub(r"[Rr]\$", "", str(self.valor.value).strip()).strip()
        bruto = bruto.replace(" ", "").replace(",", ".")
        try:
            valor_total = float(bruto)
        except ValueError:
            await utils.responder(interaction, utils.erro("Informe um valor numérico válido."))
            return
        if valor_total <= 0:
            await utils.responder(interaction, utils.erro("O valor precisa ser maior que zero."))
            return

        desconto = cupom["desconto"]
        desconto_valor = round(valor_total * desconto / 100, 2)
        valor_final = round(valor_total - desconto_valor, 2)

        usado = await database.usar_cupom(
            guild.id, codigo, interaction.user.id, ticket["id"], valor_total, valor_final
        )
        if not usado:
            await utils.responder(interaction, utils.erro("Este cupom acabou de ser utilizado."))
            return

        await utils.responder(interaction, utils.sucesso(f"Cupom `{codigo}` aplicado com sucesso."))

        titular_mencao = f"<@{cupom['titular_id']}>"
        corpo = (
            f"**Cupom** • `{codigo}` ({desconto}% OFF)\n"
            f"**Cliente** • {titular_mencao}\n"
            f"**Valor original** • {utils.formatar_real(valor_total)}\n"
            f"**Desconto** • - {utils.formatar_real(desconto_valor)}\n"
            f"**Valor final** • **{utils.formatar_real(valor_final)}**"
        )
        view = discord.ui.LayoutView(timeout=None)
        view.add_item(
            discord.ui.Container(
                discord.ui.TextDisplay(f"### 🎟️  Cupom aplicado\n{corpo}"),
                discord.ui.Separator(),
                discord.ui.TextDisplay(f"-# Aplicado por {interaction.user.mention}"),
                accent_colour=config.COR_SUCESSO,
            )
        )
        await canal.send(view=view, allowed_mentions=discord.AllowedMentions(users=True))

        await utils.enviar_log(
            guild,
            _log_view(
                "🎟️  Cupom utilizado",
                [
                    f"**Ticket** • #{ticket['numero']:04d}",
                    f"**Código** • `{codigo}` ({desconto}% OFF)",
                    f"**Cliente** • {titular_mencao}",
                    f"**Valor original** • {utils.formatar_real(valor_total)}",
                    f"**Valor final** • {utils.formatar_real(valor_final)}",
                    f"**Aplicado por** • {interaction.user.mention}",
                ],
                guild,
                config.COR_SUCESSO,
            ),
        )
