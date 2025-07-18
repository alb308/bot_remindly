// src/controllers/apiController.js  
const express = require('express');
const router = express.Router();
const { dataStore } = require('../models');
const { calendarService, whatsAppService } = require('../services');

// Get all conversations
router.get('/conversations', (req, res) => {
  try {
    const conversations = dataStore.getAllConversations();
    const conversationsData = conversations.map(conv => ({
      ...conv.toJSON(),
      qualification: conv.leadData.getQualificationProgress()
    }));
    
    res.json(conversationsData);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Get conversation by ID
router.get('/conversations/:id', (req, res) => {
  try {
    const conversation = dataStore.getConversation(req.params.id);
    if (!conversation) {
      return res.status(404).json({ error: 'Conversation not found' });
    }
    
    res.json(conversation);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Get available calendar slots
router.get('/calendar/slots', async (req, res) => {
  try {
    const slots = await calendarService.getAvailableSlots();
    res.json({ 
      available: slots.length > 0, 
      slots,
      count: slots.length 
    });
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Get analytics/stats
router.get('/stats', (req, res) => {
  try {
    const stats = dataStore.getStats();
    res.json(stats);
  } catch (error) {
    res.status(500).json({ error: error.message });
  }
});

// Test message endpoint
router.post('/test/send', async (req, res) => {
  try {
    const { to, message } = req.body;
    
    if (!to || !message) {
      return res.status(400).json({ error: 'Missing to or message parameter' });
    }
    
    const result = await whatsAppService.sendMessage(to, message);
    
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

module.exports = router;