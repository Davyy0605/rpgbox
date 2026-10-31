# Guia de deploy do RPGBox

Este guia leva o site do seu computador até a internet. Você vai criar três contas gratuitas (Neon, Cloudflare e Render), copiar alguns valores de uma para a outra e conferir tudo em um celular de verdade. Não é preciso saber programar: siga os passos na ordem e não pule a parte "Conferir".

Regra de ouro: as chaves e senhas que você vai copiar abaixo **nunca** vão para o código nem para o GitHub. Elas só entram nas "variáveis de ambiente" do Render.

## Resumo do que cada serviço faz

| Serviço | Para quê | Valor que você leva dele |
|---|---|---|
| Neon | Banco de dados (textos, registros, contas) | `DATABASE_URL` |
| Cloudflare R2 | Guarda fotos, PDFs e Word | `R2_BUCKET`, `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY` |
| Render | Executa o site | recebe todas as variáveis acima, mais `SECRET_KEY` e `ALLOWED_HOSTS` |

O arquivo `.env.example` na raiz do projeto lista todas as variáveis, sem valores reais.

## 1. Criar o banco no Neon

1. Entre em https://neon.tech e crie a conta.
2. Crie um projeto (o nome pode ser `rpgbox`). Escolha a região mais próxima do Brasil disponível (por exemplo, São Paulo, se houver; senão, a região dos EUA mais ao leste).
3. Na tela do projeto, clique em **Connect** e copie a **connection string** (começa com `postgresql://`). Ela deve terminar com `?sslmode=require`.
4. Guarde esse texto: é o `DATABASE_URL`. Trate como senha.

## 2. Criar o bucket e a chave no Cloudflare R2

1. Entre em https://dash.cloudflare.com e crie a conta. O R2 pede um cartão para ativar, mas o plano gratuito (10 GB) não cobra enquanto você ficar dentro dele.
2. No menu, abra **R2 Object Storage** e clique em **Create bucket**. Nome sugerido: `rpgbox-arquivos`. Deixe o bucket **privado** (não ative "Public access"). Esse nome é o `R2_BUCKET`.
3. Na página inicial do R2, copie o endereço da conta que aparece como **S3 API**: algo como `https://<codigo>.r2.cloudflarestorage.com`. É o `R2_ENDPOINT_URL`. Não inclua o nome do bucket no fim.
4. Ainda no R2, clique em **Manage API Tokens** e depois **Create API token**. Permissão: **Object Read & Write**. Restrinja ao bucket `rpgbox-arquivos`.
5. Ao criar, a tela mostra **Access Key ID** e **Secret Access Key**. A secret só aparece uma vez: copie agora. São `R2_ACCESS_KEY_ID` e `R2_SECRET_ACCESS_KEY`.

### 2.1 CORS do bucket (obrigatório para o leitor de PDF)

O leitor de PDF baixa o arquivo em pedaços (cabeçalho `Range`). Sem o CORS abaixo, o PDF não abre no site.

1. Abra o bucket, vá em **Settings** e procure **CORS Policy**, clique em **Add CORS policy**.
2. Cole (troque o endereço pelo do seu site no Render, ou pelo domínio próprio, sem barra no final):

```json
[
  {
    "AllowedOrigins": ["https://SEU-SITE.onrender.com"],
    "AllowedMethods": ["GET"],
    "AllowedHeaders": ["Range"],
    "ExposeHeaders": ["Content-Range", "Accept-Ranges", "Content-Length"],
    "MaxAgeSeconds": 3600
  }
]
```

3. Salve. Se mais tarde você trocar o domínio do site, volte aqui e atualize `AllowedOrigins`.

## 3. Acesso periódico para o site não "dormir" (conclusão sobre os termos do Render)

Pesquisado em 2026-10-31.

O plano gratuito do Render dorme o site depois de 15 minutos sem visitas e leva cerca de 1 minuto para acordar, o que atrapalha a consulta rápida durante a sessão de jogo. A ideia de manter o site acordado seria um serviço externo que acessa `/health` a cada 14 minutos.

O que os documentos do Render dizem de fato:

