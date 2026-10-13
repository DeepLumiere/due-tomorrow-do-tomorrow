# SmartPark Detailed Technical Report

## 1. Project Overview

SmartPark is a full-stack parking management system implemented with:

- Backend: Java (JDK standard library only, `com.sun.net.httpserver.HttpServer`)
- Frontend: Single-page HTML/CSS/JavaScript UI
- Data model: In-memory objects with file-based logs (`parking_log.txt`)

Core objective: Manage check-in, check-out, slot allocation, fee calculation, tracking, analytics, and monitoring using object-oriented design principles.

---

## 2. High-Level Architecture

### Backend components

- `com.parking.ParkingServer` - HTTP server bootstrap and API routing
- `com.parking.service.ParkingLotService` - core business logic (singleton service)
- `com.parking.model.*` - domain objects (`Vehicle`, `ParkingSlot`, `ParkingTicket`)
- `com.parking.service.SlotAllocator` - strategy-based slot selection
- `com.parking.thread.ParkingMonitor` - scheduled background monitoring
- `com.parking.util.FileLogger` and `com.parking.util.JsonBuilder` - utility services
- `com.parking.exception.*` - custom exception hierarchy

### Frontend component

- `parking-system/frontend/index.html` - dashboard, forms, tables, map, logs, and API integration

### Request/response pattern

1. Browser sends request (e.g., `/api/checkin`)
2. `ParkingServer` handler parses body/query
3. `ParkingLotService` executes business rule
4. Response JSON is built via `JsonBuilder`
5. Frontend updates UI from JSON payload

---

## 3. OOP Concepts Used (with code evidence)

## 3.1 Classes and Objects

Domain entities are represented as classes and instantiated at runtime.

**Code snippet (`ParkingTicket.java`)**
```java
public class ParkingTicket {
    private final String ticketId;
    private final String vehicleId;
    private final String licensePlate;
    private final String slotId;
    private final LocalDateTime entryTime;
    // ...

    public ParkingTicket(String ticketId, Vehicle vehicle, ParkingSlot slot) {
        this.ticketId = ticketId;
        this.vehicleId = vehicle.getVehicleId();
        this.licensePlate = vehicle.getLicensePlate();
        this.slotId = slot.getSlotId();
        this.entryTime = vehicle.getEntryTime();
    }
}
```

**Working:** On check-in, a `ParkingTicket` object is created and stored in active collections. It becomes the transaction identity for checkout and tracking.

---

## 3.2 Constructors

Constructors initialize object state at creation time.

**Code snippet (`Vehicle.java`)**
```java
public Vehicle(String licensePlate, String ownerName, String ownerPhone) {
    this.vehicleId = UUID.randomUUID().toString().substring(0, 8).toUpperCase();
    this.licensePlate = licensePlate.toUpperCase().trim();
    this.ownerName = ownerName;
    this.ownerPhone = ownerPhone;
    this.entryTime = LocalDateTime.now();
}
```

**Working:** Every vehicle is created with identity, normalized plate, owner details, and entry timestamp used later for billing.

---

## 3.3 Inheritance

Specialized vehicle types inherit from abstract base `Vehicle`.

**Code snippet (`Vehicles.java`)**
```java
class Truck extends Vehicle {
    public Truck(String licensePlate, String ownerName, String ownerPhone) {
        super(licensePlate, ownerName, ownerPhone);
    }
    @Override public VehicleType getType() { return VehicleType.TRUCK; }
    @Override public double getHourlyRate() { return 100.0; }
    @Override public int getRequiredSlotSize() { return 3; }
}
```

**Working:** Common fields (plate, owner, time) remain in base class; each subtype overrides pricing and size requirement.

---

## 3.4 Abstraction (Abstract Class)

Abstract base class enforces mandatory behavior while hiding implementation details.

**Code snippet (`Vehicle.java`)**
```java
public abstract class Vehicle {
    public abstract VehicleType getType();
    public abstract double getHourlyRate();
    public abstract int getRequiredSlotSize();
}
```

**Working:** Service logic can work with `Vehicle` polymorphically without needing concrete-type conditionals for every operation.

---

## 3.5 Interface

`ParkingOperations` defines the service contract, implemented by `ParkingLotService`.

