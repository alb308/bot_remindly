// src/utils/logger.js - Sistema di logging professionale
const winston = require('winston');
const path = require('path');

// Configurazione logger
const logger = winston.createLogger({
  level: process.env.LOG_LEVEL || 'info',
  format: winston.format.combine(
    winston.format.timestamp({
      format: 'YYYY-MM-DD HH:mm:ss'
    }),
    winston.format.errors({ stack: true }),
    winston.format.json()
  ),
  defaultMeta: { 
    service: 'whatsapp-bot',
    version: process.env.npm_package_version || '1.0.0'
  },
  transports: [
    // Console output per development
    new winston.transports.Console({
      format: winston.format.combine(
        winston.format.colorize(),
        winston.format.simple(),
        winston.format.printf(({ level, message, timestamp, ...meta }) => {
          return `${timestamp} [${level}]: ${message} ${Object.keys(meta).length ? JSON.stringify(meta, null, 2) : ''}`;
        })
      )
    })
  ]
});

// In produzione, aggiungi file logging
if (process.env.NODE_ENV === 'production') {
  logger.add(new winston.transports.File({
    filename: path.join('logs', 'error.log'),
    level: 'error',
    maxsize: 5242880, // 5MB
    maxFiles: 5
  }));
  
  logger.add(new winston.transports.File({
    filename: path.join('logs', 'combined.log'),
    maxsize: 5242880, // 5MB
    maxFiles: 5
  }));
}

// Metodi helper per logging strutturato
const botLogger = {
  // Log messaggio ricevuto
  messageReceived: (userId, message, profileName) => {
    logger.info('Message received', {
      userId,
      message: message.substring(0, 100), // Primi 100 caratteri per privacy
      profileName,
      timestamp: new Date().toISOString()
    });
  },

  // Log risposta inviata
  messageSent: (userId, response, hasButtons = false) => {
    logger.info('Message sent', {
      userId,
      response: response.substring(0, 100),
      hasButtons,
      timestamp: new Date().toISOString()
    });
  },

  // Log errori specifici del bot
  botError: (error, context = {}) => {
    logger.error('Bot error', {
      error: error.message,
      stack: error.stack,
      context,
      timestamp: new Date().toISOString()
    });
  },

  // Log conversioni (lead qualificato, booking, ecc.)
  conversion: (type, userId, data = {}) => {
    logger.info('Conversion event', {
      type, // 'lead_qualified', 'booking_made', 'demo_requested'
      userId,
      data,
      timestamp: new Date().toISOString()
    });
  },

  // Log performance (tempo risposta AI, ecc.)
  performance: (operation, duration, success = true) => {
    logger.info('Performance metric', {
      operation, // 'openai_request', 'calendar_check', 'db_query'
      duration,
      success,
      timestamp: new Date().toISOString()
    });
  },

  // Log eventi business importanti
  businessEvent: (event, details = {}) => {
    logger.info('Business event', {
      event, // 'new_lead', 'booking_confirmed', 'payment_received'
      details,
      timestamp: new Date().toISOString()
    });
  }
};

// Export sia winston che i metodi helper
module.exports = {
  logger,
  botLogger
};