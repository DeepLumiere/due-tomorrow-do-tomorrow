package com.parking.exception;

// Custom Exception Hierarchy - Exception Handling concept

public class ParkingException extends Exception {
    private final String errorCode;

    public ParkingException(String message) {
        super(message);
        this.errorCode = "PARKING_ERROR";
    }

    public ParkingException(String message, String errorCode) {
        super(message);
        this.errorCode = errorCode;
    }

    public ParkingException(String message, Throwable cause) {
        super(message, cause);
        this.errorCode = "PARKING_ERROR";
    }

    public String getErrorCode() { return errorCode; }
}
