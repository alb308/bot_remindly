require('dotenv').config();
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const OpenAI = require('openai');
const { google } = require('googleapis');
const moment = require('moment-timezone');
const fs = require('fs');

const app = express();
const PORT = process.env.PORT || 3000;

// Inizializza OpenAI
const openai = new OpenAI({
  apiKey: process.env.OPENAI_API_KEY
});

// Inizializza Google Calendar
let calendar;
try {
  const credentials = JSON.parse(fs.readFileSync('google-credentials.json'));
  const auth = new google.auth.GoogleAuth({
    credentials: credentials,
    scopes: ['https://www.googleapis.com/auth/calendar']
  });
  calendar = google.calendar({ version: 'v3', auth });
  console.log('📅 Google Calendar configurato');
} catch (error) {
  console.log('⚠️ Google Calendar non configurato:', error.message);
}

// Store temporaneo per conversazioni
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
    service: 'Bot Remindly AI + Calendar + Buttons',
    ai: process.env.OPENAI_API_KEY ? 'Configurato' : 'Non configurato',
    twilio: process.env.TWILIO_ACCOUNT_SID ? 'Configurato' : 'Non configurato',
    calendar: calendar ? 'Configurato' : 'Non configurato'
  });
});

// Funzione per ottenere slot disponibili
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
    
    // Genera slot disponibili (9:00-18:00, esclusi weekend)
    for (let day = 1; day <= 7; day++) {
      const currentDay = moment().tz('Europe/Rome').add(day, 'days');
      
      // Salta weekend
      if (currentDay.day() === 0 || currentDay.day() === 6) continue;
      
      // Orari disponibili: 9:00, 11:00, 14:00, 16:00
      const hours = [9, 11, 14, 16];
      
      for (const hour of hours) {
        const slotStart = currentDay.clone().hour(hour).minute(0).second(0);
        const slotEnd = slotStart.clone().add(30, 'minutes');
        
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
    
    return availableSlots.slice(0, 3); // Primi 3 slot disponibili
    
  } catch (error) {
    console.error('❌ Errore ottenimento slot:', error);
    return [];
  }
}

// Funzione per creare evento in calendario
async function createCalendarEvent(leadData, slot) {
  if (!calendar) {
    console.log('⚠️ Calendar non configurato, evento non creato');
    return null;
  }
  
  try {
    const startTime = moment(slot.datetime);
    const endTime = startTime.clone().add(30, 'minutes');
    
    console.log(`📅 Creando evento per ${startTime.format('DD/MM/YYYY HH:mm')}`);
    
    const event = {
      summary: `Demo Remindly - ${leadData.name}`,
      description: `Demo personalizzata Remindly

Cliente: ${leadData.name}
Azienda: ${leadData.company || 'Non specificata'}
Email: ${leadData.email || 'Non fornita'}
Telefono: ${leadData.phone}
Esigenze: ${leadData.needs || 'Da definire'}

🤖 Generato automaticamente da RemindlyBot
📧 Ricordati di inviare manualmente la conferma a: ${leadData.email}`,
      start: {
        dateTime: startTime.toISOString(),
        timeZone: 'Europe/Rome'
      },
      end: {
        dateTime: endTime.toISOString(),
        timeZone: 'Europe/Rome'
      },
      // Rimosso attendees per evitare errore 403
      reminders: {
        useDefault: false,
        overrides: [
          { method: 'popup', minutes: 30 }       // 30 minuti prima
        ]
      }
    };
    
    const response = await calendar.events.insert({
      calendarId: process.env.GOOGLE_CALENDAR_ID || 'primary',
      resource: event
      // Rimosso sendUpdates per evitare errore
    });
    
    console.log(`✅ Evento creato con successo: ${response.data.id}`);
    console.log(`🔗 Link evento: ${response.data.htmlLink}`);
    
    return response.data;
    
  } catch (error) {
    console.error('❌ Errore creazione evento:', error);
    return null;
  }
}

