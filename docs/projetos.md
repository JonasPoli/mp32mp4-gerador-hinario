# Documentação dos Projetos — Hinário CCB

Este documento detalha a estrutura, configuração e funcionamento de cada projeto do pipeline de geração de vídeos do Hinário CCB.

---

## Visão Geral

O sistema gera vídeos MP4 a partir de:
1. **Áudio** (`.mp3`) — gravação instrumental do hino
2. **Legenda** (`.json`) — letra sincronizada com timestamps
3. **Thumbnail** — imagem gerada a partir da máscara do canal + instrumento + número/nome do hino
4. **Vinheta** — abertura padrão do canal

Cada **projeto** representa um timbre/instrumento diferente e é uma pasta independente dentro de `projects/`.

---

## Estrutura de Diretórios de um Projeto

```
projects/<nome_do_projeto>/
├── config.json          # Configuração do projeto (metadados, template de título, etc.)
├── assets/
│   ├── mascara.png      # Máscara de fundo para thumbnails (1280x720)
│   └── instrumento.png  # Imagem do instrumento para composição da thumb
├── inputs/
│   ├── hino_001.json    # Legenda sincronizada do hino 001
│   ├── hino_001.mp3     # Áudio do hino 001
│   ├── hino_002.json
│   ├── hino_002.mp3
│   └── ...
└── outputs/             # Diretório onde os vídeos gerados são salvos
    ├── hino_001.mp4
    └── ...
```

---

## Formato do `config.json`

```json
{
  "nome_exibicao": "Nome do Projeto para Exibição",
  "csv_path": "fontes/hinario5.csv",
  "mp3_dir": "mp3",
  "thumb_pipeline": "v01",
  "vinheta": "vinheta/vinheta-hinario-04-v1.mp4",
  "titulo_template": "Hino <numero-do-hino> - <nome-do-hino> | Hinário 5 CCB | <nome-do-projeto>",
  "palavras_chaves": "hino <numero-do-hino>, ... palavras-chave para SEO ...",
  "descricao": "Descrição completa para o YouTube ...",
  "desenho": {
    "numero": {
      "x": 120,
      "y_top": 150,
      "y_bottom": 780,
      "max_width": 580,
      "cor": [26, 45, 90, 255],
      "brilho": {
        "raio": 3,
        "cor": [255, 255, 255, 255]
      }
    },
    "nome": {
      "x": 780,
      "y_top": 200,
      "y_bottom": 800,
      "max_width": 550,
      "cor": [26, 45, 90, 255],
      "max_font_size": 100,
      "align": "left",
      "brilho": {
        "raio": 3,
        "cor": [255, 255, 255, 255]
      }
    }
  },
  "instrumento": "projects/<projeto>/assets/instrumento.png",
  "inputs_dir": "projects/<projeto>/inputs",
  "mascara": "projects/<projeto>/assets/mascara.png"
}
```

### Campos Principais

| Campo | Descrição |
|-------|-----------|
| `nome_exibicao` | Nome legível do projeto (usado em títulos e descrições) |
| `csv_path` | Caminho para o CSV com metadados dos hinos |
| `thumb_pipeline` | Versão do pipeline de geração de thumbnails |
| `vinheta` | Caminho para o vídeo de vinheta/abertura |
| `titulo_template` | Template do título do vídeo no YouTube |
| `palavras_chaves` | Template de palavras-chave para SEO |
| `descricao` | Template da descrição do vídeo |
| `desenho` | Configurações de posicionamento de texto na thumbnail |
| `instrumento` | Caminho para a imagem PNG do instrumento |
| `inputs_dir` | Diretório contendo os inputs (MP3 + JSON) |
| `mascara` | Caminho para a máscara de fundo da thumbnail |

### Variáveis de Template

Estas variáveis são substituídas automaticamente nos campos `titulo_template`, `palavras_chaves` e `descricao`:

| Variável | Substituição |
|----------|-------------|
| `<numero-do-hino>` | Número do hino (ex: 001) |
| `<nome-do-hino>` | Nome completo do hino |
| `<nome-sem-acento>` | Nome do hino sem acentos |
| `<nome-do-projeto>` | Valor do campo `nome_exibicao` |

---

## Formato do JSON de Legenda

Cada hino possui um arquivo `.json` com a legenda sincronizada:

