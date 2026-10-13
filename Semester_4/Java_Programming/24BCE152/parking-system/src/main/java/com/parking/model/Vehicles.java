package com.parking.model;

// Inheritance - All concrete vehicle types extend Vehicle

class Motorcycle extends Vehicle {
    public Motorcycle(String licensePlate, String ownerName, String ownerPhone) {
        super(licensePlate, ownerName, ownerPhone);
    }
    @Override public VehicleType getType() { return VehicleType.MOTORCYCLE; }
    @Override public double getHourlyRate() { return 20.0; }
    @Override public int getRequiredSlotSize() { return 1; }
}

class Car extends Vehicle {
    public Car(String licensePlate, String ownerName, String ownerPhone) {
        super(licensePlate, ownerName, ownerPhone);
    }
    @Override public VehicleType getType() { return VehicleType.CAR; }
    @Override public double getHourlyRate() { return 50.0; }
    @Override public int getRequiredSlotSize() { return 2; }
}

class Truck extends Vehicle {
    public Truck(String licensePlate, String ownerName, String ownerPhone) {
        super(licensePlate, ownerName, ownerPhone);
    }
    @Override public VehicleType getType() { return VehicleType.TRUCK; }
    @Override public double getHourlyRate() { return 100.0; }
    @Override public int getRequiredSlotSize() { return 3; }
}

class ElectricCar extends Vehicle {
    private static final double EV_DISCOUNT = 0.8;
    public ElectricCar(String licensePlate, String ownerName, String ownerPhone) {
        super(licensePlate, ownerName, ownerPhone);
    }
    @Override public VehicleType getType() { return VehicleType.ELECTRIC_CAR; }
    @Override public double getHourlyRate() { return 50.0 * EV_DISCOUNT; }
    @Override public int getRequiredSlotSize() { return 2; }
}

class HandicappedVehicle extends Vehicle {
    public HandicappedVehicle(String licensePlate, String ownerName, String ownerPhone) {
        super(licensePlate, ownerName, ownerPhone);
    }
    @Override public VehicleType getType() { return VehicleType.HANDICAPPED; }
    @Override public double getHourlyRate() { return 25.0; }
    @Override public int getRequiredSlotSize() { return 2; }
}
