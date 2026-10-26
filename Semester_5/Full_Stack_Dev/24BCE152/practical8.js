/**
 * ============================================================================
 * Practical 8: Node.js Express REST API with MySQL (XAMPP)
 * ============================================================================
 * Project Title : SatSys - Satellite Management System
 * Operations     :
 *   - Database & Table Creation (satsys_db, satellites)
 *   - Insert Record (POST /api/satellites)
 *   - Update Record (PUT /api/satellites/:id)
 *   - Fetch Records (GET /api/satellites)
 *   - Delete Record (DELETE /api/satellites/:id)
 *   - Database Status (GET /api/status)
 * Note           : Serves API endpoints for the Practical 8 web UI.
 *                  Outputs are displayed directly in the browser interface.
 * ============================================================================
 */

const express = require("express");
const cors = require("cors");
const mysql = require("mysql2/promise");
const path = require("path");

const app = express();
const PORT = process.env.PORT || 3000;

// Enable CORS and JSON body parsing
app.use(cors());
app.use(express.json());
app.use(express.static(__dirname));

// XAMPP MySQL Database Configuration
const dbConfig = {
    host: "localhost",
    user: "root",
    password: "", // Default XAMPP MySQL password is empty
    port: 3306
};

const DB_NAME = "satsys_db";
const TABLE_NAME = "satellites";

let pool = null;

/**
 * Perform Database and Table Creation (Operations 1 & 2)
 */
async function initDatabase() {
    // 1. Connect to MySQL server without selecting database
    const rootConn = await mysql.createConnection(dbConfig);
    
    // Operation 1: Create Database
    await rootConn.query(`CREATE DATABASE IF NOT EXISTS \`${DB_NAME}\`;`);
    await rootConn.end();

    // 2. Initialize connection pool targeting satsys_db
    pool = mysql.createPool({
        ...dbConfig,
        database: DB_NAME,
        waitForConnections: true,
        connectionLimit: 10,
        queueLimit: 0
    });

    // Operation 2: Create Table
    const createTableSQL = `
        CREATE TABLE IF NOT EXISTS \`${TABLE_NAME}\` (
            \`id\` INT AUTO_INCREMENT PRIMARY KEY,
            \`name\` VARCHAR(100) NOT NULL,
            \`org\` VARCHAR(100) NOT NULL DEFAULT 'Deep',
            \`launch_date\` DATE NOT NULL,
            \`status\` ENUM('Pending', 'In Progress', 'Done', 'Missed', 'Crashed') NOT NULL DEFAULT 'Pending',
            \`created_at\` TIMESTAMP DEFAULT CURRENT_TIMESTAMP
        ) ENGINE=InnoDB DEFAULT CHARSET=utf8mb4;
    `;
    await pool.query(createTableSQL);

    // Seed default records if table is brand new
    const [rows] = await pool.query(`SELECT COUNT(*) as count FROM \`${TABLE_NAME}\`;`);
    if (rows[0].count === 0) {
        const seedSQL = `
            INSERT INTO \`${TABLE_NAME}\` (\`name\`, \`org\`, \`launch_date\`, \`status\`) VALUES
            ('GoSa', 'Deep', '2026-05-10', 'Done'),
            ('MoSa', 'Nirma', '2026-08-15', 'In Progress'),
            ('DoSa', 'Nasa', '2026-12-01', 'Pending'),
            ('LoSa', 'Isro', '2026-11-20', 'Crashed');
        `;
        await pool.query(seedSQL);
    }
}

// ============================================================================
// API ROUTES FOR FRONTEND WEB APPLICATION
// ============================================================================

