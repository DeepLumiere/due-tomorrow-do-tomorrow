package com.parking.exception;

class VehicleNotFoundException extends ParkingException {
    public VehicleNotFoundException(String identifier) {
        super("Vehicle not found: " + identifier, "VEHICLE_NOT_FOUND");
    }
}

class DuplicateVehicleException extends ParkingException {
    public DuplicateVehicleException(String licensePlate) {
        super("Vehicle with license plate " + licensePlate + " is already parked.", "DUPLICATE_VEHICLE");
    }
}

class InvalidTicketException extends ParkingException {
    public InvalidTicketException(String ticketId) {
        super("Invalid or already processed ticket: " + ticketId, "INVALID_TICKET");
    }
}
