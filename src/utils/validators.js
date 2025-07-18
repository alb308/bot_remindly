// src/utils/validators.js - Validazioni input con Joi
const Joi = require('joi');

// Schema per validare webhook WhatsApp
const whatsappWebhookSchema = Joi.object({
  From: Joi.string()
    .pattern(/^whatsapp:\+[1-9]\d{1,14}$/)
    .required()
    .messages({
      'string.pattern.base': 'Formato numero WhatsApp non valido'
    }),
  
  Body: Joi.string()
    .min(1)
    .max(1000)
    .required()
    .messages({
      'string.min': 'Messaggio vuoto',
      'string.max': 'Messaggio troppo lungo (max 1000 caratteri)'
    }),
  
  WaId: Joi.string()
    .pattern(/^[0-9]{10,15}$/)
    .required(),
  
  ProfileName: Joi.string()
    .min(1)
    .max(100)
    .required()
});

// Schema per validare dati lead
const leadDataSchema = Joi.object({
  name: Joi.string()
    .min(2)
    .max(50)
    .pattern(/^[a-zA-ZÀ-ÿ\s]+$/)
    .messages({
      'string.pattern.base': 'Nome deve contenere solo lettere e spazi'
    }),
  
  phone: Joi.string()
    .pattern(/^\+?[0-9\s-()]{8,20}$/)
    .messages({
      'string.pattern.base': 'Formato telefono non valido'
    }),
  
  email: Joi.string()
    .email()
    .lowercase(),
  
  company: Joi.string()
    .min(2)
    .max(100),
  
  goal: Joi.string()
    .valid('perdita peso', 'aumento massa', 'tonificazione', 'fitness generale'),
  
  stage: Joi.string()
    .valid('initial', 'qualifying', 'booking', 'booked', 'converted')
    .default('initial')
});

// Schema per validare slot calendario
const slotSchema = Joi.object({
  id: Joi.string()
    .pattern(/^slot_\d{4}-\d{2}-\d{2}-\d{2}-\d{2}$/)
    .required(),
  
  datetime: Joi.string()
    .isoDate()
    .required(),
  
  display: Joi.string()
    .required(),
  
  buttonText: Joi.string()
    .max(20)
    .required()
});

// Schema per configurazione business
const businessConfigSchema = Joi.object({
  business: Joi.object({
    name: Joi.string().min(2).max(50).required(),
    description: Joi.string().min(10).max(200).required(),
    industry: Joi.string().min(2).max(50).required(),
    website: Joi.string().uri().optional(),
    services: Joi.array().items(Joi.string().min(3).max(100)).min(1).max(5),
    benefits: Joi.array().items(Joi.string().min(10).max(200)).min(1).max(5)
  }).required(),
  
  personality: Joi.object({
    name: Joi.string().min(2).max(30).required(),
    role: Joi.string().min(3).max(50).required(),
    tone: Joi.string().min(5).max(100).required()
  }).required(),
  
  calendar: Joi.object({
    timezone: Joi.string().valid('Europe/Rome').default('Europe/Rome'),
    workingHours: Joi.object({
      start: Joi.number().integer().min(0).max(23).required(),
      end: Joi.number().integer().min(1).max(24).required()
    }).required(),
    workingDays: Joi.array().items(Joi.number().integer().min(0).max(6)).min(1).max(7),
    slotDuration: Joi.number().integer().valid(30, 60, 90, 120).default(60),
    daysAhead: Joi.number().integer().min(1).max(30).default(7)
  }).required()
});

// Funzioni di validazione
const validators = {
  // Valida webhook WhatsApp
  validateWebhook: (data) => {
    const { error, value } = whatsappWebhookSchema.validate(data);
    if (error) {
      throw new Error(`Webhook validation failed: ${error.details[0].message}`);
    }
    return value;
  },

  // Valida e pulisce dati lead
  validateLead: (data) => {
    const { error, value } = leadDataSchema.validate(data, { 
      stripUnknown: true,
      abortEarly: false 
    });
    
    if (error) {
      const errors = error.details.map(detail => detail.message);
      throw new Error(`Lead validation failed: ${errors.join(', ')}`);
    }
    
    return value;
  },

  // Valida slot calendario
  validateSlot: (data) => {
    const { error, value } = slotSchema.validate(data);
    if (error) {
      throw new Error(`Slot validation failed: ${error.details[0].message}`);
    }
    return value;
  },

  // Valida configurazione business
  validateBusinessConfig: (data) => {
    const { error, value } = businessConfigSchema.validate(data, {
      stripUnknown: true,
      abortEarly: false
    });
    
    if (error) {
      const errors = error.details.map(detail => detail.message);
      throw new Error(`Business config validation failed: ${errors.join(', ')}`);
    }
    
    return value;
  },

  // Valida numero di telefono specifico per Italia
  validateItalianPhone: (phone) => {
    const italianPhoneRegex = /^(\+39)?[\s]?([0-9]{2,3})([\s]?)([0-9]{6,7})$/;
    return italianPhoneRegex.test(phone);
  },

  // Valida formato email specifico
  validateEmail: (email) => {
    const emailRegex = /^[^\s@]+@[^\s@]+\.[^\s@]+$/;
    return emailRegex.test(email);
  },

  // Sanitizza input per prevenire XSS
  sanitizeMessage: (message) => {
    return message
      .replace(/[<>]/g, '') // Rimuovi < e >
      .replace(/javascript:/gi, '') // Rimuovi javascript:
      .trim()
      .substring(0, 1000); // Limita lunghezza
  },

  // Valida orario slot (deve essere nel futuro e in orari lavorativi)
  validateSlotTime: (datetime, workingHours) => {
    const moment = require('moment-timezone');
    const slotTime = moment(datetime).tz('Europe/Rome');
    const now = moment().tz('Europe/Rome');
    
    // Controlla se è nel futuro
    if (!slotTime.isAfter(now)) {
      throw new Error('Lo slot deve essere nel futuro');
    }
    
    // Controlla se è in orari lavorativi
    const hour = slotTime.hour();
    if (hour < workingHours.start || hour >= workingHours.end) {
      throw new Error(`Lo slot deve essere tra le ${workingHours.start}:00 e le ${workingHours.end}:00`);
    }
    
    return true;
  }
};

module.exports = validators;