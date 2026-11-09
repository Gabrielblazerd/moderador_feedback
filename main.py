import discord
from discord.ext import commands
import openai
import os
import asyncio
from datetime import datetime, timedelta
from dotenv import load_dotenv
import base64
import aiohttp
import json
import sqlite3
from contextlib import closing
import logging
import sys

# Carrega variáveis de ambiente
load_dotenv()

# ==================== CONFIGURAÇÕES ====================
DISCORD_TOKEN = os.getenv("DISCORD_TOKEN")
OPENAI_API_KEY = os.getenv("OPENAI_API_KEY")
LEADER_ID = int(os.getenv("LEADER_ID", "0"))  # Configurar no .env
FEEDBACK_CHANNEL_ID = int(os.getenv("FEEDBACK_CHANNEL_ID", "0"))  # Configurar no .env
GUILD_ID = int(os.getenv("GUILD_ID", "0"))  # Configurar no .env

# Tempos de silenciamento
# POSSO_PERDER_CLIENTE = 1 hora, NEGATIVO = 1 dia
TIMEOUT_MEDIO_DURATION = timedelta(hours=1)  # 1 hora
TIMEOUT_NEGATIVO_DURATION = timedelta(days=1)  # 1 dia

# ==================== CONFIGURAÇÃO DO OPENAI ====================
openai.api_key = OPENAI_API_KEY

# ==================== PROMPT DE ANÁLISE ====================
ANALYSIS_PROMPT = """🧩 PROMPT DE JULGAMENTO DE FEEDBACK — BLAZERD STORE

🎯 OBJETIVO
Seu papel é analisar mensagens e imagens de feedback enviadas por clientes e classificar em três categorias:
- POSITIVO
- POSSO_PERDER_CLIENTE
- NEGATIVO

Você deve julgar com base no texto e/ou imagem.
O foco é proteger o servidor e a imagem da marca, evitando punir feedbacks construtivos.

🟢 1. POSITIVO
Use esta categoria se:
- O cliente elogia o bot, o suporte ou o serviço;
- Dá sugestões educadas (ex: "poderia adicionar tal função");
- Envia apenas uma imagem mostrando o produto funcionando (sem texto ofensivo);
- Diz algo neutro, mas sem risco de prejudicar vendas.

🧠 Exemplo de mensagens POSITIVAS:
- "Funciona perfeitamente!"
- "Seria legal adicionar suporte para mais contas."
- "Top bot 🔥"
- (Apenas imagem do bot em uso)

🟡 2. POSSO_PERDER_CLIENTE
Use esta categoria se:
- O cliente não está sendo ofensivo, mas faz comentários negativos sobre o produto, servidor ou suporte que podem afastar novos clientes;
- Reclama de banimento, demora, erro, ou insinua que o produto tem falhas, mas ainda de forma moderada;
- Diz algo que pode prejudicar a reputação da loja, mesmo sem insultos diretos.

💬 Exemplo de mensagens POSSO_PERDER_CLIENTE:
- "O bot parou de funcionar pra mim."
- "Fui banido do servidor e não sei o motivo."
- "Demorou muito pra receber o produto."
- "O suporte às vezes demora a responder."

🛑 Ação: excluir a mensagem, mas NÃO silenciar o usuário.

🔴 3. NEGATIVO
Use esta categoria se:
- O usuário está ofendendo, acusando, mentindo ou tentando prejudicar a imagem da Blazerd Store;
- Usa palavras agressivas ou ofensivas;
- Chama o produto de "scam", "lixo", "roubo", "enganoso", etc.;
- O tom é claramente de ataque, difamação ou intenção de causar dano.

💬 Exemplo de mensagens NEGATIVAS:
- "Esse servidor é uma fraude."
- "Roubaram meu dinheiro."
- "Não comprem, é scam."
- "Suporte horrível, não funciona nada."

🛑 Ação: silenciar o usuário e reprovar o feedback.

🧩 OBSERVAÇÕES IMPORTANTES
- Se só houver imagem, NUNCA marque como negativo (pode ser apenas o cliente mostrando o bot funcionando).
- Se houver texto + imagem, analise o texto como prioridade.
- Se for só emoji, "ok", "funciona", ou qualquer frase curta neutra → POSITIVO.
- Se a crítica for forte, agressiva ou insultante, mesmo curta → NEGATIVO.
- Se for crítica leve mas pública, que pode afastar outros clientes, → POSSO_PERDER_CLIENTE.

🔎 Formato esperado de resposta
Responda APENAS com um JSON no seguinte formato:
{
    "classificacao": "POSITIVO" | "POSSO_PERDER_CLIENTE" | "NEGATIVO",
    "motivo": "Breve explicação do motivo da classificação",
    "confianca": 0.0 a 1.0
}
"""

