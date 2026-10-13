package com.parking.service;

import com.parking.exception.ParkingException;
import com.parking.exception.ParkingFullException;
import com.parking.model.*;
import com.parking.thread.ParkingMonitor;
import com.parking.util.FileLogger;

import java.time.LocalDateTime;
import java.util.*;
import java.util.concurrent.ConcurrentHashMap;
import java.util.concurrent.atomic.AtomicInteger;
import java.util.stream.Collectors;

// Implements ParkingOperations interface - Interface concept
public class ParkingLotService implements ParkingOperations {

    private static ParkingLotService instance; // Singleton pattern

    private final String lotName;
    private final int totalFloors;
    private final List<ParkingSlot> allSlots;

    private final Map<String, Vehicle> activeVehicles = new ConcurrentHashMap<>(); // ticketId -> Vehicle
    private final Map<String, ParkingTicket> activeTickets = new ConcurrentHashMap<>();
    private final List<ParkingTicket> completedTickets = Collections.synchronizedList(new ArrayList<>());
    private final Map<String, String> licensePlateIndex = new ConcurrentHashMap<>(); // plate -> ticketId

    private final AtomicInteger ticketCounter = new AtomicInteger(1000);
    private final FileLogger logger;
    private final ParkingMonitor monitor;

    // Private constructor for Singleton
    private ParkingLotService(String lotName, int floors, int slotsPerFloor) {
        this.lotName = lotName;
        this.totalFloors = floors;
        this.allSlots = new ArrayList<>();
        this.logger = new FileLogger("parking_log.txt");
        initializeSlots(floors, slotsPerFloor);
        this.monitor = new ParkingMonitor(this, logger);
        this.monitor.start(); // Start background monitoring thread
    }

    // Singleton getInstance
    public static synchronized ParkingLotService getInstance() {
        if (instance == null) {
            instance = new ParkingLotService("SmartPark Premium", 3, 20);
        }
        return instance;
    }

    private void initializeSlots(int floors, int slotsPerFloor) {
        for (int floor = 0; floor < floors; floor++) {
            for (int num = 1; num <= slotsPerFloor; num++) {
                String slotId = "F" + floor + "S" + String.format("%02d", num);
                ParkingSlot.SlotSize size;

                // First 5 slots per floor: SMALL (motorcycles)
                // Next 10: MEDIUM (cars)
                // Last 5: LARGE (trucks)
                if (num <= 5) size = ParkingSlot.SlotSize.SMALL;
                else if (num <= 15) size = ParkingSlot.SlotSize.MEDIUM;
                else size = ParkingSlot.SlotSize.LARGE;

                ParkingSlot slot = new ParkingSlot(slotId, floor, num, size);

                // Designate special slots
                if (floor == 0 && num == 1) slot.setHandicapped(true);
                if (floor == 0 && num == 2) slot.setHandicapped(true);
                if (floor == 0 && num == 6) slot.setEVCharging(true);
                if (floor == 0 && num == 7) slot.setEVCharging(true);
                if (floor == 1 && num == 6) slot.setEVCharging(true);

                allSlots.add(slot);
            }
        }
    }

    @Override
    public synchronized ParkingTicket checkIn(Vehicle vehicle) throws ParkingException {
        // Check for duplicate
        if (licensePlateIndex.containsKey(vehicle.getLicensePlate())) {
            throw new ParkingException("Vehicle " + vehicle.getLicensePlate() + " is already parked!", "DUPLICATE");
        }

        // Dynamic Method Dispatch - correct allocator chosen at runtime based on vehicle type
        SlotAllocator allocator = SlotAllocator.getFor(vehicle.getType());
        Optional<ParkingSlot> slotOpt = allocator.allocate(allSlots, vehicle);

        if (slotOpt.isEmpty()) {
            throw new ParkingFullException(vehicle.getType().getDisplayName());
        }

        ParkingSlot slot = slotOpt.get();
        String ticketId = "TKT" + ticketCounter.getAndIncrement();

        slot.occupy(vehicle.getVehicleId());
        vehicle.setAssignedSlotId(slot.getSlotId());

        ParkingTicket ticket = new ParkingTicket(ticketId, vehicle, slot);
        activeTickets.put(ticketId, ticket);
        activeVehicles.put(ticketId, vehicle);
        licensePlateIndex.put(vehicle.getLicensePlate(), ticketId);

        logger.log("CHECK-IN", vehicle + " -> " + slot.getSlotId() + " | Ticket: " + ticketId);
        return ticket;
    }

