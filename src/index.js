require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');

const app = express();
const PORT = process.env.PORT || 3000;

// Middleware
app.use(helmet());
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Basic logging
app.use((req, res, next) => {
  console.log(`${new Date().toISOString()} - ${req.method} ${req.path}`);
  next();
});

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'OK', 
    timestamp: new Date().toISOString(),
    service: 'Bot Remindly'
  });
});

// Webhook endpoint per Twilio (per ora solo test)
app.post('/webhook/whatsapp', (req, res) => {
  console.log('Webhook ricevuto:', req.body);
  
  // Per ora rispondiamo solo OK
  res.status(200).send('OK');
});

// Test endpoint per inviare messaggi WhatsApp
app.post('/test/send', async (req, res) => {
  try {
    const { to, message } = req.body;
    
    if (!to || !message) {
      return res.status(400).json({ error: 'Mancano parametri to e message' });
    }
    
    // Verifica credenziali
    if (!process.env.TWILIO_ACCOUNT_SID || !process.env.TWILIO_AUTH_TOKEN) {
      return res.status(500).json({ error: 'Credenziali Twilio non configurate' });
    }
    
    // Inizializza client Twilio
    const twilio = require('twilio');
    const client = twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);
    
    // Invia messaggio WhatsApp
    const result = await client.messages.create({
      from: process.env.TWILIO_WHATSAPP_NUMBER,
      to: `whatsapp:${to}`,
      body: message
    });
    
    console.log(`✅ Messaggio inviato a ${to}: ${result.sid}`);
    
    res.json({ 
      success: true, 
      messageId: result.sid,
      to,
      content: message,
      status: result.status
    });
    
  } catch (error) {
    console.error('❌ Errore invio messaggio:', error);
    res.status(500).json({ error: error.message });
  }
});

// Error handling
app.use((err, req, res, next) => {
  console.error('Errore server:', err);
  res.status(500).json({ error: 'Errore interno del server' });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({ error: 'Endpoint non trovato' });
});

app.listen(PORT, () => {
  console.log(`🚀 Server Bot Remindly running on port ${PORT}`);
  console.log(`🔗 Webhook URL: http://localhost:${PORT}/webhook/whatsapp`);
});