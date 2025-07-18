// src/services/index.js - All services

const OpenAI = require('openai');
const twilio = require('twilio');
const { google } = require('googleapis');
const moment = require('moment-timezone');
const fs = require('fs');
const config = require('../config/business');
const { botLogger } = require('../utils/logger');
const validators = require('../utils/validators');
const { Slot } = require('../models');

// OpenAI Service
class OpenAIService {
  constructor() {
    this.client = new OpenAI({
      apiKey: process.env.OPENAI_API_KEY
    });
  }

  async generateResponse(systemPrompt, messages, maxTokens = 80) {
    const startTime = Date.now();
    
    try {
      const response = await this.client.chat.completions.create({
        model: "gpt-4o-mini",
        messages: [
          { role: "system", content: systemPrompt },
          ...messages
        ],
        max_tokens: maxTokens,
        temperature: 0.7
      });

      const duration = Date.now() - startTime;
      botLogger.performance('openai_request', duration, true);

      return response.choices[0].message.content;
    } catch (error) {
      const duration = Date.now() - startTime;
      botLogger.performance('openai_request', duration, false);
      botLogger.botError(error, { systemPrompt, messages });
      throw error;
    }
  }
}

// WhatsApp Service
class WhatsAppService {
  constructor() {
    this.client = twilio(
      process.env.TWILIO_ACCOUNT_SID, 
      process.env.TWILIO_AUTH_TOKEN
    );
  }

  async sendMessage(to, message, buttons = null) {
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

      const result = await this.client.messages.create(messageBody);
      return result;
    } catch (error) {
      botLogger.botError(error, { to, message });
      throw error;
    }
  }
}

// Calendar Service
class CalendarService {
  constructor() {
    this.calendar = null;
    this.initializeCalendar();
  }

  initializeCalendar() {
    try {
      const credentials = JSON.parse(fs.readFileSync('google-credentials.json'));
      const auth = new google.auth.GoogleAuth({
        credentials: credentials,
        scopes: ['https://www.googleapis.com/auth/calendar']
      });
      this.calendar = google.calendar({ version: 'v3', auth });
      botLogger.businessEvent('calendar_initialized');
    } catch (error) {
      botLogger.botError(error, { service: 'calendar_initialization' });
    }
  }

  async getAvailableSlots() {
    if (!this.calendar) return [];

    const startTime = Date.now();

    try {
      const now = moment().tz(config.calendar.timezone);
      const endTime = moment().tz(config.calendar.timezone)
        .add(config.calendar.daysAhead, 'days');

      const response = await this.calendar.events.list({
        calendarId: process.env.GOOGLE_CALENDAR_ID || 'primary',
        timeMin: now.toISOString(),
        timeMax: endTime.toISOString(),
        singleEvents: true,
        orderBy: 'startTime'
      });

      const busySlots = response.data.items || [];
      const availableSlots = [];

      for (let day = 1; day <= config.calendar.daysAhead; day++) {
        const currentDay = moment().tz(config.calendar.timezone).add(day, 'days');
        
        if (!config.calendar.workingDays.includes(currentDay.day())) continue;

        for (const hour of config.calendar.availableSlots) {
          const slotStart = currentDay.clone().hour(hour).minute(0).second(0);
          const slotEnd = slotStart.clone().add(config.calendar.slotDuration, 'minutes');

          const isBooked = busySlots.some(event => {
            if (!event.start || !event.start.dateTime) return false;
            const eventStart = moment(event.start.dateTime);
            const eventEnd = moment(event.end.dateTime);
            return slotStart.isBetween(eventStart, eventEnd, null, '[)') ||
                   slotEnd.isBetween(eventStart, eventEnd, null, '(]') ||
                   (slotStart.isSameOrBefore(eventStart) && slotEnd.isSameOrAfter(eventEnd));
          });

          if (!isBooked && slotStart.isAfter(now)) {
            availableSlots.push(new Slot(slotStart, config.calendar.slotDuration));
          }
        }
      }

      const duration = Date.now() - startTime;
      botLogger.performance('calendar_check', duration, true);

      return availableSlots.slice(0, 3);
    } catch (error) {
      const duration = Date.now() - startTime;
      botLogger.performance('calendar_check', duration, false);
      botLogger.botError(error, { service: 'calendar_slots' });
      return [];
    }
  }

