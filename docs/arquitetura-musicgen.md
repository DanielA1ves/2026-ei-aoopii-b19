# Arquitetura Proposta com MusicGen

## Objetivo

Esta arquitetura tem como objetivo permitir que um utilizador escreva um prompt textual, ou selecione um ambiente e um género musical, e receba como resposta uma música original gerada com MusicGen.

## Visão Geral

A arquitetura recomendada para o projeto pode ser organizada em três camadas:

1. Frontend em React
2. API intermédia em Node.js
3. Serviço de geração musical em Python com FastAPI e MusicGen

Esta abordagem separa claramente a interface, a lógica da aplicação e a execução do modelo.

## Diagrama Lógico

```text
Frontend React
     |
     v
API Node.js
     |
     v
Serviço Python + FastAPI + MusicGen
     |
     v
Ficheiros .wav gerados
```

## Papel de Cada Camada

### 1. Frontend em React

O frontend é responsável por:

- recolher o prompt do utilizador
- permitir a seleção de ambiente e género, caso essa opção seja usada
- enviar o pedido para a API
- apresentar o estado de carregamento
- reproduzir o áudio gerado

Exemplos de dados introduzidos pelo utilizador:

- prompt livre: `sad jazz for 3am`
- ambiente: `sad`
- género: `jazz`

Se forem usados campos estruturados, o frontend pode construir um prompt final, por exemplo:

```text
sad jazz for 3am, soft piano, slow tempo, intimate atmosphere
```

### 2. API em Node.js

O Node.js funciona como camada de integração entre o frontend e o serviço Python.

As responsabilidades desta camada podem ser:

- receber pedidos do frontend
- validar os dados recebidos
- normalizar prompts
- chamar o serviço Python
- devolver uma resposta simples ao frontend
- centralizar registos, tratamento de erros, autenticação ou controlo de acesso, caso o projeto evolua

Esta camada não gera música. Apenas coordena o fluxo entre a interface e o serviço Python.

### 3. Serviço Python com FastAPI e MusicGen

O serviço Python é responsável por:

- receber o prompt
- executar o modelo MusicGen
- gerar o áudio
- guardar o ficheiro `.wav`
- devolver o nome do ficheiro ou a respetiva URL

É nesta camada que ocorre a geração musical.

## Fluxo do Pedido

O fluxo recomendado é o seguinte:

1. O utilizador introduz um prompt no frontend.
2. O React envia um `POST` para a API Node.js.
3. A API Node valida o pedido e encaminha-o para o serviço Python.
4. O FastAPI chama o MusicGen para gerar o áudio.
5. O serviço Python grava o ficheiro na pasta de saídas.
6. O serviço Python devolve o nome do ficheiro gerado.
7. O Node.js devolve ao frontend uma resposta com a URL do áudio.
8. O frontend reproduz o ficheiro num elemento `<audio>`.

## Exemplo de Endpoints

### Endpoint no Node.js

```http
POST /api/generate
```

Pedido:

```json
{
  "prompt": "sad jazz for 3am"
}
```

Resposta ao frontend:

```json
{
  "audioUrl": "http://localhost:8000/abc123.wav"
}
```

### Endpoint no Python

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
  "file": "abc123.wav"
}
```

## Porque Usar um Node.js Entre React e Python

Colocar uma API em Node.js entre o frontend e o MusicGen é uma decisão válida e útil por várias razões:

- o frontend comunica apenas com uma API própria
- a lógica de validação fica centralizada
- o serviço Python fica isolado da interface
- torna-se mais fácil trocar o motor de geração no futuro
- permite adicionar funcionalidades sem mexer no frontend nem no Python

Exemplos dessas funcionalidades:

- autenticação
- limitação de pedidos
- cache
- registo de eventos
- análise de pedidos
- histórico de gerações

## Alternativa Mais Simples

Se o objetivo for apenas um protótipo rápido, também é possível usar uma arquitetura mais curta:

```text
React -> FastAPI -> MusicGen
```

Esta opção reduz a complexidade, mas oferece menos controlo e menos margem para escalar a aplicação.

## Recomendação para o Projeto

Para um trabalho académico com demonstração funcional, a melhor estratégia costuma ser:

1. começar pela versão simples e funcional
2. depois, se fizer sentido, introduzir a API Node.js como camada intermédia

Se a intenção for apresentar uma arquitetura mais organizada e próxima de um sistema real, então faz sentido usar:

```text
React -> Node.js -> FastAPI/MusicGen
```

## Conclusão

O MusicGen encaixa naturalmente numa arquitetura em serviços. O frontend trata da experiência do utilizador, o Node.js pode servir como API de integração e o Python executa o modelo de geração. Esta separação torna o sistema mais modular, mais claro e mais fácil de evoluir.
