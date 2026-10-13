package com.parking.model;

import java.time.LocalDateTime;
import java.util.UUID;

// Abstract base class - Fundamental OOP: classes, objects, constructors
public abstract class Vehicle {
    private final String vehicleId;
    private final String licensePlate;
    private final String ownerName;
    private final String ownerPhone;
    private LocalDateTime entryTime;
    private LocalDateTime exitTime;
    private String assignedSlotId;

    // Constructor
    public Vehicle(String licensePlate, String ownerName, String ownerPhone) {
        this.vehicleId = UUID.randomUUID().toString().substring(0, 8).toUpperCase();
        this.licensePlate = licensePlate.toUpperCase().trim();
        this.ownerName = ownerName;
        this.ownerPhone = ownerPhone;
        this.entryTime = LocalDateTime.now();
    }

    // Abstract methods - enforcing contract via abstraction
    public abstract VehicleType getType();
    public abstract double getHourlyRate();
    public abstract int getRequiredSlotSize(); // 1=small, 2=medium, 3=large

    // Getters
    public String getVehicleId() { return vehicleId; }
    public String getLicensePlate() { return licensePlate; }
    public String getOwnerName() { return ownerName; }
    public String getOwnerPhone() { return ownerPhone; }
    public LocalDateTime getEntryTime() { return entryTime; }
    public LocalDateTime getExitTime() { return exitTime; }
    public String getAssignedSlotId() { return assignedSlotId; }

    public void setExitTime(LocalDateTime exitTime) { this.exitTime = exitTime; }
    public void setAssignedSlotId(String slotId) { this.assignedSlotId = slotId; }

    // Calculate parking duration in minutes
    public long getParkingDurationMinutes() {
        LocalDateTime end = (exitTime != null) ? exitTime : LocalDateTime.now();
        return java.time.Duration.between(entryTime, end).toMinutes();
    }

    // Calculate fee
    public double calculateFee() {
        long minutes = getParkingDurationMinutes();
        double hours = Math.ceil(minutes / 60.0); // Bill per hour, rounding up
        if (hours < 1) hours = 1; // Minimum 1 hour charge
        return hours * getHourlyRate();
    }

    @Override
    public String toString() {
        return String.format("[%s] %s | %s | %s", getType(), licensePlate, ownerName, vehicleId);
    }
}
