

const express = require("express");
const cors = require("cors");
const path = require("path");

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());
app.use(express.static(__dirname));

let satellites = [
    { id: 1, name: "GoSa", org: "Deep", launchDate: "2026-05-10", status: "Done" },
    { id: 2, name: "MoSa", org: "Nirma", launchDate: "2026-08-15", status: "In Progress" },
    { id: 3, name: "DoSa", org: "Nasa", launchDate: "2026-12-01", status: "Pending" },
    { id: 4, name: "LoSa", org: "Isro", launchDate: "2026-11-20", status: "Crashed" }
];

let nextId = 5;

function requireEditor(req, res, next) {
    const role = (req.headers["x-user-role"] || req.query.role || "viewer").toLowerCase();

    if (role === "editor" || role === "admin") {
        next(); // Permission granted
    } else {
        // Access Denied: 403 Forbidden
        return res.status(403).json({
            success: false,
            error: "Access Denied (403 Forbidden): 'Viewer' role is read-only. Switch to 'Editor' to modify satellites."
        });
    }
}

// Status Route
app.get("/api/status", (req, res) => {
    res.json({
        success: true,
        project: "SatSys - Role-Based Access Control",
        roles: ["viewer", "editor"],
        recordsCount: satellites.length
    });
});

app.get("/api/satellites", (req, res) => {
    const search = req.query.search;
    let result = satellites;

    if (search && search.trim()) {
        const query = search.toLowerCase().trim();
        result = satellites.filter(s =>
            s.name.toLowerCase().includes(query) ||
            s.org.toLowerCase().includes(query) ||
            s.status.toLowerCase().includes(query)
        );
    }

    res.json({ success: true, data: result });
});

app.post("/api/satellites", requireEditor, (req, res) => {
    const { name, org, launchDate, status } = req.body;
    if (!name || !name.trim()) {
        return res.status(400).json({ success: false, error: "Satellite name is required." });
    }

    const newSat = {
        id: nextId++,
        name: name.trim(),
        org: (org || "Deep").trim(),
        launchDate: launchDate || "2026-06-06",
        status: status || "Pending"
    };

    satellites.push(newSat);

    res.status(201).json({
        success: true,
        message: `Satellite '${newSat.name}' added successfully by Editor!`,
        satellite: newSat
    });
});

// PUT /api/satellites/:id - Update status (Editor only)
app.put("/api/satellites/:id", requireEditor, (req, res) => {
    const id = parseInt(req.params.id);
    const { status } = req.body;

    const sat = satellites.find(s => s.id === id);
    if (!sat) {
        return res.status(404).json({ success: false, error: `Satellite ID ${id} not found.` });
    }

    if (status) sat.status = status;

    res.json({
        success: true,
        message: `Satellite ID ${id} status updated to '${sat.status}' by Editor!`,
        satellite: sat
    });
});

// DELETE /api/satellites/:id - Delete a record (Editor only)
app.delete("/api/satellites/:id", requireEditor, (req, res) => {
    const id = parseInt(req.params.id);
    const index = satellites.findIndex(s => s.id === id);

    if (index === -1) {
        return res.status(404).json({ success: false, error: `Satellite ID ${id} not found.` });
    }

    const deleted = satellites.splice(index, 1)[0];
    res.json({
        success: true,
        message: `Satellite ID ${id} ('${deleted.name}') deleted successfully by Editor.`
    });
});

// Default root route serves practical9.html
app.get("/", (req, res) => {
    res.sendFile(path.join(__dirname, "practical9.html"));
});

// Start Express server
app.listen(PORT, () => {
    console.log(`SatSys RBAC API Server running on http://localhost:${PORT}`);
    console.log(`Open in browser: http://localhost:${PORT}/practical9.html`);
});
