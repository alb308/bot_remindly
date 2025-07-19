// src/controllers/apiController.js
const express = require('express');
const router = express.Router();

router.get('/stats', (req, res) => {
  res.json({ status: 'working' });
});

module.exports = router;