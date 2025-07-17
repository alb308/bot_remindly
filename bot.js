// bot.js - Engine del bot con risposte più umane
const config = require('./config');

class BotEngine {
  constructor(openai) {
    this.openai = openai;
    this.config = config;
  }

  // Analizza il messaggio dell'utente per capire l'intent
  analyzeIntent(message, conversation) {
    const lowerMessage = message.toLowerCase();
    
    // Intent demo/booking
    if (this.containsAny(lowerMessage, this.config.triggers.demo)) {
      return 'booking';
    }
    
    // Intent pricing
    if (this.containsAny(lowerMessage, this.config.triggers.pricing)) {
      return 'pricing';
    }
    
    // Intent features
    if (this.containsAny(lowerMessage, this.config.triggers.features)) {
      return 'features';
    }
    
    // Intent integration
    if (this.containsAny(lowerMessage, this.config.triggers.integration)) {
      return 'integration';
    }
    
    // Se è il primo messaggio
    if (conversation.messages.length <= 1) {
      return 'welcome';
    }
    
    // Se siamo in fase di qualificazione
    if (conversation.leadData.stage === 'qualifying') {
      return 'qualifying';
    }
    
    return 'general';
  }

  // Estrae informazioni dal messaggio
  extractInfo(message, leadData) {
    const updates = {};
    
    // Estrae nome
    const namePatterns = [
      /(?:sono|mi chiamo|il mio nome è)\s+([a-zA-ZÀ-ÿ\s]{2,30})/i,
      /^([a-zA-ZÀ-ÿ\s]{2,30})$/i // Se scrive solo il nome
    ];
    
    for (const pattern of namePatterns) {
      const match = message.match(pattern);
      if (match && !leadData.name) {
        updates.name = this.cleanName(match[1]);
        break;
      }
    }
    
    // Estrae azienda
    const companyPatterns = [
      /(?:lavoro|sono|work)\s+(?:in|da|per|at)\s+([a-zA-ZÀ-ÿ\s]{2,50})/i,
      /(?:azienda|company|ditta)\s+([a-zA-ZÀ-ÿ\s]{2,50})/i
    ];
    
    for (const pattern of companyPatterns) {
      const match = message.match(pattern);
      if (match && !leadData.company) {
        updates.company = this.cleanCompany(match[1]);
        break;
      }
    }
    
    // Estrae email
    const emailMatch = message.match(/([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/);
    if (emailMatch && !leadData.email) {
      updates.email = emailMatch[1].toLowerCase();
    }
    
    // Estrae ruolo
    const rolePatterns = [
      /(?:sono|faccio il|lavoro come)\s+(.*?)(?:\.|$|,)/i,
      /(?:ruolo|position|job)\s+([a-zA-ZÀ-ÿ\s]{2,50})/i
    ];
    
    for (const pattern of rolePatterns) {
      const match = message.match(pattern);
      if (match && !leadData.role) {
        updates.role = this.cleanRole(match[1]);
        break;
      }
    }
    
    return updates;
  }

  // Genera risposta basata su intent e contesto
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
        
      case 'features':
        return this.handleFeatures(message, leadData);
        
      case 'integration':
        return this.handleIntegration(leadData);
        
      default:
        return await this.handleGeneral(message, conversation);
    }
  }

  handleWelcome(leadData) {
    if (leadData.name) {
      return `Ciao ${leadData.name}! ${this.config.salesFlow.stages.welcome}`;
    }
    return this.config.salesFlow.stages.welcome;
  }

  handleQualifying(message, leadData) {
    // Se ha appena fornito informazioni, ringrazia e chiedi la prossima
    const missingInfo = this.getMissingInfo(leadData);
    
    if (missingInfo.length === 0) {
      // Ha tutte le info necessarie, passa alla presentazione
      return this.buildPresentationMessage(leadData);
    }
    
    // Chiedi la prossima informazione mancante
    const nextQuestion = this.config.salesFlow.questions[missingInfo[0]];
    return `Perfetto! ${nextQuestion}`;
  }

  handleBooking(leadData) {
    if (!leadData.email) {
      return "Ottimo! Per fissare la demo ho bisogno della tua email per inviarti i dettagli dell'appuntamento.";
    }
    
    return "booking_slots"; // Segnale per mostrare gli slot
  }

