# RPGBox: design

Data: 2026-10-30. Documento de produto e arquitetura para a primeira versão.

Convenção: **[Autor]** marca o que o autor do projeto decidiu. **[Decisão de design]** marca o que foi escolhido pelo Claude e pode ser contestado na revisão.

## 1. Intenção

RPGBox é um serviço web para mestres de RPG. Hoje o autor guarda o material das campanhas em Google Docs e canais do Discord, e os links das trilhas em outro documento. Durante a sessão, os jogadores esperam enquanto o mestre procura imagem, nome e detalhes de um personagem, ou troca de trilha.

O serviço tem dois objetivos de mesmo peso:

1. **Consulta rápida no meio da sessão:** achar personagem, item, região ou trilha em segundos.
2. **Criação fácil, divertida e motivadora:** escrever personagens, itens, regiões e tudo o mais sem atrito, inclusive em um momento de inspiração.

Público inicial: mestres próximos ao autor, com conta própria. Pode crescer para mais pessoas se ficar muito bom, mas a primeira versão não é construída para escala pública.

**O celular é a experiência principal.** O autor usa o celular quando o PC não está disponível e quer foco nele. O computador se adapta às telas do celular, não o contrário.

## 2. Objetivos

- Login com nome de usuário, email e senha, com o espaço de cada mestre isolado.
- Campanhas dentro do espaço do mestre, com cópia de registros entre campanhas.
- Tipos de registro (Personagens, Itens, Regiões, Trilhas e outros criados pelo mestre), cada um com modelo personalizável.
- Abas em cada registro, aceitando texto, imagens e documentos.
- Links internos com `@` no meio do texto, com retorno automático ("Citado em").
- Busca global, lista por texto e galeria por imagem.
- Consulta rápida em painel e tela completa com tudo.
- Trilhas guardadas como links, com cópia em um toque.

## 3. Não objetivos da primeira versão

- Tocar música, ter bot próprio ou integrar com o Discord. O bot musical atual continua sendo usado, com copiar e colar. **[Autor]**
- Acesso de jogadores. A ferramenta é só do mestre, e o que os jogadores veem continua passando pelo Discord. **[Autor]**
- Converter Word em texto editável dentro do site. **[Autor]**
- Recuperação de senha por email, porque exige mais um serviço externo. **[Decisão de design]**
- Busca de imagens para o mestre: o serviço só facilita guardar. **[Autor]**
- Tema claro. **[Decisão de design]**
- Colaboração entre mestres na mesma campanha. **[Decisão de design]**

## 4. Antiobjetivos

Isto seria um fracasso mesmo funcionando:

- **Poluição visual.** O autor testou o Karpal e o maior defeito foi o excesso de informação na tela, apertado no celular. Telas limpas e pouca informação por vez são uma regra, não um acabamento.
- **Sessão parada.** Qualquer fluxo de consulta que faça os jogadores esperarem.
- **Perder escrita.** Uma ideia digitada e perdida por falta de salvamento.
- **Ficar perdido nos links.** Navegar entre registros sem conseguir voltar facilmente, sobretudo no celular.

## 5. Conceitos

| Conceito | Definição |
|---|---|
| Mestre | Conta de usuário. Tudo abaixo pertence a um mestre. |
| Campanha | Espaço de uma história. Contém tipos, modelos e registros próprios. |
| Tipo de registro | Categoria dentro da campanha: Personagens, Itens, Regiões, Trilhas, Raças, Cartas etc. |
| Modelo | Definição de um tipo: campos básicos e abas iniciais. |
| Registro | Uma entrada concreta: Kael, Elfos, Porto Cinza. |
| Aba | Seção de um registro: Ficha, Habilidades, Magias, Raça, Galeria etc. |
| Bloco | Conteúdo dentro de uma aba: texto, imagens ou documentos. |
| Link | Referência `@` de um texto para um registro ou para um título dentro dele. |

