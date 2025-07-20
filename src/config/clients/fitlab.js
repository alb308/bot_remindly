// src/config/clients/fitlab.js - Configurazione specifica per Fitlab
const gymTemplate = require('../templates/gym');

module.exports = {
  // Eredita dal template palestre
  ...gymTemplate,
  
  // Override specifici per Fitlab
  businessName: "Fitlab",
  businessType: "Palestra Premium", 
  location: "Milano Centro",
  
  // Personalizzazioni Fitlab
  variables: {
    ...gymTemplate.variables,
    assistantName: "Giuseppe",
    price: "35€ a sessione",
    hours: "6:00-20:00 tutti i giorni",
    location: "Milano, zona Porta Garibaldi",
    specialty: "personal training e aumento massa muscolare"
  },
  
  // Servizi specifici Fitlab
  services: [
    "Personal Training 1:1",
    "Piani alimentari personalizzati", 
    "Consulenza posturale",
    "Allenamenti di gruppo"
  ],
  
  // Specialità Fitlab
  specialties: [
    "Aumento massa muscolare",
    "Definizione e cutting",
    "Ricomposizione corporea",
    "Preparazione atletica"
  ],
  
  // FAQ personalizzate
  faq: {
    ...gymTemplate.faq,
    prezzo: "Personal training a 35€/sessione. Prima prova gratuita sempre!",
    trainer: "Giuseppe è certificato CONI e specializzato in bodybuilding e powerlifting.",
    risultati: "I miei clienti vedono risultati in 4-6 settimane con il mio metodo.",
    alimentazione: "Includo sempre un piano alimentare personalizzato nel programma."
  },
  
  // Stile comunicazione Fitlab
  communicationStyle: {
    tone: "amichevole ma professionale",
    language: "diretto e motivante", 
    personality: "esperto e appassionato"
  },
  
  // Configurazione calendario
  calendar: {
    timezone: "Europe/Rome",
    workingDays: [1, 2, 3, 4, 5, 6, 0], // Tutti i giorni
    workingHours: { start: 6, end: 20 },
    slotDuration: 60,
    availableSlots: [6, 7, 8, 9, 10, 11, 14, 15, 16, 17, 18, 19, 20]
  },
  
  // Configurazione WhatsApp
  whatsapp: {
    webhookPath: "/webhook/fitlab",
    responseDelay: 1000 // 1 secondo delay per sembrare più umano
  }
};