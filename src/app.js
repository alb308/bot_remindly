// src/app.js - Applicazione multi-tenant scalabile
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const twilio = require('twilio');
const UniversalBotEngine = require('./core/BotEngine');

const app = express();

// Middleware
app.use(helmet());
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Logging middleware
app.use((req, res, next) => {
  console.log(`${req.method} ${req.path} - ${new Date().toISOString()}`);
  next();
});

// Setup Twilio
const twilioClient = twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);

// Storage per bot engines (uno per cliente)
const botEngines = new Map();

// Funzione per ottenere bot engine del cliente
function getBotEngine(clientId) {
  if (!botEngines.has(clientId)) {
    try {
      // Carica configurazione cliente
      const clientConfig = require(`./config/clients/${clientId}`);
      
      // Crea bot engine per questo cliente
      const engine = new UniversalBotEngine(clientConfig);
      botEngines.set(clientId, engine);
      
      console.log(`🤖 Bot engine creato per cliente: ${clientId}`);
    } catch (error) {
      console.error(`❌ Errore caricamento config per ${clientId}:`, error.message);
      return null;
    }
  }
  
  return botEngines.get(clientId);
}
// Nel webhook, dopo getBotEngine:
if (!botEngine) {
  console.error(`❌ Cliente ${clientId} non configurato`);
  console.log(`📁 Cercando file: ./config/clients/${clientId}.js`);
  
  // Lista file disponibili per debug
  try {
    const fs = require('fs');
    const files = fs.readdirSync('./src/config/clients/');
    console.log(`📂 File disponibili:`, files);
  } catch (e) {
    console.log(`❌ Errore lettura cartella clients:`, e.message);
  }
  
  return res.status(404).json({ error: 'Cliente non trovato' });
}

// Funzione per inviare messaggi WhatsApp
async function sendWhatsAppMessage(to, message) {
  try {
    const result = await twilioClient.messages.create({
      from: process.env.TWILIO_WHATSAPP_NUMBER,
      to: `whatsapp:${to}`,
      body: message
    });
    
    console.log(`✅ Message sent to ${to}: ${message.substring(0, 50)}...`);
    return result;
  } catch (error) {
    console.error('❌ Send message error:', error);
    throw error;
  }
}

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'OK', 
    timestamp: new Date().toISOString(),
    service: 'Universal WhatsApp Bot',
    version: '2.0.0',
    activeClients: botEngines.size
  });
});

// Webhook universale - funziona per tutti i clienti
app.post('/webhook/:clientId', async (req, res) => {
  const { clientId } = req.params;
  
  try {
    const { From, Body, WaId, ProfileName } = req.body;
    console.log(`📱 [${clientId}] Message from ${ProfileName}: ${Body}`);
    
    // Ottieni bot engine per questo cliente
    const botEngine = getBotEngine(clientId);
    if (!botEngine) {
      console.error(`❌ Cliente ${clientId} non configurato`);
      return res.status(404).json({ error: 'Cliente non trovato' });
    }
    
    const userPhone = From.replace('whatsapp:', '');
    
    // Processa messaggio con engine universale
    const response = botEngine.processMessage(WaId, Body, ProfileName);
    
    // Invia risposta
    await sendWhatsAppMessage(userPhone, response);
    
    console.log(`🤖 [${clientId}] Response: ${response.substring(0, 50)}...`);
    
    res.status(200).send('OK');
    
  } catch (error) {
    console.error(`❌ [${clientId}] Webhook error:`, error);
    
    // Fallback response
    try {
      const userPhone = req.body.From?.replace('whatsapp:', '');
      if (userPhone) {
        await sendWhatsAppMessage(userPhone, 'Problema tecnico temporaneo. Ti ricontatto subito!');
      }
    } catch (fallbackError) {
      console.error('❌ Fallback error:', fallbackError);
    }
    
    res.status(500).send('Error');
  }
});

