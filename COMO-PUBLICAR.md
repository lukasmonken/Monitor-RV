# Como pôr o monitor no ar (repositório público + secrets)

## Por que assim?

O **GitHub Pages grátis só publica de repositório público**. Como o repositório
fica público, **nada sensível pode estar nele**. Por isso:

| O quê | Onde fica | Vai pro GitHub? |
|-------|-----------|-----------------|
| Código (`atualizar.py`, `docs/index.html`) | repositório | **Sim** — não tem segredo nenhum |
| `docs/dados.enc.js` | repositório | **Sim** — mas **cifrado** (ilegível sem a senha) |
| **Carteiras** (ativos e pesos) | secret `MONITOR_CARTEIRAS` | **Não** |
| **Senha** | secret `MONITOR_SENHA` | **Não** |
| `pdfs/`, `carteiras/`, `senha.local` | só na sua máquina | **Não** (`.gitignore`) |

Resultado: o repositório é público, mas **não revela os ativos**. Eles só existem
dentro do secret e do arquivo cifrado.

---

## Passo 1 — Enviar o código

No **GitHub Desktop**, com o repositório **Monitor-RV** aberto:
1. Ele vai listar ~9 arquivos (código, `docs/`, workflow, os .md).
2. Escreva uma mensagem (ex.: "monitor de carteiras") → **Commit to main**.
3. Clique **Push origin**.

> Confira que **não** aparecem `carteiras/`, `pdfs/`, `senha.local`. Se aparecerem,
> pare e avise — o `.gitignore` deveria bloquear.

## Passo 2 — Criar os 3 secrets ⚠️ (é o que protege tudo)

No navegador: repositório → **Settings → Secrets and variables → Actions →
New repository secret**. Crie os três:

**1. `MONITOR_SENHA`** — a senha de acesso ao painel.
> Use uma senha **longa e aleatória** (ex.: `Cavalo-Nuvem-Terra-9182-Vento`).
> O arquivo cifrado é público: senha fraca (tipo marca+ano) pode ser quebrada
> por tentativa e erro fora do site.

**2. `MONITOR_USUARIO`** — o usuário (ex.: `VAROS`).

**3. `MONITOR_CARTEIRAS`** — as carteiras. Abra o arquivo **`carteiras.local.txt`**
(está na pasta do projeto e não vai pro GitHub), **copie tudo** e cole aqui.
O formato é:

```
### Crescimento
ticker,empresa,peso
BBAS3,Banco do Brasil,16.67
...

### Internacional
ticker,empresa,peso,mercado
QQQM,Invesco NASDAQ 100,36,US
```

## Passo 3 — Ligar o site (Pages na pasta `/docs`)

1. **Settings → Pages**
2. **Source:** "Deploy from a branch" · **Branch:** `main` · **Pasta: `/docs`** → **Save**
3. Em ~1 min aparece: **"Your site is live at https://SEU-USUARIO.github.io/Monitor-RV/"**

## Passo 4 — Ligar o robô e gerar os dados

1. Aba **Actions** → se pedir, **"I understand my workflows, go ahead and enable them"**
2. Clique em **"Atualizar monitor de carteiras"** → **Run workflow → Run workflow**
3. Em 1–2 min ele lê as carteiras do secret, busca as cotações e publica o
   `docs/dados.enc.js` **cifrado com a sua senha**.

> Antes deste passo o site mostra "Arquivo de dados não encontrado" — é normal,
> o robô ainda não gerou nada.

Depois disso ele roda sozinho **a cada 15 min, seg–sex, 10h–17h45 (Brasília)**.

## Passo 5 — Conferir

1. Abra o link do site → deve aparecer a **tela de login** → entre → o painel carrega.
2. Na aba **Code** do repositório, confirme que **não existe** pasta `carteiras/`
   nem senha em lugar nenhum.

Mande o link para o time, e o usuário/senha **por canal privado** (não junto do link).

---

## Manutenção

**Mudou uma carteira (rebalanceamento)?**
1. Edite o CSV em `carteiras/` na sua máquina.
2. Rode `python3 gerar_secret.py` — ele regera o `carteiras.local.txt`.
3. Copie o conteúdo e **atualize o secret `MONITOR_CARTEIRAS`**.
4. Aba **Actions → Run workflow** (ou espere o próximo ciclo).

**Trocar a senha?** Atualize o secret `MONITOR_SENHA` → **Run workflow**.

**Rodar na hora?** Actions → **Run workflow**.

---

## Rodar na sua máquina (opcional)

O robô já faz tudo. Se quiser testar local:

```bash
pip install -r requirements.txt
python3 atualizar.py
```

Ele usa os CSVs de `carteiras/` e a senha do arquivo `senha.local` — os dois
ficam só no seu computador.
