// src/app.js - BOT CHE RISPONDE
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const twilio = require('twilio');
const OpenAI = require('openai');

const app = express();

// Setup OpenAI
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
});

// Setup Twilio
const twilioClient = twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);

// Storage conversazioni
const conversations = new Map();

// Middleware
app.use(helmet());
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use((req, res, next) => {
  console.log(`${req.method} ${req.path}`);
  next();
});

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'OK', 
    timestamp: new Date().toISOString(),
    service: 'Fitlab Bot',
    version: '1.0.0'
  });
});

// Funzione per inviare messaggi WhatsApp
async function sendWhatsAppMessage(to, message) {
  try {
    const result = await twilioClient.messages.create({
      from: process.env.TWILIO_WHATSAPP_NUMBER,
      to: `whatsapp:${to}`,
      body: message
    });
    console.log(`✅ Message sent to ${to}: ${message}`);
    return result;
  } catch (error) {
    console.error('❌ Send message error:', error);
    throw error;
  }
}

// Funzione per generare risposta AI
async function generateAIResponse(message, profileName) {
  try {
    const response = await openai.chat.completions.create({
      model: "gpt-4o-mini",
      messages: [
        {
          role: "system", 
          content: `Sei Giuseppe, assistente di Fitlab palestra. Offri personal training, orari 6-20, sessioni da 35€. Raccogli: nome, obiettivo fitness, telefono. Proponi prova gratuita. Rispondi in massimo 160 caratteri, NO emoji, tono professionale ma amichevole.`
        },
        { role: "user", content: `${profileName} dice: ${message}` }
      ],
      max_tokens: 80,
      temperature: 0.7
    });
    
    return response.choices[0].message.content;
  } catch (error) {
    console.error('❌ OpenAI error:', error);
    return `Ciao ${profileName}! Sono Giuseppe di Fitlab. Ti aiuto con personal training personalizzato. Come ti chiami?`;
  }
}

// Webhook WhatsApp - VERSIONE CHE RISPONDE
app.post('/webhook/whatsapp', async (req, res) => {
  try {
    const { From, Body, WaId, ProfileName } = req.body;
    console.log(`📱 Message from ${ProfileName}: ${Body}`);
    
    const userPhone = From.replace('whatsapp:', '');
    
    // Gestisci conversazione
    let conversation = conversations.get(WaId);
    if (!conversation) {
      conversation = {
        userId: WaId,
        name: ProfileName,
        phone: userPhone,
        messages: [],
        leadData: { stage: 'initial' }
      };
      conversations.set(WaId, conversation);
      console.log(`👤 New conversation: ${ProfileName}`);
    }
    
    // Salva messaggio utente
    conversation.messages.push({
      role: 'user',
      content: Body,
      timestamp: new Date()
    });
    
    // Genera risposta AI
    const aiResponse = await generateAIResponse(Body, ProfileName);
    
    // Invia risposta
    await sendWhatsAppMessage(userPhone, aiResponse);
    
    // Salva risposta bot
    conversation.messages.push({
      role: 'assistant',
      content: aiResponse,
      timestamp: new Date()
    });
    
    res.status(200).send('OK');
    
  } catch (error) {
    console.error('❌ Webhook error:', error);
    
    // Fallback response
    try {
      const userPhone = req.body.From?.replace('whatsapp:', '');
      if (userPhone) {
        await sendWhatsAppMessage(userPhone, 'Ciao! Sono Giuseppe di Fitlab. C\'è stato un problema tecnico, ti ricontatto subito!');
      }
    } catch (fallbackError) {
      console.error('❌ Fallback error:', fallbackError);
    }
    
    res.status(500).send('Error');
  }
});

// API routes
app.get('/api/stats', (req, res) => {
  res.json({
    status: 'working',
    totalConversations: conversations.size,
    totalMessages: Array.from(conversations.values()).reduce((total, conv) => total + conv.messages.length, 0)
  });
});

app.get('/api/conversations', (req, res) => {
  const convArray = Array.from(conversations.values()).map(conv => ({
    userId: conv.userId,
    name: conv.name,
    phone: conv.phone,
    messageCount: conv.messages.length,
    lastMessage: conv.messages[conv.messages.length - 1]?.timestamp
  }));
  res.json(convArray);
});

// Error handling
app.use((err, req, res, next) => {
  console.error('❌ Server error:', err);
  res.status(500).json({ error: 'Internal server error' });
});

app.use((req, res) => {
  res.status(404).json({ error: 'Endpoint not found' });
});

module.exports = app;