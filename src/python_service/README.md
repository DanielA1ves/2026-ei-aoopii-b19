# Servico Python de Musica e Voz

Servico local em FastAPI para:

- gerar instrumental com `facebook/musicgen-small`
- gerar musica com `deAPI.ai` atraves de uma chave de API
- gerar voz com `Piper`, `XTTS v2` ou `Bark`
- misturar voz e musica no backend
- exportar a musica final em MP3

O endpoint antigo de musica continua disponivel, agora com escolha entre `music_provider: "local"` e `music_provider: "deapi"`.

## Estrutura

```text
src/
  python_service/
    main.py
    requirements.txt
    outputs/
```

As vozes `Piper` nao precisam de existir dentro do repositorio. O backend descarrega e guarda essas vozes automaticamente em cache local no Windows, em `C:\Users\<utilizador>\AppData\Local\music_speech_service\piper_voices`.

## Requisitos

- Python 3.10 ou 3.11 para usar `XTTS`
- Python 3.13 continua a servir para `MusicGen` e `Bark`, mas `XTTS` nao instala nesse ambiente
- ligacao a internet na primeira execucao para descarregar os modelos
- GPU NVIDIA com CUDA e opcional, mas ajuda bastante
- FFmpeg instalado e disponivel no PATH para exportar MP3 com `pydub`
- chave `DEAPI_API_KEY` se quiserem gerar musica via deAPI.ai
- No Windows, o `XTTS` pode precisar de `Microsoft Visual C++ Build Tools` para compilar a dependencia `TTS`
- `Piper` funciona localmente e e a opcao recomendada para speech claro sem clonagem de voz

## Instalacao

No diretorio `src/python_service`:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

Para ativar a deAPI.ai:

```powershell
$env:DEAPI_API_KEY="a_tua_chave"
```

A chave pode ser criada em `https://app.deapi.ai/settings/api-keys`.

Variaveis opcionais:

```powershell
$env:DEAPI_MUSIC_MODEL="ACE-Step-v1.5-turbo"
$env:DEAPI_MUSIC_FORMAT="wav"
```

Se quiserem a melhor qualidade para voz em portugues, usem mesmo um ambiente com Python `3.10` ou `3.11`.

Se a instalacao falhar em `TTS` com erro sobre `Microsoft Visual C++ 14.0 or greater is required`, instalem primeiro:

```powershell
winget install --id Microsoft.VisualStudio.2022.BuildTools -e
```

Depois abram o instalador e ativem pelo menos a workload:

- `Desktop development with C++`

## Execucao

```powershell
python -m uvicorn main:app --reload --port 8000
```

Depois de arrancar:

- API: `http://localhost:8000`
- Docs Swagger: `http://localhost:8000/docs`

## Endpoints

### `GET /health`

Resposta:

```json
{
  "status": "ok"
}
```

### `POST /generate`

Gera apenas musica.

Pedido:

```json
{
  "prompt": "sad jazz for 3am",
  "duration_seconds": 8,
  "music_provider": "local"
}
```

`duration_seconds` e opcional. No modo local aceita ate 20 segundos. No modo `deapi` aceita duracoes maiores, dentro dos limites do modelo da deAPI.

Pedido via deAPI:

```json
{
  "prompt": "upbeat electronic dance music with energetic synths",
  "duration_seconds": 30,
  "music_provider": "deapi",
  "deapi_lyrics": "[Instrumental]"
}
```

### `POST /generate-with-speech`

Gera instrumental, gera voz e devolve tambem a mistura final.

Pedido minimo:

```json
{
  "music_prompt": "old school hip hop beat with warm bass and soft piano",
  "lyrics": "Este projeto junta musica e voz geradas localmente.",
  "duration_seconds": 8,
  "music_provider": "local",
  "speech_engine": "piper",
  "vocal_delivery": "rhythmic",
  "language": "pt-PT"
}
```

Para usar a deAPI apenas como instrumental de fundo e manter a voz local:

```json
{
  "music_prompt": "warm boom bap beat with soft keys",
  "lyrics": "Entramos na batida com voz gerada localmente.",
  "duration_seconds": 30,
  "music_provider": "deapi",
  "speech_engine": "piper",
  "language": "pt-PT"
}
```

Para tentar vocals mais ritmados ou cantados, usem `speech_engine: "bark"` com `vocal_delivery: "rhythmic"` ou `"singing"`. A qualidade pode variar bastante.

Pedido com controlo de voz:

```json
{
  "music_prompt": "cinematic ambient beat with soft drums",
  "lyrics": "Bem-vindo a demonstracao do nosso projeto.",
  "speech_engine": "xtts",
  "language": "pt",
  "speaker_name": "Ana Florence",
  "music_gain_db": -3,
  "speech_gain_db": 4
}
```

Nota: no estado atual do `XTTS`, as vozes embutidas podem soar mal em portugues. Para resultados realmente inteligiveis, usem `speaker_wav_path`.

Pedido recomendado para voz clara local com Piper:

```json
{
  "music_prompt": "old school hip hop beat with warm bass and soft piano",
  "lyrics": "Este projeto junta musica e voz geradas localmente.",
  "speech_engine": "piper",
  "vocal_delivery": "rhythmic",
  "language": "pt-PT",
  "piper_length_scale": 1.0,
  "piper_noise_scale": 0.667,
  "piper_noise_w_scale": 0.8,
  "music_gain_db": -4,
  "speech_gain_db": 4
}
```

Pedido com delivery ritmico mais limpo usando Bark:

```json
{
  "music_prompt": "warm boom bap beat with soft keys",
  "lyrics": "Entramos na batida\nfalamos por cima do groove\ncom mais clareza",
  "speech_engine": "bark",
  "vocal_style": "chant",
  "music_gain_db": -3,
  "speech_gain_db": 3
}
```

Pedido com portugues do Brasil:

```json
{
  "music_prompt": "beat trap suave com pads escuros",
  "lyrics": "Agora a voz sai em portugues do Brasil.",
  "speech_engine": "piper",
  "language": "pt-BR"
}
```

Pedido com ingles dos Estados Unidos:

```json
{
  "music_prompt": "uplifting pop instrumental with clean drums",
  "lyrics": "This project can now speak with a U.S. English Piper voice.",
  "speech_engine": "piper",
  "language": "en-US"
}
```

Pedido com clonagem de voz local:

```json
{
  "music_prompt": "relaxed lo fi beat",
  "lyrics": "Esta voz foi sintetizada a partir de uma referencia.",
  "speech_engine": "xtts",
  "vocal_delivery": "rhythmic",
  "language": "pt",
  "speaker_wav_path": "samples/minha_voz.wav"
}
```

Resposta:

```json
{
  "file": "abc123.mp3",
  "audio_url": "http://localhost:8000/audio/abc123.mp3",
  "music_file": "abc123-music.wav",
  "music_url": "http://localhost:8000/audio/abc123-music.wav",
  "speech_file": "abc123-vocal.wav",
  "speech_url": "http://localhost:8000/audio/abc123-vocal.wav",
  "mixed_wav_file": "abc123-mix.wav",
  "mixed_wav_url": "http://localhost:8000/audio/abc123-mix.wav",
  "speech_engine": "xtts",
  "music_provider": "local",
  "deapi_request_id": null,
  "speaker_name": "Ana Florence",
  "speaker_wav_path": null
}
```

### `GET /deapi/models`

Lista modelos de musica disponiveis na deAPI para escolher um `deapi_model`.

### `GET /deapi/balance`

Consulta o saldo da conta deAPI configurada em `DEAPI_API_KEY`.

### `GET /audio/{file_name}`

Devolve qualquer ficheiro `.wav` gerado pelo servico.

## Motores de voz

### `xtts`

- melhor opcao para portugues
- suporta clonagem de voz com `speaker_wav_path`
- para portugues, a opcao recomendada e usar uma referencia real em `speaker_wav_path`
- requer Python 3.10 ou 3.11

### `piper`

