# Plano: Geração Automática de Vídeos — Hinário 4 CCB

## Objetivo

Gerar automaticamente um vídeo por hino para todos os arquivos MP3 existentes na pasta `mp3/`, combinando vídeos de fundo disponíveis localmente (ou baixados automaticamente quando necessário), adicionando um frame inicial com o número do hino, e produzindo um arquivo `.md` com títulos, descrições e tags prontos para publicação no YouTube.

O sistema deve ser **incremental**: ao adicionar novos áudios (de um novo hinário ou lote), basta rodar o script novamente — apenas os vídeos ainda não gerados serão processados.

---

## Fontes de Dados

| Recurso | Localização | Descrição |
|---|---|---|
| Áudios | `mp3/` | Um arquivo `.mp3` por hino. O nome deve conter o número do hino. |
| Vídeos de fundo | `videos_flores/` | Vídeos de flores baixados automaticamente via API. |
| Fotos/vídeos extras | `Photos-1-001/` | Fotos e vídeos adicionais para composição (pool extra). |
| Frame base | `images/sem-numero.png` | Imagem de fundo do frame inicial (sem número). |
| Dados dos hinos | `fontes/hinario4_sequential.csv` | CSV com colunas `Número` e `Nome`. |
| Índice de downloads | `videos_flores/_baixados.json` | Gerado por `baixar_videos_flores.py`; registra o que já foi baixado por provedor:id. |
| Banco de progresso | `progresso.db` | SQLite com estado de todos os vídeos e clipes. |
| Script de download | `baixar_videos_flores.py` | Script Python que baixa vídeos via Pexels, Pixabay e Coverr. |

---

## Fluxo de Execução

### 1. Inicialização

1. Carregar `fontes/hinario4_sequential.csv` → dicionário `{número → nome_do_hino}`.
2. Abrir (ou criar) o banco `progresso.db` com as tabelas abaixo.
3. Escanear `mp3/` e inserir na tabela `videos` somente os hinos ainda não registrados.
4. Escanear `videos_flores/` e `Photos-1-001/` e sincronizar a tabela `clipes` (inserir novos, não remover os já usados).

> **Incremental por design:** o banco garante que rodar o script uma segunda vez — seja por adição de novos MP3s ou de novos clipes baixados — processa apenas o que falta, sem refazer o que já está `concluido`.

---

### 2. Esquema do Banco de Dados (`progresso.db`)

#### Tabela `videos` — controle de geração por hino

```sql
CREATE TABLE IF NOT EXISTS videos (
    numero      INTEGER PRIMARY KEY,
    mp3_file    TEXT NOT NULL,          -- caminho relativo ao arquivo .mp3
    hinario     TEXT NOT NULL,          -- ex.: 'hinario4', 'hinario5' (para suporte futuro)
    status      TEXT DEFAULT 'pendente',-- 'pendente' | 'processando' | 'concluido' | 'erro'
    output      TEXT,                   -- caminho do .mp4 gerado
    erro_msg    TEXT,                   -- mensagem de erro, se houver
    criado_em   TEXT,                   -- timestamp ISO 8601
    atualizado_em TEXT
);
```

#### Tabela `clipes` — pool de vídeos de fundo

```sql
CREATE TABLE IF NOT EXISTS clipes (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    caminho     TEXT UNIQUE NOT NULL,   -- caminho relativo ao arquivo de vídeo
    fonte       TEXT,                   -- 'videos_flores' | 'photos'
    duracao_s   REAL,                   -- duração em segundos (preenchida no scan)
    usado_em    INTEGER,                -- número do hino que usou este clipe; NULL = disponível
    FOREIGN KEY (usado_em) REFERENCES videos(numero)
);
```

> **Regra fundamental:** nenhum clipe deve ser reutilizado em dois hinos diferentes. Um clipe marcado com `usado_em` não pode ser atribuído a outro hino.

#### Tabela `downloads` — rastreio de clipes baixados via API