# ==================== INTENTS DO BOT ====================
intents = discord.Intents.default()
intents.message_content = True
intents.members = True
intents.guilds = True

MODERATION_STATE_DB = os.getenv("MODERATION_STATE_DB", "moderation_state.db")
moderation_enabled = True


def moderation_state(enabled=None):
    """Keep /off across restarts when this database is on the Railway volume."""
    with closing(sqlite3.connect(MODERATION_STATE_DB)) as state_db, state_db:
        state_db.execute("CREATE TABLE IF NOT EXISTS moderation_state (id INTEGER PRIMARY KEY CHECK(id=1), enabled INTEGER NOT NULL)")
        if enabled is not None:
            state_db.execute(
                "INSERT INTO moderation_state VALUES (1, ?) ON CONFLICT(id) DO UPDATE SET enabled=excluded.enabled",
                (int(enabled),),
            )
        row = state_db.execute("SELECT enabled FROM moderation_state WHERE id=1").fetchone()
        return bool(row[0]) if row else True


class FeedbackBot(commands.Bot):
    async def setup_hook(self):
        global moderation_enabled
        moderation_enabled = moderation_state()
        await self.tree.sync()


_stdout_handler = logging.StreamHandler(sys.stdout)
_stdout_handler.addFilter(lambda record: record.levelno < logging.WARNING)
_stderr_handler = logging.StreamHandler(sys.stderr)
_stderr_handler.setLevel(logging.WARNING)
logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s %(levelname)s %(name)s %(message)s",
    handlers=[_stdout_handler, _stderr_handler],
)
bot = FeedbackBot(command_prefix="!", intents=intents)


# ==================== FUNÇÕES AUXILIARES ====================

async def download_image_as_base64(url: str) -> str:
    """Baixa uma imagem e converte para base64"""
    try:
        async with aiohttp.ClientSession() as session:
            async with session.get(url) as response:
                if response.status == 200:
                    image_data = await response.read()
                    return base64.b64encode(image_data).decode('utf-8')
    except Exception as e:
        print(f"Erro ao baixar imagem: {e}")
    return None


async def analyze_feedback_with_ai(text_content: str, image_urls: list = None) -> dict:
    """Analisa o feedback usando OpenAI GPT-4 Vision"""
    try:
        messages = [
            {"role": "system", "content": ANALYSIS_PROMPT}
        ]
        
        # Construir conteúdo da mensagem
        user_content = []
        
        # Adicionar texto
        feedback_text = f"FEEDBACK DO CLIENTE:\n{text_content if text_content else '(Sem texto - apenas imagem)'}"
        user_content.append({"type": "text", "text": feedback_text})
        
        # Adicionar imagens se houver
        if image_urls:
            for img_url in image_urls[:3]:  # Máximo 3 imagens
                user_content.append({
                    "type": "image_url",
                    "image_url": {"url": img_url, "detail": "high"}
                })
        
        messages.append({"role": "user", "content": user_content})
        
        # Fazer chamada à API
        client = openai.OpenAI(api_key=OPENAI_API_KEY)
        response = client.chat.completions.create(
            model="gpt-4o",
            messages=messages,
            max_tokens=500,
            temperature=0.3
        )
        
        # Parsear resposta JSON
        response_text = response.choices[0].message.content.strip()
        
        # Tentar extrair JSON da resposta
        try:
            # Remover possíveis marcadores de código
            if "```json" in response_text:
                response_text = response_text.split("```json")[1].split("```")[0]
            elif "```" in response_text:
                response_text = response_text.split("```")[1].split("```")[0]
            
            result = json.loads(response_text)
            return result
        except json.JSONDecodeError:
            # Se não conseguir parsear, tentar extrair classificação manualmente
            if "NEGATIVO" in response_text.upper():
                return {"classificacao": "NEGATIVO", "motivo": response_text, "confianca": 0.7}
            elif "POSSO_PERDER_CLIENTE" in response_text.upper():
                return {"classificacao": "POSSO_PERDER_CLIENTE", "motivo": response_text, "confianca": 0.7}
            else:
                return {"classificacao": "POSITIVO", "motivo": response_text, "confianca": 0.7}
                
    except Exception as e:
        print(f"Erro na análise de IA: {e}")
        return {"classificacao": "POSITIVO", "motivo": f"Erro na análise: {e}", "confianca": 0.0}


