# Monitor de Carteira — VAROS Academy Renda Variável

Painel para acompanhar, **em tempo quase real (~15 min)**, a performance das
carteiras da VAROS Academy: a variação de **cada carteira** e de **cada ativo**,
nas janelas **Dia**, **Semana** e **Mês**, com **benchmark** e **alpha** por
carteira. A página é protegida por **login e senha** (os dados ficam cifrados;
sem a senha, nada aparece).

Identidade visual VAROS: fundo preto, paleta verde-turquesa, fonte Instrument Sans.

---

## Como funciona

```
   ┌──────────────┐   consulta o Yahoo,    ┌───────────────────┐   login+senha   ┌──────────────────┐
   │ atualizar.py │  calcula e CIFRA os    │ docs/dados.enc.js  │  descriptografa │  docs/index.html │
   │   (Python)   │ ─────────────────────► │  (cifrado)         │ ──────────────► │   (interface)    │
   └──────────────┘                        └───────────────────┘   no navegador  └──────────────────┘
     roda na nuvem                            lido pelo raw.                      a equipe acessa
     a cada 15 min                            githubusercontent                   por um link
```

- **O Python faz o trabalho pesado**: lê as carteiras, busca preços no Yahoo,
  calcula as variações ponderadas e os benchmarks, e **cifra tudo** (AES-256).
- **O navegador é a vitrine**: com o login e a senha certos, ele descriptografa
  o arquivo ali mesmo (Web Crypto) e desenha o painel. Sem a senha, é ilegível.

### De onde a página lê os dados

A página é servida pelo GitHub Pages, mas o `dados.enc.js` ela busca **direto no
repositório**, pelo `raw.githubusercontent.com`. Isso é de propósito.

Publicar no Pages não acontece no commit: depois de cada push, um segundo job do
GitHub (o `pages build and deployment`, que não é nosso e entra numa fila) é quem
leva o arquivo pro ar. Normalmente ele leva ~25s — mas em 24/07/2026 travou por
15 min e foi cancelado pelo push do ciclo seguinte, e a rodada daquele ciclo
simplesmente nunca chegou ao site. Somava-se a isso o cache de borda do Pages, de
10 min, que ignora a query string (o velho truque do `?t=` só enganava o cache do
navegador). O raw enxerga o commit na hora e tem cache de 5 min, ou seja: menos da
metade do ciclo de 15 min, então nenhuma rodada se perde.

Se o raw não responder, a página cai no arquivo do próprio Pages — e nunca troca
o que está na tela por um dado com carimbo mais **velho** que o já exibido.

---

## Segurança: nada sensível fica neste repositório

O GitHub Pages grátis só publica de repositório **público**. Por isso este
repositório **não contém nenhum dado sensível**:

| O quê | Onde fica | Está no repositório? |
|-------|-----------|----------------------|
| Código (`atualizar.py`, `docs/index.html`) | repositório | **Sim** — sem segredo algum |
| `docs/dados.enc.js` | repositório | **Sim**, mas **cifrado** (ilegível sem a senha) |
| **Carteiras** (ativos e pesos) | secret `MONITOR_CARTEIRAS` | **Não** |
| **Senha** | secret `MONITOR_SENHA` | **Não** |
| `carteiras/`, `pdfs/`, `senha.local` | só na máquina do autor | **Não** (`.gitignore`) |

O Pages serve a pasta **`/docs`** — onde está só o site e o arquivo cifrado.

---

## Login e senha

- O acesso é por **usuário + senha únicos** (sem cadastro de usuários).
- Eles **não estão no código**: ficam nos *secrets* `MONITOR_USUARIO` e
  `MONITOR_SENHA` do GitHub (Settings → Secrets and variables → Actions).
- Trocou a senha? Atualize o secret e rode o robô (Actions → **Run workflow**)
  para regerar o `docs/dados.enc.js` com a senha nova.

---

## As carteiras (pasta `carteiras/`)

Uma carteira = **um CSV** em `carteiras/`. O **nome do arquivo** vira o nome no
painel (ex.: `Renda.csv` → "Renda").

```
ticker,empresa,peso,mercado
BBDC4,Bradesco,14.29
QQQM,Invesco NASDAQ 100,36,US
```

- **ticker** — código do ativo (sem `.SA`; o script adiciona para papéis da B3).
- **empresa** — nome amigável (opcional).
- **peso** — percentual de alocação. É o que torna a variação da carteira
  **ponderada**. A soma não precisa dar 100 (normaliza sozinho). Sem a coluna =
  pesos iguais.
- **mercado** — opcional. `US` = ativo em bolsa dos EUA (cotado em **US$**, sem
  `.SA`); vazio ou `BR` = B3, em **R$**. As carteiras Internacionais usam isso.

**Benchmark de cada carteira:** definido no dicionário `BENCHMARKS` no topo do
`atualizar.py`, pelo **nome da carteira**. Hoje:

| Carteira | Benchmark | Como é medido (ETF que replica) |
|----------|-----------|----------------------------------|
| Crescimento / Crescimento PRO | SMLL (Small Caps) | SMAL11 |
| Renda / Renda PRO | IDIV (Dividendos) | DIVO11 |
| FIIs / FIIs PRO | IFIX | XFIX11 |
| Internacional / Internacional PRO | S&P 500 | SPY |

Os índices SMLL/IDIV/IFIX não têm histórico no Yahoo, então usamos os ETFs que
os replicam como proxy (retorno praticamente igual ao do índice). O **Alpha** é
quanto a carteira rendeu acima do benchmark **no mês**.

---

## Rodar no seu computador (opcional)

Só para gerar/testar localmente. Na nuvem, o robô faz sozinho.

```bash
pip install -r requirements.txt
python3 atualizar.py
```

Gera `docs/dados.enc.js`. Para ver o painel, abra `docs/index.html` (pelo link
https do GitHub Pages é o ideal; localmente o Chrome abre pelo `file://`).

---

## Períodos e cálculos

- **Dia** = agora vs. o **fechamento do pregão anterior** (variação de hoje).
- **Semana** = vs. o pregão mais próximo de **7 dias** atrás.
- **30 dias** = vs. o pregão mais próximo de **30 dias** atrás (janela móvel — não é
  o mês corrente).
- **Variação da carteira** = média das variações dos ativos **ponderada pelos
  pesos**; por janela, só entram os ativos com dado naquela janela.
- Preços do **Yahoo Finance**, fechamento **ajustado** (proventos e
  desdobramentos), atraso de ~15 min. Ativos **US$** têm a variação medida em dólar.

## Além do desempenho

- **Exibir → Setores:** exposição por setor de cada carteira (ações/FIIs por setor;
  internacionais pela composição real dos ETFs, via Yahoo).
- **Exibir → Destaques:** maiores altas e baixas por período (hoje / semana / 30 dias).
- **Topo:** Dólar (Bacen, série 1), CDI (série 4389) e IPCA 12m (série 13522), da API pública do Banco Central.
- **Bitcoin** (na visão "Todas"): preço em US$ · R$ e variação nas duas moedas.

Ferramenta de **acompanhamento** — não é recomendação de investimento.