```sql
CREATE TABLE IF NOT EXISTS downloads (
    id          INTEGER PRIMARY KEY AUTOINCREMENT,
    provider    TEXT,                   -- 'pexels' | 'pixabay' | 'coverr'
    provider_id TEXT,                   -- id do vídeo no provedor
    query       TEXT,                   -- termo de busca usado
    caminho     TEXT UNIQUE,            -- arquivo local salvo
    baixado_em  TEXT                    -- timestamp
);
```

---

### 3. Download Automático de Clipes (quando o pool se esgota)

Antes de processar cada hino, verificar se há clipes disponíveis (`usado_em IS NULL`).

**Se não houver clipes suficientes:**

1. Chamar `baixar_videos_flores.py` programaticamente (via `subprocess`) ou importar suas funções diretamente.
2. O script aceita os seguintes parâmetros relevantes:

| Parâmetro | Padrão | Descrição |
|---|---|---|
| `--query` | `flores` | Termo de busca (pode variar: `flowers`, `natureza`, `campo`, etc.) |
| `--out` | `videos_flores` | Pasta de destino dos downloads |
| `--providers` | `pexels,pixabay` | Provedores ativos (requer chaves de API) |
| `--per-page` | `40` | Resultados por página |
| `--max-pages` | `5` | Máximo de páginas consultadas por provedor |
| `--min-duration` | `0` | Duração mínima dos vídeos em segundos |
| `--orientation` | `landscape` | Preferência de orientação |

3. As chaves de API devem estar nas variáveis de ambiente:
   - `PEXELS_API_KEY`
   - `PIXABAY_API_KEY`
   - `COVERR_API_KEY` (opcional)

4. Após o download, re-escanear `videos_flores/` e atualizar a tabela `clipes` com os novos arquivos.
5. Registrar os novos downloads também na tabela `downloads` para auditoria.

**Estratégia de busca progressiva:** se `flores` já foi buscado e não há novidades, tentar queries alternativas em sequência:
`flores` → `flowers` → `natureza` → `nature` → `campo` → `jardim` → `primavera`

O estado da última query usada pode ser guardado em uma tabela de configuração simples:

```sql
CREATE TABLE IF NOT EXISTS config (
    chave TEXT PRIMARY KEY,
    valor TEXT
);
-- ex.: INSERT OR REPLACE INTO config VALUES ('ultima_query_download', 'natureza');
```

---

### 4. Geração do Frame Inicial

Para cada hino:

1. Abrir `images/sem-numero.png` com Pillow.
2. Renderizar o número do hino centralizado, em fonte grande e clara (ex.: branca com sombra).
3. Salvar o resultado em memória (não em disco, para não sobrescrever a cada hino).
4. Converter a imagem em um clipe de vídeo de **5 segundos** via `ffmpeg`.

---

### 5. Composição do Vídeo Principal

#### 5.1 Seleção de clipes

1. Calcular a duração do MP3 com `mutagen` ou `ffprobe`.
2. Selecionar clipes disponíveis (`usado_em IS NULL`) até cobrir a duração necessária.
3. Se um único clipe for insuficiente, usar loop espelhado para o mesmo clipe:
   ```
   [clipe] → [clipe reverso] → [clipe] → ...
   ```
   Isso preenche a duração sem consumir novos clipes de outros hinos.
4. Se não houver clipes suficientes mesmo com loop → acionar o download automático (seção 3).

#### 5.2 Transições entre clipes diferentes

Ao concatenar dois clipes distintos, aplicar transição **blur/fade** via `ffmpeg`:

- Filtro: `xfade=fade` ou passagem com `gblur` progressivo.
- Duração da transição: **1 segundo**.

#### 5.3 Montagem final

```
[Frame inicial — 5s, sem áudio] + [Vídeo principal — duração do MP3, com áudio]
```

- Áudio = arquivo `.mp3` do hino.
- O frame inicial tem silêncio ou fade-in suave de 0.5s no início do áudio.
- Duração total = 5s + duração do MP3.

