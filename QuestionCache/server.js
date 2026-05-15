const express = require('express');
const cors = require('cors');
const bodyParser = require('body-parser');
const bcrypt = require('bcrypt');
const jwt = require('jsonwebtoken');
const path = require('path');
const db = require('./db');

const app = express();
const PORT = process.env.PORT || 3000;
const JWT_SECRET = process.env.JWT_SECRET || 'your-secret-key'; // In production, use environment variable

app.use(cors());
app.use(bodyParser.json());
app.use(express.static('.')); // Serve static files from current directory

// Middleware to verify JWT token
function authenticateToken(req, res, next) {
  const authHeader = req.headers['authorization'];
  const token = authHeader && authHeader.split(' ')[1];

  if (!token) {
    return res.status(401).json({ error: 'Access token required' });
  }

  jwt.verify(token, JWT_SECRET, (err, user) => {
    if (err) {
      return res.status(403).json({ error: 'Invalid token' });
    }
    req.user = user;
    next();
  });
}

// Auth routes
app.post('/api/login', (req, res) => {
  const { username, password } = req.body;

  if (!username || !password) {
    return res.status(400).json({ error: 'Username and password required' });
  }

  db.get('SELECT * FROM users WHERE username = ?', [username], async (err, user) => {
    if (err) {
      return res.status(500).json({ error: 'Database error' });
    }

    if (!user) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    const validPassword = await bcrypt.compare(password, user.password_hash);
    if (!validPassword) {
      return res.status(401).json({ error: 'Invalid credentials' });
    }

    const token = jwt.sign({ id: user.id, username: user.username }, JWT_SECRET, { expiresIn: '8h' });
    res.json({ token, user: { id: user.id, username: user.username, email: user.email } });
  });
});

// Questions routes (protected)
app.get('/api/questions', authenticateToken, (req, res) => {
  db.all('SELECT * FROM questions WHERE user_id = ? ORDER BY date DESC', [req.user.id], (err, rows) => {
    if (err) {
      return res.status(500).json({ error: 'Database error' });
    }
    res.json(rows);
  });
});

app.post('/api/questions', authenticateToken, (req, res) => {
  const { unit, skill, stimulus, difficulty, stem, A, B, C, D, correct, notes } = req.body;

  if (!unit || !skill || !stem || !A || !B || !C || !D || !correct) {
    return res.status(400).json({ error: 'All required fields must be provided' });
  }

  db.run(
    `INSERT INTO questions (user_id, unit, skill, stimulus, difficulty, stem, A, B, C, D, correct, notes)
     VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)`,
    [req.user.id, unit, skill, stimulus || 'None', difficulty, stem, A, B, C, D, correct, notes],
    function(err) {
      if (err) {
        return res.status(500).json({ error: 'Database error' });
      }
      res.status(201).json({ id: this.lastID });
    }
  );
});

app.put('/api/questions/:id', authenticateToken, (req, res) => {
  const { id } = req.params;
  const { unit, skill, stimulus, difficulty, stem, A, B, C, D, correct, notes } = req.body;

  db.run(
    `UPDATE questions SET unit = ?, skill = ?, stimulus = ?, difficulty = ?, stem = ?, A = ?, B = ?, C = ?, D = ?, correct = ?, notes = ?
     WHERE id = ? AND user_id = ?`,
    [unit, skill, stimulus || 'None', difficulty, stem, A, B, C, D, correct, notes, id, req.user.id],
    function(err) {
      if (err) {
        return res.status(500).json({ error: 'Database error' });
      }
      if (this.changes === 0) {
        return res.status(404).json({ error: 'Question not found' });
      }
      res.json({ message: 'Question updated' });
    }
  );
});

app.delete('/api/questions/:id', authenticateToken, (req, res) => {
  const { id } = req.params;

  db.run('DELETE FROM questions WHERE id = ? AND user_id = ?', [id, req.user.id], function(err) {
    if (err) {
      return res.status(500).json({ error: 'Database error' });
    }
    if (this.changes === 0) {
      return res.status(404).json({ error: 'Question not found' });
    }
    res.json({ message: 'Question deleted' });
  });
});

// Serve the main HTML file
app.get('/', (req, res) => {
  res.sendFile(path.join(__dirname, 'QBank.html'));
});

app.listen(PORT, () => {
  console.log(`Server running on port ${PORT}`);
});