require('dotenv').config();
const express = require('express');
const twilio = require('twilio');
const OpenAI = require('openai');

const app = express();
const port = process.env.PORT || 3000;

// Verifica variabili ambiente
if (!process.env.TWILIO_ACCOUNT_SID || !process.env.TWILIO_AUTH_TOKEN || !process.env.OPENAI_API_KEY) {
  console.error('❌ Mancano variabili ambiente necessarie nel file .env');
  process.exit(1);
}

// Inizializza OpenAI
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
});

// Inizializza Twilio
const twilioClient = twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);

// Middleware
app.use(express.urlencoded({ extended: true }));
app.use(express.json());

// Carica config business
let businessConfig;
try {
  businessConfig = require('./config/business-config.json');
  console.log(`✅ Config caricata per: ${businessConfig.business.name}`);
} catch (error) {
  console.error('❌ Errore caricamento business-config.json:', error.message);
  console.error('💡 Assicurati che il file config/business-config.json esista');
  process.exit(1);
}

// Memory store conversazioni
const conversations = new Map();

// Genera prompt di sistema
function generateSystemPrompt() {
  const { business, services, schedules, faq, bot_personality } = businessConfig;
  
  return `Sei l'assistente virtuale di ${business.name}, ${business.description}.

INFORMAZIONI AZIENDALI:
- Nome: ${business.name}
- Indirizzo: ${business.address}
- Telefono: ${business.phone}
- Email: ${business.email}

SERVIZI:
${services.map(s => `- ${s.name}: ${s.description} (${s.price})`).join('\n')}

ORARI:
${Object.entries(schedules).map(([day, hours]) => `- ${translateDay(day)}: ${hours}`).join('\n')}

FAQ:
${faq.map(item => `Q: ${item.question}\nR: ${item.answer}`).join('\n\n')}

REGOLE:
1. Rispondi in italiano, tono ${bot_personality.tone}
2. NON usare emoji
3. Sii preciso su orari e prezzi
4. Se non sai qualcosa, dillo chiaramente
5. Se chiede prenotazioni/appuntamenti, suggerisci di chiamare ${business.phone}

Rispondi sempre in modo utile e professionale.`;
}

function translateDay(day) {
  const days = {
    'monday': 'Lunedì', 'tuesday': 'Martedì', 'wednesday': 'Mercoledì',
    'thursday': 'Giovedì', 'friday': 'Venerdì', 'saturday': 'Sabato', 'sunday': 'Domenica'
  };
  return days[day] || day;
}

function maskPhone(phone) {
  if (!phone) return 'unknown';
  return phone.substring(0, 8) + '***' + phone.substring(phone.length - 2);
}

// Bot logic
async function processMessage(from, message) {
  try {
    console.log(`📱 ${maskPhone(from)}: ${message}`);

    let conversation = conversations.get(from);
    if (!conversation) {
      conversation = { 
        history: [], 
        startTime: Date.now(),
        messageCount: 0
      };
      conversations.set(from, conversation);
      console.log(`✨ Nuova conversazione iniziata con ${maskPhone(from)}`);
    }

    conversation.messageCount++;

    if (conversation.history.length > 20) {
      conversation.history = conversation.history.slice(-20);
    }

    const messages = [
      { role: 'system', content: generateSystemPrompt() },
      ...conversation.history,
      { role: 'user', content: message }
    ];

    const completion = await openai.chat.completions.create({
      model: 'gpt-4o-mini',
      messages: messages,
      max_tokens: 200,
      temperature: 0.7
    });

    const response = completion.choices[0].message.content.trim();

    conversation.history.push(
      { role: 'user', content: message },
      { role: 'assistant', content: response }
    );

    console.log(`🤖 Bot → ${maskPhone(from)}: ${response}`);
    console.log(`📊 Conversazione: ${conversation.messageCount} messaggi`);

    return response;

  } catch (error) {
    console.error('❌ Errore processamento messaggio:', error.message);
    
    const fallbacks = [
      'Mi dispiace, sto avendo problemi tecnici. Riprova tra poco.',
      'Errore temporaneo del sistema. Puoi contattarci direttamente per assistenza.',
      'Difficoltà tecniche in corso. Per urgenze chiama il nostro numero diretto.'
    ];
    
    return fallbacks[Math.floor(Math.random() * fallbacks.length)];
  }
}