// Status Route
app.get("/api/status", async (req, res) => {
    try {
        const [countResult] = await pool.query(`SELECT COUNT(*) as count FROM \`${TABLE_NAME}\`;`);
        res.json({
            success: true,
            database: DB_NAME,
            table: TABLE_NAME,
            recordsCount: countResult[0].count,
            message: "Connected to MySQL server (XAMPP localhost:3306)"
        });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

// Setup / Reinitialize Database & Table
app.post("/api/setup", async (req, res) => {
    try {
        await initDatabase();
        res.json({
            success: true,
            message: `Database '${DB_NAME}' and Table '${TABLE_NAME}' verified and initialized successfully.`
        });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

// GET /api/satellites - Fetch all records or search (Search & Initial Fetch)
app.get("/api/satellites", async (req, res) => {
    try {
        const search = req.query.search;
        let sql = `
            SELECT id, name, org, DATE_FORMAT(launch_date, '%Y-%m-%d') as launchDate, status, created_at
            FROM \`${TABLE_NAME}\`
        `;
        let params = [];
        if (search && search.trim()) {
            const queryPattern = `%${search.trim()}%`;
            sql += ` WHERE name LIKE ? OR org LIKE ? OR status LIKE ?`;
            params = [queryPattern, queryPattern, queryPattern];
        }
        sql += ` ORDER BY id ASC;`;

        const [rows] = await pool.query(sql, params);
        res.json({ success: true, data: rows });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

// POST /api/satellites - Insert a new record (Operation 3)
app.post("/api/satellites", async (req, res) => {
    const { name, org, launchDate, status } = req.body;
    if (!name || !name.trim()) {
        return res.status(400).json({ success: false, error: "Satellite name is required." });
    }

    try {
        const sql = `
            INSERT INTO \`${TABLE_NAME}\` (\`name\`, \`org\`, \`launch_date\`, \`status\`)
            VALUES (?, ?, ?, ?);
        `;
        const params = [
            name.trim(),
            (org || "Deep").trim(),
            launchDate || "2026-06-06",
            status || "Pending"
        ];
        const [result] = await pool.execute(sql, params);

        res.status(201).json({
            success: true,
            message: `Satellite '${name}' inserted successfully with ID ${result.insertId}!`,
            insertedId: result.insertId,
            satellite: {
                id: result.insertId,
                name: name.trim(),
                org: (org || "Deep").trim(),
                launchDate: launchDate || "2026-06-06",
                status: status || "Pending"
            }
        });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

// PUT /api/satellites/:id - Update an existing record (Operation 4)
app.put("/api/satellites/:id", async (req, res) => {
    const id = req.params.id;
    const { name, org, launchDate, status } = req.body;

    try {
        const updates = [];
        const params = [];

        if (name !== undefined) {
            updates.push("`name` = ?");
            params.push(name.trim());
        }
        if (org !== undefined) {
            updates.push("`org` = ?");
            params.push(org.trim());
        }
        if (launchDate !== undefined) {
            updates.push("`launch_date` = ?");
            params.push(launchDate);
        }
        if (status !== undefined) {
            updates.push("`status` = ?");
            params.push(status);
        }

        if (updates.length === 0) {
            return res.status(400).json({ success: false, error: "No fields provided to update." });
        }

        params.push(id);
        const sql = `UPDATE \`${TABLE_NAME}\` SET ${updates.join(", ")} WHERE \`id\` = ?;`;
        const [result] = await pool.execute(sql, params);

        if (result.affectedRows === 0) {
            return res.status(404).json({ success: false, error: `Satellite ID ${id} not found.` });
        }

        res.json({
            success: true,
            message: `Satellite ID ${id} updated successfully! (Status: ${status || "Modified"})`,
            affectedRows: result.affectedRows
        });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

// DELETE /api/satellites/:id - Delete a record
app.delete("/api/satellites/:id", async (req, res) => {
    const id = req.params.id;
    try {
        const [result] = await pool.execute(`DELETE FROM \`${TABLE_NAME}\` WHERE \`id\` = ?;`, [id]);
        if (result.affectedRows === 0) {
            return res.status(404).json({ success: false, error: `Satellite ID ${id} not found.` });
        }
        res.json({
            success: true,
            message: `Satellite ID ${id} deleted successfully from MySQL.`
        });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

// POST /api/seed - Seed sample records
app.post("/api/seed", async (req, res) => {
    try {
        await pool.query(`TRUNCATE TABLE \`${TABLE_NAME}\`;`);
        const seedSQL = `
            INSERT INTO \`${TABLE_NAME}\` (\`name\`, \`org\`, \`launch_date\`, \`status\`) VALUES
            ('GoSa', 'Deep', '2026-05-10', 'Done'),
            ('MoSa', 'Nirma', '2026-08-15', 'In Progress'),
            ('DoSa', 'Nasa', '2026-12-01', 'Pending'),
            ('LoSa', 'Isro', '2026-11-20', 'Crashed');
        `;
        await pool.query(seedSQL);
        res.json({
            success: true,
            message: "Table reset and seeded with default satellites (GoSa, MoSa, DoSa, LoSa)."
        });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

// Default root route serves practical8.html
app.get("/", (req, res) => {
    res.sendFile(path.join(__dirname, "practical8.html"));
});

// Start Express server and connect to MySQL
initDatabase()
    .then(() => {
        app.listen(PORT, () => {
            console.log(`SatSys API Server running on http://localhost:${PORT}`);
        });
    })
    .catch((err) => {
        console.error("Database connection initialization failed:", err.message);
    });