```json
{
  "titulo": "Louvemos ao Senhor",
  "numero": 1,
  "legendas": [
    {
      "inicio": 0.0,
      "fim": 5.5,
      "texto": "Louvemos ao Senhor,"
    },
    {
      "inicio": 5.5,
      "fim": 11.2,
      "texto": "Que é digno de louvor!"
    }
  ]
}
```

---

## Projetos Configurados

### Projetos com pipeline completo (config + assets + inputs)

| Projeto | Hinos | Config | Instrumento | Máscara | Status |
|---------|-------|--------|-------------|---------|--------|
| `orgao_yamaha` | 486 | ✅ | ✅ | ✅ | Ativo — 485 concluídos |
| `hinos_de_ninar` | 480 | ✅ | ✅ | ✅ | Pendente |
| `piano_yamaha` | 480 | ✅ | ✅ | ✅ | Pendente |
| `meia_hora` | 50 | ✅ | ✅ (reutiliza orgao) | ✅ (reutiliza orgao) | 50 concluídos |

### Novos projetos configurados (aguardando `instrumento.png`)

| Projeto | Hinos | Config | Instrumento | Máscara | Status |
|---------|-------|--------|-------------|---------|--------|
| `brass` | 480 | ✅ | ⚠️ pendente | ✅ | Pendente |
| `orquestra` | 480 | ✅ | ⚠️ pendente | ✅ | Pendente |
| `palhetas` | 479 | ✅ | ⚠️ pendente | ✅ | Pendente |
| `sopro` | 480 | ✅ | ⚠️ pendente | ✅ | Pendente |
| `string` | 479 | ✅ | ⚠️ pendente | ✅ | Pendente |

> **Nota**: Para que as thumbnails sejam geradas corretamente, é necessário adicionar o arquivo `instrumento.png` em `projects/<projeto>/assets/` para cada um dos projetos pendentes.

### Projetos legados (formato antigo no `projetos.json`)

| Projeto | Hinos | Notas |
|---------|-------|-------|
| `hinario4` | 79 | Formato de configuração diretamente no `projetos.json` |
| `coros` | 6 | Apenas 6 coros configurados |

---

## Como Adicionar um Novo Projeto

1. **Criar o diretório** do projeto:
   ```bash
   mkdir -p projects/<novo_projeto>/{assets,inputs,outputs}
   ```

2. **Preparar os assets**:
   - Criar ou copiar `mascara.png` (1280x720) em `assets/`
   - Criar ou copiar `instrumento.png` em `assets/`

3. **Preparar os inputs**:
   - Colocar os arquivos `.mp3` e `.json` em `inputs/`
   - Formato dos nomes: `hino_NNN.mp3` / `hino_NNN.json`

4. **Criar o `config.json`**:
   - Copiar de um projeto existente e ajustar `nome_exibicao`, `descricao`, `palavras_chaves`, etc.

5. **Registrar no `projetos.json`**:
   - Adicionar a entrada com a chave do projeto

6. **Popular o banco de dados**:
   ```sql
   INSERT INTO videos (projeto, numero, mp3_file, hinario, status, criado_em)
   VALUES ('<novo_projeto>', <numero>, '<mp3_path>', 'hinario5', 'pendente', datetime('now'));
   ```

7. **Gerar os vídeos**:
   ```bash
   python gerar_videos.py --projeto <novo_projeto>
   ```

---

## Banco de Dados (`progresso.db`)

A tabela `videos` no SQLite controla o progresso de geração:

| Coluna | Tipo | Descrição |
|--------|------|-----------|
| `id` | INTEGER | Chave primária |
| `projeto` | TEXT | Chave do projeto |
| `numero` | INTEGER | Número do hino |
| `mp3_file` | TEXT | Caminho para o MP3 |
| `hinario` | TEXT | Identificador do hinário |
| `status` | TEXT | `pendente` ou `concluido` |
| `criado_em` | TEXT | Data de criação do registro |

### Consultas Úteis

```sql
-- Ver progresso por projeto
SELECT projeto, COUNT(*) as total,
       SUM(CASE WHEN status='pendente' THEN 1 ELSE 0 END) as pendentes,
       SUM(CASE WHEN status='concluido' THEN 1 ELSE 0 END) as concluidos
FROM videos GROUP BY projeto ORDER BY projeto;

-- Ver hinos pendentes de um projeto
SELECT numero, mp3_file FROM videos
WHERE projeto = 'brass' AND status = 'pendente'
ORDER BY numero;

-- Marcar hino como concluído
UPDATE videos SET status = 'concluido'
WHERE projeto = 'brass' AND numero = 1;
```
