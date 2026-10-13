package com.parking.model;

import com.parking.exception.ParkingException;

public class VehicleFactory {
    public static Vehicle createVehicle(String type, String licensePlate, String ownerName, String ownerPhone)
            throws ParkingException {
        if (licensePlate == null || licensePlate.isBlank())
            throw new ParkingException("License plate cannot be empty");
        if (ownerName == null || ownerName.isBlank())
            throw new ParkingException("Owner name cannot be empty");

        return switch (type.toUpperCase()) {
            case "MOTORCYCLE" -> new Motorcycle(licensePlate, ownerName, ownerPhone);
            case "CAR" -> new Car(licensePlate, ownerName, ownerPhone);
            case "TRUCK" -> new Truck(licensePlate, ownerName, ownerPhone);
            case "ELECTRIC_CAR" -> new ElectricCar(licensePlate, ownerName, ownerPhone);
            case "HANDICAPPED" -> new HandicappedVehicle(licensePlate, ownerName, ownerPhone);
            default -> throw new ParkingException("Unknown vehicle type: " + type);
        };
    }
}
