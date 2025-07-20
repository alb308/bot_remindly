// src/config/templates/gym.js - Template per palestre
module.exports = {
  industry: "fitness",
  
  // Informazioni da raccogliere
  requiredFields: ["name", "goal", "phone"],
  optionalFields: ["age", "experience", "availability"],
  
  // Flusso conversazione
  conversationFlow: {
    welcome: "Ciao! Sono {assistantName} di {businessName}. Come posso aiutarti con il tuo allenamento?",
    collect_name: "Come ti chiami?",
    collect_goal: "Qual è il tuo obiettivo? Aumentare massa, perdere peso, tonificare o mantenerti in forma?",
    collect_phone: "Per la tua prova gratuita, mi serve il tuo numero di telefono.",
    closing: "Perfetto {name}! Ti chiamo per fissare la prova gratuita. Obiettivo: {goal}, numero: {phone}."
  },
  
  // Riconoscimento obiettivi fitness
  goalRecognition: {
    "aumento massa": ["massa", "muscoli", "grosso", "enorme", "bulk", "ipertrofia"],
    "perdita peso": ["dimagrire", "peso", "grasso", "magro", "dieta"],
    "tonificazione": ["tonificare", "forma", "tonico", "definire"],
    "fitness generale": ["mantenermi", "forma", "salute", "benessere"]
  },
  
  // Domande frequenti
  faq: {
    prezzo: "Le sessioni costano {price}. La prima prova è gratuita!",
    orari: "Siamo aperti {hours}. Quando preferisci allenarti?",
    dove: "Siamo in {location}. Ti do l'indirizzo quando fissiamo!",
    attrezzature: "Abbiamo tutto: pesi liberi, macchine, cardio. Tutto quello che serve!",
    trainer: "I nostri trainer sono certificati e specializzati nel tuo obiettivo."
  },
  
  // Gestione obiezioni
  objections: {
    "troppo caro": "Capisco! Ma considera che investi nella tua salute. La prima prova è gratuita, che ne dici?",
    "non ho tempo": "Bastano 3 allenamenti a settimana di 45 minuti. Troveremo l'orario perfetto per te!",
    "sono principiante": "Perfetto! Amiamo i principianti. Ti seguiamo passo passo dall'inizio.",
    "già ho palestra": "Ottimo! Ma hai mai provato un personal trainer dedicato? Cambia tutto!"
  },
  
  // Variabili template
  variables: {
    assistantName: "Giuseppe",
    price: "35€ a sessione", 
    hours: "6:00-20:00",
    location: "centro città",
    specialty: "personal training personalizzato"
  }
};