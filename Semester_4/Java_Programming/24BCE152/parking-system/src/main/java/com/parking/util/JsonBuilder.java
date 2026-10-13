package com.parking.util;

import com.parking.model.*;

import java.time.format.DateTimeFormatter;
import java.util.List;
import java.util.Map;

// Utility class for building JSON responses
public class JsonBuilder {
    private static final DateTimeFormatter FMT = DateTimeFormatter.ofPattern("dd-MM-yyyy HH:mm:ss");

    public static String success(String data) {
        return "{\"status\":\"success\",\"data\":" + data + "}";
    }

    public static String error(String message, String code) {
        return "{\"status\":\"error\",\"code\":\"" + code + "\",\"message\":" + quote(message) + "}";
    }

    public static String ticketToJson(ParkingTicket ticket, Vehicle vehicle) {
        return "{" +
                "\"ticketId\":" + quote(ticket.getTicketId()) + "," +
                "\"vehicleId\":" + quote(ticket.getVehicleId()) + "," +
                "\"licensePlate\":" + quote(ticket.getLicensePlate()) + "," +
                "\"slotId\":" + quote(ticket.getSlotId()) + "," +
                "\"entryTime\":" + quote(ticket.getFormattedEntryTime()) + "," +
                "\"exitTime\":" + quote(ticket.getFormattedExitTime()) + "," +
                "\"status\":" + quote(ticket.getStatus().toString()) + "," +
                "\"vehicleType\":" + quote(vehicle != null ? vehicle.getType().getDisplayName() : "N/A") + "," +
                "\"ownerName\":" + quote(vehicle != null ? vehicle.getOwnerName() : "N/A") + "," +
                "\"ownerPhone\":" + quote(vehicle != null ? vehicle.getOwnerPhone() : "N/A") + "," +
                "\"durationMinutes\":" + (vehicle != null ? vehicle.getParkingDurationMinutes() : 0) + "," +
                "\"estimatedFee\":" + (vehicle != null ? vehicle.calculateFee() : 0) + "," +
                "\"amountPaid\":" + ticket.getAmountPaid() +
                "}";
    }

    public static String slotToJson(ParkingSlot slot) {
        return "{" +
                "\"slotId\":" + quote(slot.getSlotId()) + "," +
                "\"floor\":" + slot.getFloor() + "," +
                "\"slotNumber\":" + slot.getSlotNumber() + "," +
                "\"size\":" + quote(slot.getSize().toString()) + "," +
                "\"status\":" + quote(slot.getStatus().toString()) + "," +
                "\"isEVCharging\":" + slot.isEVCharging() + "," +
                "\"isHandicapped\":" + slot.isHandicapped() + "," +
                "\"occupiedBy\":" + quote(slot.getOccupiedByVehicleId() != null ? slot.getOccupiedByVehicleId() : "") +
                "}";
    }

    public static String statsToJson(Map<String, Integer> stats, double revenue, String lotName) {
        return "{" +
                "\"lotName\":" + quote(lotName) + "," +
                "\"totalSlots\":" + stats.get("totalSlots") + "," +
                "\"available\":" + stats.get("available") + "," +
                "\"occupied\":" + stats.get("occupied") + "," +
                "\"smallAvail\":" + stats.get("smallAvail") + "," +
                "\"mediumAvail\":" + stats.get("mediumAvail") + "," +
                "\"largeAvail\":" + stats.get("largeAvail") + "," +
                "\"evAvail\":" + stats.get("evAvail") + "," +
                "\"handicappedAvail\":" + stats.get("handicappedAvail") + "," +
                "\"activeVehicles\":" + stats.get("activeVehicles") + "," +
                "\"totalCompleted\":" + stats.get("totalCompleted") + "," +
                "\"totalRevenue\":" + revenue +
                "}";
    }

    public static String listToJson(List<String> items) {
        return "[" + String.join(",", items) + "]";
    }

    private static String quote(String s) {
        if (s == null) return "\"\"";
        return "\"" + s.replace("\\", "\\\\").replace("\"", "\\\"") + "\"";
    }
}
