// src/app.js - Express app setup
const express = require('express');
const cors = require('cors');
const helmet = require('helmet');
const { logger, botLogger } = require('./utils/logger');
const webhookController = require('./controllers/webhookController');
const apiController = require('./controllers/apiController');

const app = express();

// Middleware
app.use(helmet());
app.use(cors());
app.use(express.json());
app.use(express.urlencoded({ extended: true }));

// Request logging
app.use((req, res, next) => {
  logger.info(`${req.method} ${req.path}`, {
    ip: req.ip,
    userAgent: req.get('User-Agent')
  });
  next();
});

// Routes
app.use('/webhook', webhookController);
app.use('/api', apiController);

// Health check
app.get('/health', (req, res) => {
  res.json({ 
    status: 'OK', 
    timestamp: new Date().toISOString(),
    service: 'WhatsApp Bot',
    version: process.env.npm_package_version || '1.0.0'
  });
});

// Error handling
app.use((err, req, res, next) => {
  botLogger.botError(err, {
    path: req.path,
    method: req.method,
    body: req.body
  });
  
  res.status(500).json({ 
    error: process.env.NODE_ENV === 'production' 
      ? 'Internal server error' 
      : err.message 
  });
});

// 404 handler
app.use((req, res) => {
  res.status(404).json({ error: 'Endpoint not found' });
});

module.exports = app;