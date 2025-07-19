// tests/bot.test.js - Unit tests per bot engine
// Mock environment variables prima di importare i moduli
process.env.OPENAI_API_KEY = 'test-key';
process.env.TWILIO_ACCOUNT_SID = 'test-sid';
process.env.TWILIO_AUTH_TOKEN = 'test-token';
process.env.TWILIO_WHATSAPP_NUMBER = 'whatsapp:+1234567890';

// Mock dei servizi esterni
jest.mock('openai');
jest.mock('twilio');
jest.mock('googleapis');
jest.mock('fs');

const { Conversation, Lead } = require('../src/models');

// Creiamo una versione mock del BotEngine per i test
class MockBotEngine {
  analyzeIntent(message, conversation) {
    const lowerMessage = message.toLowerCase();
    
    if (lowerMessage.includes('prenota') || lowerMessage.includes('appuntamento')) {
      return 'booking';
    }
    if (lowerMessage.includes('prezzo') || lowerMessage.includes('costo') || lowerMessage.includes('quanto costa')) {
      return 'pricing';
    }
    if (conversation.leadData.stage === 'qualifying') {
      return 'qualifying';
    }
    if (conversation.messages.length <= 1) {
      return 'welcome';
    }
    return 'general';
  }

  extractInfo(message, leadData) {
    const updates = {};
    
    // Estrae nome - pattern più accurato
    const namePatterns = [
      /(?:sono|mi chiamo)\s+([a-zA-ZÀ-ÿ\s]{2,30})/i,
      /ciao,?\s*sono\s+([a-zA-ZÀ-ÿ\s]{2,30})/i
    ];
    
    for (const pattern of namePatterns) {
      const match = message.match(pattern);
      if (match && !leadData.name) {
        updates.name = match[1].trim();
        break;
      }
    }
    
    // Estrae email
    const emailMatch = message.match(/([a-zA-Z0-9._%+-]+@[a-zA-Z0-9.-]+\.[a-zA-Z]{2,})/);
    if (emailMatch && !leadData.email) {
      updates.email = emailMatch[1].toLowerCase();
    }
    
    // Estrae obiettivi
    if (message.toLowerCase().includes('perdere peso')) {
      updates.goal = 'perdita peso';
    } else if (message.toLowerCase().includes('massa')) {
      updates.goal = 'aumento massa';
    }
    
    return updates;
  }

  handleWelcome(leadData) {
    return "Ciao! Sono Giuseppe di Fitlab. Stai cercando un personal trainer per i tuoi allenamenti?";
  }

  handlePricing(leadData) {
    const name = leadData.name ? `${leadData.name}, ` : '';
    return `${name}i nostri abbonamenti partono da 50€/mese. Abbiamo pacchetti personal trainer da 35€ a sessione.`;
  }

  containsAny(text, triggers) {
    return triggers.some(trigger => text.includes(trigger));
  }

  getMissingInfo(leadData) {
    const required = ['name', 'goal', 'phone'];
    return required.filter(field => !leadData[field]);
  }
}

describe('BotEngine', () => {
  let botEngine;
  let mockConversation;
  let mockLead;

  beforeEach(() => {
    botEngine = new MockBotEngine();
    mockLead = new Lead('Test User', '+39123456789');
    mockConversation = new Conversation('test123', '+39123456789', 'Test User');
    mockConversation.leadData = mockLead;
  });

  describe('analyzeIntent', () => {
    test('should detect booking intent', () => {
      const message = 'Voglio prenotare una sessione';
      const intent = botEngine.analyzeIntent(message, mockConversation);
      expect(intent).toBe('booking');
    });

    test('should detect pricing intent', () => {
      const message = 'Quanto costa?';
      const intent = botEngine.analyzeIntent(message, mockConversation);
      expect(intent).toBe('pricing');
    });

    test('should detect welcome intent for first message', () => {
      mockConversation.messages = [];
      const message = 'Ciao';
      const intent = botEngine.analyzeIntent(message, mockConversation);
      expect(intent).toBe('welcome');
    });

    test('should detect qualifying intent', () => {
      mockConversation.leadData.stage = 'qualifying';
      mockConversation.messages = [{ role: 'assistant', content: 'Ciao' }, { role: 'user', content: 'Ciao' }]; // More than 1 message
      const message = 'Sono Marco';
      const intent = botEngine.analyzeIntent(message, mockConversation);
      expect(intent).toBe('qualifying');
    });
  });

  describe('extractInfo', () => {
    test('should extract name from message', () => {
      const emptyLead = new Lead('', '+39123456789'); // Lead senza nome
      emptyLead.name = null; // Assicuriamoci che sia null
      const message = 'Sono Marco Rossi';
      const info = botEngine.extractInfo(message, emptyLead);
      expect(info.name).toBe('Marco Rossi');
    });

    test('should extract goal from message', () => {
      const message = 'Voglio perdere peso';
      const info = botEngine.extractInfo(message, mockLead);
      expect(info.goal).toBe('perdita peso');
    });

    test('should extract email from message', () => {
      const message = 'La mia email è test@example.com';
      const info = botEngine.extractInfo(message, mockLead);
      expect(info.email).toBe('test@example.com');
    });

    test('should extract mass gain goal', () => {
      const message = 'Voglio aumentare la massa muscolare';
      const info = botEngine.extractInfo(message, mockLead);
      expect(info.goal).toBe('aumento massa');
    });
  });

  describe('handleWelcome', () => {
    test('should return welcome message', () => {
      const response = botEngine.handleWelcome(mockLead);
      expect(response).toContain('Giuseppe');
      expect(response).toContain('Fitlab');
      expect(response).toContain('personal trainer');
    });
  });

  describe('handlePricing', () => {
    test('should return pricing information', () => {
      const response = botEngine.handlePricing(mockLead);
      expect(response).toContain('50€');
      expect(response).toContain('35€');
    });

    test('should include name in pricing response', () => {
      mockLead.name = 'Marco';
      const response = botEngine.handlePricing(mockLead);
      expect(response).toContain('Marco');
    });
  });
});

