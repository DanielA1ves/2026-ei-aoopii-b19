# Serviço Python MusicGen

Serviço local em FastAPI para gerar música a partir de um prompt textual usando o modelo `facebook/musicgen-small`.

## Estrutura

```text
src/
  python_service/
    main.py
    requirements.txt
    outputs/
```

## Funcionamento

O serviço carrega o modelo MusicGen no arranque da aplicação. Quando recebe um prompt, gera um ficheiro `.wav`, guarda-o na pasta `outputs/` e devolve o nome do ficheiro juntamente com a URL para reprodução.

O modelo é executado localmente. Na primeira execução, os ficheiros do modelo são descarregados e ficam guardados em cache no computador.

## Requisitos

- Python 3.10 ou 3.11
- Ligação à internet na primeira execução, para descarregar o modelo
- GPU NVIDIA com CUDA é opcional, mas recomendada para melhor desempenho

Se não existir GPU disponível, o serviço usa CPU automaticamente.

## Instalação

No directório `src/python_service`:

```powershell
python -m venv .venv
.venv\Scripts\Activate.ps1
python -m pip install --upgrade pip setuptools wheel
pip install -r requirements.txt
```

## Execução

```powershell
python -m uvicorn main:app --reload --port 8000
```

Depois de arrancar, a API fica disponível em:

```text
http://localhost:8000
```

A documentação automática do FastAPI fica disponível em:

```text
http://localhost:8000/docs
```

## Endpoints

### `GET /health`

Verifica se o serviço está activo.

Resposta:

```json
{
  "status": "ok"
}
```

### `POST /generate`

Gera música a partir de um prompt.

Pedido:

```json
{
  "prompt": "sad jazz for 3am"
}
```

Resposta:

```json
{
  "file": "abc123.wav",
  "audio_url": "http://localhost:8000/audio/abc123.wav"
}
```

### `GET /audio/{file_name}`

Devolve o ficheiro de áudio gerado.

Exemplo:

```text
http://localhost:8000/audio/abc123.wav
```

## Teste no PowerShell

```powershell
Invoke-RestMethod -Method POST http://localhost:8000/generate `
  -ContentType "application/json" `
  -Body '{"prompt":"sad jazz for 3am"}'
```

## Configuração

As principais configurações estão no ficheiro `main.py`:

```python
MODEL_NAME = "facebook/musicgen-small"
MAX_NEW_TOKENS = 256
```

`MODEL_NAME` define o modelo usado para gerar música.

`MAX_NEW_TOKENS` controla aproximadamente a duração do áudio. Um valor maior gera áudio mais longo, mas também aumenta o tempo de processamento e o consumo de memória.

Exemplos:

```python
MAX_NEW_TOKENS = 256
MAX_NEW_TOKENS = 512
```

## Notas

- A primeira geração pode demorar mais porque o modelo precisa de ser carregado.
- Os ficheiros `.wav` gerados ficam na pasta `outputs/`.
- Em CPU, a geração pode ser lenta.
- Se o comando `uvicorn` não for reconhecido, usar sempre `python -m uvicorn main:app --reload --port 8000`.