  handlePricing(leadData) {
    const name = leadData.name ? leadData.name : '';
    return `${name ? name + ', ' : ''}Remindly ha piani flessibili che partono da 9€/mese per utente. Il prezzo finale dipende dalle funzioni che ti servono. Ti va di fare una demo? Così posso consigliarti il piano più adatto.`;
  }

  handleFeatures(message, leadData) {
    // Risposte specifiche basate su cosa chiede
    if (message.includes('integraz')) {
      return 'Remindly si integra con Calendar, Slack, Teams, Trello e oltre 50 app. Quali strumenti usi ora?';
    }
    
    if (message.includes('AI') || message.includes('intelligente')) {
      return 'La nostra AI analizza i tuoi pattern e crea promemoria automatici. Per esempio, se hai sempre riunioni il lunedì, ti ricorderà di preparare i materiali ogni venerdì.';
    }
    
    return 'Remindly ti aiuta a non dimenticare mai nulla: promemoria intelligenti, task automatici, notifiche personalizzate. Quale aspetto ti interessa di più?';
  }

  handleIntegration(leadData) {
    return 'Remindly si connette facilmente ai tuoi strumenti attuali. Quali app usi per lavoro? Così ti spiego esattamente come funzionerebbe l\'integrazione.';
  }

  async handleGeneral(message, conversation) {
    // Usa OpenAI solo per conversazioni generali, con prompt migliorato
    const systemPrompt = this.buildSystemPrompt(conversation.leadData);
    
    try {
      const response = await this.openai.chat.completions.create({
        model: "gpt-4o-mini",
        messages: [
          { role: "system", content: systemPrompt },
          ...conversation.messages.slice(-3).map(m => ({
            role: m.role === 'user' ? 'user' : 'assistant',
            content: m.content
          })),
          { role: "user", content: message }
        ],
        max_tokens: 80,
        temperature: 0.7
      });
      
      return response.choices[0].message.content;
      
    } catch (error) {
      console.error('Errore OpenAI:', error);
      return this.config.autoResponses.fallback;
    }
  }

  buildSystemPrompt(leadData) {
    const business = this.config.business;
    const personality = this.config.personality;
    
    return `Sei ${personality.name}, ${personality.role} di ${business.name}.

BUSINESS: ${business.description}
SERVIZI: ${business.services.join(', ')}
BENEFICI: ${business.benefits.join(', ')}

LEAD INFO:
- Nome: ${leadData.name || 'Non fornito'}
- Azienda: ${leadData.company || 'Non fornita'}  
- Email: ${leadData.email || 'Non fornita'}
- Stage: ${leadData.stage}

REGOLE COMUNICAZIONE:
- Tono: ${personality.tone}
- NO emoji, NO linguaggio tecnico
- Massimo ${personality.style.maxMessageLength} caratteri
- Una domanda per volta
- Risposte dirette e chiare
- Obiettivo: qualificare il lead e proporre demo

COMPORTAMENTO:
- Se interessato ma non qualificato: fai domande per capire esigenze
- Se qualificato: proponi demo personalizzata
- Se tecnico: semplifica e dai benefici pratici
- Mantieni sempre focus su come ${business.name} risolve i suoi problemi`;
  }

  buildPresentationMessage(leadData) {
    const benefits = this.config.business.benefits;
    const name = leadData.name ? `${leadData.name}, ` : '';
    
    let message = `${name}perfetto! Basandomi su quello che mi hai detto, ${this.config.business.name} può aiutarti a: `;
    
    // Seleziona 2-3 benefici più rilevanti
    const relevantBenefits = benefits.slice(0, 2).join(' e ');
    message += relevantBenefits;
    
    message += '. Ti va di vedere una demo personalizzata?';
    
    return message;
  }

  // Utility functions
  containsAny(text, triggers) {
    return triggers.some(trigger => text.includes(trigger));
  }

  getMissingInfo(leadData) {
    return this.config.salesFlow.qualification.required.filter(field => !leadData[field]);
  }

  cleanName(name) {
    return name.trim().replace(/\b\w/g, l => l.toUpperCase()).substring(0, 30);
  }

  cleanCompany(company) {
    return company.trim().substring(0, 50);
  }

  cleanRole(role) {
    return role.trim().substring(0, 50);
  }

  getQualificationProgress(leadData) {
    const required = this.config.salesFlow.qualification.required;
    const completed = required.filter(field => leadData[field]);
    return Math.round((completed.length / required.length) * 100);
  }
}

module.exports = BotEngine;