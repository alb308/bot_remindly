// src/config/business.js - Configurazione business
module.exports = {
  business: {
    name: "Fitlab",
    description: "personal trainer, prenota la tua ora in palestra personale",
    industry: "Bodybuilding",
    website: "https://fitlab.com",
    services: [
      "Slot orari",
      "prezzi palestra abbonamenti"
    ],
    benefits: [
      "automatizazzione"
    ]
  },

  personality: {
    name: "Giuseppe",
    role: "assisente",
    tone: "professionale ma amichevole",
    introduction: "Ciao! Sono Giuseppe di Fitlab. Ti aiuto a scoprire come personal trainer, prenota la tua ora in palestra personale può migliorare la tua situazione.",
    style: {
      useEmojis: false,
      maxMessageLength: 160,
      language: "italiano",
      formality: "tu",
      questions_per_message: 1
    }
  },

  salesFlow: {
    qualification: {
      required: ["name", "company", "role"],
      optional: ["email", "phone", "team_size", "current_tools"]
    },
    questions: {
      name: "Come ti chiami?",
      company: "Per quale azienda lavori?", 
      role: "Che ruolo ricopri?",
      pain_points: "Quali sono le tue principali sfide in questo ambito?",
      team_size: "Quante persone siete nel team?",
      budget: "Hai un budget definito per questa tipologia di strumenti?",
      timeline: "Quando vorresti implementare una soluzione?"
    },
    stages: {
      welcome: "Immagino tu sia qui perché vuoi migliorare personal trainer, prenota la tua ora in palestra personale, giusto?",
      qualifying: "Perfetto! Per consigliarti al meglio, dimmi:",
      presenting: "Basandomi su quello che mi hai detto, Fitlab può aiutarti a:",
      closing: "Ti va di fare una demo personalizzata? Posso mostrarti esattamente come risolveremmo i tuoi problemi specifici."
    }
  },

  calendar: {
    timezone: "Europe/Rome",
    workingHours: {
      start: 6,
      end: 20
    },
    workingDays: [1, 2, 3, 4, 5, 6, 0],
    slotDuration: 60,
    availableSlots: [6, 7, 8, 9, 10, 11, 12, 13, 14, 15, 16, 17, 18, 19, 20],
    daysAhead: 7
  },

  autoResponses: {
    fallback: "Non sono sicuro di aver capito. Puoi essere più specifico?",
    booking_confirmed: "Perfetto! Ho prenotato la demo per {date} alle {time}. Ti invierò tutti i dettagli via email.",
    no_slots: "Al momento non ho slot disponibili. Ti contatto via email per trovare un orario che funzioni per entrambi.",
    technical_error: "C'è stato un piccolo problema tecnico. Ti contatterò direttamente per la demo. Grazie per la pazienza!"
  },

  triggers: {
    demo: ["demo", "chiamata", "appuntamento", "incontro", "presentazione", "mostrami"],
    pricing: ["prezzo", "costo", "quanto costa", "tariffe", "piano"],
    features: ["funzioni", "caratteristiche", "cosa fa", "come funziona"],
    integration: ["integrazione", "collegare", "connettere", "sincronizzare"],
    competitor: ["competitor", "alternativa", "vs", "confronto"]
  }
};