async def send_user_warning(user: discord.User, classification: str, is_edit: bool = False):
    """Envia mensagem de aviso para o usuário (em inglês)"""
    try:
        edit_text = " (edited message)" if is_edit else ""
        
        if classification == "NEGATIVO":
            message = f"""⚠️ **WARNING - BLAZERD STORE**{edit_text}

Your message in the feedback channel has been removed for violating server rules.

📋 **Rule violated:** Offensive/harmful feedback
⏰ **Consequence:** You have been muted for **1 DAY (24 hours)**

🚨 **WARNING:** If you continue breaking the rules, you will be **PERMANENTLY BANNED** from the server.

If you believe this was a mistake, please contact support after the mute period."""

        elif classification == "POSSO_PERDER_CLIENTE":
            message = f"""⚠️ **WARNING - BLAZERD STORE**{edit_text}

Your message in the feedback channel has been removed.

📋 **Reason:** The content may harm the store's image
⏰ **Consequence:** You have been muted for **1 HOUR**

💡 If you have issues with the product, please contact support directly.

🎁 5% off coupon after sending positive feedback: **E9GSMSBS**"""

        await user.send(message)
        print(f"✅ Aviso enviado para {user.name}#{user.discriminator}")
        
    except discord.Forbidden:
        print(f"❌ Não foi possível enviar DM para {user.name} (DMs fechadas)")
    except Exception as e:
        print(f"❌ Erro ao enviar aviso: {e}")


async def send_leader_report(
    leader: discord.User | discord.Member,
    author: discord.Member,
    message_content: str,
    attachments: list,
    classification: str,
    reason: str,
    confidence: float,
    is_edit: bool = False,
    original_content: str = None
):
    """Envia relatório completo para o líder do servidor"""
    try:
        edit_info = ""
        if is_edit and original_content:
            edit_info = f"\n📝 **Mensagem Original:** {original_content[:500]}\n📝 **Mensagem Editada:** {message_content[:500]}"
        
        # Classificação emoji
        class_emoji = {
            "POSITIVO": "🟢",
            "POSSO_PERDER_CLIENTE": "🟡", 
            "NEGATIVO": "🔴"
        }
        
        # Ação tomada
        action_text = {
            "POSITIVO": "Nenhuma ação (feedback aprovado)",
            "POSSO_PERDER_CLIENTE": "Mensagem excluída + Silenciado por 1 HORA",
            "NEGATIVO": "Mensagem excluída + Silenciado por 1 DIA (24h)"
        }
        
        report = f"""📊 **RELATÓRIO DE FEEDBACK MODERADO**
{'━' * 40}

{class_emoji.get(classification, '⚪')} **Classificação:** {classification}
📈 **Confiança da IA:** {confidence * 100:.1f}%

👤 **Usuário:** {author.mention} ({author.name}#{author.discriminator})
🆔 **ID do Usuário:** {author.id}

{'📝 **Tipo:** Mensagem EDITADA' if is_edit else '📝 **Tipo:** Mensagem Nova'}
{edit_info if is_edit else f'💬 **Conteúdo:** {message_content[:500] if message_content else "(Sem texto)"}'}

📎 **Anexos:** {len(attachments)} arquivo(s)
{'🖼️ **URLs das imagens:**' if attachments else ''}
{chr(10).join([f'• {att.url}' for att in attachments[:3]]) if attachments else ''}

🤖 **Motivo da IA:** {reason}

⚡ **Ação Tomada:** {action_text.get(classification, 'Desconhecida')}

🕐 **Data/Hora:** {datetime.now().strftime('%d/%m/%Y %H:%M:%S')}
{'━' * 40}"""

        await leader.send(report)
        
        # Enviar imagens separadamente se houver (para o líder ver o conteúdo)
        for i, att in enumerate(attachments[:3]):
            try:
                await leader.send(f"**Anexo {i+1}:** {att.url}")
            except:
                pass
                
        print(f"✅ Relatório enviado para o líder")
        
    except discord.Forbidden:
        print(f"❌ Não foi possível enviar relatório para o líder (DMs fechadas)")
    except Exception as e:
        print(f"❌ Erro ao enviar relatório: {e}")