- https://render.com/docs/free: "Render spins down a Free web service that goes 15 minutes without receiving any inbound traffic." Cada workspace recebe 750 horas gratuitas por mês ("Render grants 750 Free instance hours to each workspace per calendar month"); acabando elas, os serviços gratuitos são suspensos até o mês seguinte. Um único site ligado o mês inteiro usa cerca de 744 horas, então cabe, mas sem folga para um segundo serviço gratuito no mesmo workspace. A página recomenda: "Do not use them for production applications." e diz que Render pode suspender um serviço gratuito que gere um volume incomum de tráfego de saída. A página **não** menciona pings, monitores externos ou keep-alive, nem para permitir nem para proibir.
- https://render.com/terms (Termos de Serviço): li o texto e **não há** cláusula sobre tráfego automatizado, keep-alive ou o plano gratuito.
- https://render.com/acceptable-use (Política de Uso Aceitável): não cita keep-alive. Proíbe "scrape, crawl, or harvest data" por meios automatizados e "attempt to bypass, circumvent, or defeat any access or usage restrictions". Um acesso periódico a `/health` não coleta dados, mas pode ser lido como contornar a regra de suspensão por inatividade; é uma interpretação, não uma proibição escrita.

**Conclusão:** nem permitido nem proibido de forma explícita. Por isso **não configurei** nenhum acesso periódico, e o `render.yaml` não tem nada disso. A decisão é sua:

