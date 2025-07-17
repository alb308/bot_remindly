require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const OpenAI = require('openai');
const { google } = require('googleapis');
const moment = require('moment-timezone');
const fs = require('fs');
const BotEngine = require('./bot');
const config = require('./config');

const app = express();
const PORT = process.env.PORT || 3000;

// Inizializza OpenAI
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
});

// Inizializza Bot Engine
const botEngine = new BotEngine(openai);

// Inizializza Google Calendar
let calendar;
try {
  const credentials = JSON.parse(fs.readFileSync('google-credentials.json'));
  const auth = new google.auth.GoogleAuth({
    credentials: credentials,
    scopes: ['https://www.googleapis.com/auth/calendar']
  });
  calendar = google.calendar({ version: 'v3', auth });
  console.log('Google Calendar configurato');
} catch (error) {
  console.log('Google Calendar non configurato:', error.message);
}

// Store conversazioni
const conversations = new Map();

// Middleware
app.use(helmet());
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

app.use((req, res, next) => {
  console.log(`${new Date().toISOString()} - ${req.method} ${req.path}`);
  next();
});

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'OK', 
    timestamp: new Date().toISOString(),
    service: `Bot ${config.business.name}`,
    bot_name: config.personality.name,
    ai: process.env.OPENAI_API_KEY ? 'Configurato' : 'Non configurato',
    twilio: process.env.TWILIO_ACCOUNT_SID ? 'Configurato' : 'Non configurato',
    calendar: calendar ? 'Configurato' : 'Non configurato'
  });
});

// Funzione per ottenere slot disponibili (ottimizzata per palestra 6-20)
async function getAvailableSlots() {
  if (!calendar) return [];
  
  try {
    const now = moment().tz('Europe/Rome');
    const endTime = moment().tz('Europe/Rome').add(7, 'days');
    
    // Ottieni eventi esistenti
    const response = await calendar.events.list({
      calendarId: process.env.GOOGLE_CALENDAR_ID || 'primary',
      timeMin: now.toISOString(),
      timeMax: endTime.toISOString(),
      singleEvents: true,
      orderBy: 'startTime'
    });
    
    const busySlots = response.data.items || [];
    const availableSlots = [];
    
    // Slot palestra: 6:00-20:00, ogni ora
    const gymHours = [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20];
    
    for (let day = 1; day <= 7; day++) {
      const currentDay = moment().tz('Europe/Rome').add(day, 'days');
      
      // Palestra aperta tutti i giorni
      for (const hour of gymHours) {
        const slotStart = currentDay.clone().hour(hour).minute(0).second(0);
        const slotEnd = slotStart.clone().add(60, 'minutes'); // Sessioni da 1 ora
        
        // Controlla se lo slot è libero
        const isBooked = busySlots.some(event => {
          if (!event.start || !event.start.dateTime) return false;
          const eventStart = moment(event.start.dateTime);
          const eventEnd = moment(event.end.dateTime);
          return slotStart.isBetween(eventStart, eventEnd, null, '[)') ||
                 slotEnd.isBetween(eventStart, eventEnd, null, '(]') ||
                 (slotStart.isSameOrBefore(eventStart) && slotEnd.isSameOrAfter(eventEnd));
        });
        
        if (!isBooked && slotStart.isAfter(now)) {
          availableSlots.push({
            id: `slot_${slotStart.format('YYYY-MM-DD-HH-mm')}`,
            date: slotStart.format('YYYY-MM-DD'),
            time: slotStart.format('HH:mm'),
            display: slotStart.format('dddd DD/MM - HH:mm'),
            datetime: slotStart.toISOString(),
            buttonText: slotStart.format('ddd DD/MM HH:mm')
          });
        }
      }
    }
    
    return availableSlots.slice(0, 3); // Primi 3 slot
    
  } catch (error) {
    console.error('Errore ottenimento slot:', error);
    return [];
  }
}

