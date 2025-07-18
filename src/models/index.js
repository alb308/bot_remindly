// src/models/index.js - Data models

class Conversation {
  constructor(userId, userPhone, profileName) {
    this.id = this.generateId();
    this.userId = userId;
    this.userPhone = userPhone;
    this.profileName = profileName;
    this.messages = [];
    this.leadData = new Lead(profileName, userPhone);
    this.createdAt = new Date();
    this.updatedAt = new Date();
    this.availableSlots = null;
  }

  addMessage(role, content, buttons = null) {
    this.messages.push({
      id: this.generateId(),
      role,
      content,
      buttons,
      timestamp: new Date()
    });
    this.updatedAt = new Date();
  }

  generateId() {
    return Math.random().toString(36).substr(2, 9);
  }

  toJSON() {
    return {
      id: this.id,
      userId: this.userId,
      userPhone: this.userPhone,
      profileName: this.profileName,
      messagesCount: this.messages.length,
      leadData: this.leadData,
      createdAt: this.createdAt,
      updatedAt: this.updatedAt
    };
  }
}

class Lead {
  constructor(name, phone) {
    this.id = this.generateId();
    this.name = name;
    this.phone = phone;
    this.email = null;
    this.company = null;
    this.role = null;
    this.goal = null;
    this.stage = 'initial';
    this.source = 'whatsapp';
    this.qualified = false;
    this.createdAt = new Date();
    this.updatedAt = new Date();
  }

  updateData(updates) {
    Object.assign(this, updates);
    this.updatedAt = new Date();
    this.checkQualification();
  }

  checkQualification() {
    const requiredFields = ['name', 'phone', 'goal'];
    this.qualified = requiredFields.every(field => this[field]);
    return this.qualified;
  }

  getQualificationProgress() {
    const requiredFields = ['name', 'phone', 'goal'];
    const completedFields = requiredFields.filter(field => this[field]);
    return Math.round((completedFields.length / requiredFields.length) * 100);
  }

  generateId() {
    return Math.random().toString(36).substr(2, 9);
  }
}

class Booking {
  constructor(leadId, slotId, datetime) {
    this.id = this.generateId();
    this.leadId = leadId;
    this.slotId = slotId;
    this.datetime = datetime;
    this.status = 'pending';
    this.type = 'personal_training';
    this.duration = 60;
    this.isFirstSession = false;
    this.calendarEventId = null;
    this.createdAt = new Date();
    this.updatedAt = new Date();
  }

  confirm(calendarEventId = null) {
    this.status = 'confirmed';
    this.calendarEventId = calendarEventId;
    this.updatedAt = new Date();
  }

  cancel() {
    this.status = 'cancelled';
    this.updatedAt = new Date();
  }

  generateId() {
    return Math.random().toString(36).substr(2, 9);
  }
}

class Slot {
  constructor(datetime, duration = 60) {
    this.id = `slot_${datetime.format('YYYY-MM-DD-HH-mm')}`;
    this.datetime = datetime.toISOString();
    this.date = datetime.format('YYYY-MM-DD');
    this.time = datetime.format('HH:mm');
    this.display = datetime.format('dddd DD/MM - HH:mm');
    this.buttonText = datetime.format('ddd DD/MM HH:mm');
    this.duration = duration;
    this.available = true;
  }

  book() {
    this.available = false;
  }
}

// In-memory storage (temporaneo)
class DataStore {
  constructor() {
    this.conversations = new Map();
    this.leads = new Map();
    this.bookings = new Map();
  }

  // Conversations
  getConversation(userId) {
    return this.conversations.get(userId);
  }

  createConversation(userId, userPhone, profileName) {
    const conversation = new Conversation(userId, userPhone, profileName);
    this.conversations.set(userId, conversation);
    return conversation;
  }

  updateConversation(userId, updates) {
    const conversation = this.conversations.get(userId);
    if (conversation) {
      Object.assign(conversation, updates);
      conversation.updatedAt = new Date();
    }
    return conversation;
  }

  getAllConversations() {
    return Array.from(this.conversations.values());
  }

  // Leads
  createLead(leadData) {
    const lead = new Lead(leadData.name, leadData.phone);
    lead.updateData(leadData);
    this.leads.set(lead.id, lead);
    return lead;
  }

  // Bookings
  createBooking(leadId, slotId, datetime) {
    const booking = new Booking(leadId, slotId, datetime);
    this.bookings.set(booking.id, booking);
    return booking;
  }

  getBookingsByDate(date) {
    return Array.from(this.bookings.values())
      .filter(booking => booking.datetime.startsWith(date));
  }

  // Stats
  getStats() {
    const conversations = this.getAllConversations();
    const leads = Array.from(this.leads.values());
    const bookings = Array.from(this.bookings.values());

    return {
      totalConversations: conversations.length,
      totalLeads: leads.length,
      qualifiedLeads: leads.filter(l => l.qualified).length,
      totalBookings: bookings.length,
      confirmedBookings: bookings.filter(b => b.status === 'confirmed').length,
      conversionRate: leads.length > 0 ? 
        Math.round((bookings.length / leads.length) * 100) : 0
    };
  }
}

// Singleton instance
const dataStore = new DataStore();

module.exports = {
  Conversation,
  Lead,
  Booking,
  Slot,
  dataStore
};