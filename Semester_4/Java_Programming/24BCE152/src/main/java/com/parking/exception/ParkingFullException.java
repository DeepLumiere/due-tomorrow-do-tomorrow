package com.parking.exception;

public class ParkingFullException extends ParkingException {
    public ParkingFullException(String vehicleType) {
        super("No available slot for vehicle type: " + vehicleType + ". Parking lot is full.", "PARKING_FULL");
    }
}