    @Override
    public synchronized ParkingTicket checkOut(String ticketId) throws ParkingException {
        ParkingTicket ticket = activeTickets.get(ticketId);
        if (ticket == null) {
            throw new ParkingException("Ticket not found or already checked out: " + ticketId, "INVALID_TICKET");
        }

        Vehicle vehicle = activeVehicles.get(ticketId);
        vehicle.setExitTime(LocalDateTime.now());
        double fee = vehicle.calculateFee();

        ticket.checkout(fee);

        // Free the slot
        ParkingSlot slot = findSlotById(ticket.getSlotId());
        if (slot != null) slot.vacate();

        // Update records
        activeTickets.remove(ticketId);
        activeVehicles.remove(ticketId);
        licensePlateIndex.remove(vehicle.getLicensePlate());
        completedTickets.add(ticket);

        logger.log("CHECK-OUT", vehicle + " from " + ticket.getSlotId()
                + " | Duration: " + vehicle.getParkingDurationMinutes() + " mins | Fee: ₹" + fee);

        return ticket;
    }

    @Override
    public ParkingTicket findTicketByLicensePlate(String licensePlate) throws ParkingException {
        String ticketId = licensePlateIndex.get(licensePlate.toUpperCase().trim());
        if (ticketId == null) {
            throw new ParkingException("No active parking found for: " + licensePlate, "NOT_FOUND");
        }
        return activeTickets.get(ticketId);
    }

    @Override
    public List<ParkingSlot> getAvailableSlots() {
        return allSlots.stream().filter(ParkingSlot::isAvailable).collect(Collectors.toList());
    }

    @Override
    public List<ParkingTicket> getActiveTickets() {
        return new ArrayList<>(activeTickets.values());
    }

    @Override
    public List<ParkingTicket> getCompletedTickets() {
        return new ArrayList<>(completedTickets);
    }

    @Override
    public Map<String, Integer> getOccupancyStats() {
        Map<String, Integer> stats = new LinkedHashMap<>();
        stats.put("totalSlots", allSlots.size());
        stats.put("available", (int) allSlots.stream().filter(ParkingSlot::isAvailable).count());
        stats.put("occupied", (int) allSlots.stream().filter(s -> s.getStatus() == ParkingSlot.SlotStatus.OCCUPIED).count());
        stats.put("smallAvail", (int) allSlots.stream().filter(s -> s.isAvailable() && s.getSize() == ParkingSlot.SlotSize.SMALL).count());
        stats.put("mediumAvail", (int) allSlots.stream().filter(s -> s.isAvailable() && s.getSize() == ParkingSlot.SlotSize.MEDIUM).count());
        stats.put("largeAvail", (int) allSlots.stream().filter(s -> s.isAvailable() && s.getSize() == ParkingSlot.SlotSize.LARGE).count());
        stats.put("evAvail", (int) allSlots.stream().filter(s -> s.isAvailable() && s.isEVCharging()).count());
        stats.put("handicappedAvail", (int) allSlots.stream().filter(s -> s.isAvailable() && s.isHandicapped()).count());
        stats.put("activeVehicles", activeTickets.size());
        stats.put("totalCompleted", completedTickets.size());
        return stats;
    }

    @Override
    public double getTotalRevenue() {
        return completedTickets.stream().mapToDouble(ParkingTicket::getAmountPaid).sum();
    }

    public List<ParkingSlot> getAllSlots() { return Collections.unmodifiableList(allSlots); }
    public String getLotName() { return lotName; }

    // Get active vehicle for a ticket
    public Vehicle getVehicleByTicketId(String ticketId) {
        return activeVehicles.get(ticketId);
    }

    private ParkingSlot findSlotById(String slotId) {
        return allSlots.stream().filter(s -> s.getSlotId().equals(slotId)).findFirst().orElse(null);
    }

    public void shutdown() {
        monitor.stopMonitoring();
        logger.close();
    }
}
