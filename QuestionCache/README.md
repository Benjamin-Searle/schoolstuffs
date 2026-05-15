# QBank Server

This folder contains the AP Physics 2 question bank web app and a Node.js/SQLite backend.

## Files

- `QBank.html` — frontend UI with login/register and question forms
- `QBank.js` — frontend logic updated to call the backend API
- `QBank.css` — application styles
- `server.js` — Express server with auth and question CRUD routes
- `db.js` — SQLite database initialization and schema
- `package.json` — Node dependencies and start script
- `.gitignore` — ignores local database and node modules

## Setup

1. Install Node.js and npm on your server.
2. In this folder, run:
   ```bash
   npm install
   ```
3. Set a secure JWT secret before starting the server:
   ```bash
   export JWT_SECRET="your-strong-secret"
   export DB_FILE="/path/to/qbank.db"
   ```
4. Start the server:
   ```bash
   node server.js
   ```

## API

- `POST /api/login` — authenticate and return JWT
- `GET /api/questions` — load user questions
- `POST /api/questions` — create a question
- `PUT /api/questions/:id` — update a question
- `DELETE /api/questions/:id` — delete a question

User accounts are intended to be created administratively on the server. The frontend no longer supports self-registration.

The frontend stores the JWT in `localStorage` and sends it in the `Authorization: Bearer ...` header.