**Code snippet (`ParkingOperations.java`)**
```java
public interface ParkingOperations {
    ParkingTicket checkIn(Vehicle vehicle) throws ParkingException;
    ParkingTicket checkOut(String ticketId) throws ParkingException;
    ParkingTicket findTicketByLicensePlate(String licensePlate) throws ParkingException;
    List<ParkingSlot> getAvailableSlots();
    Map<String, Integer> getOccupancyStats();
}
```

**Working:** API handlers call behavior through a clean contract, improving modularity and extensibility.

---

## 3.6 Polymorphism and Dynamic Method Dispatch

Runtime chooses correct implementation for allocators and vehicle-specific fees.

**Code snippet (`ParkingLotService.java`)**
```java
SlotAllocator allocator = SlotAllocator.getFor(vehicle.getType());
Optional<ParkingSlot> slotOpt = allocator.allocate(allSlots, vehicle);
```

**Code snippet (`Vehicle.java`)**
```java
public double calculateFee() {
    long minutes = getParkingDurationMinutes();
    double hours = Math.ceil(minutes / 60.0);
    if (hours < 1) hours = 1;
    return hours * getHourlyRate();
}
```

**Working:**

- `getFor(...)` returns allocator strategy based on type (`EV`, `TRUCK`, etc.)
- `calculateFee()` calls subclass `getHourlyRate()` automatically (dynamic dispatch)

---

## 3.7 Encapsulation

Fields are private and manipulated via controlled methods.

**Code snippet (`ParkingSlot.java`)**
```java
private SlotStatus status;
private String occupiedByVehicleId;

public void occupy(String vehicleId) {
    this.occupiedByVehicleId = vehicleId;
    this.status = SlotStatus.OCCUPIED;
}

public void vacate() {
    this.occupiedByVehicleId = null;
    this.status = SlotStatus.AVAILABLE;
}
```

**Working:** Slot state transitions happen through explicit methods, protecting invariants from random modification.

---

## 3.8 Factory Pattern

`VehicleFactory` centralizes object creation and validation.

**Code snippet (`VehicleFactory.java`)**
```java
return switch (type.toUpperCase()) {
    case "MOTORCYCLE" -> new Motorcycle(licensePlate, ownerName, ownerPhone);
    case "CAR" -> new Car(licensePlate, ownerName, ownerPhone);
    case "TRUCK" -> new Truck(licensePlate, ownerName, ownerPhone);
    case "ELECTRIC_CAR" -> new ElectricCar(licensePlate, ownerName, ownerPhone);
    case "HANDICAPPED" -> new HandicappedVehicle(licensePlate, ownerName, ownerPhone);
    default -> throw new ParkingException("Unknown vehicle type: " + type);
};
```

**Working:** Prevents scattered constructor logic in API handlers and enforces input checks in one place.

---

## 3.9 Singleton Pattern

A single service instance manages global parking state.

**Code snippet (`ParkingLotService.java`)**
```java
private static ParkingLotService instance;

public static synchronized ParkingLotService getInstance() {
    if (instance == null) {
        instance = new ParkingLotService("SmartPark Premium", 3, 20);
    }
    return instance;
}
```

**Working:** Ensures one consistent source of truth for tickets, slots, revenue, and indexes.

---

## 3.10 Exception Handling

Custom exceptions represent domain failures with error codes.

**Code snippet (`ParkingException.java`, `ParkingFullException.java`)**
```java
public class ParkingException extends Exception {
    private final String errorCode;
    public ParkingException(String message, String errorCode) {
        super(message);
        this.errorCode = errorCode;
    }
}

public class ParkingFullException extends ParkingException {
    public ParkingFullException(String vehicleType) {
        super("No available slot for vehicle type: " + vehicleType + ". Parking lot is full.", "PARKING_FULL");
    }
}
```

**Working:** API handlers catch `ParkingException` and return structured JSON errors instead of crashing.

---

## 3.11 Multithreading and Concurrency

The system uses thread-safe structures and scheduler-based background tasks.

