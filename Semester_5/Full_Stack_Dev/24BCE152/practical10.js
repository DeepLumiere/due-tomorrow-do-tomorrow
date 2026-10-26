const express = require("express");
const cors = require("cors");
const path = require("path");
const mongoose = require("mongoose");

const app = express();
const PORT = process.env.PORT || 3000;

app.use(cors());
app.use(express.json());
app.use(express.static(__dirname));

const MONGO_URI = process.env.MONGO_URI || "mongodb://127.0.0.1:27017/satsys_db";
const DB_NAME = "satsys_db";
const COLLECTION_NAME = "satellites";

const satelliteSchema = new mongoose.Schema({
    name: {
        type: String,
        required: [true, "Satellite name is required"],
        trim: true
    },
    org: {
        type: String,
        default: "Deep",
        trim: true
    },
    launchDate: {
        type: String,
        required: [true, "Launch date is required"],
        default: "2026-06-06"
    },
    status: {
        type: String,
        enum: ["Pending", "In Progress", "Done", "Missed", "Crashed"],
        default: "Pending"
    }
}, {
    timestamps: true
});

satelliteSchema.set("toJSON", {
    transform: (doc, ret) => {
        ret.id = ret._id.toString();
        return ret;
    }
});

const Satellite = mongoose.model("Satellite", satelliteSchema);

async function initDatabase() {
    try {
        await mongoose.connect(MONGO_URI);

        const count = await Satellite.countDocuments();
        if (count === 0) {
            await seedDefaultSatellites();
        }
    } catch (err) {
        console.warn("Not working MDB");
    }
}

async function seedDefaultSatellites() {
    const defaultSatellites = [
        { name: "GoSa", org: "Deep", launchDate: "2026-05-10", status: "Done" },
        { name: "MoSa", org: "Nirma", launchDate: "2026-08-15", status: "In Progress" },
        { name: "DoSa", org: "Nasa", launchDate: "2026-12-01", status: "Pending" },
        { name: "LoSa", org: "Isro", launchDate: "2026-11-20", status: "Crashed" }
    ];
    await Satellite.insertMany(defaultSatellites);
}

async function checkMongo(req, res, next) {
    if (mongoose.connection.readyState !== 1) {
        try {
            await mongoose.connect(MONGO_URI);
        } catch (err) {
            console.error("MongoDB connection error:", err.message);
            return res.status(503).json({
                success: false,
                error: "MongoDB is disconnected"
            });
        }
    }
    next();
}

app.get("/api/status", async (req, res) => {
    const isConnected = mongoose.connection.readyState === 1;
    if (!isConnected) {
        return res.json({
            success: false,
            database: DB_NAME,
            table: COLLECTION_NAME,
            message: "Disconnected from MongoDB (mongodb://127.0.0.1:27017/satsys_db)."
        });
    }

    try {
        const count = await Satellite.countDocuments();
        res.json({
            success: true,
            database: DB_NAME,
            table: COLLECTION_NAME,
            recordsCount: count,
            message: "Connected to MongoDB via Mongoose (localhost:27017)"
        });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

app.post("/api/setup", checkMongo, async (req, res) => {
    try {
        await seedDefaultSatellites();
        res.json({
            success: true,
            message: `Database '${DB_NAME}' and Collection '${COLLECTION_NAME}' verified and initialized successfully.`
        });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

app.get("/api/satellites", checkMongo, async (req, res) => {
    try {
        const search = req.query.search;
        let query = {};

        if (search && search.trim()) {
            const pattern = new RegExp(search.trim(), "i");
            query = {
                $or: [
                    { name: pattern },
                    { org: pattern },
                    { status: pattern }
                ]
            };
        }

        const satellites = await Satellite.find(query).sort({ _id: 1 });
        res.json({ success: true, data: satellites });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

app.post("/api/satellites", checkMongo, async (req, res) => {
    const { name, org, launchDate, status } = req.body;
    if (!name || !name.trim()) {
        return res.status(400).json({ success: false, error: "Satellite name is required." });
    }

    try {
        const newSatellite = new Satellite({
            name: name.trim(),
            org: (org || "nasaDeep").trim(),
            launchDate: launchDate || "2026-10-06",
            status: status || "Completed"
        });

        const saved = await newSatellite.save();

        res.status(201).json({
            success: true,
            message: `Satellite '${saved.name}' inserted successfully with MongoDB ID ${saved._id}!`,
            insertedId: saved._id,
            satellite: saved
        });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

app.put("/api/satellites/:id", checkMongo, async (req, res) => {
    const id = req.params.id;
    const { name, org, launchDate, status } = req.body;

    if (!mongoose.Types.ObjectId.isValid(id)) {
        return res.status(400).json({ success: false, error: "Invalid MongoDB ObjectId format." });
    }

    try {
        const updates = {};
        if (name !== undefined) updates.name = name.trim();
        if (org !== undefined) updates.org = org.trim();
        if (launchDate !== undefined) updates.launchDate = launchDate;
        if (status !== undefined) updates.status = status;

        if (Object.keys(updates).length === 0) {
            return res.status(400).json({ success: false, error: "No fields provided to update." });
        }

        const updated = await Satellite.findByIdAndUpdate(id, { $set: updates }, { new: true, runValidators: true });

        if (!updated) {
            return res.status(404).json({ success: false, error: `Satellite ID ${id} not found.` });
        }

        res.json({
            success: true,
            message: `Satellite ID ${id} updated successfully! (Status: ${status || "Modified"})`,
            satellite: updated
        });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

app.delete("/api/satellites/:id", checkMongo, async (req, res) => {
    const id = req.params.id;

    if (!mongoose.Types.ObjectId.isValid(id)) {
        return res.status(400).json({ success: false, error: "Invalid MongoDB ObjectId format." });
    }

    try {
        const deleted = await Satellite.findByIdAndDelete(id);

        if (!deleted) {
            return res.status(404).json({ success: false, error: `Satellite ID ${id} not found.` });
        }

        res.json({
            success: true,
            message: `Satellite ID ${id} deleted successfully from MongoDB.`
        });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

// POST /api/seed - Seed sample records
app.post("/api/seed", checkMongo, async (req, res) => {
    try {
        await Satellite.deleteMany({});
        await seedDefaultSatellites();
        res.json({
            success: true,
            message: "Collection reset and seeded with default satellites (GoSa, MoSa, DoSa, LoSa)."
        });
    } catch (err) {
        res.status(500).json({ success: false, error: err.message });
    }
});

app.get("/", (req, res) => {
    res.sendFile(path.join(__dirname, "practical10.html"));
});

initDatabase().finally(() => {
    app.listen(PORT, () => {
        console.log(`http://localhost:${PORT}`);
        console.log(`http://localhost:${PORT}/practical10.html`);
    });
});
