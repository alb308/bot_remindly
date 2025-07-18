// src/controllers/webhookController.js
const express = require('express');
const router = express.Router();
const { botLogger } = require('../utils/logger');
const validators = require('../utils/validators');
const { dataStore } = require('../models');
const { whatsAppService, calendarService, botEngine } = require('../services');

router.post('/whatsapp', async (req, res) => {
  try {
    // Validate webhook data
    const webhookData = validators.validateWebhook(req.body);
    const { From, Body, WaId, ProfileName } = webhookData;
    
    const userPhone = From.replace('whatsapp:', '');
    const userId = WaId || userPhone;
    const sanitizedMessage = validators.sanitizeMessage(Body);
    
    botLogger.messageReceived(userId, sanitizedMessage, ProfileName);
    
    // Get or create conversation
    let conversation = dataStore.getConversation(userId);
    if (!conversation) {
      conversation = dataStore.createConversation(userId, userPhone, ProfileName);
      botLogger.businessEvent('new_conversation', { userId, profileName: ProfileName });
    }
    
    // Add user message
    conversation.addMessage('user', sanitizedMessage);
    
    let response = '';
    let buttons = null;
    
    // Handle slot selection
    if (conversation.availableSlots && /^[1-3]$/.test(sanitizedMessage)) {
      const result = await handleSlotSelection(conversation, sanitizedMessage);
      response = result.response;
      buttons = result.buttons;
    } else {
      const result = await handleRegularMessage(conversation, sanitizedMessage);
      response = result.response;
      buttons = result.buttons;
    }
    
    // Send response
    await whatsAppService.sendMessage(userPhone, response, buttons);
    
    // Add bot response to conversation
    conversation.addMessage('assistant', response, buttons);
    
    botLogger.messageSent(userId, response, !!buttons);
    
    res.status(200).send('OK');
    
  } catch (error) {
    botLogger.botError(error, { body: req.body });
    res.status(500).send('Error');
  }
});

async function handleSlotSelection(conversation, message) {
  const slotIndex = parseInt(message) - 1;
  const selectedSlot = conversation.availableSlots[slotIndex];
  
  if (!selectedSlot) {
    return {
      response: `Scelta non valida. Scegli un numero da 1 a ${conversation.availableSlots.length}.`,
      buttons: null
    };
  }
  
  // Check if slot is still available
  const currentSlots = await calendarService.getAvailableSlots();
  const stillAvailable = currentSlots.some(slot => slot.id === selectedSlot.id);
  
  if (!stillAvailable) {
    const newSlots = await calendarService.getAvailableSlots();
    if (newSlots.length > 0) {
      conversation.availableSlots = newSlots;
      return {
        response: `Lo slot ${selectedSlot.display} non è più disponibile. Ecco gli slot aggiornati:`,
        buttons: newSlots.map(slot => ({ text: slot.buttonText }))
      };
    } else {
      delete conversation.availableSlots;
      return {
        response: 'Non ci sono slot disponibili al momento. Ti chiamo per fissare un orario.',
        buttons: null
      };
    }
  }
  
  // Create booking
  if (!conversation.leadData.hasBookedBefore) {
    conversation.leadData.isFirstSession = true;
    conversation.leadData.hasBookedBefore = true;
  }
  
  const booking = dataStore.createBooking(
    conversation.leadData.id, 
    selectedSlot.id, 
    selectedSlot.datetime
  );
  
  const event = await calendarService.createEvent(conversation.leadData, selectedSlot);
  
  if (event) {
    booking.confirm(event.id);
    conversation.leadData.stage = 'booked';
    conversation.leadData.appointmentDate = selectedSlot.datetime;
    
    botLogger.conversion('booking_made', conversation.userId, {
      slotId: selectedSlot.id,
      datetime: selectedSlot.datetime,
      isFirstSession: conversation.leadData.isFirstSession
    });
    
    const response = conversation.leadData.isFirstSession 
      ? `Perfetto! Sessione di PROVA GRATUITA prenotata per ${selectedSlot.display}. Ti chiamerò per confermare i dettagli. A presto in palestra!`
      : `Sessione personal training confermata per ${selectedSlot.display}. Ti aspettiamo in palestra!`;
    
    delete conversation.availableSlots;
    return { response, buttons: null };
  } else {
    return {
      response: 'Problema nella prenotazione. Ti chiamo subito per risolvere!',
      buttons: null
    };
  }
}

async function handleRegularMessage(conversation, message) {
  // Extract information from message
  const extractedInfo = botEngine.extractInfo(message, conversation.leadData);
  conversation.leadData.updateData(extractedInfo);
  
  // Analyze intent
  const intent = botEngine.analyzeIntent(message, conversation);
  
  // Update stage
  if (intent === 'booking' && conversation.leadData.stage === 'initial') {
    conversation.leadData.stage = 'booking';
  } else if (intent === 'qualifying' || extractedInfo.name) {
    conversation.leadData.stage = 'qualifying';
  }
  
  // Log lead progression
  if (extractedInfo.name && !conversation.leadData.name) {
    botLogger.conversion('lead_identified', conversation.userId, extractedInfo);
  }
  
  if (conversation.leadData.checkQualification()) {
    botLogger.conversion('lead_qualified', conversation.userId, {
      qualificationProgress: conversation.leadData.getQualificationProgress()
    });
  }
  
  // Generate response
  const botResponse = await botEngine.generateResponse(intent, message, conversation);
  
  if (botResponse === 'booking_slots') {
    if (conversation.leadData.phone) {
      const availableSlots = await calendarService.getAvailableSlots();
      
      if (availableSlots.length > 0) {
        conversation.availableSlots = availableSlots;
        return {
          response: 'Perfetto! Ecco i prossimi slot disponibili per la tua sessione:',
          buttons: availableSlots.map(slot => ({ text: slot.buttonText }))
        };
      } else {
        return {
          response: 'Non ci sono slot liberi al momento. Ti chiamo per trovare un orario perfetto!',
          buttons: null
        };
      }
    } else {
      return {
        response: 'Per prenotare la sessione ho bisogno del tuo numero. Puoi condividerlo?',
        buttons: null
      };
    }
  }
  
  return { response: botResponse, buttons: null };
}

module.exports = router;