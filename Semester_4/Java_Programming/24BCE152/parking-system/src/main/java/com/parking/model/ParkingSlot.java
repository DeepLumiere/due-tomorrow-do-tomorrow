package com.parking.model;

public class ParkingSlot {
    public enum SlotSize { SMALL, MEDIUM, LARGE }
    public enum SlotStatus { AVAILABLE, OCCUPIED, RESERVED, MAINTENANCE }

    private final String slotId;
    private final int floor;
    private final int slotNumber;
    private final SlotSize size;
    private SlotStatus status;
    private String occupiedByVehicleId;
    private boolean isEVCharging;
    private boolean isHandicapped;

    public ParkingSlot(String slotId, int floor, int slotNumber, SlotSize size) {
        this.slotId = slotId;
        this.floor = floor;
        this.slotNumber = slotNumber;
        this.size = size;
        this.status = SlotStatus.AVAILABLE;
        this.isEVCharging = false;
        this.isHandicapped = false;
    }

    public boolean isAvailable() { return status == SlotStatus.AVAILABLE; }

    public boolean canFit(Vehicle vehicle) {
        if (!isAvailable()) return false;
        int required = vehicle.getRequiredSlotSize();
        int capacity = switch (size) {
            case SMALL -> 1;
            case MEDIUM -> 2;
            case LARGE -> 3;
        };
        // Special slot matching for EV and handicapped
        if (vehicle.getType() == VehicleType.ELECTRIC_CAR && !isEVCharging) return false;
        if (vehicle.getType() == VehicleType.HANDICAPPED && !isHandicapped) {
            // Handicapped can park in any slot if no handicapped slot available
        }
        return capacity >= required;
    }

    public void occupy(String vehicleId) {
        this.occupiedByVehicleId = vehicleId;
        this.status = SlotStatus.OCCUPIED;
    }

    public void vacate() {
        this.occupiedByVehicleId = null;
        this.status = SlotStatus.AVAILABLE;
    }

    // Getters & Setters
    public String getSlotId() { return slotId; }
    public int getFloor() { return floor; }
    public int getSlotNumber() { return slotNumber; }
    public SlotSize getSize() { return size; }
    public SlotStatus getStatus() { return status; }
    public String getOccupiedByVehicleId() { return occupiedByVehicleId; }
    public boolean isEVCharging() { return isEVCharging; }
    public boolean isHandicapped() { return isHandicapped; }

    public void setStatus(SlotStatus status) { this.status = status; }
    public void setEVCharging(boolean EVCharging) { isEVCharging = EVCharging; }
    public void setHandicapped(boolean handicapped) { isHandicapped = handicapped; }

    @Override
    public String toString() {
        return String.format("Slot[%s] Floor:%d #%d (%s) - %s", slotId, floor, slotNumber, size, status);
    }
}