- opcao recomendada para speech local claro sem gravacao de referencia
- descarrega uma voz local na primeira utilizacao
- por defeito usa `pt_PT-tugão-medium` quando `language` e `pt` ou `pt-PT`
- usa `pt_BR-faber-medium` quando `language` e `pt-BR`
- usa `en_US-lessac-medium` quando `language` e `en` ou `en-US`
- continua a suportar outras vozes Piper com `piper_voice`
- o backend faz o download da voz `pt_PT-tugão-medium` corretamente, apesar do `ã` no nome
- tambem aceita o alias ASCII `pt_PT-tugao-medium` se preferirem evitar acentos no codigo

### `bark`

- opcao experimental para vocals mais expressivos
- pode ser pedido com `"speech_engine": "bark"`
- modos de lyrics disponiveis: `"speech"` e `"chant"`
- `"speech"` e o modo mais estavel
- `"chant"` tenta um delivery ritmico mais fluido mantendo inteligibilidade
- para melhor qualidade no modo `chant`, escrevam a letra em linhas curtas
- se nao for indicado `speaker_name`, o backend usa um preset `v2` por defeito conforme o idioma
- para canto verdadeiro, o ideal e trocar para um modelo especifico de singing voice
- pode usar `"vocal_delivery": "rhythmic"` ou `"singing"`
- nao garante canto afinado nem sincronizado, mas tende a soar menos lido do que `Piper`

## Notas de implementacao

- O `MusicGen` e carregado no arranque.
- A deAPI e usada apenas quando o pedido tem `music_provider: "deapi"`.
- `XTTS` e `Bark` sao carregados apenas quando usados.
- `Piper` descarrega a voz na primeira utilizacao e depois fica em cache local.
- A geracao e feita de forma sequencial para evitar conflitos de GPU e picos de memoria.
- A mistura final e feita em `audio_merge.py` com reamostragem, controlo de ganho e exportacao MP3 via `pydub`/FFmpeg.
- Se a voz for maior do que a musica, o instrumental e repetido para evitar silencio no fim.

## Testes rapidos no PowerShell

Gerar apenas musica:

```powershell
Invoke-RestMethod -Method POST http://localhost:8000/generate `
  -ContentType "application/json" `
  -Body '{"prompt":"sad jazz for 3am","duration_seconds":8}'
```

Gerar musica com voz:

```powershell
Invoke-RestMethod -Method POST http://localhost:8000/generate-with-speech `
  -ContentType "application/json" `
  -Body '{"music_prompt":"old school hip hop beat","lyrics":"Esta e uma demo com voz por cima da batida.","duration_seconds":8,"speech_engine":"piper","language":"pt-PT"}'
```

Gerar musica com voz em ingles dos Estados Unidos:

```powershell
Invoke-RestMethod -Method POST http://localhost:8000/generate-with-speech `
  -ContentType "application/json" `
  -Body '{"music_prompt":"uplifting pop beat","lyrics":"This is a demo with a U.S. English voice.","speech_engine":"piper","language":"en-US"}'
```

Tentar vocals cantados com Bark:

```powershell
Invoke-RestMethod -Method POST http://localhost:8000/generate-with-speech `
  -ContentType "application/json" `
  -Body '{"music_prompt":"Brazilian pagode instrumental backing track with cavaquinho, pandeiro and tantan, space for singing vocals","lyrics":"Hoje eu quero cantar, sentir o samba no ar, deixar o coracao falar, e a alegria chegar","duration_seconds":12,"speech_engine":"bark","vocal_delivery":"singing","language":"pt-PT","music_gain_db":-12,"speech_gain_db":7}'
```

Usar XTTS com referencia de voz:

```powershell
Invoke-RestMethod -Method POST http://localhost:8000/generate-with-speech `
  -ContentType "application/json" `
  -Body '{"music_prompt":"ambient electronic track","lyrics":"Clonagem de voz com XTTS.","speech_engine":"xtts","language":"pt","speaker_wav_path":"samples/minha_voz.wav"}'
```