// Funzione per inviare messaggi WhatsApp con pulsanti
async function sendWhatsAppMessage(to, message, buttons = null) {
  const twilio = require('twilio');
  const client = twilio(process.env.TWILIO_ACCOUNT_SID, process.env.TWILIO_AUTH_TOKEN);
  
  try {
    let messageBody = {
      from: process.env.TWILIO_WHATSAPP_NUMBER,
      to: `whatsapp:${to}`,
      body: message
    };
    
    // Se ci sono pulsanti, usa il formato Twilio per i pulsanti
    if (buttons && buttons.length > 0) {
      // Per WhatsApp, i pulsanti sono limitati, quindi usiamo un messaggio con opzioni numerate
      let numberedMessage = message + '\n\n';
      buttons.forEach((button, index) => {
        numberedMessage += `${index + 1}. ${button.text}\n`;
      });
      numberedMessage += '\nRispondi con il numero della tua scelta 👆';
      
      messageBody.body = numberedMessage;
    }
    
    const result = await client.messages.create(messageBody);
    return result;
    
  } catch (error) {
    console.error('❌ Errore invio messaggio:', error);
    throw error;
  }
}

// Webhook endpoint per messaggi WhatsApp con AI + Calendar + Buttons
app.post('/webhook/whatsapp', async (req, res) => {
  const { From, Body, WaId, ProfileName } = req.body;
  
  console.log(`📱 Messaggio da ${ProfileName}: ${Body}`);
  
  const userPhone = From.replace('whatsapp:', '');
  const userId = WaId || userPhone;
  
  // Recupera o inizializza conversazione
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
        console.log(`🎯 Slot selezionato: ${selectedSlot.display}`);
        
        // Controlla di nuovo la disponibilità dello slot
        const currentSlots = await getAvailableSlots();
        const stillAvailable = currentSlots.some(slot => slot.id === selectedSlot.id);
        
        if (!stillAvailable) {
          response = `😔 Mi dispiace, lo slot ${selectedSlot.display} non è più disponibile. Ecco gli slot aggiornati:`;
          
          const newSlots = await getAvailableSlots();
          if (newSlots.length > 0) {
            buttons = newSlots.map(slot => ({ text: slot.buttonText }));
            conversation.availableSlots = newSlots;
          } else {
            response += '\n\nAl momento non ci sono slot disponibili. Ti contatterò via email per concordare un orario.';
            delete conversation.availableSlots;
          }
        } else {
          // Crea evento in calendario
          const event = await createCalendarEvent(conversation.leadData, selectedSlot);
          
          if (event) {
            response = `🎉 Perfetto! Demo confermata per ${selectedSlot.display}

✅ L'evento è stato aggiunto al mio calendario
📧 Ti invierò manualmente la conferma via email a: ${conversation.leadData.email}
🚀 Preparerò una demo personalizzata basata sulle tue esigenze

Dettagli appuntamento:
📅 Data: ${selectedSlot.display}
⏱️ Durata: 30 minuti
💼 Tipo: Demo personalizzata Remindly

A presto! 😊`;
            
            conversation.leadData.stage = 'booked';
            conversation.leadData.appointmentDate = selectedSlot.datetime;
          } else {
            response = `😔 Si è verificato un problema nella prenotazione. Ti contatterò personalmente per confermare l'appuntamento ${selectedSlot.display}. Grazie per la pazienza! 🙏`;
          }
          
          delete conversation.availableSlots;
        }
      } else {
        response = `❌ Selezione non valida. Scegli un numero da 1 a ${conversation.availableSlots.length} 😊`;
      }
    }
    // Gestione richiesta demo/appuntamento
    else if (lowerBody.includes('demo') || lowerBody.includes('appuntamento') || 
             lowerBody.includes('chiamata') || lowerBody.includes('incontro') ||
             conversation.leadData.stage === 'booking') {
      
      conversation.leadData.stage = 'booking';
      
      // Controlla se ha fornito email
      const emailMatch = Body.match(/[a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,}/);
      if (emailMatch) {
        conversation.leadData.email = emailMatch[0];
      }
      
      if (conversation.leadData.email) {
        console.log('📅 Cercando slot disponibili...');
        const availableSlots = await getAvailableSlots();
        
        if (availableSlots.length > 0) {
          response = `🎯 Perfetto! Ecco i prossimi slot disponibili per la demo:`;
          buttons = availableSlots.map(slot => ({ text: slot.buttonText }));
          conversation.availableSlots = availableSlots;
        } else {
          response = `😔 Al momento non ci sono slot disponibili questa settimana. Ti contatterò via email per concordare un orario personalizzato. Grazie! 📧`;
        }
      } else {
        response = `👋 Ottimo! Per fissare la demo ho bisogno della tua email. Puoi condividerla? 📧

Questo mi permetterà di inviarti la conferma e i dettagli dell'appuntamento.`;
      }
    }
    // Conversazione normale con AI
    else {
      console.log('🤖 Generando risposta AI...');
      
      // Estrai informazioni utente se presenti
      if (lowerBody.includes('sono ') || lowerBody.includes('mi chiamo ')) {
        const nameMatch = Body.match(/(?:sono|mi chiamo)\s+([a-zA-Z\s]+)/i);
        if (nameMatch) {
          conversation.leadData.name = nameMatch[1].trim();
        }
      }
      
      if (lowerBody.includes('lavoro') && (lowerBody.includes('in ') || lowerBody.includes('da ') || lowerBody.includes('per '))) {
        const companyMatch = Body.match(/(?:lavoro|sono)\s+(?:in|da|per)\s+([a-zA-Z\s]+)/i);
        if (companyMatch) {
          conversation.leadData.company = companyMatch[1].trim();
        }
      }
      
      const systemPrompt = `Sei RemindlyBot, un assistente vendite per Remindly, un'app di promemoria intelligente.

INFORMAZIONI LEAD:
- Nome: ${conversation.leadData.name || 'Non fornito'}
- Azienda: ${conversation.leadData.company || 'Non fornita'}
- Email: ${conversation.leadData.email || 'Non fornita'}
- Stage: ${conversation.leadData.stage}

OBIETTIVI:
1. Qualificare il lead (nome, azienda, esigenze)
2. Spiegare benefici Remindly (app AI per promemoria e produttività)
3. Portare verso richiesta demo/appuntamento
4. Essere naturale e professionale

REGOLE:
- Rispondi in italiano
- Massimo 160 caratteri
- Una domanda per volta
- Usa emoji con moderazione
- Se il lead è qualificato e interessato, proponi demo
- Mantieni focus su Remindly e produttività

CONVERSAZIONE PRECEDENTE:
${conversation.messages.slice(-3).map(m => `${m.role}: ${m.content}`).join('\n')}`;

      const aiResponse = await openai.chat.completions.create({
        model: "gpt-4o-mini",
        messages: [
          { role: "system", content: systemPrompt },
          { role: "user", content: Body }
        ],
        max_tokens: 120,
        temperature: 0.7
      });
      
      response = aiResponse.choices[0].message.content;
      console.log(`💭 Risposta AI: ${response}`);
    }
    
    // Invia risposta
    await sendWhatsAppMessage(userPhone, response, buttons);
    
    // Salva risposta bot nella conversazione
    conversation.messages.push({ 
      role: 'assistant', 
      content: response, 
      timestamp: new Date(),
      buttons: buttons 
    });
    
    console.log(`✅ Risposta inviata: ${response.substring(0, 50)}...`);
    
  } catch (error) {
    console.log('❌ Errore:', error.message);
    
    // Fallback
    try {
      await sendWhatsAppMessage(userPhone, 
        `Ciao ${ProfileName}! 👋 RemindlyBot qui. C'è stato un problema tecnico, ma ti contatterò presto per la demo di Remindly! 😊`
      );
    } catch (backupError) {
      console.log('❌ Errore anche nel backup:', backupError.message);
    }
  }
  
  res.status(200).send('OK');
});

// API per vedere conversazioni
app.get('/api/conversations', (req, res) => {
  const conversationsArray = Array.from(conversations.entries()).map(([userId, data]) => ({
    userId,
    leadData: data.leadData,
    messageCount: data.messages.length,
    lastMessage: data.messages[data.messages.length - 1]?.timestamp,
    stage: data.leadData.stage
  }));
  
  res.json(conversationsArray);
});

// API per vedere slot disponibili
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
  console.log(`🚀 Server Bot Remindly AI + Calendar + Buttons running on port ${PORT}`);
  console.log(`🔗 Webhook URL: http://localhost:${PORT}/webhook/whatsapp`);
  console.log(`🤖 AI: ${process.env.OPENAI_API_KEY ? 'Configurato ✅' : 'Non configurato ❌'}`);
  console.log(`📱 Twilio: ${process.env.TWILIO_ACCOUNT_SID ? 'Configurato ✅' : 'Non configurato ❌'}`);
  console.log(`📅 Calendar: ${calendar ? 'Configurato ✅' : 'Non configurato ❌'}`);
  console.log(`📱 Per testare: invia messaggio WhatsApp a +1 415 523 8886`);
});