  async createEvent(leadData, slot) {
    if (!this.calendar) {
      botLogger.botError(new Error('Calendar not configured'));
      return null;
    }

    try {
      const startTime = moment(slot.datetime);
      const endTime = startTime.clone().add(config.calendar.slotDuration, 'minutes');

      const event = {
        summary: `${config.business.name} - ${leadData.name}`,
        description: `Sessione ${config.business.name}

Cliente: ${leadData.name}
Telefono: ${leadData.phone}
Obiettivo: ${leadData.goal || 'Da definire'}
Email: ${leadData.email || 'Non fornita'}

Tipo: ${leadData.isFirstSession ? 'PROVA GRATUITA' : 'Sessione regolare'}

Generato da ${config.personality.name}`,
        start: {
          dateTime: startTime.toISOString(),
          timeZone: config.calendar.timezone
        },
        end: {
          dateTime: endTime.toISOString(),
          timeZone: config.calendar.timezone
        },
        reminders: {
          useDefault: false,
          overrides: [
            { method: 'popup', minutes: 60 },
            { method: 'popup', minutes: 15 }
          ]
        }
      };

      const response = await this.calendar.events.insert({
        calendarId: process.env.GOOGLE_CALENDAR_ID || 'primary',
        resource: event
      });

      botLogger.businessEvent('booking_created', {
        eventId: response.data.id,
        clientName: leadData.name,
        datetime: slot.datetime
      });

      return response.data;
    } catch (error) {
      botLogger.botError(error, { service: 'calendar_create_event', leadData, slot });
      return null;
    }
  }
}

// Bot Engine Service
class BotEngine {
  constructor() {
    this.openAI = new OpenAIService();
  }

  analyzeIntent(message, conversation) {
    const lowerMessage = message.toLowerCase();
    
    if (this.containsAny(lowerMessage, ['prenota', 'prenotazione', 'slot', 'ora', 'orario', 'appuntamento', 'allenamento'])) {
      return 'booking';
    }
    
    if (this.containsAny(lowerMessage, ['prezzo', 'costo', 'abbonamento', 'quanto costa', 'tariffe'])) {
      return 'pricing';
    }
    
    if (this.containsAny(lowerMessage, ['servizi', 'cosa offrite', 'allenamenti', 'personal trainer'])) {
      return 'services';
    }
    
    if (this.containsAny(lowerMessage, ['orari', 'quando aperto', 'apertura', 'chiusura'])) {
      return 'hours';
    }
    
    if (conversation.messages.length <= 1) {
      return 'welcome';
    }
    
    if (conversation.leadData.stage === 'qualifying') {
      return 'qualifying';
    }
    
    return 'general';
  }

