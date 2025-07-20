// src/core/BotEngine.js - Engine universale per tutti i settori
class UniversalBotEngine {
  constructor(clientConfig) {
    this.config = clientConfig;
    this.industry = clientConfig.industry;
    this.requiredFields = clientConfig.requiredFields;
    this.conversations = new Map();
  }

  // Processa un messaggio in arrivo
  processMessage(userId, message, profileName) {
    // Ottieni o crea conversazione
    let conversation = this.getOrCreateConversation(userId, profileName);
    
    // Aggiungi messaggio utente
    conversation.messages.push({
      role: 'user',
      content: message,
      timestamp: new Date()
    });
    
    // Estrai informazioni dal messaggio
    const extractedInfo = this.extractInformation(message, conversation);
    
    // Aggiorna dati lead
    Object.assign(conversation.leadData, extractedInfo);
    
    // Determina stage conversazione
    const stage = this.determineStage(conversation.leadData);
    
    // Genera risposta appropriata
    const response = this.generateResponse(stage, message, conversation, extractedInfo);
    
    // Aggiungi risposta bot
    conversation.messages.push({
      role: 'assistant', 
      content: response,
      timestamp: new Date()
    });
    
    return response;
  }

  // Ottieni o crea conversazione
  getOrCreateConversation(userId, profileName) {
    if (!this.conversations.has(userId)) {
      this.conversations.set(userId, {
        userId,
        profileName,
        messages: [],
        leadData: {
          profileName,
          stage: 'initial',
          createdAt: new Date()
        },
        startTime: new Date()
      });
    }
    return this.conversations.get(userId);
  }

  // Estrai informazioni basate sul settore
  extractInformation(message, conversation) {
    const updates = {};
    const lowerMessage = message.toLowerCase().trim();
    
    // Estrai nome (logica universale)
    if (!conversation.leadData.name && this.looksLikeName(message, conversation)) {
      updates.name = this.extractName(message);
    }
    
    // Estrai telefono (logica universale)
    if (!conversation.leadData.phone) {
      const phone = this.extractPhone(message);
      if (phone) updates.phone = phone;
    }
    
    // Estrai informazioni specifiche del settore
    const sectorInfo = this.extractSectorSpecificInfo(message, conversation);
    Object.assign(updates, sectorInfo);
    
    return updates;
  }

  // Estrai informazioni specifiche del settore
  extractSectorSpecificInfo(message, conversation) {
    const updates = {};
    const lowerMessage = message.toLowerCase();
    
    if (this.industry === 'fitness') {
      return this.extractFitnessInfo(lowerMessage, conversation);
    } else if (this.industry === 'dental') {
      return this.extractDentalInfo(lowerMessage, conversation);
    }
    
    return updates;
  }

  // Estrai info fitness
  extractFitnessInfo(lowerMessage, conversation) {
    const updates = {};
    
    if (!conversation.leadData.goal && this.config.goalRecognition) {
      for (const [goal, keywords] of Object.entries(this.config.goalRecognition)) {
        if (keywords.some(keyword => lowerMessage.includes(keyword))) {
          updates.goal = goal;
          break;
        }
      }
    }
    
    return updates;
  }

  // Estrai info dental
  extractDentalInfo(lowerMessage, conversation) {
    const updates = {};
    
    if (!conversation.leadData.issue && this.config.issueRecognition) {
      for (const [issue, keywords] of Object.entries(this.config.issueRecognition)) {
        if (keywords.some(keyword => lowerMessage.includes(keyword))) {
          updates.issue = issue;
          break;
        }
      }
    }
    
    return updates;
  }

  // Controlla se sembra un nome
  looksLikeName(message, conversation) {
    if (conversation.messages.length > 4) return false;
    
    const words = message.trim().split(' ');
    if (words.length > 2) return false;
    
    const word = words[0];
    if (word.length < 2) return false;
    
    // Deve contenere solo lettere
    if (!/^[a-zA-ZÀ-ÿ]+$/.test(word)) return false;
    
    // Non deve essere una parola comune
    const commonWords = ['ciao', 'salve', 'buongiorno', 'grazie', 'ok', 'sì', 'no'];
    return !commonWords.includes(word.toLowerCase());
  }

  // Estrai nome pulito
  extractName(message) {
    const word = message.trim().split(' ')[0];
    return word.charAt(0).toUpperCase() + word.slice(1).toLowerCase();
  }