// Routes
app.get('/', (req, res) => {
  res.json({
    name: 'WhatsApp Chatbot MVP',
    business: businessConfig.business.name,
    status: 'running',
    uptime: Math.round(process.uptime()),
    conversations: conversations.size,
    version: '1.0.0'
  });
});

app.get('/health', (req, res) => {
  const memUsage = process.memoryUsage();
  res.json({
    status: 'ok',
    timestamp: new Date().toISOString(),
    uptime: Math.round(process.uptime()),
    memory: {
      used: Math.round(memUsage.heapUsed / 1024 / 1024) + 'MB',
      total: Math.round(memUsage.heapTotal / 1024 / 1024) + 'MB'
    },
    conversations: {
      active: conversations.size,
      total: Array.from(conversations.values()).reduce((sum, conv) => sum + conv.messageCount, 0)
    },
    business: businessConfig.business.name
  });
});

// Webhook WhatsApp principale
app.post('/webhook/whatsapp', async (req, res) => {
  try {
    const { From, Body, MessageSid } = req.body;
    
    console.log(`📨 Webhook ricevuto - ID: ${MessageSid}`);
    
    if (!From || !Body) {
      console.error('❌ Webhook malformato:', req.body);
      return res.status(400).json({ error: 'Missing From or Body' });
    }

    const cleanMessage = Body.trim();
    if (cleanMessage.length === 0) {
      console.log('⚠️ Messaggio vuoto ignorato');
      return res.status(200).send('Empty message ignored');
    }

    const response = await processMessage(From, cleanMessage);

    const twilioResponse = await twilioClient.messages.create({
      body: response,
      from: process.env.TWILIO_WHATSAPP_NUMBER,
      to: From
    });

    console.log(`✅ Risposta inviata - Twilio ID: ${twilioResponse.sid}`);
    res.status(200).json({ 
      status: 'success', 
      messageId: twilioResponse.sid 
    });

  } catch (error) {
    console.error('❌ Errore webhook:', error.message);
    res.status(500).json({ 
      error: 'Internal server error',
      message: error.message 
    });
  }
});

// Admin endpoint
app.get('/admin/stats', (req, res) => {
  const stats = {
    conversations: conversations.size,
    totalMessages: Array.from(conversations.values()).reduce((sum, conv) => sum + conv.messageCount, 0),
    uptime: Math.round(process.uptime()),
    memory: process.memoryUsage(),
    business: businessConfig.business.name
  };
  
  res.json(stats);
});

// Cleanup automatico
const cleanupInterval = setInterval(() => {
  const now = Date.now();
  const maxAge = 2 * 60 * 60 * 1000; // 2 ore
  let cleaned = 0;
  
  for (const [userId, conversation] of conversations) {
    if (now - conversation.startTime > maxAge) {
      conversations.delete(userId);
      cleaned++;
    }
  }
  
  if (cleaned > 0) {
    console.log(`🧹 Cleanup automatico: ${cleaned} conversazioni vecchie rimosse`);
  }
}, 60 * 60 * 1000);

// Graceful shutdown
process.on('SIGTERM', () => {
  console.log('🛑 SIGTERM ricevuto, shutdown graceful...');
  clearInterval(cleanupInterval);
  process.exit(0);
});

// Start server
app.listen(port, () => {
  console.log('🚀 =====================================');
  console.log(`🤖 WhatsApp Chatbot MVP avviato!`);
  console.log(`📱 Business: ${businessConfig.business.name}`);
  console.log(`🌐 Server: http://localhost:${port}`);
  console.log(`📞 Webhook: /webhook/whatsapp`);
  console.log(`📊 Stats: /admin/stats`);
  console.log('=====================================');
});