async def timeout_user_via_api(guild_id: int, user_id: int, duration: timedelta, reason: str):
    """Aplica timeout usando a API REST do Discord diretamente (fallback)"""
    try:
        from datetime import timezone
        
        # Calcular o timestamp ISO 8601 para quando o timeout expira
        timeout_until = (datetime.now(timezone.utc) + duration).isoformat()
        
        url = f"https://discord.com/api/v10/guilds/{guild_id}/members/{user_id}"
        
        headers = {
            "Authorization": f"Bot {DISCORD_TOKEN}",
            "Content-Type": "application/json",
            "X-Audit-Log-Reason": reason
        }
        
        payload = {
            "communication_disabled_until": timeout_until
        }
        
        async with aiohttp.ClientSession() as session:
            async with session.patch(url, headers=headers, json=payload) as response:
                if response.status == 200:
                    print(f"✅ Usuário silenciado via API REST")
                    return True
                else:
                    error_text = await response.text()
                    print(f"❌ Erro API Discord ({response.status}): {error_text}")
                    return False
                    
    except Exception as e:
        print(f"❌ Erro ao silenciar via API: {e}")
        return False


async def timeout_user(member: discord.Member, duration: timedelta, reason: str = "Feedback negativo/ofensivo"):
    """Aplica timeout (silenciamento) ao usuário - tenta discord.py, depois API REST"""
    try:
        # Método 1: discord.py com timedelta diretamente
        await member.timeout(duration, reason=reason)
        print(f"✅ Usuário {member.name} silenciado via discord.py")
        return True
    except Exception as e:
        print(f"⚠️ Falha discord.py ({e}), tentando via API REST...")
        
        # Método 2: Fallback para API REST
        return await timeout_user_via_api(
            guild_id=member.guild.id,
            user_id=member.id,
            duration=duration,
            reason=reason
        )


async def delete_message_safely(message: discord.Message):
    """Deleta uma mensagem de forma segura"""
    try:
        await message.delete()
        print(f"✅ Mensagem deletada: {message.id}")
        return True
    except discord.NotFound:
        print(f"⚠️ Mensagem já foi deletada: {message.id}")
        return False
    except discord.Forbidden:
        print(f"❌ Sem permissão para deletar mensagem: {message.id}")
        return False
    except Exception as e:
        print(f"❌ Erro ao deletar mensagem: {e}")
        return False


