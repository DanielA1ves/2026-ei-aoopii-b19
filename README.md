# Projeto Music + Speech

Autores:
- Luis Flores, n.º 31442
- Daniel Alves, n.º 31383

## Estado atual

O projeto ja tem implementada a componente base de backend em Python para geracao de audio. Neste momento, o sistema consegue:

- gerar instrumental a partir de prompts com `MusicGen`
- gerar musica por API externa com `deAPI.ai`
- gerar voz com `Piper`, `XTTS v2` ou `Bark`
- devolver audio apenas de musica
- devolver audio apenas de voz
- devolver uma mistura final de musica com voz
- expor tudo atraves de uma API `FastAPI`

O repositorio inclui tambem uma app React simples para escolher o modo e pedir a geracao ao backend.

## Estrutura atual

```text
src/
  python_service/
    main.py
    README.md
    requirements.txt
    outputs/
  react_app/
    src/
    package.json
```

## Componente ja concluida

### Backend Python

A pasta `src/python_service` contem o servico principal do projeto. Essa componente ja inclui:

- endpoint para gerar apenas musica
- endpoint para gerar musica com voz
- suporte a diferentes motores de voz
- escolha entre geracao local (`MusicGen`) e geracao via `deAPI.ai`
- controlo de mistura entre instrumental e voz
- armazenamento local dos ficheiros `.wav` gerados

Documentacao tecnica do backend:

- [README do servico Python](src/python_service/README.md)

## Proximos passos

- melhorar a experiencia de utilizacao da geracao de audio
- continuar a afinar a qualidade da voz ritmada

## Execucao atual

Neste momento, o projeto pode correr com backend Python e frontend React.

Para correr essa componente, consultar:

- [src/python_service/README.md](src/python_service/README.md)

## deAPI.ai

Para gerar musica via deAPI.ai:

1. criar uma chave em `https://app.deapi.ai/settings/api-keys`
2. criar um ficheiro `.env` na raiz com base em `.env.example`
3. definir `DEAPI_API_KEY`
4. usar `music_provider: "deapi"` nos pedidos da API ou escolher `deAPI` no frontend

Sem `DEAPI_API_KEY`, o modo local continua a funcionar normalmente.