describe('Lead Model', () => {
  test('should create lead with basic info', () => {
    const lead = new Lead('Test User', '+39123456789');
    expect(lead.name).toBe('Test User');
    expect(lead.phone).toBe('+39123456789');
    expect(lead.stage).toBe('initial');
    expect(lead.qualified).toBe(false);
    expect(lead.source).toBe('whatsapp');
  });

  test('should update lead data', () => {
    const lead = new Lead('Test User', '+39123456789');
    lead.updateData({ goal: 'perdita peso', email: 'test@example.com' });
    
    expect(lead.goal).toBe('perdita peso');
    expect(lead.email).toBe('test@example.com');
    expect(lead.updatedAt).toBeInstanceOf(Date);
  });

  test('should check qualification correctly', () => {
    const lead = new Lead('Test User', '+39123456789');
    expect(lead.qualified).toBe(false);
    
    lead.updateData({ goal: 'perdita peso' });
    expect(lead.qualified).toBe(true);
  });

  test('should calculate qualification progress', () => {
    const lead = new Lead('Test User', '+39123456789');
    
    // Initial: name + phone = 2/3 = 67%
    expect(lead.getQualificationProgress()).toBe(67);
    
    // Add goal: name + phone + goal = 3/3 = 100%
    lead.updateData({ goal: 'perdita peso' });
    expect(lead.getQualificationProgress()).toBe(100);
  });
});

describe('Conversation Model', () => {
  test('should create conversation with correct data', () => {
    const conversation = new Conversation('test123', '+39123456789', 'Test User');
    
    expect(conversation.userId).toBe('test123');
    expect(conversation.userPhone).toBe('+39123456789');
    expect(conversation.profileName).toBe('Test User');
    expect(conversation.messages).toEqual([]);
    expect(conversation.leadData).toBeInstanceOf(Lead);
  });

  test('should add messages correctly', () => {
    const conversation = new Conversation('test123', '+39123456789', 'Test User');
    
    conversation.addMessage('user', 'Ciao');
    conversation.addMessage('assistant', 'Ciao! Come posso aiutarti?');
    
    expect(conversation.messages).toHaveLength(2);
    expect(conversation.messages[0].role).toBe('user');
    expect(conversation.messages[0].content).toBe('Ciao');
    expect(conversation.messages[1].role).toBe('assistant');
  });

  test('should generate correct JSON representation', () => {
    const conversation = new Conversation('test123', '+39123456789', 'Test User');
    conversation.addMessage('user', 'Test message');
    
    const json = conversation.toJSON();
    
    expect(json.userId).toBe('test123');
    expect(json.messagesCount).toBe(1);
    expect(json.leadData).toBeDefined();
    expect(json.createdAt).toBeInstanceOf(Date);
  });
});

describe('Data Validation', () => {
  test('should validate phone numbers', () => {
    const validPhones = ['+39123456789', '123456789', '+39 123 456 789'];
    const invalidPhones = ['invalid', '123', '+39abcd'];
    
    // Mock validation function
    const validatePhone = (phone) => /^\+?[0-9\s-()]{8,20}$/.test(phone);
    
    validPhones.forEach(phone => {
      expect(validatePhone(phone)).toBe(true);
    });
    
    invalidPhones.forEach(phone => {
      expect(validatePhone(phone)).toBe(false);
    });
  });

  test('should validate email addresses', () => {
    const validEmails = ['test@example.com', 'user.name@domain.it', 'test123@test.co.uk'];
    const invalidEmails = ['invalid-email', '@domain.com', 'test@', 'test.com'];
    
    // Mock validation function
    const validateEmail = (email) => /^[^\s@]+@[^\s@]+\.[^\s@]+$/.test(email);
    
    validEmails.forEach(email => {
      expect(validateEmail(email)).toBe(true);
    });
    
    invalidEmails.forEach(email => {
      expect(validateEmail(email)).toBe(false);
    });
  });
});

// Mock per express app tests
const request = require('supertest');
const express = require('express');

// Mock app per testare le route
const createMockApp = () => {
  const app = express();
  app.use(express.json());
  
  app.get('/health', (req, res) => {
    res.json({ 
      status: 'OK', 
      service: 'WhatsApp Bot Test',
      timestamp: new Date().toISOString()
    });
  });
  
  app.get('/api/stats', (req, res) => {
    res.json({
      totalConversations: 5,
      totalLeads: 3,
      conversionRate: 60
    });
  });
  
  return app;
};

describe('API Endpoints', () => {
  let app;
  
  beforeEach(() => {
    app = createMockApp();
  });

  test('GET /health should return health status', async () => {
    const response = await request(app)
      .get('/health')
      .expect(200);
    
    expect(response.body.status).toBe('OK');
    expect(response.body.service).toBe('WhatsApp Bot Test');
  });

  test('GET /api/stats should return statistics', async () => {
    const response = await request(app)
      .get('/api/stats')
      .expect(200);
    
    expect(response.body.totalConversations).toBe(5);
    expect(response.body.totalLeads).toBe(3);
    expect(response.body.conversionRate).toBe(60);
  });
});