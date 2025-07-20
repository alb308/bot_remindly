// src/config/templates/dental.js - Template per studi dentistici
module.exports = {
  industry: "dental",
  
  // Informazioni da raccogliere
  requiredFields: ["name", "issue", "phone"],
  optionalFields: ["urgency", "insurance", "last_visit"],
  
  // Flusso conversazione
  conversationFlow: {
    welcome: "Salve! Sono {assistantName} dello {businessName}. Come posso aiutarla?",
    collect_name: "Mi può dire il suo nome?",
    collect_issue: "Che tipo di problema dentale ha? Dolore, pulizia, estetica o controllo?",
    collect_phone: "Per fissare la visita, mi serve il suo numero di telefono.",
    closing: "Perfetto {name}! La ricontatto per la visita. Problema: {issue}, numero: {phone}."
  },
  
  // Riconoscimento problemi dentali
  issueRecognition: {
    "dolore": ["male", "dolore", "fa male", "duole", "dolente"],
    "pulizia": ["pulizia", "igiene", "tartaro", "placca"],
    "estetica": ["bianchi", "sbiancare", "estetica", "belli", "apparecchio"],
    "controllo": ["controllo", "visita", "check", "prevenzione"],
    "urgenza": ["urgente", "subito", "emergenza", "pronto soccorso"]
  },
  
  // Domande frequenti
  faq: {
    prezzo: "I prezzi variano per trattamento. La prima visita costa {visitPrice}.",
    orari: "Siamo aperti {hours}. Quando è più comodo per lei?",
    dove: "Siamo in {location}, facilmente raggiungibili.",
    dolore: "Per il dolore la riceviamo in urgenza. Ha preso antidolorifici?",
    paura: "Capisco la paura! Usiamo tecniche dolci e anestesia se necessario."
  },
  
  // Gestione obiezioni  
  objections: {
    "troppo caro": "La salute dentale è un investimento. Offriamo piani di pagamento personalizzati.",
    "ho paura": "È normale! Siamo specializzati in pazienti ansiosi. La metteremo a suo agio.",
    "non ho tempo": "Capiamo gli impegni. Abbiamo orari flessibili, anche serali.",
    "non è urgente": "La prevenzione è fondamentale! Un controllo ora evita problemi futuri."
  },
  
  // Variabili template
  variables: {
    assistantName: "Dott.ssa Maria",
    visitPrice: "80€",
    hours: "9:00-19:00",
    location: "centro storico",
    specialty: "odontoiatria moderna e indolore"
  }
};