Uma nova campanha já vem com os tipos Personagens, Itens, Regiões e Trilhas, cada um com modelo pronto. **[Decisão de design]** Os modelos prontos também valem para campanhas novas, sem biblioteca global de modelos do mestre nesta versão: cada campanha edita os seus. **[Decisão de design]**

Modelos prontos iniciais **[Decisão de design]**:

- **Personagens:** nome, ocupação, idade, resumo; abas Ficha, Habilidades, Magias, História.
- **Itens:** nome, categoria, raridade, resumo; abas Descrição, Efeitos.
- **Regiões:** nome, tipo de lugar, resumo; abas Descrição, Eventos.
- **Trilhas:** nome, link, clima (texto livre); sem abas no modelo, porque a trilha é só um link com cópia em um toque.

Todo registro, de qualquer tipo, já tem uma Galeria embutida (seção 6.9), que não é um campo nem uma aba do modelo.

## 6. Comportamento

### 6.1 Contas e isolamento

Cadastro e login com nome de usuário, email e senha. Um mestre nunca vê nem acessa dados ou arquivos de outro, e isso vale também para os links diretos de arquivos. **[Autor: espaço próprio]**

O cadastro é aberto a quem tiver o link do site, e o autor pretende divulgar só para pessoas próximas. **[Autor]** Sem recuperação por email, quem esquecer a senha pede ao autor, que redefine pelo painel administrativo do Django. **[Decisão de design]**

Não há limite de espaço por mestre. **[Autor]** O site mostra ao mestre quanto ele está usando, e o painel administrativo mostra o total, para o autor acompanhar os 10 GB gratuitos. **[Decisão de design]**

### 6.2 Navegação no celular

**[Autor: opção B no modelo visual]** Ao abrir a campanha, a tela inicial mostra busca, a lista de tipos com contagem de registros, incluindo os criados pelo mestre, e um botão de criar. Não há barra fixa inferior.

Ao tocar em um tipo, abre a lista daquele tipo, com a busca no topo e a alternância **Lista / Galeria**. A lista por texto nunca é removida. **[Autor]**

A primeira tela após o login abre a última campanha usada, para o mestre chegar rápido ao que estava fazendo. **[Decisão de design]** Criar e personalizar precisam estar a um toque. **[Autor]**

### 6.3 Consulta rápida e tela completa

**[Autor]** Tocar em um registro abre um painel que sobe do fim da tela, com imagem, dados básicos e links, sem sair da lista. Arrastar para baixo fecha. "Expandir" abre a tela completa, com todas as abas.

O painel mostra a imagem principal e os campos básicos do modelo. Campos de texto longo, como `resumo`, usam o mesmo editor das abas e aceitam `@`, e são eles que trazem links ao painel. O painel não reúne links das abas nem mostra "Citado em", que fica na tela completa, para não poluir. **[Decisão de design]**

No computador, o mesmo conteúdo aparece em um painel lateral ao lado da lista. **[Decisão de design]**

Tocar em um `@` dentro da consulta rápida abre a consulta do destino. **[Decisão de design]**

### 6.4 Voltar

**[Autor: voltar precisa ser fácil, sobretudo no celular]** O botão de voltar do navegador e do celular sempre funciona, inclusive para fechar o painel de consulta rápida. A tela mostra o caminho percorrido no topo, como `Kael › Elfos › Visão no Escuro`. **[Decisão de design: como cumprir o pedido]**

### 6.5 Busca

Uma busca sempre disponível encontra personagens, itens, regiões, trilhas, registros de tipos criados pelo mestre e títulos dentro dos textos. Resultados aparecem enquanto se digita. No computador, abre com `Ctrl + K`. A busca é limitada à campanha aberta. **[Decisão de design]**

### 6.6 Editor de texto e links

Editor com o básico: títulos, negrito, itálico e listas, com salvamento automático. **[Decisão de design]**

