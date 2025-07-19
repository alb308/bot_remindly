// src/controllers/webhookController.js
const express = require('express');
const router = express.Router();

router.post('/whatsapp', async (req, res) => {
  try {
    console.log('Webhook received:', req.body);
    res.status(200).send('OK');
  } catch (error) {
    console.error('Webhook error:', error);
    res.status(500).send('Error');
  }
});

module.exports = router;