// API Stats per cliente specifico
app.get('/api/:clientId/stats', (req, res) => {
  const { clientId } = req.params;
  
  try {
    const botEngine = getBotEngine(clientId);
    if (!botEngine) {
      return res.status(404).json({ error: 'Cliente non trovato' });
    }
    
    const stats = botEngine.getStats();
    res.json({
      clientId,
      ...stats,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// API Conversazioni per cliente specifico
app.get('/api/:clientId/conversations', (req, res) => {
  const { clientId } = req.params;
  
  try {
    const botEngine = getBotEngine(clientId);
    if (!botEngine) {
      return res.status(404).json({ error: 'Cliente non trovato' });
    }
    
    const conversations = botEngine.getAllConversations();
    res.json({
      clientId,
      conversations,
      count: conversations.length
    });
    
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// API Global Stats (tutti i clienti)
app.get('/api/global/stats', (req, res) => {
  try {
    const globalStats = {
      totalClients: botEngines.size,
      clients: []
    };
    
    for (const [clientId, engine] of botEngines.entries()) {
      const stats = engine.getStats();
      globalStats.clients.push({
        clientId,
        ...stats
      });
    }
    
    // Calcola totali globali
    globalStats.totalConversations = globalStats.clients.reduce((sum, client) => sum + client.totalConversations, 0);
    globalStats.totalQualifiedLeads = globalStats.clients.reduce((sum, client) => sum + client.qualifiedLeads, 0);
    globalStats.averageConversionRate = globalStats.clients.length > 0 
      ? Math.round(globalStats.clients.reduce((sum, client) => sum + client.conversionRate, 0) / globalStats.clients.length)
      : 0;
    
    res.json(globalStats);
    
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// API per testare un cliente specifico
app.post('/api/:clientId/test', async (req, res) => {
  const { clientId } = req.params;
  const { phone, message } = req.body;
  
  try {
    if (!phone || !message) {
      return res.status(400).json({ error: 'Phone e message sono richiesti' });
    }
    
    const botEngine = getBotEngine(clientId);
    if (!botEngine) {
      return res.status(404).json({ error: 'Cliente non trovato' });
    }
    
    // Simula messaggio di test
    const response = botEngine.processMessage('test_user', message, 'Test User');
    
    res.json({
      clientId,
      testMessage: message,
      botResponse: response,
      timestamp: new Date().toISOString()
    });
    
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// API per elencare clienti configurati
app.get('/api/clients', (req, res) => {
  try {
    const fs = require('fs');
    const path = require('path');
    
    const clientsDir = path.join(__dirname, 'config', 'clients');
    const clientFiles = fs.readdirSync(clientsDir).filter(file => file.endsWith('.js'));
    
    const clients = clientFiles.map(file => {
      const clientId = file.replace('.js', '');
      const isActive = botEngines.has(clientId);
      
      let config = null;
      try {
        config = require(`./config/clients/${clientId}`);
      } catch (error) {
        console.error(`Errore caricamento config ${clientId}:`, error.message);
      }
      
      return {
        clientId,
        businessName: config?.businessName || 'N/A',
        industry: config?.industry || 'N/A',
        isActive,
        webhookUrl: `/webhook/${clientId}`
      };
    });
    
    res.json({
      totalClients: clients.length,
      activeClients: clients.filter(c => c.isActive).length,
      clients
    });
    
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Error handling
app.use((err, req, res, next) => {
  console.error('❌ Server error:', err);
  res.status(500).json({ 
    error: 'Internal server error',
    timestamp: new Date().toISOString()
  });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({ 
    error: 'Endpoint not found',
    availableEndpoints: [
      'GET /health',
      'POST /webhook/:clientId',
      'GET /api/:clientId/stats',
      'GET /api/:clientId/conversations',
      'GET /api/global/stats',
      'GET /api/clients'
    ]
  });
});

module.exports = app;