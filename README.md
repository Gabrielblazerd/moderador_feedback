# 🤖 Bot de Moderação de Feedback - BLAZERD STORE

## 📋 Descrição

Este sistema monitora automaticamente o canal de feedback do Discord e usa IA (GPT-4 Vision) para classificar os feedbacks como:

- 🟢 **POSITIVO** - Feedbacks bons → Envia cupom de desconto
- 🟡 **POSSO_PERDER_CLIENTE** - Feedbacks prejudiciais mas não ofensivos → Exclui mensagem + avisa usuário
- 🔴 **NEGATIVO** - Feedbacks ofensivos → Exclui mensagem + silencia usuário + avisa

## 📁 Arquivos

| Arquivo | Descrição |
|---------|-----------|
| `feedback_moderation_bot.py` | Bot Discord completo em Python (RECOMENDADO) |
| `CANAL FEEDBACK DISCORD - COMPLETO.json` | Fluxo n8n atualizado |
| `CANAL FEEDBACK DISCORD.json` | Fluxo n8n original (backup) |
| `.env` | Variáveis de ambiente (configurações) |
| `requirements.txt` | Dependências Python |

## 🚀 Instalação (Bot Python)

### 1. Instalar dependências

```bash
pip install -r requirements.txt
```

### 2. Configurar variáveis de ambiente

Edite o arquivo `.env`:

```env
# Token do bot Discord
DISCORD_TOKEN=seu_token_aqui

# Chave da API OpenAI (GPT-4)
OPENAI_API_KEY=sk-sua-chave-aqui

# ID do líder do Discord que recebe os relatórios
LEADER_ID=

# ID do canal de feedback
FEEDBACK_CHANNEL_ID=

# ID do servidor Discord
GUILD_ID=



### 3. Executar o bot

```bash
python main.py
```

## 🔧 Funcionalidades

### ✅ Bot Python (Recomendado)
- [x] Análise de IA (GPT-4 Vision) para texto e imagens
- [x] Exclusão automática de mensagens + anexos
- [x] Silenciamento (timeout) de usuários
- [x] Mensagem de aviso personalizada para o infrator
- [x] Relatório completo para o líder do servidor
- [x] **Detecção de mensagens editadas**
- [x] Comandos administrativos (!status, !testar)

### ⚠️ Fluxo n8n
- [x] Análise de IA (GPT-4 Vision)
- [x] Exclusão de mensagens
- [x] Silenciamento via API HTTP
- [x] Mensagens de aviso
- [x] Relatório para o líder
- [ ] Detecção de mensagens editadas (não suportado nativamente)

## 📊 Classificações

### 🟢 POSITIVO
- Elogios ao produto/serviço
- Sugestões construtivas
- Imagens mostrando produto funcionando
- Frases neutras curtas

**Ação:** Envia cupom de 5% de desconto

### 🟡 POSSO_PERDER_CLIENTE
- Reclamações moderadas
- Críticas que podem afastar clientes
- Problemas técnicos reportados
- Reclamações sobre suporte

**Ação:** Exclui mensagem + Avisa usuário

### 🔴 NEGATIVO
- Ofensas diretas
- Acusações graves (scam, fraude, roubo)
- Linguagem agressiva
- Tentativa de difamação

**Ação:** Exclui mensagem + Silencia 30 min + Avisa usuário + Relatório ao líder

## 🛡️ Permissões Necessárias do Bot

O bot precisa das seguintes permissões no Discord:

- `VIEW_CHANNEL` - Ver canais
- `SEND_MESSAGES` - Enviar mensagens
- `MANAGE_MESSAGES` - Gerenciar mensagens (deletar)
- `MODERATE_MEMBERS` - Moderar membros (timeout)
- `READ_MESSAGE_HISTORY` - Ler histórico

## ⚙️ Comandos Administrativos

| Comando | Descrição |
|---------|-----------|
| `!status` | Verifica o status do bot |
| `!testar <texto>` | Testa a análise de IA com um texto |

## 📝 Logs

O bot exibe logs detalhados no console:

```
==================================================
📨 Nova mensagem de usuario123
📝 Conteúdo: O bot é muito bom!...
📎 Anexos: 1
🤖 Analisando feedback com IA...
📊 Resultado: POSITIVO (Confiança: 95.0%)
📝 Motivo: Feedback positivo elogiando o produto
✅ Feedback positivo - Nenhuma ação necessária
==================================================
```

## 🔒 Segurança

- Nunca compartilhe seu `.env` ou tokens
- O `.env` está no `.gitignore` (se usar Git)
- Use variáveis de ambiente em produção
