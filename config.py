import os

from dotenv import load_dotenv

load_dotenv()

TOKEN = os.getenv("DISCORD_TOKEN", "")
GUILD_ID = os.getenv("GUILD_ID") or None
DB_PATH = os.getenv("DB_PATH", "data/tickets.db")

# Cores
COR_PADRAO = 0x2B2D31
COR_SUCESSO = 0x57F287
COR_ERRO = 0xED4245
COR_AVISO = 0xFEE75C
COR_INFO = 0x5865F2

# Categorias de ticket. Para criar uma nova, basta adicionar aqui.
CATEGORIAS = {
    "suporte": {
        "nome": "Suporte",
        "emoji": "🔵",
        "descricao": "Dúvidas, ajuda geral ou problemas no servidor",
        "prefixo": "suporte",
        "campo_config": "categoria_suporte",
        "estilo": "primary",
    },
    "comprar": {
        "nome": "Comprar",
        "emoji": "💰",
        "descricao": "Compra de produtos ou serviços",
        "prefixo": "comprar",
        "campo_config": "categoria_comprar",
        "estilo": "success",
    },
}

PAINEL_TITULO = "💎 Central de Atendimento"
PAINEL_INTRO = "Selecione abaixo o tipo de ticket que deseja abrir e aguarde o suporte da equipe."
PAINEL_REGRAS = (
    "▸ Tickets abertos na categoria incorreta serão finalizados.\n"
    "▸ Descreva seu problema com o máximo de detalhes possíveis.\n"
    "▸ O prazo de resposta pode variar de 24 a 48 horas."
)
PAINEL_RODAPE = "Central de Atendimento"

MENSAGEM_ABERTURA_PADRAO = (
    "Olá {membro}, seja bem-vindo(a) ao seu atendimento!\n\n"
    "Descreva seu problema com o máximo de detalhes possíveis e aguarde "
    "que um membro da equipe assuma o seu ticket."
)

# Segundos até o canal ser apagado depois de finalizado
DELAY_DELETAR = 8

# Máximo de mensagens salvas no transcript
LIMITE_TRANSCRIPT = 2000

# Cupons de desconto
DESCONTOS = [15, 20, 30, 50, 60]  # percentuais permitidos
VALIDADE_MAX_DIAS = 365
CODIGO_MIN = 3
CODIGO_MAX = 20

CUPOM_PAINEL_DONO_TITULO = "🎫 Gerenciamento de Cupons"
CUPOM_PAINEL_DONO_INTRO = "Área restrita. Crie, consulte e cancele cupons de desconto."
CUPOM_PAINEL_PUB_TITULO = "🎟️ Meus Cupons"
CUPOM_PAINEL_PUB_INTRO = "Clique abaixo para ver os cupons de desconto que estão no seu nome."

ADMIN_PAINEL_TITULO = "🛠️ Painel Administrativo"
ADMIN_PAINEL_INTRO = "Área restrita. Configure canais, categorias, cargos e publique os painéis por aqui."
