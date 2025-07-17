// setup.js - Script per configurare rapidamente un nuovo cliente
const fs = require('fs');
const path = require('path');
const readline = require('readline');

const rl = readline.createInterface({
  input: process.stdin,
  output: process.stdout
});

function question(query) {
  return new Promise((resolve) => rl.question(query, resolve));
}

async function setupNewClient() {
  console.log('\n=== SETUP NUOVO CLIENTE BOT ===\n');
  
  try {
    // Raccolta informazioni business
    console.log('📋 INFORMAZIONI BUSINESS:');
    const businessName = await question('Nome business/prodotto: ');
    const businessDescription = await question('Descrizione breve (es: "app di promemoria intelligente"): ');
    const businessIndustry = await question('Settore/industria: ');
    const businessWebsite = await question('Sito web (opzionale): ');
    
    // Raccolta servizi (3 principali)
    console.log('\n🛠️  SERVIZI PRINCIPALI (inserisci 3):');
    const services = [];
    for (let i = 1; i <= 3; i++) {
      const service = await question(`Servizio ${i}: `);
      if (service.trim()) services.push(service.trim());
    }
    
    // Raccolta benefici (3 principali)
    console.log('\n✨ BENEFICI PRINCIPALI (inserisci 3):');
    const benefits = [];
    for (let i = 1; i <= 3; i++) {
      const benefit = await question(`Beneficio ${i}: `);
      if (benefit.trim()) benefits.push(benefit.trim());
    }
    
    // Raccolta personalità bot
    console.log('\n🤖 PERSONALITA\' BOT:');
    const botName = await question('Nome del bot (es: Andrea, Marco, Sofia): ');
    const botRole = await question('Ruolo bot (es: consulente, assistente, esperto): ');
    const botTone = await question('Tono comunicazione (es: professionale ma amichevole): ');
    
    // Raccolta setting calendario
    console.log('\n📅 IMPOSTAZIONI CALENDARIO:');
    const timezone = await question('Timezone (default: Europe/Rome): ') || 'Europe/Rome';
    const workStart = await question('Ora inizio lavoro (default: 9): ') || '9';
    const workEnd = await question('Ora fine lavoro (default: 18): ') || '18';
    
    // Genera config
    const config = {
      business: {
        name: businessName,
        description: businessDescription,
        industry: businessIndustry,
        website: businessWebsite || `https://${businessName.toLowerCase().replace(/\s+/g, '')}.com`,
        services: services,
        benefits: benefits
      },
      personality: {
        name: botName,
        role: botRole,
        tone: botTone,
        introduction: `Ciao! Sono ${botName} di ${businessName}. Ti aiuto a scoprire come ${businessDescription} può migliorare la tua situazione.`,
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
          welcome: `Immagino tu sia qui perché vuoi migliorare ${businessDescription.includes('la') ? 'la tua' : 'il tuo'} ${businessDescription.replace(/^(app|software|piattaforma|sistema) (di|per) /, '')}, giusto?`,
          qualifying: "Perfetto! Per consigliarti al meglio, dimmi:",
          presenting: `Basandomi su quello che mi hai detto, ${businessName} può aiutarti a:`,
          closing: "Ti va di fare una demo personalizzata? Posso mostrarti esattamente come risolveremmo i tuoi problemi specifici."
        }
      },
      calendar: {
        timezone: timezone,
        workingHours: {
          start: parseInt(workStart),
          end: parseInt(workEnd)
        },
        workingDays: [1, 2, 3, 4, 5],
        slotDuration: 30,
        availableSlots: [9, 11, 14, 16],
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
    
    // Salva config
    const configPath = path.join(__dirname, 'config.js');
    const configContent = `// config.js - Configurazione per ${businessName}
// Generato automaticamente il ${new Date().toLocaleDateString()}

module.exports = ${JSON.stringify(config, null, 2)};`;
    
    fs.writeFileSync(configPath, configContent);
    
    console.log('\n✅ CONFIGURAZIONE COMPLETATA!');
    console.log(`📁 File creato: ${configPath}`);
    console.log('\n📋 RIEPILOGO:');
    console.log(`🏢 Business: ${businessName}`);
    console.log(`🤖 Bot: ${botName} (${botRole})`);
    console.log(`🌍 Timezone: ${timezone}`);
    console.log(`⏰ Orari: ${workStart}:00 - ${workEnd}:00`);
    
    console.log('\n🚀 PROSSIMI PASSI:');
    console.log('1. Avvia il server: npm start');
    console.log('2. Configura webhook Twilio');
    console.log('3. Testa il bot');
    
    const createEnvExample = await question('\n❓ Vuoi che generi un file .env di esempio? (y/n): ');
    
    if (createEnvExample.toLowerCase() === 'y') {
      const envExample = `# .env di esempio per ${businessName}
PORT=3000
NODE_ENV=development

# Twilio WhatsApp
TWILIO_ACCOUNT_SID=ACxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_AUTH_TOKEN=xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
TWILIO_WHATSAPP_NUMBER=whatsapp:+14155238886

# OpenAI
OPENAI_API_KEY=sk-proj-xxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx

# Google Calendar
GOOGLE_CALENDAR_ID=primary
TIMEZONE=${timezone}

# Note:
# 1. Sostituisci i valori con le tue credenziali reali
# 2. Non committare questo file su Git
# 3. Aggiungi .env al .gitignore`;

      fs.writeFileSync('.env.example', envExample);
      console.log('📝 File .env.example creato');
    }
    
  } catch (error) {
    console.error('❌ Errore durante setup:', error.message);
  } finally {
    rl.close();
  }
}

// Avvia setup
if (require.main === module) {
  setupNewClient();
}

module.exports = { setupNewClient };