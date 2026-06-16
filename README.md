# Gerador de Vídeos — Hinário CCB

Gera automaticamente um vídeo por hino a partir dos arquivos MP3, combinando vídeos de flores como fundo, com frame inicial numerado e metadados prontos para publicação no YouTube.

---

## Instalação

### 1. Dependências do sistema

```bash
# macOS
brew install ffmpeg
```

### 2. Ambiente virtual Python (local no projeto)

Crie o venv **dentro da pasta do projeto** e ative-o:

```bash
# criar o venv na pasta .venv/ (dentro do projeto)
python3 -m venv .venv

# ativar (macOS / Linux)
source .venv/bin/activate

# instalar dependências
pip install Pillow mutagen requests tqdm
```

> O `.venv/` já está no `.gitignore` e nunca será enviado ao repositório.

Para desativar o ambiente quando terminar:

```bash
deactivate
```

**Sempre que abrir um novo terminal para trabalhar no projeto, ative o venv primeiro:**

```bash
source .venv/bin/activate
```

### 3. Chaves de API para download de vídeos de fundo

O sistema baixa vídeos automaticamente do Pexels e Pixabay quando o pool local se esgota. Crie as chaves gratuitamente e configure as variáveis de ambiente:

```bash
export PEXELS_API_KEY="sua_chave_aqui"
export PIXABAY_API_KEY="sua_chave_aqui"
```

Coloque essas linhas no seu `~/.zshrc` para não precisar repetir.

---

## Uso

### Gerar todos os vídeos

Roda pela primeira vez, gera tudo do zero:

```bash
python gerar_videos.py
```

O script:
1. Lê todos os MP3s da pasta `mp3/`
2. Busca vídeos de fundo em `videos_flores/` e `Photos-1-001/`
3. Baixa mais vídeos automaticamente se o pool acabar
4. Gera cada vídeo em `output/`
5. Atualiza `videos_gerados.md` com os metadados para YouTube

---

### Continuar de onde parou

Se o processo foi interrompido (queda de energia, `Ctrl+C`, erro), basta rodar o mesmo comando novamente:

```bash
python gerar_videos.py
```

O banco `progresso.db` registra o status de cada hino (`pendente`, `processando`, `concluido`, `erro`). O script pula automaticamente tudo que já está `concluido` e retoma os `pendente`.

> Hinos que ficaram presos em `processando` (interrupção abrupta) são tratados como `pendente` na próxima inicialização.

---

### Gerar apenas os novos (novos MP3s adicionados)

Adicione os novos arquivos MP3 à pasta `mp3/` e rode normalmente:

```bash
python gerar_videos.py
```

O script detecta automaticamente os hinos que ainda não estão no banco e os adiciona como `pendente`. Os vídeos já gerados **não são refeitos**.

#### Adicionar um novo hinário completo (ex.: Hinário 5)

1. Adicione o CSV com os nomes dos hinos em `fontes/hinario5_sequential.csv`
2. Adicione os MP3s em `mp3/` (com o número do hino no nome)
3. Rode filtrando pelo hinário:

```bash
python gerar_videos.py --hinario hinario5
```

---

### Gerar um hino específico

Útil para testar ou regravar um hino individualmente:

```bash
python gerar_videos.py --apenas 290
```

Isso processa **somente** o hino 290, mesmo que esteja marcado como `concluido`.

---

### Regerar um hino que já foi gerado

Para forçar a regeração de um vídeo específico (ex.: o resultado ficou ruim):

```bash
python gerar_videos.py --resetar 290
python gerar_videos.py --apenas 290
```

O `--resetar` volta o status do hino para `pendente` no banco e libera os clipes que ele havia reservado.

---

### Começar a partir de um número específico

Para pular os primeiros hinos e começar a partir de um número determinado:

```bash
python gerar_videos.py --forcar-inicio 100
```

Processa os hinos de 100 em diante que ainda estiverem `pendente`.

---

### Forçar download de novos vídeos de fundo antes de começar

Se quiser garantir um pool grande de vídeos antes de gerar:

```bash
python gerar_videos.py --forcar-download
```

Ou baixar manualmente com mais controle:

```bash
python baixar_videos_flores.py --query "natureza" --max-pages 10
```

---

### Gerar sem baixar vídeos (apenas o que já tem localmente)

```bash
python gerar_videos.py --sem-download
```

Se o pool de clipes se esgotar, o script para e avisa — sem tentar acessar a internet.

---

## Gerador de Coletâneas

Após gerar todos os hinos individuais de um projeto, você pode agrupá-los em coletâneas (vídeos longos compilados por temas) prontas para publicação no YouTube.

Para rodar o gerador de coletâneas:

```bash
python gerar_coletaneas.py --projeto hinos_de_ninar
```

Flags opcionais:
* `--forcar`: Força a regeração das capas e a concatenação dos vídeos, mesmo que os arquivos correspondentes já existam.