async def process_feedback_message(message: discord.Message, is_edit: bool = False, original_content: str = None):
    """Processa uma mensagem de feedback (nova ou editada)"""
    
    if not moderation_enabled:
        return

    # Ignorar mensagens do próprio bot
    if message.author.bot:
        return
    
    # Verificar se é o canal correto
    if message.channel.id != FEEDBACK_CHANNEL_ID:
        return
    
    print(f"\n{'=' * 50}")
    print(f"📨 {'Mensagem EDITADA' if is_edit else 'Nova mensagem'} de {message.author.name}")
    print(f"📝 Conteúdo: {message.content[:100]}...")
    print(f"📎 Anexos: {len(message.attachments)}")
    
    # Coletar URLs de imagens
    image_urls = []
    for attachment in message.attachments:
        if any(attachment.filename.lower().endswith(ext) for ext in ['.png', '.jpg', '.jpeg', '.gif', '.webp']):
            image_urls.append(attachment.url)
    
    # Analisar com IA
    print("🤖 Analisando feedback com IA...")
    analysis = await analyze_feedback_with_ai(message.content, image_urls)
    
    classification = analysis.get("classificacao", "POSITIVO")
    reason = analysis.get("motivo", "Sem motivo especificado")
    confidence = analysis.get("confianca", 0.5)
    
    print(f"📊 Resultado: {classification} (Confiança: {confidence * 100:.1f}%)")
    print(f"📝 Motivo: {reason}")
    
    # Obter o líder
    guild = message.guild
    leader = guild.get_member(LEADER_ID) or await bot.fetch_user(LEADER_ID)
    
    # Processar baseado na classificação
    if classification == "POSITIVO":
        print("✅ Feedback positivo - Nenhuma ação necessária")
        
        # Opcional: Enviar cupom de desconto
        try:
            await message.author.send(
                f"🎉 **Thank you for your positive feedback!**\n\n"
                f"🎁 5% off coupon: **E9GSMSBS**\n"
                f"🔗 https://blazerdstore.com/"
            )
        except:
            pass
            
    elif classification == "POSSO_PERDER_CLIENTE":
        print("🟡 Feedback pode prejudicar - Excluindo e silenciando 1 HORA...")
        
        # Deletar mensagem
        await delete_message_safely(message)
        
        # Silenciar usuário por 1 HORA
        member = message.author if isinstance(message.author, discord.Member) else guild.get_member(message.author.id)
        if member:
            await timeout_user(member, TIMEOUT_MEDIO_DURATION, "Feedback pode prejudicar a imagem da loja")
        
        # Enviar aviso ao usuário
        await send_user_warning(message.author, classification, is_edit)
        
        # Enviar relatório ao líder
        await send_leader_report(
            leader=leader,
            author=message.author,
            message_content=message.content,
            attachments=message.attachments,
            classification=classification,
            reason=reason,
            confidence=confidence,
            is_edit=is_edit,
            original_content=original_content
        )
        
    elif classification == "NEGATIVO":
        print("🔴 Feedback negativo - Excluindo e silenciando...")
        
        # Deletar mensagem
        await delete_message_safely(message)
        
        # Silenciar usuário por 1 DIA
        member = message.author if isinstance(message.author, discord.Member) else guild.get_member(message.author.id)
        if member:
            await timeout_user(member, TIMEOUT_NEGATIVO_DURATION, "Feedback negativo/ofensivo")
        
        # Enviar aviso ao usuário
        await send_user_warning(message.author, classification, is_edit)
        
        # Enviar relatório ao líder
        await send_leader_report(
            leader=leader,
            author=message.author,
            message_content=message.content,
            attachments=message.attachments,
            classification=classification,
            reason=reason,
            confidence=confidence,
            is_edit=is_edit,
            original_content=original_content
        )
    
    print(f"{'=' * 50}\n")


# ==================== EVENTOS DO BOT ====================

@bot.event
async def on_ready():
    """Evento quando o bot está pronto"""
    print(f"""
{'=' * 60}
🤖 BOT DE MODERAÇÃO DE FEEDBACK - BLAZERD STORE
{'=' * 60}
✅ Bot conectado como: {bot.user.name}#{bot.user.discriminator}
🆔 Bot ID: {bot.user.id}
{'=' * 60}
📋 CONFIGURAÇÕES:
   • Canal de Feedback: {FEEDBACK_CHANNEL_ID}
   • ID do Líder: {LEADER_ID}
   • Timeout Médio: 1 hora
   • Timeout Negativo: 1 dia
   • Servidor: {GUILD_ID}
{'=' * 60}
🔍 Monitorando canal de feedback...
{'=' * 60}
""")