---

### 6. Flags de Linha de Comando

```
python gerar_videos.py [opções]
```

| Flag | Descrição |
|---|---|
| `--forcar-inicio <numero>` | Processa a partir deste número, ignorando os anteriores. |
| `--apenas <numero>` | Processa somente o hino indicado (modo teste). |
| `--resetar <numero>` | Redefine status para `pendente` no banco (permite regerar). |
| `--resetar-todos` | Redefine todos os hinos para `pendente` (regerar tudo). |
| `--hinario <nome>` | Filtra pelo campo `hinario` na tabela `videos` (ex.: `hinario5`). |
| `--sem-download` | Nunca chama `baixar_videos_flores.py`, mesmo sem clipes disponíveis. |
| `--forcar-download` | Baixa novos clipes antes de iniciar, independente do pool atual. |

---

### 7. Suporte a Novos Áudios / Hinários Futuros

O sistema foi projetado para ser **extensível sem refazer o que já existe**:

1. **Adicionar novos MP3s:** basta colocar os arquivos na pasta `mp3/` e rodar o script novamente. O banco identificará os números/hinos novos (não presentes em `videos`) e os adicionará como `pendente`.

2. **Novo hinário (ex.: Hinário 5):** adicionar um novo CSV em `fontes/` (ex.: `hinario5_sequential.csv`) e um novo lote de MP3s identificados. O campo `hinario` na tabela `videos` diferencia os lotes. A flag `--hinario hinario5` permite processar somente o novo lote.

3. **Novos vídeos de fundo:** basta rodar `baixar_videos_flores.py` manualmente com novas queries ou novos provedores. O script salva os arquivos em `videos_flores/` e o banco de progresso os incorpora automaticamente no próximo scan.

4. **Regerar vídeos com erro:** usar `--resetar <numero>` para um hino específico ou `--resetar-todos` para refazer toda a fila.

---

### 8. Geração do Arquivo de Metadados (`videos_gerados.md`)

Após cada vídeo gerado com sucesso, **acrescentar** (não sobrescrever) a entrada correspondente em `videos_gerados.md`.

**Formato de cada entrada:**

```md
# {numero}

## Título para o vídeo
Hino {numero} - {nome_hino} | Hinário 4 CCB | Teclado Yamaha PSR


## Descrição para o YouTube

Hino {numero} - {nome_hino}
Hinário 4 - Congregação Cristã no Brasil

Execução instrumental no teclado Yamaha PSR.

Este vídeo apresenta o áudio do hino {numero}, "{nome_hino}", tocado em teclado, com uma interpretação simples e reverente para momentos de meditação, estudo, louvor e acompanhamento musical.

Que esta melodia possa trazer paz, comunhão e edificação.

🎹 Instrumento: Teclado Yamaha PSR
🎵 Hino: {numero}
📖 Hinário: Hinário 4
🎶 Título: {nome_hino}

Inscreva-se no canal para acompanhar mais hinos instrumentais da CCB no teclado.

#{tag_hino} #Hinario4 #CCB


## Descrição mais completa

Hino {numero} - {nome_hino}
Hinário 4 - Congregação Cristã no Brasil

Neste vídeo, apresento o áudio instrumental do hino {numero}, "{nome_hino}", tocado em teclado Yamaha PSR.

A proposta deste conteúdo é compartilhar uma versão instrumental simples, tranquila e reverente, ideal para quem deseja ouvir, estudar, acompanhar ou meditar por meio dos hinos.

🎹 Instrumento utilizado: Teclado Yamaha PSR
🎼 Hino: {numero}
📖 Hinário: Hinário 4
🎵 Nome do hino: {nome_hino}
🎧 Tipo de conteúdo: Áudio instrumental

Se este hino falou ao seu coração, deixe seu like, compartilhe com alguém e inscreva-se no canal para acompanhar novos hinos tocados no teclado.

Que Deus abençoe a todos.

#{tag_hino} #Hinario4 #CCB #{tag_nome}


## Tags para YouTube

hino {numero}, hino {numero} ccb, {nome_sem_acento}, hinário 4, hinario 4, ccb hino {numero}, hinos ccb, hinos da ccb, congregação cristã no brasil, congregacao crista no brasil, hinos tocados no teclado, hino no teclado, teclado yamaha psr, yamaha psr, hinos ccb teclado, hino instrumental ccb, ccb instrumental, hinário ccb, hinario ccb, hinos para meditação, hinos para meditacao, música instrumental cristã, musica instrumental crista, louvor instrumental, teclado evangélico, hinos evangélicos no teclado, hino {numero} instrumental

---
```

