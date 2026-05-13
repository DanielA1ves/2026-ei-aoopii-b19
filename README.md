# Projeto Music + Speech

Autores:
- Luis Flores, n.º 31442
- Daniel Alves, n.º 31383

## Estado atual

O projeto ja tem implementada a componente base de backend em Python para geracao de audio. Neste momento, o sistema consegue:

- gerar instrumental a partir de prompts com `MusicGen`
- gerar voz com `Piper`, `XTTS v2` ou `Bark`
- devolver audio apenas de musica
- devolver audio apenas de voz
- devolver uma mistura final de musica com voz
- expor tudo atraves de uma API `FastAPI`

Neste momento, a parte de frontend ainda nao foi adicionada ao repositorio.

## Estrutura atual

```text
src/
  python_service/
    main.py
    README.md
    requirements.txt
    outputs/
```

## Componente ja concluida

### Backend Python

A pasta `src/python_service` contem o servico principal do projeto. Essa componente ja inclui:

- endpoint para gerar apenas musica
- endpoint para gerar musica com voz
- suporte a diferentes motores de voz
- controlo de mistura entre instrumental e voz
- armazenamento local dos ficheiros `.wav` gerados

Documentacao tecnica do backend:

- [README do servico Python](src/python_service/README.md)

## Proximos passos

- adicionar frontend ao projeto
- ligar frontend ao backend existente
- melhorar a experiencia de utilizacao da geracao de audio
- continuar a afinar a qualidade da voz ritmada

## Execucao atual

Neste momento, a parte executavel do projeto e o backend Python.

Para correr essa componente, consultar:

- [src/python_service/README.md](src/python_service/README.md)
