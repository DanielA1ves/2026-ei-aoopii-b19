# Mc Mozart

## Plataforma de Geração Musical com Inteligência Artificial

O Mc Mozart é uma plataforma baseada em Inteligência Artificial capaz de gerar músicas completas automaticamente a partir de prompts textuais fornecidos pelo utilizador.

O sistema combina vários modelos de IA e ferramentas de processamento áudio para gerar:
- letras
- instrumentais
- vocais
- músicas finais em formato MP3

O objetivo principal deste projeto é demonstrar a integração de modelos generativos de IA numa pipeline completa de geração musical automatizada.

---

# Objetivo

Esta arquitetura tem como objetivo permitir que um utilizador introduza um prompt textual ou selecione parâmetros estruturados, como:
- ambiente
- género musical
- instrumentos
- ritmo

e receba como resposta uma música original gerada automaticamente através de Inteligência Artificial.

O sistema pretende automatizar:
- geração de prompts
- geração instrumental
- geração vocal
- processamento de áudio
- exportação final da música

---

# Visão Geral da Arquitetura

A arquitetura proposta organiza-se em quatro componentes principais:

1. Frontend em React
2. API intermédia em Node.js
3. Serviço de IA em Python com FastAPI
4. Sistema de processamento e fusão de áudio

Esta separação permite criar uma aplicação:
- modular
- organizada
- escalável
- preparada para evolução futura

---

# Diagrama Lógico

```text
Frontend React
     |
     v
API Node.js
     |
     v
Serviço Python + FastAPI
     |
     +-------------------+
     |                   |
     v                   v
MusicGen             Modelo Vocal AI
     |                   |
     +---------+---------+
               |
               v
FFmpeg / pydub
               |
               v
Ficheiro MP3 Final
```

---

# Papel de Cada Camada

## 1. Frontend em React

O frontend é responsável pela interação com o utilizador.

As suas funções incluem:
- recolher prompts
- permitir seleção de ambiente
- permitir seleção de género musical
- apresentar estados de carregamento
- reproduzir o áudio final
- permitir download da música

---

# Exemplos de Dados Introduzidos

## Prompt Livre

```text
sad jazz for 3am
```

---

## Campos Estruturados

- ambiente: sad
- género: jazz
- instrumentos: soft piano
- ritmo: slow tempo

O frontend pode construir automaticamente um prompt final:

```text
sad jazz for 3am, soft piano, slow tempo, intimate atmosphere
```

---

## 2. API em Node.js

O Node.js funciona como camada intermédia entre o frontend e os serviços de IA.

As suas responsabilidades incluem:
- receber pedidos do frontend
- validar dados
- normalizar prompts
- encaminhar pedidos para o serviço Python
- centralizar tratamento de erros
- gerir futuras funcionalidades

---

# Funcionalidades Futuras Possíveis

Esta camada permite adicionar:
- autenticação
- sistema de utilizadores
- histórico de gerações
- limitação de pedidos
- cache
- análise de utilização
- logging

---

## 3. Serviço Python com FastAPI

O serviço Python é responsável pela execução dos modelos de Inteligência Artificial.

As suas funções incluem:
- receber prompts
- executar o MusicGen
- gerar instrumentais
- gerar vocais através de modelos de voz
- guardar ficheiros temporários
- devolver URLs dos ficheiros gerados

---

# MusicGen

O MusicGen é utilizado para gerar:
- instrumentais
- ambientes sonoros
- batidas
- melodias

A geração é feita a partir de prompts textuais fornecidos pelo utilizador.

---

# Modelo Vocal de IA

Além do instrumental, o sistema pode utilizar modelos vocais como:
- Bark
- RVC

Estes modelos convertem texto em voz cantada ou vocais sintéticos.

---

## 4. Processamento de Áudio

Após a geração do instrumental e dos vocais, o sistema utiliza:
- FFmpeg
- pydub

para:
- juntar faixas de áudio
- ajustar volumes
- converter formatos
- exportar MP3 final

---

# Fluxo Completo do Pedido

1. O utilizador introduz um prompt no frontend.
2. O React envia um POST para a API Node.js.
3. A API Node valida e normaliza o pedido.
4. O pedido é enviado para o serviço Python.
5. O MusicGen gera o instrumental.
6. O modelo vocal gera os vocais.
7. O FFmpeg ou pydub junta todas as faixas.
8. O sistema exporta um ficheiro MP3 final.
9. O Node.js devolve ao frontend a URL do ficheiro.
10. O frontend reproduz a música gerada.