// Funzione per creare evento (ottimizzata per personal training)
async function createCalendarEvent(leadData, slot) {
  if (!calendar) {
    console.log('Calendar non configurato, evento non creato');
    return null;
  }
  
  try {
    const startTime = moment(slot.datetime);
    const endTime = startTime.clone().add(60, 'minutes'); // Sessioni da 1 ora
    
    console.log(`Creando sessione personal training per ${startTime.format('DD/MM/YYYY HH:mm')}`);
    
    const event = {
      summary: `Personal Training - ${leadData.name}`,
      description: `Sessione di Personal Training Fitlab

Cliente: ${leadData.name}
Telefono: ${leadData.phone}
Obiettivo: ${leadData.goal || 'Da definire'}
Email: ${leadData.email || 'Non fornita'}

Tipo: ${leadData.isFirstSession ? 'PROVA GRATUITA' : 'Sessione regolare'}

Generato automaticamente da Giuseppe - Fitlab Bot`,
      start: {
        dateTime: startTime.toISOString(),
        timeZone: 'Europe/Rome'
      },
      end: {
        dateTime: endTime.toISOString(),
        timeZone: 'Europe/Rome'
      },
      reminders: {
        useDefault: false,
        overrides: [
          { method: 'popup', minutes: 60 }, // 1 ora prima
          { method: 'popup', minutes: 15 }  // 15 minuti prima
        ]
      }
    };
    
    const response = await calendar.events.insert({
      calendarId: process.env.GOOGLE_CALENDAR_ID || 'primary',
      resource: event
    });
    
    console.log(`Sessione creata: ${response.data.id}`);
    return response.data;
    
  } catch (error) {
    console.error('Errore creazione sessione:', error);
    return null;
  }
}

// Funzione per inviare messaggi WhatsApp
async function sendWhatsAppMessage(to, message, buttons = null) {
  const twilio = require('twilio');
  const client = twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);
  
  try {
    let messageBody = {
      from: process.env.TWILIO_WHATSAPP_NUMBER,
      to: `whatsapp:${to}`,
      body: message
    };
    
    if (buttons && buttons.length > 0) {
      let numberedMessage = message + '\n\n';
      buttons.forEach((button, index) => {
        numberedMessage += `${index + 1}. ${button.text}\n`;
      });
      numberedMessage += '\nRispondi con il numero della tua scelta';
      
      messageBody.body = numberedMessage;
    }
    
    const result = await client.messages.create(messageBody);
    return result;
    
  } catch (error) {
    console.error('Errore invio messaggio:', error);
    throw error;
  }
}

// Webhook WhatsApp
app.post('/webhook/whatsapp', async (req, res) => {
  const { From, Body, WaId, ProfileName } = req.body;
  
  console.log(`Messaggio da ${ProfileName}: ${Body}`);
  
  const userPhone = From.replace('whatsapp:', '');
  const userId = WaId || userPhone;
  
  // Inizializza conversazione
  if (!conversations.has(userId)) {
    conversations.set(userId, {
      messages: [],
      leadData: {
        name: ProfileName,
        phone: userPhone,
        stage: 'initial'
      }
    });
  }
  
  const conversation = conversations.get(userId);
  conversation.messages.push({ role: 'user', content: Body, timestamp: new Date() });
  
  try {
    let response = '';
    let buttons = null;
    
    const lowerBody = Body.toLowerCase().trim();
    
    // Gestione selezione slot
    if (conversation.availableSlots && /^[1-3]$/.test(lowerBody)) {
      const slotIndex = parseInt(lowerBody) - 1;
      const selectedSlot = conversation.availableSlots[slotIndex];
      
      if (selectedSlot) {
        const currentSlots = await getAvailableSlots();
        const stillAvailable = currentSlots.some(slot => slot.id === selectedSlot.id);
        
        if (!stillAvailable) {
          response = `Lo slot ${selectedSlot.display} non è più disponibile. Ecco gli slot aggiornati:`;
          const newSlots = await getAvailableSlots();
          if (newSlots.length > 0) {
            buttons = newSlots.map(slot => ({ text: slot.buttonText }));
            conversation.availableSlots = newSlots;
          } else {
            response += '\n\nNon ci sono slot disponibili al momento. Ti chiamo per fissare un orario.';
            delete conversation.availableSlots;
          }
        } else {
          // Controlla se è la prima sessione
          if (!conversation.leadData.hasBookedBefore) {
            conversation.leadData.isFirstSession = true;
            conversation.leadData.hasBookedBefore = true;
          }
          
          const event = await createCalendarEvent(conversation.leadData, selectedSlot);
          
          if (event) {
            response = conversation.leadData.isFirstSession 
              ? `Perfetto! Sessione di PROVA GRATUITA prenotata per ${selectedSlot.display}. Ti chiamerò per confermare i dettagli. A presto in palestra!`
              : `Sessione personal training confermata per ${selectedSlot.display}. Ti aspettiamo in palestra!`;
            
            conversation.leadData.stage = 'booked';
            conversation.leadData.appointmentDate = selectedSlot.datetime;
          } else {
            response = 'Problema nella prenotazione. Ti chiamo subito per risolvere!';
          }
          
          delete conversation.availableSlots;
        }
      } else {
        response = `Scelta non valida. Scegli un numero da 1 a ${conversation.availableSlots.length}.`;
      }
    } else {
      // Estrai informazioni
      const extractedInfo = botEngine.extractInfo(Body, conversation.leadData);
      Object.assign(conversation.leadData, extractedInfo);
      
      // Analizza intent
      const intent = botEngine.analyzeIntent(Body, conversation);
      
      // Aggiorna stage
      if (intent === 'booking' && conversation.leadData.stage === 'initial') {
        conversation.leadData.stage = 'booking';
      } else if (intent === 'qualifying' || extractedInfo.name) {
        conversation.leadData.stage = 'qualifying';
      }
      
      // Genera risposta
      const botResponse = await botEngine.generateResponse(intent, Body, conversation);
      
      if (botResponse === 'booking_slots') {
        if (conversation.leadData.phone) {
          const availableSlots = await getAvailableSlots();
          
          if (availableSlots.length > 0) {
            response = `Perfetto! Ecco i prossimi slot disponibili per la tua sessione:`;
            buttons = availableSlots.map(slot => ({ text: slot.buttonText }));
            conversation.availableSlots = availableSlots;
          } else {
            response = 'Non ci sono slot liberi al momento. Ti chiamo per trovare un orario perfetto!';
          }
        } else {
          response = 'Per prenotare la sessione ho bisogno del tuo numero. Puoi condividerlo?';
        }
      } else {
        response = botResponse;
      }
    }
    
    // Invia risposta
    await sendWhatsAppMessage(userPhone, response, buttons);
    
    // Salva risposta
    conversation.messages.push({ 
      role: 'assistant', 
      content: response, 
      timestamp: new Date(),
      buttons: buttons 
    });
    
    console.log(`Risposta inviata: ${response.substring(0, 50)}...`);
    
  } catch (error) {
    console.log('Errore:', error.message);
    
    try {
      await sendWhatsAppMessage(userPhone, 'Problema tecnico. Ti chiamo subito per aiutarti!');
    } catch (backupError) {
      console.log('Errore backup:', backupError.message);
    }
  }
  
  res.status(200).send('OK');
});