Salvamento **[Decisão de design]**: o texto fica guardado no aparelho até o servidor confirmar, e o envio é repetido sozinho. Isso cobre sinal fraco e o site acordando. Se o mesmo texto foi alterado em outro aparelho, o site avisa e mantém as duas versões visíveis para o mestre escolher, sem sobrescrever em silêncio. Não há histórico de versões nem uso offline completo.

Colar do Google Docs preserva títulos, negrito e listas, para migrar o material existente. Isso é requisito na escolha do editor. **[Decisão de design]**

Digitar `@` abre uma lista de sugestões com registros e títulos da campanha. Escolher uma opção cria um link. **[Autor: link em texto]**

- **Títulos são alvos de link.** Todo título dentro de um texto vira alvo automaticamente, como `Elfos › Visão no Escuro`, sem marcação manual. Abrir esse link leva direto ao trecho, e a consulta rápida pode mostrar só aquele trecho. **[Decisão de design, aprovada pelo autor no resumo final]**
- **Citado em.** A página do destino lista automaticamente onde ela foi citada. Assim, a relação entre registros é escrita uma vez, dentro do texto. Isso ataca o desânimo que o autor relatou ao escrever relações de regiões com personagens e eventos. **[Decisão de design]**
- **Renomear não quebra links:** o link aponta para o registro, e o texto exibido acompanha o novo nome. **[Decisão de design]**
- **Apagar:** um link para algo apagado aparece como texto simples riscado. Apagar pede confirmação e informa quantas citações existem. **[Decisão de design]**
- Links só apontam para dentro da mesma campanha.

### 6.7 Registros compartilhados, como Raças

Uma raça é um registro comum de um tipo criado pelo mestre. "Elfos" guarda as habilidades, e a aba "Raça" do personagem **mostra o texto completo de Elfos dentro da própria aba**, só para leitura. **[Autor]** O texto mostrado é sempre o atual: mudar Elfos muda para todos. Quem precisar de uma versão própria escreve na ficha do personagem, ao lado do conteúdo trazido. **[Decisão de design]**

Isso exige um bloco próprio, o **bloco incorporado**, que pode ser adicionado a qualquer aba e aponta para um registro ou para um título dentro dele. Regras **[Decisão de design]**:

- O mestre escolhe a origem com a mesma lista de sugestões do `@`. Um toque no bloco abre a origem para editar.
- Só há um nível: um bloco incorporado dentro do conteúdo trazido aparece como link, o que evita repetição infinita, como A mostrar B e B mostrar A.
- A origem lista o registro em "Citado em". A busca encontra o texto só na origem, sem repetir um resultado por personagem.
- Se a origem for apagada, o bloco mostra um aviso com o nome antigo, e o aviso de apagar conta esses usos.

### 6.8 Modelos personalizáveis

O mestre edita um modelo adicionando, renomeando, reordenando e removendo campos básicos e abas. Abas são sempre livres e aceitam texto, imagens e documentos. Um campo básico é texto curto, texto longo, número ou link. Um campo do tipo link ganha botão de copiar nas listas e na consulta rápida, em qualquer tipo. **[Decisão de design]**

Mudar um modelo não apaga o que já foi escrito. **[Decisão de design, aprovada pelo autor no resumo final]** Um novo campo ou aba aparece nos registros existentes, vazio. Um campo ou aba removido deixa de aparecer em registros novos, mas nos existentes o conteúdo continua visível enquanto houver conteúdo.

Além do modelo, cada registro pode ter abas próprias, adicionadas só nele. **[Autor: "outras abas que o mestre queira adicionar"]**

**Sub-abas [Autor]:** criar uma sub-aba precisa ser fácil, em qualquer aba. Elas funcionam em dois lugares:

- **Dentro de um registro:** qualquer aba pode ter sub-abas, com um botão `+` direto na própria aba, sem passar pelo editor de modelo. Por exemplo, Magias pode ter Fogo e Gelo. Cada sub-aba aceita o mesmo conteúdo de uma aba. Sub-abas também podem fazer parte do modelo. **[Decisão de design]**
- **Na lista de um tipo:** o mestre cria sub-abas para separar os registros, como Combate, Taverna e Suspense em Trilhas. Isso cumpre o exemplo do autor, porque cada trilha é um registro. Uma sub-aba "Todas" fica sempre disponível, e cada registro pode estar em uma sub-aba, ou em nenhuma. **[Decisão de design]**

Há um único nível de sub-abas, para manter o celular limpo. No celular, elas aparecem em uma faixa que desliza para o lado. **[Decisão de design]**

### 6.9 Documentos e imagens

**[Autor]** PDFs e imagens abrem dentro do site. Word e outros formatos são guardados e baixados com um toque, abrindo no aplicativo do celular.

Imagens entram arrastando, colando ou escolhendo do aparelho, sem etapas de upload separadas. **[Decisão de design]**

Todo registro tem uma Galeria embutida, que aparece como aba na tela completa, sem depender do modelo. A primeira imagem é a principal, e o mestre pode trocar. Essa imagem é a que aparece na consulta rápida, na lista e na alternância Galeria, com um espaço neutro com o nome quando não há imagem. Não existe campo de imagem separado. Em registros sem imagens, a aba fica discreta, para não poluir tipos como Trilhas. **[Decisão de design]**

**Imagens leves [Autor: pesar bem pouco para economizar espaço]:** toda imagem é reduzida antes de ser guardada, para no máximo 1600 px no lado maior, em WebP com qualidade em torno de 80, o que costuma resultar em poucas centenas de KB. A redução acontece no navegador, antes do envio, para gastar menos dados no celular e não pesar no servidor gratuito, e o servidor confere o resultado. O original não é guardado. Miniaturas pequenas são geradas para listas e galeria. **[Decisão de design: como cumprir o pedido]**

Limite de 25 MB por arquivo, antes da redução no caso das imagens. **[Decisão de design]** PDFs e documentos são guardados como vieram. Tipos aceitos: imagens, PDF, documentos de Office e OpenDocument, texto simples. Arquivos que o navegador poderia executar, como HTML e SVG, nunca são abertos dentro do site. **[Decisão de design]**

### 6.10 Trilhas

Trilhas é um tipo comum, com um campo do tipo link. A lista mostra um botão de copiar em cada linha, com um toque. **[Autor: copiar e colar no bot]** O mestre pode editar esse modelo e criar outros tipos com link, como "Efeitos sonoros". Trilhas também aparecem na busca e aceitam links `@`, para constar em uma região, por exemplo. **[Decisão de design]**

Para migrar o documento atual, é possível colar várias trilhas de uma vez, uma por linha, com nome e link. **[Decisão de design]**

### 6.11 Copiar entre campanhas

Um registro pode ser copiado para outra campanha do mesmo mestre. A cópia é independente: mudar uma não altera a outra. **[Decisão de design, aprovada pelo autor no resumo final]**

A cópia leva campos, abas, textos e arquivos. Se o tipo não existir no destino, ele é criado a partir do modelo de origem. Links `@` para registros que não foram copiados viram texto simples com o nome. Um bloco incorporado cuja origem não foi copiada vira texto normal, editável, com o conteúdo daquele momento, para o personagem não perder as habilidades ao mudar de campanha. **[Decisão de design]**

## 7. Visual

O autor deixou a parte visual por conta do Claude. **[Autor]** Direção: fantasia sóbria e escura, com poucos elementos por tela, texto confortável e alvos de toque grandes. **[Decisão de design]** Os esboços da sessão foram só estruturais e não fixam cores.

## 8. Restrições