**Code snippet (`ParkingLotService.java`)**
```java
private final Map<String, Vehicle> activeVehicles = new ConcurrentHashMap<>();
private final Map<String, ParkingTicket> activeTickets = new ConcurrentHashMap<>();
private final List<ParkingTicket> completedTickets = Collections.synchronizedList(new ArrayList<>());
```

**Code snippet (`ParkingMonitor.java`)**
```java
scheduler.scheduleAtFixedRate(this::logOccupancySnapshot, 30, 60, TimeUnit.SECONDS);
scheduler.scheduleAtFixedRate(this::checkOverdueVehicles, 60, 300, TimeUnit.SECONDS);
```

**Working:**

- HTTP requests run through server thread pool
- synchronized service methods protect critical write operations
- monitor thread logs occupancy and overdue alerts independently

---

## 3.12 File Handling

Logs are persisted with append mode and retrievable via API.

**Code snippet (`FileLogger.java`)**
```java
writer = new BufferedWriter(new FileWriter(logFilePath, true));

public List<String> readLogs(int lastNLines) {
    Path path = Paths.get(logFilePath);
    if (Files.exists(path)) {
        List<String> allLines = Files.readAllLines(path);
        int start = Math.max(0, allLines.size() - lastNLines);
        return allLines.subList(start, allLines.size());
    }
    return new ArrayList<>();
}
```

**Working:** Every important event (check-in/out, monitor snapshot, errors) is durable and viewable from the UI.

---

## 4. Detailed Working of Major Flows

## 4.1 Server Startup Flow

1. `ParkingServer.main()` initializes singleton service and server logger
2. Registers API contexts (`/api/checkin`, `/api/checkout`, `/api/stats`, etc.)
3. Registers static frontend handler (`/`)
4. Starts server with fixed thread pool
5. Installs JVM shutdown hook for graceful stop and logger close

**Key code (`ParkingServer.java`)**
```java
server.createContext("/api/checkin", ParkingServer::handleCheckIn);
server.createContext("/api/checkout", ParkingServer::handleCheckOut);
server.createContext("/", ParkingServer::handleStatic);
server.setExecutor(java.util.concurrent.Executors.newFixedThreadPool(10));
server.start();
```

---

## 4.2 Check-In Flow

1. Frontend calls `POST /api/checkin` with form-urlencoded body
2. `handleCheckIn()` parses request and validates through `VehicleFactory`
3. `ParkingLotService.checkIn(vehicle)`:
   - checks duplicate plate
   - gets runtime allocator strategy (`SlotAllocator.getFor`)
   - selects best available slot
   - occupies slot and creates ticket
   - updates active maps and indexes
   - writes check-in log
4. JSON ticket returned to frontend modal

**Key logic (`ParkingLotService.java`)**
```java
if (licensePlateIndex.containsKey(vehicle.getLicensePlate())) {
    throw new ParkingException("Vehicle " + vehicle.getLicensePlate() + " is already parked!", "DUPLICATE");
}

SlotAllocator allocator = SlotAllocator.getFor(vehicle.getType());
Optional<ParkingSlot> slotOpt = allocator.allocate(allSlots, vehicle);

ParkingSlot slot = slotOpt.get();
slot.occupy(vehicle.getVehicleId());
ParkingTicket ticket = new ParkingTicket(ticketId, vehicle, slot);
```

---

## 4.3 Check-Out Flow

1. Frontend resolves ticket (ticket id or plate lookup)
2. Calls `POST /api/checkout` with ticket id
3. `ParkingLotService.checkOut(ticketId)`:
   - fetches active ticket
   - sets exit time in vehicle
   - computes fee (`vehicle.calculateFee()`)
   - marks ticket paid
   - vacates slot
   - moves ticket from active to completed list
   - logs transaction and fee
4. Paid receipt returned to frontend

**Key logic (`ParkingLotService.java`)**
```java
Vehicle vehicle = activeVehicles.get(ticketId);
vehicle.setExitTime(LocalDateTime.now());
double fee = vehicle.calculateFee();

ticket.checkout(fee);
ParkingSlot slot = findSlotById(ticket.getSlotId());
if (slot != null) slot.vacate();

activeTickets.remove(ticketId);
activeVehicles.remove(ticketId);
completedTickets.add(ticket);
```

---

## 4.4 Slot Allocation Strategies