- **Opção A, aceitar a espera:** o primeiro acesso depois de 15 minutos parados demora cerca de 1 minuto. Sem risco para a conta.
- **Opção B, plano pago do Render (a partir de US$ 7/mês no plano Starter, confirme o preço atual em https://render.com/pricing):** o site fica sempre ligado, sem depender de interpretação dos termos.
- **Opção C, assumir o risco e usar o acesso periódico:** crie um monitor externo gratuito (por exemplo, UptimeRobot, https://uptimerobot.com) do tipo HTTP(s), endereço `https://SEU-SITE.onrender.com/health`, intervalo de 14 minutos (o gratuito mais curto costuma ser 5 minutos; use esse se 14 não existir). O Render pode, no pior caso, suspender o serviço. Se isso acontecer, volte para A ou B.

Se você escolher B ou C, avise para registrarmos aqui.

## 4. Subir o site no Render

1. Coloque o projeto no GitHub (repositório privado serve).
2. Entre em https://render.com e crie a conta, ligando ao GitHub.
3. Clique em **New** e depois **Blueprint**. Escolha o repositório. O Render lê o arquivo `render.yaml` e já cria o serviço `rpgbox` no plano `free`, com `build.sh` e o comando de início (`gunicorn config.wsgi --workers 1 --threads 4 --timeout 120`).
4. O Render vai pedir os valores marcados como secretos. Preencha:

| Variável | Valor |
|---|---|
| `DATABASE_URL` | a string do Neon (passo 1) |
| `R2_BUCKET` | nome do bucket |
| `R2_ENDPOINT_URL` | endereço S3 do R2 |
| `R2_ACCESS_KEY_ID` | chave do R2 |
| `R2_SECRET_ACCESS_KEY` | segredo do R2 |
| `ALLOWED_HOSTS` | o endereço do site sem `https://`, ex.: `rpgbox.onrender.com` (vários: separados por vírgula) |

   `SECRET_KEY` é gerada sozinha pelo Render. **Não** crie a variável `DEBUG` (sem ela o site roda em modo de produção). `DATABASE_URL` e `R2_BUCKET` são obrigatórios nesse modo: se um estiver vazio, o build falha na hora com uma mensagem clara, em vez de o site rodar em banco e disco que o Render apaga a cada reinício.
5. Confirme. O primeiro build leva alguns minutos e já roda as migrações.
   Se o build falhar dizendo que a versão do Python não existe ou não é aceita, abra o serviço no Render, vá em **Environment** e troque `PYTHON_VERSION` por uma versão completa mais antiga (por exemplo `3.13.5`, o formato exige os três números). O código foi testado só no 3.14.3; em outra versão, rode os testes (`pytest --ignore=tests/e2e`) antes de confiar.
6. Quando ficar "Live", abra `https://SEU-SITE.onrender.com/health`: deve mostrar `ok`.
7. Volte ao passo 2.1 e coloque o endereço real em `AllowedOrigins`, se ainda não colocou.

### Criar o superusuário (administrador)

No painel do serviço no Render, abra **Shell** (no plano gratuito pode não estar disponível) e rode:

```
python manage.py createsuperuser
```

Se o Shell não existir no plano gratuito, rode do seu computador com o `DATABASE_URL` do Neon:

No Windows (PowerShell):

```
$env:DATABASE_URL="cole-a-string-do-neon"; $env:SECRET_KEY="qualquer"; $env:DEBUG="true"
python manage.py createsuperuser
```

No Mac ou Linux:

```
DATABASE_URL="cole-a-string-do-neon" SECRET_KEY=qualquer DEBUG=true python manage.py createsuperuser
```

O administrador fica em `/admin/`.

## 5. Conferir o R2 de verdade

Antes de confiar nos arquivos, teste o bucket real (uma vez). Defina no seu computador as quatro variáveis do R2 (`R2_BUCKET`, `R2_ENDPOINT_URL`, `R2_ACCESS_KEY_ID`, `R2_SECRET_ACCESS_KEY`) e as três de apoio (`SECRET_KEY` com qualquer texto e `DEBUG=true`). No PowerShell, cada uma assim: `$env:R2_BUCKET="rpgbox-arquivos"`. Depois:

```
python manage.py shell
>>> from django.core.files.base import ContentFile
>>> from django.core.files.storage import default_storage as s
>>> n = s.save("teste/ola.txt", ContentFile(b"ola"))      # PUT
>>> s.open(n).read()                                       # GET
b'ola'
>>> import urllib.request; urllib.request.urlopen(s.url(n)).read()   # link assinado
b'ola'
>>> s.delete(n); s.exists(n)                               # DELETE
False
```

O `render.yaml` já define `AWS_REQUEST_CHECKSUM_CALCULATION=when_required` e `AWS_RESPONSE_CHECKSUM_VALIDATION=when_required` (nomes e valores conferidos na documentação do boto3, https://docs.aws.amazon.com/boto3/latest/guide/configuration.html). Eles evitam que versões novas do `boto3` enviem checksums extras que o R2 pode recusar. A documentação da Cloudflare que li não fala disso, então este teste é a prova. Para reproduzir no seu computador, defina também as duas variáveis (`$env:AWS_REQUEST_CHECKSUM_CALCULATION="when_required"` no PowerShell). Se ainda assim aparecer erro de checksum ou `NotImplemented`, me envie a mensagem.

Também confira o CORS: no site, abra um PDF enviado. Ele deve abrir e permitir rolar as páginas. Se ficar em branco, o CORS do passo 2.1 está errado (ou o endereço em `AllowedOrigins` não é igual ao do site).

## 6. Testar em um celular de verdade

Use o celular, com o site aberto pelo endereço do Render. Se tiver iPhone e Android, repita nos dois.

1. Criar uma conta nova e entrar.
2. Criar uma campanha e um registro.
3. Tirar uma foto com a câmera, dentro do registro, e ver a miniatura aparecer.
4. Enviar um PDF e abri-lo no leitor.
5. Enviar um arquivo Word.
6. Escrever um texto e digitar `@` para citar outro registro.
7. Escrever, desligar o sinal (modo avião) no meio, continuar escrevendo, religar. O texto deve ser salvo e nada se perde.
8. Voltar pelo gesto/botão do aparelho: deve voltar para a tela anterior do site, sem sair dele por engano.
9. **Android, botão físico de voltar, link direto com o painel aberto:** abra um registro por um link direto (cole o endereço em uma aba nova), abra o painel lateral e aperte o voltar do aparelho. Esperado: fecha o painel e continua no registro; um segundo voltar sai do registro.
10. **Voltar sem cache de página (bfcache):** navegue por duas ou três telas, volte pelo gesto e confira que a tela anterior aparece atualizada (sem texto antigo) e que o editor continua funcionando. Teste também depois de deixar o site em segundo plano por alguns minutos e voltar a ele.

Anote o que falhou (modelo do celular, navegador e o passo) e me envie.

## Problemas comuns

- **Erro 400 "Bad Request" ao abrir o site:** `ALLOWED_HOSTS` não tem o endereço certo.
- **Erro ao subir: `SECRET_KEY é obrigatória`:** a variável não foi criada (ela é gerada pelo `render.yaml`; confira em Environment).
- **Primeiro acesso muito lento:** é o site acordando (passo 3).
- **Fotos não aparecem:** confira as quatro variáveis do R2 e o passo 5.
