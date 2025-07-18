# WhatsApp Sales Bot 🤖

Bot WhatsApp intelligente per vendite con AI e integrazione calendario. Progetto professionale con architettura modulare, testing e logging avanzato.

## 🚀 Features

- **Bot WhatsApp Intelligente**: Conversazioni naturali con OpenAI GPT
- **Qualificazione Lead Automatica**: Raccolta progressiva di informazioni cliente
- **Integrazione Calendario**: Prenotazioni automatiche con Google Calendar
- **Analytics e Logging**: Tracking completo di conversazioni e conversioni
- **Architettura Modulare**: Codice scalabile e manutenibile
- **Testing Completo**: Unit e integration tests
- **Validazione Input**: Sicurezza e robustezza

## 📁 Struttura Progetto

```
src/
├── config/          # Configurazioni
├── controllers/     # Logica HTTP routes
├── models/          # Modelli dati
├── services/        # Servizi business
├── utils/           # Utilità e validatori
└── app.js          # Setup Express

tests/              # Test suite
docs/               # Documentazione
logs/               # File di log
```

## 🛠️ Setup

### 1. Installazione
```bash
git clone <repo>
cd whatsapp-bot
npm install
```

### 2. Configurazione Environment
```bash
cp .env.example .env
# Configura le variabili in .env
```

### 3. Credenziali Google Calendar
- Crea progetto su Google Cloud Console
- Abilita Calendar API
- Scarica `google-credentials.json` nella root

### 4. Configurazione Twilio
- Account Twilio con WhatsApp sandbox
- Configura webhook: `https://your-domain.com/webhook/whatsapp`

## 🎯 Configurazione Business

Modifica `src/config/business.js`:

```javascript
module.exports = {
  business: {
    name: "La Tua Azienda",
    description: "descrizione servizio",
    // ...
  },
  personality: {
    name: "Nome Bot",
    role: "ruolo",
    // ...
  }
  // ...
}
```

## 💻 Comandi

```bash
# Development
npm run dev

# Production
npm start

# Testing
npm test
npm run test:watch
npm run test:coverage

# Linting
npm run lint
npm run lint:fix
```

## 📊 API Endpoints

### Webhook
- `POST /webhook/whatsapp` - Webhook Twilio

### Analytics
- `GET /api/conversations` - Lista conversazioni
- `GET /api/conversations/:id` - Dettaglio conversazione
- `GET /api/stats` - Statistiche aggregate
- `GET /api/calendar/slots` - Slot disponibili

### Testing
- `POST /api/test/send` - Invio messaggio test

## 🔧 Architettura

### Services Layer
- **BotEngine**: Logica conversazione e AI
- **WhatsAppService**: Gestione messaggi Twilio
- **CalendarService**: Integrazione Google Calendar
- **OpenAIService**: Interazioni con GPT

### Models Layer
- **Conversation**: Gestione conversazioni
- **Lead**: Qualificazione prospect
- **Booking**: Prenotazioni calendario
- **DataStore**: Storage in-memory (temporaneo)

### Utils Layer
- **Logger**: Sistema logging strutturato
- **Validators**: Validazione e sanitizzazione input

## 📈 Analytics e Logging

Il sistema traccia automaticamente:

- **Conversazioni**: Messaggi, risposte, intent
- **Lead**: Qualificazione, progressione
- **Conversioni**: Booking, demo richieste
- **Performance**: Tempi risposta AI, errori
- **Business Events**: Eventi importanti

Esempio log:
```json
{
  "level": "info",
  "message": "Conversion event",
  "type": "booking_made",
  "userId": "123456789",
  "data": { "slotId": "slot_2024-01-15-14-00" }
}
```

## 🧪 Testing

```bash
# Run all tests
npm test

# Specific test files
npm test -- bot.test.js
npm test -- api.test.js

# Coverage report
npm run test:coverage
```

Test coverage include:
- Unit tests per BotEngine
- Integration tests per API
- Validation tests per input sanitization

## 🚀 Deploy Production

### Railway (Consigliato)
```bash
# Install Railway CLI
npm install -g @railway/cli

# Login and deploy
railway login
railway init
railway up
```

### Environment Variables Production
Configura su Railway:
- `NODE_ENV=production`
- `TWILIO_*` - Credenziali Twilio
- `OPENAI_API_KEY` - Chiave OpenAI
- `GOOGLE_CALENDAR_ID` - ID calendario

## 📝 Customizzazione

### Nuovo Cliente
1. Modifica `src/config/business.js`
2. Personalizza logica in `src/services/BotEngine.js`
3. Aggiorna validatori se necessario
4. Deploy

### Nuove Funzionalità
1. Aggiungi service in `src/services/`
2. Aggiorna controller in `src/controllers/`
3. Scrivi tests in `tests/`
4. Aggiorna documentazione

## 🔒 Sicurezza

- Input sanitization automatica
- Validazione dati con Joi
- Rate limiting (da implementare)
- CORS e Helmet configurati
- Logging sicuro (no dati sensibili)

## 📚 Prossimi Step

- [ ] Database PostgreSQL
- [ ] Sistema multi-tenant
- [ ] Dashboard web cliente
- [ ] Integrazione pagamenti Stripe
- [ ] Rate limiting e cache Redis
- [ ] Deploy automatico CI/CD
- [ ] Monitoring e alerting

## 🤝 Contribuire

1. Fork del repository
2. Crea feature branch
3. Commit modifiche
4. Push e crea Pull Request
5. Tests devono passare

## 📄 License

MIT License - vedi LICENSE file

## 📞 Support

- GitHub Issues per bug e feature requests
- Documentation: `/docs` folder
- Examples: `/examples` folder