Allocation behavior is separated by strategy classes.

- `EVSlotAllocator`: prioritize EV charging slots; fallback to medium/large
- `HandicappedSlotAllocator`: prioritize handicapped slots; fallback to floor 0
- `NearestExitAllocator`: lowest floor and slot number (cars/motorcycles default)
- `LargeSlotAllocator`: large slots only (trucks)

**Key code (`SlotAllocator.java`)**
```java
public static SlotAllocator getFor(VehicleType type) {
    return switch (type) {
        case ELECTRIC_CAR -> new EVSlotAllocator();
        case HANDICAPPED -> new HandicappedSlotAllocator();
        case MOTORCYCLE -> new NearestExitAllocator();
        case TRUCK -> new LargeSlotAllocator();
        default -> new NearestExitAllocator();
    };
}
```

---

## 4.5 Monitoring and Analytics Flow

`ParkingMonitor` runs in background and triggers two periodic tasks:

- Snapshot logging every 60 seconds
- Overstay check (>=12 hours) every 5 minutes

This demonstrates asynchronous operational monitoring independent of user API calls.

---

## 4.6 Frontend and API Integration

Frontend JavaScript uses:

- `apiGet(path)` for GET endpoints
- `apiPost(path, data)` for POST endpoints (`application/x-www-form-urlencoded`)
- periodic refresh every 15 seconds for dashboard/map/active pages

**Key code (`frontend/index.html`)**
```javascript
async function apiPost(path, data) {
  const body = Object.entries(data)
    .map(([k,v]) => `${encodeURIComponent(k)}=${encodeURIComponent(v)}`)
    .join('&');
  const r = await fetch(API + path, {
    method: 'POST',
    headers: {'Content-Type':'application/x-www-form-urlencoded'},
    body
  });
  return r.json();
}
```

---

## 5. Data Structures and Why They Matter

- `ConcurrentHashMap` for active entities: safe concurrent reads/writes under API load
- synchronized list for completed tickets: preserves thread-safe history appends
- license plate index map: O(1) lookup for `/api/find`
- immutable slot exposure (`Collections.unmodifiableList(allSlots)`): prevents accidental external mutation

---

## 6. REST Endpoints and Functional Role

- `POST /api/checkin` - create vehicle and ticket, allocate slot
- `POST /api/checkout` - settle payment, vacate slot, archive ticket
- `GET /api/find?plate=...` - plate-based active ticket lookup
- `GET /api/slots` - full slot map for visualization
- `GET /api/stats` - dashboard KPIs and revenue
- `GET /api/active` - all currently parked vehicles
- `GET /api/history` - completed transactions
- `GET /api/logs` - tail view of persisted logs

---

## 7. End-to-End Example Scenario

1. User selects `ELECTRIC_CAR` in UI and submits plate/owner
2. Server constructs `ElectricCar` object through `VehicleFactory`
3. EV allocator tries EV charging slots first
4. Ticket `TKTxxxx` is issued and returned
5. Dashboard updates active count and occupancy
6. On checkout, duration is computed from entry/exit timestamps
7. Fee uses EV hourly rate (`50 * 0.8 = 40` INR/hour), rounded up by hour
8. Slot is released and history/revenue are updated

---

## 8. Design Strengths

- Clean layering between HTTP, service logic, model, and utilities
- Good OOP coverage for academic evaluation (abstraction, inheritance, polymorphism, interface, encapsulation)
- Thread-safe state management with background monitoring
- No external dependencies, simple to run in classroom/lab machines
- Rich frontend UX with real-time data and visual map

---

## 9. Current Constraints / Improvement Opportunities

- State is in-memory (tickets and slot occupancy reset on restart)
- Manual JSON string building can be error-prone at scale
- No authentication/authorization for API endpoints
- Slot fallback behavior is hardcoded; policy configuration can be externalized
- No formal automated unit tests included in current source

---

## 10. Conclusion

SmartPark is a strong OOP-focused parking management implementation that demonstrates practical software engineering patterns in a compact Java codebase. The project combines object-oriented modeling, strategy-based allocation, thread-safe operations, file persistence, and frontend integration to provide an end-to-end, working smart parking solution suitable for academic demonstration and viva explanation.

