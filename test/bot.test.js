// tests/bot.test.js - Unit tests for bot engine
const { botEngine } = require('../src/services');
const { Conversation, Lead } = require('../src/models');

describe('BotEngine', () => {
  let mockConversation;
  let mockLead;

  beforeEach(() => {
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
  });

  describe('extractInfo', () => {
    test('should extract name from message', () => {
      const message = 'Ciao, sono Marco Rossi';
      const info = botEngine.extractInfo(message, mockLead);
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
  });

  describe('handleWelcome', () => {
    test('should return welcome message', () => {
      const response = botEngine.handleWelcome(mockLead);
      expect(response).toContain('Giuseppe');
      expect(response).toContain('Fitlab');
    });
  });

  describe('handlePricing', () => {
    test('should return pricing information', () => {
      const response = botEngine.handlePricing(mockLead);
      expect(response).toContain('50€');
      expect(response).toContain('35€');
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
  });

  test('should update qualification status', () => {
    const lead = new Lead('Test User', '+39123456789');
    lead.updateData({ goal: 'perdita peso' });
    expect(lead.qualified).toBe(true);
  });

  test('should calculate qualification progress', () => {
    const lead = new Lead('Test User', '+39123456789');
    lead.updateData({ goal: 'perdita peso' });
    expect(lead.getQualificationProgress()).toBe(100);
  });
});

// tests/api.test.js - Integration tests
const request = require('supertest');
const app = require('../src/app');

describe('API Endpoints', () => {
  describe('GET /health', () => {
    test('should return health status', async () => {
      const response = await request(app)
        .get('/health')
        .expect(200);
      
      expect(response.body.status).toBe('OK');
      expect(response.body.service).toBe('WhatsApp Bot');
    });
  });

  describe('GET /api/conversations', () => {
    test('should return conversations list', async () => {
      const response = await request(app)
        .get('/api/conversations')
        .expect(200);
      
      expect(Array.isArray(response.body)).toBe(true);
    });
  });

  describe('GET /api/stats', () => {
    test('should return analytics stats', async () => {
      const response = await request(app)
        .get('/api/stats')
        .expect(200);
      
      expect(response.body).toHaveProperty('totalConversations');
      expect(response.body).toHaveProperty('totalLeads');
      expect(response.body).toHaveProperty('conversionRate');
    });
  });
});

// tests/validators.test.js - Validator tests
const validators = require('../src/utils/validators');

describe('Validators', () => {
  describe('validateWebhook', () => {
    test('should validate correct webhook data', () => {
      const validData = {
        From: 'whatsapp:+39123456789',
        Body: 'Test message',
        WaId: '123456789',
        ProfileName: 'Test User'
      };
      
      expect(() => validators.validateWebhook(validData)).not.toThrow();
    });

    test('should reject invalid phone format', () => {
      const invalidData = {
        From: 'invalid-phone',
        Body: 'Test message',
        WaId: '123456789',
        ProfileName: 'Test User'
      };
      
      expect(() => validators.validateWebhook(invalidData)).toThrow();
    });
  });

  describe('sanitizeMessage', () => {
    test('should remove HTML tags', () => {
      const maliciousMessage = '<script>alert("hack")</script>Hello';
      const sanitized = validators.sanitizeMessage(maliciousMessage);
      expect(sanitized).toBe('Hello');
    });

    test('should limit message length', () => {
      const longMessage = 'a'.repeat(2000);
      const sanitized = validators.sanitizeMessage(longMessage);
      expect(sanitized.length).toBeLessThanOrEqual(1000);
    });
  });
});

module.exports = {
  // Export for other test files if needed
};