---

# Exemplo de Endpoints

## Endpoint Node.js

```http
POST /api/generate
```

Pedido:

```json
{
  "prompt": "sad jazz for 3am"
}
```

Resposta:

```json
{
  "audioUrl": "http://localhost:8000/generated/song123.mp3"
}
```

---

## Endpoint Python

```http
POST /generate
```

Pedido:

```json
{
  "prompt": "sad jazz for 3am"
}
```

Resposta:

```json
{
  "file": "song123.mp3"
}
```

---

# Estratégia de Construção de Prompts

A qualidade da música gerada depende diretamente da qualidade do prompt enviado ao MusicGen.

Prompts mais detalhados produzem resultados mais coerentes e interessantes.

---

# Exemplos de Prompts

## Prompts Simples

```text
sad jazz for 3am
```

```text
relaxing lo-fi study music
```

```text
dark cinematic orchestral soundtrack
```

---

## Prompts Estruturados

```text
sad jazz for 3am, soft piano, slow tempo, intimate atmosphere
```

```text
retro synthwave, 1980s vibe, neon atmosphere, driving bassline
```

```text
melancholic Portuguese guitar, emotional atmosphere, slow rhythm
```

---

# Categorias Possíveis de Prompt

## Ambientes
- sad
- happy
- cinematic
- emotional
- aggressive
- relaxing

## Géneros
- jazz
- trap
- lo-fi
- synthwave
- orchestral
- ambient

## Instrumentos
- piano
- violin
- electric guitar
- drums
- synthesizer

## Ritmos
- slow tempo
- energetic beat
- calm rhythm
- fast tempo

---

# Porque Utilizar Node.js Entre React e Python

A utilização de uma API intermédia em Node.js traz várias vantagens:

- separação clara de responsabilidades
- maior modularidade
- melhor controlo dos pedidos
- isolamento do serviço de IA
- facilidade de manutenção
- possibilidade de trocar o motor de IA futuramente

---

# Estrutura Recomendada do Projeto

```text
project/
│
├── frontend/
│   ├── src/
│   └── public/
│
├── backend-node/
│   ├── routes/
│   ├── controllers/
│   └── services/
│
├── ai-service/
│   ├── app.py
│   ├── musicgen_service.py
│   ├── vocal_service.py
│   ├── audio_merge.py
│   └── outputs/
│
├── docker-compose.yml
├── README.md
└── .gitignore
```

---

# Tecnologias Utilizadas

## Frontend
- React
- Tailwind CSS

## Backend
- Node.js
- Express
- Python
- FastAPI

## Inteligência Artificial
- MusicGen
- Bark
- RVC

## Processamento de Áudio
- FFmpeg
- pydub

## Infraestrutura
- Docker
- Docker Compose

---

# Alternativa Mais Simples

Caso o objetivo seja apenas um protótipo rápido, também é possível utilizar uma arquitetura reduzida:

```text
React -> FastAPI -> MusicGen
```

Esta abordagem reduz a complexidade, mas oferece menos modularidade e menos capacidade de expansão.

---

# Recomendação para o Projeto

Para um projeto académico, a estratégia recomendada é:

1. começar por uma versão funcional simples
2. introduzir modularidade gradualmente
3. adicionar a API Node.js como camada intermédia
4. automatizar completamente o processamento de áudio

---

# Limitações

Por utilizar modelos gratuitos e open-source:
- a qualidade vocal pode variar
- a sincronização pode não ser perfeita
- o tempo de geração depende do hardware
- a qualidade pode não atingir níveis comerciais

---

# Melhorias Futuras

Possíveis melhorias futuras:
- melhor sincronização vocal
- modelos especializados por género
- sistema de masterização automática
- geração em tempo real
- sistema de utilizadores
- playlists automáticas
- personalização avançada

---

# Conclusão

O MusicGen encaixa naturalmente numa arquitetura baseada em serviços. O frontend gere a experiência do utilizador, o Node.js atua como camada de integração e o Python executa os modelos de Inteligência Artificial.

A utilização de ferramentas como FFmpeg e pydub permite automatizar a fusão das faixas de áudio e produzir uma música final totalmente gerada por IA.

Esta separação torna o sistema:
- modular
- escalável
- organizado
- mais próximo de arquiteturas modernas utilizadas em aplicações reais de Inteligência Artificial.