const sqlite3 = require('sqlite3').verbose();
const path = require('path');

const dbPath = process.env.DB_FILE || path.join(__dirname, 'qbank.db');

const db = new sqlite3.Database(dbPath, (err) => {
  if (err) {
    console.error('Error opening database:', err.message);
  } else {
    console.log('Connected to SQLite database.');
  }
});

// Create tables
db.serialize(() => {
  // Users table
  db.run(`
    CREATE TABLE IF NOT EXISTS users (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      username TEXT UNIQUE NOT NULL,
      password_hash TEXT NOT NULL,
      email TEXT,
      created_at DATETIME DEFAULT CURRENT_TIMESTAMP
    )
  `);

  // Questions table
  db.run(`
    CREATE TABLE IF NOT EXISTS questions (
      id INTEGER PRIMARY KEY AUTOINCREMENT,
      user_id INTEGER NOT NULL,
      unit TEXT NOT NULL,
      skill TEXT NOT NULL,
      stimulus TEXT DEFAULT 'None',
      difficulty TEXT NOT NULL,
      stem TEXT NOT NULL,
      A TEXT NOT NULL,
      B TEXT NOT NULL,
      C TEXT NOT NULL,
      D TEXT NOT NULL,
      correct TEXT NOT NULL,
      notes TEXT,
      date DATETIME DEFAULT CURRENT_TIMESTAMP,
      FOREIGN KEY (user_id) REFERENCES users (id)
    )
  `);

  console.log('Database tables initialized.');
});

module.exports = db;