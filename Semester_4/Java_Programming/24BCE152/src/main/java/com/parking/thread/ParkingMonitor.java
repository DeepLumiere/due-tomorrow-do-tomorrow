package com.parking.thread;

import com.parking.service.ParkingLotService;
import com.parking.util.FileLogger;

import java.time.LocalDateTime;
import java.time.format.DateTimeFormatter;
import java.util.Map;
import java.util.concurrent.Executors;
import java.util.concurrent.ScheduledExecutorService;
import java.util.concurrent.TimeUnit;

// Multithreading concept - Background monitoring using ScheduledExecutorService
public class ParkingMonitor {
    private final ParkingLotService service;
    private final FileLogger logger;
    private final ScheduledExecutorService scheduler;
    private volatile boolean running = false;

    public ParkingMonitor(ParkingLotService service, FileLogger logger) {
        this.service = service;
        this.logger = logger;
        this.scheduler = Executors.newScheduledThreadPool(2);
    }

    public void start() {
        running = true;

        // Task 1: Log occupancy stats every 60 seconds
        scheduler.scheduleAtFixedRate(this::logOccupancySnapshot, 30, 60, TimeUnit.SECONDS);

        // Task 2: Check for long-parked vehicles every 5 minutes (>12 hours)
        scheduler.scheduleAtFixedRate(this::checkOverdueVehicles, 60, 300, TimeUnit.SECONDS);
    }

    private void logOccupancySnapshot() {
        try {
            Map<String, Integer> stats = service.getOccupancyStats();
            String msg = String.format("SNAPSHOT | Total:%d | Occupied:%d | Available:%d | Revenue:₹%.2f",
                    stats.get("totalSlots"),
                    stats.get("occupied"),
                    stats.get("available"),
                    service.getTotalRevenue());
            logger.log("MONITOR", msg);
        } catch (Exception e) {
            logger.log("MONITOR_ERROR", "Failed to log snapshot: " + e.getMessage());
        }
    }

    private void checkOverdueVehicles() {
        try {
            service.getActiveTickets().forEach(ticket -> {
                long hours = java.time.Duration.between(ticket.getEntryTime(), LocalDateTime.now()).toHours();
                if (hours >= 12) {
                    logger.log("OVERDUE_ALERT", "Vehicle " + ticket.getLicensePlate()
                            + " has been parked for " + hours + " hours! Slot: " + ticket.getSlotId());
                }
            });
        } catch (Exception e) {
            logger.log("MONITOR_ERROR", "Overdue check failed: " + e.getMessage());
        }
    }

    public void stopMonitoring() {
        running = false;
        scheduler.shutdownNow();
        logger.log("MONITOR", "Monitoring stopped.");
    }

    public boolean isRunning() { return running; }
}