// API conversazioni
app.get('/api/conversations', (req, res) => {
  const conversationsArray = Array.from(conversations.entries()).map(([userId, data]) => ({
    userId,
    leadData: data.leadData,
    messageCount: data.messages.length,
    lastMessage: data.messages[data.messages.length - 1]?.timestamp,
    stage: data.leadData.stage,
    qualification: botEngine.getQualificationProgress(data.leadData)
  }));
  
  res.json(conversationsArray);
});

// API slot disponibili
app.get('/api/calendar/slots', async (req, res) => {
  try {
    const slots = await getAvailableSlots();
    res.json({ available: slots.length > 0, slots });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Test endpoint
app.post('/test/send', async (req, res) => {
  try {
    const { to, message } = req.body;
    
    if (!to || !message) {
      return res.status(400).json({ error: 'Mancano parametri to e message' });
    }
    
    const result = await sendWhatsAppMessage(to, message);
    
    res.json({ 
      success: true, 
      messageId: result.sid,
      to,
      content: message,
      status: result.status
    });
    
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Error handling
app.use((err, req, res, next) => {
  console.error('Errore server:', err);
  res.status(500).json({ error: 'Errore interno del server' });
});

app.use((req, res) => {
  res.status(404).json({ error: 'Endpoint non trovato' });
});

app.listen(PORT, () => {
  console.log(`Server ${config.business.name} Bot in esecuzione sulla porta ${PORT}`);
  console.log(`Bot: ${config.personality.name} (${config.personality.role})`);
  console.log(`Business: ${config.business.name} - Personal Training`);
  console.log(`Orari palestra: 6:00-20:00 tutti i giorni`);
  console.log(`Webhook URL: http://localhost:${PORT}/webhook/whatsapp`);
  console.log(`AI: ${process.env.OPENAI_API_KEY ? 'Configurato' : 'Non configurato'}`);
  console.log(`Twilio: ${process.env.TWILIO_ACCOUNT_SID ? 'Configurato' : 'Non configurato'}`);
  console.log(`Calendar: ${calendar ? 'Configurato' : 'Non configurato'}`);
});