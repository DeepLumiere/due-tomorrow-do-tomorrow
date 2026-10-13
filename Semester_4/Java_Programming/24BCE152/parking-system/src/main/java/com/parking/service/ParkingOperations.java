package com.parking.service;

import com.parking.exception.ParkingException;
import com.parking.model.ParkingSlot;
import com.parking.model.ParkingTicket;
import com.parking.model.Vehicle;

import java.util.List;
import java.util.Map;

// Interface concept - defines contract for parking operations
public interface ParkingOperations {
    ParkingTicket checkIn(Vehicle vehicle) throws ParkingException;
    ParkingTicket checkOut(String ticketId) throws ParkingException;
    ParkingTicket findTicketByLicensePlate(String licensePlate) throws ParkingException;
    List<ParkingSlot> getAvailableSlots();
    List<ParkingTicket> getActiveTickets();
    List<ParkingTicket> getCompletedTickets();
    Map<String, Integer> getOccupancyStats();
    double getTotalRevenue();
}

// Interface for payment processing
interface PaymentProcessor {
    double calculateAmount(Vehicle vehicle) throws ParkingException;
    boolean processPayment(String ticketId, double amount) throws ParkingException;
    String generateReceipt(ParkingTicket ticket, Vehicle vehicle);
}