  extractInfo(message, leadData) {
    const updates = {};
    
    // Estrae nome
    const namePatterns = [
      /(?:sono|mi chiamo|il mio nome è)\s+([a-zA-ZÀ-ÿ\s]{2,30})/i,
      /^([a-zA-ZÀ-ÿ\s]{2,30})$/i
    ];
    
    for (const pattern of namePatterns) {
      const match = message.match(pattern);
      if (match && !leadData.name) {
        updates.name = this.cleanName(match[1]);
        break;
      }
    }
    
    // Estrae telefono
    const phoneMatch = message.match(/(\+?39\s?)?([0-9\s]{8,15})/);
    if (phoneMatch && !leadData.phone) {
      updates.phone = phoneMatch[0].replace(/\s/g, '');
    }
    
    // Estrae email
    const emailMatch = message.match(/([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/);
    if (emailMatch && !leadData.email) {
      updates.email = emailMatch[1].toLowerCase();
    }
    
    // Estrae obiettivi fitness
    if (message.toLowerCase().includes('perdere peso') || message.toLowerCase().includes('dimagrire')) {
      updates.goal = 'perdita peso';
    } else if (message.toLowerCase().includes('massa') || message.toLowerCase().includes('muscoli')) {
      updates.goal = 'aumento massa';
    } else if (message.toLowerCase().includes('tonificare') || message.toLowerCase().includes('definire')) {
      updates.goal = 'tonificazione';
    }
    
    return updates;
  }

  async generateResponse(intent, message, conversation) {
    const { leadData } = conversation;
    
    switch (intent) {
      case 'welcome':
        return this.handleWelcome(leadData);
      case 'qualifying':
        return this.handleQualifying(message, leadData);
      case 'booking':
        return this.handleBooking(leadData);
      case 'pricing':
        return this.handlePricing(leadData);
      case 'services':
        return this.handleServices(leadData);
      case 'hours':
        return this.handleHours();
      default:
        return await this.handleGeneral(message, conversation);
    }
  }

  handleWelcome(leadData) {
    const welcomeMessages = [
      "Ciao! Sono Giuseppe di Fitlab. Stai cercando un personal trainer per i tuoi allenamenti?",
      "Benvenuto in Fitlab! Ti aiuto a trovare il personal trainer perfetto per i tuoi obiettivi.",
      "Ciao! Giuseppe di Fitlab qui. Vuoi prenotare una sessione di allenamento personalizzato?"
    ];
    
    return welcomeMessages[Math.floor(Math.random() * welcomeMessages.length)];
  }

  handleQualifying(message, leadData) {
    const missingInfo = this.getMissingInfo(leadData);
    
    if (missingInfo.length === 0) {
      return this.buildRecommendation(leadData);
    }
    
    if (!leadData.name) {
      return "Perfetto! Come ti chiami?";
    }
    
    if (!leadData.goal) {
      return "Qual è il tuo obiettivo principale? Perdere peso, aumentare massa muscolare o tonificare?";
    }
    
    if (!leadData.phone) {
      return "Ottimo! Lasciami il tuo numero per confermare la prenotazione.";
    }
    
    return "Perfetto! Hai tutto quello che serve per iniziare.";
  }

  handleBooking(leadData) {
    if (!leadData.phone) {
      return "Per prenotare ho bisogno del tuo numero di telefono. Puoi condividerlo?";
    }
    
    return "booking_slots";
  }

  handlePricing(leadData) {
    const name = leadData.name ? `${leadData.name}, ` : '';
    return `${name}i nostri abbonamenti partono da 50€/mese. Abbiamo pacchetti personal trainer da 35€ a sessione. Ti interessa una prova gratuita?`;
  }

  handleServices(leadData) {
    return "Offriamo personal training personalizzato, piani alimentari, allenamenti di gruppo e consulenze fitness. Cosa ti interessa di più?";
  }

  handleHours() {
    return "Siamo aperti tutti i giorni dalle 6:00 alle 20:00. I nostri personal trainer sono disponibili su prenotazione in tutti gli orari.";
  }

  async handleGeneral(message, conversation) {
    const systemPrompt = this.buildSystemPrompt(conversation.leadData);
    
    try {
      const messages = conversation.messages.slice(-3).map(m => ({
        role: m.role === 'user' ? 'user' : 'assistant',
        content: m.content
      }));
      
      messages.push({ role: "user", content: message });
      
      return await this.openAI.generateResponse(systemPrompt, messages);
    } catch (error) {
      return config.autoResponses.fallback;
    }
  }

  buildSystemPrompt(leadData) {
    return `Sei Giuseppe, assistente di Fitlab, palestra specializzata in personal training.

SERVIZI FITLAB:
- Personal training personalizzato
- Slot orari flessibili (6:00-20:00)
- Abbonamenti palestra da 50€/mese
- Sessioni personal trainer da 35€

LEAD INFO:
- Nome: ${leadData.name || 'Non fornito'}
- Telefono: ${leadData.phone || 'Non fornito'}
- Obiettivo: ${leadData.goal || 'Non specificato'}
- Stage: ${leadData.stage}

REGOLE:
- Tono professionale ma amichevole
- NO emoji
- Massimo 160 caratteri
- Focus su prenotazione sessioni
- Se interessato: proponi prova gratuita
- Raccogli: nome, obiettivo, telefono

OBIETTIVO: Portare alla prenotazione di una sessione di prova gratuita`;
  }

  buildRecommendation(leadData) {
    const name = leadData.name ? `${leadData.name}, ` : '';
    let message = `${name}perfetto! `;
    
    if (leadData.goal === 'perdita peso') {
      message += 'I nostri personal trainer sono specializzati in programmi dimagrimento. ';
    } else if (leadData.goal === 'aumento massa') {
      message += 'Abbiamo trainer esperti in ipertrofia e aumento massa muscolare. ';
    } else if (leadData.goal === 'tonificazione') {
      message += 'I nostri programmi di tonificazione sono molto efficaci. ';
    }
    
    message += 'Ti va di prenotare una sessione di prova gratuita?';
    return message;
  }

  containsAny(text, triggers) {
    return triggers.some(trigger => text.includes(trigger));
  }

  getMissingInfo(leadData) {
    const required = ['name', 'goal', 'phone'];
    return required.filter(field => !leadData[field]);
  }

  cleanName(name) {
    return name.trim().replace(/\b\w/g, l => l.toUpperCase()).substring(0, 30);
  }
}

// Export services
const openAIService = new OpenAIService();
const whatsAppService = new WhatsAppService();
const calendarService = new CalendarService();
const botEngine = new BotEngine();

module.exports = {
  openAIService,
  whatsAppService,
  calendarService,
  botEngine
};