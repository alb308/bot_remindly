// promptBuilder.js - Costruisce prompt più umani per OpenAI
const config = require('./config');

class PromptBuilder {
  constructor() {
    this.config = config;
  }

  // Analizza il contesto della conversazione
  analyzeContext(messages) {
    const lastMessages = messages.slice(-5);
    const userMessages = lastMessages.filter(m => m.role === 'user');
    const botMessages = lastMessages.filter(m => m.role === 'assistant');
    
    // Conta quante volte abbiamo già chiesto certe cose
    const questionsAsked = {
      name: this._hasAskedFor(botMessages, ['come ti chiami', 'il tuo nome', 'posso sapere']),
      company: this._hasAskedFor(botMessages, ['azienda', 'lavori', 'società']),
      email: this._hasAskedFor(botMessages, ['email', 'mail', 'indirizzo']),
      demo: this._hasAskedFor(botMessages, ['demo', 'chiamata', 'appuntamento'])
    };
    
    // Identifica lo stato emotivo del cliente
    const lastUserMessage = userMessages[userMessages.length - 1]?.content || '';
    const sentiment = this._analyzeSentiment(lastUserMessage);
    
    return { questionsAsked, sentiment, messageCount: messages.length };
  }

  // Costruisce il prompt per OpenAI
  buildPrompt(messages, leadData) {
    const context = this.analyzeContext(messages);
    const stage = leadData.stage || 'initial';
    
    // Variazioni casuali per sembrare più umano
    const randomGreeting = this._getRandomPhrase('greetings');
    const randomQualifying = this._getRandomPhrase('qualifying');
    
    const prompt = `Sei ${config.bot.name}, un ${config.bot.role} di ${config.company.name}.

CONTESTO ATTUALE:
- Cliente: ${leadData.name || 'sconosciuto'}
- Azienda: ${leadData.company || 'non specificata'} 
- Email: ${leadData.email || 'non fornita'}
- Fase vendita: ${stage}
- Sentiment cliente: ${context.sentiment}
- Messaggi scambiati: ${context.messageCount}

PERSONALITÀ:
- Parla come una persona reale, non un bot
- Usa frasi brevi e dirette (max ${config.bot.responseStyle.maxLength} caratteri)
- ${config.bot.responseStyle.useEmoji ? 'Usa emoji con parsimonia' : 'NON usare emoji'}
- Sii ${config.bot.tone}
- Evita formule di cortesia eccessive
- Non ripetere concetti già detti

REGOLE CONVERSAZIONE:
1. Se non hai il nome, chiedilo in modo naturale
2. Se non sai l'azienda e hai il nome, chiedi dove lavora
3. Una sola domanda per messaggio
4. Non essere insistente - se dice no, accetta
5. Proponi demo solo se c'è interesse reale
6. Rispondi sempre al punto, senza giri di parole

OBIETTIVO ATTUALE: ${this._getCurrentGoal(stage, leadData, context)}

ESEMPI DI STILE (usa questo tono):
- "Ciao Marco, piacere. Di cosa si occupa la tua azienda?"
- "Ah interessante. Quanti siete in team?"
- "Capisco. Avete mai perso scadenze importanti?"
- "Ti va se ne parliamo 15 minuti giovedì?"

CONVERSAZIONE FINO AD ORA:
${messages.slice(-3).map(m => `${m.role === 'user' ? 'Cliente' : config.bot.name}: ${m.content}`).join('\n')}

IMPORTANTE: Rispondi SOLO come ${config.bot.name}, in modo naturale e diretto.`;

    return prompt;
  }

  // Determina l'obiettivo corrente basato su stage e contesto
  _getCurrentGoal(stage, leadData, context) {
    if (!leadData.name) {
      return "Scopri come si chiama il cliente in modo naturale";
    }
    
    if (!leadData.company && context.messageCount > 2) {
      return "Chiedi dove lavora o di cosa si occupa";
    }
    
    if (!leadData.email && stage === 'booking') {
      return "Ottieni l'email per inviare l'invito";
    }
    
    if (stage === 'discovery' && !leadData.needs) {
      return "Capire quali problemi hanno con la gestione del tempo/promemoria";
    }
    
    if (leadData.needs && !context.questionsAsked.demo) {
      return "Proporre una demo veloce se c'è fit";
    }
    
    return "Mantenere conversazione naturale e rispondere alle domande";
  }

  // Analizza il sentiment del messaggio
  _analyzeSentiment(message) {
    const negative = ['no', 'non', 'basta', 'smetti', 'fastidio'];
    const positive = ['si', 'ok', 'interessante', 'dimmi', 'curioso'];
    
    const lowerMessage = message.toLowerCase();
    
    if (negative.some(word => lowerMessage.includes(word))) {
      return 'negativo';
    }
    
    if (positive.some(word => lowerMessage.includes(word))) {
      return 'positivo';
    }
    
    return 'neutro';
  }

  // Controlla se abbiamo già chiesto qualcosa
  _hasAskedFor(messages, keywords) {
    return messages.some(msg => 
      keywords.some(keyword => 
        msg.content.toLowerCase().includes(keyword)
      )
    );
  }

  // Prende una frase casuale dalla configurazione
  _getRandomPhrase(category) {
    const phrases = config.phrases[category];
    if (!phrases || phrases.length === 0) return '';
    return phrases[Math.floor(Math.random() * phrases.length)];
  }

  // Gestisce le obiezioni in modo naturale
  handleObjection(objectionType) {
    return config.phrases.objectionHandling[objectionType] || 
           "Capisco perfettamente. Nessun problema.";
  }
}

module.exports = PromptBuilder;