> **Geração das variáveis de template:**
> - `{tag_hino}` = `Hino{numero}` (ex.: `Hino290`)
> - `{tag_nome}` = nome do hino sem espaços e sem acentos em CamelCase (ex.: `CristoJesusSuaMaoMeDa`)
> - `{nome_sem_acento}` = nome em minúsculas sem acentos (ex.: `cristo jesus sua mao me da`)
> - Nome do hino obtido sempre via `fontes/hinario4_sequential.csv` pelo número

---

## Dependências Técnicas

| Pacote | Uso |
|---|---|
| `ffmpeg` (sistema) | Composição, concatenação, transições e conversão de vídeo |
| `Pillow` | Renderização do número no frame inicial |
| `mutagen` | Leitura da duração dos arquivos MP3 |
| `requests` + `tqdm` | Usados internamente por `baixar_videos_flores.py` |
| `sqlite3` | Banco de progresso (built-in do Python) |
| `subprocess` | Chamadas ao `ffmpeg` e ao script de download |
| `unicodedata` | Remoção de acentos para geração de tags |

Instalar dependências Python:
```bash
pip install Pillow mutagen requests tqdm
```

---

## Estrutura de Arquivos

```
hinário/
├── mp3/                        ← áudios dos hinos (input)
├── videos_flores/              ← vídeos de fundo baixados
│   └── _baixados.json          ← índice de downloads (gerado por baixar_videos_flores.py)
├── Photos-1-001/               ← pool extra de vídeos/fotos
├── images/
│   └── sem-numero.png          ← frame base para o número
├── fontes/
│   └── hinario4_sequential.csv ← dados dos hinos
├── output/                     ← vídeos finais gerados
│   ├── hino_001.mp4
│   └── ...
├── videos_gerados.md           ← metadados para YouTube (acrescentado a cada run)
├── progresso.db                ← banco SQLite de controle
├── baixar_videos_flores.py     ← script de download de clipes
└── gerar_videos.py             ← script principal (a criar)
```

---

## Algoritmo Principal

```
INICIALIZAÇÃO:
  carregar CSV → dicionário {numero → nome}
  abrir/criar progresso.db
  sincronizar tabela videos com mp3/ (inserir novos como 'pendente')
  sincronizar tabela clipes com videos_flores/ e Photos-1-001/

LOOP PRINCIPAL (por hino em ordem numérica):
  se status != 'pendente': pular

  marcar status = 'processando'

  1. verificar clipes disponíveis (usado_em IS NULL)
     → se insuficientes e --sem-download não ativo:
         chamar baixar_videos_flores.py com próxima query disponível
         re-escanear e atualizar tabela clipes

  2. gerar frame inicial (5s) com número renderizado via Pillow

  3. calcular duração do mp3 via mutagen/ffprobe

  4. selecionar clipes até cobrir duração:
     → usar loop espelhado [original → reverso → original] se clipe único for suficiente
     → usar múltiplos clipes se necessário (cada um marcado como usado_em)

  5. concatenar clipes com transições blur via ffmpeg

  6. montar vídeo final:
     [frame inicial 5s] + [vídeo principal + áudio mp3]

  7. salvar em output/hino_{numero}.mp4

  8. marcar status = 'concluido', registrar output e clipes usados no banco

  9. acrescentar entrada em videos_gerados.md
```