### Como funciona:
1. **Definições**: O script possui 10 coletâneas temáticas pré-definidas (Ex: *Oração e Comunhão*, *Esperança e Vida Eterna*, *Louvor e Gratidão*, etc.).
2. **Criação de Pastas**: Cada coletânea é criada dentro de uma pasta própria no diretório `output/coletaneas/` (ex: `output/coletaneas/01 - Coletânea de Oração e Comunhão/`).
3. **Capa Personalizada (`capa.png`)**: O script usa a imagem de base do projeto (especificada no `projetos.json`) e escreve o nome da coletânea no local do número (com quebra de linha dinâmica), adicionando a lista dos hinos participantes logo abaixo.
4. **Concatenação Lossless**: Une os vídeos individuais em um único arquivo de vídeo longo (ex: `Coletânea de Oração e Comunhão.mp4`) utilizando o concat demuxer do FFmpeg. Como todos os vídeos possuem o mesmo codec e dimensões, o merge é feito sem re-codificação, finalizando em segundos sem perda de qualidade.
5. **Timeline e Capítulos (`capitulos.txt`)**: O script calcula dinamicamente o ponto de início (timeline) de cada hino dentro do vídeo longo, gerando um arquivo contendo a minutagem exata.
6. **Metadados (`info.md`)**: Produz um arquivo Markdown contendo:
   - **Título** ideal para o YouTube.
   - **Descrição** pronta contendo as informações das coletâneas e os capítulos já formatados para o YouTube gerar a linha do tempo clicável automaticamente.
   - **Tags** temáticas consolidadas que respeitam o limite máximo de 400 caracteres.

---

## Painel Administrativo Web

O projeto conta com um painel administrativo baseado em Flask para visualizar o progresso de geração de vídeos e gerenciar as postagens/metadados.

### Como Iniciar no Terminal

1. **Ative o ambiente virtual** local (instalado na raiz do projeto):
   * Se você estiver na raiz do projeto:
     ```bash
     source .venv/bin/activate
     cd admin
     ```
   * Se você já estiver dentro da pasta `admin/`:
     ```bash
     source ../.venv/bin/activate
     ```
2. **Instale o Flask** (caso não esteja instalado no ambiente virtual):
   ```bash
   pip install flask
   ```
3. **Execute o aplicativo**:
   ```bash
   python app.py
   ```
4. **Acesse no navegador**: [http://localhost:5000](http://localhost:5000)

---

## Resultado

| Arquivo | Descrição |
|---|---|
| `output/hino_001.mp4` | Vídeos gerados, um por hino |
| `videos_gerados.md` | Títulos, descrições e tags prontos para o YouTube |
| `progresso.db` | Banco SQLite com o estado completo do processo |

---

## Estrutura do Projeto

```
hinário/
├── mp3/                        ← coloque aqui os áudios dos hinos
├── videos_flores/              ← vídeos de fundo (baixados automaticamente)
│   └── _baixados.json          ← índice de downloads já feitos
├── Photos-1-001/               ← vídeos extras para composição
├── images/
│   ├── sem-numero.png          ← frame base (sem número)
│   └── com-numero.png          ← modelo de referência (não é gerado pelo script)
├── fontes/
│   └── hinario4_sequential.csv ← nomes dos hinos (Número, Nome)
├── thumbs/                     ← thumbnails PNG para upload no YouTube (geradas automaticamente)
│   ├── hino_001.png
│   └── ...
├── output/                     ← vídeos gerados
├── videos_gerados.md           ← metadados para YouTube
├── progresso.db                ← banco de controle (gerado automaticamente)
├── baixar_videos_flores.py     ← script de download de vídeos de fundo
├── gerar_videos.py             ← script principal ← EXECUTE ESTE
└── README.md                   ← este arquivo
```

---

## Referência Rápida de Flags

| Comando | O que faz |
|---|---|
| `python gerar_videos.py` | Gera tudo / continua de onde parou |
| `python gerar_videos.py --projeto hinario4` | Executa o gerador para o projeto `hinario4` |
| `python gerar_videos.py --projeto hinario5` | Executa o gerador para o projeto `hinario5` |
| `python gerar_videos.py --apenas 290` | Gera somente o hino 290 do projeto selecionado |
| `python gerar_videos.py --apenas-imagem` | Gera apenas a miniatura (thumbnail) de todos os hinos do projeto selecionado, sem renderizar o vídeo |
| `python gerar_videos.py --projeto hinario4 --apenas 5 --apenas-imagem` | Gera apenas a miniatura do hino 5 do projeto `hinario4` (excelente para testar layout de texto) |
| `python gerar_videos.py --forcar-inicio 100` | Começa a partir do hino 100 |
| `python gerar_videos.py --resetar 290` | Marca o hino 290 para regerar |
| `python gerar_videos.py --resetar-todos` | Marca tudo para regerar do zero |
| `python gerar_videos.py --forcar-download` | Baixa novos clipes antes de começar |
| `python gerar_videos.py --sem-download` | Nunca acessa a internet |


# Comandos mais usados
cd ~/work/hinário/
source .venv/bin/activate
python gerar_videos.py --projeto hinos_de_ninar

# Admin
source .venv/bin/activate
cd admin
python app.py