// server.js - Entry point per sistema multi-tenant
require('dotenv').config();
const app = require('./src/app');

const PORT = process.env.PORT || 3000;

// Validazione environment variables essenziali
const requiredEnvVars = [
  'TWILIO_ACCOUNT_SID',
  'TWILIO_AUTH_TOKEN', 
  'TWILIO_WHATSAPP_NUMBER'
];

console.log('🔍 Checking environment variables...');
const missingVars = requiredEnvVars.filter(varName => !process.env[varName]);

if (missingVars.length > 0) {
  console.error('❌ Missing required environment variables:', missingVars);
  console.error('💡 Please check your .env file');
  process.exit(1);
}

console.log('✅ All required environment variables found');

// Avvia server
app.listen(PORT, () => {
  console.log('\n🚀 Universal WhatsApp Bot Server Started!');
  console.log(`📡 Port: ${PORT}`);
  console.log(`🌍 Environment: ${process.env.NODE_ENV || 'development'}`);
  console.log(`📱 Twilio configured: ${process.env.TWILIO_ACCOUNT_SID ? 'Yes' : 'No'}`);
  console.log('\n📋 Available endpoints:');
  console.log(`   Health: http://localhost:${PORT}/health`);
  console.log(`   Webhook: http://localhost:${PORT}/webhook/{clientId}`);
  console.log(`   Stats: http://localhost:${PORT}/api/{clientId}/stats`);
  console.log(`   Global: http://localhost:${PORT}/api/global/stats`);
  console.log(`   Clients: http://localhost:${PORT}/api/clients`);
  console.log('\n💡 Example webhook format:');
  console.log(`   http://localhost:${PORT}/webhook/{clientId}`);
  console.log('\n🎯 Ready to serve unlimited clients!');
});