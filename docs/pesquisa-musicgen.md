# Pesquisa Técnica sobre o MusicGen

## Introdução

MusicGen é um modelo de geração musical desenvolvido pela Meta para a tarefa de text-to-music. O modelo foi apresentado no trabalho "Simple and Controllable Music Generation" e faz parte do ecossistema AudioCraft, uma biblioteca focada na geração e no processamento de áudio com deep learning.

Para este projeto, o MusicGen é especialmente relevante porque permite gerar música original a partir de descrições textuais como:

```text
sad jazz for 3am
```

Isto encaixa diretamente no enunciado do sistema de composição musical.

## O que é o MusicGen

De acordo com a documentação oficial e com o artigo original, o MusicGen é um modelo auto-regressivo de uma única etapa, desenhado para gerar música condicionada por texto e, em algumas variantes, também por melodia.

Em termos simples:

- o utilizador fornece um prompt textual
- o modelo converte esse prompt em representações internas
- o sistema gera tokens discretos de áudio
- esses tokens são descodificados na forma de onda final

O resultado é um ficheiro de áudio que pode ser reproduzido diretamente.

## Como Funciona a Nível Geral

O MusicGen combina três ideias principais:

1. Um codificador textual para interpretar a descrição escrita
2. Um modelo generativo auto-regressivo para prever tokens de áudio
3. Um codec de áudio, como o EnCodec, para reconstruir a waveform final

Segundo o artigo original, uma das contribuições principais do MusicGen é evitar uma arquitetura em cascata com vários modelos separados. Em vez disso, usa um modelo único com um padrão eficiente de interleaving de tokens, o que simplifica a geração e melhora a eficiência.

## Relação com o AudioCraft

O AudioCraft é a biblioteca da Meta onde o MusicGen está integrado. O repositório oficial descreve o AudioCraft como uma biblioteca PyTorch para investigação e inferência em geração de áudio, contendo modelos como:

- MusicGen
- AudioGen
- EnCodec
- MAGNeT
- MusicGen Style

Isto significa que o MusicGen não aparece isolado, mas como parte de um conjunto mais amplo de ferramentas de áudio generativo.

## Variantes Disponíveis

A documentação oficial do AudioCraft lista várias versões pré-treinadas do MusicGen:

- `facebook/musicgen-small`
- `facebook/musicgen-medium`
- `facebook/musicgen-large`
- `facebook/musicgen-melody`
- variantes estéreo

Em termos práticos:

- `small` exige menos recursos e é mais adequada para protótipos
- `medium` oferece um melhor equilíbrio entre qualidade e custo computacional
- `large` pode produzir melhores resultados, mas exige mais memória e mais tempo
- `melody` permite condicionar a geração com uma melodia de entrada

Para um projeto académico local, a variante `musicgen-small` costuma ser a escolha mais segura para começar.

## Capacidades do MusicGen

O MusicGen permite:

- geração de música a partir de texto
- geração condicionada por melodia em algumas variantes
- execução local, sem depender de uma API externa
- controlo por descrição textual de ambiente, estilo e instrumentação

Exemplos de prompts:

- `happy rock with electric guitar and energetic drums`
- `sad jazz for 3am`
- `ambient piano with soft rain and calm mood`

## Porque é Adequado para Este Projeto

O MusicGen encaixa bem no trabalho por várias razões:

- resolve diretamente o problema de text-to-music
- tem implementação em Python fácil de integrar com FastAPI
- pode correr localmente
- permite demonstrar um fluxo completo de geração musical
- aproxima-se do exemplo dado no enunciado

Em vez de construir um sistema mais complexo com LLM + MIDI + sintetizador, o MusicGen oferece uma via mais direta para obter uma demonstração funcional.

## Vantagens

As principais vantagens do MusicGen para este tipo de projeto são:

- facilidade de integração
- geração de música original a partir de linguagem natural
- suporte oficial através do AudioCraft
- existência de variantes com diferentes níveis de custo computacional
- boa adequação para demonstrações locais e protótipos académicos

## Limitações

Apesar de ser uma opção forte, o MusicGen tem limites importantes:

- a geração pode ser lenta em hardware modesto
- a execução local é mais indicada com GPU
- a qualidade pode variar conforme o prompt
- o controlo musical ainda é mais limitado do que em composição simbólica com MIDI
- as durações longas aumentam bastante o custo computacional

Segundo a documentação do AudioCraft, a utilização local do MusicGen requer GPU, sendo recomendados 16 GB de memória para uma experiência mais confortável. GPUs menores podem, ainda assim, gerar sequências curtas, especialmente com `musicgen-small`.

## Requisitos Técnicos

No ecossistema oficial, o MusicGen é usado sobre PyTorch e AudioCraft. A documentação oficial do AudioCraft indica:

- Python 3.9
- PyTorch
- instalação da biblioteca `audiocraft`
- `ffmpeg` recomendado em alguns cenários

Para este projeto, o essencial será:

- FastAPI para a API Python
- AudioCraft para carregar o modelo
- torchaudio para guardar ou manipular o áudio

## Considerações de Licenciamento

O repositório AudioCraft indica que:

- o código está sob licença MIT
- os pesos dos modelos estão sob CC-BY-NC 4.0

Isto é importante porque, para contexto académico e demonstração, normalmente não há problema. No entanto, para uso comercial, esta parte deve ser verificada com cuidado.

## Conclusão

O MusicGen é uma tecnologia muito adequada para um projeto de composição musical. Permite transformar descrições textuais em música gerada automaticamente, com uma integração relativamente simples em Python. Para um protótipo funcional, a combinação de React, uma API e um serviço Python com MusicGen oferece uma solução clara, demonstrável e tecnicamente consistente.

## Fontes

- Artigo original: https://arxiv.org/abs/2306.05284
- Repositório oficial AudioCraft: https://github.com/facebookresearch/audiocraft
- Documentação MusicGen no AudioCraft: https://github.com/facebookresearch/audiocraft/blob/main/docs/MUSICGEN.md
- Documentação Hugging Face para MusicGen: https://huggingface.co/docs/transformers/en/model_doc/musicgen
