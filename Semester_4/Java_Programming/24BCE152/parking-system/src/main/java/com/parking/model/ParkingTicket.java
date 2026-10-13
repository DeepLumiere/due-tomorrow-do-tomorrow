package com.parking.model;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;

public class ParkingTicket {
    private static final DateTimeFormatter FORMATTER = DateTimeFormatter.ofPattern("dd-MM-yyyy HH:mm:ss");

    private final String ticketId;
    private final String vehicleId;
    private final String licensePlate;
    private final String slotId;
    private final LocalDateTime entryTime;
    private LocalDateTime exitTime;
    private double amountPaid;
    private TicketStatus status;

    public enum TicketStatus { ACTIVE, PAID, CANCELLED }

    public ParkingTicket(String ticketId, Vehicle vehicle, ParkingSlot slot) {
        this.ticketId = ticketId;
        this.vehicleId = vehicle.getVehicleId();
        this.licensePlate = vehicle.getLicensePlate();
        this.slotId = slot.getSlotId();
        this.entryTime = vehicle.getEntryTime();
        this.status = TicketStatus.ACTIVE;
    }

    public void checkout(double amount) {
        this.exitTime = LocalDateTime.now();
        this.amountPaid = amount;
        this.status = TicketStatus.PAID;
    }

    // Getters
    public String getTicketId() { return ticketId; }
    public String getVehicleId() { return vehicleId; }
    public String getLicensePlate() { return licensePlate; }
    public String getSlotId() { return slotId; }
    public LocalDateTime getEntryTime() { return entryTime; }
    public LocalDateTime getExitTime() { return exitTime; }
    public double getAmountPaid() { return amountPaid; }
    public TicketStatus getStatus() { return status; }
    public String getFormattedEntryTime() { return entryTime.format(FORMATTER); }
    public String getFormattedExitTime() { return exitTime != null ? exitTime.format(FORMATTER) : "Still Parked"; }
}