  // Estrai telefono
  extractPhone(message) {
    const phoneMatch = message.match(/\b\d{10}\b/);
    return phoneMatch ? phoneMatch[0] : null;
  }

  // Determina stage della conversazione
  determineStage(leadData) {
    const completed = this.requiredFields.filter(field => leadData[field]);
    
    if (completed.length === 0) return 'welcome';
    if (completed.length < this.requiredFields.length) {
      const missing = this.requiredFields.find(field => !leadData[field]);
      return `collect_${missing}`;
    }
    return 'closing';
  }

  // Genera risposta appropriata
  generateResponse(stage, message, conversation, extractedInfo) {
    const lowerMessage = message.toLowerCase();
    
    // Gestisci FAQ
    const faqResponse = this.handleFAQ(lowerMessage);
    if (faqResponse) return faqResponse;
    
    // Gestisci obiezioni
    const objectionResponse = this.handleObjections(lowerMessage);
    if (objectionResponse) return objectionResponse;
    
    // Gestisci messaggi confusi
    if (this.isConfusedMessage(message)) {
      return this.handleConfusedMessage(stage, conversation);
    }
    
    // Genera risposta basata su stage
    return this.generateStageResponse(stage, conversation, extractedInfo);
  }

  // Gestisci FAQ
  handleFAQ(lowerMessage) {
    if (!this.config.faq) return null;
    
    for (const [topic, response] of Object.entries(this.config.faq)) {
      if (lowerMessage.includes(topic) || 
          (topic === 'prezzo' && (lowerMessage.includes('costo') || lowerMessage.includes('quanto'))) ||
          (topic === 'orari' && (lowerMessage.includes('quando') || lowerMessage.includes('che ore')))) {
        return this.fillTemplate(response);
      }
    }
    return null;
  }

  // Gestisci obiezioni
  handleObjections(lowerMessage) {
    if (!this.config.objections) return null;
    
    for (const [objection, response] of Object.entries(this.config.objections)) {
      if (lowerMessage.includes(objection)) {
        return this.fillTemplate(response);
      }
    }
    return null;
  }

  // Controlla se è un messaggio confuso
  isConfusedMessage(message) {
    return message.length > 8 && !/[aeiouAEIOU]/.test(message);
  }

  // Gestisci messaggio confuso
  handleConfusedMessage(stage, conversation) {
    if (stage.includes('collect_phone')) {
      return "Non ho capito bene. Mi serve il tuo numero per contattarti.";
    }
    return "Non ho capito bene. Puoi ripetere?";
  }

  // Genera risposta basata su stage
  generateStageResponse(stage, conversation, extractedInfo) {
    const template = this.config.conversationFlow[stage];
    if (!template) {
      return "Come posso aiutarti?";
    }
    
    return this.fillTemplate(template, conversation.leadData);
  }

  // Riempi template con variabili
  fillTemplate(template, leadData = {}) {
    let filled = template;
    
    // Sostituisci variabili leadData
    for (const [key, value] of Object.entries(leadData)) {
      const placeholder = `{${key}}`;
      filled = filled.replace(new RegExp(placeholder, 'g'), value || '');
    }
    
    // Sostituisci variabili config
    for (const [key, value] of Object.entries(this.config.variables || {})) {
      const placeholder = `{${key}}`;
      filled = filled.replace(new RegExp(placeholder, 'g'), value || '');
    }
    
    // Sostituisci business name
    filled = filled.replace(/{businessName}/g, this.config.businessName || '');
    
    return filled;
  }

  // Ottieni statistiche
  getStats() {
    const conversations = Array.from(this.conversations.values());
    const qualified = conversations.filter(conv => 
      this.requiredFields.every(field => conv.leadData[field])
    );
    
    return {
      totalConversations: conversations.length,
      qualifiedLeads: qualified.length,
      conversionRate: conversations.length > 0 ? 
        Math.round((qualified.length / conversations.length) * 100) : 0,
      averageMessages: conversations.length > 0 ?
        Math.round(conversations.reduce((sum, conv) => sum + conv.messages.length, 0) / conversations.length) : 0
    };
  }

  // Ottieni tutte le conversazioni
  getAllConversations() {
    return Array.from(this.conversations.values()).map(conv => ({
      ...conv,
      isQualified: this.requiredFields.every(field => conv.leadData[field]),
      stage: this.determineStage(conv.leadData)
    }));
  }
}

module.exports = UniversalBotEngine;