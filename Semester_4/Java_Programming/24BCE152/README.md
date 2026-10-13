# 🅿 SmartPark — Intelligent Parking Management System

A full-stack Parking Lot Management System with a **Java backend** and **HTML/CSS/JS frontend**, demonstrating all core OOP concepts required for academic purposes.

---

## 🧠 OOP Concepts Used

| Concept | Where Applied |
|---|---|
| **Classes & Objects** | `Vehicle`, `ParkingSlot`, `ParkingTicket`, `ParkingLotService` |
| **Constructors** | All model classes have parameterized constructors |
| **Inheritance** | `Motorcycle`, `Car`, `Truck`, `ElectricCar`, `HandicappedVehicle` extend `Vehicle` |
| **Interface** | `ParkingOperations` interface implemented by `ParkingLotService` |
| **Abstract Class** | `Vehicle` (abstract), `SlotAllocator` (abstract) |
| **Dynamic Method Dispatch** | `SlotAllocator.getFor()` returns polymorphic allocator; `vehicle.calculateFee()` calls correct subclass method |
| **Package** | `com.parking`, `com.parking.model`, `com.parking.service`, `com.parking.exception`, `com.parking.thread`, `com.parking.util` |
| **Exception Handling** | `ParkingException`, `ParkingFullException` with custom error codes; try-catch in all API handlers |
| **Multithreading** | `ParkingMonitor` uses `ScheduledExecutorService`; `ConcurrentHashMap` for thread-safe storage; HTTP server uses thread pool |
| **File Handling** | `FileLogger` writes/reads `parking_log.txt` persistently using `BufferedWriter` / `Files.readAllLines` |

---

## 📁 Project Structure

```
parking-system/
├── src/main/java/com/parking/
│   ├── ParkingServer.java          ← HTTP server entry point
│   ├── model/
│   │   ├── Vehicle.java            ← Abstract base class
│   │   ├── Vehicles.java           ← Motorcycle, Car, Truck, EV, Handicapped
│   │   ├── VehicleType.java        ← Enum
│   │   ├── VehicleFactory.java     ← Factory pattern
│   │   ├── ParkingSlot.java        ← Slot model
│   │   └── ParkingTicket.java      ← Ticket model
│   ├── service/
│   │   ├── ParkingOperations.java  ← Interface
│   │   ├── ParkingLotService.java  ← Core business logic (Singleton)
│   │   └── SlotAllocator.java      ← Strategy pattern + Dynamic Dispatch
│   ├── exception/
│   │   ├── ParkingException.java   ← Base exception
│   │   ├── ParkingFullException.java
│   │   └── Exceptions.java         ← Other exceptions
│   ├── thread/
│   │   └── ParkingMonitor.java     ← Background monitoring thread
│   └── util/
│       ├── FileLogger.java         ← File I/O logging
│       └── JsonBuilder.java        ← JSON response builder
├── frontend/
│   └── index.html                  ← Complete UI (HTML + CSS + JS)
├── run.sh                          ← Linux/Mac startup script
├── run.bat                         ← Windows startup script
└── README.md
```

---

## 🚀 How to Run

### Prerequisites
- **Java JDK 17+** installed
- No Maven/Gradle needed — uses only standard Java library

### Linux / macOS
```bash
chmod +x run.sh
./run.sh
```

### Windows
```
run.bat
```

### Manual
```bash
mkdir -p classes
javac -d classes $(find src -name "*.java")
java -cp classes com.parking.ParkingServer
```

Then open: **http://localhost:8080**

---

## 🛠 Features

### Parking Operations
- ✅ **Check-In** — Register vehicle, auto-assign best slot, generate ticket
- ✅ **Check-Out** — Calculate fee, process payment, release slot
- ✅ **Find Vehicle** — Search by license plate
- ✅ **Active Tickets** — View all currently parked vehicles

### Smart Slot Allocation
- Motorcycles → small slots, nearest to exit
- Cars → medium slots
- Trucks → large slots only
- Electric Cars → EV charging slots (with 20% discount)
- Handicapped → designated accessible spots near entrance

### Monitoring & Analytics
- Live dashboard with occupancy stats
- Interactive parking map (per floor)
- Transaction history with full records
- System logs (backed by `parking_log.txt`)
- Background thread alerts for 12+ hour overstays

### Pricing (₹ INR)
| Type | Rate |
|---|---|
| Motorcycle | ₹20/hour |
| Car | ₹50/hour |
| Truck | ₹100/hour |
| Electric Car | ₹40/hour (20% off) |
| Handicapped | ₹25/hour |

Minimum charge: 1 hour. Billing rounds up per hour.

---

## 🔌 REST API Endpoints

| Method | Endpoint | Description |
|---|---|---|
| POST | `/api/checkin` | Check in vehicle |
| POST | `/api/checkout` | Check out & pay |
| GET | `/api/find?plate=XX` | Find by plate |
| GET | `/api/slots` | All slot statuses |
| GET | `/api/stats` | Dashboard stats |
| GET | `/api/active` | Active tickets |
| GET | `/api/history` | Completed tickets |
| GET | `/api/logs` | System logs |

---

## 📝 Notes
- **No external libraries** — uses only `com.sun.net.httpserver` (built into JDK)
- Data is **in-memory** (resets on restart), logs are persisted to disk
- Thread-safe using `ConcurrentHashMap` and `synchronized` blocks
- UI auto-refreshes every 15 seconds