- **Linguagem:** Python, porque o autor tem experiência e quer poder corrigir pequenos bugs sozinho. **[Autor]**
- **Hospedagem:** Render, no plano gratuito. **[Autor]**
- **Custo:** a proposta é ficar nos planos gratuitos. O autor aceitou criar contas no Neon e no Cloudflare, e vai criá-las por conta própria. **[Autor]**
- **Idioma da interface:** português do Brasil. **[Decisão de design]**
- O projeto hoje contém apenas um `app.py` vazio, que pode ser substituído.

## 9. Arquitetura

**[Decisão de design, salvo Python e Render]**

- **Django**, servindo páginas prontas do servidor. Traz login, banco de dados, migrações e painel administrativo prontos, e é fácil de manter para quem sabe Python.
- **Mínimo de JavaScript:** htmx para painéis e navegação parcial, e um editor pronto para o texto e as sugestões de `@`. O restante é HTML e CSS. A escolha exata do editor fica para quem constrói, e ele precisa gravar conteúdo estruturado (JSON), funcionar bem em teclado de celular e suportar sugestões `@`.
- **Banco de dados:** Postgres no Neon. Registros guardam campos em JSON, o que permite modelos personalizados sem criar tabelas novas. Links ficam em uma tabela própria, atualizada ao salvar, o que permite montar "Citado em" e renomear sem reprocessar textos.
- **Busca:** busca textual do Postgres, com suporte a nomes parciais e acentos.
- **Arquivos:** Cloudflare R2. O site entrega links temporários assinados só depois de confirmar que o arquivo é do mestre logado.
- **Configuração:** endereços e chaves ficam em variáveis de ambiente no Render, nunca no código.

Por que três serviços: o sistema de arquivos gratuito do Render é apagado a cada reinício, e o Postgres gratuito dele expira em 30 dias, com exclusão após 14 dias de carência. O Supabase foi descartado por oferecer só 1 GB de arquivos, limitar cada arquivo a 50 MB e pausar após uma semana com pouco uso.

### Risco conhecido: início lento

O plano gratuito do Render adormece após 15 minutos sem acessos e leva cerca de 1 minuto para acordar. Isso contraria diretamente o objetivo de consulta rápida. Mitigação: um serviço externo acessa o site a cada 14 minutos, consumindo as 750 horas mensais gratuitas, suficientes para um site ligado o mês todo. Ainda falta confirmar se os termos do Render permitem essa prática. Se não permitirem, o autor decide entre aceitar a espera ou pagar pelo plano pago. A arquitetura não muda.

### Risco conhecido: espaço de arquivos

Com cadastro aberto e sem limite por mestre, os 10 GB gratuitos do R2 são compartilhados por todos, e nada impede uma conta de consumir tudo. O autor aceitou esse risco, porque vai divulgar o link a poucas pessoas. Se o site crescer, cadastro por convite e limite por mestre são os primeiros ajustes.

### Backups

Os planos gratuitos do Render não oferecem backup, e o histórico do Neon gratuito é limitado. Como perda de dados é um antiobjetivo, o mestre pode exportar uma campanha em um arquivo zip legível, com textos e arquivos. É uma cópia para guardar: não há importação de volta nesta versão, então recuperar dados a partir dela é manual. **[Decisão de design]**

## 10. O que fica para quem constrói

- Estrutura de pastas e nomes.
- Biblioteca exata de editor e de CSS, respeitando a seção 9.
- Detalhes visuais e de animação, respeitando as seções 4 e 7.
- Formato do arquivo de exportação.
- Ordem das etapas de construção. O autor colocou personagens com abas, documentos, galeria, links e busca como base, e praticamente tudo acima entra na primeira versão.

## 11. Como saber que deu certo

- Em uma campanha real, o autor larga o Docs e o documento de trilhas.
- No celular, com uma mão, chegar a um personagem e ver imagem e resumo leva poucos segundos e poucos toques.
- Uma ideia registrada no celular está lá, salva, ao reabrir.
- Os mestres próximos conseguem criar um tipo próprio, como Raças, sem explicação.
