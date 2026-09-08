[33mcommit 75a6231acb41cdd7bf409c529482dd640e8764b0[m[33m ([m[1;36mHEAD[m[33m -> [m[1;32mmain[m[33m, [m[1;31morigin/main[m[33m, [m[1;31morigin/HEAD[m[33m)[m
Author: kaio <lorenaekaio@gmail.com>
Date:   Tue Sep 8 16:39:32 2026 -0300

    mesnsagem 33

[33mcommit 64bec6ddc6915216781f94db2f402f5b912a58e2[m
Author: kaio <lorenaekaio@gmail.com>
Date:   Tue Sep 8 16:10:38 2026 -0300

    Adicionar painel administrativo e remover comandos redundantes de /config
    
    Centraliza canais, categorias, cargos, opcoes e publicacao de paineis em
    um unico Painel Admin (botao "Configuracao" com menu de selecao), para
    nao depender de varios slash commands. Mantem so /config ver e
    /config painel-admin (bootstrap) no grupo de comandos.
    
    Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

[33mcommit bf17e7a09bbe565195f19921588f2bd1d638079e[m
Author: kaio <lorenaekaio@gmail.com>
Date:   Tue Sep 8 15:16:05 2026 -0300

    Adicionar sistema de cupons de desconto
    
    Cria a tabela cupons e migracao idempotente de guild_config, o modulo
    cupons.py com paineis de dono/publico e modais de criacao/aplicacao, o
    botao "Aplicar Cupom" no atendimento e os comandos /config e /cupom
    para gerenciar tudo pelo Discord.
    
    Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

[33mcommit aaac7083e4153fcf4adcbfc15b7c9f5dac1e68a6[m
Author: kaio <lorenaekaio@gmail.com>
Date:   Mon Sep 7 02:24:42 2026 -0300

    Redesenhar embed de historico de ticket fechado
    
    Substitui o embed generico por um layout dedicado (Ticket, Mensagens,
    Aberto por, Fechado por) quando a transcricao esta ativa, mantendo o
    arquivo .html como anexo do historico.
    
    Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

[33mcommit 3cbee1f1b57d413d8ca902002f2f21f317c5531f[m
Author: kaio <lorenaekaio@gmail.com>
Date:   Mon Sep 7 02:13:49 2026 -0300

    first commit

[33mcommit 471580012df715941bccf6c0b0a2c111f36f4036[m
Author: kaio <lorenaekaio@gmail.com>
Date:   Fri Sep 4 17:38:52 2026 -0300

    Modernizar UI para Components V2 e adicionar DM de chamado + rename ao assumir
    
    - Reescreve utils.py e ui.py trocando embeds classicos por Components V2
      (Container, Section, TextDisplay, Separator, Thumbnail, ActionRow), o
      formato de UI mais recente do Discord, para um visual mais limpo e atual.
    - Chamar Membro agora tambem envia DM ao autor do ticket avisando que foi
      chamado, alem do aviso no canal.
    - Assumir Atendimento agora renomeia automaticamente o canal para o nome
      do staff que assumiu.
    - Corrige chamadas para utils.log_embed (renomeada para log_view) que
      ficariam quebradas em /ticket adicionar e /ticket remover.
    
    Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>

[33mcommit 52a8c4f2187358ea866e816398f232a46f09ba0c[m
Author: kaio <lorenaekaio@gmail.com>
Date:   Fri Sep 4 17:13:38 2026 -0300

    Initial commit: bot de tickets para Discord
    
    Sistema de central de atendimento com abertura/fechamento de tickets,
    categorias configuraveis, transcript em HTML, avaliacao por estrelas
    e comandos de configuracao via slash commands.
    
    Co-Authored-By: Claude Sonnet 5 <noreply@anthropic.com>
