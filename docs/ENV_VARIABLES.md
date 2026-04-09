# 🔐 Guia de Variáveis de Ambiente e Credenciais

Este arquivo mapeia todas as permissões/chaves contidas ou esperadas de existirem no ambiente root através de um arquivo local `.env` ou injetado por ambiente de VPS. 
**NOTA:** Por motivos de segurança, nenhum valor de token autêntico foi injetado aqui. Este guia serve estritamente como modelo consultivo.

---

## 🤖 1. LLM / Inteligência Artificial

```env
# GROQ (Language Model)
# Requisitado por instâncias LangChain nativas ou fluxos de conversação primária.
GROQ_API_KEY=YOUR_GROQ_KEY_HERE
```

## 🗄️ 2. Supabase (Database Primário)

```env
# URL de API pública ou interna do Supabase Project.
SUPABASE_URL=https://[YOUR_INSTANCE].supabase.co

# Chave Anônima (anon key) ou Service Role recomendada para operações Backend seguras.
SUPABASE_API_KEY=YOUR_SUPABASE_SERVICE_ROLE_KEY
```

## 📱 3. Evolution API (Motor WhatsApp)

Integração padrão com Webhooks de recepção e roteadores de pacotes WhatsApp V2.

```env
# Host IP ou Domínio Público apontando para onde o Evolution V2 Manager roda.
EVOLUTION_API_URL=http://xxx.xxx.xxx.xxx:8080

# Chave Global API injetada na inicialização do docker-compose do Evolution API.
EVOLUTION_API_KEY=YOUR_EVO_GLOBAL_KEY

# Nome exato da Instância conectada via QR Code no Postman ou Evolution Manager.
EVOLUTION_INSTANCE_ID=NomeDaInstanciaDoMedico
```

## 📧 4. E-Mail Service (Transacional)

Serviço usado para enviar logs analíticos `log_analyzer.py` ou lembretes (Opcional).
```env
EMAIL_SMTP_SERVER=smtp.gmail.com
EMAIL_SMTP_PORT=587
EMAIL_ADDRESS=clinica@gmail.com
EMAIL_PASSWORD=app_password_gerada_no_google
```

## 📅 5. Google Calendar (Opcional / Legacy)

```env
GOOGLE_API_KEY=YOUR_GCP_API_KEY
GOOGLE_CALENDAR_URL=YOUR_CAL_ENDPOINT
```

## 🔒 6. Segurança e Webhooks

```env
# Caso decida assinar JWT ou cookies internos numa dashboard do futuro.
SECRET_KEY=long_random_string_here

# Header enviado pelo Supabase Triggers para a API python, se não der match, a requisição sofre drop 401.
SUPABASE_WEBHOOK_SECRET=your_configured_webhook_password
```

---

> **⚠ Recomendação Operacional:** Se qualquer uma dessas chaves expirar (como Senhas de Aplicação do Google, ou reset de instância WhatsApp), alterne a variável no servidor local onde o `.env` se encontra (ou declare via painel web caso use Vercel/Render/Heroku/Railway) e em seguida realize Hard Restart no bot usando `screen` ou derrubando a task do Uvicorn para que Python injete elas na memória.