@bot.event
async def on_message(message: discord.Message):
    """Evento para novas mensagens"""
    await process_feedback_message(message, is_edit=False)
    await bot.process_commands(message)


@bot.event
async def on_message_edit(before: discord.Message, after: discord.Message):
    """Evento para mensagens editadas"""
    # Só processa se o conteúdo mudou
    if before.content != after.content or before.attachments != after.attachments:
        print(f"\n🔄 Mensagem EDITADA detectada de {after.author.name}")
        await process_feedback_message(after, is_edit=True, original_content=before.content)


# ==================== COMANDOS ADMINISTRATIVOS ====================

@bot.hybrid_command(name="off", description="Pausar a moderação automática")
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def disable_moderation(ctx):
    global moderation_enabled
    moderation_state(False)
    moderation_enabled = False
    await ctx.send("Moderação automática pausada.", ephemeral=ctx.interaction is not None)


@bot.hybrid_command(name="on", description="Retomar a moderação automática")
@commands.guild_only()
@commands.has_permissions(administrator=True)
async def enable_moderation(ctx):
    global moderation_enabled
    moderation_state(True)
    moderation_enabled = True
    await ctx.send("Moderação automática ativada.", ephemeral=ctx.interaction is not None)


@bot.command(name="status")
@commands.has_permissions(administrator=True)
async def status_command(ctx):
    """Verifica o status do bot"""
    embed = discord.Embed(
        title="🤖 Status do Bot de Moderação",
        color=discord.Color.green()
    )
    embed.add_field(name="Estado", value="Ativa" if moderation_enabled else "Pausada", inline=True)
    embed.add_field(name="Canal Monitorado", value=f"<#{FEEDBACK_CHANNEL_ID}>", inline=True)
    embed.add_field(name="Líder", value=f"<@{LEADER_ID}>", inline=True)
    embed.add_field(name="Timeout Médio", value="1 hora", inline=True)
    embed.add_field(name="Timeout Negativo", value="1 dia", inline=True)
    embed.set_footer(text=f"Bot ID: {bot.user.id}")
    
    await ctx.send(embed=embed)


@bot.command(name="testar")
@commands.has_permissions(administrator=True)
async def test_command(ctx, *, texto: str):
    """Testa a análise de IA com um texto"""
    await ctx.send("🤖 Analisando texto...")
    
    analysis = await analyze_feedback_with_ai(texto)
    
    embed = discord.Embed(
        title="📊 Resultado da Análise",
        color=discord.Color.blue()
    )
    embed.add_field(name="Classificação", value=analysis.get("classificacao", "N/A"), inline=True)
    embed.add_field(name="Confiança", value=f"{analysis.get('confianca', 0) * 100:.1f}%", inline=True)
    embed.add_field(name="Motivo", value=analysis.get("motivo", "N/A")[:1000], inline=False)
    
    await ctx.send(embed=embed)


@bot.command(name="testtimeout")
@commands.has_permissions(administrator=True)
async def test_timeout_command(ctx, member: discord.Member, minutos: int = 1):
    """Testa o timeout em um membro"""
    await ctx.send(f"⏳ Testando timeout em {member.name} por {minutos} minuto(s)...")
    
    success = await timeout_user(member, timedelta(minutes=minutos), "Teste de timeout")
    
    if success:
        await ctx.send(f"✅ {member.name} silenciado por {minutos} minuto(s)!")
    else:
        await ctx.send(f"❌ Falha ao silenciar {member.name}. Verifique as permissões do bot.")


# ==================== INICIALIZAÇÃO ====================

if __name__ == "__main__":
    if not DISCORD_TOKEN:
        print("❌ ERRO: DISCORD_TOKEN não encontrado no .env")
        exit(1)
    
    if not OPENAI_API_KEY:
        print("❌ ERRO: OPENAI_API_KEY não encontrado no .env")
        exit(1)
    
    print("🚀 Iniciando bot...")
    bot.run(DISCORD_TOKEN, log_handler=None)
